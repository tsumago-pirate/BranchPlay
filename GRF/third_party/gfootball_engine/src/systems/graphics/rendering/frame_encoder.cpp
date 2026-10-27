#include "frame_encoder.hpp"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>

#ifdef __APPLE__

#define GL_SILENCE_DEPRECATION
#include <OpenGL/OpenGL.h>
#include <OpenGL/CGLIOSurface.h>
#include <OpenGL/gl3.h>

#include <CoreFoundation/CoreFoundation.h>
#include <CoreMedia/CoreMedia.h>
#include <CoreVideo/CoreVideo.h>
#include <VideoToolbox/VideoToolbox.h>

namespace blunted {

struct FrameEncoder::State {
  static const int kSlots = 6;
  struct Slot {
    CVPixelBufferRef pixels = nullptr;
    GLuint texture = 0;
    GLuint framebuffer = 0;
    bool busy = false;
  };
  int width = 0;
  int height = 0;
  GLuint source_texture = 0;
  GLuint vertex_array = 0;
  GLuint program = 0;
  Slot slots[kSlots];
  VTCompressionSessionRef session = nullptr;
  std::mutex packets_lock;
  std::vector<std::string> packets;
  std::atomic<bool> want_key{true};
  uint64_t frame_index = 0;
  bool ready = false;
  std::string codec;
  std::string avcc;
};

namespace {

void ReleaseCF(CFTypeRef ref) {
  if (ref) CFRelease(ref);
}

std::string CodecFromSps(const uint8_t* sps, size_t size) {
  if (size < 4) return "avc1.42001F";
  char text[16];
  std::snprintf(text, sizeof(text), "avc1.%02X%02X%02X", sps[1], sps[2], sps[3]);
  return text;
}

std::string BuildAvcc(const uint8_t* sps, size_t sps_size, const uint8_t* pps,
                      size_t pps_size) {
  std::string out;
  out.push_back(1);
  out.push_back(sps[1]);
  out.push_back(sps[2]);
  out.push_back(sps[3]);
  out.push_back(static_cast<char>(0xFF));
  out.push_back(static_cast<char>(0xE1));
  out.push_back(static_cast<char>((sps_size >> 8) & 0xFF));
  out.push_back(static_cast<char>(sps_size & 0xFF));
  out.append(reinterpret_cast<const char*>(sps), sps_size);
  out.push_back(1);
  out.push_back(static_cast<char>((pps_size >> 8) & 0xFF));
  out.push_back(static_cast<char>(pps_size & 0xFF));
  out.append(reinterpret_cast<const char*>(pps), pps_size);
  return out;
}

std::string PackConfig(int width, int height, const std::string& codec,
                       const std::string& avcc) {
  std::string out;
  out.push_back(1);
  out.push_back(static_cast<char>(width & 0xFF));
  out.push_back(static_cast<char>((width >> 8) & 0xFF));
  out.push_back(static_cast<char>(height & 0xFF));
  out.push_back(static_cast<char>((height >> 8) & 0xFF));
  out.push_back(static_cast<char>(codec.size()));
  out.append(codec);
  out.append(avcc);
  return out;
}

std::string PackFrame(uint8_t kind, uint64_t timestamp, const uint8_t* data,
                      size_t size) {
  std::string out;
  out.push_back(static_cast<char>(kind));
  for (int shift = 0; shift < 8; ++shift) {
    out.push_back(static_cast<char>((timestamp >> (8 * shift)) & 0xFF));
  }
  out.append(reinterpret_cast<const char*>(data), size);
  return out;
}

void ReleaseCaptureBindings() {
  glBindFramebuffer(GL_FRAMEBUFFER, 0);
  glBindTexture(GL_TEXTURE_2D, 0);
  glBindTexture(GL_TEXTURE_RECTANGLE, 0);
}

GLuint Compile(GLenum type, const char* source) {
  GLuint shader = glCreateShader(type);
  glShaderSource(shader, 1, &source, nullptr);
  glCompileShader(shader);
  GLint ok = 0;
  glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
  if (!ok) {
    char log[512];
    glGetShaderInfoLog(shader, sizeof(log), nullptr, log);
    std::fprintf(stderr, "Video shader: %s\n", log);
    glDeleteShader(shader);
    return 0;
  }
  return shader;
}

bool SetBool(VTCompressionSessionRef session, CFStringRef key, bool value) {
  return VTSessionSetProperty(session, key, value ? kCFBooleanTrue
                                                  : kCFBooleanFalse) == noErr;
}

bool SetInt(VTCompressionSessionRef session, CFStringRef key, int value) {
  CFNumberRef number = CFNumberCreate(kCFAllocatorDefault, kCFNumberIntType, &value);
  OSStatus status = VTSessionSetProperty(session, key, number);
  ReleaseCF(number);
  return status == noErr;
}

}  // namespace

void FrameEncoder::OnEncoded(void* refcon, void* source, int status, unsigned,
                             opaqueCMSampleBuffer* sample_ref) {
  State* state = static_cast<State*>(refcon);
  const int slot = static_cast<int>(reinterpret_cast<intptr_t>(source));
  auto release_slot = [&]() {
    if (slot < 0 || slot >= State::kSlots) return;
    std::lock_guard<std::mutex> guard(state->packets_lock);
    state->slots[slot].busy = false;
  };
  CMSampleBufferRef sample = sample_ref;
  if (status != noErr || sample == nullptr ||
      !CMSampleBufferDataIsReady(sample)) {
    release_slot();
    return;
  }
  CFArrayRef attachments = CMSampleBufferGetSampleAttachmentsArray(sample, false);
  bool key = true;
  if (attachments != nullptr && CFArrayGetCount(attachments) > 0) {
    CFDictionaryRef info = static_cast<CFDictionaryRef>(
        CFArrayGetValueAtIndex(attachments, 0));
    key = !CFDictionaryContainsKey(info, kCMSampleAttachmentKey_NotSync);
  }
  if (state->avcc.empty()) key = true;

  std::string config;
  if (key) {
    CMFormatDescriptionRef format = CMSampleBufferGetFormatDescription(sample);
    const uint8_t* sps = nullptr;
    const uint8_t* pps = nullptr;
    size_t sps_size = 0;
    size_t pps_size = 0;
    size_t count = 0;
    int nal_length = 4;
    if (CMVideoFormatDescriptionGetH264ParameterSetAtIndex(
            format, 0, &sps, &sps_size, &count, &nal_length) != noErr ||
        CMVideoFormatDescriptionGetH264ParameterSetAtIndex(
            format, 1, &pps, &pps_size, &count, &nal_length) != noErr) {
      release_slot();
      return;
    }
    state->codec = CodecFromSps(sps, sps_size);
    state->avcc = BuildAvcc(sps, sps_size, pps, pps_size);
    config = PackConfig(state->width, state->height, state->codec, state->avcc);
  }

  CMBlockBufferRef block = CMSampleBufferGetDataBuffer(sample);
  if (block == nullptr) {
    release_slot();
    return;
  }
  size_t length = CMBlockBufferGetDataLength(block);
  std::string bytes(length, '\0');
  if (CMBlockBufferCopyDataBytes(block, 0, length, &bytes[0]) != noErr) {
    release_slot();
    return;
  }
  CMTime pts = CMSampleBufferGetPresentationTimeStamp(sample);
  uint64_t timestamp = 0;
  if (pts.timescale > 0 && pts.value > 0) {
    timestamp = static_cast<uint64_t>(pts.value) * 1000000 /
                static_cast<uint64_t>(pts.timescale);
  }
  std::string frame = PackFrame(key ? 2 : 3, timestamp,
                                reinterpret_cast<const uint8_t*>(bytes.data()),
                                bytes.size());
  std::lock_guard<std::mutex> guard(state->packets_lock);
  if (!config.empty()) state->packets.push_back(config);
  state->packets.push_back(frame);
  if (slot >= 0 && slot < State::kSlots) state->slots[slot].busy = false;
}

FrameEncoder::FrameEncoder() : state_(new State) {}

FrameEncoder::~FrameEncoder() {
  if (state_->session != nullptr) {
    VTCompressionSessionCompleteFrames(state_->session, kCMTimeInvalid);
    VTCompressionSessionInvalidate(state_->session);
    ReleaseCF(state_->session);
  }
  if (state_->program) glDeleteProgram(state_->program);
  if (state_->vertex_array) glDeleteVertexArrays(1, &state_->vertex_array);
  for (int i = 0; i < State::kSlots; ++i) {
    if (state_->slots[i].framebuffer) {
      glDeleteFramebuffers(1, &state_->slots[i].framebuffer);
    }
    if (state_->slots[i].texture) glDeleteTextures(1, &state_->slots[i].texture);
    ReleaseCF(state_->slots[i].pixels);
  }
  if (state_->source_texture) glDeleteTextures(1, &state_->source_texture);
  delete state_;
}

void FrameEncoder::request_keyframe() { state_->want_key.store(true); }

std::vector<std::string> FrameEncoder::take() {
  std::lock_guard<std::mutex> guard(state_->packets_lock);
  std::vector<std::string> packets;
  packets.swap(state_->packets);
  return packets;
}

bool FrameEncoder::capture_and_encode(int width, int height) {
  if (width <= 0 || height <= 0) return false;
  State* state = state_;
  if (!state->ready || state->width != width || state->height != height) {
    if (state->session != nullptr) {
      VTCompressionSessionInvalidate(state->session);
      ReleaseCF(state->session);
      state->session = nullptr;
    }
    for (int i = 0; i < State::kSlots; ++i) {
      ReleaseCF(state->slots[i].pixels);
      state->slots[i].pixels = nullptr;
      state->slots[i].busy = false;
    }

    CFMutableDictionaryRef empty = CFDictionaryCreateMutable(
        kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks,
        &kCFTypeDictionaryValueCallBacks);
    CFMutableDictionaryRef attrs = CFDictionaryCreateMutable(
        kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks,
        &kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(attrs, kCVPixelBufferIOSurfacePropertiesKey, empty);
    CFDictionarySetValue(attrs, kCVPixelBufferOpenGLCompatibilityKey, kCFBooleanTrue);
    bool buffers_ready = true;
    for (int i = 0; i < State::kSlots; ++i) {
      CVReturn created = CVPixelBufferCreate(
          kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA, attrs,
          &state->slots[i].pixels);
      if (created != kCVReturnSuccess || state->slots[i].pixels == nullptr) {
        std::fprintf(stderr, "Video pixel buffer failed (%d)\n", created);
        buffers_ready = false;
        break;
      }
    }
    ReleaseCF(attrs);
    ReleaseCF(empty);
    if (!buffers_ready) return false;

    if (!state->source_texture) glGenTextures(1, &state->source_texture);
    glBindTexture(GL_TEXTURE_2D, state->source_texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA,
                 GL_UNSIGNED_BYTE, nullptr);

    for (int i = 0; i < State::kSlots; ++i) {
      IOSurfaceRef surface = CVPixelBufferGetIOSurface(state->slots[i].pixels);
      if (surface == nullptr) {
        ReleaseCaptureBindings();
        return false;
      }
      if (!state->slots[i].texture) glGenTextures(1, &state->slots[i].texture);
      glBindTexture(GL_TEXTURE_RECTANGLE, state->slots[i].texture);
      CGLError cgl = CGLTexImageIOSurface2D(
          CGLGetCurrentContext(), GL_TEXTURE_RECTANGLE, GL_RGBA, width, height,
          GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, surface, 0);
      if (cgl != kCGLNoError) {
        std::fprintf(stderr, "Video surface failed (%d)\n", cgl);
        ReleaseCaptureBindings();
        return false;
      }
      if (!state->slots[i].framebuffer) {
        glGenFramebuffers(1, &state->slots[i].framebuffer);
      }
      glBindFramebuffer(GL_FRAMEBUFFER, state->slots[i].framebuffer);
      glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                             GL_TEXTURE_RECTANGLE, state->slots[i].texture, 0);
      if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        std::fprintf(stderr, "Video framebuffer incomplete\n");
        ReleaseCaptureBindings();
        return false;
      }
    }

    if (!state->program) {
      const char* vertex =
          "#version 150\n"
          "out vec2 uv;\n"
          "void main() {\n"
          "  vec2 corner = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);\n"
          "  uv = corner;\n"
          "  gl_Position = vec4(corner * 2.0 - 1.0, 0.0, 1.0);\n"
          "}\n";
      // The window stores the picture bottom-up. The video's first row is the
      // top, so the sample flips. The surface keeps red, green, and blue.
      const char* fragment =
          "#version 150\n"
          "in vec2 uv;\n"
          "out vec4 color;\n"
          "uniform sampler2D source;\n"
          "void main() {\n"
          "  color = texture(source, vec2(uv.x, 1.0 - uv.y));\n"
          "  color.a = 1.0;\n"
          "}\n";
      GLuint vs = Compile(GL_VERTEX_SHADER, vertex);
      GLuint fs = Compile(GL_FRAGMENT_SHADER, fragment);
      if (!vs || !fs) {
        ReleaseCaptureBindings();
        return false;
      }
      state->program = glCreateProgram();
      glAttachShader(state->program, vs);
      glAttachShader(state->program, fs);
      glLinkProgram(state->program);
      glDeleteShader(vs);
      glDeleteShader(fs);
      GLint linked = 0;
      glGetProgramiv(state->program, GL_LINK_STATUS, &linked);
      if (!linked) {
        char log[512];
        glGetProgramInfoLog(state->program, sizeof(log), nullptr, log);
        std::fprintf(stderr, "Video program: %s\n", log);
        ReleaseCaptureBindings();
        return false;
      }
      glGenVertexArrays(1, &state->vertex_array);
    }

    VTCompressionSessionRef session = nullptr;
    OSStatus opened = VTCompressionSessionCreate(
        kCFAllocatorDefault, width, height, kCMVideoCodecType_H264,
        nullptr, nullptr, nullptr, OnEncoded, state, &session);
    if (opened != noErr || session == nullptr) {
      std::fprintf(stderr, "Video encoder failed (%d)\n", opened);
      ReleaseCaptureBindings();
      return false;
    }
    SetBool(session, kVTCompressionPropertyKey_RealTime, true);
    SetBool(session, kVTCompressionPropertyKey_AllowFrameReordering, false);
    SetBool(session, kVTCompressionPropertyKey_PrioritizeEncodingSpeedOverQuality,
            true);
    VTSessionSetProperty(session, kVTCompressionPropertyKey_ProfileLevel,
                         kVTProfileLevel_H264_Baseline_AutoLevel);
    SetInt(session, kVTCompressionPropertyKey_AverageBitRate, 30000000);
    SetInt(session, kVTCompressionPropertyKey_ExpectedFrameRate, 100);
    SetInt(session, kVTCompressionPropertyKey_MaxKeyFrameInterval, 300);
    SetInt(session, kVTCompressionPropertyKey_MaxFrameDelayCount, 0);
    VTCompressionSessionPrepareToEncodeFrames(session);
    state->session = session;
    state->width = width;
    state->height = height;
    state->ready = true;
    state->want_key.store(true);
    ReleaseCaptureBindings();
  }

  GLint previous_read = 0;
  GLint previous_draw = 0;
  GLint previous_texture = 0;
  GLint previous_program = 0;
  GLint previous_array = 0;
  GLint previous_viewport[4] = {0, 0, 0, 0};
  GLint previous_active = 0;
  GLint previous_buffer = 0;
  glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &previous_read);
  glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &previous_draw);
  glGetIntegerv(GL_TEXTURE_BINDING_2D, &previous_texture);
  glGetIntegerv(GL_CURRENT_PROGRAM, &previous_program);
  glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &previous_array);
  glGetIntegerv(GL_VIEWPORT, previous_viewport);
  glGetIntegerv(GL_ACTIVE_TEXTURE, &previous_active);
  glGetIntegerv(GL_READ_BUFFER, &previous_buffer);
  GLboolean depth = glIsEnabled(GL_DEPTH_TEST);
  GLboolean blend = glIsEnabled(GL_BLEND);
  GLboolean cull = glIsEnabled(GL_CULL_FACE);
  GLboolean scissor = glIsEnabled(GL_SCISSOR_TEST);

  int slot = -1;
  {
    std::lock_guard<std::mutex> guard(state->packets_lock);
    for (int i = 0; i < State::kSlots; ++i) {
      if (!state->slots[i].busy) {
        state->slots[i].busy = true;
        slot = i;
        break;
      }
    }
  }
  if (slot < 0) {
    VTCompressionSessionCompleteFrames(state->session, kCMTimeInvalid);
    std::lock_guard<std::mutex> guard(state->packets_lock);
    for (int i = 0; i < State::kSlots; ++i) {
      if (!state->slots[i].busy) {
        state->slots[i].busy = true;
        slot = i;
        break;
      }
    }
  }
  if (slot < 0) return false;

  glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);
  glReadBuffer(GL_BACK);
  glBindTexture(GL_TEXTURE_2D, state->source_texture);
  glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 0, 0, width, height);

  glBindFramebuffer(GL_DRAW_FRAMEBUFFER, state->slots[slot].framebuffer);
  glViewport(0, 0, width, height);
  glDisable(GL_DEPTH_TEST);
  glDisable(GL_BLEND);
  glDisable(GL_CULL_FACE);
  glDisable(GL_SCISSOR_TEST);
  glUseProgram(state->program);
  glBindVertexArray(state->vertex_array);
  glActiveTexture(GL_TEXTURE0);
  glBindTexture(GL_TEXTURE_2D, state->source_texture);
  glUniform1i(glGetUniformLocation(state->program, "source"), 0);
  glDrawArrays(GL_TRIANGLES, 0, 3);
  glFinish();

  glBindFramebuffer(GL_READ_FRAMEBUFFER, previous_read);
  glBindFramebuffer(GL_DRAW_FRAMEBUFFER, previous_draw);
  glReadBuffer(previous_buffer);
  glUseProgram(previous_program);
  glBindVertexArray(previous_array);
  glActiveTexture(previous_active);
  glBindTexture(GL_TEXTURE_2D, previous_texture);
  glViewport(previous_viewport[0], previous_viewport[1], previous_viewport[2],
             previous_viewport[3]);
  if (depth) glEnable(GL_DEPTH_TEST);
  if (blend) glEnable(GL_BLEND);
  if (cull) glEnable(GL_CULL_FACE);
  if (scissor) glEnable(GL_SCISSOR_TEST);

  bool key = state->want_key.exchange(false);
  CFMutableDictionaryRef options = nullptr;
  if (key) {
    options = CFDictionaryCreateMutable(kCFAllocatorDefault, 1,
                                        &kCFTypeDictionaryKeyCallBacks,
                                        &kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(options, kVTEncodeFrameOptionKey_ForceKeyFrame,
                         kCFBooleanTrue);
  }
  CMTime pts = CMTimeMake(static_cast<int64_t>(state->frame_index), 100);
  state->frame_index += 1;
  OSStatus encoded = VTCompressionSessionEncodeFrame(
      state->session, state->slots[slot].pixels, pts, kCMTimeInvalid, options,
      reinterpret_cast<void*>(static_cast<intptr_t>(slot)), nullptr);
  ReleaseCF(options);
  if (encoded != noErr) {
    std::lock_guard<std::mutex> guard(state->packets_lock);
    state->slots[slot].busy = false;
    std::fprintf(stderr, "Video encode failed (%d)\n", encoded);
    return false;
  }
  return true;
}

}  // namespace blunted

#else

namespace blunted {

struct FrameEncoder::State {};

FrameEncoder::FrameEncoder() : state_(nullptr) {}
FrameEncoder::~FrameEncoder() {}
bool FrameEncoder::capture_and_encode(int, int) { return false; }
void FrameEncoder::request_keyframe() {}
std::vector<std::string> FrameEncoder::take() { return {}; }

}  // namespace blunted

#endif
