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

#ifndef _HPP_RENDERER3D
#define _HPP_RENDERER3D

#include "../../../types/resource.hpp"

#include <string>
#include <vector>

#include "../../../base/sdl_surface.hpp"
#include "../../../base/math/vector3.hpp"

#include "../resources/vertexbuffer.hpp"

#include "../../../base/geometry/triangle.hpp"

#include "../../../types/material.hpp"

namespace blunted {

  class Camera;
  class Geometry;
  class Texture;

  struct Overlay2DQueueEntry {
    boost::intrusive_ptr < Resource<Texture> > texture;
    int position[2];
    int size[2];
    float alpha = 1.0f;
  };

  struct Renderer3DMaterial {
    boost::intrusive_ptr < Resource<Texture> > diffuseTexture;
    boost::intrusive_ptr < Resource<Texture> > normalTexture;
    boost::intrusive_ptr < Resource<Texture> > specularTexture;
    boost::intrusive_ptr < Resource<Texture> > illuminationTexture;
    float shininess = 0.0f;
    float specular_amount = 0.0f;
    Vector3 self_illumination;
  };

  struct VertexBufferIndex {
    int startIndex = 0;
    int size = 0;
    Renderer3DMaterial material;
  };

  struct VertexBufferQueueEntry {
    std::list<VertexBufferIndex>* vertexBufferIndices;
    boost::intrusive_ptr < Resource<VertexBuffer> > vertexBuffer;
    AABB aabb;
    Vector3 position;
    Quaternion rotation;

  };

  struct ShadowMap {
    std::string cameraName;
    Matrix4 lightProjectionMatrix;
    Matrix4 lightViewMatrix;
    std::deque < VertexBufferQueueEntry > visibleGeometry;
    boost::intrusive_ptr < Resource<Texture> > texture;
    int frameBufferID = 0;
    // Window size this map was built for. A resize was replacing the
    // stored depth image with the window size.
    int kept_w = 0;
    int kept_h = 0;
  };

  enum e_ViewRenderTarget {
    e_ViewRenderTarget_Texture,
    e_ViewRenderTarget_Context
  };

  struct View {
    e_ViewRenderTarget target;
    int targetTexID = 0;
    int x, y, width, height;
    // Percent of the window these pixels were made from, so a resize can
    // rebuild the picture at the new size.
    float x_percent = 0;
    float y_percent = 0;
    float width_percent = 100;
    float height_percent = 100;

    int gBufferID = 0;
    int gBuffer_DepthTexID = 0;
    int gBuffer_AlbedoTexID = 0;
    int gBuffer_NormalTexID = 0;
    int gBuffer_AuxTexID = 0;

    int accumBufferID = 0;
    int accumBuffer_AccumTexID = 0;
    int accumBuffer_ModifierTexID = 0;
  };

  struct LightQueueEntry {
    bool hasShadow = false;
    Matrix4 lightProjectionMatrix;
    Matrix4 lightViewMatrix;
    boost::intrusive_ptr < Resource<Texture> > shadowMapTexture;
    Vector3 position;
    int type = 0; // 0 == directional, 1 == point
    Vector3 color;
    float radius = 0.0f;
    bool shadow = false;
    AABB aabb;
  };

  enum e_MatrixMode {
    e_MatrixMode_Projection,
    e_MatrixMode_ModelView
  };

  enum e_CullingMode {
    e_CullingMode_Off,
    e_CullingMode_Front,
    e_CullingMode_Back
  };

  enum e_BlendingMode {
    e_BlendingMode_Off,
    e_BlendingMode_On
  };

  enum e_BlendingFunction {
    e_BlendingFunction_Zero,
    e_BlendingFunction_One
  };

  enum e_DepthFunction {
    e_DepthFunction_Never,
    e_DepthFunction_Equal,
    e_DepthFunction_Greater,
    e_DepthFunction_Less,
    e_DepthFunction_GreaterOrEqual,
    e_DepthFunction_LessOrEqual,
    e_DepthFunction_NotEqual,
    e_DepthFunction_Always
  };

  enum e_TextureMode {
    e_TextureMode_Off,
    e_TextureMode_2D
  };

  enum e_TargetAttachment {
    e_TargetAttachment_None,
    e_TargetAttachment_Front,
    e_TargetAttachment_Back,
    e_TargetAttachment_Depth, // can not be used with drawbuffers
    e_TargetAttachment_Stencil, // can not be used with drawbuffers
    e_TargetAttachment_Color0,
    e_TargetAttachment_Color1,
    e_TargetAttachment_Color2,
    e_TargetAttachment_Color3
  };

  enum e_PixelFormat {
    e_PixelFormat_Alpha,
    e_PixelFormat_RGB,
    e_PixelFormat_RGBA,
    e_PixelFormat_DepthComponent,
    e_PixelFormat_Luminance
  };

  enum e_InternalPixelFormat {
//    e_InternalPixelFormat_RGB,
    e_InternalPixelFormat_RGB8,
    e_InternalPixelFormat_SRGB8,
    e_InternalPixelFormat_RGB16,
//    e_InternalPixelFormat_RGBA,
    e_InternalPixelFormat_RGBA8,
    e_InternalPixelFormat_SRGBA8,
    e_InternalPixelFormat_RGBA16,
    e_InternalPixelFormat_RGBA16F,
    e_InternalPixelFormat_RGBA32F,

    e_InternalPixelFormat_RGBA4,
		e_InternalPixelFormat_RGB5_A1,
		e_InternalPixelFormat_DepthComponent,
		e_InternalPixelFormat_DepthComponent16,
		e_InternalPixelFormat_DepthComponent24,
		e_InternalPixelFormat_DepthComponent32,
		e_InternalPixelFormat_DepthComponent32F,
		e_InternalPixelFormat_StencilIndex8
  };

  enum e_VertexBufferUsage {
    e_VertexBufferUsage_StreamDraw,
    e_VertexBufferUsage_StreamRead,
    e_VertexBufferUsage_StreamCopy,
    e_VertexBufferUsage_StaticDraw,
    e_VertexBufferUsage_StaticRead,
    e_VertexBufferUsage_StaticCopy,
    e_VertexBufferUsage_DynamicDraw,
    e_VertexBufferUsage_DynamicRead,
    e_VertexBufferUsage_DynamicCopy
  };

  enum e_RenderMode {
    e_RenderMode_GeometryOnly,
    e_RenderMode_Diffuse,
    e_RenderMode_Full
  };

  struct Shader {
    std::string name;
    unsigned int programID = 0;
    unsigned int vertexShaderID = 0;
    unsigned int fragmentShaderID = 0;
  };

  // Keys and drag from the visible match window. The hidden-window path
  // leaves this empty and keeps taking input on the browser page.
  struct WindowControl {
    bool freeze = false;
    bool escape = false;
    bool view_prev = false;
    bool view_next = false;
    bool lens = false;
    int look_dx = 0;
    int look_dy = 0;
    bool forward = false;
    bool back = false;
    bool left = false;
    bool right = false;
    bool down = false;
    bool up = false;
    bool fast = false;
    // Mouse positions are in the same pixels as the match HUD.
    bool pressed = false;
    bool released = false;
    bool clicked = false;
    // 2 when this click is the second of a double-click.
    int clicks = 0;
    // Delete or Backspace. Edit mode removes the selected players.
    bool remove_players = false;
    bool mouse_held = false;
    bool dragged = false;
    // Right button. Edit mode looks with this and moves players with the left.
    bool look_held = false;
    int x = 0;
    int y = 0;
    int press_x = 0;
    int press_y = 0;
    int click_x = 0;
    int click_y = 0;
  };

  class Renderer3D {

    public:
      virtual ~Renderer3D() { DO_VALIDATION;};
      virtual void SetContext() = 0;
      virtual void DisableContext() = 0;
      virtual const screenshoot& GetScreen() = 0;
      // Empty unless the live page is playing a hardware-encoded video.
      virtual void RequestVideoKeyframe() {}
      virtual std::vector<std::string> TakeVideoPackets() { return {}; }

      virtual void SwapBuffers() = 0;
      virtual WindowControl PollWindow(bool free_look) {
        (void)free_look;
        WindowControl unused;
        return unused;
      }
      virtual bool PresentsWindow() const { return false; }
      virtual void SetMouseLook(bool on) { (void)on; }
      virtual void SetFullscreen(bool on) { (void)on; }
      virtual void ShowWindow() {}
      // Leave fullscreen and inset the window for a key-moment clip, then
      // put the previous frame back. The picture is still this window.
      virtual void PlacePlaybackWindow() {}
      virtual void RestorePlaybackWindow() {}
      // Points of window height reserved under the picture for the timeline.
      virtual void SetBottomBand(int points) { (void)points; }
      virtual bool Fullscreen() const { return false; }
      // Where a context-sized rectangle lands in the window. A larger
      // window letterboxes the 1280 by 720 picture instead of stretching it.
      virtual void GetPresentRect(int context_x, int context_y, int context_w,
                                 int context_h, int &x, int &y, int &w,
                                 int &h) {
        x = context_x;
        y = context_y;
        w = context_w;
        h = context_h;
      }
      virtual void GetDrawableSize(int &w, int &h) {
        int bpp = 0;
        GetContextSize(w, h, bpp);
      }
      // A larger window renders at the window size. The camera then sees
      // more, instead of painting black bars around a fixed picture.
      virtual void FitOutputToWindow() {}

      // The picture's projection, kept so a click can be turned back into a
      // world ray. vp_* is the viewport the picture was drawn into, in
      // drawable pixels, origin bottom left.
      virtual void RememberClip(const Matrix4 &projection, const Matrix4 &view,
                                int vp_x, int vp_y, int vp_w, int vp_h) {
        (void)projection;
        (void)view;
        (void)vp_x;
        (void)vp_y;
        (void)vp_w;
        (void)vp_h;
      }
      virtual bool ScreenRay(int x, int y, Vector3 &near_point,
                             Vector3 &far_point) const {
        (void)x;
        (void)y;
        (void)near_point;
        (void)far_point;
        return false;
      }
      // corners is box_count boxes, 8 xyz corners each, 24 floats per box.
      virtual void SetSelectionBoxes(const float *corners, int box_count) {
        (void)corners;
        (void)box_count;
      }
      // points is line_count segments, two xyz ends each, 6 floats per line.
      virtual void SetLinkLines(const float *points, int line_count) {
        (void)points;
        (void)line_count;
      }
      // A drag rectangle in HUD pixels. Off clears it.
      virtual void SetEditRect(bool on, float x0, float y0, float x1, float y1) {
        (void)on;
        (void)x0;
        (void)y0;
        (void)x1;
        (void)y1;
      }
      // The same HUD pixels a click uses. False when the point is behind the camera.
      virtual bool ProjectToHud(float x, float y, float z, float &hud_x,
                                float &hud_y) const {
        (void)x;
        (void)y;
        (void)z;
        (void)hud_x;
        (void)hud_y;
        return false;
      }
      // xyz is rings of counts[i] points. colors[i] 0 is magenta, 1 is cyan.
      virtual void SetMomentRings(const float *xyz, const int *counts,
                                  const int *colors, int rings) {
        (void)xyz;
        (void)counts;
        (void)colors;
        (void)rings;
      }
      virtual void DrawSelectionBoxes(const Matrix4 &projection,
                                      const Matrix4 &view) {
        (void)projection;
        (void)view;
      }
      // Rings on the pitch. Drawn into the lit picture, tested against the
      // scene depth, so a player covers the ring where they stand.
      virtual void DrawMomentRings(const Matrix4 &projection,
                                   const Matrix4 &view, int accum_buffer,
                                   int depth_tex, int width, int height) {
        (void)projection;
        (void)view;
        (void)accum_buffer;
        (void)depth_tex;
        (void)width;
        (void)height;
      }

      virtual void SetMatrix(const std::string &shaderUniformName, const Matrix4 &matrix) = 0;

      virtual void RenderOverlay2D(const std::vector<Overlay2DQueueEntry> &overlay2DQueue) = 0;
      virtual void RenderOverlay2D() = 0;
      virtual void RenderLights(std::deque<LightQueueEntry> &lightQueue, const Matrix4 &projectionMatrix, const Matrix4 &viewMatrix) = 0;


      // --- new & improved

      // init & exit
      virtual bool CreateContext(int width, int height, int bpp, bool fullscreen) = 0;
      virtual void Exit() = 0;

      virtual int CreateView(float x_percent, float y_percent, float width_percent, float height_percent) = 0;
      virtual View &GetView(int viewID) = 0;
      virtual void DeleteView(int viewID) = 0;

      // general
      virtual void SetCullingMode(e_CullingMode cullingMode) = 0;
      virtual void SetBlendingMode(e_BlendingMode blendingMode) = 0;
      virtual void SetDepthFunction(e_DepthFunction depthFunction) = 0;
      virtual void SetDepthTesting(bool OnOff) = 0;
      virtual void SetDepthMask(bool OnOff) = 0;
      virtual void SetBlendingFunction(e_BlendingFunction blendingFunction1, e_BlendingFunction blendingFunction2) = 0;
      virtual void SetTextureMode(e_TextureMode textureMode) = 0;
      virtual void SetColor(const Vector3 &color, float alpha) = 0;
      virtual void SetColorMask(bool r, bool g, bool b, bool alpha) = 0;

      virtual void ClearBuffer(const Vector3 &color, bool clearDepth, bool clearColor) = 0;

      virtual Matrix4 CreatePerspectiveMatrix(float aspectRatio, float nearCap = -1, float farCap = -1) = 0;
      virtual Matrix4 CreateOrthoMatrix(float left, float right, float bottom, float top, float nearCap = -1, float farCap = -1) = 0;

      // vertex buffers
      virtual VertexBufferID CreateVertexBuffer(float *vertices, unsigned int verticesDataSize, const std::vector<unsigned int>& indices, e_VertexBufferUsage usage) = 0;
      virtual void UpdateVertexBuffer(VertexBufferID vertexBufferID, float *vertices, unsigned int verticesDataSize) = 0;
      virtual void DeleteVertexBuffer(VertexBufferID vertexBufferID) = 0;
      virtual void RenderVertexBuffer(const std::deque<VertexBufferQueueEntry> &vertexBufferQueue, e_RenderMode renderMode = e_RenderMode_Full) = 0;

      // lights
      virtual void SetLight(const Vector3 &position, const Vector3 &color, float radius) = 0;

      // textures
      virtual int CreateTexture(e_InternalPixelFormat internalPixelFormat, e_PixelFormat pixelFormat, int width, int height, bool alpha = false, bool repeat = true, bool mipmaps = true, bool filter = true, bool multisample = false, bool compareDepth = false) = 0;
      virtual void ResizeTexture(int textureID, SDL_Surface *source, e_InternalPixelFormat internalPixelFormat, e_PixelFormat pixelFormat, bool alpha = false, bool mipmaps = true) = 0;
      virtual void UpdateTexture(int textureID, SDL_Surface *source, bool alpha = false, bool mipmaps = true) = 0;
      virtual void DeleteTexture(int textureID) = 0;
      virtual void CopyFrameBufferToTexture(int textureID, int width, int height) = 0;
      virtual void BindTexture(int textureID) = 0;
      virtual void SetTextureUnit(int textureUnit) = 0;
      virtual void SetClientTextureUnit(int textureUnit) = 0;

      // frame buffer
      virtual int CreateFrameBuffer() = 0;
      virtual void DeleteFrameBuffer(int fbID) = 0;
      virtual void BindFrameBuffer(int fbID) = 0;
      virtual void SetFrameBufferRenderBuffer(e_TargetAttachment targetAttachment, int rbID) = 0;
      virtual void SetFrameBufferTexture2D(e_TargetAttachment targetAttachment, int texID) = 0;
      virtual bool CheckFrameBufferStatus() = 0;
      virtual void SetFramebufferGammaCorrection(bool onOff) = 0;

      // render targets
      virtual void SetRenderTargets(std::vector<e_TargetAttachment> targetAttachments) = 0;

      // utility
      virtual void SetFOV(float angle) = 0;
      // Fraction of the drawable kept for the timeline. Zero when there is none.
      virtual float BottomBandShare() const { return 0.0f; }
      virtual void PushAttribute(int attr) = 0;
      virtual void PopAttribute() = 0;
      virtual void SetViewport(int x, int y, int width, int height) = 0;
      virtual void GetContextSize(int &width, int &height, int &bpp) = 0;

      // shaders
      virtual void LoadShader(const std::string &name, const std::string &filename) = 0;
      virtual void UseShader(const std::string &name) = 0;
      virtual void SetUniformInt(const std::string &shaderName, const std::string &varName, int value) = 0;
      virtual void SetUniformFloat(const std::string &shaderName, const std::string &varName, float value) = 0;
      virtual void SetUniformFloat2(const std::string &shaderName, const std::string &varName, float value1, float value2) = 0;
      virtual void SetUniformFloat3(const std::string &shaderName, const std::string &varName, float value1, float value2, float value3) = 0;
      virtual void SetUniformFloat3Array(const std::string &shaderName, const std::string &varName, int count, float *values) = 0;
      virtual void SetUniformMatrix4(const std::string &shaderName, const std::string &varName, const Matrix4 &mat) = 0;

    protected:
      std::map<std::string, Shader> shaders;
      std::map<std::string, Shader>::iterator currentShader;
      std::vector<View> views;

  };

  class MockRenderer3D: public Renderer3D {
   public:
    MockRenderer3D() { DO_VALIDATION;
      view_.x = 0;
      view_.y = 0;
      view_.width = 10;
      view_.height = 10;
    }
    virtual void SetContext() {}
    virtual void DisableContext() {}
    virtual const screenshoot& GetScreen() { DO_VALIDATION; return screen_; }
    virtual ~MockRenderer3D() { DO_VALIDATION;};

    virtual void SwapBuffers() { DO_VALIDATION;};

    virtual void SetMatrix(const std::string &shaderUniformName, const Matrix4 &matrix) { DO_VALIDATION;}

    virtual void RenderOverlay2D(const std::vector<Overlay2DQueueEntry> &overlay2DQueue) { DO_VALIDATION;}
    virtual void RenderOverlay2D() { DO_VALIDATION;}
    virtual void RenderLights(std::deque<LightQueueEntry> &lightQueue, const Matrix4 &projectionMatrix, const Matrix4 &viewMatrix) { DO_VALIDATION;}


      // --- new & improved

      // init & exit
    virtual bool CreateContext(int width, int height, int bpp, bool fullscreen) { DO_VALIDATION; return true;};
    virtual void Exit() { DO_VALIDATION;};

    virtual int CreateView(float x_percent, float y_percent, float width_percent, float height_percent) { DO_VALIDATION;
      return 1;
    }
    virtual View &GetView(int viewID) { DO_VALIDATION; return view_; }
    virtual void DeleteView(int viewID) { DO_VALIDATION;}

      // general
      virtual void SetCullingMode(e_CullingMode cullingMode) { DO_VALIDATION;}
      virtual void SetBlendingMode(e_BlendingMode blendingMode) { DO_VALIDATION;}
      virtual void SetDepthFunction(e_DepthFunction depthFunction) { DO_VALIDATION;}
      virtual void SetDepthTesting(bool OnOff) { DO_VALIDATION;}
      virtual void SetDepthMask(bool OnOff) { DO_VALIDATION;}
      virtual void SetBlendingFunction(e_BlendingFunction blendingFunction1, e_BlendingFunction blendingFunction2) { DO_VALIDATION;}
      virtual void SetTextureMode(e_TextureMode textureMode) { DO_VALIDATION;}
      virtual void SetColor(const Vector3 &color, float alpha) { DO_VALIDATION;}
      virtual void SetColorMask(bool r, bool g, bool b, bool alpha) { DO_VALIDATION;}

      virtual void ClearBuffer(const Vector3 &color, bool clearDepth, bool clearColor) { DO_VALIDATION;}

      virtual Matrix4 CreatePerspectiveMatrix(float aspectRatio, float nearCap = -1, float farCap = -1) { DO_VALIDATION;
        return Matrix4(); }

      virtual Matrix4 CreateOrthoMatrix(float left, float right, float bottom, float top, float nearCap = -1, float farCap = -1) { DO_VALIDATION; return Matrix4(); }

      // vertex buffers
      virtual VertexBufferID CreateVertexBuffer(float *vertices, unsigned int verticesDataSize, const std::vector<unsigned int>& indices, e_VertexBufferUsage usage) { DO_VALIDATION; return VertexBufferID(); }
      virtual void UpdateVertexBuffer(VertexBufferID vertexBufferID, float *vertices, unsigned int verticesDataSize) { DO_VALIDATION;}
      virtual void DeleteVertexBuffer(VertexBufferID vertexBufferID) { DO_VALIDATION;}
      virtual void RenderVertexBuffer(const std::deque<VertexBufferQueueEntry> &vertexBufferQueue, e_RenderMode renderMode = e_RenderMode_Full) { DO_VALIDATION;}

      // lights
      virtual void SetLight(const Vector3 &position, const Vector3 &color, float radius) { DO_VALIDATION;}

      // textures
      virtual int CreateTexture(e_InternalPixelFormat internalPixelFormat, e_PixelFormat pixelFormat, int width, int height, bool alpha = false, bool repeat = true, bool mipmaps = true, bool filter = true, bool multisample = false, bool compareDepth = false) { DO_VALIDATION; return 1;}
      virtual void ResizeTexture(int textureID, SDL_Surface *source, e_InternalPixelFormat internalPixelFormat, e_PixelFormat pixelFormat, bool alpha = false, bool mipmaps = true) { DO_VALIDATION;}
      virtual void UpdateTexture(int textureID, SDL_Surface *source, bool alpha = false, bool mipmaps = true) { DO_VALIDATION;}
      virtual void DeleteTexture(int textureID) { DO_VALIDATION;}
      virtual void CopyFrameBufferToTexture(int textureID, int width, int height) { DO_VALIDATION;}
      virtual void BindTexture(int textureID) { DO_VALIDATION;}
      virtual void SetTextureUnit(int textureUnit) { DO_VALIDATION;}
      virtual void SetClientTextureUnit(int textureUnit) { DO_VALIDATION;}

      // frame buffer
      virtual int CreateFrameBuffer() { DO_VALIDATION; return 1;}
      virtual void DeleteFrameBuffer(int fbID) { DO_VALIDATION;}
      virtual void BindFrameBuffer(int fbID) { DO_VALIDATION;}
      virtual void SetFrameBufferRenderBuffer(e_TargetAttachment targetAttachment, int rbID) { DO_VALIDATION;}
      virtual void SetFrameBufferTexture2D(e_TargetAttachment targetAttachment, int texID) { DO_VALIDATION;}
      virtual bool CheckFrameBufferStatus() { DO_VALIDATION; return true; }
      virtual void SetFramebufferGammaCorrection(bool onOff) { DO_VALIDATION;}

      // render targets
      virtual void SetRenderTargets(std::vector<e_TargetAttachment> targetAttachments) { DO_VALIDATION;}

      // utility
      virtual void SetFOV(float angle) { DO_VALIDATION;}
      virtual void PushAttribute(int attr) { DO_VALIDATION;}
      virtual void PopAttribute() { DO_VALIDATION;}
      virtual void SetViewport(int x, int y, int width, int height) { DO_VALIDATION;}
      virtual void GetContextSize(int &width, int &height, int &bpp) { DO_VALIDATION;}

      // shaders
      virtual void LoadShader(const std::string &name, const std::string &filename) { DO_VALIDATION;}
      virtual void UseShader(const std::string &name) { DO_VALIDATION;}
      virtual void SetUniformInt(const std::string &shaderName, const std::string &varName, int value) { DO_VALIDATION;}
      virtual void SetUniformFloat(const std::string &shaderName, const std::string &varName, float value) { DO_VALIDATION;}
      virtual void SetUniformFloat2(const std::string &shaderName, const std::string &varName, float value1, float value2) { DO_VALIDATION;}
      virtual void SetUniformFloat3(const std::string &shaderName, const std::string &varName, float value1, float value2, float value3) { DO_VALIDATION;}
      virtual void SetUniformFloat3Array(const std::string &shaderName, const std::string &varName, int count, float *values) { DO_VALIDATION;}
      virtual void SetUniformMatrix4(const std::string &shaderName, const std::string &varName, const Matrix4 &mat) { DO_VALIDATION;}

    protected:
      View view_;
      screenshoot screen_;
  };


}

#endif
