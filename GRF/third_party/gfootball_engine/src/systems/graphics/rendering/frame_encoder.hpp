#ifndef BRANCHPLAY_FRAME_ENCODER_HPP
#define BRANCHPLAY_FRAME_ENCODER_HPP

#include <string>
#include <vector>

#ifdef __APPLE__
struct opaqueCMSampleBuffer;
#endif

namespace blunted {

// Hardware H.264 of the frame that was just drawn. The live page plays these
// packets. When this is off, the renderer keeps copying the picture to memory.
struct FrameEncoder {
  FrameEncoder();
  ~FrameEncoder();
  FrameEncoder(const FrameEncoder&) = delete;
  FrameEncoder& operator=(const FrameEncoder&) = delete;

  // GL context is current and the finished picture is in the back buffer.
  bool capture_and_encode(int width, int height);
  void request_keyframe();
  std::vector<std::string> take();

 private:
  struct State;
#ifdef __APPLE__
  // Same shape as the VideoToolbox output callback. The system headers are
  // included only in the encoder file, because they publish a global pi.
  static void OnEncoded(void* refcon, void* source, int status, unsigned flags,
                        opaqueCMSampleBuffer* sample);
#endif
  State* state_;
};

}

#endif
