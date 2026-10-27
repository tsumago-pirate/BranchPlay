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

// written by bastiaan konings schuiling 2008 - 2015
// this work is public domain. the code is undocumented, scruffy, untested, and should generally not be used for anything important.
// i do not offer support, so don't ask. to be used for inspiration :)

#ifndef _HPP_MATCH
#define _HPP_MATCH

#include "team.hpp"
#include "ball.hpp"
#include "referee.hpp"
#include "officials.hpp"

#include "../data/matchdata.hpp"
#include "player/humanoid/animcollection.hpp"
#include "AIsupport/mentalimage.hpp"

#include "../menu/menutask.hpp"

#include <string>
#include <vector>

#include "../utils/gui2/widgets/caption.hpp"
#include "../menu/ingame/scoreboard.hpp"
#include "../menu/ingame/radar.hpp"

#include "../scene/objects/camera.hpp"
#include "../scene/objects/light.hpp"

#include "../types/messagequeue.hpp"
#include "../types/command.hpp"

#include <boost/circular_buffer.hpp>

#include <fstream>
#include <iostream>

struct PlayerBounce {
  Player *opp;
  float force = 0.0f;
};

class Gui2ScoreBoard;
class Gui2MatchControls;
class Gui2ActionFeed;

// One body appended past the starting eleven. Loading a branch that has
// these puts the same bodies back before the snapshot is read.
struct EditAddition {
  int team = 0;
  std::string name;
  int shirt = 0;
  float x = 0.0f;
  float y = 0.0f;
  int role = 0;
};

class Match {

  public:
    Match(MatchData *matchData, const std::vector<AIControlledKeyboard*> &controllers, bool init_animation);
    virtual ~Match();

    void Exit();
    void Mirror(bool team_0, bool team_1, bool ball);

    void SetRandomSunParams();
    void RandomizeAdboards(boost::intrusive_ptr<Node> stadiumNode);
    void UpdateControllerSetup();
    void SpamMessage(const std::string &msg, int time_ms = 3000);
    int GetScore(int teamID) { DO_VALIDATION; return matchData->GetGoalCount(teamID); }
    Ball *GetBall() { DO_VALIDATION; return ball; }
    Team *GetTeam(int teamID) { DO_VALIDATION; return teams[teamID]; }
    Gui2MatchControls *GetControls() { return controls; }
    Gui2ActionFeed *GetActionFeed() { return actionFeed; }
    void GetActiveTeamPlayers(int teamID, std::vector<Player*> &players);
    void GetOfficialPlayers(std::vector<PlayerBase*> &players);
    boost::shared_ptr<AnimCollection> GetAnimCollection();

    MentalImage* GetMentalImage(int history_ms);
    void UpdateLatestMentalImageBallPredictions();

    void ResetSituation(const Vector3 &focusPos);

    void SetMatchPhase(e_MatchPhase newMatchPhase);
    e_MatchPhase GetMatchPhase() const { return matchPhase; }

    void StartPlay() { DO_VALIDATION; inPlay = true; }
    void StopPlay() { DO_VALIDATION; inPlay = false; }
    bool IsInPlay() const { return inPlay; }

    void StartSetPiece() { DO_VALIDATION; inSetPiece = true; }
    void StopSetPiece() { DO_VALIDATION; inSetPiece = false; }
    bool IsInSetPiece() const { return inSetPiece; }
    Referee *GetReferee() { DO_VALIDATION; return referee; }
    Officials *GetOfficials() { DO_VALIDATION; return officials; }

    void SetGoalScored(bool onOff) { DO_VALIDATION; if (onOff == false) ballIsInGoal = false; goalScored = onOff; }
    bool IsGoalScored() const { return goalScored; }
    Team* GetLastGoalTeam() const { return lastGoalTeam; }
    void SetLastTouchTeamID(int id, e_TouchType touchType = e_TouchType_Intentional_Kicked) { DO_VALIDATION; lastTouchTeamIDs[touchType] = id; lastTouchTeamID = id; referee->BallTouched(); }
    int GetLastTouchTeamID(e_TouchType touchType) const { return lastTouchTeamIDs[touchType]; }
    int GetLastTouchTeamID() const { return lastTouchTeamID; }
    Team *GetLastTouchTeam() { DO_VALIDATION;
      if (lastTouchTeamID != -1)
        return teams[lastTouchTeamID];
      else
        return teams[first_team];
    }
    Player *GetLastTouchPlayer() { DO_VALIDATION;
      if (GetLastTouchTeam())
        return GetLastTouchTeam()->GetLastTouchPlayer();
      else
        return 0;
    }
    float GetLastTouchBias(int decay_ms, unsigned long time_ms = 0) { DO_VALIDATION; if (GetLastTouchTeam()) return GetLastTouchTeam()->GetLastTouchBias(decay_ms, time_ms); else return 0; }
    bool IsBallInGoal() const { return ballIsInGoal; }

    Team* GetBestPossessionTeam();

    Player *GetDesignatedPossessionPlayer() { DO_VALIDATION; return designatedPossessionPlayer; }
    Player *GetBallRetainer() { DO_VALIDATION; return ballRetainer; }
    void SetBallRetainer(Player *retainer) { DO_VALIDATION;
      ballRetainer = retainer;
    }

    float GetAveragePossessionSide(int time_ms) const { return possessionSideHistory.GetAverage(time_ms); }

    unsigned long GetMatchTime_ms() const { return matchTime_ms; }
    unsigned long GetActualTime_ms() const { return actualTime_ms; }
    void BumpActualTime_ms(unsigned long time);
    void UpdateIngameCamera();


    boost::intrusive_ptr<Camera> GetCamera() { DO_VALIDATION; return camera; }
    // Pose of the camera last drawn, in free-camera units. Not saved.
    void CopyShownCamera(float &x, float &y, float &z, float &yaw, float &pitch) const;
    void GetTeamState(SharedInfo *state, std::map<AIControlledKeyboard*, int>& controller_mapping, int team_id);
    void GetState(SharedInfo* state);
    void ProcessState(EnvState* state);
    bool Process();
    void UpdateCamera();
    void PreparePutBuffers();
    void FetchPutBuffers();
    void Put();
    // The drawn body or ball. The simulation keeps moving.
    void SetHidden(const int *teams, const int *indices, int count, bool ball);
    bool IsHidden(int team, int index) const;
    bool BallHidden() const { return ball_hidden_; }

    boost::intrusive_ptr<Node> GetDynamicNode();

    void FollowCamera(Quaternion &orientation, Quaternion &nodeOrientation, Vector3 &position, float &FOV, const Vector3 &targetPosition, float zoom);

    void SetAutoUpdateIngameCamera(bool autoUpdate = true) { DO_VALIDATION; if (autoUpdate != autoUpdateIngameCamera) { DO_VALIDATION; camPos.clear(); autoUpdateIngameCamera = autoUpdate; } }

    int GetReplaySize_ms();

    MatchData* GetMatchData() { DO_VALIDATION; return matchData; }

    float GetMatchDurationFactor() const { return matchDurationFactor; }
    bool GetUseMagnet() const { return _useMagnet; }

    const std::vector<Vector3> &GetAnimPositionCache(Animation *anim) const;

    void UploadGoalNetting();

    // Stand an extra player on the grass. Null when that side has no room.
    Player* AddOutfieldPlayer(int team_id, float visual_x, float visual_y);
    // Make each side's extra bodies match this list, then a snapshot can load.
    void SyncAdded(const std::vector<EditAddition>& wanted);
    void AddedPlayers(std::vector<EditAddition>& out);
    // Drop match pointers that would otherwise keep a removed body.
    void DetachPlayer(Player* gone);

    int FirstTeam() { DO_VALIDATION; return first_team; }
    int SecondTeam() { DO_VALIDATION; return second_team; }
    bool isBallMirrored() { DO_VALIDATION; return ball_mirrored; }

  private:
    bool CheckForGoal(signed int side, const Vector3& previousBallPos);

    void CalculateBestPossessionTeamID();
    void CheckHumanoidCollisions();
    void CheckHumanoidCollision(Player *p1, Player *p2, std::vector<PlayerBounce> &p1Bounce, std::vector<PlayerBounce> &p2Bounce);
    void CheckBallCollisions();

    void ApplyFirstPersonCamera(bool reverse);
    void ApplyLongLensCamera(bool reverse);
    void ApplyActionCamera(bool reverse);
    void ApplyFreeCamera();
    void ApplySidelineLens(const Vector3 &target, float fov, int subjectTeam,
                           int subjectPlayer, float positionTau, float aimTau);
    void PrepareGoalNetting();
    void UpdateGoalNetting(bool ballTouchesNet = false);
    void ApplyHidden();

    MatchData *matchData;
    Team *teams[2];
    int first_team = 0;
    int second_team = 1;
    bool ball_mirrored = false;

    Officials *officials;

    boost::intrusive_ptr<Node> dynamicNode;

    boost::intrusive_ptr<Node> cameraNode;
    boost::intrusive_ptr<Camera> camera;
    boost::intrusive_ptr<Node> sunNode;

    boost::intrusive_ptr<Node> stadiumNode;

    const std::vector<AIControlledKeyboard*> &controllers;

    Ball *ball = nullptr;
    struct HiddenBody {
      int team;
      int index;
    };
    std::vector<HiddenBody> hidden_bodies_;
    bool ball_hidden_ = false;

    std::vector<MentalImage> mentalImages; // [index] == index * 10 ms ago ([0] == now)

    Gui2ScoreBoard *scoreboard;
    Gui2MatchControls *controls = nullptr;
    Gui2ActionFeed *actionFeed = nullptr;
    Gui2Radar *radar;
    Gui2Caption *messageCaption;
    unsigned long messageCaptionRemoveTime_ms = 0;
    unsigned long matchTime_ms = 0;
    unsigned long actualTime_ms = 0;
    unsigned long goalScoredTimer = 0;

    e_MatchPhase matchPhase = e_MatchPhase_PreMatch; // 0 - first half; 1 - second half; 2 - 1st extra time; 3 - 2nd extra time; 4 - penalties
    bool inPlay = false;
    bool inSetPiece = false; // Whether game is in special mode (corner etc...)
    bool goalScored = false; // true after goal scored, false again after next match state change
    bool ballIsInGoal = false;
    Team* lastGoalTeam = 0;
    Player *lastGoalScorer;
    int lastTouchTeamIDs[e_TouchType_SIZE];
    int lastTouchTeamID = 0;
    Team* bestPossessionTeam = 0;
    Player *designatedPossessionPlayer;
    Player *ballRetainer;

    ValueHistory<float> possessionSideHistory;

    bool autoUpdateIngameCamera = false;

    // camera
    Quaternion cameraOrientation;
    Quaternion cameraNodeOrientation;
    Vector3 cameraNodePosition;
    float cameraFOV = 0.0f;
    float shownCameraX = 0.0f;
    float shownCameraY = -40.0f;
    float shownCameraZ = 5.0f;
    float shownCameraYaw = 1.5707963f;
    float shownCameraPitch = -0.1f;
    bool shownCameraReady = false;
    void NoteShownCamera(float x, float y, float z, float yaw, float pitch);
    float cameraNearCap = 0.0f;
    float cameraFarCap = 0.0f;
    float cameraFocusDistance = 0.0f;

    unsigned int lastBodyBallCollisionTime_ms = 0;

    // Smoothed first-person pose. Not part of the saved match state.
    int firstPersonTeam = -2;
    int firstPersonPlayer = -1;
    bool firstPersonReady = false;
    Vector3 firstPersonEye;
    float firstPersonAngle = 0.0f;
    unsigned long firstPersonTime_ms = 0;

    // Smoothed long-lens pose. Not part of the saved match state.
    int longLensTeam = -2;
    int longLensPlayer = -1;
    bool longLensReady = false;
    Vector3 longLensPos;
    Vector3 longLensAim;
    unsigned long longLensTime_ms = 0;

    std::deque<Vector3> camPos;

    Referee *referee;

    boost::shared_ptr<MenuTask> menuTask;

    boost::shared_ptr<Scene3D> scene3D;

    bool resetNetting = false;
    bool nettingHasChanged = false;

    const float matchDurationFactor = 0.0f;

    std::vector<Vector3> nettingMeshesSrc[2];
    std::vector<float*> nettingMeshes[2];
    // Whether to use magnet logic (that automatically pushes active player
    // towards the ball).
    const bool _useMagnet;
};

#endif
