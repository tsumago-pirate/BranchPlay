// Copyright 2019 Google LLC & Bastiaan Konings
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// written by bastiaan konings schuiling 2008 - 2014
// this work is public domain. the code is undocumented, scruffy, untested, and should generally not be used for anything important.
// i do not offer support, so don't ask. to be used for inspiration :)

#include "opengl_renderer3d.hpp"

#ifndef GL_GLEXT_PROTOTYPES
#define GL_GLEXT_PROTOTYPES
#endif
#ifdef __APPLE__
#define GL_SILENCE_DEPRECATION
#include <OpenGL/gl3.h>
#include <OpenGL/gl3ext.h>
#else
#include <GL/gl.h>
#endif

#ifdef __linux__
#include <GL/glext.h>
#define EGL_EGLEXT_PROTOTYPES
#include <EGL/egl.h>
#include <EGL/eglext.h>
#elif defined(WIN32)
#include <SDL2/SDL_opengl_glext.h>
#endif

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "wrap_SDL.h"
#ifdef __APPLE__
#include <SDL2/SDL_image.h>
#include <SDL2/SDL_syswm.h>
#include <objc/message.h>
#include <objc/runtime.h>
#endif

#include "../../../base/geometry/aabb.hpp"
#include "../../../base/geometry/trianglemeshutils.hpp"
#include "../../../base/log.hpp"
#include "../../../base/math/bluntmath.hpp"
#include "../../../base/sdl_surface.hpp"
#include "../../../base/utils.hpp"
#include "../../../main.hpp"
#include "../../../types/command.hpp"
#include "../../../utils/gui2/widgets/image.hpp"
#include "../resources/texture.hpp"

namespace blunted {

#ifdef __APPLE__
// A fullscreen space was taking the display color and the picture went dark.
// Keep the same sRGB window color the match has when it first opens.
void KeepWindowColor(SDL_Window *window) {
  if (!window) return;
  SDL_SysWMinfo info;
  SDL_VERSION(&info.version);
  if (!SDL_GetWindowWMInfo(window, &info)) return;
  if (info.subsystem != SDL_SYSWM_COCOA) return;
  id nswindow = (id)info.info.cocoa.window;
  if (!nswindow) return;
  Class spaceClass = objc_getClass("NSColorSpace");
  if (!spaceClass) return;
  id srgb = ((id (*)(Class, SEL))objc_msgSend)(
      spaceClass, sel_registerName("sRGBColorSpace"));
  id current = ((id (*)(id, SEL))objc_msgSend)(
      nswindow, sel_registerName("colorSpace"));
  if (current == srgb) return;
  ((void (*)(id, SEL, id))objc_msgSend)(
      nswindow, sel_registerName("setColorSpace:"), srgb);
}
#else
void KeepWindowColor(SDL_Window *) {}
#endif

struct GLfunctions {
#define SDL_PROC(ret,func,params) ret (APIENTRYP func) params;
#include "sdl_glfuncs.h"
#undef SDL_PROC
};

GLfunctions mapping;

OpenGLRenderer3D::OpenGLRenderer3D() {
  DO_VALIDATION;
  FOV = 45;
  overallBrightness = 128;

  _cache_activeTextureUnit = -1;

  currentShader = shaders.end();

  // SetPriorityClass(thread.native_handle(), HIGH_PRIORITY_CLASS);
};

OpenGLRenderer3D::~OpenGLRenderer3D() {
    DO_VALIDATION;
};

void OpenGLRenderer3D::ReadScreen() {
  // The visible picture includes the timeline strip. A saved frame is the
  // framing above that strip, so a clip stays the same shape it had before.
  int x = 0;
  int y = 0;
  int w = context_width;
  int h = context_height;
  GetPresentRect(0, 0, context_width, context_height, x, y, w, h);
  int band = BottomBandPixels();
  if (band > 0 && y < band && h - (band - y) >= 16) {
    int drop = band - y;
    y += drop;
    h -= drop;
  }
  if (w < 2 || h < 2) {
    x = 0;
    y = 0;
    w = context_width;
    h = context_height;
  }
  last_screen_.resize(w * h * 3);
  // Default pack alignment pads rows. A width that is not a multiple of four
  // would then not match this buffer, and the key-moment video would tear.
  glPixelStorei(GL_PACK_ALIGNMENT, 1);
  mapping.glReadPixels(x, y, w, h, GL_RGB, GL_UNSIGNED_BYTE,
                       &last_screen_[0]);
}

void OpenGLRenderer3D::SwapBuffers() {
  DO_VALIDATION;
  // The visible window is polled from the match loop so those events can
  // move the camera. A hidden window has no other reader, so it still
  // watches for the close here.
  if (window && !present_window_) {
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
      bool closed = event.type == SDL_QUIT;
      if (event.type == SDL_WINDOWEVENT &&
          event.window.event == SDL_WINDOWEVENT_CLOSE &&
          event.window.windowID == SDL_GetWindowID(window)) {
        closed = true;
      }
      if (closed) {
        std::_Exit(0);
      }
    }
  }
  if (window) {
    HoldPlaybackFrame();
    SDL_GL_SwapWindow(window);
  }
  // A visible window is the picture. Copying it off the GPU is only needed
  // when the window is hidden and a caller reads the frame back.
  if (!present_window_) {
    ReadScreen();
  }
}

int OpenGLRenderer3D::ToHudX(int x) const {
  int window_w = 0;
  int window_h = 0;
  SDL_GetWindowSize(window, &window_w, &window_h);
  if (window_w <= 0) return x;
  return int(std::lround(x * (double)context_width / (double)window_w));
}

int OpenGLRenderer3D::ToHudY(int y) const {
  int window_w = 0;
  int window_h = 0;
  SDL_GetWindowSize(window, &window_w, &window_h);
  (void)window_w;
  if (window_h <= 0) return y;
  return int(std::lround(y * (double)context_height / (double)window_h));
}

bool OpenGLRenderer3D::PresentsWindow() const {
  return present_window_;
}

void OpenGLRenderer3D::SetMouseLook(bool on) {
  SDL_SetRelativeMouseMode(on ? SDL_TRUE : SDL_FALSE);
}

WindowControl OpenGLRenderer3D::PollWindow(bool free_look) {
  DO_VALIDATION;
  WindowControl input;
  if (!free_look && SDL_GetRelativeMouseMode() == SDL_TRUE) {
    SDL_SetRelativeMouseMode(SDL_FALSE);
  }
  if (!window) return input;
  SDL_Event event;
  while (SDL_PollEvent(&event)) {
    bool closed = event.type == SDL_QUIT;
    if (event.type == SDL_WINDOWEVENT &&
        event.window.event == SDL_WINDOWEVENT_CLOSE &&
        event.window.windowID == SDL_GetWindowID(window)) {
      closed = true;
    }
    if (closed) {
      std::_Exit(0);
    }
    if (event.type == SDL_MOUSEBUTTONDOWN &&
        event.button.button == SDL_BUTTON_LEFT) {
      mouse_down_ = true;
      mouse_dragged_ = false;
      mouse_down_x_ = ToHudX(event.button.x);
      mouse_down_y_ = ToHudY(event.button.y);
      input.pressed = true;
      input.press_x = mouse_down_x_;
      input.press_y = mouse_down_y_;
    }
    if (event.type == SDL_MOUSEMOTION && mouse_down_) {
      int dx = ToHudX(event.motion.x) - mouse_down_x_;
      int dy = ToHudY(event.motion.y) - mouse_down_y_;
      if (dx * dx + dy * dy > 25) mouse_dragged_ = true;
    }
    if (event.type == SDL_MOUSEBUTTONUP &&
        event.button.button == SDL_BUTTON_LEFT) {
      input.released = true;
      if (mouse_down_ && !mouse_dragged_) {
        input.clicked = true;
        input.click_x = mouse_down_x_;
        input.click_y = mouse_down_y_;
        input.clicks = (int)event.button.clicks;
      }
      mouse_down_ = false;
      if (!right_down_) SDL_SetRelativeMouseMode(SDL_FALSE);
    }
    if (event.type == SDL_MOUSEBUTTONDOWN &&
        event.button.button == SDL_BUTTON_RIGHT) {
      right_down_ = true;
    }
    if (event.type == SDL_MOUSEBUTTONUP &&
        event.button.button == SDL_BUTTON_RIGHT) {
      right_down_ = false;
      if (!mouse_down_) SDL_SetRelativeMouseMode(SDL_FALSE);
    }
    if (event.type == SDL_MOUSEMOTION &&
        SDL_GetRelativeMouseMode() == SDL_TRUE) {
      input.look_dx += event.motion.xrel;
      input.look_dy += event.motion.yrel;
    }
    if (event.type == SDL_KEYDOWN && event.key.repeat == 0) {
      SDL_Keycode key = event.key.keysym.sym;
      bool command = (event.key.keysym.mod & KMOD_GUI) != 0;
      if (key == SDLK_F11 || (key == SDLK_f && command)) {
        SetFullscreen(!Fullscreen());
      } else if (key == SDLK_f) {
        input.freeze = true;
      }
      if (key == SDLK_ESCAPE) input.escape = true;
      if (key == SDLK_BACKSPACE || key == SDLK_DELETE) input.remove_players = true;
      if (key == SDLK_l) input.lens = true;
      if (key == SDLK_LEFTBRACKET || key == SDLK_COMMA) input.view_prev = true;
      if (key == SDLK_RIGHTBRACKET || key == SDLK_PERIOD) input.view_next = true;
    }
  }
  input.mouse_held = mouse_down_;
  input.look_held = right_down_;
  input.dragged = mouse_dragged_;
  int mouse_x = 0;
  int mouse_y = 0;
  SDL_GetMouseState(&mouse_x, &mouse_y);
  input.x = ToHudX(mouse_x);
  input.y = ToHudY(mouse_y);
  const Uint8* keys = SDL_GetKeyboardState(NULL);
  input.forward = keys[SDL_SCANCODE_W] != 0;
  input.back = keys[SDL_SCANCODE_S] != 0;
  input.left = keys[SDL_SCANCODE_A] != 0;
  input.right = keys[SDL_SCANCODE_D] != 0;
  input.down = keys[SDL_SCANCODE_Q] != 0;
  input.up = keys[SDL_SCANCODE_E] != 0;
  input.fast = keys[SDL_SCANCODE_LSHIFT] != 0 ||
               keys[SDL_SCANCODE_RSHIFT] != 0;
  return input;
}

void OpenGLRenderer3D::RememberClip(const Matrix4 &projection,
                                    const Matrix4 &view, int vp_x, int vp_y,
                                    int vp_w, int vp_h) {
  if (vp_w < 1 || vp_h < 1) {
    clip_ready_ = false;
    return;
  }
  clip_ = projection * view;
  clip_inverse_ = clip_.GetInverse();
  // The picture viewport, including the timeline strip. The projection
  // leaves the extra view along the bottom edge of this rectangle.
  picture_x_ = vp_x;
  picture_y_ = vp_y;
  picture_w_ = vp_w;
  picture_h_ = vp_h;
  vp_x_ = vp_x;
  vp_y_ = vp_y;
  vp_w_ = vp_w;
  vp_h_ = vp_h;
  pick_w_ = context_width;
  pick_h_ = context_height;
  GetDrawableSize(draw_w_, draw_h_);
  clip_ready_ = pick_w_ > 0 && pick_h_ > 0 && draw_w_ > 0 && draw_h_ > 0;
}

bool OpenGLRenderer3D::HudToNdc(float x, float y, float &ndc_x,
                                float &ndc_y) const {
  if (!clip_ready_ || picture_w_ < 1 || picture_h_ < 1 || pick_w_ < 1 ||
      pick_h_ < 1 || draw_w_ < 1 || draw_h_ < 1) {
    return false;
  }
  // The click is in picture pixels. The picture is the whole window.
  float px = (x / (float)pick_w_) * (float)draw_w_;
  float py = (float)draw_h_ - (y / (float)pick_h_) * (float)draw_h_;
  ndc_x = ((px - (float)picture_x_) / (float)picture_w_) * 2.0f - 1.0f;
  ndc_y = ((py - (float)picture_y_) / (float)picture_h_) * 2.0f - 1.0f;
  return true;
}

bool OpenGLRenderer3D::ScreenRay(int x, int y, Vector3 &near_point,
                                 Vector3 &far_point) const {
  float ndc_x = 0.0f;
  float ndc_y = 0.0f;
  if (!HudToNdc((float)x, (float)y, ndc_x, ndc_y)) return false;
  if (ndc_x < -1.02f || ndc_x > 1.02f || ndc_y < -1.02f || ndc_y > 1.02f) {
    return false;
  }
  float rx = 0.0f;
  float ry = 0.0f;
  float rz = 0.0f;
  float rw = 0.0f;
  Matrix4 inverse = clip_inverse_;
  inverse.MultiplyVec4(ndc_x, ndc_y, -1.0f, 1.0f, rx, ry, rz, rw);
  if (std::fabs(rw) < 1e-8f) return false;
  near_point = Vector3(rx / rw, ry / rw, rz / rw);
  inverse.MultiplyVec4(ndc_x, ndc_y, 1.0f, 1.0f, rx, ry, rz, rw);
  if (std::fabs(rw) < 1e-8f) return false;
  far_point = Vector3(rx / rw, ry / rw, rz / rw);
  return true;
}

void OpenGLRenderer3D::SetEditRect(bool on, float x0, float y0, float x1,
                                   float y1) {
  edit_rect_ = on;
  edit_x0_ = x0;
  edit_y0_ = y0;
  edit_x1_ = x1;
  edit_y1_ = y1;
}

bool OpenGLRenderer3D::ProjectToHud(float x, float y, float z, float &hud_x,
                                    float &hud_y) const {
  if (!clip_ready_ || picture_w_ < 1 || picture_h_ < 1 || pick_w_ < 1 ||
      pick_h_ < 1 || draw_w_ < 1 || draw_h_ < 1) {
    return false;
  }
  float cx = 0.0f;
  float cy = 0.0f;
  float cz = 0.0f;
  float cw = 0.0f;
  Matrix4 clip = clip_;
  clip.MultiplyVec4(x, y, z, 1.0f, cx, cy, cz, cw);
  if (cw <= 1e-4f) return false;
  float ndc_x = cx / cw;
  float ndc_y = cy / cw;
  float px = ((ndc_x + 1.0f) * 0.5f) * (float)picture_w_ + (float)picture_x_;
  float py = ((ndc_y + 1.0f) * 0.5f) * (float)picture_h_ + (float)picture_y_;
  hud_x = px / (float)draw_w_ * (float)pick_w_;
  hud_y = ((float)draw_h_ - py) / (float)draw_h_ * (float)pick_h_;
  return true;
}

void OpenGLRenderer3D::SetSelectionBoxes(const float *corners, int box_count) {
  if (box_count < 0) box_count = 0;
  box_count_ = box_count;
  box_corners_.assign(box_count * 24, 0.0f);
  if (box_count > 0 && corners) {
    std::memcpy(&box_corners_[0], corners,
                sizeof(float) * (size_t)box_count * 24);
  }
}

void OpenGLRenderer3D::EnsureBoxProgram() {
  if (box_program_ || box_failed_) return;
  const char *vs_src =
      "#version 150\n"
      "uniform mat4 clip;\n"
      "in vec3 position;\n"
      "void main() {\n"
      "  gl_Position = clip * vec4(position, 1.0);\n"
      "}\n";
  const char *fs_src =
      "#version 150\n"
      "uniform vec4 ink;\n"
      "out vec4 frag;\n"
      "void main() {\n"
      "  frag = ink;\n"
      "}\n";
  GLuint vs = mapping.glCreateShader(GL_VERTEX_SHADER);
  GLuint fs = mapping.glCreateShader(GL_FRAGMENT_SHADER);
  mapping.glShaderSource(vs, 1, &vs_src, NULL);
  mapping.glShaderSource(fs, 1, &fs_src, NULL);
  mapping.glCompileShader(vs);
  mapping.glCompileShader(fs);
  GLuint prog = mapping.glCreateProgram();
  mapping.glBindAttribLocation(prog, 0, "position");
  mapping.glAttachShader(prog, vs);
  mapping.glAttachShader(prog, fs);
  mapping.glLinkProgram(prog);
  mapping.glDeleteShader(vs);
  mapping.glDeleteShader(fs);
  GLint linked = 0;
  glGetProgramiv(prog, GL_LINK_STATUS, &linked);
  if (!linked) {
    char log[512];
    log[0] = 0;
    glGetProgramInfoLog(prog, (int)sizeof(log), NULL, log);
    std::fprintf(stderr, "player box shader: %s\n", log);
    mapping.glDeleteProgram(prog);
    box_failed_ = true;
    return;
  }
  box_program_ = prog;
  mapping.glGenVertexArrays(1, &box_vao_);
  mapping.glGenBuffers(1, &box_vbo_);
}

void OpenGLRenderer3D::EnsureThickProgram() {
  if (thick_program_ || thick_failed_) return;
  // Core profile will not draw a line wider than one pixel. This program
  // takes positions that are already in clip space, so a stroke can be
  // built in screen pixels along the original line.
  const char *vs_src =
      "#version 150\n"
      "in vec4 clipPos;\n"
      "void main() {\n"
      "  gl_Position = clipPos;\n"
      "}\n";
  const char *fs_src =
      "#version 150\n"
      "uniform vec4 ink;\n"
      "out vec4 frag;\n"
      "void main() {\n"
      "  frag = ink;\n"
      "}\n";
  GLuint vs = mapping.glCreateShader(GL_VERTEX_SHADER);
  GLuint fs = mapping.glCreateShader(GL_FRAGMENT_SHADER);
  mapping.glShaderSource(vs, 1, &vs_src, NULL);
  mapping.glShaderSource(fs, 1, &fs_src, NULL);
  mapping.glCompileShader(vs);
  mapping.glCompileShader(fs);
  GLuint prog = mapping.glCreateProgram();
  mapping.glBindAttribLocation(prog, 0, "clipPos");
  mapping.glAttachShader(prog, vs);
  mapping.glAttachShader(prog, fs);
  mapping.glLinkProgram(prog);
  mapping.glDeleteShader(vs);
  mapping.glDeleteShader(fs);
  GLint linked = 0;
  glGetProgramiv(prog, GL_LINK_STATUS, &linked);
  if (!linked) {
    char log[512];
    log[0] = 0;
    glGetProgramInfoLog(prog, (int)sizeof(log), NULL, log);
    std::fprintf(stderr, "thick line shader: %s\n", log);
    mapping.glDeleteProgram(prog);
    thick_failed_ = true;
    return;
  }
  thick_program_ = prog;
}

namespace {

// A screen-pixel quad along each segment of a closed line. The center of
// the stroke is the line that was passed in.
void AppendScreenStroke(std::vector<float> &out, const float *xyz, int count,
                        Matrix4 clip, float width_px, int vp_w, int vp_h) {
  if (count < 2 || vp_w < 1 || vp_h < 1 || !xyz) return;
  struct Projected {
    float x, y, z, w;
    bool ok;
  };
  // The box shader uploads this matrix with the transpose flag and multiplies
  // it by the point. MultiplyVec4 is that same product.
  std::vector<Projected> points((size_t)count);
  for (int i = 0; i < count; i++) {
    Projected &point = points[(size_t)i];
    clip.MultiplyVec4(xyz[i * 3], xyz[i * 3 + 1], xyz[i * 3 + 2], 1.0f,
                      point.x, point.y, point.z, point.w);
    point.ok = point.w > 1.0e-4f;
  }
  float half = width_px * 0.5f;
  for (int i = 0; i < count; i++) {
    const Projected &a = points[(size_t)i];
    const Projected &b = points[(size_t)((i + 1) % count)];
    if (!a.ok || !b.ok) continue;
    float ax = a.x / a.w;
    float ay = a.y / a.w;
    float bx = b.x / b.w;
    float by = b.y / b.w;
    float dx = (bx - ax) * 0.5f * (float)vp_w;
    float dy = (by - ay) * 0.5f * (float)vp_h;
    float length = std::sqrt(dx * dx + dy * dy);
    if (length < 0.001f) continue;
    float px = -dy / length * half;
    float py = dx / length * half;
    float ox = px * 2.0f / (float)vp_w;
    float oy = py * 2.0f / (float)vp_h;
    float corner[4][2] = {
        {ax + ox, ay + oy},
        {ax - ox, ay - oy},
        {bx + ox, by + oy},
        {bx - ox, by - oy},
    };
    const int tri[6] = {0, 1, 2, 1, 3, 2};
    for (int v = 0; v < 6; v++) {
      bool end = tri[v] >= 2;
      const Projected &src = end ? b : a;
      out.push_back(corner[tri[v]][0] * src.w);
      out.push_back(corner[tri[v]][1] * src.w);
      out.push_back(src.z);
      out.push_back(src.w);
    }
  }
}

}  // namespace

void OpenGLRenderer3D::SetLinkLines(const float *points, int line_count) {
  if (line_count < 0) line_count = 0;
  link_count_ = line_count;
  link_points_.assign((size_t)line_count * 6, 0.0f);
  if (line_count > 0 && points) {
    std::memcpy(&link_points_[0], points,
                sizeof(float) * (size_t)line_count * 6);
  }
}

void OpenGLRenderer3D::SetMomentRings(const float *xyz, const int *counts,
                                       const int *colors, int rings) {
  moment_xyz_.clear();
  moment_counts_.clear();
  moment_colors_.clear();
  if (rings <= 0 || !xyz || !counts) return;
  int cursor = 0;
  for (int ring = 0; ring < rings; ring++) {
    int count = counts[ring];
    if (count < 3) {
      cursor += count > 0 ? count : 0;
      continue;
    }
    moment_counts_.push_back(count);
    moment_colors_.push_back(colors ? colors[ring] : 0);
    moment_xyz_.insert(moment_xyz_.end(), xyz + cursor * 3,
                       xyz + (cursor + count) * 3);
    cursor += count;
  }
}

void OpenGLRenderer3D::DrawSelectionBoxes(const Matrix4 &projection,
                                          const Matrix4 &view) {
  bool draw_boxes = box_count_ > 0 || link_count_ > 0;
  bool draw_rect = edit_rect_ && pick_w_ > 0 && pick_h_ > 0;
  if ((!draw_boxes && !draw_rect) || picture_w_ < 1 || picture_h_ < 1) {
    return;
  }
  EnsureBoxProgram();
  if (!box_program_) return;

  Matrix4 clip = projection * view;
  mapping.glViewport(picture_x_, picture_y_, picture_w_, picture_h_);
  mapping.glDisable(GL_DEPTH_TEST);
  mapping.glDisable(GL_CULL_FACE);
  mapping.glDisable(GL_BLEND);
  GLfloat line_range[2] = {1.0f, 1.0f};
  glGetFloatv(GL_ALIASED_LINE_WIDTH_RANGE, line_range);
  glLineWidth(line_range[1] >= 2.0f ? 2.0f : 1.0f);
  mapping.glUseProgram(box_program_);
  GLint clip_location = mapping.glGetUniformLocation(box_program_, "clip");
  if (clip_location >= 0) {
    mapping.glUniformMatrix4fv(clip_location, 1, GL_TRUE, (float *)clip.elements);
  }
  GLint ink = mapping.glGetUniformLocation(box_program_, "ink");
  mapping.glBindVertexArray(box_vao_);
  mapping.glBindBuffer(GL_ARRAY_BUFFER, box_vbo_);
  mapping.glEnableVertexAttribArray(0);
  mapping.glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, (void *)0);

  if (box_count_ > 0) {
    static const int kEdges[24] = {0, 1, 1, 2, 2, 3, 3, 0, 4, 5, 5, 6,
                                   6, 7, 7, 4, 0, 4, 1, 5, 2, 6, 3, 7};
    std::vector<float> lines;
    lines.reserve((size_t)box_count_ * 24 * 3);
    for (int box = 0; box < box_count_; box++) {
      const float *corners = &box_corners_[(size_t)box * 24];
      for (int edge = 0; edge < 24; edge++) {
        const float *point = corners + kEdges[edge] * 3;
        lines.push_back(point[0]);
        lines.push_back(point[1]);
        lines.push_back(point[2]);
      }
    }
    if (ink >= 0) glUniform4f(ink, 1.0f, 0.92f, 0.15f, 1.0f);
    mapping.glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)(lines.size() * sizeof(float)),
                         &lines[0], GL_STREAM_DRAW);
    mapping.glDrawArrays(GL_LINES, 0, box_count_ * 24);
  }
  if (link_count_ > 0) {
    if (ink >= 0) glUniform4f(ink, 1.0f, 1.0f, 1.0f, 1.0f);
    mapping.glBufferData(GL_ARRAY_BUFFER,
                         (GLsizeiptr)(link_points_.size() * sizeof(float)),
                         &link_points_[0], GL_STREAM_DRAW);
    mapping.glDrawArrays(GL_LINES, 0, link_count_ * 2);
  }
  float nx0 = 0.0f;
  float ny0 = 0.0f;
  float nx1 = 0.0f;
  float ny1 = 0.0f;
  if (draw_rect &&
      (!HudToNdc(edit_x0_, edit_y0_, nx0, ny0) ||
       !HudToNdc(edit_x1_, edit_y1_, nx1, ny1))) {
    draw_rect = false;
  }
  if (draw_rect) {
    float rect[12] = {nx0, ny0, 0, nx1, ny0, 0, nx1, ny1, 0, nx0, ny1, 0};
    static const float kIdentity[16] = {
        1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1,
    };
    if (clip_location >= 0) {
      mapping.glUniformMatrix4fv(clip_location, 1, GL_FALSE, kIdentity);
    }
    if (ink >= 0) glUniform4f(ink, 1.0f, 0.92f, 0.15f, 1.0f);
    mapping.glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)sizeof(rect), rect,
                         GL_STREAM_DRAW);
    mapping.glDrawArrays(GL_LINE_LOOP, 0, 4);
  }

  mapping.glBindVertexArray(0);
  mapping.glBindBuffer(GL_ARRAY_BUFFER, 0);
  glLineWidth(1.0f);
  mapping.glEnable(GL_CULL_FACE);
  mapping.glCullFace(GL_BACK);
}

void OpenGLRenderer3D::DrawMomentRings(const Matrix4 &projection,
                                       const Matrix4 &view, int accum_buffer,
                                       int depth_tex, int width, int height) {
  if (moment_counts_.empty() || width < 1 || height < 1 || accum_buffer <= 0 ||
      depth_tex <= 0) {
    return;
  }
  EnsureBoxProgram();
  EnsureThickProgram();
  if (!box_program_ || !box_vao_) return;

  BindFrameBuffer(accum_buffer);
  SetFrameBufferTexture2D(e_TargetAttachment_Depth, depth_tex);
  std::vector<e_TargetAttachment> color_only;
  color_only.push_back(e_TargetAttachment_Color0);
  SetRenderTargets(color_only);
  GLenum status = mapping.glCheckFramebufferStatus(GL_FRAMEBUFFER);
  if (status != GL_FRAMEBUFFER_COMPLETE) {
    SetFrameBufferTexture2D(e_TargetAttachment_Depth, 0);
    std::vector<e_TargetAttachment> both;
    both.push_back(e_TargetAttachment_Color0);
    both.push_back(e_TargetAttachment_Color1);
    SetRenderTargets(both);
    BindFrameBuffer(0);
    std::fprintf(stderr, "moment ring depth: framebuffer %d\n", (int)status);
    return;
  }

  // Same picture the scene was drawn into. Depth test keeps the ring on the
  // grass and lets the player cover it.
  const float kStrokePx = 14.0f;
  Matrix4 clip = projection * view;
  mapping.glViewport(0, 0, width, height);
  mapping.glDisable(GL_SCISSOR_TEST);
  mapping.glDisable(GL_BLEND);
  mapping.glDisable(GL_CULL_FACE);
  mapping.glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
  mapping.glEnable(GL_DEPTH_TEST);
  mapping.glDepthFunc(GL_LEQUAL);
  mapping.glDepthMask(GL_FALSE);
  mapping.glEnable(GL_POLYGON_OFFSET_FILL);
  mapping.glPolygonOffset(-1.0f, -1.0f);
  mapping.glBindVertexArray(box_vao_);
  mapping.glBindBuffer(GL_ARRAY_BUFFER, box_vbo_);
  mapping.glEnableVertexAttribArray(0);

  int cursor = 0;
  if (thick_program_) {
    mapping.glUseProgram(thick_program_);
    GLint thick_ink = mapping.glGetUniformLocation(thick_program_, "ink");
    mapping.glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 0, (void *)0);
    for (unsigned int ring = 0; ring < moment_counts_.size(); ring++) {
      int count = moment_counts_[ring];
      std::vector<float> stroke;
      AppendScreenStroke(stroke, &moment_xyz_[(size_t)cursor * 3], count, clip,
                         kStrokePx, width, height);
      if (!stroke.empty()) {
        if (thick_ink >= 0 && moment_colors_[ring] == 1) {
          glUniform4f(thick_ink, 0.016f, 0.961f, 1.0f, 1.0f);
        } else if (thick_ink >= 0) {
          glUniform4f(thick_ink, 0.914f, 0.0f, 0.322f, 1.0f);
        }
        mapping.glBufferData(GL_ARRAY_BUFFER,
                             (GLsizeiptr)(stroke.size() * sizeof(float)),
                             &stroke[0], GL_STREAM_DRAW);
        mapping.glDrawArrays(GL_TRIANGLES, 0, (int)(stroke.size() / 4));
      }
      cursor += count;
    }
  }

  mapping.glBindVertexArray(0);
  mapping.glBindBuffer(GL_ARRAY_BUFFER, 0);
  mapping.glDisable(GL_POLYGON_OFFSET_FILL);
  mapping.glDepthMask(GL_TRUE);
  mapping.glDepthFunc(GL_LESS);
  mapping.glDisable(GL_DEPTH_TEST);
  mapping.glEnable(GL_CULL_FACE);
  mapping.glCullFace(GL_BACK);
  SetFrameBufferTexture2D(e_TargetAttachment_Depth, 0);
  std::vector<e_TargetAttachment> both;
  both.push_back(e_TargetAttachment_Color0);
  both.push_back(e_TargetAttachment_Color1);
  SetRenderTargets(both);
  BindFrameBuffer(0);
}

#ifdef __APPLE__
static void SetMoveToActiveSpace(SDL_Window *sdl_window, bool on);
#endif

void OpenGLRenderer3D::SetFullscreen(bool on) {
  if (!window) return;
#ifdef __APPLE__
  if (on) SetMoveToActiveSpace(window, false);
#endif
  SDL_SetWindowFullscreen(window, on ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
#ifdef __APPLE__
  if (!on) SetMoveToActiveSpace(window, true);
#endif
  KeepWindowColor(window);
}

void OpenGLRenderer3D::WaitUntilWindowed() {
  if (!window || !Fullscreen()) return;
  SetFullscreen(false);
  // Leaving full screen finishes on a later event. A size set before that
  // is discarded, and the clip stays on the whole screen.
  Uint32 deadline = SDL_GetTicks() + 800;
  while (Fullscreen() && SDL_GetTicks() < deadline) {
    SDL_PumpEvents();
    SDL_Delay(10);
  }
}

void OpenGLRenderer3D::HoldPlaybackFrame() {
  if (!window || !playback_placed_) return;
  if (Fullscreen()) {
    SetFullscreen(false);
    return;
  }
  int w = 0;
  int h = 0;
  SDL_GetWindowSize(window, &w, &h);
  if (w > playback_view_w_ + 8 || h > playback_view_h_ + 8 ||
      w + 8 < playback_view_w_ || h + 8 < playback_view_h_) {
    SDL_SetWindowSize(window, playback_view_w_, playback_view_h_);
    SDL_SetWindowPosition(window, playback_view_x_, playback_view_y_);
  }
}

void OpenGLRenderer3D::PlacePlaybackWindow() {
  if (!window || playback_placed_) return;
  // The clip plays in this same window. Full screen is left first so the
  // saved frame is the window the viewer had, not the display.
  playback_fullscreen_ = Fullscreen();
  if (playback_fullscreen_) WaitUntilWindowed();
  SDL_GetWindowPosition(window, &playback_x_, &playback_y_);
  SDL_GetWindowSize(window, &playback_w_, &playback_h_);
  playback_band_ = bottom_band_points_;
  bottom_band_points_ = 0;
  applied_band_points_ = 0;

  int index = SDL_GetWindowDisplayIndex(window);
  SDL_Rect bounds;
  bounds.x = 0;
  bounds.y = 0;
  bounds.w = 0;
  bounds.h = 0;
  if (index < 0 || SDL_GetDisplayUsableBounds(index, &bounds) != 0 || bounds.w < 200) {
    SDL_Rect display;
    display.x = 0;
    display.y = 0;
    display.w = 1280;
    display.h = 720;
    if (index >= 0) SDL_GetDisplayBounds(index, &display);
    bounds = display;
  }
  // Mid-sized, 16:9. About 960 by 540, and never more than half the screen,
  // so the desktop stays visible around the clip.
  int w = 960;
  int h = 540;
  int limit_w = bounds.w / 2;
  int limit_h = bounds.h / 2;
  if (limit_w < 640) limit_w = bounds.w > 700 ? bounds.w - 80 : bounds.w;
  if (limit_h < 360) limit_h = bounds.h > 420 ? bounds.h - 80 : bounds.h;
  if (w > limit_w) w = limit_w;
  h = w * 9 / 16;
  if (h > limit_h) {
    h = limit_h;
    w = h * 16 / 9;
  }
  if (w < 320) w = bounds.w;
  if (h < 180) h = bounds.h;
  int x = bounds.x + (bounds.w - w) / 2;
  int y = bounds.y + (bounds.h - h) / 2;
  playback_view_x_ = x;
  playback_view_y_ = y;
  playback_view_w_ = w;
  playback_view_h_ = h;
  playback_placed_ = true;
  SDL_SetWindowSize(window, w, h);
  SDL_SetWindowPosition(window, x, y);
  KeepWindowColor(window);
  HoldPlaybackFrame();
}

void OpenGLRenderer3D::RestorePlaybackWindow() {
  if (!window || !playback_placed_) return;
  playback_placed_ = false;
  bottom_band_points_ = playback_band_;
  applied_band_points_ = playback_band_;
  if (playback_w_ > 16 && playback_h_ > 16) {
    SDL_SetWindowSize(window, playback_w_, playback_h_);
    SDL_SetWindowPosition(window, playback_x_, playback_y_);
  }
  if (playback_fullscreen_) SetFullscreen(true);
  KeepWindowColor(window);
}

#ifdef __APPLE__
static id MatchCocoaWindow(SDL_Window *sdl_window) {
  if (!sdl_window) return nil;
  SDL_SysWMinfo info;
  SDL_VERSION(&info.version);
  if (!SDL_GetWindowWMInfo(sdl_window, &info)) return nil;
  if (info.subsystem != SDL_SYSWM_COCOA) return nil;
  return (id)info.info.cocoa.window;
}

// NSWindowCollectionBehaviorMoveToActiveSpace. Kept on so the match stays on
// the desktop in front. Cleared while entering fullscreen, which needs its
// own space.
static void SetMoveToActiveSpace(SDL_Window *sdl_window, bool on) {
  id nswindow = MatchCocoaWindow(sdl_window);
  if (!nswindow) return;
  unsigned long behavior = ((unsigned long (*)(id, SEL))objc_msgSend)(
      nswindow, sel_registerName("collectionBehavior"));
  if (on) behavior |= 2ul;
  else behavior &= ~2ul;
  ((void (*)(id, SEL, unsigned long))objc_msgSend)(
      nswindow, sel_registerName("setCollectionBehavior:"), behavior);
}

static id CocoaString(const char *text) {
  return ((id (*)(Class, SEL, const char *))objc_msgSend)(
      objc_getClass("NSString"), sel_registerName("stringWithUTF8String:"),
      text);
}

// Homebrew's SDL2 is the SDL3 compatibility shim. Showing the window pumps
// AppKit, and AppKit then offers to restore windows from earlier Python
// crashes. That dialog loads a placeholder icon through ImageIO and can
// take the process down before the match appears. This is process-local.
static void IgnoreSavedWindowState() {
  setenv("ApplePersistenceIgnoreState", "YES", 1);
  id yes = ((id (*)(Class, SEL, signed char))objc_msgSend)(
      objc_getClass("NSNumber"), sel_registerName("numberWithBool:"),
      (signed char)1);
  id dict = ((id (*)(Class, SEL))objc_msgSend)(
      objc_getClass("NSMutableDictionary"), sel_registerName("dictionary"));
  ((void (*)(id, SEL, id, id))objc_msgSend)(
      dict, sel_registerName("setObject:forKey:"), yes,
      CocoaString("ApplePersistenceIgnoreState"));
  id defaults = ((id (*)(Class, SEL))objc_msgSend)(
      objc_getClass("NSUserDefaults"), sel_registerName("standardUserDefaults"));
  if (!defaults || !dict) return;
  ((void (*)(id, SEL, id, id))objc_msgSend)(
      defaults, sel_registerName("setVolatileDomain:forName:"), dict,
      CocoaString("NSArgumentDomain"));
}

static void SetBranchPlayIcon(SDL_Window *sdl_window) {
  // Purple and magenta, with white BP. Set this after the process becomes
  // a normal app. Doing it earlier lets the Dock put the Python icon back.
  const char *from_env = getenv("BRANCHPLAY_ICON");
  const char *paths[] = {
      from_env && from_env[0] ? from_env : "",
      "viewer/brand/branchplay-icon.png",
      "../viewer/brand/branchplay-icon.png",
  };
  for (unsigned int i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
    if (!paths[i] || !paths[i][0]) continue;
    id path = CocoaString(paths[i]);
    id image = ((id (*)(id, SEL, id))objc_msgSend)(
        ((id (*)(Class, SEL))objc_msgSend)(
            objc_getClass("NSImage"), sel_registerName("alloc")),
        sel_registerName("initWithContentsOfFile:"), path);
    if (!image) continue;
    id app = ((id (*)(Class, SEL))objc_msgSend)(
        objc_getClass("NSApplication"), sel_registerName("sharedApplication"));
    if (app) {
      ((void (*)(id, SEL, id))objc_msgSend)(
          app, sel_registerName("setApplicationIconImage:"), image);
    }
    SDL_Surface *icon = IMG_Load(paths[i]);
    if (icon && sdl_window) {
      SDL_SetWindowIcon(sdl_window, icon);
      SDL_FreeSurface(icon);
    }
    break;
  }
}

static void ActivateMatchApp(SDL_Window *sdl_window) {
  id app = ((id (*)(Class, SEL))objc_msgSend)(
      objc_getClass("NSApplication"), sel_registerName("sharedApplication"));
  if (app) {
    // NSApplicationActivationPolicyRegular, so the process can come forward.
    ((signed char (*)(id, SEL, long))objc_msgSend)(
        app, sel_registerName("setActivationPolicy:"), 0L);
    ((void (*)(id, SEL, signed char))objc_msgSend)(
        app, sel_registerName("activateIgnoringOtherApps:"), (signed char)1);
  }
  id nswindow = MatchCocoaWindow(sdl_window);
  if (!nswindow) return;
  ((void (*)(id, SEL, id))objc_msgSend)(
      nswindow, sel_registerName("makeKeyAndOrderFront:"), nil);
}
#endif

void OpenGLRenderer3D::ShowWindow() {
  if (!window || !present_window_) return;
#ifdef __APPLE__
  IgnoreSavedWindowState();
#endif
  SDL_ShowWindow(window);
  SDL_RaiseWindow(window);
#ifdef __APPLE__
  SetMoveToActiveSpace(window, true);
  ActivateMatchApp(window);
  SetBranchPlayIcon(window);
#endif
}

void OpenGLRenderer3D::SetBottomBand(int points) {
  if (points < 0) points = 0;
  if (points > 420) points = 420;
  bottom_band_points_ = points;
  ApplyBottomBand();
}

void OpenGLRenderer3D::ApplyBottomBand() {
  if (!window || !present_window_ || Fullscreen()) return;
  if (bottom_band_points_ == applied_band_points_) return;
  int w = 0;
  int h = 0;
  SDL_GetWindowSize(window, &w, &h);
  if (w < 16 || h < 16) return;
  int next = h + (bottom_band_points_ - applied_band_points_);
  if (next < 64) next = 64;
  int index = SDL_GetWindowDisplayIndex(window);
  SDL_Rect bounds;
  bounds.x = 0;
  bounds.y = 0;
  bounds.w = 0;
  bounds.h = 0;
  bool bounded = index >= 0 && SDL_GetDisplayUsableBounds(index, &bounds) == 0 &&
                 bounds.h > 64;
  if (bounded && next > bounds.h) next = bounds.h;
  int x = 0;
  int y = 0;
  SDL_GetWindowPosition(window, &x, &y);
  if (bounded && y + next > bounds.y + bounds.h) {
    y = bounds.y + bounds.h - next;
    if (y < bounds.y) y = bounds.y;
    SDL_SetWindowPosition(window, x, y);
  }
  if (next != h) SDL_SetWindowSize(window, w, next);
  applied_band_points_ = bottom_band_points_;
}

float OpenGLRenderer3D::BottomBandShare() const {
  int band = BottomBandPixels();
  if (band <= 0 || !window) return 0.0f;
  int drawable_w = 0;
  int drawable_h = 0;
  SDL_GL_GetDrawableSize(window, &drawable_w, &drawable_h);
  (void)drawable_w;
  if (drawable_h <= band) return 0.0f;
  return (float)band / (float)drawable_h;
}

int OpenGLRenderer3D::BottomBandPixels() const {
  if (!window || bottom_band_points_ <= 0 || Fullscreen()) return 0;
  int window_w = 0;
  int window_h = 0;
  int drawable_w = 0;
  int drawable_h = 0;
  SDL_GetWindowSize(window, &window_w, &window_h);
  SDL_GL_GetDrawableSize(window, &drawable_w, &drawable_h);
  if (window_h < 1 || drawable_h < 1) return 0;
  int pixels = int(std::lround(bottom_band_points_ * (double)drawable_h /
                               (double)window_h));
  if (pixels > drawable_h - 16) pixels = drawable_h - 16;
  if (pixels < 0) pixels = 0;
  return pixels;
}

bool OpenGLRenderer3D::Fullscreen() const {
  if (!window) return false;
  Uint32 flags = SDL_GetWindowFlags(window);
  return (flags & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP)) != 0;
}

void OpenGLRenderer3D::GetDrawableSize(int &width, int &height) {
  width = context_width;
  height = context_height;
  if (window) SDL_GL_GetDrawableSize(window, &width, &height);
  if (width < 1) width = context_width;
  if (height < 1) height = context_height;
}

void OpenGLRenderer3D::GetPresentRect(int context_x, int context_y, int context_w,
                                     int context_h, int &x, int &y, int &w,
                                     int &h) {
  int drawable_w = context_width;
  int drawable_h = context_height;
  GetDrawableSize(drawable_w, drawable_h);
  if (context_width < 1 || context_height < 1 || drawable_w < 1 || drawable_h < 1) {
    x = context_x;
    y = context_y;
    w = context_w;
    h = context_h;
    return;
  }
  double scale_w = double(drawable_w) / double(context_width);
  double scale_h = double(drawable_h) / double(context_height);
  double scale = scale_w < scale_h ? scale_w : scale_h;
  int box_w = int(std::lround(context_width * scale));
  int box_h = int(std::lround(context_height * scale));
  if (box_w > drawable_w) box_w = drawable_w;
  if (box_h > drawable_h) box_h = drawable_h;
  int box_x = (drawable_w - box_w) / 2;
  // GL origin is the bottom. The picture fills the window, timeline included.
  int box_y = (drawable_h - box_h) / 2;
  x = box_x + int(std::lround(context_x * scale));
  y = box_y + int(std::lround(context_y * scale));
  w = context_w > 0 ? int(std::lround(context_w * scale)) : 0;
  h = context_h > 0 ? int(std::lround(context_h * scale)) : 0;
  if (w < 1 && context_w > 0) w = 1;
  if (h < 1 && context_h > 0) h = 1;
}

void OpenGLRenderer3D::SetMatrix(const std::string &shaderUniformName,
                                 const Matrix4 &matrix) {
  DO_VALIDATION;
  SetUniformMatrix4(currentShader->first, shaderUniformName, matrix);
}

// void OpenGLRenderer3D::RenderOverlay2D(MessageQueue<Overlay2DQueueEntry>
// &overlay2DQueue) { DO_VALIDATION;
void OpenGLRenderer3D::RenderOverlay2D(
    const std::vector<Overlay2DQueueEntry> &overlay2DQueue) {
  DO_VALIDATION;

  if (overlay2DQueue.empty()) {
    return;
  }

  // The radar is laid out in the 1280 by 720 picture, then this viewport
  // places that picture in the letterboxed window.
  int present_x = 0;
  int present_y = 0;
  int present_w = context_width;
  int present_h = context_height;
  GetPresentRect(0, 0, context_width, context_height, present_x, present_y,
                 present_w, present_h);
  mapping.glViewport(present_x, present_y, present_w, present_h);

  mapping.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
  mapping.glEnable(GL_BLEND);
  mapping.glDisable(GL_DEPTH_TEST);
  SetDepthMask(false);
  mapping.glDisable(GL_CULL_FACE);

  UseShader("overlay");

  Matrix4 orthoMatrix = CreateOrthoMatrix(0, context_width, context_height, 0, 0.1, 10);
  SetMatrix("projection", orthoMatrix);

  mapping.glBindVertexArray(overlayBuffer.vertexArrayID);
  SetTextureUnit(0);

  for (unsigned int i = 0; i < overlay2DQueue.size(); i++) {
    DO_VALIDATION;
    const Overlay2DQueueEntry &queueEntry = overlay2DQueue[i];

    Matrix4 modelMatrix(MATRIX4_IDENTITY);
    modelMatrix.SetTranslation(Vector3(queueEntry.position[0], queueEntry.position[1], -1.0f));
    modelMatrix.SetScale(Vector3(queueEntry.size[0], queueEntry.size[1], 1.0f));
    SetMatrix("model", modelMatrix);
    SetUniformFloat("overlay", "opacity", queueEntry.alpha);

    BindTexture(queueEntry.texture->GetResource()->GetID());
    mapping.glDrawArrays(GL_TRIANGLES, 0, 6);
  }

  mapping.glBindVertexArray(0);

  mapping.glEnable(GL_DEPTH_TEST);
  mapping.glEnable(GL_CULL_FACE);
  SetDepthMask(true);
  mapping.glDisable(GL_BLEND);
}

void OpenGLRenderer3D::RenderOverlay2D() {
  DO_VALIDATION;

  Matrix4 orthoMatrix = CreateOrthoMatrix(-1, 1, -1, 1, 0.0f, 1.0f);
  SetMatrix("orthoProjectionMatrix", orthoMatrix);
  Matrix4 viewMatrix(MATRIX4_IDENTITY);
  viewMatrix.SetTranslation(Vector3(0, 0, -0.5f));
  SetMatrix("orthoViewMatrix", viewMatrix);

  SetCullingMode(e_CullingMode_Off);

  SetTextureUnit(4);  // noise
  BindTexture(noiseTexID);
  SetTextureUnit(0);

  mapping.glBindVertexArray(quadBuffer.vertexArrayID);
  mapping.glDrawArrays(GL_TRIANGLES, 0, 6);
  mapping.glBindVertexArray(0);

  // unbind noise
  SetTextureUnit(4);
  BindTexture(0);

  SetCullingMode(e_CullingMode_Back);
}

void drawSphere(float r, int lats, int longs) {
  DO_VALIDATION;
  // Never called (because light.type is always set to 0) and uses deprecated methods.
  // Possible implementation, that uses modern OpenGl can be found here:
  // https://gist.github.com/zwzmzd/0195733fa1210346b00d
  /*
  int i, j;
  for (i = 0; i <= lats; i++) {
    DO_VALIDATION;
    float lat0 = pi * (-0.5 + (float)(i - 1) / lats);
    float z0 = std::sin(lat0);
    float zr0 = std::cos(lat0);

    float lat1 = pi * (-0.5 + (float)i / lats);
    float z1 = std::sin(lat1);
    float zr1 = std::cos(lat1);

    mapping.glBegin(GL_QUAD_STRIP);
    for (j = 0; j <= longs; j++) {
      DO_VALIDATION;
      float lng = 2 * pi * (float)(j - 1) / longs;
      float x = std::cos(lng);
      float y = std::sin(lng);

      mapping.glNormal3f(x * zr0, y * zr0, z0);
      mapping.glVertex3f(x * zr0 * r, y * zr0 * r, z0 * r);
      mapping.glNormal3f(x * zr1, y * zr1, z1);
      mapping.glVertex3f(x * zr1 * r, y * zr1 * r, z1 * r);
    }
    mapping.glEnd();
  }
   */
}

void OpenGLRenderer3D::RenderLights(std::deque<LightQueueEntry> &lightQueue,
                                    const Matrix4 &projectionMatrix,
                                    const Matrix4 &viewMatrix) {
  DO_VALIDATION;
  Vector3 cameraPos = viewMatrix.GetInverse().GetTranslation();

  //  mapping.glDisable(GL_ALPHA_TEST);

  SetUniformFloat3(currentShader->first, "cameraPosition", cameraPos.coords[0],
                   cameraPos.coords[1], cameraPos.coords[2]);

  std::deque<LightQueueEntry>::iterator lightIter = lightQueue.begin();

  while (lightIter != lightQueue.end()) {
    DO_VALIDATION;
    const LightQueueEntry &light = (*lightIter);

    // bind shadow map
    SetUniformInt(currentShader->first, "has_shadow", (int)light.hasShadow);
    if (light.hasShadow) {
      DO_VALIDATION;
      SetTextureUnit(7);
      //mapping.glEnable(GL_TEXTURE_2D);
      mapping.glBindTexture(GL_TEXTURE_2D,
                            light.shadowMapTexture->GetResource()->GetID());

      Matrix4 toTexCoords(MATRIX4_IDENTITY);
      toTexCoords.SetTranslation(Vector3(0.5f, 0.5f, 0.5f));
      toTexCoords.SetScale(Vector3(0.5f, 0.5f, 0.5f));
      Matrix4 light_to_shadow = toTexCoords * (*lightIter).lightProjectionMatrix *
                                (*lightIter).lightViewMatrix;
      SetUniformMatrix4(currentShader->first, "lightViewProjectionMatrix",
                        light_to_shadow);

    } else {
      //mapping.glDisable(GL_TEXTURE_2D);
    }

    SetUniformFloat3(currentShader->first, "lightColor", light.color.coords[0],
                     light.color.coords[1], light.color.coords[2]);
    SetUniformFloat(currentShader->first, "lightRadius", light.radius);
    SetUniformFloat3(currentShader->first, "lightPosition",
                     light.position.coords[0], light.position.coords[1],
                     light.position.coords[2]);

    int quad_or_sphere = 1;
    if (light.type == 0) {
      DO_VALIDATION;

      quad_or_sphere = 0;  // directional light: visible anyway, everywhere.
                           // draw fullscreen quad

    } else if (light.type == 1) {
      DO_VALIDATION;  // sphere
      AABB aabb = light.aabb;
      // get the spherical bounding box of the aabb
      // if the camera is inside this sphere, draw a fullscreen quad instead of
      // a sphere else, the sphere wouldn't be rendered..
      // float boundingSphereRadius =
      // aabb.GetRadius();//light.position.GetDistance(Vector3(aabb.minxyz.coords[0],
      // aabb.minxyz.coords[1], aabb.minxyz.coords[2]));
      if (cameraPos.GetDistance(light.position) <= aabb.GetRadius()) {
        DO_VALIDATION;
        // cam is within light radius, draw all
        quad_or_sphere = 0;
      } else {
        quad_or_sphere = 1;
      }
    }

    if (quad_or_sphere == 0) {
      DO_VALIDATION;

      // QUAD

      SetCullingMode(e_CullingMode_Off);
      SetDepthFunction(e_DepthFunction_Always);

      Matrix4 orthoMatrix = CreateOrthoMatrix(-1, 1, -1, 1, 0.0f, 1.0f);
      SetMatrix("projectionMatrix", orthoMatrix);
      Matrix4 xviewMatrix(MATRIX4_IDENTITY);
      xviewMatrix.SetTranslation(Vector3(0, 0, -0.5f));
      SetMatrix("viewMatrix", xviewMatrix);
      Matrix4 modelMatrix(MATRIX4_IDENTITY);
      SetMatrix("modelMatrix", modelMatrix);

      mapping.glBindVertexArray(quadBuffer.vertexArrayID);
      mapping.glDrawArrays(GL_TRIANGLES, 0, 6);
      mapping.glBindVertexArray(0);
    } else {  // Never called (because light.type is always set to 0)
      // SPHERE

      SetCullingMode(e_CullingMode_Back);
      SetDepthFunction(e_DepthFunction_Less);

      AABB aabb = light.aabb;

      SetMatrix("projectionMatrix", projectionMatrix);
      SetMatrix("viewMatrix", viewMatrix);
      Matrix4 modelMatrix(MATRIX4_IDENTITY);
      modelMatrix.SetTranslation(light.position);
      SetMatrix("modelMatrix", modelMatrix);
      drawSphere(aabb.GetRadius() * 0.52f, 6, 6);
    }

    if (light.hasShadow) {
      DO_VALIDATION;
      mapping.glBindTexture(GL_TEXTURE_2D, 0);
      //mapping.glDisable(GL_TEXTURE_2D);
      SetTextureUnit(0);
    }

    lightIter++;
  }
}

  // --- new & improved


  // init & exit

VertexBufferID OpenGLRenderer3D::CreateSimpleVertexBuffer(GLfloat *vertices, unsigned int size) {
  GLuint VBO, VAO;
  mapping.glGenVertexArrays(1, &VAO);
  mapping.glGenBuffers(1, &VBO);

  mapping.glBindVertexArray(VAO);

  mapping.glBindBuffer(GL_ARRAY_BUFFER, VBO);
  mapping.glBufferData(GL_ARRAY_BUFFER, size, vertices, GL_STATIC_DRAW);

  mapping.glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat), (GLvoid*)0);
  mapping.glEnableVertexAttribArray(0);

  mapping.glBindBuffer(GL_ARRAY_BUFFER, 0);
  mapping.glBindVertexArray(0);

  VertexBufferID vertexBufferId;
  vertexBufferId.bufferID = VBO;
  vertexBufferId.vertexArrayID = VAO;
  return vertexBufferId;
}

void OpenGLRenderer3D::DeleteSimpleVertexBuffer(VertexBufferID vertexBufferID) {
  DO_VALIDATION;
  GLuint glVertexBufferID = vertexBufferID.bufferID;
  mapping.glDeleteBuffers(1, &glVertexBufferID);

  GLuint glVertexArrayID = vertexBufferID.vertexArrayID;
  mapping.glDeleteVertexArrays(1, &glVertexArrayID);
}

// This method was introduced to replace OpenGL's fixed function pipeline
// (e.g. glBegin, glEnd, etc.) that was used for overlay rendering.
void OpenGLRenderer3D::InitializeOverlayAndQuadBuffers() {
  GLfloat overlayVertices[] = {
          0.0f, 1.0f, 0.0f, 1.0f,
          1.0f, 0.0f, 0.0f, 1.0f,
          0.0f, 0.0f, 0.0f, 1.0f,

          0.0f, 1.0f, 0.0f, 1.0f,
          1.0f, 1.0f, 0.0f, 1.0f,
          1.0f, 0.0f, 0.0f, 1.0f
  };
  overlayBuffer = CreateSimpleVertexBuffer(overlayVertices, sizeof(overlayVertices));

  GLfloat quadVertices[] = {
          -1.0f,  1.0f, 0.0f, 1.0f,
          1.0f, -1.0f, 0.0f, 1.0f,
          -1.0f, -1.0f, 0.0f, 1.0f,

          -1.0f,  1.0f, 0.0f, 1.0f,
          1.0f,  1.0f, 0.0f, 1.0f,
          1.0f, -1.0f, 0.0f, 1.0f
  };
  quadBuffer = CreateSimpleVertexBuffer(quadVertices, sizeof(quadVertices));
}

void OpenGLRenderer3D::CreateContextSdl() {
  DO_VALIDATION;
  // Read before video init. This is what lets the green button use a
  // fullscreen space instead of staying a fixed window.
  SDL_SetHint(SDL_HINT_VIDEO_MAC_FULLSCREEN_SPACES, "1");
#ifdef __APPLE__
  IgnoreSavedWindowState();
#endif
  SDL_Init(SDL_INIT_VIDEO);

  SDL_GL_SetAttribute(SDL_GL_RED_SIZE, 8);
  SDL_GL_SetAttribute(SDL_GL_GREEN_SIZE, 8);
  SDL_GL_SetAttribute(SDL_GL_BLUE_SIZE, 8);
  SDL_GL_SetAttribute(SDL_GL_ALPHA_SIZE, 8);
  SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 16);

  SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);

  SDL_GL_SetAttribute(SDL_GL_ACCELERATED_VISUAL, 1);  // DISABLED?

#ifdef __APPLE__
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
#endif

  // BRANCHPLAY_HIDE_WINDOW keeps the pixels available through get_frame
  // without presenting the native SDL window. The menu window is also
  // created hidden: showing it here would flash the broadcast view for as
  // long as the menu page takes to load. show_window() presents it.
  Uint32 window_flags = SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIDDEN;
  const char* hide_window = getenv("BRANCHPLAY_HIDE_WINDOW");
  bool headless = hide_window && hide_window[0] == '1';
  // A click that focuses the window should still reach the match bar.
  SDL_SetHint(SDL_HINT_MOUSE_FOCUS_CLICKTHROUGH, "1");
  window = SDL_CreateWindow("BranchPlay Engine", SDL_WINDOWPOS_UNDEFINED,
                            SDL_WINDOWPOS_UNDEFINED, context_width,
                            context_height, window_flags);
  context = SDL_GL_CreateContext(window);
  present_window_ = !headless;
  if (present_window_) {
    SDL_GL_SetSwapInterval(0);
    KeepWindowColor(window);
  }

  if (!context) {
    DO_VALIDATION;
    std::string errorString = SDL_GetError();
    std::cout << "Failed on SDL error: " << errorString << std::endl;
    std::cout << "You can solve this problem by:" << std::endl;
    std::cout << "1) If you are running inside Docker make sure container has "
                 "access to XServer by running (outside of the container):"
              << std::endl;
    std::cout << "  > xhost +\"local:docker@\"" << std::endl;
    std::cout << "2) Switch to off-screen rendering by unsetting DISPLAY "
                 "environment variable"
              << std::endl;
    std::cout
        << "3) Disable 3D rendering (which makes environment run much faster)."
        << std::endl;
    exit(1);
  }
#define SDL_PROC(ret, func, params)                                        \
  do {                                                                     \
    *reinterpret_cast<void **>(&(mapping.func)) =                          \
        SDL_GL_GetProcAddress(#func);                                      \
    if (!mapping.func) {                                                   \
      DO_VALIDATION;                                                       \
      printf("Couldn't load GL function %s: %s\n", #func, SDL_GetError()); \
      SDL_SetError("Couldn't load GL function %s: %s\n", #func,            \
                   SDL_GetError());                                        \
      print_stacktrace();                                                  \
      exit(1);                                                             \
    }                                                                      \
  } while (0);
#include "sdl_glfuncs.h"
#undef SDL_PROC
}

#ifdef __linux__
// Helper macro to check for EGL errors.
#define FAIL_IF_EGL_ERROR(egl_expr)                             \
  do {                                                          \
    (egl_expr);                                                 \
    auto error = eglGetError();                                 \
    if (error != EGL_SUCCESS) {                                 \
      Log(e_FatalError, "OpenGLRenderer3D", "CreateContextEgl", \
          "EGL failure: " + int_to_str(__LINE__));              \
    }                                                           \
  } while (false)

void OpenGLRenderer3D::CreateContextEgl() {
  static const int MAX_DEVICES = 16;
  EGLDeviceEXT eglDevs[MAX_DEVICES];
  EGLint numDevices;
  PFNEGLQUERYDEVICESEXTPROC eglQueryDevicesEXT =
      (PFNEGLQUERYDEVICESEXTPROC)eglGetProcAddress("eglQueryDevicesEXT");
  if (eglQueryDevicesEXT == nullptr) {
    Log(e_FatalError, "OpenGLRenderer3D", "CreateContextEgl",
        "Failed on obtain eglQueryDevicesEXT function");
  }
  eglQueryDevicesEXT(MAX_DEVICES, eglDevs, &numDevices);

  PFNEGLGETPLATFORMDISPLAYEXTPROC eglGetPlatformDisplayEXT =
      (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress(
          "eglGetPlatformDisplayEXT");
  if (eglGetPlatformDisplayEXT == nullptr) {
    Log(e_FatalError, "OpenGLRenderer3D", "CreateContextEgl",
        "Failed on obtain eglGetPlatformDisplayEXT function");
  }
  EGLBoolean success;
  int major, minor;
  for (EGLint i = 0; i < numDevices; ++i) {
    EGLDisplay display =
        eglGetPlatformDisplayEXT(EGL_PLATFORM_DEVICE_EXT, eglDevs[i], nullptr);
    if (eglGetError() == EGL_SUCCESS && display != EGL_NO_DISPLAY) {
      success = eglInitialize(display, &major, &minor);
      if (eglGetError() == EGL_SUCCESS && success == EGL_TRUE) {
        egl_display = display;
        break;
      }
    }
  }
  if (egl_display == EGL_NO_DISPLAY) {
    Log(e_FatalError, "OpenGLRenderer3D", "CreateContextEgl",
        "Failed on construct EGL Display");
  }

  FAIL_IF_EGL_ERROR(success = eglBindAPI(EGL_OPENGL_API));
  EGLint num_configs;
  EGLConfig egl_config;
  constexpr EGLint kConfigAttribs[] = {EGL_RED_SIZE,
                                       8,
                                       EGL_GREEN_SIZE,
                                       8,
                                       EGL_BLUE_SIZE,
                                       8,
                                       EGL_SURFACE_TYPE,
                                       EGL_PBUFFER_BIT,
                                       EGL_RENDERABLE_TYPE,
                                       EGL_OPENGL_BIT,
                                       EGL_NONE};
  FAIL_IF_EGL_ERROR(success = eglChooseConfig(egl_display, kConfigAttribs,
                                              &egl_config, 1, &num_configs));

  // Create EGL surface.
  EGLint kPixelBufferAttribs[] = {
      EGL_WIDTH, context_width, EGL_HEIGHT, context_height, EGL_NONE,
  };
  FAIL_IF_EGL_ERROR(egl_surface = eglCreatePbufferSurface(
                        egl_display, egl_config, kPixelBufferAttribs));

  FAIL_IF_EGL_ERROR(egl_context = eglCreateContext(egl_display, egl_config,
                                                   EGL_NO_CONTEXT, nullptr));
  FAIL_IF_EGL_ERROR(
      eglMakeCurrent(egl_display, egl_surface, egl_surface, egl_context));
#define SDL_PROC(ret, func, params)                                        \
  do {                                                                     \
    *reinterpret_cast<void **>(&(mapping.func)) =                          \
        (void*) eglGetProcAddress(#func);                                          \
    if (!mapping.func) {                                                   \
      DO_VALIDATION;                                                       \
      printf("Couldn't load mapping.gl function %s\n", #func); \
      SDL_SetError("Couldn't load mapping.gl function %s\n", #func);               \
      print_stacktrace();                                                  \
      exit(1);                                                             \
    }                                                                      \
  } while (0);
#include "sdl_glfuncs.h"
#undef SDL_PROC
}
#endif

bool OpenGLRenderer3D::CreateContext(int width, int height, int bpp,
                                     bool fullscreen) {
  this->context_width = width;
  this->context_height = height;
  this->context_bpp = bpp;

  // default values
  this->cameraNear = 30.0;
  this->cameraFar = 270.0;
#ifdef __linux__
  if (!getenv("DISPLAY")) {
    std::cout << "No DISPLAY defined, doing off-screen rendering" << std::endl;
    CreateContextEgl();
  } else {
    CreateContextSdl();
  }
#else
  CreateContextSdl();
#endif
  largest_supported_anisotropy = 2;
  mapping.glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT,
                      &largest_supported_anisotropy);

  mapping.glDisable(GL_MULTISAMPLE);
  mapping.glCullFace(GL_BACK);

  // shaders
  LoadShader("simple", "media/shaders/simple");
  LoadShader("lighting", "media/shaders/lighting");
  LoadShader("ambient", "media/shaders/ambient");
  LoadShader("zphase", "media/shaders/zphase");
  LoadShader("postprocess", "media/shaders/postprocess");
  LoadShader("overlay", "media/shaders/overlay");

  currentShader = shaders.begin();

  SDL_Surface *noise = IMG_LoadBmp("media/shaders/noise.png");
  noiseTexID =
      CreateTexture(e_InternalPixelFormat_RGB8, e_PixelFormat_RGB, noise->w,
                    noise->h, false, true, false, false, false);
  UpdateTexture(noiseTexID, noise, false, false);
  SDL_FreeSurface(noise);

  // create buffers for overlay and simple quad rendering to use shaders instead
  // of fixed pipeline.
  InitializeOverlayAndQuadBuffers();

  mapping.glClearColor(0, 0, 0, 0);
  mapping.glClearDepth(1.0);
  mapping.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
  mapping.glDisable(GL_MULTISAMPLE);
  return true;
}

void OpenGLRenderer3D::Exit() {
  DO_VALIDATION;
  DeleteTexture(noiseTexID);

  std::map<std::string, Shader>::iterator shaderIter = shaders.begin();
  while (shaderIter != shaders.end()) {
    DO_VALIDATION;
    mapping.glDeleteShader((*shaderIter).second.vertexShaderID);
    mapping.glDeleteShader((*shaderIter).second.fragmentShaderID);
    mapping.glDeleteProgram((*shaderIter).second.programID);
    shaderIter++;
  }

  currentShader = shaders.end();
  DeleteSimpleVertexBuffer(overlayBuffer);
  DeleteSimpleVertexBuffer(quadBuffer);

  // assert(views.size() == 0);
}

int OpenGLRenderer3D::CreateView(float x_percent, float y_percent,
                                 float width_percent, float height_percent) {
  DO_VALIDATION;

  View view;

  view.target = e_ViewRenderTarget_Context;
  view.targetTexID = 0;
  view.x_percent = x_percent;
  view.y_percent = y_percent;
  view.width_percent = width_percent;
  view.height_percent = height_percent;
  view.x = int(floor(x_percent * 0.01 * context_width));
  view.y = int(floor(y_percent * 0.01 * context_height));
  view.width = int(floor(width_percent * 0.01 * context_width));
  view.height = int(floor(height_percent * 0.01 * context_height));
  BuildViewTargets(view);

  views.push_back(view);

  return views.size() - 1;
}

void OpenGLRenderer3D::BuildViewTargets(View &view) {
  DO_VALIDATION;

  // init FBO

  int gBufWidth = view.width;
  int gBufHeight = view.height;

  view.gBufferID = CreateFrameBuffer();
  BindFrameBuffer(view.gBufferID);

  // texture buffers
  // 16-bit depth crawls along player and line edges. 24-bit holds those edges still.
  view.gBuffer_DepthTexID = CreateTexture(
      e_InternalPixelFormat_DepthComponent24, e_PixelFormat_DepthComponent,
      gBufWidth, gBufHeight, false, false, false, false, false);
  SetFrameBufferTexture2D(e_TargetAttachment_Depth, view.gBuffer_DepthTexID);

  view.gBuffer_AlbedoTexID =
      CreateTexture(e_InternalPixelFormat_RGBA16F, e_PixelFormat_RGBA,
                    gBufWidth, gBufHeight, false, false, false, false, false);
  SetFrameBufferTexture2D(e_TargetAttachment_Color0, view.gBuffer_AlbedoTexID);

  view.gBuffer_NormalTexID =
      CreateTexture(e_InternalPixelFormat_RGBA16F, e_PixelFormat_RGBA,
                    gBufWidth, gBufHeight, false, false, false, false, false);
  SetFrameBufferTexture2D(e_TargetAttachment_Color1, view.gBuffer_NormalTexID);

  view.gBuffer_AuxTexID =
      CreateTexture(e_InternalPixelFormat_RGBA16F, e_PixelFormat_RGBA,
                    gBufWidth, gBufHeight, false, false, false, false, false);
  SetFrameBufferTexture2D(e_TargetAttachment_Color2, view.gBuffer_AuxTexID);

  std::vector<e_TargetAttachment> targets;
  targets.push_back(e_TargetAttachment_Color0);
  targets.push_back(e_TargetAttachment_Color1);
  targets.push_back(e_TargetAttachment_Color2);
  SetRenderTargets(targets);
  targets.clear();

  if (!CheckFrameBufferStatus())
    Log(e_FatalError, "OpenGLRenderer3D", "CreateView",
        "Could not create G-buffer");

  BindFrameBuffer(0);

  targets.push_back(e_TargetAttachment_Back);
  SetRenderTargets(targets);
  targets.clear();

  // accumulation buffer

  int accumBufWidth = view.width;
  int accumBufHeight = view.height;

  view.accumBufferID = CreateFrameBuffer();
  BindFrameBuffer(view.accumBufferID);

  // Nearest. A linear filter mixes each pixel with its neighbors.
  view.accumBuffer_AccumTexID = CreateTexture(
      e_InternalPixelFormat_RGBA16F, e_PixelFormat_RGBA, accumBufWidth,
      accumBufHeight, false, false, false, false, false);
  SetFrameBufferTexture2D(e_TargetAttachment_Color0,
                          view.accumBuffer_AccumTexID);

  view.accumBuffer_ModifierTexID = CreateTexture(
      e_InternalPixelFormat_RGBA16F, e_PixelFormat_RGBA, accumBufWidth,
      accumBufHeight, false, false, false, false, false);
  SetFrameBufferTexture2D(e_TargetAttachment_Color1,
                          view.accumBuffer_ModifierTexID);

  targets.push_back(e_TargetAttachment_Color0);
  targets.push_back(e_TargetAttachment_Color1);
  SetRenderTargets(targets);
  targets.clear();

  if (!CheckFrameBufferStatus())
    Log(e_FatalError, "OpenGLRenderer3D", "CreateView",
        "Could not create Accumulation buffer");

  BindFrameBuffer(0);

  targets.push_back(e_TargetAttachment_Back);
  SetRenderTargets(targets);
  targets.clear();
}

View &OpenGLRenderer3D::GetView(int viewID) {
  DO_VALIDATION;
  return views.at(viewID);
}

void OpenGLRenderer3D::DeleteView(int viewID) {
  DO_VALIDATION;
  ReleaseViewTargets(views.at(viewID));
}

void OpenGLRenderer3D::ReleaseViewTargets(View &view) {
  DO_VALIDATION;

  BindFrameBuffer(view.gBufferID);
  SetFrameBufferTexture2D(e_TargetAttachment_Depth, 0);
  SetFrameBufferTexture2D(e_TargetAttachment_Color0, 0);
  SetFrameBufferTexture2D(e_TargetAttachment_Color1, 0);
  SetFrameBufferTexture2D(e_TargetAttachment_Color2, 0);
  DeleteFrameBuffer(view.gBufferID);

  BindFrameBuffer(view.accumBufferID);
  SetFrameBufferTexture2D(e_TargetAttachment_Color0, 0);
  SetFrameBufferTexture2D(e_TargetAttachment_Color1, 0);
  DeleteFrameBuffer(view.accumBufferID);

  DeleteTexture(view.gBuffer_AlbedoTexID);
  DeleteTexture(view.gBuffer_NormalTexID);
  DeleteTexture(view.gBuffer_DepthTexID);
  DeleteTexture(view.gBuffer_AuxTexID);

  DeleteTexture(view.accumBuffer_AccumTexID);
  DeleteTexture(view.accumBuffer_ModifierTexID);
}

void OpenGLRenderer3D::FitOutputToWindow() {
  if (!present_window_ || !window) return;
  ApplyBottomBand();
  KeepWindowColor(window);
  int width = 0;
  int height = 0;
  GetDrawableSize(width, height);
  // The timeline strip is part of the camera, not a margin under it.
  if (width < 16 || height < 16) return;
  if (width == context_width && height == context_height) return;
  context_width = width;
  context_height = height;
  for (unsigned int i = 0; i < views.size(); i++) {
    View &view = views[i];
    int x = int(floor(view.x_percent * 0.01 * context_width));
    int y = int(floor(view.y_percent * 0.01 * context_height));
    int w = int(floor(view.width_percent * 0.01 * context_width));
    int h = int(floor(view.height_percent * 0.01 * context_height));
    if (w < 1) w = 1;
    if (h < 1) h = 1;
    if (x == view.x && y == view.y && w == view.width && h == view.height) continue;
    ReleaseViewTargets(view);
    view.x = x;
    view.y = y;
    view.width = w;
    view.height = h;
    BuildViewTargets(view);
  }
}

  // general

void OpenGLRenderer3D::SetCullingMode(e_CullingMode cullingMode) {
  DO_VALIDATION;

  switch (cullingMode) {
    DO_VALIDATION;

    case e_CullingMode_Off:
      mapping.glDisable(GL_CULL_FACE);
      break;

    case e_CullingMode_Front:
      mapping.glEnable(GL_CULL_FACE);
      mapping.glCullFace(GL_FRONT);
      break;

    case e_CullingMode_Back:
      mapping.glEnable(GL_CULL_FACE);
      mapping.glCullFace(GL_BACK);
      break;
  }
}

void OpenGLRenderer3D::SetBlendingMode(e_BlendingMode blendingMode) {
  DO_VALIDATION;
  switch (blendingMode) {
    DO_VALIDATION;

    case e_BlendingMode_Off:
      mapping.glDisable(GL_BLEND);
      break;

    case e_BlendingMode_On:
      mapping.glEnable(GL_BLEND);
      break;
  }
}

GLenum GetGLBlendingFunction(e_BlendingFunction blendingFunction) {
  DO_VALIDATION;

  GLenum GLfunc = GL_ONE;

  switch (blendingFunction) {
    DO_VALIDATION;

    case e_BlendingFunction_Zero:
      GLfunc = GL_ZERO;
      break;

    case e_BlendingFunction_One:
      GLfunc = GL_ONE;
      break;
  }

  return GLfunc;
}

void OpenGLRenderer3D::SetBlendingFunction(
    e_BlendingFunction blendingFunction1,
    e_BlendingFunction blendingFunction2) {
  DO_VALIDATION;

  GLenum func1 = GetGLBlendingFunction(blendingFunction1);
  GLenum func2 = GetGLBlendingFunction(blendingFunction2);

  mapping.glBlendFunc(func1, func2);
}

void OpenGLRenderer3D::SetDepthFunction(e_DepthFunction depthFunction) {
  DO_VALIDATION;
  switch (depthFunction) {
    DO_VALIDATION;

    case e_DepthFunction_Never:
      mapping.glDepthFunc(GL_NEVER);
      break;

    case e_DepthFunction_Equal:
      mapping.glDepthFunc(GL_EQUAL);
      break;

    case e_DepthFunction_Greater:
      mapping.glDepthFunc(GL_GREATER);
      break;

    case e_DepthFunction_Less:
      mapping.glDepthFunc(GL_LESS);
      break;

    case e_DepthFunction_GreaterOrEqual:
      mapping.glDepthFunc(GL_GEQUAL);
      break;

    case e_DepthFunction_LessOrEqual:
      mapping.glDepthFunc(GL_LEQUAL);
      break;

    case e_DepthFunction_NotEqual:
      mapping.glDepthFunc(GL_NOTEQUAL);
      break;

    case e_DepthFunction_Always:
      mapping.glDepthFunc(GL_ALWAYS);
      break;
  }
}

void OpenGLRenderer3D::SetDepthTesting(bool OnOff) {
  DO_VALIDATION;
  if (OnOff) {
    DO_VALIDATION;
    mapping.glEnable(GL_DEPTH_TEST);
  } else {
    mapping.glDisable(GL_DEPTH_TEST);
  }
}

void OpenGLRenderer3D::SetDepthMask(bool OnOff) {
  DO_VALIDATION;
  if (OnOff) {
    DO_VALIDATION;
    mapping.glDepthMask(GL_TRUE);
  } else {
    mapping.glDepthMask(GL_FALSE);
  }
}

void OpenGLRenderer3D::SetTextureMode(e_TextureMode textureMode) {
  DO_VALIDATION;
  // Never called. Uses deprecated methods
  /*
  switch (textureMode) {
    DO_VALIDATION;

    case e_TextureMode_Off:
      mapping.glDisable(GL_TEXTURE_2D);
      break;

    case e_TextureMode_2D:
      mapping.glEnable(GL_TEXTURE_2D);
      break;
  }
   */
}

void OpenGLRenderer3D::SetColor(const Vector3 &color, float alpha) {
  DO_VALIDATION;
  mapping.glColor4f(color.coords[0], color.coords[1], color.coords[2], alpha);
}

void OpenGLRenderer3D::SetColorMask(bool r, bool g, bool b, bool alpha) {
  DO_VALIDATION;
  mapping.glColorMask(r, g, b, alpha);
}

void OpenGLRenderer3D::ClearBuffer(const Vector3 &color, bool clearDepth,
                                   bool clearColor) {
  DO_VALIDATION;
  // xx    glClearColor(color.coords[0], color.coords[1], color.coords[2], 0.0);
  // REDUNDANT? deprecated?
  // xx    glClearDepth(1.0f);
  // glClear((GL_COLOR_BUFFER_BIT && clearColor) | (GL_DEPTH_BUFFER_BIT &&
  // clearDepth));
  GLbitfield mask = 0;
  if (clearDepth) mask |= GL_DEPTH_BUFFER_BIT;
  if (clearColor) mask |= GL_COLOR_BUFFER_BIT;
  // A depth clear is dropped while depth writes are off. The previous frame
  // leaves them off, which kept old player shadows in the shadow map.
  if (clearDepth) mapping.glDepthMask(GL_TRUE);
  mapping.glClear(mask);
}

Matrix4 OpenGLRenderer3D::CreatePerspectiveMatrix(float aspectRatio,
                                                  float nearCap, float farCap) {
  DO_VALIDATION;
  // XX deprecated glMatrixMode(GL_PROJECTION);
  // XX deprecated glLoadIdentity();
  float Xnear = nearCap;
  if (Xnear == -1) Xnear = cameraNear;
  float Xfar = farCap;
  if (Xfar == -1) Xfar = cameraFar;
  // XX deprecated gluPerspective(FOV, aspectRatio, Xnear, Xfar);

  Matrix4 projectionMatrix;
  float share = BottomBandShare();
  float used_aspect = aspectRatio;
  if (share > 0.001f && share < 0.92f && aspectRatio > 0.05f) {
    used_aspect = aspectRatio / (1.0f - share);
  }
  projectionMatrix.ConstructProjection(FOV, used_aspect, Xnear, Xfar, share);

  return projectionMatrix;
}

Matrix4 OpenGLRenderer3D::CreateOrthoMatrix(float left, float right,
                                            float bottom, float top,
                                            float nearCap, float farCap) {
  DO_VALIDATION;
  // XX deprecated glMatrixMode(GL_PROJECTION);
  // XX deprecated glLoadIdentity();
  float Xnear = nearCap;
  if (Xnear == -1) Xnear = cameraNear;
  float Xfar = farCap;
  if (Xfar == -1) Xfar = cameraFar;
  // XX deprecated glOrtho(left, right, bottom, top, Xnear, Xfar);

  Matrix4 orthoMatrix;
  orthoMatrix.ConstructOrtho(left, right, bottom, top, Xnear, Xfar);

  return orthoMatrix;
}

  // vertex buffers

GLenum GetGLVertexBufferUsage(e_VertexBufferUsage usage) {
  DO_VALIDATION;

  GLenum GLfunc = GL_STREAM_DRAW;

  switch (usage) {
    DO_VALIDATION;

    case e_VertexBufferUsage_StreamDraw:
      GLfunc = GL_STREAM_DRAW;
      break;

    case e_VertexBufferUsage_StreamRead:
      GLfunc = GL_STREAM_READ;
      break;

    case e_VertexBufferUsage_StreamCopy:
      GLfunc = GL_STREAM_COPY;
      break;

    case e_VertexBufferUsage_StaticDraw:
      GLfunc = GL_STATIC_DRAW;
      break;

    case e_VertexBufferUsage_StaticRead:
      GLfunc = GL_STATIC_READ;
      break;

    case e_VertexBufferUsage_StaticCopy:
      GLfunc = GL_STATIC_COPY;
      break;

    case e_VertexBufferUsage_DynamicDraw:
      GLfunc = GL_DYNAMIC_DRAW;
      break;

    case e_VertexBufferUsage_DynamicRead:
      GLfunc = GL_DYNAMIC_READ;
      break;

    case e_VertexBufferUsage_DynamicCopy:
      GLfunc = GL_DYNAMIC_COPY;
      break;
  }

  return GLfunc;
}

VertexBufferID OpenGLRenderer3D::CreateVertexBuffer(
    float *vertices, unsigned int verticesDataSize,
    const std::vector<unsigned int> &c_indices, e_VertexBufferUsage usage) {
  DO_VALIDATION;
  std::vector<unsigned int> indices = c_indices;
  GLuint iid = 0;  // element indices
  unsigned int vertexArrayID = 0;

  bool pingPong = false;
  if (usage == e_VertexBufferUsage_DynamicDraw ||
      usage == e_VertexBufferUsage_DynamicRead ||
      usage == e_VertexBufferUsage_DynamicCopy ||
      usage == e_VertexBufferUsage_StreamDraw ||
      usage == e_VertexBufferUsage_StreamRead ||
      usage == e_VertexBufferUsage_StreamCopy)
    pingPong = true;
  pingPong = false;  // use orphaning instead
  int number = 1;
  if (pingPong) number = 2;

  int firstBuffer_id = 0;
  int firstArray_id = 0;

  for (int b = 0; b < number; b++) {
    DO_VALIDATION;
    GLuint vid = 0;
    mapping.glGenVertexArrays(1, &vid);
    mapping.glBindVertexArray(vid);
    vertexArrayID = vid;
    if (b == 0) firstArray_id = vertexArrayID;

    GLuint bid = 0;
    mapping.glGenBuffers(1, &bid);
    int buffer_id = bid;
    if (b == 0) firstBuffer_id = buffer_id;
    // printf("array size: %i\n", triangleCount * 3 * 3);
    mapping.glBindBuffer(GL_ARRAY_BUFFER, buffer_id);
    mapping.glBufferData(GL_ARRAY_BUFFER, verticesDataSize * sizeof(float),
                         NULL, GetGLVertexBufferUsage(usage));
    mapping.glBufferSubData(GL_ARRAY_BUFFER, 0,
                            verticesDataSize * sizeof(float), vertices);

    // generate a buffer for the indices

    if (indices.size() == 0) {
      DO_VALIDATION;
      for (unsigned int i = 0;
           i < verticesDataSize / GetTriangleMeshElementCount() / 3; i++) {
        DO_VALIDATION;
        indices.push_back(i);
      }
    }
    mapping.glGenBuffers(1, &iid);
    mapping.glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, iid);
    mapping.glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                         indices.size() * sizeof(unsigned int), NULL,
                         GetGLVertexBufferUsage(usage));
    mapping.glBufferSubData(GL_ELEMENT_ARRAY_BUFFER, 0,
                            indices.size() * sizeof(unsigned int), &indices[0]);

#define BUFFER_OFFSET(i) ((char *)NULL + (i))
    for (int i = 0; i < GetTriangleMeshElementCount(); i++) {
      DO_VALIDATION;
      mapping.glVertexAttribPointer(
          (GLuint)i, 3, GL_FLOAT, GL_FALSE, 0,
          BUFFER_OFFSET(verticesDataSize / GetTriangleMeshElementCount() * i *
                        sizeof(float)));
      mapping.glEnableVertexAttribArray(i);
    }

    if (b == 1) {
      DO_VALIDATION;
      VAOReadIndex.insert(std::pair<int, int>(firstArray_id, 0));
      VBOPingPongMap.insert(std::pair<int, int>(firstBuffer_id, buffer_id));
      VAOPingPongMap.insert(std::pair<int, int>(firstArray_id, vertexArrayID));
    }
  }

  mapping.glBindVertexArray(0);

  mapping.glBindBuffer(GL_ARRAY_BUFFER, 0);
  mapping.glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);

  VertexBufferID vertexBufferID;
  vertexBufferID.bufferID = firstBuffer_id;
  vertexBufferID.vertexArrayID = firstArray_id;
  vertexBufferID.elementArrayID = iid;

  // vertexArrayID = firstArray_id;
  return vertexBufferID;
}

void OpenGLRenderer3D::UpdateVertexBuffer(VertexBufferID vertexBufferID,
                                          float *vertices,
                                          unsigned int verticesDataSize) {
  DO_VALIDATION;
  int writeVertexBufferID = vertexBufferID.bufferID;
  int writeVertexArrayID = vertexBufferID.vertexArrayID;

  int pingPongReadSwitch = 0;
  // bool pingPong = false;
  std::map<int, int>::iterator pingPongIter =
      VAOReadIndex.find(vertexBufferID.vertexArrayID);
  if (pingPongIter != VAOReadIndex.end()) {
    DO_VALIDATION;
    pingPongReadSwitch = pingPongIter->second;
    // pingPong = true;

    pingPongIter->second++;
    if (pingPongIter->second == 2) pingPongIter->second = 0;
  }

  if (pingPongReadSwitch == 0) {
    DO_VALIDATION;
    pingPongIter = VBOPingPongMap.find(vertexBufferID.bufferID);
    if (pingPongIter != VBOPingPongMap.end()) {
      DO_VALIDATION;
      writeVertexBufferID = pingPongIter->second;
    }

    pingPongIter = VAOPingPongMap.find(vertexBufferID.vertexArrayID);
    if (pingPongIter != VAOPingPongMap.end()) {
      DO_VALIDATION;
      writeVertexArrayID = pingPongIter->second;
    }
  }

  mapping.glBindVertexArray((GLuint)writeVertexArrayID);
  mapping.glBindBuffer(
      GL_ARRAY_BUFFER,
      writeVertexBufferID);
  // glBufferData(GL_ARRAY_BUFFER, verticesDataSize * sizeof(float), vertices,
  // GL_DYNAMIC_DRAW);

  //    glBufferData(GL_ARRAY_BUFFER, verticesDataSize * sizeof(float), NULL,
  //    GL_DYNAMIC_DRAW);

  //    if (!pingPong) { DO_VALIDATION;
  // i don't think we can use glMapBufferRange with GL_MAP_UNSYNCHRONIZED_BIT in
  // a non-pingponged situation, but may want to test this sometimes
  //      glBufferSubData(GL_ARRAY_BUFFER, 0, verticesDataSize * sizeof(float),
  //      vertices);
  //    } else {
  // glBufferData(GL_ARRAY_BUFFER, verticesDataSize * sizeof(float), NULL,
  // GL_STREAM_DRAW); float *ptr = (float*)glMapBuffer(GL_ARRAY_BUFFER,
  // GL_WRITE_ONLY);

  // the next 2 statements, as well as the invalidate_bit stuff in the 3rd
  // statement, should do the same thing: orphaning the vertexbuffer. however,
  // on my current AMD (HD 6850), only the first seems to actually work! is this
  // an AMD driver bug? can't find anything about it on the interwebz..

  mapping.glBufferData(GL_ARRAY_BUFFER, verticesDataSize * sizeof(float), NULL,
                       GL_DYNAMIC_DRAW);
  // glInvalidateBufferData(vertexBufferID.bufferID);
  float *ptr = (float *)mapping.glMapBufferRange(
      GL_ARRAY_BUFFER, 0, verticesDataSize * sizeof(float),
      GL_MAP_WRITE_BIT |
          GL_MAP_UNSYNCHRONIZED_BIT);  // GL_MAP_INVALIDATE_BUFFER_BIT |
                                       // GL_MAP_INVALIDATE_RANGE_BIT |
  // A buffer already drawn this match, such as a shared hairstyle, will not
  // map. The orphan above dropped the old storage, so write the bytes directly.
  if (ptr) {
    memcpy(ptr, vertices, verticesDataSize * sizeof(float));
    mapping.glUnmapBuffer(GL_ARRAY_BUFFER);
  } else if (vertices != 0 && verticesDataSize > 0) {
    mapping.glBufferData(GL_ARRAY_BUFFER, verticesDataSize * sizeof(float),
                         vertices, GL_DYNAMIC_DRAW);
  }

  //      glBufferData(GL_ARRAY_BUFFER, verticesDataSize * sizeof(float),
  //      vertices, GL_DYNAMIC_DRAW);

  //    }

  // this fence doesn't seem necessary. the frame swap will glflush things
  // anyway, so as long as you don't update the mesh and render stuff in the
  // same frame, you should be okay. ^ investigate if this is correct thinking.
  // not sure. hairstyles seem to be late, so there is something wrong with
  // omitting the fence. if it's true, users of the engine will need to make
  // sure to not update and render in parallel. maybe make this an option? maybe
  // put something about it in a future manual?
  // GLsync syncObj = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
  /*fenceoff
      // delete possible previous sync object
      std::map<int, GLsync>::iterator syncIter =
     VAOfence.find(writeVertexArrayID); if (syncIter != VAOfence.end()) {
     DO_VALIDATION; glDeleteSync(syncIter->second); VAOfence.erase(syncIter);
      }
  */
  // VAOfence.insert(std::pair<int, GLsync>(writeVertexArrayID, syncObj));

  mapping.glBindVertexArray(0);
  mapping.glBindBuffer(GL_ARRAY_BUFFER, 0);
}

void OpenGLRenderer3D::DeleteVertexBuffer(VertexBufferID vertexBufferID) {
  DO_VALIDATION;
  GLuint glVertexBufferID = vertexBufferID.bufferID;
  mapping.glDeleteBuffers(1, &glVertexBufferID);

  GLuint glElementArrayID = vertexBufferID.elementArrayID;
  mapping.glDeleteBuffers(1, &glElementArrayID);

  GLuint glVertexArrayID = vertexBufferID.vertexArrayID;
  mapping.glDeleteVertexArrays(1, &glVertexArrayID);

  std::map<int, int>::iterator pingPongIter =
      VBOPingPongMap.find(vertexBufferID.bufferID);
  if (pingPongIter != VBOPingPongMap.end()) {
    DO_VALIDATION;
    glVertexBufferID = pingPongIter->second;
    mapping.glDeleteBuffers(1, &glVertexBufferID);
    VBOPingPongMap.erase(pingPongIter);
  }

  pingPongIter = VAOPingPongMap.find(vertexBufferID.vertexArrayID);
  if (pingPongIter != VAOPingPongMap.end()) {
    DO_VALIDATION;
    glVertexArrayID = pingPongIter->second;
    mapping.glDeleteVertexArrays(1, &glVertexArrayID);
    VAOPingPongMap.erase(pingPongIter);
  }

  pingPongIter = VAOReadIndex.find(vertexBufferID.vertexArrayID);
  if (pingPongIter != VAOReadIndex.end()) {
    DO_VALIDATION;
    VAOReadIndex.erase(pingPongIter);
  }
}

void DrawBufferChunk(int startIndex, int count) {
  DO_VALIDATION;
  // draw buffer
  if (count > 0) {
    DO_VALIDATION;
#define BUFFER_OFFSET(i) ((char *)NULL + (i))
    mapping.glDrawRangeElements(
        GL_TRIANGLES, startIndex, startIndex + count, count, GL_UNSIGNED_INT,
        BUFFER_OFFSET(startIndex * sizeof(unsigned int)));
  }
}

void OpenGLRenderer3D::RenderVertexBuffer(
    const std::deque<VertexBufferQueueEntry> &vertexBufferQueue,
    e_RenderMode renderMode) {
  DO_VALIDATION;
  VertexBuffer *vertexBuffer;

// Deprecated
//  if (renderMode != e_RenderMode_GeometryOnly) {
//    DO_VALIDATION;
//    mapping.glEnable(GL_TEXTURE_2D);
//  } else {
//    mapping.glDisable(GL_TEXTURE_2D);
//  }

  signed int currentDiffuseTextureID = -1;
  signed int currentNormalTextureID = -1;
  signed int currentSpecularTextureID = -1;
  signed int currentIlluminationTextureID = -1;
  signed int currentBoundBuffer = -1;

  int bufferSwitches = 0;

  Matrix4 transform;

  std::deque<VertexBufferQueueEntry>::const_iterator vertexBufferQueueIter =
      vertexBufferQueue.begin();
  while (vertexBufferQueueIter != vertexBufferQueue.end()) {
    DO_VALIDATION;
    const VertexBufferQueueEntry *queueEntry = &(*vertexBufferQueueIter);

    vertexBuffer = queueEntry->vertexBuffer->GetResource();
    if (currentBoundBuffer != vertexBuffer->GetVaoID()) {
      DO_VALIDATION;
      bufferSwitches++;

      int vaoID = vertexBuffer->GetVaoID();
      int pingPongReadSwitch = 0;
      std::map<int, int>::iterator pingPongIter = VAOReadIndex.find(vaoID);
      if (pingPongIter != VAOReadIndex.end()) {
        DO_VALIDATION;
        pingPongReadSwitch = pingPongIter->second;
      }

      if (pingPongReadSwitch == 1) {
        DO_VALIDATION;
        std::map<int, int>::iterator pingPongIter = VAOPingPongMap.find(vaoID);
        if (pingPongIter != VAOPingPongMap.end()) {
          DO_VALIDATION;
          vaoID = pingPongIter->second;
        }
      }

      /*
              // block on VAO update
              std::map<int, GLsync>::iterator syncIter = VAOfence.find(vaoID);
              if (syncIter != VAOfence.end()) { DO_VALIDATION;
                //glFlush();
                //glWaitSync(syncIter->second, 0, GL_TIMEOUT_IGNORED);
                GLenum returnVal = GL_WAIT_FAILED;
                while (returnVal != GL_ALREADY_SIGNALED && returnVal !=
         GL_CONDITION_SATISFIED) { DO_VALIDATION; returnVal =
         glClientWaitSync(syncIter->second, GL_SYNC_FLUSH_COMMANDS_BIT,
         1000000);
                  //returnVal = glClientWaitSync(syncIter->second, 0, 1000);
                  //if (returnVal == GL_TIMEOUT_EXPIRED) printf("TIMEOUT
         EXPIRED!\n"); assert(returnVal != GL_INVALID_VALUE);
                }
              }
      */

      currentBoundBuffer = vaoID;
      mapping.glBindVertexArray(vaoID);
      // glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, vertexBuffer->GetElementID());
      /*
              if (renderMode != e_RenderMode_GeometryOnly) { DO_VALIDATION;
                if (renderMode == e_RenderMode_Full) { DO_VALIDATION;
                }
              }
      */
    }

    // glPushMatrix();

    // slow, why?
    transform.Construct(queueEntry->position, Vector3(1, 1, 1),
                        queueEntry->rotation);
    // transform.Transpose();
    // glMultMatrixf((float*)transform.elements);
    SetMatrix("modelMatrix", transform);

    bool sequential = true;  // buffer vertexbuffer chunks until a change
                             // happens (in texture or index, for example)
    struct BufferChunk {
      BufferChunk() {
        DO_VALIDATION;
        startIndex = 0;
        count = 0;
      }
      int startIndex = 0;
      int count = 0;
    };
    BufferChunk bufferChunk;

    auto vertexBufferIter = queueEntry->vertexBufferIndices->begin();
    while (vertexBufferIter != queueEntry->vertexBufferIndices->end()) {
      DO_VALIDATION;

      // VertexBufferIndex *vbIndex = (*vertexBufferIter).get();
      const VertexBufferIndex *vbIndex = &(*vertexBufferIter);

      if (renderMode != e_RenderMode_GeometryOnly) {
        DO_VALIDATION;
        int diffuseTextureID = 0;
        int normalTextureID = 0;
        int specularTextureID = 0;
        int illuminationTextureID = 0;
        if (vbIndex->material.diffuseTexture) {
          DO_VALIDATION;
          diffuseTextureID =
              vbIndex->material.diffuseTexture->GetResource()->GetID();
        }

        if (renderMode == e_RenderMode_Full) {
          DO_VALIDATION;
          if (vbIndex->material.normalTexture) {
            DO_VALIDATION;
            normalTextureID =
                vbIndex->material.normalTexture->GetResource()->GetID();
          }
          if (vbIndex->material.specularTexture) {
            DO_VALIDATION;
            specularTextureID =
                vbIndex->material.specularTexture->GetResource()->GetID();
          }
          if (vbIndex->material.illuminationTexture) {
            DO_VALIDATION;
            illuminationTextureID =
                vbIndex->material.illuminationTexture->GetResource()->GetID();
          }
        }

        if (diffuseTextureID != currentDiffuseTextureID ||
            normalTextureID != currentNormalTextureID ||
            specularTextureID != currentSpecularTextureID ||
            illuminationTextureID != currentIlluminationTextureID) {
          DO_VALIDATION;

          if (sequential) {
            DO_VALIDATION;
            DrawBufferChunk(bufferChunk.startIndex, bufferChunk.count);
            sequential = false;
          }

          bool has_normal = false;
          bool has_specular = false;
          bool has_illumination = false;
          if (normalTextureID != 0) has_normal = true;
          if (specularTextureID != 0) has_specular = true;
          if (illuminationTextureID != 0) has_illumination = true;

          if (renderMode == e_RenderMode_Full) {
            DO_VALIDATION;
            if (has_normal && normalTextureID != currentNormalTextureID) {
              DO_VALIDATION;
              SetTextureUnit(1);
              mapping.glBindTexture(GL_TEXTURE_2D, normalTextureID);
            }
            if (has_specular && specularTextureID != currentSpecularTextureID) {
              DO_VALIDATION;
              SetTextureUnit(2);
              mapping.glBindTexture(GL_TEXTURE_2D, specularTextureID);
            }
            if (has_illumination &&
                illuminationTextureID != currentIlluminationTextureID) {
              DO_VALIDATION;
              SetTextureUnit(3);
              mapping.glBindTexture(GL_TEXTURE_2D, illuminationTextureID);
            }
          }

          SetTextureUnit(0);
          mapping.glBindTexture(GL_TEXTURE_2D, diffuseTextureID);

          if (renderMode == e_RenderMode_Full) {
            DO_VALIDATION;
            // SetUniformFloat("simple", "shininess",
            // vbIndex->material.shininess * 60 + 1); SetUniformFloat("simple",
            // "specular", vbIndex->material.specular_amount);
            // SetUniformFloat("simple", "self_illumination",
            // vbIndex->material.self_illumination.coords[0]);
            // SetUniformFloat3("simple", "materialparams",
            // vbIndex->material.shininess * 60 + 1,
            // vbIndex->material.specular_amount,
            // vbIndex->material.self_illumination.coords[0]);
            SetUniformFloat3("simple", "materialparams",
                             vbIndex->material.shininess,
                             vbIndex->material.specular_amount,
                             vbIndex->material.self_illumination.coords[0]);

            // SetUniformInt("simple", "has_normal", (int)has_normal);
            // SetUniformInt("simple", "has_specular", (int)has_specular);
            // SetUniformInt("simple", "has_illumination",
            // (int)has_illumination);
            SetUniformFloat3("simple", "materialbools", (int)has_normal,
                             (int)has_specular, (int)has_illumination);
          }

          currentDiffuseTextureID = diffuseTextureID;
          currentNormalTextureID = normalTextureID;
          currentSpecularTextureID = specularTextureID;
          currentIlluminationTextureID = illuminationTextureID;
        }
      }  // if !GeometryOnly

      int start = vbIndex->startIndex;
      int count = vbIndex->size;

      // if (currentShader->first.compare("zphase") == 0) printf("drawing %i
      // elements in zphase mode\n", count);

      if (sequential)
        if (bufferChunk.startIndex + bufferChunk.count != start) {
          DO_VALIDATION;
          DrawBufferChunk(bufferChunk.startIndex, bufferChunk.count);
          sequential = false;
        }

        //if (sequential) if (vertexBufferIter + 1 == queueEntry->vertexBufferIndices.end()) sequential = false; // data end
        if (sequential) {
          DO_VALIDATION;
          // add to buffer
          bufferChunk.count += count;
        } else {
          // reset buffer
          bufferChunk.startIndex = start;
          bufferChunk.count = count;
          sequential = true;
        }

        vertexBufferIter++;

        if (sequential)
          if (vertexBufferIter == queueEntry->vertexBufferIndices->end()) {
            DO_VALIDATION;
            DrawBufferChunk(bufferChunk.startIndex, bufferChunk.count);
            sequential = false;
          }
    }

      vertexBufferQueueIter++;
  }

    //printf("%i buffer switches\n", bufferSwitches);

    if (renderMode != e_RenderMode_GeometryOnly) {
      DO_VALIDATION;
      if (renderMode == e_RenderMode_Full) {
        DO_VALIDATION;
        SetTextureUnit(1);
        mapping.glBindTexture(GL_TEXTURE_2D, 0);
        SetTextureUnit(2);
        mapping.glBindTexture(GL_TEXTURE_2D, 0);
        SetTextureUnit(3);
        mapping.glBindTexture(GL_TEXTURE_2D, 0);
      }
      SetTextureUnit(0);
      mapping.glBindTexture(GL_TEXTURE_2D, 0);
      //mapping.glDisable(GL_TEXTURE_2D);
    }

    mapping.glBindVertexArray(0);
}

  // lights

void OpenGLRenderer3D::SetLight(const Vector3 &position, const Vector3 &color,
                                float radius) {
  DO_VALIDATION;
  // Deprecated functionality, everything is implemented in the shaders
  /*
  Vector3 pos = position;

  // printf("%f %f %f\n", cameraPos.coords[0], cameraPos.coords[1],
  // cameraPos.coords[2]);

  GLfloat positionF[4] = {pos.coords[0], pos.coords[1], pos.coords[2], 1.0};
  mapping.glLightfv(GL_LIGHT0, GL_POSITION, positionF);
  SetUniformFloat3(currentShader->first, "lightPosition", pos.coords[0],
                   pos.coords[1], pos.coords[2]);

  GLfloat diffuseF[4] = {color.coords[0], color.coords[1], color.coords[2],
                         radius};
  mapping.glLightfv(GL_LIGHT0, GL_DIFFUSE, diffuseF);

  GLfloat specular[3] = {1, 1, 1};
  mapping.glLightfv(GL_LIGHT0, GL_SPECULAR, specular);

  mapping.glEnable(GL_LIGHT0);
   */
}

  // textures

GLenum GetGLPixelFormat(e_PixelFormat pixelFormat) {
  DO_VALIDATION;
  GLenum format = GL_RGB;

  switch (pixelFormat) {
    DO_VALIDATION;

    case e_PixelFormat_Alpha:
      format = GL_ALPHA;
      break;
    case e_PixelFormat_RGB:
      format = GL_RGB;
      break;
    case e_PixelFormat_RGBA:
      format = GL_RGBA;
      break;
    case e_PixelFormat_DepthComponent:
      format = GL_DEPTH_COMPONENT;
      break;
    case e_PixelFormat_Luminance:
      Log(e_Error, "OpenGLRenderer3D", "GetGLPixelFormat",
          "e_PixelFormat_Luminance not supported");
      break;
  }

  return format;
}

GLenum GetGLInternalPixelFormat(e_InternalPixelFormat pixelFormat) {
  DO_VALIDATION;
  GLenum format = GL_RGB8;

  switch (pixelFormat) {
    DO_VALIDATION;

    case e_InternalPixelFormat_RGB8:
      format = GL_RGB8;
      break;
    case e_InternalPixelFormat_SRGB8:
      format = GL_SRGB8;
      break;
    case e_InternalPixelFormat_RGB16:
      format = GL_RGB16;
      break;
    case e_InternalPixelFormat_RGBA4:
      format = GL_RGBA4;
      break;
    case e_InternalPixelFormat_RGBA8:
      format = GL_RGBA8;
      break;
    case e_InternalPixelFormat_SRGBA8:
      format = GL_SRGB8_ALPHA8;
      break;
    case e_InternalPixelFormat_RGBA16:
      format = GL_RGBA16;
      break;
    case e_InternalPixelFormat_RGBA16F:
      format = GL_RGBA16F;
      break;
    case e_InternalPixelFormat_RGBA32F:
      format = GL_RGBA32F;
      break;
    case e_InternalPixelFormat_RGB5_A1:
      format = GL_RGB5_A1;
      break;
    case e_InternalPixelFormat_DepthComponent:
      format = GL_DEPTH_COMPONENT;
      break;
    case e_InternalPixelFormat_DepthComponent16:
      format = GL_DEPTH_COMPONENT16;
      break;
    case e_InternalPixelFormat_DepthComponent24:
      format = GL_DEPTH_COMPONENT24;
      break;
    case e_InternalPixelFormat_DepthComponent32:
      format = GL_DEPTH_COMPONENT32;
      break;
    case e_InternalPixelFormat_DepthComponent32F:
      format = GL_DEPTH_COMPONENT32F;
      break;
    case e_InternalPixelFormat_StencilIndex8:
      format = GL_STENCIL_INDEX8;
      break;
  }

  return format;
}

int OpenGLRenderer3D::CreateTexture(e_InternalPixelFormat internalPixelFormat,
                                    e_PixelFormat pixelFormat, int width,
                                    int height, bool alpha, bool repeat,
                                    bool mipmaps, bool filter, bool multisample,
                                    bool compareDepth) {
  DO_VALIDATION;

  /*
      if (pot(source->w) != source->w || pot(source->h) != source->h) {
     DO_VALIDATION; Log(e_Warning, "OpenGLRenderer3D", "CreateTexture",
     "Non-power-of-2 texture!");
      }
  */

  GLuint texID = 0;
  GLint bound_before = 0, fbo_before = 0;
  mapping.glGetIntegerv(GL_TEXTURE_BINDING_2D, &bound_before);
  mapping.glGetIntegerv(GL_FRAMEBUFFER_BINDING, &fbo_before);
  mapping.glGenTextures(1, &texID);
  BindTexture(texID);

  GLint filter_min, filter_mag;

  if (filter == true) {
    DO_VALIDATION;
    filter_min = (mipmaps) ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR;
    filter_mag = GL_LINEAR;
  } else {
    filter_min = (mipmaps) ? GL_NEAREST_MIPMAP_NEAREST : GL_NEAREST;
    filter_mag = GL_NEAREST;
  }

  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S,
                          (repeat) ? GL_REPEAT : GL_CLAMP_TO_EDGE);
  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T,
                          (repeat) ? GL_REPEAT : GL_CLAMP_TO_EDGE);
  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter_min);
  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter_mag);
  if (internalPixelFormat == e_InternalPixelFormat_DepthComponent16 ||
      internalPixelFormat == e_InternalPixelFormat_DepthComponent24 ||
      internalPixelFormat == e_InternalPixelFormat_DepthComponent32 ||
      internalPixelFormat == e_InternalPixelFormat_DepthComponent32F) {
    DO_VALIDATION;
    // XXglTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE);
    if (compareDepth) {
      DO_VALIDATION;
      mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE,
                              GL_COMPARE_REF_TO_TEXTURE);
      mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_FUNC,
                              GL_LEQUAL);
    } else {
      // A depth texture otherwise keeps the compare mode, and a normal
      // sample comes back as the compare result instead of the depth.
      mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE);
    }
    //      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    //      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    // glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_FUNC, GL_LEQUAL);
    // glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);
    // Post-GLSL 1.3, DEPTH_TEXTURE_MODE is deprecated and GLSL behaves as if
    // its always set to LUMINANCE
    // glTexParameteri(GL_TEXTURE_2D, GL_DEPTH_TEXTURE_MODE, GL_INTENSITY);
    // glTexParameteri(GL_TEXTURE_2D, GL_DEPTH_TEXTURE_MODE, GL_LUMINANCE);
  }

  if (filter) {
    DO_VALIDATION;
    SetMaxAnisotropy();
  }

  if (!multisample) {
    DO_VALIDATION;
    GLenum upload_type = GL_UNSIGNED_BYTE;
    if (internalPixelFormat == e_InternalPixelFormat_DepthComponent16) {
      upload_type = GL_UNSIGNED_SHORT;
    } else if (internalPixelFormat == e_InternalPixelFormat_DepthComponent ||
               internalPixelFormat == e_InternalPixelFormat_DepthComponent24 ||
               internalPixelFormat == e_InternalPixelFormat_DepthComponent32) {
      upload_type = GL_UNSIGNED_INT;
    } else if (internalPixelFormat == e_InternalPixelFormat_DepthComponent32F) {
      upload_type = GL_FLOAT;
    }
    mapping.glTexImage2D(
        GL_TEXTURE_2D, 0, GetGLInternalPixelFormat(internalPixelFormat), width,
        height, 0, GetGLPixelFormat(pixelFormat), upload_type, NULL);
    bool depth_tex =
        internalPixelFormat == e_InternalPixelFormat_DepthComponent16 ||
        internalPixelFormat == e_InternalPixelFormat_DepthComponent24 ||
        internalPixelFormat == e_InternalPixelFormat_DepthComponent32 ||
        internalPixelFormat == e_InternalPixelFormat_DepthComponent32F;
  } else {

  }

  /* test if this actually helps
      GLclampf prior = (width * height) / 1048576.0; // 1024*1024 tex = max
     priority
      //printf("%f\n", (pot(source->w) * pot(source->h)) / 1048576.0);
      glPrioritizeTextures(1, (const GLuint*)&texID, &prior);
  */
  BindTexture(0);

  return texID;
}

void OpenGLRenderer3D::ResizeTexture(int textureID, SDL_Surface *source,
                                     e_InternalPixelFormat internalPixelFormat,
                                     e_PixelFormat pixelFormat, bool alpha,
                                     bool mipmaps) {
  DO_VALIDATION;

  BindTexture(textureID);
  int x = 0;
  int y = 0;
  int width = source->w;
  int height = source->h;

  SDL_LockSurface(source);
  mapping.glTexImage2D(GL_TEXTURE_2D, 0,
          GetGLInternalPixelFormat(internalPixelFormat), width,
          height, 0, GetGLPixelFormat(pixelFormat),
          GL_UNSIGNED_BYTE, source->pixels);
  SDL_UnlockSurface(source);

  if (mipmaps) {
    DO_VALIDATION;
    mapping.glGenerateMipmap(GL_TEXTURE_2D);
  }

  bool repeat = false;
  bool filter = true;
  if (!mipmaps) filter = false;  // <-- todo: hack
  GLint filter_min, filter_mag;

  if (filter == true) {
    DO_VALIDATION;
    filter_min = (mipmaps) ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR;
    filter_mag = GL_LINEAR;
    // glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT,
    // &largest_supported_anisotropy);
    SetMaxAnisotropy();
  } else {
    filter_min = (mipmaps) ? GL_NEAREST_MIPMAP_NEAREST : GL_NEAREST;
    filter_mag = GL_NEAREST;
  }

  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S,
                          (repeat) ? GL_REPEAT : GL_CLAMP_TO_EDGE);
  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T,
                          (repeat) ? GL_REPEAT : GL_CLAMP_TO_EDGE);
  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter_min);
  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter_mag);
  if (internalPixelFormat == e_InternalPixelFormat_DepthComponent16 ||
      internalPixelFormat == e_InternalPixelFormat_DepthComponent24 ||
      internalPixelFormat == e_InternalPixelFormat_DepthComponent32 ||
      internalPixelFormat == e_InternalPixelFormat_DepthComponent32F) {
    DO_VALIDATION;
    mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE);
    // Post-GLSL 1.3, DEPTH_TEXTURE_MODE is deprecated and GLSL behaves as if
    // its always set to LUMINANCE
    //mapping.glTexParameteri(GL_TEXTURE_2D, GL_DEPTH_TEXTURE_MODE, GL_INTENSITY);
  }

  // GLclampf prior = (width * height) / 1048576.0; // 1024*1024 tex = max
  // priority printf("%f\n", (pot(source->w) * pot(source->h)) / 1048576.0);
  // glPrioritizeTextures(1, (const GLuint*)&textureID, &prior);

  BindTexture(0);
}

void OpenGLRenderer3D::UpdateTexture(int textureID, SDL_Surface *source,
                                     bool alpha, bool mipmaps) {
  DO_VALIDATION;

  mapping.glBindTexture(GL_TEXTURE_2D, textureID);

  GLint type1 = GL_RGBA8;
  GLint type2 = (alpha) ? GL_RGBA : GL_RGB;

  int x = 0;
  int y = 0;
  int w = source->w;
  int h = source->h;

  SDL_LockSurface(source);
  mapping.glTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, type2, GL_UNSIGNED_BYTE,
          source->pixels);
  SDL_UnlockSurface(source);

  if (mipmaps) {
    DO_VALIDATION;
    mapping.glGenerateMipmap(GL_TEXTURE_2D);
  }
  GLint filter_min, filter_mag;

  bool filter = true;

  if (filter == true) {
    DO_VALIDATION;
    filter_min = (mipmaps) ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR;
    filter_mag = GL_LINEAR;
    // glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT,
    // &largest_supported_anisotropy);
    SetMaxAnisotropy();
  } else {
    filter_min = (mipmaps) ? GL_NEAREST_MIPMAP_NEAREST : GL_NEAREST;
    filter_mag = GL_NEAREST;
  }

  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter_min);
  mapping.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter_mag);

  BindTexture(0);
}

void OpenGLRenderer3D::DeleteTexture(int textureID) {
  DO_VALIDATION;
  GLuint texID = textureID;
  // printf("deleting tex id: %i\n", textureID);
  mapping.glDeleteTextures(1, &texID);
}

void OpenGLRenderer3D::CopyFrameBufferToTexture(int textureID, int width,
                                                int height) {
  DO_VALIDATION;
  mapping.glBindTexture(GL_TEXTURE_2D, textureID);
  mapping.glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 0, 0, width, height);
}

void OpenGLRenderer3D::BindTexture(int textureID) {
  DO_VALIDATION;
  mapping.glBindTexture(GL_TEXTURE_2D, (GLuint)textureID);
}

void OpenGLRenderer3D::SetTextureUnit(int textureUnit) {
  DO_VALIDATION;
  if (textureUnit != _cache_activeTextureUnit) {
    DO_VALIDATION;
    // assert(glActiveTexture);
    mapping.glActiveTexture(GL_TEXTURE0 + (GLuint)textureUnit);
    _cache_activeTextureUnit = textureUnit;
  }
}

void OpenGLRenderer3D::SetClientTextureUnit(int textureUnit) {
  DO_VALIDATION;
  // assert(glClientActiveTexture);
  mapping.glClientActiveTexture(GL_TEXTURE0 + (GLuint)textureUnit);
}

void OpenGLRenderer3D::SetMaxAnisotropy() {
  DO_VALIDATION;
//#ifndef __APPLE__  // Can be used to check for Core Profile Mode on Linux
  mapping.glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT,
          largest_supported_anisotropy);
//#endif
}

  // frame buffer objects

GLenum GetGLTargetAttachment(e_TargetAttachment targetAttachment) {
  DO_VALIDATION;
  GLenum target = GL_FRONT;

  switch (targetAttachment) {
    DO_VALIDATION;

    case e_TargetAttachment_None:
      target = GL_NONE;
      break;
    case e_TargetAttachment_Front:
      target = GL_FRONT_LEFT;
      break;
    case e_TargetAttachment_Back:
      target = GL_BACK_LEFT;
      break;
    case e_TargetAttachment_Depth:
      target = GL_DEPTH_ATTACHMENT;
      break;
    case e_TargetAttachment_Stencil:
      target = GL_STENCIL_ATTACHMENT;
      break;
    case e_TargetAttachment_Color0:
      target = GL_COLOR_ATTACHMENT0;
      break;
    case e_TargetAttachment_Color1:
      target = GL_COLOR_ATTACHMENT1;
      break;
    case e_TargetAttachment_Color2:
      target = GL_COLOR_ATTACHMENT2;
      break;
    case e_TargetAttachment_Color3:
      target = GL_COLOR_ATTACHMENT3;
      break;
  }

  return target;
}

int OpenGLRenderer3D::CreateFrameBuffer() {
  DO_VALIDATION;
  GLuint id = 0;
  mapping.glGenFramebuffers(1, &id);
  return id;
}

void OpenGLRenderer3D::DeleteFrameBuffer(int fbID) {
  DO_VALIDATION;
  const GLuint id = fbID;
  mapping.glDeleteFramebuffers(1, &id);
}

void OpenGLRenderer3D::BindFrameBuffer(int fbID) {
  DO_VALIDATION;
  mapping.glBindFramebuffer(GL_FRAMEBUFFER, (GLuint)fbID);
}

void OpenGLRenderer3D::SetFrameBufferRenderBuffer(
    e_TargetAttachment targetAttachment, int rbID) {
  DO_VALIDATION;
  mapping.glFramebufferRenderbuffer(GL_FRAMEBUFFER,
                                    GetGLTargetAttachment(targetAttachment),
                                    GL_RENDERBUFFER, rbID);
}

void OpenGLRenderer3D::SetFrameBufferTexture2D(
    e_TargetAttachment targetAttachment, int texID) {
  DO_VALIDATION;
  mapping.glFramebufferTexture2D(GL_FRAMEBUFFER,
                                 GetGLTargetAttachment(targetAttachment),
                                 GL_TEXTURE_2D, texID, 0);
}

bool OpenGLRenderer3D::CheckFrameBufferStatus() {
  DO_VALIDATION;
  GLenum status = mapping.glCheckFramebufferStatus(GL_FRAMEBUFFER);
  if (status == GL_FRAMEBUFFER_COMPLETE) {
    DO_VALIDATION;
    return true;
  } else {
    Log(e_FatalError, "OpenGLRenderer3D", "CheckFrameBufferStatus",
        "Framebuffer error state #" + int_to_str(status));
    return false;
  }
}

  // render targets

void OpenGLRenderer3D::SetRenderTargets(
    std::vector<e_TargetAttachment> targetAttachments) {
  DO_VALIDATION;
#ifdef WIN32
  std::vector<GLenum> targets(targetAttachments.size());
#else
  GLenum targets[targetAttachments.size()];
#endif
  for (int i = 0; i < (signed int)targetAttachments.size(); i++) {
    DO_VALIDATION;
    targets[i] = GetGLTargetAttachment(targetAttachments[i]);
  }
#ifdef WIN32
  mapping.glDrawBuffers(targetAttachments.size(), &targets[0]);
#else
  mapping.glDrawBuffers(targetAttachments.size(), targets);
#endif
}

  // utility

void OpenGLRenderer3D::SetFOV(float angle) {
  DO_VALIDATION;
  FOV = angle;
}

void OpenGLRenderer3D::PushAttribute(int attr) {
  DO_VALIDATION;
  mapping.glPushAttrib((GLbitfield)attr);
}

void OpenGLRenderer3D::PopAttribute() {
  DO_VALIDATION;
  mapping.glPopAttrib();
}

void OpenGLRenderer3D::SetViewport(int x, int y, int width, int height) {
  DO_VALIDATION;
  mapping.glViewport(x, y, width, height);
}

void OpenGLRenderer3D::GetContextSize(int &width, int &height, int &bpp) {
  DO_VALIDATION;
  width = context_width;
  height = context_height;
  bpp = context_bpp;
}

  // shaders

void LoadGLShader(GLuint shaderID, const std::string &filename) {
  DO_VALIDATION;
  std::vector<std::string> source;
  file_to_vector(filename, source);

  std::string source_flat;
  for (int i = 0; i < (signed int)source.size(); i++) {
    DO_VALIDATION;
    source_flat.append(source[i].c_str());
    source_flat.append("\n");
  }

  const char *sourceChar = source_flat.c_str();
  mapping.glShaderSource(shaderID, 1, &sourceChar, NULL);
  mapping.glCompileShader(shaderID);

  GLint compiled = 0;
  mapping.glGetShaderiv(shaderID, GL_COMPILE_STATUS, &compiled);
  if (compiled == GL_FALSE) {
    DO_VALIDATION;
    printf("shader compilation error (%s)\n", filename.c_str());
    Log(e_Warning, "", "LoadGLShader",
        "shader compilation error (" + filename + ")");
  }

  GLint blen = 0;
  GLsizei slen = 0;
  mapping.glGetShaderiv(shaderID, GL_INFO_LOG_LENGTH, &blen);
  if (blen > 1) {
    DO_VALIDATION;
    GLchar *compiler_log = (GLchar *)malloc(blen);
    mapping.glGetShaderInfoLog(shaderID, blen, &slen, compiler_log);
    printf("shader compilation info: %s\n", compiler_log);
    Log(e_Warning, "", "LoadGLShader",
        "shader compilation info (" + filename + "):\n" +
            std::string(compiler_log));
    free(compiler_log);
  }
}

void GeneratePoissonKernel(float *kernel, unsigned int kernelSize) {
  DO_VALIDATION;

  bool usePrecalculatedSet = false;

  if (!usePrecalculatedSet || kernelSize != 32) {
    DO_VALIDATION;
    unsigned int candidateSize = 32;

#ifdef WIN32
    std::vector<Vector3> samples(kernelSize);
    std::vector<Vector3> candidates(candidateSize);
#else
    Vector3 samples[kernelSize];
    Vector3 candidates[candidateSize];
#endif

    for (unsigned int i = 0; i < kernelSize; i++) {
      DO_VALIDATION;

      // first, create a set of candidates. all these are on the 'hull' of a
      // hemisphere.

      for (unsigned int candidate = 0; candidate < candidateSize; candidate++) {
        DO_VALIDATION;
        // http://www.pouet.net/topic.php?which=9613&page=1 (evenly distributed
        // points on hemisphere) "To generate uniformly distributed random
        // points on a sphere, you generate them on a unit cylinder (but not the
        // caps), and project onto the sphere. While it's not intuitive to see,
        // this actually gives uniform distribution." (also see page 2 for
        // corrections!)
        float s = random_non_determ(0.0f, 2.0f * pi);
        float t = random_non_determ(-1.0f, 1.0f);
        float m = std::sqrt(1.0f - t * t);
        candidates[candidate] = Vector3(std::sin(s) * m, std::cos(s) * m,
                                        fabs(t));  // fabs for hemi
      }

      // second, pick the candidate furthest away from the samples already
      // there. this will distribute them evenly all over the hull.

      int furthestCandidateID = 0;
      float furthestCandidateDistance = 0.0f;
      for (unsigned int candidate = 0; candidate < candidateSize; candidate++) {
        DO_VALIDATION;
        float distanceToClosestSample = 1.0f;
        for (unsigned int x = 0; x < i; x++) {
          DO_VALIDATION;
          float distance = candidates[candidate].GetDistance(samples[x]);
          if (distance < distanceToClosestSample)
            distanceToClosestSample = distance;
        }
        if (distanceToClosestSample > furthestCandidateDistance) {
          DO_VALIDATION;
          furthestCandidateDistance = distanceToClosestSample;
          furthestCandidateID = candidate;
        }
      }

      samples[i] = candidates[furthestCandidateID];
    }

    for (unsigned int i = 0; i < kernelSize; i++) {
      DO_VALIDATION;

      // third, randomize the length, so the samples fill the volume.

      float minDistance = 0.14f;
      samples[i] =
          samples[i].GetNormalized(0) * random_non_determ(minDistance, 1.0f);

      // information around the normal vec is most useful
      samples[i] = samples[i] * 0.75f + Vector3(0, 0, 1) * 0.25f;

      kernel[i * 3 + 0] = samples[i].coords[0];
      kernel[i * 3 + 1] = samples[i].coords[1];
      kernel[i * 3 + 2] = samples[i].coords[2];

      // printf("samples[%i].Set(%f, %f, %f);\n", i, samples[i].coords[0],
      // samples[i].coords[1], samples[i].coords[2]);
    }

  } else {  // PRECALCULATED SET
#ifdef WIN32
    std::vector<Vector3> samples(kernelSize);
#else
    Vector3 samples[kernelSize];
#endif

    // these samples seem relatively close to z = 0 (much 'ground effect' on
    // flat surface)
    samples[0].Set(-0.164502, 0.198563, 0.847836);
    samples[1].Set(-0.371169, -0.311732, 0.271810);
    samples[2].Set(0.395387, -0.169534, 0.356410);
    samples[3].Set(0.199861, 0.154104, 0.106548);
    samples[4].Set(0.003958, -0.331189, 0.151894);
    samples[5].Set(-0.128020, 0.276624, 0.133732);
    samples[6].Set(-0.576721, 0.032381, 0.472200);
    samples[7].Set(0.042701, 0.189697, 0.215682);
    samples[8].Set(0.095873, -0.029585, 0.376675);
    samples[9].Set(-0.018931, -0.559727, 0.723850);
    samples[10].Set(0.354553, -0.531634, 0.250052);
    samples[11].Set(0.211686, 0.082632, 0.250673);
    samples[12].Set(-0.586181, -0.060375, 0.086480);
    samples[13].Set(0.529458, -0.009977, 0.084485);
    samples[14].Set(-0.452887, -0.303541, 0.721515);
    samples[15].Set(-0.223906, 0.180655, 0.100284);
    samples[16].Set(-0.278485, -0.709826, 0.082907);
    samples[17].Set(0.195230, 0.204728, 0.573875);
    samples[18].Set(-0.426917, 0.460452, 0.610940);
    samples[19].Set(0.115942, -0.134919, 0.290054);
    samples[20].Set(-0.089691, -0.266767, 0.910242);
    samples[21].Set(0.259113, 0.638836, 0.159923);
    samples[22].Set(0.621548, -0.384182, 0.089235);
    samples[23].Set(0.261258, 0.331540, 0.306923);
    samples[24].Set(0.170094, -0.678424, 0.471292);
    samples[25].Set(-0.398759, -0.300976, 0.082431);
    samples[26].Set(-0.291338, 0.080905, 0.159125);
    samples[27].Set(-0.391219, 0.082053, 0.638896);
    samples[28].Set(0.051567, 0.476222, 0.765788);
    samples[29].Set(-0.181921, 0.545340, 0.430360);
    samples[30].Set(0.542024, 0.161835, 0.173717);
    samples[31].Set(-0.059420, 0.778527, 0.233026);

    Vector3 average;
    for (unsigned int i = 0; i < kernelSize; i++) {
      DO_VALIDATION;
      average += samples[i];
    }
    average /= kernelSize;
    Vector3 newAverage;
    for (unsigned int i = 0; i < kernelSize; i++) {
      DO_VALIDATION;
      samples[i] -= average.Get2D();
      kernel[i * 3 + 0] = samples[i].coords[0];
      kernel[i * 3 + 1] = samples[i].coords[1];
      kernel[i * 3 + 2] = samples[i].coords[2];
      newAverage += samples[i];
    }
    newAverage /= kernelSize;
  }
}

void OpenGLRenderer3D::LoadShader(const std::string &name,
                                  const std::string &filename) {
  DO_VALIDATION;
  GLint info = 0;

  Shader shader;
  shader.name = filename;

  shader.vertexShaderID = mapping.glCreateShader(GL_VERTEX_SHADER);
  LoadGLShader(shader.vertexShaderID, filename + ".vert");
  mapping.glGetShaderiv(shader.vertexShaderID, GL_COMPILE_STATUS, &info);
  if (info != GL_TRUE || mapping.glIsShader(shader.vertexShaderID) != GL_TRUE) {
    DO_VALIDATION;
    printf("%d %d\n", info, mapping.glIsShader(shader.vertexShaderID));
    Log(e_FatalError, "OpenGLRenderer3D", "LoadShader",
        "1Could not compile vertex program: " + name);
  }

  shader.fragmentShaderID = mapping.glCreateShader(GL_FRAGMENT_SHADER);
  LoadGLShader(shader.fragmentShaderID, filename + ".frag");
  mapping.glGetShaderiv(shader.fragmentShaderID, GL_COMPILE_STATUS, &info);
  if (info != GL_TRUE ||
      mapping.glIsShader(shader.fragmentShaderID) != GL_TRUE) {
    DO_VALIDATION;
    Log(e_FatalError, "OpenGLRenderer3D", "LoadShader",
        "2Could not compile fragment program: " + name);
  }

  shader.programID = mapping.glCreateProgram();
  mapping.glAttachShader(shader.programID, shader.vertexShaderID);
  mapping.glAttachShader(shader.programID, shader.fragmentShaderID);

  shaders.insert(std::pair<std::string, Shader>(name, shader));

  if (name == "zphase") {
    DO_VALIDATION;
    mapping.glBindAttribLocation(shader.programID, 0, "position");
    mapping.glBindFragDataLocation(shader.programID, 0, "stdout");
  }
  if (name == "simple") {
    DO_VALIDATION;
    mapping.glBindAttribLocation(shader.programID, 0, "position");
    mapping.glBindAttribLocation(shader.programID, 1, "normal");
    mapping.glBindAttribLocation(shader.programID, 2, "texcoord");
    mapping.glBindAttribLocation(shader.programID, 3, "tangent");
    mapping.glBindAttribLocation(shader.programID, 4, "bitangent");
    mapping.glBindFragDataLocation(shader.programID, 0, "stdout0");
    mapping.glBindFragDataLocation(shader.programID, 1, "stdout1");
    mapping.glBindFragDataLocation(shader.programID, 2, "stdout2");
  }
  if (name == "ambient") {
    DO_VALIDATION;
    mapping.glBindAttribLocation(shader.programID, 0, "position");
    mapping.glBindFragDataLocation(shader.programID, 0, "stdout0");
  }
  if (name == "lighting") {
    DO_VALIDATION;
    mapping.glBindFragDataLocation(shader.programID, 0, "stdout0");
    mapping.glBindFragDataLocation(shader.programID, 1, "stdout1");
  }
  if (name == "postprocess") {
    DO_VALIDATION;
    mapping.glBindAttribLocation(shader.programID, 0, "position");
    mapping.glBindFragDataLocation(shader.programID, 0, "stdout");
  }
  if (name == "overlay") {
    DO_VALIDATION;
    mapping.glBindAttribLocation(shader.programID, 0, "vertex");
    mapping.glBindFragDataLocation(shader.programID, 0, "stdout");
  }

  mapping.glLinkProgram(shader.programID);

  mapping.glUseProgram(shader.programID);

  GLint location = 0;
  if (name == "simple") {
    DO_VALIDATION;
    SetUniformInt("simple", "map_albedo", 0);
    SetUniformInt("simple", "map_normal", 1);
    SetUniformInt("simple", "map_specular", 2);
    SetUniformInt("simple", "map_illumination", 3);
  }
  if (name == "ambient") {
    DO_VALIDATION;
    SetUniformInt("ambient", "map_albedo", 0);
    SetUniformInt("ambient", "map_aux", 3);

    SetUniformFloat("ambient", "contextX", (float)0.0);
    SetUniformFloat("ambient", "contextY", (float)0.0);
    SetUniformFloat("ambient", "contextWidth", (float)context_width);
    SetUniformFloat("ambient", "contextHeight", (float)context_height);
  }
  if (name == "lighting") {
    DO_VALIDATION;
    // on (at least older) nvidia cards, we can't 'skip' id's, or so it seems.
    // so make them consecutive edit ^ not sure after all if that is the case
    SetUniformInt("lighting", "map_albedo", 0);
    SetUniformInt("lighting", "map_normal", 1);
    SetUniformInt("lighting", "map_depth", 2);  // was: 3
    // SetUniformInt("lighting", "map_aux", 3); // was: 2
    SetUniformInt("lighting", "map_shadow", 7);

    SetUniformFloat("lighting", "contextX", (float)0.0);
    SetUniformFloat("lighting", "contextY", (float)0.0);
    SetUniformFloat("lighting", "contextWidth", (float)context_width);
    SetUniformFloat("lighting", "contextHeight", (float)context_height);
  }
  if (name == "postprocess") {
    DO_VALIDATION;
    SetUniformInt("postprocess", "map_accumulation", 0);
    SetUniformInt("postprocess", "map_depth", 2);

    SetUniformFloat("postprocess", "contextX", (float)0.0);
    SetUniformFloat("postprocess", "contextY", (float)0.0);
    SetUniformFloat("postprocess", "contextWidth", (float)context_width);
    SetUniformFloat("postprocess", "contextHeight", (float)context_height);
  }

  SetTextureUnit(0);

  UseShader("");
}

void OpenGLRenderer3D::SetFramebufferGammaCorrection(bool onOff) {
  DO_VALIDATION;
  if (onOff) {
    DO_VALIDATION;
    mapping.glEnable(GL_FRAMEBUFFER_SRGB);
  } else {
    mapping.glDisable(GL_FRAMEBUFFER_SRGB);
  }
}

void OpenGLRenderer3D::UseShader(const std::string &name) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(name);
  if (shaderIter != shaders.end()) {
    DO_VALIDATION;

    currentShader = shaderIter;

    mapping.glUseProgram((*shaderIter).second.programID);
  } else {
    mapping.glUseProgram(0);
  }
}

void OpenGLRenderer3D::SetUniformInt(const std::string &shaderName,
                                     const std::string &varName, int value) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(shaderName);
  assert(shaderIter != shaders.end());

  std::map<std::string, GLint>::iterator iter =
      uniformCache.find(shaderName + "_var_" + varName);
  GLint location = 0;
  if (iter != uniformCache.end()) {
    DO_VALIDATION;
    location = iter->second;
  } else {
    location = mapping.glGetUniformLocation((*shaderIter).second.programID,
                                            varName.c_str());
    if (location == -1)
      Log(e_Error, "OpenGLRenderer3D", "SetUniformInt",
          "Uniform location for shader '" + shaderName +
              "' not found: " + varName);
    uniformCache.insert(std::pair<std::string, GLint>(
        shaderName + "_var_" + varName, location));
  }
  mapping.glUniform1i(location, value);
}

void OpenGLRenderer3D::SetUniformInt3(const std::string &shaderName,
                                      const std::string &varName, int value1,
                                      int value2, int value3) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(shaderName);
  assert(shaderIter != shaders.end());

  std::map<std::string, GLint>::iterator iter =
      uniformCache.find(shaderName + "_var_" + varName);
  GLint location = 0;
  if (iter != uniformCache.end()) {
    DO_VALIDATION;
    location = iter->second;
  } else {
    location = mapping.glGetUniformLocation((*shaderIter).second.programID,
                                            varName.c_str());
    if (location == -1)
      Log(e_Error, "OpenGLRenderer3D", "SetUniformInt3",
          "Uniform location for shader '" + shaderName +
              "' not found: " + varName);
    uniformCache.insert(std::pair<std::string, GLint>(
        shaderName + "_var_" + varName, location));
  }
  mapping.glUniform3i(location, value1, value2, value3);
}

void OpenGLRenderer3D::SetUniformFloat(const std::string &shaderName,
                                       const std::string &varName,
                                       float value) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(shaderName);
  assert(shaderIter != shaders.end());

  std::map<std::string, GLint>::iterator iter =
      uniformCache.find(shaderName + "_var_" + varName);
  GLint location = 0;
  if (iter != uniformCache.end()) {
    DO_VALIDATION;
    location = iter->second;
  } else {
    location = mapping.glGetUniformLocation((*shaderIter).second.programID,
                                            varName.c_str());
    if (location == -1)
      Log(e_Error, "OpenGLRenderer3D", "SetUniformFloat",
          "Uniform location for shader '" + shaderName +
              "' not found: " + varName);
    uniformCache.insert(std::pair<std::string, GLint>(
        shaderName + "_var_" + varName, location));
  }
  mapping.glUniform1f(location, value);
}

void OpenGLRenderer3D::SetUniformFloat2(const std::string &shaderName,
                                        const std::string &varName,
                                        float value1, float value2) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(shaderName);
  assert(shaderIter != shaders.end());

  std::map<std::string, GLint>::iterator iter =
      uniformCache.find(shaderName + "_var_" + varName);
  GLint location = 0;
  if (iter != uniformCache.end()) {
    DO_VALIDATION;
    location = iter->second;
  } else {
    location = mapping.glGetUniformLocation((*shaderIter).second.programID,
                                            varName.c_str());
    if (location == -1)
      Log(e_Error, "OpenGLRenderer3D", "SetUniformFloat2",
          "Uniform location for shader '" + shaderName +
              "' not found: " + varName);
    uniformCache.insert(std::pair<std::string, GLint>(
        shaderName + "_var_" + varName, location));
  }
  mapping.glUniform2f(location, value1, value2);
}

void OpenGLRenderer3D::SetUniformFloat3(const std::string &shaderName,
                                        const std::string &varName,
                                        float value1, float value2,
                                        float value3) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(shaderName);
  assert(shaderIter != shaders.end());

  std::map<std::string, GLint>::iterator iter =
      uniformCache.find(shaderName + "_var_" + varName);
  GLint location = 0;
  if (iter != uniformCache.end()) {
    DO_VALIDATION;
    location = iter->second;
  } else {
    location = mapping.glGetUniformLocation((*shaderIter).second.programID,
                                            varName.c_str());
    if (location == -1)
      Log(e_Error, "OpenGLRenderer3D", "SetUniformFloat3",
          "Uniform location for shader '" + shaderName +
              "' not found: " + varName);
    uniformCache.insert(std::pair<std::string, GLint>(
        shaderName + "_var_" + varName, location));
  }
  mapping.glUniform3f(location, value1, value2, value3);
}

void OpenGLRenderer3D::SetUniformFloat3Array(const std::string &shaderName,
                                             const std::string &varName,
                                             int count, float *values) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(shaderName);
  assert(shaderIter != shaders.end());

  std::map<std::string, GLint>::iterator iter =
      uniformCache.find(shaderName + "_var_" + varName);
  GLint location = 0;
  if (iter != uniformCache.end()) {
    DO_VALIDATION;
    location = iter->second;
  } else {
    location = mapping.glGetUniformLocation((*shaderIter).second.programID,
                                            varName.c_str());
    if (location == -1)
      Log(e_Error, "OpenGLRenderer3D", "SetUniformFloat3Array",
          "Uniform location for shader '" + shaderName +
              "' not found: " + varName);
    uniformCache.insert(std::pair<std::string, GLint>(
        shaderName + "_var_" + varName, location));
  }
  mapping.glUniform3fv(location, count, values);
}

void OpenGLRenderer3D::SetUniformMatrix4(const std::string &shaderName,
                                         const std::string &varName,
                                         const Matrix4 &mat) {
  DO_VALIDATION;
  std::map<std::string, Shader>::iterator shaderIter = shaders.find(shaderName);
  assert(shaderIter != shaders.end());

  std::map<std::string, GLint>::iterator iter =
      uniformCache.find(shaderName + "_var_" + varName);
  GLint location = 0;
  if (iter != uniformCache.end()) {
    DO_VALIDATION;
    location = iter->second;
  } else {
    location = mapping.glGetUniformLocation((*shaderIter).second.programID,
                                            varName.c_str());
    if (location == -1)
      Log(e_Error, "OpenGLRenderer3D", "SetUniformMatrix4",
          "Uniform location for shader '" + shaderName +
              "' not found: " + varName);
    uniformCache.insert(std::pair<std::string, GLint>(
        shaderName + "_var_" + varName, location));
  }
  // mapping.glUniformMatrix4fv(location, 1, false,
  // (float*)mat.GetTransposed().elements);
  mapping.glUniformMatrix4fv(location, 1, true,
                             (float *)mat.elements);  // true == transposed
}

void OpenGLRenderer3D::SetContext() {
  if (window) {
    SDL_GL_MakeCurrent(window, context);
  }
}

void OpenGLRenderer3D::DisableContext() {
  if (window) {
    SDL_GL_MakeCurrent(window, nullptr);
  }
}

void OpenGLRenderer3D::RequestVideoKeyframe() {
}

std::vector<std::string> OpenGLRenderer3D::TakeVideoPackets() {
  return {};
}

const screenshoot &OpenGLRenderer3D::GetScreen() {
  if (present_window_) {
    ReadScreen();
  }
  return last_screen_;
}
}
