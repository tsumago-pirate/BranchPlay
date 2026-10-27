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

#undef NDEBUG

#include "src/game_env.hpp"
#include "src/menu/ingame/actionfeed.hpp"
#include "src/menu/ingame/matchcontrols.hpp"
#include "src/gamedefines.hpp"
#include "src/onthepitch/match.hpp"
#include "src/systems/graphics/graphics_system.hpp"
#include <Python.h>

#ifdef WIN32
#define BOOST_USE_WINDOWS_H
#endif
#include <boost/python.hpp>
#include <boost/interprocess/managed_shared_memory.hpp>
#include <boost/interprocess/sync/interprocess_mutex.hpp>
#include <boost/python/suite/indexing/vector_indexing_suite.hpp>

namespace bp = boost::python;
using namespace boost::python;
using namespace boost::interprocess;
using std::string;

class GameEnv_Python : public GameEnv {
 public:
  PyObject* get_frame_python() {
    ContextHolder c(this);
    screenshoot screen = get_frame();
    PyObject* str = PyBytes_FromStringAndSize(screen.data(), screen.size());
    return str;
  }

  PyObject* get_state_python(const std::string& to_pickle) {
    std::string state = get_state(to_pickle);
    PyObject* str = PyBytes_FromStringAndSize(state.data(), state.size());
    return str;
  }

  PyObject* set_state_python(const std::string& state) {
    std::string from_pickle = set_state(state);
    PyObject* str = PyBytes_FromStringAndSize(from_pickle.data(), from_pickle.size());
    return str;
  }

  void step_python() {
    ContextHolder c(this);
    PyThreadState* _save = NULL;
    Py_UNBLOCK_THREADS;
    step();
    Py_BLOCK_THREADS;
  }

  void render_python(bool swap_buffer) {
    ContextHolder c(this);
    PyThreadState* _save = NULL;
    Py_UNBLOCK_THREADS;
    render(swap_buffer);
    Py_BLOCK_THREADS;
  }

  bool poll_window(double dt) {
    ContextHolder c(this);
    bool free_look = game_config.camera_lens == 3;
    blunted::WindowControl input =
        GetGraphicsSystem()->PollWindow(free_look);
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (controls) controls->Apply(input, (float)dt);
    bool editing = controls && controls->Editing();
    bool menu = controls && controls->MenuOpen();
    if (input.pressed && !editing) {
      bool on_bar = controls && controls->Hit(input.press_x, input.press_y);
      look_armed_ = free_look && !on_bar && !menu;
    }
    // Edit keeps the left button for the players. The right button turns the view.
    if (editing && input.look_held && free_look && !menu) look_armed_ = true;
    if (!free_look || menu) look_armed_ = false;
    else if (editing) {
      if (!input.look_held) look_armed_ = false;
    } else if (!input.mouse_held) {
      look_armed_ = false;
    }
    GetGraphicsSystem()->SetMouseLook(
        look_armed_ && (editing ? input.look_held : input.mouse_held));
    if (input.escape) escape_requested_ = true;
    return controls && controls->Held();
  }

  bool take_escape() {
    bool pressed = escape_requested_;
    escape_requested_ = false;
    return pressed;
  }

  void set_held(bool held) {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (controls) controls->SetHeld(held);
  }

  // Pointer drags on the pitch. The formation table is not changed.
  void set_editing(bool on) {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (controls) controls->SetEditing(on);
  }

  // The freeze key stays ignored until the edit is resumed or dropped.
  void set_edit_lock(bool on) {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (controls) controls->SetEditLock(on);
  }

  bool add_prompt_pending() {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    return controls && controls->AddPromptPending();
  }

  void dismiss_add_prompt() {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (controls) controls->DismissAddPrompt();
  }

  // 1 added, 0 ignored, -1 when that side has no room left.
  // The body is uploaded here. That needs the GL context, which render holds
  // and this call otherwise does not. Without it the new mesh is an empty
  // array and only the selection box appears.
  int add_edit_player(int team) {
    ContextHolder c(this);
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (!controls) return 0;
    return controls->AddPromptPlayer(team);
  }

  void remove_edit_players() {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (controls) controls->RemovePicked();
  }

  bp::list added_players() {
    bp::list rows;
    Match *match = GetGameTask()->GetMatch();
    if (!match) return rows;
    std::vector<EditAddition> added;
    match->AddedPlayers(added);
    for (unsigned int i = 0; i < added.size(); i++) {
      bp::dict row;
      row["team"] = added[i].team;
      row["name"] = added[i].name;
      row["shirt"] = added[i].shirt;
      row["x"] = added[i].x;
      row["y"] = added[i].y;
      row["role"] = added[i].role;
      rows.append(row);
    }
    return rows;
  }

  void sync_added(bp::object rows) {
    ContextHolder c(this);
    Match *match = GetGameTask()->GetMatch();
    if (!match || rows.is_none()) return;
    std::vector<EditAddition> wanted;
    int count = bp::len(rows);
    for (int i = 0; i < count; i++) {
      bp::dict row = bp::extract<bp::dict>(rows[i]);
      EditAddition item;
      item.team = bp::extract<int>(row["team"]);
      item.name = bp::extract<std::string>(row["name"]);
      item.shirt = bp::extract<int>(row["shirt"]);
      item.x = bp::extract<float>(row["x"]);
      item.y = bp::extract<float>(row["y"]);
      item.role = bp::extract<int>(row["role"]);
      if (item.team != 0 && item.team != 1) continue;
      if (item.name.empty()) continue;
      wanted.push_back(item);
    }
    match->SyncAdded(wanted);
  }

  // A restored snapshot puts the old generator back. Set pieces later call
  // randomize with game_engine_random_seed, so the seed changes with it.
  void reseed(unsigned int seed) {
    ContextHolder c(this);
    scenario_config.game_engine_random_seed = seed;
    randomize(seed);
  }

  void set_fullscreen(bool on) {
    GetGraphicsSystem()->SetFullscreen(on);
  }

  void place_playback_window() {
    GetGraphicsSystem()->PlacePlaybackWindow();
  }

  void restore_playback_window() {
    GetGraphicsSystem()->RestorePlaybackWindow();
  }

  void show_window() {
    GetGraphicsSystem()->ShowWindow();
  }

  // Grow the window by the timeline and keep the picture above that band.
  void set_bottom_band(int points) {
    GetGraphicsSystem()->SetBottomBand(points);
  }

  // The camera pose last drawn, so a move can leave that spot and return.
  bp::list camera_pose() {
    bp::list pose;
    Match *match = GetGameTask()->GetMatch();
    float x = 0.0f;
    float y = -40.0f;
    float z = 5.0f;
    float yaw = 1.5707963f;
    float pitch = -0.1f;
    if (match) match->CopyShownCamera(x, y, z, yaw, pitch);
    pose.append(x);
    pose.append(y);
    pose.append(z);
    pose.append(yaw);
    pose.append(pitch);
    return pose;
  }

  void set_action_labels(bool on) {
    action_labels = on;
  }

  // Rings and names drawn in the key-moment clip. An empty list clears them.
  void set_moment_marks(bp::object marks) {
    moment_marks.clear();
    if (marks.is_none()) return;
    int count = bp::len(marks);
    for (int i = 0; i < count; i++) {
      bp::dict row = bp::extract<bp::dict>(marks[i]);
      MomentMark mark;
      mark.team = bp::extract<int>(row["team"]);
      mark.index = bp::extract<int>(row["player"]);
      mark.shape = 0;
      if (row.has_key("shape")) mark.shape = bp::extract<int>(row["shape"]);
      std::string text = bp::extract<std::string>(row["text"]);
      if ((int)text.size() > 16) text.resize(16);
      mark.text = text;
      moment_marks.push_back(mark);
    }
  }

  // Which goal this team is defending. -1 is the negative-x goal.
  int team_side(int team_id) {
    Match *match = GetGameTask()->GetMatch();
    if (!match || team_id < 0 || team_id > 1) return -1;
    int side = match->GetTeam(team_id)->GetDynamicSide();
    if (side == 0) side = team_id == 0 ? -1 : 1;
    return side;
  }

  // The shape the team is playing, one row per roster index. This table is
  // not part of the snapshot, so a branch stores it and puts it back.
  bp::list read_formation(int team_id) {
    bp::list rows;
    Match *match = GetGameTask()->GetMatch();
    if (!match || team_id < 0 || team_id > 1) return rows;
    const std::vector<Player *> &players =
        match->GetTeam(team_id)->GetAllPlayers();
    for (int index = 0; index < (int)players.size(); index++) {
      FormationEntry entry = players[index]->GetFormationEntry();
      bp::dict row;
      row["player"] = index;
      row["role"] = (int)entry.role;
      row["x"] = entry.position.coords[0];
      row["y"] = entry.position.coords[1];
      rows.append(row);
    }
    return rows;
  }

  // Set each listed player's role and slot. place also stands them there.
  // The standing-up formula matches viewer/formations.py slot_to_world:
  // six tenths of each half, the length halved again and shifted toward
  // the team's own goal, and the goalkeeper on the goal line.
  void apply_formation(int team_id, bp::object entries, bool place) {
    Match *match = GetGameTask()->GetMatch();
    if (!match || team_id < 0 || team_id > 1 || entries.is_none()) return;
    Team *team = match->GetTeam(team_id);
    const std::vector<Player *> &players = team->GetAllPlayers();
    int side = team->GetDynamicSide();
    if (side == 0) side = team_id == 0 ? -1 : 1;
    int count = bp::len(entries);
    const float depth = pitchHalfW * 0.6f * 0.5f;
    const float width = pitchHalfH * 0.6f;
    const float shift = pitchHalfW * 0.2f * side;
    for (int i = 0; i < count; i++) {
      bp::dict row = bp::extract<bp::dict>(entries[i]);
      int index = bp::extract<int>(row["player"]);
      int role = bp::extract<int>(row["role"]);
      float x = bp::extract<float>(row["x"]);
      float y = bp::extract<float>(row["y"]);
      if (index < 0 || index >= (int)players.size()) continue;
      if (role < 0 || role > (int)e_PlayerRole_CF) continue;
      if (x < -1.0f) x = -1.0f;
      if (x > 1.0f) x = 1.0f;
      if (y < -1.0f) y = -1.0f;
      if (y > 1.0f) y = 1.0f;
      Player *player = players[index];
      FormationEntry entry = player->GetFormationEntry();
      entry.role = (e_PlayerRole)role;
      entry.position = Vector3(x, y, 0);
      entry.start_position = entry.position;
      team->SetFormationEntry(player, entry);
      // The job the player is playing, not only the table a restart reads.
      // A one-time stand puts the old jobs back with place false, so a later
      // restart does not walk them out into the shape they were shown once.
      player->SetDynamicFormationEntry(entry);
      if (!place || !player->IsActive()) continue;
      float px = -side * x * depth + shift;
      float py = -side * y * width;
      if (role == (int)e_PlayerRole_GK) {
        px = pitchHalfW * side * 0.98f;
        py = 0.0f;
      }
      player->ResetPosition(
          Vector3(px, py, 0),
          Vector3(-side * pitchHalfW, 0, 0));
    }
  }

  void set_menu_screen(bool on) {
    menu_screen = on;
  }

  // The match chat resolves a request to team and roster index, then this
  // replaces the wire boxes. The click toggle still edits that same list.
  void set_boxes(bp::object marks) {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (!controls) return;
    std::vector<int> teams;
    std::vector<int> indices;
    if (!marks.is_none()) {
      int count = bp::len(marks);
      for (int i = 0; i < count; i++) {
        bp::dict row = bp::extract<bp::dict>(marks[i]);
        teams.push_back(bp::extract<int>(row["team"]));
        indices.push_back(bp::extract<int>(row["player"]));
      }
    }
    controls->SetBoxes(teams.empty() ? nullptr : teams.data(),
                       indices.empty() ? nullptr : indices.data(),
                       (int)teams.size());
  }

  // Same team and roster index as set_boxes. Team -1 index 0 is the referee.
  // ball is the drawn ball. The next Put moves those bodies out of the picture.
  void set_hidden(bp::object marks, bool ball) {
    Match *match = GetGameTask()->GetMatch();
    if (!match) return;
    std::vector<int> teams;
    std::vector<int> indices;
    if (!marks.is_none()) {
      int count = bp::len(marks);
      for (int i = 0; i < count; i++) {
        bp::dict row = bp::extract<bp::dict>(marks[i]);
        teams.push_back(bp::extract<int>(row["team"]));
        indices.push_back(bp::extract<int>(row["player"]));
      }
    }
    match->SetHidden(teams.empty() ? nullptr : teams.data(),
                     indices.empty() ? nullptr : indices.data(),
                     (int)teams.size(), ball);
  }

  // Same team and roster index as set_boxes. Each row is one line, from a
  // to b. An empty list clears the lines. PublishLinks draws them next frame.
  void set_lines(bp::object marks) {
    Match *match = GetGameTask()->GetMatch();
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (!controls) return;
    std::vector<int> teams;
    std::vector<int> indices;
    if (!marks.is_none()) {
      int count = bp::len(marks);
      for (int i = 0; i < count; i++) {
        bp::dict row = bp::extract<bp::dict>(marks[i]);
        bp::dict a = bp::extract<bp::dict>(row["a"]);
        bp::dict b = bp::extract<bp::dict>(row["b"]);
        teams.push_back(bp::extract<int>(a["team"]));
        indices.push_back(bp::extract<int>(a["player"]));
        teams.push_back(bp::extract<int>(b["team"]));
        indices.push_back(bp::extract<int>(b["player"]));
      }
    }
    controls->SetLinks(teams.empty() ? nullptr : teams.data(),
                       indices.empty() ? nullptr : indices.data(),
                       (int)teams.size());
  }

  bp::list touch_log() {
    bp::list rows;
    Match *match = GetGameTask()->GetMatch();
    Gui2ActionFeed *feed = match ? match->GetActionFeed() : nullptr;
    if (!feed) return rows;
    for (int index = 0; index < feed->HistoryCount(); index++) {
      const Gui2ActionFeed::TouchLine &line = feed->HistoryAt(index);
      bp::dict row;
      row["team"] = line.team;
      row["shirt"] = line.shirt;
      row["name"] = line.name;
      row["action"] = line.action;
      row["clock"] = line.clock;
      row["x"] = line.x;
      row["y"] = line.y;
      row["speed"] = line.speed;
      row["ball_x"] = line.ball_x;
      row["ball_y"] = line.ball_y;
      row["ball_speed"] = line.ball_speed;
      rows.append(row);
    }
    return rows;
  }

  void clear_touches() {
    Match *match = GetGameTask()->GetMatch();
    Gui2ActionFeed *feed = match ? match->GetActionFeed() : nullptr;
    if (feed) feed->ClearTouches();
  }

  bool fullscreen() {
    return GetGraphicsSystem()->Fullscreen();
  }

  bp::dict hud_feed() {
    bp::dict out;
    bp::list left;
    bp::list right;
    bp::list players;
    out["speed"] = 0.0;
    out["clock"] = "";
    out["left_name"] = "";
    out["right_name"] = "";
    Match *match = GetGameTask()->GetMatch();
    Gui2ActionFeed *feed = match ? match->GetActionFeed() : nullptr;
    if (feed) {
      out["speed"] = feed->Speed();
      out["clock"] = feed->ClockText();
      out["left_name"] = feed->TeamName(0);
      out["right_name"] = feed->TeamName(1);
      for (int team = 0; team < 2; team++) {
        bp::list &rows = team == 0 ? left : right;
        for (int index = 0; index < feed->LineCount(team); index++) {
          const Gui2ActionFeed::TouchLine &line = feed->Line(team, index);
          bp::dict row;
          row["shirt"] = line.shirt;
          row["action"] = line.action;
          row["clock"] = line.clock;
          rows.append(row);
        }
      }
    }
    Gui2MatchControls *controls = match ? match->GetControls() : nullptr;
    if (controls) {
      for (int team = 0; team < 2; team++) {
        int count = controls->PlayerCount(team);
        for (int index = 0; index < count; index++) {
          bp::dict row;
          row["team"] = team;
          row["player"] = index;
          row["name"] = controls->PlayerLabel(team, index);
          row["surname"] = controls->PlayerSurname(team, index);
          row["shirt"] = controls->PlayerShirt(team, index);
          players.append(row);
        }
      }
    }
    out["left"] = left;
    out["right"] = right;
    out["players"] = players;
    bp::list callouts;
    if (feed && action_labels) {
      for (int index = 0; index < feed->CalloutCount(); index++) {
        const Gui2ActionFeed::Callout &callout = feed->CalloutAt(index);
        bp::dict row;
        row["text"] = callout.text;
        row["x"] = callout.x;
        row["y"] = callout.y;
        callouts.append(row);
      }
    }
    out["callouts"] = callouts;
    bp::list dots;
    bp::dict ball_dot;
    ball_dot["x"] = 0.5;
    ball_dot["y"] = 0.5;
    if (match && match->GetBall()) {
      auto map_dot = [](Vector3 position) {
        Vector3 pos2d = position * Vector3(1.0f / (pitchHalfW * 2.0f),
                                           -(1.0f / (pitchHalfH * 2.0f)), 0);
        pos2d = pos2d + Vector3(0.5f, 0.5f, 0);
        return pos2d * Vector3(0.96f, 0.96f, 0) + Vector3(0.02f, 0.02f, 0);
      };
      Vector3 ball_pos = map_dot(match->GetBall()->Predict(0).Get2D());
      ball_dot["x"] = ball_pos.coords[0];
      ball_dot["y"] = ball_pos.coords[1];
      for (int team = 0; team < 2; team++) {
        std::vector<Player *> playing;
        match->GetActiveTeamPlayers(team, playing);
        const std::vector<Player *> &roster = match->GetTeam(team)->GetAllPlayers();
        Vector3 color = match->GetMatchData()->GetTeamData(team).GetColor1();
        for (unsigned int i = 0; i < playing.size(); i++) {
          int roster_index = -1;
          for (unsigned int n = 0; n < roster.size(); n++) {
            if (roster[n] == playing[i]) roster_index = (int)n;
          }
          if (roster_index >= 0 && match->IsHidden(team, roster_index)) continue;
          Vector3 position = playing[i]->GetPosition();
          if (team == 1) position *= Vector3(-1, -1, 0);
          Vector3 pos2d = map_dot(position);
          bp::dict dot;
          dot["team"] = team;
          dot["x"] = pos2d.coords[0];
          dot["y"] = pos2d.coords[1];
          dot["r"] = int(color.coords[0]);
          dot["g"] = int(color.coords[1]);
          dot["b"] = int(color.coords[2]);
          dots.append(dot);
        }
      }
    }
    out["dots"] = dots;
    out["ball"] = ball_dot;
    out["ball_hidden"] = match && match->BallHidden();
    return out;
  }

  bool look_armed_ = false;
  bool escape_requested_ = false;

  void reset_python(ScenarioConfig& game_config, bool init_animation) {
    ContextHolder c(this);
    context->step = -1;
    PyThreadState* _save = NULL;
    Py_UNBLOCK_THREADS;
    GetTracker()->setDisabled(true);
    reset(game_config, init_animation);
    GetTracker()->setDisabled(false);
    Py_BLOCK_THREADS;
  }
};

BOOST_PYTHON_MODULE(_gameplayfootball) {
  class_<std::vector<float> >("FloatVec")
      .def(vector_indexing_suite<std::vector<float> >());

  class_<std::vector<int> >("IntVec")
      .def(vector_indexing_suite<std::vector<int> >());

  class_<std::vector<PlayerInfo> >("PlayerInfoVec")
      .def(vector_indexing_suite<std::vector<PlayerInfo> >());

  class_<StringVector>("StringVector")
      .def(boost::python::vector_indexing_suite<StringVector>());

  class_<Position>("Position")
      .def("__getitem__", &Position::env_coord)
      .def("__str__", &Position::debug);

  class_<PlayerInfo>("PlayerInfo")
      .def_readonly("position", &PlayerInfo::player_position)
      .def_readonly("direction", &PlayerInfo::player_direction)
      .def_readonly("tired_factor", &PlayerInfo::tired_factor)
      .def_readonly("has_card", &PlayerInfo::has_card)
      .def_readonly("is_active", &PlayerInfo::is_active)
      .def_readonly("role", &PlayerInfo::role)
      .def_readonly("designated_player", &PlayerInfo::designated_player);

  class_<ControllerInfo>("ControllerInfo", init<int>())
      .add_property("controlled_player", &ControllerInfo::controlled_player);

  class_<std::vector<ControllerInfo> >("ControllerInfoVec").def(
      vector_indexing_suite<std::vector<ControllerInfo> >());

  class_<SharedInfo>("SharedInfo")
      .def_readonly("ball_position", &SharedInfo::ball_position)
      .def_readonly("ball_rotation", &SharedInfo::ball_rotation)
      .def_readonly("ball_direction", &SharedInfo::ball_direction)
      .def_readonly("left_team", &SharedInfo::left_team)
      .def_readonly("right_team", &SharedInfo::right_team)
      .def_readonly("left_goals", &SharedInfo::left_goals)
      .def_readonly("right_goals", &SharedInfo::right_goals)
      .def_readonly("is_in_play", &SharedInfo::is_in_play)
      .def_readonly("ball_owned_team", &SharedInfo::ball_owned_team)
      .def_readonly("ball_owned_player", &SharedInfo::ball_owned_player)
      .add_property("left_controllers", &SharedInfo::left_controllers)
      .add_property("right_controllers", &SharedInfo::right_controllers)
      .def_readonly("game_mode", &SharedInfo::game_mode)
      .def_readonly("step", &SharedInfo::step);

  enum_<GameState>("GameState")
      .value("game_created", GameState::game_created)
      .value("game_initiated", GameState::game_initiated)
      .value("game_running", GameState::game_running)
      .value("game_done", GameState::game_done);

  class_<GameEnv_Python>("GameEnv")
      .def("start_game", &GameEnv_Python::start_game)
      .def("get_info", &GameEnv_Python::get_info)
      .def("get_frame", &GameEnv_Python::get_frame_python)
      .def("perform_action", &GameEnv_Python::action)
      .def("sticky_action_state", &GameEnv_Python::sticky_action_state)
      .def("step", &GameEnv_Python::step_python)
      .def("get_state", &GameEnv_Python::get_state_python)
      .def("set_state", &GameEnv_Python::set_state_python)
      .def("reset", &GameEnv_Python::reset_python)
      .def("render", &GameEnv_Python::render_python)
      .def("poll_window", &GameEnv_Python::poll_window)
      .def("take_escape", &GameEnv_Python::take_escape)
      .def("set_held", &GameEnv_Python::set_held)
      .def("set_editing", &GameEnv_Python::set_editing)
      .def("set_edit_lock", &GameEnv_Python::set_edit_lock)
      .def("add_prompt_pending", &GameEnv_Python::add_prompt_pending)
      .def("dismiss_add_prompt", &GameEnv_Python::dismiss_add_prompt)
      .def("add_edit_player", &GameEnv_Python::add_edit_player)
      .def("remove_edit_players", &GameEnv_Python::remove_edit_players)
      .def("added_players", &GameEnv_Python::added_players)
      .def("sync_added", &GameEnv_Python::sync_added)
      .def("reseed", &GameEnv_Python::reseed)
      .def("set_fullscreen", &GameEnv_Python::set_fullscreen)
      .def("place_playback_window", &GameEnv_Python::place_playback_window)
      .def("restore_playback_window", &GameEnv_Python::restore_playback_window)
      .def("show_window", &GameEnv_Python::show_window)
      .def("set_bottom_band", &GameEnv_Python::set_bottom_band)
      .def("camera_pose", &GameEnv_Python::camera_pose)
      .def("set_action_labels", &GameEnv_Python::set_action_labels)
      .def("set_moment_marks", &GameEnv_Python::set_moment_marks)
      .def("team_side", &GameEnv_Python::team_side)
      .def("read_formation", &GameEnv_Python::read_formation)
      .def("apply_formation", &GameEnv_Python::apply_formation)
      .def("set_menu_screen", &GameEnv_Python::set_menu_screen)
      .def("set_boxes", &GameEnv_Python::set_boxes)
      .def("set_hidden", &GameEnv_Python::set_hidden)
      .def("set_lines", &GameEnv_Python::set_lines)
      .def("touch_log", &GameEnv_Python::touch_log)
      .def("clear_touches", &GameEnv_Python::clear_touches)
      .def("fullscreen", &GameEnv_Python::fullscreen)
      .def("hud_feed", &GameEnv_Python::hud_feed)
      .def_readwrite("config", &GameEnv_Python::scenario_config)
      .def_readwrite("game_config", &GameEnv_Python::game_config)
      .def_readwrite("state", &GameEnv_Python::state)
      .def_readwrite("waiting_for_game_count",
                     &GameEnv_Python::waiting_for_game_count)
      .def("tracker_setup", &GameEnv::tracker_setup);

  class_<Vector3>("Vector3", init<float, float, float>())
     .def("__getitem__", &Vector3::GetEnvCoord)
     .def("__setitem__", &Vector3::SetEnvCoord);

  class_<GameConfig, SHARED_PTR<GameConfig>, boost::noncopyable>("GameConfig", no_init)
      .def("make", &GameConfig::make)
      .staticmethod("make")
      .def_readwrite("render", &GameConfig::render)
      .def_readwrite("physics_steps_per_frame",
                     &GameConfig::physics_steps_per_frame)
      .def_readwrite("render_resolution_x",
                     &GameConfig::render_resolution_x)
      .def_readwrite("render_resolution_y",
                     &GameConfig::render_resolution_y)
      .def_readwrite("camera_team", &GameConfig::camera_team)
      .def_readwrite("camera_player", &GameConfig::camera_player)
      .def_readwrite("camera_lens", &GameConfig::camera_lens)
      .def_readwrite("camera_x", &GameConfig::camera_x)
      .def_readwrite("camera_y", &GameConfig::camera_y)
      .def_readwrite("camera_z", &GameConfig::camera_z)
      .def_readwrite("camera_yaw", &GameConfig::camera_yaw)
      .def_readwrite("camera_pitch", &GameConfig::camera_pitch)
      .def_readwrite("camera_fov", &GameConfig::camera_fov)
      .def_readwrite("camera_focus", &GameConfig::camera_focus)
      .def_readwrite("reuse_meshes", &GameConfig::reuse_meshes);

  class_<ScenarioConfig, SHARED_PTR<ScenarioConfig>, boost::noncopyable>(
      "ScenarioConfig", no_init)
      .def("make", &ScenarioConfig::make)
      .staticmethod("make")
      .def_readwrite("ball_position", &ScenarioConfig::ball_position)
      .def_readwrite("left_team", &ScenarioConfig::left_team)
      .def_readwrite("right_team", &ScenarioConfig::right_team)
      .def_readwrite("left_agents", &ScenarioConfig::left_agents)
      .def_readwrite("right_agents", &ScenarioConfig::right_agents)
      .def_readwrite("use_magnet", &ScenarioConfig::use_magnet)
      .def_readwrite("game_engine_random_seed",
                     &ScenarioConfig::game_engine_random_seed)
      .def_readwrite("reverse_team_processing",
                     &ScenarioConfig::reverse_team_processing)
      .def_readwrite("offsides", &ScenarioConfig::offsides)
      .def_readwrite("real_time", &ScenarioConfig::real_time)
      .def_readwrite("left_team_difficulty",
                     &ScenarioConfig::left_team_difficulty)
      .def_readwrite("right_team_difficulty",
                     &ScenarioConfig::right_team_difficulty)
      .def_readwrite("deterministic", &ScenarioConfig::deterministic)
      .def_readwrite("end_episode_on_score",
                     &ScenarioConfig::end_episode_on_score)
      .def_readwrite("end_episode_on_possession_change",
                     &ScenarioConfig::end_episode_on_possession_change)
      .def_readwrite("end_episode_on_out_of_play",
                     &ScenarioConfig::end_episode_on_out_of_play)
      .def_readwrite("game_duration", &ScenarioConfig::game_duration)
      .def_readwrite("second_half", &ScenarioConfig::second_half)
      .def_readwrite("control_all_players",
                     &ScenarioConfig::control_all_players)
      .def_readonly("dynamic_player_selection",
                    &ScenarioConfig::DynamicPlayerSelection)
      .def_readonly("controllable_left_players",
                    &ScenarioConfig::ControllableLeftPlayers)
      .def_readonly("controllable_right_players",
                    &ScenarioConfig::ControllableRightPlayers);

  class_<std::vector<FormationEntry> >("FormationEntryVec").def(
      vector_indexing_suite<std::vector<FormationEntry> >());

  class_<FormationEntry>("FormationEntry",
                         init<float, float, e_PlayerRole, bool, bool>())
      .def_readonly("role", &FormationEntry::role)
      .add_property("position", &FormationEntry::position_env)
      .def_readwrite("lazy", &FormationEntry::lazy)
      .def_readwrite("controllable", &FormationEntry::controllable);

  enum_<e_PlayerRole>("e_PlayerRole")
      .value("e_PlayerRole_GK", e_PlayerRole::e_PlayerRole_GK)
      .value("e_PlayerRole_CB", e_PlayerRole::e_PlayerRole_CB)
      .value("e_PlayerRole_LB", e_PlayerRole::e_PlayerRole_LB)
      .value("e_PlayerRole_RB", e_PlayerRole::e_PlayerRole_RB)
      .value("e_PlayerRole_DM", e_PlayerRole::e_PlayerRole_DM)
      .value("e_PlayerRole_CM", e_PlayerRole::e_PlayerRole_CM)
      .value("e_PlayerRole_LM", e_PlayerRole::e_PlayerRole_LM)
      .value("e_PlayerRole_RM", e_PlayerRole::e_PlayerRole_RM)
      .value("e_PlayerRole_AM", e_PlayerRole::e_PlayerRole_AM)
      .value("e_PlayerRole_CF", e_PlayerRole::e_PlayerRole_CF);

  enum_<e_RenderingMode>("e_RenderingMode")
      .value("e_Disabled", e_RenderingMode::e_Disabled)
      .value("e_Onscreen", e_RenderingMode::e_Onscreen)
      .value("e_Offscreen", e_RenderingMode::e_Offscreen);

  enum_<e_GameMode>("e_GameMode")
      .value("e_GameMode_Normal", e_GameMode::e_GameMode_Normal)
      .value("e_GameMode_KickOff", e_GameMode::e_GameMode_KickOff)
      .value("e_GameMode_GoalKick", e_GameMode::e_GameMode_GoalKick)
      .value("e_GameMode_FreeKick", e_GameMode::e_GameMode_FreeKick)
      .value("e_GameMode_Corner", e_GameMode::e_GameMode_Corner)
      .value("e_GameMode_ThrowIn", e_GameMode::e_GameMode_ThrowIn)
      .value("e_GameMode_Penalty", e_GameMode::e_GameMode_Penalty);

  enum_<Action>("e_BackendAction")
    .value("idle", Action::game_idle)
    .value("left", Action::game_left)
    .value("top_left", Action::game_top_left)
    .value("top", Action::game_top)
    .value("top_right", Action::game_top_right)
    .value("right", Action::game_right)
    .value("bottom_right", Action::game_bottom_right)
    .value("bottom", Action::game_bottom)
    .value("bottom_left", Action::game_bottom_left)
    .value("long_pass", Action::game_long_pass)
    .value("high_pass", Action::game_high_pass)
    .value("short_pass", Action::game_short_pass)
    .value("shot", Action::game_shot)
    .value("keeper_rush", Action::game_keeper_rush)
    .value("sliding", Action::game_sliding)
    .value("pressure", Action::game_pressure)
    .value("team_pressure", Action::game_team_pressure)
    .value("switch", Action::game_switch)
    .value("sprint", Action::game_sprint)
    .value("dribble", Action::game_dribble)
    .value("release_direction", Action::game_release_direction)
    .value("release_long_pass", Action::game_release_long_pass)
    .value("release_high_pass", Action::game_release_high_pass)
    .value("release_short_pass", Action::game_release_short_pass)
    .value("release_shot", Action::game_release_shot)
    .value("release_keeper_rush", Action::game_release_keeper_rush)
    .value("release_sliding", Action::game_release_sliding)
    .value("release_pressure", Action::game_release_pressure)
    .value("release_team_pressure", Action::game_release_team_pressure)
    .value("release_switch", Action::game_release_switch)
    .value("release_sprint", Action::game_release_sprint)
    .value("release_dribble", Action::game_release_dribble)
    .value("builtin_ai", Action::game_builtin_ai);

  enum_<e_Team>("e_Team")
      .value("e_Left", e_Team::e_Left)
      .value("e_Right", e_Team::e_Right);
}
