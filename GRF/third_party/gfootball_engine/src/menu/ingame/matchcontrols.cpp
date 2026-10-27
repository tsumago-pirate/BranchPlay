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

#include "matchcontrols.hpp"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

#include "../../gamedefines.hpp"
#include "../../game_env.hpp"
#include "../../main.hpp"
#include "../../onthepitch/match.hpp"
#include "../../onthepitch/player/playerofficial.hpp"
#include "../../systems/graphics/rendering/interface_renderer3d.hpp"
#include "../../utils/gui2/widgets/caption.hpp"
#include "../../utils/gui2/widgets/image.hpp"

using namespace blunted;

namespace {

const char *RoleName(e_PlayerRole role) {
  switch (role) {
    case e_PlayerRole_GK: return "GK";
    case e_PlayerRole_CB: return "CB";
    case e_PlayerRole_LB: return "LB";
    case e_PlayerRole_RB: return "RB";
    case e_PlayerRole_DM: return "DM";
    case e_PlayerRole_CM: return "CM";
    case e_PlayerRole_LM: return "LM";
    case e_PlayerRole_RM: return "RM";
    case e_PlayerRole_AM: return "AM";
    case e_PlayerRole_CF: return "CF";
    default: return "";
  }
}

float Clamp(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

bool TeamMirrored(Match *match, int team) {
  bool reverse = GetScenarioConfig().reverse_team_processing;
  return (team == match->FirstTeam()) ? reverse : !reverse;
}

void PlayerBounds(PlayerBase *player, bool mirrored, Vector3 &bmin, Vector3 &bmax) {
  Vector3 pos = player->GetPosition();
  if (mirrored) {
    pos.coords[0] = -pos.coords[0];
    pos.coords[1] = -pos.coords[1];
  }
  float height = player->GetPlayerData()->GetHeight();
  if (height < 0.5f) height = 1.8f;
  const float half = 0.48f;
  bmin = Vector3(pos.coords[0] - half, pos.coords[1] - half, pos.coords[2]);
  bmax = Vector3(pos.coords[0] + half, pos.coords[1] + half,
                 pos.coords[2] + height);
}

bool RayHitsBox(const Vector3 &start, const Vector3 &end, const Vector3 &bmin,
                const Vector3 &bmax, float &t_hit) {
  Vector3 dir(end.coords[0] - start.coords[0], end.coords[1] - start.coords[1],
              end.coords[2] - start.coords[2]);
  float tmin = 0.0f;
  float tmax = 1.0f;
  for (int axis = 0; axis < 3; axis++) {
    float origin = start.coords[axis];
    float delta = dir.coords[axis];
    float lo = bmin.coords[axis];
    float hi = bmax.coords[axis];
    if (std::fabs(delta) < 1e-8f) {
      if (origin < lo || origin > hi) return false;
      continue;
    }
    float t1 = (lo - origin) / delta;
    float t2 = (hi - origin) / delta;
    if (t1 > t2) {
      float swap = t1;
      t1 = t2;
      t2 = swap;
    }
    if (t1 > tmin) tmin = t1;
    if (t2 < tmax) tmax = t2;
    if (tmin > tmax) return false;
  }
  t_hit = tmin;
  return true;
}

bool PlayerAnchor(Match *match, int team, int index, Vector3 &out) {
  if (team != 0 && team != 1) return false;
  const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
  if (index < 0 || index >= (int)players.size()) return false;
  Player *player = players[index];
  if (!player->IsActive() || match->IsHidden(team, index)) return false;
  Vector3 pos = player->GetPosition();
  if (TeamMirrored(match, team)) {
    pos.coords[0] = -pos.coords[0];
    pos.coords[1] = -pos.coords[1];
  }
  // The player's position is at the feet. A few centimetres keeps the line
  // on the grass instead of in it.
  pos.coords[2] += 0.04f;
  out = pos;
  return true;
}

float ClampPitch(float value, float limit) {
  float edge = limit - 1.0f;
  if (value < -edge) return -edge;
  if (value > edge) return edge;
  return value;
}

Vector3 VisualPosition(PlayerBase *player, bool mirrored) {
  Vector3 pos = player->GetPosition();
  if (mirrored) {
    pos.coords[0] = -pos.coords[0];
    pos.coords[1] = -pos.coords[1];
  }
  return pos;
}

void PlaceVisual(Player *player, bool mirrored, float visual_x, float visual_y) {
  float x = mirrored ? -visual_x : visual_x;
  float y = mirrored ? -visual_y : visual_y;
  player->ResetPosition(Vector3(x, y, 0), Vector3(x + 1.0f, y, 0));
  // The body record moves here. The drawn skeleton does not, until the idle
  // pose is applied. Without that, a group drag walks the boxes off the players.
  player->PreparePutBuffers();
  player->FetchPutBuffers();
}

void PushCorners(std::vector<float> &out, const Vector3 &bmin,
                 const Vector3 &bmax) {
  float x0 = bmin.coords[0];
  float y0 = bmin.coords[1];
  float z0 = bmin.coords[2];
  float x1 = bmax.coords[0];
  float y1 = bmax.coords[1];
  float z1 = bmax.coords[2];
  const float corners[8][3] = {
      {x0, y0, z0}, {x1, y0, z0}, {x1, y1, z0}, {x0, y1, z0},
      {x0, y0, z1}, {x1, y0, z1}, {x1, y1, z1}, {x0, y1, z1},
  };
  for (int i = 0; i < 8; i++) {
    out.push_back(corners[i][0]);
    out.push_back(corners[i][1]);
    out.push_back(corners[i][2]);
  }
}

}  // namespace

Gui2MatchControls::Gui2MatchControls(Gui2WindowManager *windowManager,
                                     Match *match, bool draw)
    : Gui2View(windowManager, "match_controls", 2, 8.5f, 96, 4.8f),
      match(match),
      text_color_(255),
      outline_color_(0) {
  DO_VALIDATION;
  if (!draw) return;
  Gui2Image *background = new Gui2Image(
      windowManager, "match_controls_bg", 0, 0, 96, 4.8f);
  background->LoadImage("media/menu/scoreboard_bg.png");
  AddView(background);
  background->Show();

  view_caption_ = MakeCaption("match_controls_view", 1, 0.3f, 46, 4.2f,
                              "View  Broadcast");
  lens_caption_ = MakeCaption("match_controls_lens", 48, 0.3f, 16, 4.2f,
                              "Lens");
  freeze_caption_ = MakeCaption("match_controls_freeze", 65, 0.3f, 14, 4.2f,
                                "Freeze");
  hint_caption_ = MakeCaption("match_controls_hint", 80, 0.3f, 15, 4.2f, " ");
  Refresh();
  this->Show();
}

Gui2MatchControls::~Gui2MatchControls() { DO_VALIDATION; }

Gui2Caption *Gui2MatchControls::MakeCaption(const std::string &name, float x,
                                            float y, float w, float h,
                                            const std::string &text) {
  Gui2Caption *caption =
      new Gui2Caption(windowManager, name, x, y, w, h, text);
  caption->SetColor(text_color_);
  caption->SetOutlineColor(outline_color_);
  AddView(caption);
  caption->Show();
  return caption;
}

bool Gui2MatchControls::Inside(float x_percent, float y_percent,
                               float w_percent, float h_percent, int x,
                               int y) const {
  int left = 0;
  int top = 0;
  int width = 0;
  int height = 0;
  windowManager->GetCoordinates(x_percent, y_percent, w_percent, h_percent,
                                left, top, width, height);
  return x >= left && x < left + width && y >= top && y < top + height;
}

bool Gui2MatchControls::HitView(int x, int y) const {
  float left = 0.0f;
  float top = 0.0f;
  float width = 0.0f;
  float height = 0.0f;
  view_caption_->GetDerivedPosition(left, top);
  view_caption_->GetSize(width, height);
  return Inside(left, top, width, height, x, y);
}

bool Gui2MatchControls::HitLens(int x, int y) const {
  float left = 0.0f;
  float top = 0.0f;
  float width = 0.0f;
  float height = 0.0f;
  lens_caption_->GetDerivedPosition(left, top);
  lens_caption_->GetSize(width, height);
  return Inside(left, top, width, height, x, y);
}

bool Gui2MatchControls::HitFreeze(int x, int y) const {
  float left = 0.0f;
  float top = 0.0f;
  float width = 0.0f;
  float height = 0.0f;
  freeze_caption_->GetDerivedPosition(left, top);
  freeze_caption_->GetSize(width, height);
  return Inside(left, top, width, height, x, y);
}

bool Gui2MatchControls::Hit(int x, int y) const {
  if (!view_caption_) return false;
  float left = 0.0f;
  float top = 0.0f;
  float width = 0.0f;
  float height = 0.0f;
  GetDerivedPosition(left, top);
  GetSize(width, height);
  if (Inside(left, top, width, height, x, y)) return true;
  for (unsigned int i = 0; i < choices_.size(); i++) {
    const Choice &choice = choices_[i];
    if (Inside(choice.x, choice.y, choice.w, choice.h, x, y)) return true;
  }
  return false;
}

void Gui2MatchControls::SetHeld(bool held) {
  if (held_ == held) return;
  held_ = held;
  if (view_caption_) Refresh();
}

void Gui2MatchControls::SetBoxes(const int *teams, const int *indices,
                                 int count) {
  boxed_.clear();
  if (!teams || !indices || count <= 0) return;
  for (int i = 0; i < count; i++) {
    int team = teams[i];
    int index = indices[i];
    // Team -1, index 0 is the referee. The referee is not on a team roster.
    if (team == -1) {
      if (index != 0) continue;
    } else if (team != 0 && team != 1) {
      continue;
    } else if (index < 0 || index >= PlayerCount(team)) {
      continue;
    }
    bool seen = false;
    for (unsigned int n = 0; n < boxed_.size(); n++) {
      if (boxed_[n].team == team && boxed_[n].index == index) {
        seen = true;
        break;
      }
    }
    if (seen) continue;
    BoxedPlayer mark;
    mark.team = team;
    mark.index = index;
    boxed_.push_back(mark);
  }
}

void Gui2MatchControls::SetLinks(const int *teams, const int *indices,
                                 int count) {
  links_.clear();
  if (!teams || !indices || count < 2) return;
  int pairs = count / 2;
  for (int i = 0; i < pairs; i++) {
    LinkEnd a;
    LinkEnd b;
    a.team = teams[i * 2];
    a.index = indices[i * 2];
    b.team = teams[i * 2 + 1];
    b.index = indices[i * 2 + 1];
    if ((a.team != 0 && a.team != 1) || (b.team != 0 && b.team != 1)) continue;
    if (a.index < 0 || a.index >= PlayerCount(a.team)) continue;
    if (b.index < 0 || b.index >= PlayerCount(b.team)) continue;
    if (a.team == b.team && a.index == b.index) continue;
    if (a.team > b.team || (a.team == b.team && a.index > b.index)) {
      LinkEnd swap = a;
      a = b;
      b = swap;
    }
    bool seen = false;
    for (unsigned int n = 0; n < links_.size(); n++) {
      if (links_[n].a.team == a.team && links_[n].a.index == a.index &&
          links_[n].b.team == b.team && links_[n].b.index == b.index) {
        seen = true;
        break;
      }
    }
    if (seen) continue;
    LinkLine line;
    line.a = a;
    line.b = b;
    links_.push_back(line);
  }
}

int Gui2MatchControls::PlayerCount(int team) const {
  if (team != 0 && team != 1) return 0;
  return (int)match->GetTeam(team)->GetAllPlayers().size();
}

void Gui2MatchControls::SetEditing(bool on) {
  editing_ = on;
  if (!on) add_prompt_ = false;
  if (on) return;
  drag_active_ = false;
  drag_players_ = false;
  drag_ball_ = false;
  drag_marquee_ = false;
  picked_.clear();
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  if (renderer) renderer->SetEditRect(false, 0, 0, 0, 0);
}

void Gui2MatchControls::SetEditLock(bool on) { edit_lock_ = on; }

bool Gui2MatchControls::GroundAt(int x, int y, float &out_x, float &out_y) const {
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  if (!renderer) return false;
  Vector3 near_point;
  Vector3 far_point;
  if (!renderer->ScreenRay(x, y, near_point, far_point)) return false;
  float dz = far_point.coords[2] - near_point.coords[2];
  if (std::fabs(dz) < 1e-6f) return false;
  float t = (0.0f - near_point.coords[2]) / dz;
  if (t < 0.0f) return false;
  out_x = near_point.coords[0] + (far_point.coords[0] - near_point.coords[0]) * t;
  out_y = near_point.coords[1] + (far_point.coords[1] - near_point.coords[1]) * t;
  if (std::fabs(out_x) > pitchHalfW + 8.0f || std::fabs(out_y) > pitchHalfH + 8.0f) {
    return false;
  }
  return true;
}

bool Gui2MatchControls::PickPlayer(int x, int y, int &team, int &index) const {
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  if (!renderer) return false;
  Vector3 near_point;
  Vector3 far_point;
  if (!renderer->ScreenRay(x, y, near_point, far_point)) return false;
  int best_team = -1;
  int best_index = -1;
  float best_t = 2.0f;
  for (int side = 0; side < 2; side++) {
    bool mirrored = TeamMirrored(match, side);
    const std::vector<Player *> &players = match->GetTeam(side)->GetAllPlayers();
    for (unsigned int i = 0; i < players.size(); i++) {
      Player *player = players[i];
      if (!player->IsActive() || match->IsHidden(side, (int)i)) continue;
      Vector3 bmin;
      Vector3 bmax;
      PlayerBounds(player, mirrored, bmin, bmax);
      float t = 0.0f;
      if (!RayHitsBox(near_point, far_point, bmin, bmax, t)) continue;
      if (t < best_t) {
        best_t = t;
        best_team = side;
        best_index = (int)i;
      }
    }
  }
  if (best_t >= 2.0f) return false;
  team = best_team;
  index = best_index;
  return true;
}

bool Gui2MatchControls::PickBall(int x, int y) const {
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  Ball *ball = match->GetBall();
  if (!renderer || !ball) return false;
  Vector3 near_point;
  Vector3 far_point;
  if (!renderer->ScreenRay(x, y, near_point, far_point)) return false;
  Vector3 pos = ball->GetPosition();
  const float half = 0.8f;
  Vector3 bmin(pos.coords[0] - half, pos.coords[1] - half, 0.0f);
  Vector3 bmax(pos.coords[0] + half, pos.coords[1] + half, pos.coords[2] + 0.8f);
  float t = 0.0f;
  return RayHitsBox(near_point, far_point, bmin, bmax, t);
}

void Gui2MatchControls::RememberPicked() {
  for (unsigned int i = 0; i < picked_.size(); i++) {
    int team = picked_[i].team;
    const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
    int index = picked_[i].index;
    if (index < 0 || index >= (int)players.size()) continue;
    Player *player = players[index];
    if (!player->IsActive()) continue;
    Vector3 pos = VisualPosition(player, TeamMirrored(match, team));
    picked_[i].x = pos.coords[0];
    picked_[i].y = pos.coords[1];
  }
}

void Gui2MatchControls::PlacePicked(float dx, float dy) {
  Player *retainer = match->GetBallRetainer();
  Vector3 before(0);
  bool follow_ball = false;
  if (retainer) before = retainer->GetPosition();
  for (unsigned int i = 0; i < picked_.size(); i++) {
    int team = picked_[i].team;
    const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
    int index = picked_[i].index;
    if (index < 0 || index >= (int)players.size()) continue;
    Player *player = players[index];
    if (!player->IsActive() || match->IsHidden(team, index)) continue;
    if (player == retainer) follow_ball = true;
    float x = ClampPitch(picked_[i].x + dx, pitchHalfW);
    float y = ClampPitch(picked_[i].y + dy, pitchHalfH);
    PlaceVisual(player, TeamMirrored(match, team), x, y);
  }
  if (follow_ball && retainer && match->GetBall()) {
    Vector3 after = retainer->GetPosition();
    Vector3 ball = match->GetBall()->GetPosition();
    ball.coords[0] += after.coords[0] - before.coords[0];
    ball.coords[1] += after.coords[1] - before.coords[1];
    ball.coords[0] = ClampPitch(ball.coords[0], pitchHalfW);
    ball.coords[1] = ClampPitch(ball.coords[1], pitchHalfH);
    if (ball.coords[2] < 0.11f) ball.coords[2] = 0.11f;
    match->GetBall()->SetPosition(ball);
  }
}

void Gui2MatchControls::SelectMarquee() {
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  picked_.clear();
  if (!renderer) return;
  float x0 = std::min(press_x_, pointer_x_);
  float x1 = std::max(press_x_, pointer_x_);
  float y0 = std::min(press_y_, pointer_y_);
  float y1 = std::max(press_y_, pointer_y_);
  for (int team = 0; team < 2; team++) {
    bool mirrored = TeamMirrored(match, team);
    const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
    for (unsigned int i = 0; i < players.size(); i++) {
      Player *player = players[i];
      if (!player->IsActive() || match->IsHidden(team, (int)i)) continue;
      Vector3 pos = VisualPosition(player, mirrored);
      float hx = 0.0f;
      float hy = 0.0f;
      if (!renderer->ProjectToHud(pos.coords[0], pos.coords[1], pos.coords[2], hx, hy)) {
        continue;
      }
      if (hx < x0 || hx > x1 || hy < y0 || hy > y1) continue;
      EditPick pick;
      pick.team = team;
      pick.index = (int)i;
      pick.x = pos.coords[0];
      pick.y = pos.coords[1];
      picked_.push_back(pick);
    }
  }
}

void Gui2MatchControls::EditPointer(const blunted::WindowControl &input) {
  pointer_x_ = (float)input.x;
  pointer_y_ = (float)input.y;
  if (input.pressed) {
    press_x_ = (float)input.press_x;
    press_y_ = (float)input.press_y;
    pointer_x_ = press_x_;
    pointer_y_ = press_y_;
    drag_active_ = true;
    drag_players_ = false;
    drag_ball_ = false;
    drag_marquee_ = false;
    int team = 0;
    int index = 0;
    float ground_x = 0.0f;
    float ground_y = 0.0f;
    bool ground = GroundAt(input.press_x, input.press_y, ground_x, ground_y);
    if (PickPlayer(input.press_x, input.press_y, team, index)) {
      bool in_selection = false;
      for (unsigned int i = 0; i < picked_.size(); i++) {
        if (picked_[i].team == team && picked_[i].index == index) in_selection = true;
      }
      if (!in_selection) {
        picked_.clear();
        EditPick pick;
        pick.team = team;
        pick.index = index;
        picked_.push_back(pick);
      }
      RememberPicked();
      if (!ground && !picked_.empty()) {
        ground_x = picked_[0].x;
        ground_y = picked_[0].y;
        ground = true;
      }
      anchor_x_ = ground_x;
      anchor_y_ = ground_y;
      drag_players_ = true;
    } else if (PickBall(input.press_x, input.press_y) && match->GetBall()) {
      Vector3 pos = match->GetBall()->GetPosition();
      ball_x_ = pos.coords[0];
      ball_y_ = pos.coords[1];
      if (!ground) {
        ground_x = ball_x_;
        ground_y = ball_y_;
      }
      anchor_x_ = ground_x;
      anchor_y_ = ground_y;
      drag_ball_ = true;
    } else {
      anchor_x_ = ground_x;
      anchor_y_ = ground_y;
      drag_marquee_ = true;
    }
  }
  if (drag_active_ && input.dragged && (input.mouse_held || input.released)) {
    float ground_x = 0.0f;
    float ground_y = 0.0f;
    if (GroundAt(input.x, input.y, ground_x, ground_y)) {
      float dx = ground_x - anchor_x_;
      float dy = ground_y - anchor_y_;
      if (drag_players_) {
        PlacePicked(dx, dy);
      } else if (drag_ball_ && match->GetBall()) {
        match->SetBallRetainer(0);
        float x = ClampPitch(ball_x_ + dx, pitchHalfW);
        float y = ClampPitch(ball_y_ + dy, pitchHalfH);
        match->GetBall()->SetPosition(Vector3(x, y, 0.11f));
      }
    }
  }
  if (input.released && drag_active_) {
    if (drag_marquee_ && !input.dragged && input.clicks >= 2 && !add_prompt_) {
      float ground_x = 0.0f;
      float ground_y = 0.0f;
      if (GroundAt((int)press_x_, (int)press_y_, ground_x, ground_y)) {
        add_x_ = ground_x;
        add_y_ = ground_y;
        add_prompt_ = true;
      }
    } else if (drag_marquee_) {
      if (input.dragged) SelectMarquee();
      else picked_.clear();
    }
    drag_active_ = false;
    drag_players_ = false;
    drag_ball_ = false;
    drag_marquee_ = false;
  }
}

int Gui2MatchControls::AddPromptPlayer(int team) {
  if (!editing_ || !add_prompt_ || (team != 0 && team != 1) || match == nullptr) {
    return 0;
  }
  Player* player = match->AddOutfieldPlayer(team, add_x_, add_y_);
  add_prompt_ = false;
  if (player == nullptr) return -1;
  picked_.clear();
  EditPick pick;
  pick.team = team;
  pick.index = (int)match->GetTeam(team)->GetAllPlayers().size() - 1;
  picked_.push_back(pick);
  RememberPicked();
  return 1;
}

void Gui2MatchControls::RemovePicked() {
  if (!editing_ || match == nullptr || picked_.empty()) return;
  struct Victim {
    int team = 0;
    int index = 0;
    Player* player = nullptr;
    bool spare = false;
  };
  std::vector<Victim> victims;
  for (unsigned int i = 0; i < picked_.size(); i++) {
    int team = picked_[i].team;
    if (team != 0 && team != 1) continue;
    const std::vector<Player*>& players = match->GetTeam(team)->GetAllPlayers();
    int index = picked_[i].index;
    if (index < 0 || index >= (int)players.size()) continue;
    Player* player = players[index];
    if (!player->IsActive()) continue;
    bool seen = false;
    for (unsigned int n = 0; n < victims.size(); n++) {
      if (victims[n].player == player) seen = true;
    }
    if (seen) continue;
    Victim victim;
    victim.team = team;
    victim.index = index;
    victim.player = player;
    victims.push_back(victim);
  }
  for (int team = 0; team < 2; team++) {
    int active = match->GetTeam(team)->GetActivePlayersCount();
    int chosen = 0;
    for (unsigned int i = 0; i < victims.size(); i++) {
      if (victims[i].team == team) chosen++;
    }
    if (chosen == 0 || active - chosen >= 1) continue;
    int need = chosen - active + 1;
    for (unsigned int i = 0; i < victims.size() && need > 0; i++) {
      if (victims[i].team != team) continue;
      if (victims[i].player->GetFormationEntry().role != e_PlayerRole_GK) continue;
      victims[i].spare = true;
      need--;
    }
    for (int i = (int)victims.size() - 1; i >= 0 && need > 0; i--) {
      if (victims[i].team != team || victims[i].spare) continue;
      victims[i].spare = true;
      need--;
    }
  }
  for (unsigned int i = 0; i < victims.size(); i++) {
    if (victims[i].spare) continue;
    Player* player = victims[i].player;
    if (match->GetBallRetainer() == player) match->SetBallRetainer(nullptr);
    if (player->GetFormationEntry().role == e_PlayerRole_GK) {
      std::vector<Player*> activePlayers;
      match->GetTeam(victims[i].team)->GetActivePlayers(activePlayers);
      FormationEntry entry = player->GetFormationEntry();
      for (unsigned int n = 0; n < activePlayers.size(); n++) {
        if (activePlayers[n] == player) continue;
        bool going = false;
        for (unsigned int v = 0; v < victims.size(); v++) {
          if (victims[v].player == activePlayers[n] && !victims[v].spare) going = true;
        }
        if (going) continue;
        match->GetTeam(victims[i].team)->SetFormationEntry(activePlayers[n], entry);
        activePlayers[n]->SetDynamicFormationEntry(entry);
        break;
      }
    }
    match->DetachPlayer(player);
    player->Deactivate();
  }
  picked_.clear();
  for (unsigned int i = 0; i < victims.size(); i++) {
    if (!victims[i].spare) continue;
    EditPick pick;
    pick.team = victims[i].team;
    pick.index = victims[i].index;
    picked_.push_back(pick);
  }
  if (!picked_.empty()) RememberPicked();
}

void Gui2MatchControls::Apply(const blunted::WindowControl &input, float dt) {
  DO_VALIDATION;
  // The menu is this same match. A click there is for the menu, so it must
  // not toggle a wire box. Boxes already drawn are dropped while that
  // screen is up. A chosen simulation can still toggle a box, and it still
  // draws the head labels. Edit mode picks players instead of toggling.
  GameEnv *env = GetGame();
  if (env && env->menu_screen) {
    if (!boxed_.empty()) boxed_.clear();
    if (!links_.empty()) links_.clear();
  } else if (editing_) {
    EditPointer(input);
    if (input.remove_players) RemovePicked();
  } else if (input.clicked && view_caption_) {
    OnClick(input.click_x, input.click_y);
  } else if (input.clicked) {
    TogglePlayerBox(input.click_x, input.click_y);
  }
  if (input.freeze && !edit_lock_) ToggleHold();
  if (input.view_prev && !input.view_next) Cycle(-1);
  else if (input.view_next && !input.view_prev) Cycle(1);
  if (input.lens) ToggleLens();
  MoveFree(input, dt);
}

void Gui2MatchControls::TogglePlayerBox(int x, int y) {
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  if (!renderer) return;
  Vector3 near_point;
  Vector3 far_point;
  if (!renderer->ScreenRay(x, y, near_point, far_point)) return;

  int best_team = -1;
  int best_index = -1;
  float best_t = 2.0f;
  for (int team = 0; team < 2; team++) {
    bool mirrored = TeamMirrored(match, team);
    const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
    for (unsigned int index = 0; index < players.size(); index++) {
      Player *player = players[index];
      if (!player->IsActive() || match->IsHidden(team, (int)index)) continue;
      Vector3 bmin;
      Vector3 bmax;
      PlayerBounds(player, mirrored, bmin, bmax);
      float t = 0.0f;
      if (!RayHitsBox(near_point, far_point, bmin, bmax, t)) continue;
      if (t < best_t) {
        best_t = t;
        best_team = team;
        best_index = (int)index;
      }
    }
  }
  Officials *officials = match->GetOfficials();
  PlayerOfficial *referee = officials ? officials->GetReferee() : nullptr;
  if (referee && referee->IsActive() && !match->IsHidden(-1, 0)) {
    Vector3 bmin;
    Vector3 bmax;
    PlayerBounds(referee, TeamMirrored(match, match->FirstTeam()), bmin, bmax);
    float t = 0.0f;
    if (RayHitsBox(near_point, far_point, bmin, bmax, t) && t < best_t) {
      best_t = t;
      best_team = -1;
      best_index = 0;
    }
  }
  if (best_t >= 2.0f) return;
  for (unsigned int i = 0; i < boxed_.size(); i++) {
    if (boxed_[i].team == best_team && boxed_[i].index == best_index) {
      boxed_.erase(boxed_.begin() + i);
      return;
    }
  }
  BoxedPlayer mark;
  mark.team = best_team;
  mark.index = best_index;
  boxed_.push_back(mark);
}

void Gui2MatchControls::PublishBoxes() {
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  if (!renderer) return;
  std::vector<float> corners;
  corners.reserve(boxed_.size() * 24);
  for (unsigned int i = 0; i < boxed_.size(); i++) {
    int team = boxed_[i].team;
    int index = boxed_[i].index;
    Vector3 bmin;
    Vector3 bmax;
    if (team == -1 && index == 0) {
      Officials *officials = match->GetOfficials();
      PlayerOfficial *referee = officials ? officials->GetReferee() : nullptr;
      if (!referee || !referee->IsActive() || match->IsHidden(-1, 0)) continue;
      PlayerBounds(referee, TeamMirrored(match, match->FirstTeam()), bmin, bmax);
    } else if (team == 0 || team == 1) {
      const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
      if (index < 0 || index >= (int)players.size()) continue;
      Player *player = players[index];
      if (!player->IsActive() || match->IsHidden(team, index)) continue;
      PlayerBounds(player, TeamMirrored(match, team), bmin, bmax);
    } else {
      continue;
    }
    PushCorners(corners, bmin, bmax);
  }
  if (editing_) {
    for (unsigned int i = 0; i < picked_.size(); i++) {
      int team = picked_[i].team;
      int index = picked_[i].index;
      bool already = false;
      for (unsigned int mark = 0; mark < boxed_.size(); mark++) {
        if (boxed_[mark].team == team && boxed_[mark].index == index) already = true;
      }
      if (already) continue;
      const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
      if (index < 0 || index >= (int)players.size()) continue;
      Player *player = players[index];
      if (!player->IsActive() || match->IsHidden(team, index)) continue;
      Vector3 bmin;
      Vector3 bmax;
      PlayerBounds(player, TeamMirrored(match, team), bmin, bmax);
      PushCorners(corners, bmin, bmax);
    }
  }
  int count = (int)corners.size() / 24;
  renderer->SetSelectionBoxes(count > 0 ? &corners[0] : nullptr, count);
  if (editing_ && drag_marquee_ && drag_active_) {
    renderer->SetEditRect(true, press_x_, press_y_, pointer_x_, pointer_y_);
  } else {
    renderer->SetEditRect(false, 0, 0, 0, 0);
  }
}

void Gui2MatchControls::PublishLinks() {
  Renderer3D *renderer = GetGraphicsSystem()->GetRenderer3D();
  if (!renderer) return;
  std::vector<float> points;
  points.reserve(links_.size() * 6);
  for (unsigned int i = 0; i < links_.size(); i++) {
    Vector3 a;
    Vector3 b;
    if (!PlayerAnchor(match, links_[i].a.team, links_[i].a.index, a)) continue;
    if (!PlayerAnchor(match, links_[i].b.team, links_[i].b.index, b)) continue;
    points.push_back(a.coords[0]);
    points.push_back(a.coords[1]);
    points.push_back(a.coords[2]);
    points.push_back(b.coords[0]);
    points.push_back(b.coords[1]);
    points.push_back(b.coords[2]);
  }
  int count = (int)points.size() / 6;
  renderer->SetLinkLines(count > 0 ? &points[0] : nullptr, count);
}

void Gui2MatchControls::OnClick(int x, int y) {
  if (menu_open_) {
    for (unsigned int i = 0; i < choices_.size(); i++) {
      const Choice &choice = choices_[i];
      if (Inside(choice.x, choice.y, choice.w, choice.h, x, y)) {
        int team = choice.team;
        int player = choice.player;
        int lens = choice.lens;
        CloseMenu();
        Choose(team, player, lens);
        return;
      }
    }
    bool view = HitView(x, y);
    bool lens = HitLens(x, y);
    bool freeze = HitFreeze(x, y);
    CloseMenu();
    if (view) return;
    if (lens) ToggleLens();
    else if (freeze) ToggleHold();
    return;
  }
  if (HitView(x, y)) OpenMenu();
  else if (HitLens(x, y)) ToggleLens();
  else if (HitFreeze(x, y)) ToggleHold();
}

void Gui2MatchControls::BuildChoices(std::vector<Choice> &out) const {
  Choice broadcast;
  broadcast.team = -1;
  broadcast.lens = 0;
  broadcast.label = "Broadcast";
  out.push_back(broadcast);

  Choice action;
  action.team = -1;
  action.lens = 2;
  action.label = "Action";
  out.push_back(action);

  Choice free_camera;
  free_camera.team = -1;
  free_camera.lens = 3;
  free_camera.label = "Free";
  out.push_back(free_camera);

  for (int team = 0; team < 2; team++) {
    const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
    for (unsigned int index = 0; index < players.size(); index++) {
      Choice choice;
      choice.team = team;
      choice.player = (int)index;
      choice.lens = 0;
      choice.label = PlayerLabel(team, (int)index);
      out.push_back(choice);
    }
  }
}

std::string Gui2MatchControls::PlayerLabel(int team, int index) const {
  const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
  const char *side = team == 0 ? "Left " : "Right ";
  if (index < 0 || index >= (int)players.size()) return side;
  std::string name = players[index]->GetPlayerData()->GetLastName();
  std::string role = RoleName(players[index]->GetFormationEntry().role);
  return std::string(side) + name + " " + role;
}

std::string Gui2MatchControls::PlayerSurname(int team, int index) const {
  const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
  if (index < 0 || index >= (int)players.size()) return "";
  return players[index]->GetPlayerData()->GetLastName();
}

int Gui2MatchControls::PlayerShirt(int team, int index) const {
  const std::vector<Player *> &players = match->GetTeam(team)->GetAllPlayers();
  if (index < 0 || index >= (int)players.size()) return 0;
  return players[index]->GetShirtNumber();
}

std::string Gui2MatchControls::CurrentLabel() const {
  const GameConfig &config = GetGameConfig();
  if (config.camera_lens == 3) return "Free";
  if (config.camera_team < 0 && config.camera_lens == 2) return "Action";
  if (config.camera_team < 0) return "Broadcast";
  return PlayerLabel(config.camera_team, config.camera_player);
}

int Gui2MatchControls::CurrentIndex(const std::vector<Choice> &choices) const {
  const GameConfig &config = GetGameConfig();
  for (unsigned int i = 0; i < choices.size(); i++) {
    const Choice &choice = choices[i];
    if (config.camera_lens == 3 && choice.lens == 3) return (int)i;
    if (config.camera_lens == 2 && config.camera_team < 0 && choice.lens == 2) {
      return (int)i;
    }
    if (config.camera_team < 0 && config.camera_lens != 2 &&
        config.camera_lens != 3 && choice.lens == 0 && choice.team < 0) {
      return (int)i;
    }
    if ((config.camera_lens == 0 || config.camera_lens == 1) &&
        choice.team == config.camera_team &&
        choice.player == config.camera_player) {
      return (int)i;
    }
  }
  return 0;
}

void Gui2MatchControls::OpenMenu() {
  if (!view_caption_ || menu_open_) return;
  CloseMenu();
  BuildChoices(choices_);
  int left_count = 3;
  const std::vector<Player *> &left = match->GetTeam(0)->GetAllPlayers();
  left_count += (int)left.size();
  const float row_h = 3.05f;
  const float row_w = 36.0f;
  const float menu_y = 5.0f;
  int right_count = (int)choices_.size() - left_count;
  if (right_count < 0) right_count = 0;

  Gui2Image *left_bg = new Gui2Image(
      windowManager, "match_controls_menu_left_bg", 0, menu_y, row_w,
      row_h * left_count);
  left_bg->LoadImage("media/menu/scoreboard_bg.png");
  AddView(left_bg);
  left_bg->Show();
  menu_views_.push_back(left_bg);

  if (right_count > 0) {
    Gui2Image *right_bg = new Gui2Image(
        windowManager, "match_controls_menu_right_bg", 38, menu_y, row_w,
        row_h * right_count);
    right_bg->LoadImage("media/menu/scoreboard_bg.png");
    AddView(right_bg);
    right_bg->Show();
    menu_views_.push_back(right_bg);
  }

  float origin_x = 0.0f;
  float origin_y = 0.0f;
  GetDerivedPosition(origin_x, origin_y);
  int column_start = 0;
  for (int column = 0; column < 2; column++) {
    int count = column == 0 ? left_count : right_count;
    float rel_x = column == 0 ? 0.0f : 38.0f;
    for (int row = 0; row < count; row++) {
      int index = column_start + row;
      if (index < 0 || index >= (int)choices_.size()) break;
      Choice &choice = choices_[index];
      choice.x = origin_x + rel_x;
      choice.y = origin_y + menu_y + row_h * row;
      choice.w = row_w;
      choice.h = row_h;
      Gui2Caption *caption = MakeCaption(
          "match_controls_menu_" + std::to_string(index), rel_x + 0.6f,
          menu_y + row_h * row, row_w - 1.0f, row_h * 0.9f, choice.label);
      menu_views_.push_back(caption);
    }
    column_start += count;
  }
  menu_open_ = true;
}

void Gui2MatchControls::CloseMenu() {
  menu_open_ = false;
  for (int i = (int)menu_views_.size() - 1; i >= 0; i--) {
    menu_views_[i]->Exit();
    delete menu_views_[i];
  }
  menu_views_.clear();
  choices_.clear();
}

void Gui2MatchControls::Choose(int team, int player, int lens) {
  GameConfig &config = GetGameConfig();
  if ((team == 0 || team == 1) &&
      (config.camera_lens == 0 || config.camera_lens == 1)) {
    lens = config.camera_lens;
  }
  config.camera_team = team;
  config.camera_player = player;
  config.camera_lens = lens;
  Refresh();
}

void Gui2MatchControls::Cycle(int direction) {
  std::vector<Choice> choices;
  BuildChoices(choices);
  if (choices.empty()) return;
  int index = CurrentIndex(choices);
  index += direction;
  if (index < 0) index = (int)choices.size() - 1;
  if (index >= (int)choices.size()) index = 0;
  const Choice &choice = choices[index];
  CloseMenu();
  Choose(choice.team, choice.player, choice.lens);
}

void Gui2MatchControls::ToggleLens() {
  GameConfig &config = GetGameConfig();
  if (config.camera_team != 0 && config.camera_team != 1) return;
  if (config.camera_lens != 0 && config.camera_lens != 1) return;
  config.camera_lens = config.camera_lens == 0 ? 1 : 0;
  Refresh();
}

void Gui2MatchControls::ToggleHold() {
  held_ = !held_;
  Refresh();
}

void Gui2MatchControls::MoveFree(const blunted::WindowControl &input,
                                 float dt) {
  if (menu_open_) return;
  GameConfig &config = GetGameConfig();
  if (config.camera_lens != 3) return;
  bool moving = input.forward || input.back || input.left || input.right ||
                input.down || input.up;
  if (input.look_dx == 0 && input.look_dy == 0 && !moving) return;
  config.camera_yaw -= input.look_dx * 0.005f;
  config.camera_pitch =
      Clamp(config.camera_pitch - input.look_dy * 0.005f, -1.15f, 1.15f);
  float speed = (input.fast ? 40.0f : 18.0f) * dt;
  if (moving && speed > 0.0f) {
    float cosine = std::cos(config.camera_yaw);
    float sine = std::sin(config.camera_yaw);
    if (input.forward) {
      config.camera_x += cosine * speed;
      config.camera_y += sine * speed;
    }
    if (input.back) {
      config.camera_x -= cosine * speed;
      config.camera_y -= sine * speed;
    }
    if (input.right) {
      config.camera_x += sine * speed;
      config.camera_y -= cosine * speed;
    }
    if (input.left) {
      config.camera_x -= sine * speed;
      config.camera_y += cosine * speed;
    }
    if (input.up) config.camera_z += speed;
    if (input.down) config.camera_z -= speed;
    config.camera_x = Clamp(config.camera_x, -100.0f, 100.0f);
    config.camera_y = Clamp(config.camera_y, -80.0f, 80.0f);
    config.camera_z = Clamp(config.camera_z, 0.4f, 60.0f);
  }
}

void Gui2MatchControls::Refresh() {
  if (!view_caption_) return;
  view_caption_->SetCaption(std::string("View  ") + CurrentLabel());
  const GameConfig &config = GetGameConfig();
  bool player_view = (config.camera_team == 0 || config.camera_team == 1) &&
                     (config.camera_lens == 0 || config.camera_lens == 1);
  if (player_view) {
    lens_caption_->SetColor(text_color_);
    lens_caption_->SetCaption(config.camera_lens == 1 ? "Lens  Long"
                                                      : "Lens  Eyes");
  } else {
    lens_caption_->SetColor(Vector3(140));
    lens_caption_->SetCaption("Lens");
  }
  freeze_caption_->SetCaption(held_ ? "Resume" : "Freeze");
  hint_caption_->SetCaption(config.camera_lens == 3
                                ? "Drag look  WASD"
                                : " ");
}
