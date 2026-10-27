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

#ifndef _HPP_MENU_ACTIONFEED
#define _HPP_MENU_ACTIONFEED

#include "../../gamedefines.hpp"
#include "../../utils/gui2/view.hpp"

#include <map>
#include <string>
#include <vector>

class Match;
class Player;

using namespace blunted;

// Ball touches for both teams, plus the ball's speed. The lines are the
// ball-touch animation a player just started. They are not the external
// action vocabulary. The React overlay draws them. This view has no captions.
class Gui2ActionFeed : public Gui2View {

  public:
    struct TouchLine {
      int team = 0;
      int shirt = 0;
      std::string name;
      std::string action;
      std::string clock;
      float x = 0.0f;
      float y = 0.0f;
      float speed = 0.0f;
      float ball_x = 0.0f;
      float ball_y = 0.0f;
      float ball_speed = 0.0f;
    };

    Gui2ActionFeed(Gui2WindowManager *windowManager, Match *match);
    virtual ~Gui2ActionFeed();

    void Update();
    // Notes new touches without drawing labels. The fast simulation does not draw.
    void RecordTouches();
    virtual void Exit();

    float Speed() const { return speed_; }
    const std::string &TeamName(int team) const;
    const std::string &ClockText() const { return clock_; }
    int LineCount(int team) const;
    const TouchLine &Line(int team, int index) const;
    // Every touch this match, not the eight rows on screen.
    int HistoryCount() const { return (int)history_.size(); }
    const TouchLine &HistoryAt(int index) const;
    void ClearTouches();
    // One row in the saved list. ownGoal is the player who put it in his own net.
    void NoteGoal(Player *player, bool ownGoal);

    struct Callout {
      std::string text;
      float x = 0.0f;
      float y = 0.0f;
      bool on_screen = false;
    };
    int CalloutCount() const { return (int)callouts_.size(); }
    const Callout &CalloutAt(int index) const;
    // Head labels, plus the key-moment rings and names, for this draw.
    void SyncOverlay();

  private:
    struct Seen {
      signed int animId = -1;
      e_FunctionType type = e_FunctionType_None;
    };

    static const int kRows = 8;

    struct LiveCallout {
      Player *player = nullptr;
      std::string text;
      unsigned long started_ms = 0;
    };

    bool NoteTouches(int team);
    void Push(int team, const TouchLine &line);
    void NoteLabel(Player *player, const std::string &text);
    void PlaceLabels();
    std::string Clock() const;

    Match *match;
    std::vector<TouchLine> lines_[2];
    std::vector<TouchLine> history_;
    struct Chip {
      std::string text;
      boost::intrusive_ptr<Image2D> image;
    };

    void ShowChip(const std::string &text, float x_px, float y_px, float alpha);
    void HideSpareChips();
    void PaintChip(Chip &chip, const std::string &text);
    void PlaceMomentMarks();
    void ShowMomentChip(const std::string &text, float x_px, float y_px);
    void HideMomentChips();
    void PaintMomentChip(Chip &chip, const std::string &text);
    void ShowScorerArrow(float x_px, float y_px);
    void HideScorerArrow();
    void PaintScorerArrow();

    std::vector<LiveCallout> labels_;
    std::vector<Callout> callouts_;
    std::vector<Chip> chips_;
    int chips_used_ = 0;
    std::vector<Chip> moment_chips_;
    int moment_used_ = 0;
    boost::intrusive_ptr<Image2D> scorer_arrow_;
    std::map<Player *, Seen> seen_;
    std::string team_name_[2];
    std::string clock_;
    float speed_ = 0.0f;
    TouchLine blank_;
    Callout blank_callout_;
};

#endif
