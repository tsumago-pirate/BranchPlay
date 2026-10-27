# Engine capabilities

Verified by reading the vendored tree in `GRF/` on 23 October 2026. This was a source inspection, not a running match. Re-check these claims if `GRF/` changes.

Google Research Football is the Python environment in `GRF/gfootball/`. Gameplay Football is the C++ engine in `GRF/third_party/gfootball_engine/`. GRF’s own docs describe the environment as built on that game.

## Match generation

Confirmed in the tree:

- `create_environment` follows a Gym-style `reset` / `step` / `observation` / `render` API (`GRF/gfootball/doc/api.md`).
- Bundled scenarios include stochastic and deterministic 11-vs-11 matches and academy setups (`GRF/gfootball/doc/scenarios.md`, `GRF/gfootball/scenarios/`).
- A scenario can set initial player coordinates, role, `lazy`, and `controllable`, and can set the ball position (`GRF/gfootball/env/scenario_builder.py`). Academy scenarios already use fewer than 11 players per side.
- `11_vs_11_stochastic` sets `deterministic = False` and `game_duration = 3000` (`GRF/gfootball/scenarios/11_vs_11_stochastic.py`).
- Each environment step runs `physics_steps_per_frame` physics frames, default 10 (`GRF/gfootball/env/config.py`). The engine comment states that this is 10 environment steps per second and 100 physics frames per second (`GRF/third_party/gfootball_engine/src/game_env.cpp`). `Match::BumpActualTime_ms(10)` advances one physics frame. `steps_left` is `game_duration - step` (`GRF/gfootball/env/football_env_core.py`).
- The engine sets `match_duration` to `0.027`, and the match clock advances only while play is in progress, scaled by `matchDurationFactor` (`GRF/third_party/gfootball_engine/src/game_env.cpp`, `match.cpp`). Upstream text calls the 3000-step scenario a full 90-minute match. That figure is the scaled match clock, not wall-clock time and not 3000 seconds of physics time.
- Controller types can be mixed in the `players` list: agent, bot, lazy, keyboard, gamepad, and replay (`GRF/gfootball/doc/multi_agent.md`, `GRF/gfootball/env/players/`).

## Recording

### External action timeline

`FootballEnvCore.step` requires one action per controlled player (`left_agents + right_agents`). It stores that list on the trace and passes each entry to `perform_action` (`GRF/gfootball/env/football_env_core.py`). Dump files pickle the trace (`GRF/gfootball/env/observation_processor.py`). The replay player reads `debug['action']` back (`GRF/gfootball/env/players/replay.py`).

The same observation names the roster player each controller is driving: `left_agent_controlled_player` and `right_agent_controlled_player`. Sticky actions for those players are `left_agent_sticky_actions` and `right_agent_sticky_actions`. The default sticky set is the eight directions plus sprint and dribble (`GRF/gfootball/doc/observation.md`).

A BranchPlay timeline can therefore be one record per step, with no engine change:

- the external action actually passed to `perform_action`
- the team and controller index
- the roster player that controller was driving when the action was applied
- player and ball positions, and speed statistics derived from the per-step direction vectors

The controlled-player index has to be read from the observation before `step()`. The observation returned by `step()` is the state after the action, and a switch can change who is controlled. During the pre-match hold, `step()` can replace the submitted action before `perform_action`. The probe logs the action that was applied.

Players without an external controller do not get an action entry. Their positions and speeds are still on the same timeline. Internal `PlayerCommand` values are out of scope and are not logged.

### Speed statistics

Raw observations include:

- `ball`, `ball_direction`, `ball_rotation`
- `left_team` / `right_team` positions
- `left_team_direction` / `right_team_direction`

The observation doc defines a direction entry as the change in position during one environment step, not a named speed (`GRF/gfootball/doc/observation.md`). The engine also keeps internal speeds such as `desiredVelocityFloat` and the constants `walkVelocity` and `sprintVelocity` (`gamedefines.hpp`). Those internal values are not in the raw observation.

**Available without an engine change:** magnitudes computed from the per-step direction vectors.

**Modification if internal speed is required:** log the engine velocity. That change is not part of the action timeline.

## State forking and counterfactual edits

`get_state()` returns an opaque snapshot that includes the random-number state, player mental model, and physics. `set_state()` restores it. The API doc says this is for trying different action sequences from a fixed state (`GRF/gfootball/doc/api.md`). The snapshot is a custom `EnvState` serialization plus a pickle, not an editable public schema (`game_env.cpp`, `football_env_core.py`).

`reseed(seed)` sets `game_engine_random_seed` and seeds the generators with `randomize`. A branch calls it after `set_state`, because the snapshot puts the old generator back. Set pieces call `randomize` with that seed again (`referee.cpp`), so the seed has to change with the generator or the next stoppage returns to the original stream. `deterministic` is part of the scenario check inside `set_state` and is left alone. The generator is inside the snapshot, so a stochastic match replays from its checkpoints the same way a fixed-seed match does.

What that API does not provide:

- removing one player from a restored moment

`apply_formation(team, entries, place)` does set a whole team's shape. Each entry is a roster index, a role, and a slot in formation space (x is -1 at that team's own goal and +1 at the goal they attack). The role and slot are written on that player. `place` also stands an active player on that slot, with the same formula as a kickoff in `viewer/formations.py`: six tenths of each half, the length halved again and shifted toward that team's own goal, and the goalkeeper on the goal line. The six shapes use the mplsoccer formation table, the same slots StatsBomb, Opta, and Wyscout use, scaled from that library's 120 by 80 pitch into this space. The goalkeeper is kept, and the other slots go to the nearest active players. The ball is not moved. `read_formation(team)` reads the table back. `team_side(team)` is which goal that team is defending.

That table is not inside the snapshot. Asking for a shape stands the players on it and holds the picture. The match does not step until Resume. The stand does not replace the table: the jobs are put back, so a later restart uses the shape the match loaded with. A formation branch that did store a table writes those roles again without moving the bodies, because the snapshot already has where they were. Showing the base match writes the shape the match loaded with. A saved match from before this call still loads. Removing a player is still not part of this call, and neither is a hand move: that is the edit drag below.

`set_editing` turns on that drag. A press on a player moves that player, or every player already inside the selection, by the same ground distance. A press on the ball moves the ball. A drag across the grass selects the players inside the rectangle. `ResetPosition` writes a player and `Ball::SetPosition` writes the ball. The idle pose is applied in the same moment, so the drawn player stays inside the box when several move together. Team 1 is mirrored so the mesh stays under the pointer. Edit mode puts the picture on the free camera, taken from the view that was showing. W, A, S, and D move that camera, Q and E move it down and up, Shift moves it faster, and the right mouse button turns it. The left button still moves the players. Delete or Backspace deactivates the selected players, and the last player on a team stays. A double-click on the grass asks for a Schmarsenal or Schman City player and stands a new one of that side on the spot. The body is that side's kit, a surname from a fixed list that is not already on the pitch, and a shirt number from 1 to 99 that is not already used. Extra players are appended past the starting eleven. A branch records them, and loading that branch puts the same bodies back before the snapshot is read. Cancel removes only the ones added in that edit. Removal uses `Player::Deactivate`, not `Player::SendOff`. The formation table is not written, so a later restart still uses the shape the match loaded with. `set_edit_lock` ignores the freeze key until BranchPlay resumes or drops the edit. The branch is saved only after the edit is committed and the match is resumed. `Ball::SetPosition` is not bound to Python. `Player::SendOff` is the red-card message (`player.cpp`), and the edit does not call it.

Rebuilding the moment with `Scenario.AddPlayer` and `SetBallPosition` can place players and the ball, including a reduced player count, but only as a new episode. It does not carry velocities, fatigue, cards, ball rotation, mental images, or the RNG state of the original moment.

**Modification:** removing a player from a restored snapshot, with the rest of the snapshot preserved. The semantics are still unresolved: deactivation versus deleting the player. Moving a player or the ball is the edit drag above.

### Behavior of specific players

`Match::UpdateControllerSetup` attaches a list of human controllers to each team (`match.cpp`). `Team::SelectPlayer` and `HumanGamersSelectAnyone` choose which controllable player a controller drives, preferring players near the ball and honoring switch (`team.cpp`). A player’s `controllable` flag can exclude them from selection. `lazy` constructs an Eliza controller that does not perform automatic actions.

There is no function that says “roster index 7 uses policy A for the rest of the branch.” Adding two external controllers controls two players, but the engine still chooses which two. `action_switch` changes the selection. A behavior change aimed at two specific players therefore needs a control-layer or engine change that pins controllers to stable player identities.

`set_state` restores the engine’s controller assignment as part of the opaque state. The Python `players` configuration is fixed when the environment is created. Changing the controller layout is not a field on the snapshot.

## Rendering and cameras

`render(mode='rgb_array')` returns one frame. The default resolution is 1280 by 720 (`GRF/gfootball/env/config.py`). The accumulation image is sampled one texel at a time, with no edge blend and no occlusion darkening. The ambient pass is a fill light on the source color. Shadows are a single lookup. The long lens still softens pixels more than about 12 meters from its focus distance, with five taps. The depth buffer is 24-bit. Hardware multisampling stays off, because the g-buffer is not a multisampled target. Turning rendering on is expensive, and the environment comment notes that the first rendered frame after enabling it can have a bad camera position (`football_env_core.py`). Creating the OpenGL context always calls `SDL_CreateWindow`. On macOS that call has to happen on the main thread. `BRANCHPLAY_HIDE_WINDOW=1` adds `SDL_WINDOW_HIDDEN` so `viewer/watch.py` can serve the same frames in a browser without presenting the native window. `get_frame()` still returns the image. Without that variable the window is created hidden, and `show_window()` presents it on the desktop in front once the menu page has loaded. The process library path for that window is `.deps/prefix/lib`. Homebrew's `lib` directory is not added, because ImageIO then loads those libraries and the process dies while setting the window icon. Before SDL starts, the process ignores saved window state so AppKit does not offer to restore windows from an earlier Python crash. The camera is already the action view by then. The swap is not waited on, and the frame is copied off the GPU only when something asks for it. That window draws the view, lens, and freeze controls with the match HUD. The browser control page is served only when the window is hidden.

`Match` creates one camera. `UpdateIngameCamera` sets `camMethod = 1` and uses the wide-camera branch. The birds-eye (`camMethod == 2`) and telephoto (`camMethod == 3`) branches are present and unreachable (`match.cpp`, around the `camMethod` assignment). Camera zoom, height, FOV, and angle factor are compile-time constants in `gamedefines.hpp`, not environment config.

Other camera behavior that already runs on its own:

- After a goal, once `goalScoredTimer` reaches 1000ms, the camera orbits the scorer or the ball.
- During certain fouls, `SetAutoUpdateIngameCamera(false)` and `FollowCamera` film the referee.

`OrbitCamera` is only included from `main.cpp`. It is not used by the match. There is no Python API for the birds-eye or telephoto branches.

A first-person view is available on the live match. `GameConfig.camera_team` and `GameConfig.camera_player` are exposed on the environment's `game_config`. A negative team keeps the broadcast camera. Team `0` or `1` with a roster index puts the camera at that player's eye height and hides that player's mesh for the frame so the camera is not inside the head. The view draws past the far end of the pitch and the stands. The background fill only replaces the empty sky, so the far half of the grass is not painted over, and the distance haze used by the broadcast camera is held back so the grass stays visible from eye height. The view eases toward a mix of the way the body faces and a small glance toward the player who has the ball. Large facing changes are flattened into a pan. Choosing a different player, or a jump of more than a few meters, starts the view at the new spot immediately. `Match::ApplyFirstPersonCamera` runs at the end of `Put`, after the broadcast, goal, and referee cameras, and uses the same mirror as the rendered player. The setting is not part of the saved match state. `viewer/watch.py` sends the choice from the hidden window's page, and the visible match window's bar sets the same fields.

`GameConfig.camera_lens` 1, with the same team and player, follows that player from one sideline. The camera stays far enough to read as a long lens, eases along the touchline, and keeps the player sharp while players and stands at a different distance go soft. `Match::ApplyLongLensCamera` runs in place of the eye-level camera. Lens 0 is the eye-level view. `camera_lens` 2, with a negative team, uses that same sideline lens and aims at the ball together with the players within about 14 meters of it, a little ahead of the way the ball and the player on it are moving. It is wider than the single-player lens, so the frame holds the contest rather than the ball alone. The aim stays inside the goal line and the touchlines, including when the ball is in the net. The players in that group stay sharp. A negative team with lens 0 keeps the wide broadcast camera. The lens is not part of the saved match state. The page's camera panel sends broadcast, the action camera, and the free camera. It does not list players. The match chat can set the same fields: a perspective request uses lens 0 on that roster player, and a follow request uses lens 1. `[` and `]` still select a player's eyes, and `L` still switches that view to the long lens.

`camera_lens` 3 is a free camera. `camera_x`, `camera_y`, and `camera_z` are its position in meters. `camera_yaw` is the ground-plane direction it looks, and `camera_pitch` is the angle above the horizon, and it can look nearly straight down. `Match::ApplyFreeCamera` places that pose at the end of `Put`, including while the match is frozen, and does not ease it. With `camera_focus` at 0 the view is wide, draws out to the stands, and stays sharp. A `camera_focus` above 1 metre focuses the long-lens blur on the pitch point the camera is aimed at. The key-moment pans set that distance. The live free camera leaves it at 0. `camera_fov`, when set between 2 and 80, is that camera's field of view in degrees; 0 keeps 60, so a move can keep the long lens. The pose last drawn for the action camera and the free camera can be read back. It is not part of the saved match state. The pose is not part of the saved match state. Choosing Free and dragging in the match window turns the camera. W, A, S, and D move it across the ground, Q and E move it down and up, and Shift moves faster. The transparent panel on the match window chooses the view, the lens, and freeze. `[`, `]`, `L`, and `F` still do that from the keyboard. When the window is hidden, the browser page owns the pose and sends it with each control message.

Each starting player receives a copy of that side's kit. White text is drawn into two rectangles on that copy: the surname, and a squad number chosen from the player's role. The goalkeeper is 1, the right back 2, the left back 3, the center backs 5 and 4 from left to right, the right winger 7, the left winger 11, the center forward 9, and an attacking midfielder 10. Three central midfielders are 10, 8, and 6 from the most advanced to the deepest. The rectangles are the back of the shirt unless a `.marks` file beside the kit bitmap says otherwise. The digit is the squad number stored for that player, which is the number the match chat and the camera use. The number follows the tactical role of that slot: the striker wears 9 and plays up front, and a center back wears 5 or 4. The scenario's kickoff list is not copied onto those roles. The letters are drawn when the player is created, so a running match reloads before a moved box appears. The same surname is not drawn floating above the player. A ball touch can place a short word above that player's head when `set_action_labels` is on. The menu background and a chosen simulation both turn it on. The word is drawn into that same frame, above the head, in San Francisco Text Medium on a see-through dark grey box. It rises into place, then rises and fades out. It leads the run by about a tenth of a second.

The rendered frame includes `Gui2Radar`, a small minimap created in the `Match` constructor and shown for the whole match (`match.cpp`, `menu/ingame/radar.cpp`). That radar is not a separate static tactical view and does not draw trajectories or highlight an arbitrary player. On a visible window `Gui2ScoreBoard::Conceal` hides the engine scoreboard and `Gui2Radar::Conceal` hides the engine radar. The React panel in [in-window-ui.md](in-window-ui.md) draws the score, the clock, a separate card for each team's share of the ball, the view, freeze, fullscreen, the touch feeds, and the pitch map. The score sits at the top left, one touch list sits at the lower left, the pitch map sits at the top right, and the camera controls, labeled Camera, sit at the lower right. `Match::SpamMessage` does not draw the goal, offside, foul, or send-off line. Those events still happen. That panel sits on the picture, under the title bar. The window is resizable. A key-moment playback does not resize the match window. The panel plays a video of that stretch, drawn by the engine without presenting those frames on the match window, and deletes the file when the player closes. The video draws its own broadcast frame around that picture. It opens from a full-screen title and closes back onto that title. Head labels are off while that video is drawn. A green triangle bobs above the scorer for the opening of that video. The look at the fullbacks holds, then goes to each of them in turn, and returns to the scoring touch. It draws a thick ring on the pitch, stroked along the circle under the player, so the player covers that ring where they stand, and a name above, in that video. While that video moves the camera and the players are holding still, the meshes stay and the shadow already on the grass stays with them. Those frames are not skinned, and the shadow image is not cleared. The frame read for that video is the pitch above the timeline band, and it packs each row tightly, so a window whose width is not a multiple of four still comes back as a plain image. The timeline asks for a band of its own height at the bottom of the window. The window grows by that much, and the camera extends down into that band so the timeline sits on the picture. The framing above the band stays put. Fullscreen does not grow, so the band then sits on the picture. Fullscreen renders at the window’s pixel size and opens the camera: wider shows more sideways, taller shows more above and below, and the 1280 by 720 framing stays on the axis that did not grow. The same path is the green button, F11, and Command-F. The window stays in sRGB color, including while it is fullscreen, so the picture does not pick up a darker display tint. A hidden window still draws the engine scoreboard and the engine radar into the picture. The engine still keeps the touch log and the key handling. It does not draw that panel. The sun is fixed to a clear day in `Match::SetRandomSunParams`: high, in front of the broadcast camera, noon color. It does not draw a random position or a dusk mix. The sun shadow map is cleared before each frame, so a player shadow does not stay where that player used to be. The lighting shader compares that stored depth itself. Resizing the window was replacing that 2048 image with a window-sized depth image, and the sample then came back as shadow across the picture. The map is built again when the window size changes, so it stays 2048.

The on-screen touch list is still eight rows per team. `Gui2ActionFeed` also keeps one record for every touch in the match: team, shirt, surname, the touch name, the clock, that player's place and speed, and the ball's place and speed at that touch. The feed is created even when the window is not showing a picture. `RecordTouches` runs on the simulation step, so the list is kept when the picture is not drawn. `touch_log()` reads that list once. `clear_touches()` drops it, the eight on-screen rows, and the memory of which touches were already shown, so a restored kickoff starts the list empty. The save writes that list beside the kickoff snapshot. It is not a reading for every moment. When a goal is scored, `NoteGoal` adds one row for the scorer, `GOAL` or `OWN GOAL`, with the same place, speed, and ball fields. That row is not one of the eight on-screen lines.

If a dump has no RGB frame, `get_frame` draws a rectangle and writes player index letters at their coordinates (`observation_processor.py`). That is a debug image, not an exploration view.

`dump_full_episodes` and `write_dump` store the episode trace. `replay.py` can play a dump only when frame 0 is the start of the episode (`script_helpers.py`). Video export from a dump is a single sequence in AVI or WebM.

**Modifications for the confirmed viewing requirements:**

- Selectable static and moving cameras. The unused birds-eye and telephoto code shows those framings were considered inside `UpdateIngameCamera`; they are not available. The free camera described above is a viewer-moved camera, not one of those branches.
- A way to hold the simulation and aim the camera. Freezing the match skips `step`, and the free camera can be moved on the repeated frame.
- First-person for a chosen roster player is implemented, as described above. The action camera and the long lens are implemented as well.

A left click on a player during a chosen simulation toggles a wire box around that player. A second click on the same player removes it. Each player keeps its own box. The box is upright, as tall as that player, and about a metre across, on the position the mesh is drawn at. The menu background does not. While that screen is up, a click is ignored and any box already drawn is cleared. A chosen simulation draws the head labels until the chat turns captions off, and can still toggle a box. The match chat can replace that set: `set_boxes` takes team and roster index, and `PublishBoxes` draws those players on the next frame. Team -1, index 0 is the referee, who is not on either roster. `set_hidden` uses that same pair, plus a ball flag. The next draw moves a hidden body out of the picture and leaves the ball undrawn. The shadow pass skips that ball, so its spot on the grass goes with it. The simulation position is unchanged. The pitch card omits a hidden player and, when the ball is hidden, the ball. Showing them draws them again. A wire box is not drawn on a hidden body, and a click does not select one. Who matches a role, a place, or a stat is decided outside the engine. `set_lines` takes pairs of team and roster index, and `PublishLinks` draws a white line between those players on the next frame, at the feet, on the position the mesh is drawn at. The line is left out while either player is hidden. The menu background clears the lines. The wire box is drawn in the picture rectangle. A click is mapped through that same rectangle, so it lands on the player shown there. A trajectory of one player's path is still not drawn. A static tactical view is still not an engine mode.

## Comparison export

No engine path composites two episodes, pauses the simulation for a camera move, or draws vector overlays. Those export enhancements remain tentative. The confirmed export is a BranchPlay product: two rendered sequences, side by side, plus grounded comparison narration in a language chosen before export.

## Action vocabulary reference

Source: `GRF/gfootball/env/football_action_set.py`.

Default (`action_set_v1`): `idle`, `left`, `top_left`, `top`, `top_right`, `right`, `bottom_right`, `bottom`, `bottom_left`, `long_pass`, `high_pass`, `short_pass`, `shot`, `sprint`, `release_direction`, `release_sprint`, `sliding`, `dribble`, `release_dribble`.

`v2` adds `builtin_ai`.

`full` also adds `keeper_rush`, `pressure`, `team_pressure`, `switch`, and the release actions for long pass, high pass, short pass, shot, keeper rush, sliding, pressure, team pressure, and switch.

Narration uses this vocabulary. Internal `e_FunctionType` values are out of scope and are not observed actions.
