# In-window UI

How the match window’s controls are drawn, and how a click reaches the match.

The visible controls are a React page in `viewer/ui`, built with Tailwind, drawn by a transparent panel (`viewer/overlay.swift`) on top of the OpenGL window. Each card’s fill is a Three.js fragment shader (`viewer/ui/src/ShaderFill.jsx`): a dark grey gradient, a little darker than a flat charcoal, that keeps moving. The panel stays on the match window. It is not shown on other desktops. A move repositions the panel without waiting for the page to redraw. If the match window is not ready on the first look, the panel keeps looking instead of giving up. A click on a card stays in the panel. On the menu, a click on the picture stays in the panel too, so it does not raise the match window or draw a wire box. Once a simulation is running, a click on the pitch falls through to the game, so free-camera drag still works, and a click that lands on a player toggles a wire box around that player. A second click on the same player removes it. While the match window is the front window, the panel stays above it, including on open when that process is not the active app yet, so the menu is on the first picture and a click on the pitch does not drop the cards behind it. A single missed look at the window list does not hide the menu. The page receives match state as text. It does not receive pictures, and the match loop does not call `glReadPixels`.

Boot opens on a menu over a match that is already playing. The match window stays hidden until that menu page has loaded, then opens on the desktop in front. The camera is already the action view, and the menu is placed on that window once it has settled, so that menu is the first picture. The wordmark sits at the upper left, the choices sit lower, and a soft dark fade covers the left of the picture. About sits at the lower right. Run a simulation has a see-through black panel behind it. The other choices do not. Quit closes the window. Escape leaves a chosen simulation and returns to the menu. That match is not a chosen simulation. Its camera stays on the action view, and the match starts again when it reaches full time. When a player starts a ball touch, the word for it is drawn in that same picture, just above the player's head: Geist Medium on a see-through black box. A chosen simulation draws those words too. Run a simulation plays the match through without drawing it, saves that match, and shows a progress bar while it does. It also keeps every touch from that match: who did it, the touch, the clock, where they were, how fast they were moving, and where the ball was and how fast it was moving. It does not keep a reading for every moment. A goal is stored with the player who scored it, and an own goal is stored apart from that. When the bar finishes, that save opens from the kickoff and the match controls appear. The chat can use that saved list for the whole match, including what has not happened yet on the clock. Highlight or connect can name a future result, a role, a count, and a cutoff, as in highlighting the player who will score the most goals, or connecting the three center backs from either team who will have completed the most passes by 45:30. A completed pass is one whose next touch is a teammate. Connect A to B draws a line from each player named before "to" to each player named after it. A saved match also keeps a snapshot about once a minute. The clock on that match can be dragged to another moment: the picture jumps to the nearest snapshot, the match runs without drawing up to the chosen clock, and it holds there until Resume. That clock is one line in a band at the bottom of the window. The window grows by the height of that band, and the camera extends down into it, so the band sits on the picture and the pitch above stays clear. The bottom corners of that band follow the window's corners. A menu on the strip chooses which timeline is shown. Opening all lines shows each branch beside the others. A branch leaves its line and runs beside it to its own end. The line stops at each branch circle. Drag along a line, and at a circle drag toward the branch you want. Clear branches removes every branch of the match on screen and returns to that match. Run a simulation asks for a deterministic match or a stochastic one. Both are saved and can be scrubbed. From the moment on screen, Branch plays new matches from that moment with a new random seed. The default is two. Each one can run to the end or for a number of match minutes. An empty minutes field runs to the end. The minus and plus buttons change that length, and the field takes a number while it is focused. The original match stays as it was. Choosing one of those branches scrubs that recording. Highlight key moments, or find key moments, marks each goal on the timeline on screen, from 60 seconds before that goal through the goal. The same request on a branch marks that branch. Those marks stay with that timeline until hide key moments or remove key moments. Those stretches run from green to red. They swell up from the line when marked, and shrink back into it when removed. Double-clicking one asks for a language first: English, Spanish, French, Portuguese, or German, each with its European flag. The list drops open. That choice is the language of the article, the key-moment video, and the counterfactual. After the video plays, it can be saved to this computer. The other panels then slide off the picture, and a short article eases into the middle. The article names the moment, shows a small looping picture of that stretch, and one short paragraph on why it mattered and what allowed it. Phi-4 mini writes that paragraph through Microsoft Agent Framework from the action log of that stretch only: the players, the shirts, the actions, the places, and the speeds. The match chat is unchanged. Play the key moment, at the bottom of the article, opens the clip. That player shows a progress bar until the clip is ready, and the clip plays without playback controls. When the clip ends, the panel stays open and asks whether to run a counterfactual. Yes films the original and a new run from the start of that moment, for the same length, and plays them side by side. The new run is one in which neither side scores. Both open on the same frame. When the plays separate, both pictures freeze and the camera moves in on the ball, with a ring and a name on the player there. They freeze again when the original scores: a green triangle on the scorer, and the camera on the ball in the other run. Then the plays run on. That segment opens and closes on a full-screen title in green and purple. The new run is saved with the match and is not drawn on the timeline. No closes the panel. The match window stays the size it was. The clip is a video of the action camera at the picture's full resolution, 60 frames a second, and that file is deleted when the player closes. The article picture is a small animated WebP of the same stretch, and that file is deleted when the article closes. That video is a broadcast frame, separate from the match panels. It opens on a full-screen title, KEY MOMENT, over a moving chevron pattern in league magenta and purple. That title opens onto the broadcast frame, and at the end the frame closes back onto the same title. The picture sits on a moving stepped pattern in the league colors, the score and clock extend in at the top left, and the scorer's name, number, and minute extend in along the bottom when the pass toward the scorer begins. Head labels are off for the whole clip. For the opening of the match picture, a green triangle bobs above the player who will score. When the ball is a fifth of a metre from the scorer the picture holds, then the camera goes to each of the other team's fullbacks in turn and holds on each one, and returns for the scoring touch. A thick ring and a name mark the fullback the camera is on. The ring lies on the pitch under that player, and the player covers it where they stand. Slow motion is the scoring touch through the ball in the net, drawn by the engine one physics frame at a time. The clip keeps every picture until the restart that follows the goal. The ball and the players hold on that last picture while the camera finishes the move it was already making. A question such as who will score the most goals uses the same list and does not change the picture. Previous simulations lists those saves. Opening one plays that same match again. Remove deletes that save and its branches. Settings only switches between the window and fullscreen.

What that panel can do, once a simulation is running: choose broadcast, the action camera, or the free camera; freeze and resume; enter and leave fullscreen; show both teams’ ball touches and a pitch map; ask about this match. The score and the clock sit at the top left. A second card sits under that one and shows each team's share of the ball up to the clock on screen. The time from one touch to the next counts for the team that made the touch. The last touch holds through the clock on screen. A scrub uses only the touches up to the moment it lands on. Before any touch, the split is even. One touch list sits at the lower left. It mixes both teams and does not name them. The pitch map sits at the top right. The camera controls sit at the lower right, labeled Camera, and do not list players. A match card sits at the bottom center, between those two. A question there is answered from the score, the clock, the ball, and one record per player. That record is the full touch log counted up: control, trap, short pass, long pass, high pass, passes as those three added together, header, shot, deflect, catch, and touches, plus role, shirt, place, speed, and distance from the ball. Phi-4 Mini Instruct writes that reply. The card starts collapsed, showing that name beside the Microsoft mark. Choosing that bar grows that same card into the open one. The arrow across from Match points down and collapses that card. An empty field types an example prompt, then clears it, and goes on to the next. It is not the narration model. Asking to move a team into 4-3-3, 4-2-3-1, 4-4-2, 3-5-2, 3-4-2-1, or 4-5-1, for one side or both, stands that side in the shape on the picture and the pitch map and holds the match there. The match plays on when Resume is pressed. A later restart does not stand them in that shape again. The original line stays on the timeline. Edit on that bar slides the other cards off, holds the match, switches to the free camera, and lets a drag on the picture move players or the ball. W, A, S, D, Q, E, and Shift move that camera, and the right mouse button turns it. Delete or Backspace removes the selected players. A double-click on the grass asks whether to add a Schmarsenal or a Schman City player, and stands them on that spot with an unused shirt number and a surname that is not already on the pitch. A drag across the grass selects the players inside it, and the next drag moves that group together. Commit keeps the new positions and brings the cards back. Resume after that saves a branch and plays it. Cancel or a scrub puts the players back and does not save a branch. A request to mark players searches that record, including a team name such as Schmarsenal or Schman City, an odd or even shirt, a count such as eight or more passes, anyone who has made that touch, the most or fewest of one of those counts, or every player on the pitch, and replaces the wire boxes with the players who match. Unhighlight all players clears those boxes. Goalie means the goalkeepers, and ref means the referee. Hide and show use that same search for players, the referee, and the ball. A hidden one is left out of the picture and the pitch map until it is shown again. Connect draws a white line between each pair of players that same search finds. Those lines stay, and further connects add to them, until the lines or the connections are cleared. A new simulation starts with none. A request to see a player's perspective puts the camera at that player's eyes. A request to follow that player uses the long lens. The same request can ask for the broadcast, the action camera, or the free camera. A shirt worn on both sides asks which side. Typing in that card takes the keyboard. Leaving the card gives the keys back to the match. `[` and `]` still change the view, including a player’s eyes, and `L` still changes that player’s lens. The middle of the picture stays clear. The panel covers the picture, under the title bar. Fullscreen renders at the window size. A wider window shows more to the sides, and a taller window shows more above and below, with the original 1280 by 720 framing kept on the other axis. In the game window, drag looks around in Free, W A S D move, Q and E move down and up, and Shift is faster. `F` freezes. Fullscreen is the green button, the Full screen control, F11, or Command-F. Command-F does not freeze. The browser page that shows pictures is served only when `BRANCHPLAY_HIDE_WINDOW=1`. Camera behavior itself is in [engine-capabilities.md](engine-capabilities.md).

On a visible window the engine scoreboard and the engine radar are hidden. The overlay draws the score, the clock, a separate card for each team's share of the ball, and the pitch map. A hidden window still draws the engine scoreboard and the engine radar into the picture. The old caption bar and the old caption feed are not added to the HUD.

## Two owners

When the OpenGL window is visible, clicks belong to the overlay and keys belong to the engine. `Gui2MatchControls` is still constructed, with drawing off, so it is not on screen. It still applies `[`, `]`, `L`, `F`, and the free-camera move. The overlay sends a camera choice or a freeze only when a card is clicked. `run_window` writes that onto `game_config` or `SetHeld` once, then `poll_window` runs the keys.

```
watch.py run_window
    take a click from the overlay, if one arrived
    poll_window(dt)          keys, free-camera move, freeze, fullscreen, player box
    publish state text       no picture
    if frozen: render(True)  redraw, do not step
    else:      step()        physics, then the same redraw
```

`run_window` must not call `use_camera`. That helper writes the whole pose from the browser session and would pull the free camera back.

When the window is hidden, `PresentsWindow()` is false, the controls and the touch log are not created, and `watch.py` keeps the browser page. That page sends the same `camera_team`, `camera_player`, and `camera_lens` fields.

Rebuild the panel after changing it:

```
cd viewer/ui && npm install && npm run build
swiftc -O -o viewer/overlay viewer/overlay.swift -framework Cocoa -framework QuartzCore -framework WebKit
```

`watch.py` compiles `viewer/overlay.swift` when the binary is missing or older than the source. The page is the files in `viewer/ui/dist`.

## Where the code lives

BranchPlay code stays outside `GRF/` except for this engine change.

| Piece | File |
| --- | --- |
| Key, freeze, and free-camera handling, not drawn | `GRF/third_party/gfootball_engine/src/menu/ingame/matchcontrols.hpp`, `matchcontrols.cpp` |
| Created and destroyed with the match | `src/onthepitch/match.cpp`, pointer on `Match` in `match.hpp` |
| Build list | `sources.cmake` (`MENU_HEADERS`, `MENU_SOURCES`) |
| Mouse and keys for one poll | `src/systems/graphics/rendering/opengl_renderer3d.cpp` (`PollWindow`) |
| What one poll returns | `WindowControl` in `interface_renderer3d.hpp` |
| Python binding | `ai.cpp`, `GameEnv_Python::poll_window` |
| Visible-window loop | `viewer/watch.py`, `run_window` |
| Camera choice consumed | `Match::Put` in `match.cpp` |

The radar (`src/menu/ingame/radar.cpp`) is still drawn by the engine. `Gui2ScoreBoard::Conceal` hides the engine scoreboard when the window is visible. The React panel draws that score.

## What Gui2 actually is

The HUD is `blunted::Gui2`. A `Gui2View` is a named rectangle. It can hold child views. It is not a button, a menu, or a layout container.

Widgets that exist:

- `Gui2Caption` draws one line of text with SDL_ttf onto an `Image2D`.
- `Gui2Image` scales a bitmap onto an `Image2D`. `LoadImage` reads a BMP. A path ending in `.png` is turned into a `.bmp` under `data/media/` by the resource loader. The bar reuses `media/menu/scoreboard_bg.png`.
- `Gui2Frame` is a bordered rectangle. The bar does not use it.
- `Gui2Root` is the parent of the scoreboard, the radar, the message caption, and the bar.

There is no click handler on a view. Focus exists (`SetFocus`, `OnGainFocus`) and the engine’s own menus use it. The match bar does not. A click is a rectangle test in `Gui2MatchControls`, written for this window.

`GetImages` does not walk children. Each caption and image registers its own picture. `Show` and `Hide` only enable or disable those pictures.

## How a rectangle becomes pixels

Positions are percentages of a virtual screen, not pixels and not CSS.

- The root is `(0, 0, 100, 100)`.
- A child’s percentages are added to its parent’s. They are not scaled by the parent’s size. A caption at `(1, 0.3)` inside a bar at `(2, 8.5)` is at `(3, 8.8)` on the screen.
- `Gui2WindowManager::GetCoordinates` turns those percentages into pixels. It letterboxes to the window manager’s aspect ratio, then scales by `effectiveW` and `effectiveH`. At 1280×720 that inset is zero, so a percentage maps straight onto the framebuffer.
- `UpdateImagePosition` places each view’s image at the derived top-left. Draw order is the order views were added. Add the background first, then the text.

`Gui2Caption::SetCaption` uppercases the string and ignores an unchanged string. An empty string is drawn as a single space, because an empty caption does not render. `SetColor` and `SetCaption` redraw the text image immediately. The new pixels appear on the next `render` or `step`.

The 3D scene is drawn first. `GraphicsTask::Render` then pokes every `Image2D` in `scene2D` and draws that queue with `RenderOverlay2D`, on top of the pitch, with depth off. `SwapBuffers` presents the window. Nothing in that path knows which rectangle is a button.

## Lifetime

`Match` builds the HUD after the teams exist:

1. Scoreboard and radar are added to `Gui2Root` and shown.
2. The game page is created. That does not remove those views.
3. If the window is visible, `Gui2MatchControls` is constructed with drawing off, and `Gui2ActionFeed` is constructed with no captions. Neither is added to the root. A hidden window skips both, so `GetControls()` is null.

Construction of a caption needs rendering to be on. The match is already in that state when the bar is built.

`Gui2View::Exit` hides the view, calls `Exit` on every child, deletes those children, and removes itself from its parent. The destructor asserts that `Exit` was called. `Match::Exit` does that for the bar before it releases the menu task.

A menu row is the same kind of child. `OpenMenu` adds images and captions and remembers them. `CloseMenu` calls `Exit` and `delete` on that list only. `Exit` already removes the child from the parent, so the parent must not delete it again.

Image names go into the surface manager. Reuse a name only after `Exit` has removed that image. Two live views must not share a name.

`env.reset()` builds a new `Match`. The bar is a new object. Freeze does not survive a reset, and neither does an open menu. On a visible window the next match is started without reading the picture, because that read still expects 1280 by 720 and the window may be larger. The match is built with drawing on. That load is what brings in the stadium around the pitch; a rebuild with drawing off keeps the pitch-only stand-in. The warmup steps after that build are the part that skip the picture. The player mesh still bakes its standing pose during the build. The hair follows the head joint, so a skipped bake left the hair above a crouched body.

## Input

SDL events are not delivered to Gui2. `OpenGLRenderer3D::PollWindow` drains them. `GameEnv_Python::poll_window` then hands the result to `Gui2MatchControls::Apply`.

`WindowControl` is one poll:

- `clicked`, `click_x`, `click_y` for a left press and release that moved no more than 5 pixels. Coordinates are HUD pixels, scaled from the SDL window size to the framebuffer by `ToHudX` and `ToHudY`. When the caption bar is not drawn and the menu screen is not up, that click toggles the wire box on the player under it. The menu background does not draw a box. Head labels stay on for the menu and for a chosen simulation.
- `pressed`, `press_x`, `press_y`, and `mouse_held` for a press that is still down.
- `look_dx`, `look_dy` only while relative mouse mode is already on.
- `freeze`, `lens`, `view_prev`, `view_next` from F, L, `[` / comma, and `]` / period. These are the same actions as the bar. They are not a second UI.
- W A S D, Q, E, and Shift from the keyboard state, so a held key keeps moving the free camera.

A click on the bar or an open menu does not start mouse-look. Look arms only when the press misses the bar, the menu is closed, and the lens is already the free camera. Relative mouse mode starts at the end of that press. Closing the menu or releasing the button turns it off. Edit mode uses that same free camera, starting from the view that was on screen. W, A, S, D, Q, E, and Shift move it, and the right mouse button turns it. The left button still moves players. Delete or Backspace removes the selected players. A double-click on the grass asks whether to add a Schmarsenal or a Schman City player, and stands them on that spot with an unused shirt number and a surname that is not already on the pitch.

`SDL_HINT_MOUSE_FOCUS_CLICKTHROUGH` is set before the window is created so the click that focuses the window is also a click on the bar.

`poll_window` returns whether the simulation is held. The overlay can set that flag with `set_held`. `F` still toggles it inside `Apply`. The loop publishes the flag after `poll_window`, and it does not write the flag again unless the overlay sends a new one.

## Camera and freeze

The keys and the overlay write `GameConfig` on the environment:

| Choice | `camera_team` | `camera_player` | `camera_lens` |
| --- | --- | --- | --- |
| Broadcast | negative | 0 | 0 |
| Action | negative | 0 | 2 |
| Free | negative | 0 | 3 |
| A player, eyes | 0 left, 1 right | index in `Team::GetAllPlayers()` | 0 |
| A player, long lens | same | same | 1 |

`camera_player` is that roster index, the same order as the formation. It is not the observation’s role order. The label is the side, `PlayerData::GetLastName()`, and the formation role. `SetCaption` uppercases it.

Choosing another player while the lens is already eyes or long keeps that lens. Lens does nothing for broadcast, action, and free. The camera panel does not list players or lenses. `[` and `]` still select a player’s eyes, and `L` still switches that view to the long lens.

Free movement is `Gui2MatchControls::MoveFree`. It writes `camera_x`, `camera_y`, `camera_z`, `camera_yaw`, and `camera_pitch`. The menu being open suppresses that movement. `Match::ApplyFreeCamera` applies the pose at the end of `Put`, including on a frozen redraw.

Freeze is `Gui2MatchControls::held_`. It is not a field of `GameConfig` and it is not saved match state. The camera fields are also excluded from the saved state. `Put` still runs during a frozen redraw, so the clock caption, the radar, and the camera update, but `watch.py` does not call `step()`, so physics, the match clock, and the score do not advance.

## Adding another control

Stay inside this pattern until a real widget set exists.

1. Add a `Gui2Caption` or `Gui2Image` as a child of a `Gui2View`, then `Show` it. Put the view on `menuTask->GetWindowManager()->GetRoot()` from the match, or add it under the bar if it should sit in that rectangle.
2. Hit-test with `GetDerivedPosition`, `GetSize`, and `GetCoordinates`. Compare those pixels to `click_x` and `click_y`.
3. Change match state from `Apply`, on the same thread as `PollWindow`. Do it before `step` or `render`, so the next picture shows it.
4. If the control only changes the picture, a frozen match must `render(True)`. `step()` is what draws during play.
5. Register a new `.cpp` in `sources.cmake` and re-run CMake in `GRF/third_party/gfootball_engine`. The existing Makefile does not pick up a new file by itself. Rebuild `libgame.dylib` and copy it onto `GRF/.venv/lib/python3.11/site-packages/gfootball_engine/_gameplayfootball.so`. The running process keeps the old library mapped, so restart `viewer/watch.py` after the copy.

A new control that must work with the window hidden belongs in the browser page as well. The page and the bar are two front ends on the same `GameConfig` fields. Only one of them is active at a time.

## Action feed

`Gui2ActionFeed` keeps the touch log when the window is visible. It is not drawn. The overlay draws the lines. `Match::Put` still calls `Update`, so a frozen redraw still refreshes the log and does not add a second copy of a touch that already happened. `hud_feed` reads the lines, the team short names, the match clock, and the ball speed out to Python.

The engine keeps a column per team. The overlay shows one list of the four newest touches from both, with no team name. That list is four rows tall from the first frame. A line is added when a player starts a ball touch: control, trap, short pass, long pass, high pass, header, shot, deflect, or catch. Running, and a further control touch while the player is already controlling the ball, do not add a line. The line is the shirt number, that touch, and the match clock (`GetMatchTime_ms`, the same clock as the scoreboard). The newest line is the top line. Eight lines stay in the log.

The shirt number is the one stamped on the kit when the player is activated. It reads the same way on the back of the shirt. It is not part of the saved match state.

Between the columns, a caption shows the ball's speed for the whole match. The number is `Ball::GetMovement().GetLength()`, meters per second. That is the engine's ball momentum. It does not decide the unresolved choice of which speed quantity a recorded timeline should store.

These touch names are the animation the player started. They are not the external action names used for narration.

The same touch can also place a short word above the player's head. The chat calls that word a caption. `set_action_labels` turns those captions on. The menu background and a chosen simulation both leave them on. Turn captions off leaves them off until they are turned on again, or until the next simulation starts. The word rises into place above the head, holds, then rises and fades out. It follows the head while it is visible, a tenth of a second ahead of the run. Ball control reads as dribble, and a short pass reads as pass. A long pass, high pass, trap, header, shot, deflect, and catch keep those words. The word is drawn into the picture in the same frame as the player, so it stays on the head instead of following a later copy of the position. The type is Geist Medium, the overlay's medium weight, on a see-through black box with a 4px corner.
