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

#include "graphics_system.hpp"

#include "graphics_scene.hpp"

#include "../../base/log.hpp"
#include "../../base/utils.hpp"

#include "rendering/r3d_messages.hpp"

namespace blunted {

GraphicsSystem::GraphicsSystem() { DO_VALIDATION; }

GraphicsSystem::~GraphicsSystem() { DO_VALIDATION; }

void GraphicsSystem::Initialize(bool render, int width_, int height_) {
  DO_VALIDATION;

  if (render) {
    renderer3DTask = new OpenGLRenderer3D();
  } else {
    renderer3DTask = new MockRenderer3D();
  }
  width = width_;
  height = height_;
  bpp = 32;
  if (!static_cast<Renderer3D *>(renderer3DTask)
           ->CreateContext(width, height, bpp, false)) {
    DO_VALIDATION;
    Log(e_FatalError, "GraphicsSystem", "Initialize",
        "Could not create context");
  }

  task = new GraphicsTask(this);
}

void GraphicsSystem::SetContext() {
  if (renderer3DTask) {
    renderer3DTask->SetContext();
  }
}

void GraphicsSystem::DisableContext() {
  if (renderer3DTask) {
    renderer3DTask->DisableContext();
  }
}

const screenshoot &GraphicsSystem::GetScreen() {
  return renderer3DTask->GetScreen();
}

void GraphicsSystem::RequestVideoKeyframe() {
  if (renderer3DTask) renderer3DTask->RequestVideoKeyframe();
}

std::vector<std::string> GraphicsSystem::TakeVideoPackets() {
  if (!renderer3DTask) return {};
  return renderer3DTask->TakeVideoPackets();
}

void GraphicsSystem::Exit() {
  DO_VALIDATION;
  delete task;
  task = NULL;

  // shutdown renderer thread
  delete renderer3DTask;
  renderer3DTask = NULL;
}

  e_SystemType GraphicsSystem::GetSystemType() const {
    return systemType;
  }

  GraphicsScene *GraphicsSystem::Create2DScene(
      boost::shared_ptr<IScene> scene) {
    DO_VALIDATION;
    GraphicsScene *graphicsScene = new GraphicsScene(this);
    scene->Attach(graphicsScene->GetInterpreter(e_SceneType_Scene2D));
    return graphicsScene;
  }

  GraphicsScene *GraphicsSystem::Create3DScene(
      boost::shared_ptr<IScene> scene) {
    DO_VALIDATION;
    GraphicsScene *graphicsScene = new GraphicsScene(this);
    scene->Attach(graphicsScene->GetInterpreter(e_SceneType_Scene3D));
    return graphicsScene;
  }

  GraphicsTask *GraphicsSystem::GetTask() {
    DO_VALIDATION;
    return task;
  }

  Renderer3D *GraphicsSystem::GetRenderer3D() {
    DO_VALIDATION;
    return renderer3DTask;
  }

  WindowControl GraphicsSystem::PollWindow(bool free_look) {
    DO_VALIDATION;
    if (!renderer3DTask) {
      WindowControl empty;
      return empty;
    }
    return renderer3DTask->PollWindow(free_look);
  }

  void GraphicsSystem::SetFullscreen(bool on) {
    DO_VALIDATION;
    if (renderer3DTask) renderer3DTask->SetFullscreen(on);
  }

  void GraphicsSystem::ShowWindow() {
    DO_VALIDATION;
    if (renderer3DTask) renderer3DTask->ShowWindow();
  }

  void GraphicsSystem::PlacePlaybackWindow() {
    DO_VALIDATION;
    if (renderer3DTask) renderer3DTask->PlacePlaybackWindow();
  }

  void GraphicsSystem::RestorePlaybackWindow() {
    DO_VALIDATION;
    if (renderer3DTask) renderer3DTask->RestorePlaybackWindow();
  }

  void GraphicsSystem::SetBottomBand(int points) {
    DO_VALIDATION;
    if (renderer3DTask) renderer3DTask->SetBottomBand(points);
  }

  bool GraphicsSystem::Fullscreen() const {
    DO_VALIDATION;
    return renderer3DTask && renderer3DTask->Fullscreen();
  }

  bool GraphicsSystem::PresentsWindow() const {
    DO_VALIDATION;
    if (!renderer3DTask) return false;
    return renderer3DTask->PresentsWindow();
  }

  void GraphicsSystem::SetMouseLook(bool on) {
    DO_VALIDATION;
    if (renderer3DTask) renderer3DTask->SetMouseLook(on);
  }

  MessageQueue<Overlay2DQueueEntry> &GraphicsSystem::GetOverlay2DQueue() {
    DO_VALIDATION;
    return overlay2DQueue;
  }
}
