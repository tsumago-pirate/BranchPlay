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

#ifndef _HPP_GRAPHICS3D_OPENGL
#define _HPP_GRAPHICS3D_OPENGL
#ifdef __linux__
#include <EGL/egl.h>
#endif

#include "interface_renderer3d.hpp"
#include "frame_encoder.hpp"

namespace blunted {

  class OpenGLRenderer3D : public Renderer3D {

    public:
      OpenGLRenderer3D();
      virtual void SetContext();
      virtual void DisableContext();
      virtual const screenshoot& GetScreen();
      virtual void RequestVideoKeyframe();
      virtual std::vector<std::string> TakeVideoPackets();
      virtual ~OpenGLRenderer3D();

      virtual void SwapBuffers();
      virtual WindowControl PollWindow(bool free_look);
      virtual bool PresentsWindow() const;
      virtual void SetFullscreen(bool on);
      virtual void ShowWindow();
      virtual void PlacePlaybackWindow();
      virtual void RestorePlaybackWindow();
      virtual void SetBottomBand(int points);
      virtual bool Fullscreen() const;
      virtual void GetPresentRect(int context_x, int context_y, int context_w,
                                 int context_h, int &x, int &y, int &w,
                                 int &h);
      virtual void GetDrawableSize(int &w, int &h);
      virtual void FitOutputToWindow();
      virtual void SetMouseLook(bool on);
      virtual void RememberClip(const Matrix4 &projection, const Matrix4 &view,
                                int vp_x, int vp_y, int vp_w, int vp_h);
      virtual bool ScreenRay(int x, int y, Vector3 &near_point,
                             Vector3 &far_point) const;
      virtual void SetSelectionBoxes(const float *corners, int box_count);
      virtual void SetLinkLines(const float *points, int line_count);
      virtual void SetEditRect(bool on, float x0, float y0, float x1, float y1);
      virtual bool ProjectToHud(float x, float y, float z, float &hud_x,
                                float &hud_y) const;
      virtual void SetMomentRings(const float *xyz, const int *counts,
                                  const int *colors, int rings);
      virtual void DrawSelectionBoxes(const Matrix4 &projection,
                                      const Matrix4 &view);
      virtual void DrawMomentRings(const Matrix4 &projection,
                                   const Matrix4 &view, int accum_buffer,
                                   int depth_tex, int width, int height);

      virtual void SetMatrix(const std::string &shaderUniformName, const Matrix4 &matrix);

      virtual void RenderOverlay2D(const std::vector<Overlay2DQueueEntry> &overlay2DQueue);
      virtual void RenderOverlay2D();
      virtual void RenderLights(std::deque<LightQueueEntry> &lightQueue, const Matrix4 &projectionMatrix, const Matrix4 &viewMatrix);


      // --- new & improved

      // init & exit
      virtual bool CreateContext(int width, int height, int bpp, bool fullscreen);
      virtual void Exit();

      virtual int CreateView(float x_percent, float y_percent, float width_percent, float height_percent);
      virtual View &GetView(int viewID);
      virtual void DeleteView(int viewID);

      // general
      virtual void SetCullingMode(e_CullingMode cullingMode);
      virtual void SetBlendingMode(e_BlendingMode blendingMode);
      virtual void SetDepthFunction(e_DepthFunction depthFunction);
      virtual void SetDepthTesting(bool OnOff);
      virtual void SetDepthMask(bool OnOff);
      virtual void SetBlendingFunction(e_BlendingFunction blendingFunction1, e_BlendingFunction blendingFunction2);
      virtual void SetTextureMode(e_TextureMode textureMode);
      virtual void SetColor(const Vector3 &color, float alpha);
      virtual void SetColorMask(bool r, bool g, bool b, bool alpha);

      virtual void ClearBuffer(const Vector3 &color, bool clearDepth, bool clearColor);

      virtual Matrix4 CreatePerspectiveMatrix(float aspectRatio, float nearCap = -1, float farCap = -1);
      virtual Matrix4 CreateOrthoMatrix(float left, float right, float bottom, float top, float nearCap = -1, float farCap = -1);

      // vertex buffers
      virtual VertexBufferID CreateVertexBuffer(float *vertices, unsigned int verticesDataSize, const std::vector<unsigned int>& indices, e_VertexBufferUsage usage);
      virtual void UpdateVertexBuffer(VertexBufferID vertexBufferID, float *vertices, unsigned int verticesDataSize);
      virtual void DeleteVertexBuffer(VertexBufferID vertexBufferID);
      virtual void RenderVertexBuffer(const std::deque<VertexBufferQueueEntry> &vertexBufferQueue, e_RenderMode renderMode = e_RenderMode_Full);

      // lights
      virtual void SetLight(const Vector3 &position, const Vector3 &color, float radius);

      // textures
      virtual int CreateTexture(e_InternalPixelFormat internalPixelFormat, e_PixelFormat pixelFormat, int width, int height, bool alpha = false, bool repeat = true, bool mipmaps = true, bool filter = true, bool multisample = false, bool compareDepth = false);
      virtual void ResizeTexture(int textureID, SDL_Surface *source, e_InternalPixelFormat internalPixelFormat, e_PixelFormat pixelFormat, bool alpha = false, bool mipmaps = true);
      virtual void UpdateTexture(int textureID, SDL_Surface *source, bool alpha = false, bool mipmaps = true);
      virtual void DeleteTexture(int textureID);
      virtual void CopyFrameBufferToTexture(int textureID, int width, int height);
      virtual void BindTexture(int textureID);
      virtual void SetTextureUnit(int textureUnit);
      virtual void SetClientTextureUnit(int textureUnit);

      // frame buffers
      virtual int CreateFrameBuffer();
      virtual void DeleteFrameBuffer(int fbID);
      virtual void BindFrameBuffer(int fbID);
      virtual void SetFrameBufferRenderBuffer(e_TargetAttachment targetAttachment, int rbID);
      virtual void SetFrameBufferTexture2D(e_TargetAttachment targetAttachment, int texID);
      virtual bool CheckFrameBufferStatus();
      virtual void SetFramebufferGammaCorrection(bool onOff);

      // render targets
      virtual void SetRenderTargets(std::vector<e_TargetAttachment> targetAttachments);

      // utility
      virtual void SetFOV(float angle);
      virtual void PushAttribute(int attr);
      virtual void PopAttribute();
      virtual void SetViewport(int x, int y, int width, int height);
      virtual void GetContextSize(int &width, int &height, int &bpp);

      // shaders
      virtual void LoadShader(const std::string &name, const std::string &filename);
      virtual void UseShader(const std::string &name);
      virtual void SetUniformInt(const std::string &shaderName, const std::string &varName, int value);
      virtual void SetUniformInt3(const std::string &shaderName, const std::string &varName, int value1, int value2, int value3);
      virtual void SetUniformFloat(const std::string &shaderName, const std::string &varName, float value);
      virtual void SetUniformFloat2(const std::string &shaderName, const std::string &varName, float value1, float value2);
      virtual void SetUniformFloat3(const std::string &shaderName, const std::string &varName, float value1, float value2, float value3);
      virtual void SetUniformFloat3Array(const std::string &shaderName, const std::string &varName, int count, float *values);
      virtual void SetUniformMatrix4(const std::string &shaderName, const std::string &varName, const Matrix4 &mat);

    protected:
      SDL_GLContext context = 0;
      SDL_Window* window = nullptr;
#ifdef __linux__
      EGLDisplay egl_display = nullptr;
      EGLSurface egl_surface;
      EGLContext egl_context;
#endif
      int context_width, context_height, context_bpp;
      // The timeline's height in window points, and how much of that the
      // window has already grown by. The camera fills that strip.
      int bottom_band_points_ = 0;
      int applied_band_points_ = 0;
      bool playback_placed_ = false;
      bool playback_fullscreen_ = false;
      int playback_x_ = 0;
      int playback_y_ = 0;
      int playback_w_ = 0;
      int playback_h_ = 0;
      int playback_view_x_ = 0;
      int playback_view_y_ = 0;
      int playback_view_w_ = 0;
      int playback_view_h_ = 0;
      int playback_band_ = 0;
      void WaitUntilWindowed();
      void HoldPlaybackFrame();
      void ApplyBottomBand();
      int BottomBandPixels() const;
      virtual float BottomBandShare() const;

      float cameraNear = 0.0f;
      float cameraFar = 0.0f;

      int noiseTexID = 0;

      float FOV = 0.0f;

      float overallBrightness = 0.0f;

      float largest_supported_anisotropy = 0.0f;
      void SetMaxAnisotropy();

      std::map<std::string, int> uniformCache;

      std::map<int, int> VBOPingPongMap;
      std::map<int, int> VAOPingPongMap;
      std::map<int, int> VAOReadIndex;

      signed int _cache_activeTextureUnit = 0;
      screenshoot last_screen_;
      bool present_window_ = false;
      bool mouse_down_ = false;
      bool right_down_ = false;
      bool mouse_dragged_ = false;
      int mouse_down_x_ = 0;
      int mouse_down_y_ = 0;
      Matrix4 clip_;
      Matrix4 clip_inverse_;
      bool edit_rect_ = false;
      float edit_x0_ = 0;
      float edit_y0_ = 0;
      float edit_x1_ = 0;
      float edit_y1_ = 0;
      bool clip_ready_ = false;
      int vp_x_ = 0;
      int vp_y_ = 0;
      int vp_w_ = 0;
      int vp_h_ = 0;
      int picture_x_ = 0;
      int picture_y_ = 0;
      int picture_w_ = 0;
      int picture_h_ = 0;
      int pick_w_ = 0;
      int pick_h_ = 0;
      int draw_w_ = 0;
      int draw_h_ = 0;
      std::vector<float> box_corners_;
      int box_count_ = 0;
      std::vector<float> link_points_;
      int link_count_ = 0;
      std::vector<float> moment_xyz_;
      std::vector<int> moment_counts_;
      std::vector<int> moment_colors_;
      unsigned int box_program_ = 0;
      unsigned int thick_program_ = 0;
      unsigned int box_vao_ = 0;
      unsigned int box_vbo_ = 0;
      bool box_failed_ = false;
      bool thick_failed_ = false;
      void EnsureBoxProgram();
      void EnsureThickProgram();
      int ToHudX(int x) const;
      int ToHudY(int y) const;
      bool HudToNdc(float x, float y, float &ndc_x, float &ndc_y) const;
      void ReadScreen();
      FrameEncoder* frame_encoder_ = nullptr;
      bool video_failed_ = false;
      int video_attempts_ = 0;
      // members and functions for rendering overlay with shaders instead of deprecated methods
      VertexBufferID overlayBuffer;  // buffer for drawing textures such as player's names and game score
      VertexBufferID quadBuffer;     // buffer for drawing simple quads
      VertexBufferID CreateSimpleVertexBuffer(float *vertices, unsigned int size);
      void DeleteSimpleVertexBuffer(VertexBufferID vertexBufferID);
      void InitializeOverlayAndQuadBuffers();
      void CreateContextSdl();
      void ReleaseViewTargets(View &view);
      void BuildViewTargets(View &view);
#ifdef __linux__
      void CreateContextEgl();
#endif
  };
}

#endif
