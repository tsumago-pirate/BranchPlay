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

#ifndef _HPP_MENU_MATCHCONTROLS
#define _HPP_MENU_MATCHCONTROLS

#include "../../utils/gui2/view.hpp"
#include "../../utils/gui2/widgets/caption.hpp"

#include <string>
#include <vector>

class Match;

namespace blunted {
struct WindowControl;
}

using namespace blunted;

// View, lens, and freeze for the visible match window. The captions are the
// old HUD. The match window now draws those controls in the React overlay,
// so the window constructs this with draw=false and only the keys, the
// freeze flag, and the free-camera move remain. Not created when the
// window is hidden.
class Gui2MatchControls : public Gui2View {

  public:
    Gui2MatchControls(Gui2WindowManager *windowManager, Match *match,
                      bool draw);
    virtual ~Gui2MatchControls();

    void Apply(const blunted::WindowControl &input, float dt);
    // Copies the toggled players' boxes to the renderer for this frame.
    void PublishBoxes();
    bool Hit(int x, int y) const;
    bool MenuOpen() const { return menu_open_; }
    bool Held() const { return held_; }
    void SetHeld(bool held);
    // Drag players and the ball on the pitch. A drag on the grass selects
    // the players inside it. The formation table is not written.
    void SetEditing(bool on);
    bool Editing() const { return editing_; }
    // Ignore the freeze key until the edit is resumed or dropped.
    void SetEditLock(bool on);
    // True after a double-click on the grass, until a side is chosen.
    bool AddPromptPending() const { return add_prompt_; }
    void DismissAddPrompt() { add_prompt_ = false; }
    // 1 added, 0 ignored, -1 when that side has no room left.
    int AddPromptPlayer(int team);
    void RemovePicked();
    // Replaces the wire boxes. An empty list clears them. A click can still
    // toggle one player after this. The menu clears the list on its own.
    void SetBoxes(const int *teams, const int *indices, int count);
    // Replaces the lines between players. Each pair is two team and index
    // values, so count is twice the number of lines. An empty list clears
    // them. The menu clears the list on its own.
    void SetLinks(const int *teams, const int *indices, int count);
    void PublishLinks();
    int PlayerCount(int team) const;
    std::string PlayerLabel(int team, int index) const;
    std::string PlayerSurname(int team, int index) const;
    int PlayerShirt(int team, int index) const;

  private:
    struct Choice {
      int team = -1;
      int player = 0;
      int lens = 0;
      std::string label;
      float x = 0.0f;
      float y = 0.0f;
      float w = 0.0f;
      float h = 0.0f;
    };

    bool Inside(float x_percent, float y_percent, float w_percent,
                float h_percent, int x, int y) const;
    bool HitView(int x, int y) const;
    bool HitLens(int x, int y) const;
    bool HitFreeze(int x, int y) const;
    void OnClick(int x, int y);
    void TogglePlayerBox(int x, int y);
    void EditPointer(const blunted::WindowControl &input);
    bool GroundAt(int x, int y, float &out_x, float &out_y) const;
    bool PickPlayer(int x, int y, int &team, int &index) const;
    bool PickBall(int x, int y) const;
    void RememberPicked();
    void PlacePicked(float dx, float dy);
    void SelectMarquee();
    void OpenMenu();
    void CloseMenu();
    void Choose(int team, int player, int lens);
    void Cycle(int direction);
    void ToggleLens();
    void ToggleHold();
    void MoveFree(const blunted::WindowControl &input, float dt);
    void Refresh();
    void BuildChoices(std::vector<Choice> &out) const;
    std::string CurrentLabel() const;
    int CurrentIndex(const std::vector<Choice> &choices) const;
    Gui2Caption *MakeCaption(const std::string &name, float x, float y,
                             float w, float h, const std::string &text);

    Match *match;
    Gui2Caption *view_caption_ = nullptr;
    Gui2Caption *lens_caption_ = nullptr;
    Gui2Caption *freeze_caption_ = nullptr;
    Gui2Caption *hint_caption_ = nullptr;
    std::vector<Gui2View *> menu_views_;
    std::vector<Choice> choices_;
    struct BoxedPlayer {
      int team = -1;
      int index = 0;
    };
    struct LinkEnd {
      int team = 0;
      int index = 0;
    };
    struct LinkLine {
      LinkEnd a;
      LinkEnd b;
    };

    struct EditPick {
      int team = 0;
      int index = 0;
      float x = 0.0f;
      float y = 0.0f;
    };

    bool menu_open_ = false;
    bool held_ = false;
    bool editing_ = false;
    bool edit_lock_ = false;
    bool add_prompt_ = false;
    float add_x_ = 0.0f;
    float add_y_ = 0.0f;
    bool drag_active_ = false;
    bool drag_players_ = false;
    bool drag_ball_ = false;
    bool drag_marquee_ = false;
    float anchor_x_ = 0.0f;
    float anchor_y_ = 0.0f;
    float ball_x_ = 0.0f;
    float ball_y_ = 0.0f;
    float press_x_ = 0.0f;
    float press_y_ = 0.0f;
    float pointer_x_ = 0.0f;
    float pointer_y_ = 0.0f;
    std::vector<EditPick> picked_;
    std::vector<BoxedPlayer> boxed_;
    std::vector<LinkLine> links_;
    Vector3 text_color_;
    Vector3 outline_color_;
};

#endif
