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

#include "actionfeed.hpp"

#include <cmath>
#include <cstdio>
#include <string>

#include <SDL2/SDL.h>

#include "../../game_env.hpp"
#include "../../gamedefines.hpp"
#include "../../onthepitch/match.hpp"
#include "../../onthepitch/player/humanoid/humanoid.hpp"
#include "../../onthepitch/player/player.hpp"
#include "../../onthepitch/team.hpp"
#include "../../systems/graphics/rendering/interface_renderer3d.hpp"
#include "../../utils.hpp"

using namespace blunted;

namespace {

const char *TouchName(e_FunctionType type) {
  switch (type) {
    case e_FunctionType_BallControl: return "CONTROL";
    case e_FunctionType_Trap: return "TRAP";
    case e_FunctionType_ShortPass: return "SHORT PASS";
    case e_FunctionType_LongPass: return "LONG PASS";
    case e_FunctionType_HighPass: return "HIGH PASS";
    case e_FunctionType_Header: return "HEADER";
    case e_FunctionType_Shot: return "SHOT";
    case e_FunctionType_Deflect: return "DEFLECT";
    case e_FunctionType_Catch: return "CATCH";
    default: return nullptr;
  }
}

// Spoken form of the same touch, drawn above the player. Ball control is
// the dribble. A short pass is just a pass.
const char *LabelName(e_FunctionType type) {
  switch (type) {
    case e_FunctionType_BallControl: return "dribble";
    case e_FunctionType_Trap: return "trap";
    case e_FunctionType_ShortPass: return "pass";
    case e_FunctionType_LongPass: return "long pass";
    case e_FunctionType_HighPass: return "high pass";
    case e_FunctionType_Header: return "header";
    case e_FunctionType_Shot: return "shot";
    case e_FunctionType_Deflect: return "deflect";
    case e_FunctionType_Catch: return "catch";
    default: return nullptr;
  }
}

bool IsTouch(e_FunctionType type) { return TouchName(type) != nullptr; }

float SmoothStep(float t) {
  if (t < 0.0f) t = 0.0f;
  if (t > 1.0f) t = 1.0f;
  return t * t * (3.0f - 2.0f * t);
}

// Rise into place, hold, then keep rising while fading out.
const unsigned long kLabelInMs = 200;
const unsigned long kLabelHoldMs = 900;
const unsigned long kLabelOutMs = 320;
const unsigned long kLabelLifeMs = kLabelInMs + kLabelHoldMs + kLabelOutMs;

void LabelMotion(unsigned long age, float &alpha, float &drop) {
  const float rise_in = 12.0f;
  const float rise_out = 18.0f;
  if (age < kLabelInMs) {
    float t = SmoothStep((float)age / (float)kLabelInMs);
    alpha = t;
    drop = (1.0f - t) * rise_in;
    return;
  }
  unsigned long held = age - kLabelInMs;
  if (held < kLabelHoldMs) {
    alpha = 1.0f;
    drop = 0.0f;
    return;
  }
  float t = SmoothStep((float)(held - kLabelHoldMs) / (float)kLabelOutMs);
  alpha = 1.0f - t;
  drop = -t * rise_out;
}

}  // namespace

Gui2ActionFeed::Gui2ActionFeed(Gui2WindowManager *windowManager, Match *match)
    : Gui2View(windowManager, "action_feed", 0, 0, 100, 100), match(match) {
  DO_VALIDATION;
  team_name_[0] = match->GetTeam(0)->GetTeamData()->GetShortName();
  team_name_[1] = match->GetTeam(1)->GetTeamData()->GetShortName();
  clock_ = Clock();
}

Gui2ActionFeed::~Gui2ActionFeed() { DO_VALIDATION; }

void Gui2ActionFeed::Exit() {
  for (unsigned int i = 0; i < chips_.size(); i++) {
    if (chips_[i].image) windowManager->RemoveImage(chips_[i].image);
    chips_[i].image.reset();
  }
  chips_.clear();
  for (unsigned int i = 0; i < moment_chips_.size(); i++) {
    if (moment_chips_[i].image) windowManager->RemoveImage(moment_chips_[i].image);
    moment_chips_[i].image.reset();
  }
  moment_chips_.clear();
  if (scorer_arrow_) {
    windowManager->RemoveImage(scorer_arrow_);
    scorer_arrow_.reset();
  }
  Gui2View::Exit();
}

namespace {

TTF_Font *MomentFont() {
  static TTF_Font *font = nullptr;
  static bool tried = false;
  if (!tried) {
    tried = true;
    font = TTF_OpenFont("viewer/fonts/Montserrat-ExtraBold.ttf", 22);
    if (!font && GetContext().defaultFont) font = GetContext().defaultFont;
  }
  return font;
}

TTF_Font *LabelFont(bool *owned) {
  static TTF_Font *font = nullptr;
  static bool tried = false;
  static bool we_own = false;
  if (!tried) {
    tried = true;
    // Geist Medium is the overlay face. The system faces are a fallback.
    const char *paths[] = {
        "viewer/fonts/Geist-Medium.ttf",
        "/Library/Fonts/SF-Pro-Text-Medium.otf",
        "/System/Library/Fonts/SFNS.ttf",
    };
    for (unsigned int i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
      font = TTF_OpenFont(paths[i], 15);
      if (font) {
        we_own = true;
        break;
      }
    }
    if (!font && GetContext().defaultFont) font = GetContext().defaultFont;
  }
  if (owned) *owned = we_own;
  return font;
}

// The same view and projection the picture uses, then pixels in that picture.
// The menu page's coordinate space is letterboxed, so a percent in that space
// does not land on the player.
bool ProjectToPicture(const Vector3 &world,
                      boost::intrusive_ptr<Camera> camera, float &x_px,
                      float &y_px) {
  if (!camera) return false;
  Matrix4 view;
  view.ConstructInverse(camera->GetDerivedPosition(), Vector3(1, 1, 1),
                        camera->GetDerivedRotation());
  float near_cap = 0.2f;
  float far_cap = 200.0f;
  camera->GetCapping(near_cap, far_cap);
  if (near_cap < 0.05f) near_cap = 0.05f;
  if (far_cap <= near_cap) far_cap = near_cap + 1.0f;
  float fov = camera->GetFOV();
  Vector3 context = GetGraphicsSystem()->GetContextSize();
  float aspect = context.coords[1] > 0.0f
                     ? context.coords[0] / context.coords[1]
                     : 1.0f;
  const float base_aspect = 1280.0f / 720.0f;
  if (aspect > 0.05f && aspect < base_aspect) {
    float half = fov * (pi / 360.0f);
    fov = std::atan(std::tan(half) * (base_aspect / aspect)) * (360.0f / pi);
  }
  Matrix4 projection;
  projection.ConstructProjection(fov, aspect, near_cap, far_cap);
  Matrix4 clip = projection * view;
  float cx, cy, cz, cw;
  clip.MultiplyVec4(world.coords[0], world.coords[1], world.coords[2], 1.0f,
                    cx, cy, cz, cw);
  if (cw <= 0.05f) return false;
  float ndc_x = cx / cw;
  float ndc_y = cy / cw;
  if (ndc_x < -1.15f || ndc_x > 1.15f || ndc_y < -1.15f || ndc_y > 1.15f) {
    return false;
  }
  x_px = (ndc_x * 0.5f + 0.5f) * context.coords[0];
  y_px = (1.0f - (ndc_y * 0.5f + 0.5f)) * context.coords[1];
  return true;
}

void FillRounded(SDL_Surface *surface, int radius, Uint8 r, Uint8 g, Uint8 b,
                 Uint8 a) {
  if (!surface || surface->format->BytesPerPixel != 4) return;
  if (SDL_MUSTLOCK(surface)) SDL_LockSurface(surface);
  const int w = surface->w;
  const int h = surface->h;
  if (radius < 0) radius = 0;
  if (radius * 2 > w) radius = w / 2;
  if (radius * 2 > h) radius = h / 2;
  const int r2 = radius * radius;
  for (int y = 0; y < h; y++) {
    Uint32 *row = (Uint32 *)((Uint8 *)surface->pixels + y * surface->pitch);
    for (int x = 0; x < w; x++) {
      int dx = 0;
      int dy = 0;
      if (x < radius && y < radius) {
        dx = radius - x;
        dy = radius - y;
      } else if (x >= w - radius && y < radius) {
        dx = x - (w - radius - 1);
        dy = radius - y;
      } else if (x < radius && y >= h - radius) {
        dx = radius - x;
        dy = y - (h - radius - 1);
      } else if (x >= w - radius && y >= h - radius) {
        dx = x - (w - radius - 1);
        dy = y - (h - radius - 1);
      }
      if (dx * dx + dy * dy > r2) {
        row[x] = SDL_MapRGBA(surface->format, 0, 0, 0, 0);
      } else {
        row[x] = SDL_MapRGBA(surface->format, r, g, b, a);
      }
    }
  }
  if (SDL_MUSTLOCK(surface)) SDL_UnlockSurface(surface);
}

}  // namespace

const std::string &Gui2ActionFeed::TeamName(int team) const {
  if (team != 0 && team != 1) return blank_.action;
  return team_name_[team];
}

int Gui2ActionFeed::LineCount(int team) const {
  if (team != 0 && team != 1) return 0;
  return (int)lines_[team].size();
}

const Gui2ActionFeed::TouchLine &Gui2ActionFeed::Line(int team, int index) const {
  if (team != 0 && team != 1) return blank_;
  if (index < 0 || index >= (int)lines_[team].size()) return blank_;
  return lines_[team][index];
}

const Gui2ActionFeed::TouchLine &Gui2ActionFeed::HistoryAt(int index) const {
  if (index < 0 || index >= (int)history_.size()) return blank_;
  return history_[index];
}

void Gui2ActionFeed::ClearTouches() {
  lines_[0].clear();
  lines_[1].clear();
  history_.clear();
  seen_.clear();
  labels_.clear();
  callouts_.clear();
}

void Gui2ActionFeed::NoteGoal(Player *player, bool ownGoal) {
  if (player == nullptr || player->GetPlayerData() == nullptr ||
      player->GetTeam() == nullptr) return;
  int team = player->GetTeam()->GetID();
  TouchLine line;
  line.team = team;
  line.shirt = player->GetShirtNumber();
  line.name = player->GetPlayerData()->GetLastName();
  line.action = ownGoal ? "OWN GOAL" : "GOAL";
  line.clock = Clock();
  Vector3 pos = player->GetPosition();
  if (team == 1) pos.Mirror();
  line.x = pos.coords[0];
  line.y = pos.coords[1];
  line.speed = player->GetMovement().GetLength();
  Vector3 ball = match->GetBall()->GetAveragePosition(5);
  line.ball_x = ball.coords[0];
  line.ball_y = ball.coords[1];
  line.ball_speed = match->GetBall()->GetMovement().GetLength();
  history_.push_back(line);
}

const Gui2ActionFeed::Callout &Gui2ActionFeed::CalloutAt(int index) const {
  if (index < 0 || index >= (int)callouts_.size()) return blank_callout_;
  return callouts_[index];
}

void Gui2ActionFeed::RecordTouches() {
  NoteTouches(0);
  NoteTouches(1);
}

void Gui2ActionFeed::Update() {
  DO_VALIDATION;
  RecordTouches();
  PlaceLabels();
  speed_ = match->GetBall()->GetMovement().GetLength();
  clock_ = Clock();
}

bool Gui2ActionFeed::NoteTouches(int team) {
  bool changed = false;
  std::vector<Player *> players;
  match->GetTeam(team)->GetActivePlayers(players);
  for (unsigned int i = 0; i < players.size(); i++) {
    Player *player = players[i];
    Humanoid *humanoid = player->CastHumanoid();
    if (humanoid == nullptr) continue;
    const Anim *anim = humanoid->GetCurrentAnim();
    if (anim == nullptr || anim->anim == nullptr) continue;
    Seen &seen = seen_[player];
    if (seen.animId == anim->id) continue;
    e_FunctionType type = anim->functionType;
    bool continuing_control = type == e_FunctionType_BallControl &&
                              seen.type == e_FunctionType_BallControl;
    if (IsTouch(type) && !continuing_control) {
      TouchLine line;
      line.team = team;
      line.shirt = player->GetShirtNumber();
      line.name = player->GetPlayerData()->GetLastName();
      line.action = TouchName(type);
      line.clock = Clock();
      Vector3 pos = player->GetPosition();
      if (team == 1) pos.Mirror();
      line.x = pos.coords[0];
      line.y = pos.coords[1];
      line.speed = player->GetMovement().GetLength();
      Vector3 ball = match->GetBall()->GetAveragePosition(5);
      line.ball_x = ball.coords[0];
      line.ball_y = ball.coords[1];
      line.ball_speed = match->GetBall()->GetMovement().GetLength();
      Push(team, line);
      history_.push_back(line);
      const char *label = LabelName(type);
      if (label) NoteLabel(player, label);
      changed = true;
    }
    seen.animId = anim->id;
    seen.type = type;
  }
  return changed;
}

void Gui2ActionFeed::NoteLabel(Player *player, const std::string &text) {
  GameEnv *env = GetGame();
  if (!env || !env->action_labels || player == nullptr) return;
  for (unsigned int i = 0; i < labels_.size(); i++) {
    if (labels_[i].player == player) {
      labels_.erase(labels_.begin() + i);
      break;
    }
  }
  LiveCallout label;
  label.player = player;
  label.text = text;
  label.started_ms = match->GetActualTime_ms();
  labels_.push_back(label);
}

void Gui2ActionFeed::SyncOverlay() {
  PlaceLabels();
  PlaceMomentMarks();
}

void Gui2ActionFeed::PlaceLabels() {
  callouts_.clear();
  chips_used_ = 0;
  GameEnv *env = GetGame();
  if (!env || !env->action_labels) {
    labels_.clear();
    HideSpareChips();
    return;
  }
  unsigned long now = match->GetActualTime_ms();
  std::vector<LiveCallout> kept;
  for (unsigned int i = 0; i < labels_.size(); i++) {
    LiveCallout &label = labels_[i];
    if (label.player == nullptr || !label.player->IsActive()) continue;
    unsigned long age = now - label.started_ms;
    if (age > kLabelLifeMs) continue;
    kept.push_back(label);
    float alpha = 1.0f;
    float drop = 0.0f;
    LabelMotion(age, alpha, drop);
    // The drawn body stays on the mirrored mesh. The skeleton root is put
    // back afterwards, so the mesh node is the point in this picture.
    // Just above the hair on this camera. The box sits on that point.
    // The word still trails the run by a hair, so it leads by a tenth of a
    // second of this player's movement.
    Vector3 pos = label.player->GetFullbodyNode()->GetPosition();
    bool reverse = GetScenarioConfig().reverse_team_processing;
    int first = match->FirstTeam();
    bool mirror = (label.player->GetTeamID() == first) ? reverse : !reverse;
    Vector3 lead = label.player->GetMovement();
    lead.coords[2] = 0.0f;
    if (mirror) {
      lead.coords[0] = -lead.coords[0];
      lead.coords[1] = -lead.coords[1];
    }
    lead *= 0.1f;
    if (lead.GetLength() > 1.2f) lead = lead.GetNormalized(Vector3(0)) * 1.2f;
    pos += lead;
    pos.coords[2] += 1.82f;
    float x_px = 0.0f;
    float y_px = 0.0f;
    if (!ProjectToPicture(pos, match->GetCamera(), x_px, y_px)) continue;
    Callout callout;
    callout.text = label.text;
    Vector3 context = GetGraphicsSystem()->GetContextSize();
    callout.x = context.coords[0] > 0.0f ? x_px / context.coords[0] : 0.0f;
    callout.y = context.coords[1] > 0.0f ? y_px / context.coords[1] : 0.0f;
    callout.on_screen = true;
    callouts_.push_back(callout);
    // Drawn in this frame, so the box is on the player in the picture.
    // drop is down the picture. A negative drop is the rise.
    ShowChip(label.text, x_px, y_px + drop, alpha);
  }
  labels_.swap(kept);
  HideSpareChips();
}

void Gui2ActionFeed::PaintChip(Chip &chip, const std::string &text) {
  TTF_Font *font = LabelFont(nullptr);
  if (!font || !chip.image) return;
  // Overlay ink, #F4F4F2.
  SDL_Color white = {244, 244, 242, 255};
  SDL_Surface *glyphs = TTF_RenderUTF8_Blended(font, text.c_str(), white);
  if (!glyphs) return;
  const int pad_x = 8;
  const int pad_y = 4;
  int width = glyphs->w + pad_x * 2;
  int height = glyphs->h + pad_y * 2;
  if (width < 1) width = 1;
  if (height < 1) height = 1;
  chip.image->Resize(width, height);
  SDL_Surface *surface = chip.image->GetImage()->GetResource()->GetData();
  // The overlay chip: 4px corners, black at 0.62, no edge.
  FillRounded(surface, 4, 0, 0, 0, 158);
  SDL_Rect dest;
  dest.x = pad_x;
  dest.y = pad_y;
  dest.w = glyphs->w;
  dest.h = glyphs->h;
  SDL_SetSurfaceBlendMode(glyphs, SDL_BLENDMODE_BLEND);
  SDL_BlitSurface(glyphs, NULL, surface, &dest);
  SDL_FreeSurface(glyphs);
  chip.image->OnChange();
  chip.text = text;
}

void Gui2ActionFeed::ShowChip(const std::string &text, float x_px, float y_px,
                              float alpha) {
  if ((int)chips_.size() == chips_used_) {
    Chip chip;
    char name[32];
    std::snprintf(name, sizeof(name), "action_label_%d", chips_used_);
    chip.image = windowManager->CreateImage2D(name, 8, 8, true);
    chips_.push_back(chip);
  }
  Chip &chip = chips_[chips_used_];
  chips_used_ += 1;
  if (chip.text != text) PaintChip(chip, text);
  int width = (int)chip.image->GetSize().coords[0];
  int height = (int)chip.image->GetSize().coords[1];
  chip.image->SetPosition((int)std::lround(x_px) - width / 2,
                          (int)std::lround(y_px) - height);
  chip.image->SetAlpha(alpha);
  chip.image->Enable();
}

void Gui2ActionFeed::HideSpareChips() {
  for (int i = chips_used_; i < (int)chips_.size(); i++) {
    if (chips_[i].image) chips_[i].image->Disable();
  }
  chips_used_ = 0;
}

void Gui2ActionFeed::PaintMomentChip(Chip &chip, const std::string &text) {
  TTF_Font *font = MomentFont();
  if (!font || !chip.image) return;
  // League green on league purple, with a magenta cap. Sharp corners.
  SDL_Color ink = {0x00, 0xFF, 0x85, 255};
  SDL_Surface *glyphs = TTF_RenderUTF8_Blended(font, text.c_str(), ink);
  if (!glyphs) return;
  const int cap = 6;
  const int pad_x = 14;
  const int pad_y = 8;
  int width = glyphs->w + pad_x * 2 + cap;
  int height = glyphs->h + pad_y * 2;
  if (width < 1) width = 1;
  if (height < 1) height = 1;
  chip.image->Resize(width, height);
  SDL_Surface *surface = chip.image->GetImage()->GetResource()->GetData();
  if (!surface || surface->format->BytesPerPixel != 4) {
    SDL_FreeSurface(glyphs);
    return;
  }
  if (SDL_MUSTLOCK(surface)) SDL_LockSurface(surface);
  Uint32 magenta = SDL_MapRGBA(surface->format, 0xE9, 0x00, 0x52, 255);
  Uint32 purple = SDL_MapRGBA(surface->format, 0x38, 0x00, 0x3C, 255);
  for (int y = 0; y < surface->h; y++) {
    Uint32 *row = (Uint32 *)((Uint8 *)surface->pixels + y * surface->pitch);
    for (int x = 0; x < surface->w; x++) {
      row[x] = x < cap ? magenta : purple;
    }
  }
  if (SDL_MUSTLOCK(surface)) SDL_UnlockSurface(surface);
  SDL_Rect dest;
  dest.x = cap + pad_x;
  dest.y = pad_y;
  dest.w = glyphs->w;
  dest.h = glyphs->h;
  SDL_SetSurfaceBlendMode(glyphs, SDL_BLENDMODE_BLEND);
  SDL_BlitSurface(glyphs, NULL, surface, &dest);
  SDL_FreeSurface(glyphs);
  chip.image->OnChange();
  chip.text = text;
}

void Gui2ActionFeed::ShowMomentChip(const std::string &text, float x_px,
                                    float y_px) {
  if (text.empty()) return;
  if ((int)moment_chips_.size() == moment_used_) {
    Chip chip;
    char name[32];
    std::snprintf(name, sizeof(name), "moment_mark_%d", moment_used_);
    chip.image = windowManager->CreateImage2D(name, 8, 8, true);
    moment_chips_.push_back(chip);
  }
  Chip &chip = moment_chips_[moment_used_];
  moment_used_ += 1;
  if (chip.text != text) PaintMomentChip(chip, text);
  int width = (int)chip.image->GetSize().coords[0];
  int height = (int)chip.image->GetSize().coords[1];
  chip.image->SetPosition((int)std::lround(x_px) - width / 2,
                          (int)std::lround(y_px) - height);
  chip.image->SetAlpha(1.0f);
  chip.image->Enable();
}

void Gui2ActionFeed::PaintScorerArrow() {
  // League green, no outline. The point is the bottom of the image.
  const int w = 64;
  const int h = 50;
  scorer_arrow_->Resize(w, h);
  if (!scorer_arrow_->GetImage() || !scorer_arrow_->GetImage()->GetResource()) {
    return;
  }
  SDL_Surface *surface = scorer_arrow_->GetImage()->GetResource()->GetData();
  if (!surface || surface->format->BytesPerPixel != 4) return;
  if (SDL_MUSTLOCK(surface)) SDL_LockSurface(surface);
  Uint32 clear = SDL_MapRGBA(surface->format, 0, 0, 0, 0);
  Uint32 green = SDL_MapRGBA(surface->format, 0x00, 0xFF, 0x85, 255);
  auto inside = [&](int x, int y) -> bool {
    if (y < 1 || y > h - 2) return false;
    float t = (float)(y - 1) / (float)(h - 3);
    if (t < 0.0f || t > 1.0f) return false;
    float half = (w * 0.5f - 2.0f) * (1.0f - t);
    return std::fabs((float)x + 0.5f - w * 0.5f) <= half + 0.01f;
  };
  for (int y = 0; y < surface->h; y++) {
    Uint32 *row = (Uint32 *)((Uint8 *)surface->pixels + y * surface->pitch);
    for (int x = 0; x < surface->w; x++) {
      row[x] = inside(x, y) ? green : clear;
    }
  }
  if (SDL_MUSTLOCK(surface)) SDL_UnlockSurface(surface);
  scorer_arrow_->OnChange();
}

void Gui2ActionFeed::ShowScorerArrow(float x_px, float y_px) {
  if (!scorer_arrow_) {
    scorer_arrow_ = windowManager->CreateImage2D("scorer_arrow", 8, 8, true);
    if (!scorer_arrow_) return;
    PaintScorerArrow();
  }
  int width = (int)scorer_arrow_->GetSize().coords[0];
  int height = (int)scorer_arrow_->GetSize().coords[1];
  // A slow bob so the mark stays easy to find. The tip stays just over the head.
  float bob = std::sin(match->GetActualTime_ms() * 0.014f) * 14.0f;
  scorer_arrow_->SetPosition((int)std::lround(x_px) - width / 2,
                             (int)std::lround(y_px - height - 8.0f + bob));
  scorer_arrow_->SetAlpha(1.0f);
  scorer_arrow_->Enable();
}

void Gui2ActionFeed::HideScorerArrow() {
  if (scorer_arrow_) scorer_arrow_->Disable();
}

void Gui2ActionFeed::HideMomentChips() {
  for (int i = moment_used_; i < (int)moment_chips_.size(); i++) {
    if (moment_chips_[i].image) moment_chips_[i].image->Disable();
  }
}

void Gui2ActionFeed::PlaceMomentMarks() {
  moment_used_ = 0;
  GameEnv *env = GetGame();
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  std::vector<float> xyz;
  std::vector<int> counts;
  std::vector<int> colors;
  const int segments = 48;
  bool arrow_shown = false;
  if (env) {
    bool reverse = GetScenarioConfig().reverse_team_processing;
    int first = match->FirstTeam();
    for (unsigned int n = 0; n < env->moment_marks.size(); n++) {
      const MomentMark &mark = env->moment_marks[n];
      if (mark.team != 0 && mark.team != 1) continue;
      const std::vector<Player *> &players =
          match->GetTeam(mark.team)->GetAllPlayers();
      if (mark.index < 0 || mark.index >= (int)players.size()) continue;
      Player *player = players[mark.index];
      if (!player || !player->IsActive()) continue;
      Vector3 pos = player->GetPosition();
      bool mirror = (mark.team == first) ? reverse : !reverse;
      if (mirror) {
        pos.coords[0] = -pos.coords[0];
        pos.coords[1] = -pos.coords[1];
      }
      if (mark.shape == 1) {
        Vector3 tip = pos;
        tip.coords[2] += 1.9f;
        float x_px = 0.0f;
        float y_px = 0.0f;
        if (ProjectToPicture(tip, match->GetCamera(), x_px, y_px)) {
          ShowScorerArrow(x_px, y_px);
          arrow_shown = true;
        }
        continue;
      }
      // The circle under the player. The picture strokes this line.
      for (int ring = 0; ring < 2; ring++) {
        float radius = ring == 0 ? 1.55f : 1.12f;
        for (int step = 0; step < segments; step++) {
          float angle = (float)step / (float)segments * 2.0f * 3.14159265f;
          xyz.push_back(pos.coords[0] + std::cos(angle) * radius);
          xyz.push_back(pos.coords[1] + std::sin(angle) * radius);
          xyz.push_back(0.07f);
        }
        counts.push_back(segments);
        colors.push_back(ring);
      }
      Vector3 label = pos;
      label.coords[2] += 2.05f;
      float x_px = 0.0f;
      float y_px = 0.0f;
      if (ProjectToPicture(label, match->GetCamera(), x_px, y_px)) {
        ShowMomentChip(mark.text, x_px, y_px);
      }
    }
  }
  if (renderer) {
    renderer->SetMomentRings(
        xyz.empty() ? nullptr : &xyz[0],
        counts.empty() ? nullptr : &counts[0],
        colors.empty() ? nullptr : &colors[0], (int)counts.size());
  }
  HideMomentChips();
  if (!arrow_shown) HideScorerArrow();
}

void Gui2ActionFeed::Push(int team, const TouchLine &line) {
  lines_[team].insert(lines_[team].begin(), line);
  if ((int)lines_[team].size() > kRows) {
    lines_[team].resize(kRows);
  }
}

std::string Gui2ActionFeed::Clock() const {
  unsigned long ms = match->GetMatchTime_ms();
  int seconds = (int)(ms / 1000) % 60;
  int minutes = (int)(ms / 60000);
  char clock[16];
  std::snprintf(clock, sizeof(clock), "%02d:%02d", minutes, seconds);
  return clock;
}
