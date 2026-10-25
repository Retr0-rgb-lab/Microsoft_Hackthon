# Coach board front end v1

Design note. This version fixes only the interface and the data; it changes no existing page and connects to no backend.

The league interface stays in `touchline/index.html` and `touchline/app.js`, on port 5173. The 3D sample stays in `touchline/scene`, on port 5174. The coach board is a third screen: watching, annotating and setting a formation all happen on one pitch.

The pitch uses the v0.1 sample's centre-circle origin, metres, 105×68. Data `(x, y, z)` enters three.js as `(x, z, -y)`, and `rotation.y` takes the data facing. It does not read the league's top-left origin, 5 Hz tracking.

## 1. Directory, port, and what to take from scene

The directory is `touchline/board/`. It sits alongside `touchline/scene` and `touchline/data/samples/sample_25hz_10min`, so the sample's relative path is easy to reach without becoming the league shell.

Dev server `127.0.0.1:5175`, `strictPort: true`. When 5173 and 5174 are taken, this app fails outright rather than grabbing a port.

The Vite alias `@scene` points at `touchline/scene/src`. Read-only references; no file in scene is changed.

Direct references:

| Module | Purpose |
| --- | --- |
| `coords.ts` | `PITCH`, `toScene`, `Frame`, `sampleAt`, `pose`, `facingDirection` |
| `pitch.ts` | `createStage`, grass and lines |
| `actors.ts` | 22 capsules, the ball, `applyPose` |
| `colors.ts` | flat HOME / AWAY colours |
| `decisions.ts` | `Decision`, `probabilities`, `primary_pass`, `carry`, `loadDecisions`, `decisionAt`, `topAction` |
| `hud.ts` | clock text, clip filename validation |

The `/sample` mapping to the same sample directory in `vite.config.ts` is copied into board's own config. The default clip is still `clip.jsonl` (25 Hz, about 30 seconds). `decisions.json` goes in `touchline/board/public/decisions.json`, and its content is the decision-core output that `python scripts/export_decisions.py` writes.

`main.ts` is not referenced. That is the sample shell with a fixed camera and time driven only by `requestAnimationFrame`.

`overlay.ts` and `panel.ts` are not referenced. The ribbon drawing is written fresh in board as `ink.ts`: a flat band on the grass, arrows, pass yellow `0xffe500`, carry cyan `0x3ad6ff`. Scene's overlay only understands decision objects, swaps them out as a whole by `event_id`, and has no shots and no coach fields.

## 2. One screen

The whole page is one canvas with the pitch filling it. Four controls are layered on top, all switching within the same page, with no separate app.

The **tool rail** is on the left, one of four: pass, carry, shot, formation. The first three are annotation modes. Formation is a placing-players mode. During playback the tool rail is still there, but raycast picking is turned off.

The **ghost layer** is one pale route on the pitch plus a small label (the action class and that class's probability). It appears only while paused and only when the current time matches a decision.

**Camera** is top right, two buttons, with wording taken from scene: Broadcast, Top-down. Shortcuts `1` / `b`, `2` / `t`. Broadcast is the existing perspective camera (field of view 28°, position about `(-6, 9.5, 46)`, looking at `(14, 1.2, 0)`). Top-down is the existing orthographic camera, covering 105×68 from above.

Orbit exists only for setting the formation. On entering formation mode, `OrbitControls` is attached to the broadcast perspective camera, with the target at the centre circle and the polar angle limited to above the turf. In top-down, orbit is detached: a god view with a ground raycast is enough to drag players. On leaving formation mode the controls are detached and the view returns to the broadcast or top-down it was in before entering. Annotation and rollouts do not use a third camera.

The **transport bar** is at the bottom: play, pause, time bar. Space toggles pause, same as scene. The time bar drags by `t_ms` and, on release, stops on that frame, with the picture interpolated between adjacent frames by `sampleAt`. A rollout pauses at the end of the clip and does not loop.

The three uses are modes:

- Rollout: the transport bar plays the clip already loaded. Capsules follow the clip, and the page does not control the players.
- Annotate: paused. Pass, carry and shot write into the ink list.
- Formation: paused. Dragging capsules changes `x, y`.

During playback both annotation and dragging are disabled. Ink already written stays on the pitch, following world coordinates and not disappearing with a particular frame.

## 3. How each tool is used

Picking uses raycasts. Click a capsule to pick a player, click the grass to pick a ground point. Scene has no such layer; board adds its own.

Coordinates are always written back as centre-circle metres. While drawing, go through `toScene`.

### Pass

Select pass, playback pauses.

First click player A, and a ring appears at his feet. Then click player B. A to B immediately becomes committed ink: a solid yellow band with a filled arrow.

The coach then supplies two fields, which the model does not produce:

- Style `style`: `ground` on the grass, `lofted` in the air, `driven` low and flat. Ground hugs the grass; lofted arches the band on three.js Y while the planar endpoints stay at A and B; driven is slightly wider than ground.
- Curvature `curve`: `straight`, `inside` for an inward curve, `outside` for an outward curve. The inward curve offsets the midpoint 4 metres to the left of the path, the outward curve 4 metres to the right. This is chalk bend, not ball physics.

### Carry

Select carry, playback pauses.

Click the ball carrier, drag out a direction on the grass, and release to write the ink. Geometrically it is a two-point arrow. The colour is carry cyan, keeping scene's dashes (solid segment 1.7 metres, gap 1.0 metres) and adding a filled arrow. Scene's carry band has no arrowhead, and the coach board needs direction.

No style and no curvature.

### Shot

Select shot, playback pauses.

Click the shooter, drag out a direction on the grass, and release to write the ink. The colour is `0xff8a3d`, a solid band with a filled arrow, kept separate from the yellow and the cyan.

The angle `angle_deg` is computed by the page: the signed angle from the ray pointing from that player to the goal centre `(attack_dir × 52.5, 0)` to the arrow that was drawn, positive towards data +y. `attack_dir` uses this frame's value, where +1 means HOME attacks +x.

Style `style` is a coach field: `placed` for a placed shot, `driven` for a driven shot, `chip` for a chip. It is `null` until chosen.

### Formation

Select formation, playback pauses, and orbit is attached to the perspective camera.

Drag a capsule and the ray lands on the grass, changing that player's `x, y`. v1 does not change `facing` and does not drag the ball. All 22 players can move.

The pose after dragging stays in memory, with the fields still `player_id`, `team_id`, `x`, `y`, `facing`. It is not written back into the jsonl being played. Pressing play again returns the picture to positions from the loaded clip; re-entering formation mode reapplies the working pose from memory.

A rollout only plays a clip that has already been generated. The clip may be the sample, or a new jsonl the generator wrote after starting from this pose. The page offers clip loading. The page does not generate clips, and does not make decisions for the players during playback.

### Ghost

Appears while paused, with the same semantics as Cursor completion: a suggestion, not yet ink.

Take one class with `topAction(probabilities)`. Labels match the model: `pass`, `shoot`, `dribble`, `hold`. The interface calls `dribble` carry and `shoot` shot. Tie-breaking is the same as `decisions.ts`: replace only on strictly greater, in the order pass, shoot, dribble, hold.

Only one route is drawn:

| Action | Where the route comes from |
| --- | --- |
| `pass` | Only `primary_pass` (`target_id`, `path`, `score`). `secondary_pass` is not drawn. |
| `dribble` | Uses `carry.path`, drawn as a direction. |
| `shoot` | The decision object has no shot path. Draw a straight line from `player_id`'s current position to the goal centre `(attack_dir × 52.5, 0)`, and mark it `derived: true`. |
| `hold` | Label only, no route. |

No ghost curvature and no ghost shot style. A pass ghost carries no `style` and no `curve` either.

Accept: while paused, and when this ghost has a route, press `Tab` or click that pale band. `Esc` discards the current ghost until `t_ms` changes again. `Tab` on `hold` writes no ink.

After accepting, one piece of ink is written, then the ghost is hidden until the time changes.

- Pass: `from_id` from the decision's `player_id`, `to_id` and `path` from `primary_pass`. `style` is written as `ground` first and `curve` as `straight` first, and the coach can change them.
- Carry: `path` from `carry.path`.
- Shot: `path` from that derived straight line, `angle_deg` written from the angle above, `style` left `null` until the coach chooses.

Appearance is kept distinct from committed ink:

- Ghost: opacity about 0.28, always dashed, hollow arrow, greyed colour, and the label shows the action name and that class's probability (for example `shoot 31%`).
- Ink: opacity about 0.95. Pass solid with a filled arrow, carry dashed with a filled arrow, shot solid with a filled arrow. Style and curvature are expressed only in ink.

The ghost is not shown during playback. Committed ink stays. While paused, choosing a decision does not use scene's 8-second limit: the coach has stopped on this frame, so it shows the nearest decision that matches this frame. Call `decisionAt(set, tMs, Number.POSITIVE_INFINITY)`. Since no ghost is drawn during playback, the 8-second rule is not needed on this board.

## 4. The data needed while paused on a frame

What follows is the document the page holds while stopped on a frame. Players and the ball come from the interpolated pose of the clip; the ghost comes from the matching `Decision` in the static `decisions.json`; ink comes from this page's session.

Names follow the fields the decision core already emits where possible: `probabilities`, `primary_pass`, `carry`, plus `target_id`, `path`, `score`. Do not rename `dribble` to carry and put it into the probabilities. The four probability keys are exactly `pass`, `shoot`, `dribble`, `hold`.

```json
{
  "schema": "coach-frame/1",
  "origin": "centre_spot",
  "pitch_m": { "length": 105, "width": 68 },
  "t_ms": 14360,
  "frame_id": 359,
  "attack_dir": 1,
  "pose_source": "clip",
  "players": [
    { "player_id": "H10", "team_id": "HOME", "x": 8.556, "y": 3.839, "facing": 1.2 }
  ],
  "ball": { "x": 8.5, "y": 3.7, "z": 0.2 },
  "ghost": {
    "event_id": "e000005",
    "t_ms": 14360,
    "frame_id": 359,
    "team_id": "HOME",
    "player_id": "H10",
    "probabilities": {
      "pass": 0.218,
      "shoot": 0.311,
      "dribble": 0.216,
      "hold": 0.254
    },
    "action": "shoot",
    "primary_pass": null,
    "carry": null,
    "shot": {
      "derived": true,
      "path": [[8.556, 3.839], [52.5, 0.0]]
    }
  },
  "ink": [
    {
      "id": "ink-1",
      "tool": "pass",
      "from_id": "H10",
      "to_id": "H09",
      "path": [[8.556, 3.839], [18.229, 23.11]],
      "style": "ground",
      "curve": "straight",
      "source": "ghost"
    },
    {
      "id": "ink-2",
      "tool": "carry",
      "from_id": "H10",
      "path": [[8.556, 3.839], [17.899, 9.646]],
      "source": "coach"
    },
    {
      "id": "ink-3",
      "tool": "shot",
      "from_id": "H10",
      "path": [[8.556, 3.839], [40.0, 2.0]],
      "angle_deg": 12.4,
      "style": null,
      "source": "coach"
    }
  ]
}
```

In the document, `players` lists all 22 players. The example above keeps only one. `x, y` are centre-circle metres, `facing` is radians with 0 towards +x. The `vx, vy` from the clip line are not needed for this frame's picture, and v1 does not put them into this document.

When `pose_source` is `clip`, player positions come from the clip. After the formation has been dragged, it changes to `formation`.

`ghost.action` uses the model labels. For `pass`, fill `primary_pass`, with the same shape as the decision core: `{ "target_id", "path", "score" }`. For `dribble`, fill `carry`, with the same three fields, where `target_id` is usually the ball carrier himself. For `shoot`, fill only `shot`, with `derived` true. For `hold`, all three routes are null.

`path` is `[[x, y], ...]` in metres, the same as the paths in `public/decisions.json`.

`ink[].source` is `ghost` or `coach`, so that it is later possible to tell which stroke accepted a completion and which was hand-drawn. `style` and `curve` appear only on strokes the coach can set. A shot's `style` may be null.

In v1 the ghost's source is a static file: `loadDecisions("/decisions.json")`, whose set shape is the existing `DecisionSet` (`schema_version`, `match_id`, `frame_hz`, `origin`, `decision_count`, `decisions`).

The seam for later: swap in a local Python call. The request body is this frame's `players`, `ball`, `t_ms`, `attack_dir`. The response is still one `Decision` (`probabilities`, `primary_pass`, `secondary_pass`, `carry`). The page only swaps the loader function. Until the decision core writes a shot path, the shot ghost keeps being derived from the goal centre. This step needs no Azure. The static file still serves as an offline fallback.

## 5. Where the existing scene falls short

`touchline/scene` can play the sample, switch between two fixed cameras, and draw decisions as chalk. The coach board also needs these things it does not have:

- No raycasts. You cannot pick a player, or pick the grass.
- No dragging. `applyPose` overwrites capsule positions from the clip every frame.
- No time bar. Time only advances inside `requestAnimationFrame`, or starts from a `?t=` in the address bar. Space can only pause.
- The cameras are two hard-coded ones. No orbit.
- `decisions.json` is fetched once at startup and is not recomputed for the current pose.
- `decisionAt` returns null once past 8 seconds by default, and overlay clears the picture. When paused on a frame to study it, that rule makes the suggestion vanish.
- overlay draws only `primary_pass`, `secondary_pass` and a dashed `carry`; no shots, no style, no curvature, and no two layers of "pale suggestion / solid ink".

The sample shell keeps serving its original demo. These gaps are filled in `touchline/board`, without going back to change scene.

## 6. Build order

Step one is to make something watchable. Stand up `touchline/board`, port 5175, referencing the pitch, capsules and coordinates, playing `clip.jsonl`. Broadcast and top-down can be switched. The transport bar can play, pause and drag. No ink, no formation. This step is done when 22 capsules and the ball are visible and 5173 and 5174 still belong to the two original apps.

Step two is the paused ghost. Load the static `decisions.json`. While paused, draw one action class and one route. `Tab` or a click writes ink; during playback the ghost is hidden and the ink stays. The shot route is the straight line to the goal centre, with style left empty. This step can already demonstrate "complete, then commit". Curvature controls and shot style controls can come later; a pass defaults to `ground` / `straight` first.

Step three is hand drawing and formation. Add raycasts: pass as two points, carry as a direction, shot as direction and angle, style and curvature. The formation can be dragged, and orbit is attached only then. Loading another jsonl plays a rollout the generator wrote afterwards. The generator is not called in the browser.

## 7. Non-goals

- Do not delete or replace the league home page and `touchline/scene`.
- Do not design a league home page, a squad page or a post-match written report.
- Do not take port 5173, and do not change 5174.
- Do not load the top-left origin, 5 Hz league tracking.
- v1 does not connect to Azure and does not require a separate service just for the ghost.
- The ghost contains no curvature, no pass style, no shot style, and does not draw `secondary_pass`.
- The page does not generate rollout clips, and does not control players during playback.
- No club name or player name is printed on the capsules. The sample page does not print them now either.
