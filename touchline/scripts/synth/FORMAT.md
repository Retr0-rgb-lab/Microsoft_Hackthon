# Synthetic football data format v0.1 (draft)

Generator: `generate.py` (single-match mode, standard library only) · Validation: `validate.py` · Schema: `schema.json` (JSON Schema 2020-12)

All teams, players and venues are fictional. `validate.py` scans whole words against `forbidden_terms.txt` (650 entries: real clubs, stadiums, leagues, brands and real player names), and any hit fails validation.

## 1. Coordinate system (fixed)

| Item | Convention |
|---|---|
| Origin | Centre spot (the kick-off point at the centre of the centre circle) |
| Units | metres; velocity m/s; time ms; angles radians |
| Pitch | 105 × 68 |
| x | along the long side, range [-52.5, 52.5]; the two goal centres are at (±52.5, 0), goal width 7.32 |
| y | along the wide side, range [-34, 34]; together with x and z it forms a right-handed frame (+x to the right and +y upwards when viewed from above) |
| z | up, ground = 0 |
| facing | radians, value in (-π, π]; 0 means facing +x, counter-clockwise positive (π/2 faces +y) |
| attack_dir | present on every frame. +1 means **HOME** attacks toward +x on that frame, -1 means toward -x; the away team's direction is always the opposite. v0.1: +1 in the first half, -1 in the second |
| frame_hz | written in the metadata, default 25, minimum 10 (`--hz`) |

## 2. Files

| File | Content |
|---|---|
| `metadata.json` | match metadata: frame_hz, duration_ms, frame_count, coordinate_system, periods, teams, players, columns, limitations |
| `tracking.jsonl` | one frame per line, `duration_ms/1000*frame_hz + 1` lines in total |
| `events.jsonl` | event stream, monotonically increasing by `available_at_ms`, with `sequence` consecutive from 1 |
| `states.jsonl` | one score and running-stat snapshot per second |
| `summary.json` | summary (final score, event counts, distance run, and so on) |
| `validation_report.json` | `validate.py` output |

## 3. tracking frames

| Field | Type | Description |
|---|---|---|
| frame_id | int | consecutive from 0 |
| t_ms | int | `round(frame_id*1000/frame_hz)` |
| period, period_ms | int | half number and time within the half (50 minutes per half) |
| attack_dir | +1/-1 | see the coordinate system |
| in_play | bool | false during a dead ball (the stage of preparing to restart) |
| phase | enum | carry / pass / shot / restart_setup / ended |
| action_id | str | the current action |
| possession_team_id | HOME/AWAY/null | |
| ball_owner_id | str/null | the ball carrier; when this is non-empty the ball is within ≤0.6 m of him |
| score | [home, away] | |
| players | 22 × `[player_id, x, y, vx, vy, facing]` | column definitions in `metadata.columns` |
| ball | `[x, y, z, vx, vy, vz]` | at the instant it goes out the ball may cross the line, by at most 3 m |

## 4. Events

Common fields: `event_id, sequence, match_id, type, period, period_ms, start_ms, end_ms, available_at_ms, possession_id`, optionally `team_id, related_event_ids`. All `*location` fields are `[x, y]`, using the coordinate system above.

| type | Key fields |
|---|---|
| decision_point | `player_id, location, xt_start, options[], chosen_index, chosen_option_id, policy`. Emitted at every on-ball decision (`available_at_ms` equals the `start_ms` of the action that follows) |
| ↳ option | `option_id, type(pass/carry/shot), target_player_id, end_location, success_prob, progress_m (progression distance toward the attacking direction), xt_end, xt_gain, offside, offside_margin_m` |
| pass | `player_id, recipient_id` (the intended receiver), **`actual_receiver_id`** (who actually received it: an opponent when it is intercepted, null when it goes out of play), `outcome` (complete / intercepted / out / offside), `under_pressure, pass_height, start_location, end_location, decision_event_id` |
| carry | `player_id, start_location, end_location, decision_event_id` (the first carry after a restart has no decision point) |
| shot | `outcome` (goal / saved / off_target), `xg, score` |
| offside | `player_id` (the offside player), `location` (position at the instant of the pass), `offside_margin_m, pass_event_id`; followed by a stoppage and an indirect_free_kick |
| ball_out | `line` (touchline / goal_line), `location, last_touch_team_id, next_restart` (throw_in / corner / goal_kick), `restart_team_id` |
| restart | `restart_type` (kick_off / throw_in / corner / goal_kick / indirect_free_kick / keeper_restart), `player_id` |
| other | possession_change, interception, pressure (a distance label within 3 m), save, stoppage, action_cancelled, period_start/end, match_end |

Offside rule (a simplified Law 11): a receiver is offside at the instant of the pass when all three of the following hold — he is in the opponent's half, he is further forward than the ball, and he is further forward than the second-last opponent. In attacking-direction coordinates: `X_att > max(second-last defender, ball, 0)`.

Recovery after the ball goes out: crossing the touchline gives the opponent a throw-in; crossing the goal line gives a corner if the defending side touched it last, and a goal kick otherwise.

## 5. Read example: front end (three.js)

```js
import * as THREE from 'three';
const meta = await (await fetch('sample/metadata.json')).json();
const frames = (await (await fetch('sample/tracking.jsonl')).text())
  .trim().split('\n').map(JSON.parse);          // for large files parse incrementally in a Worker
// data frame (x along the length, y across the width, z up) -> three.js (Y up): X=x, Y=z, Z=-y
const toScene = (x, y, z = 0) => new THREE.Vector3(x, z, -y);
const meshes = {};                               // player_id -> Mesh, created up front: 22 players + 1 ball
function render(tMs) {
  const k = tMs * meta.frame_hz / 1000, i = Math.floor(k), a = k - i;
  const f0 = frames[i], f1 = frames[Math.min(i + 1, frames.length - 1)];
  f0.players.forEach(([id, x, y, vx, vy, facing], j) => {
    const [, x1, y1] = f1.players[j];
    meshes[id].position.copy(toScene(x + (x1 - x) * a, y + (y1 - y) * a));
    meshes[id].rotation.y = facing;              // about Y; data 0 = +x, counter-clockwise positive, preserved by the mapping
  });
  const [bx, by, bz] = f0.ball;
  meshes.ball.position.copy(toScene(bx, by, bz + 0.11));
  // home attacking arrow: f0.attack_dir (+1 means home attacks +x)
}
```

## 6. Read example: SysModel (Python)

```python
import json, math
from pathlib import Path
root = Path('sample_25hz_10min')
meta = json.loads((root/'metadata.json').read_text())
hz = meta['frame_hz']
frames = [json.loads(l) for l in open(root/'tracking.jsonl')]
events = [json.loads(l) for l in open(root/'events.jsonl')]
team_of = {p['player_id']: p['team_id'] for p in meta['players']}

# each decision point is one training sample: (current frame state, candidate set, chosen action)
for e in (e for e in events if e['type'] == 'decision_point'):
    f = frames[round(e['available_at_ms'] * hz / 1000)]
    d = f['attack_dir'] if e['team_id'] == 'HOME' else -f['attack_dir']   # normalise to "attacking +x"
    state = [(pid, x*d, y*d, vx*d, vy*d, math.atan2(math.sin(fa)*d, math.cos(fa)*d))
             for pid, x, y, vx, vy, fa in f['players']]
    options = [(o['type'], o['target_player_id'], o['success_prob'], o['xt_gain'], o['offside'])
               for o in e['options']]
    label = e['chosen_index']
```
Note: use only events with `available_at_ms ≤ current time`, to avoid leaking future information.

## 7. Known limitations of v0.1
- There is only one formation (4-3-3). The player speed cap is 7.2 m/s, which is low. Ball height is a parabola, with no bounce and no air resistance.
- There are no tackles, dribble duels, fouls or cards, and pressure is only a distance label.
- Throw-ins and corners restart 1.5 m inside the pitch (limited by the braking model when a player approaches the touchline).
- Offside is judged only at the instant of the pass, without details such as "interfering with play".
- Newly generated matches write `value_v1` in `decision_point.policy` (select by option value, no longer drawing with `heuristic_v0`). xT and xG are still the same analytic formulas. The already-stored seed 8 slice keeps `heuristic_v0`.
