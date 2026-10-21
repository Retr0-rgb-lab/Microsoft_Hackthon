# SysModel v1 model selection

Product decision for the on-ball model. The softmax stays the decision. Video and CV are not the v1 input. This note is the contract Backend and narration can build on.

## Decision

Four-class linear softmax: **pass**, **shoot**, **dribble**, **hold**.

Checked-in weights are `src/inside_the_game/system1/weights.json`, fit only on synthetic `decision_point` events from match `SYN-SINGLE-0001` (`touchline/data/samples/sample_25hz_10min/`). The fit does not read StatsBomb, a real-club feed, or any paid API.

```bash
python scripts/train_softmax.py
```

Labels come from the chosen option on that decision, not from a later pass or shot event:

| Chosen option | Softmax label |
| --- | --- |
| `pass` | pass |
| `shot` | shoot |
| `carry` with `progress_m` ≥ 4, or with the nearest opponent beyond 3 m | dribble |
| `carry` with `progress_m` < 4 and the nearest opponent within 3 m | hold |

The sample's own pressure events use a 3 m radius. A short carry inside that radius keeps the ball with the same player, which is the hold class. The decision stream has no hold type of its own.

`SoftmaxActionPolicy.predict` is unchanged for `MatchEvent`. The tracking entry point is `predict_tracking(frame, decision_point, team_of)`.

## Inputs

SynthData tracking frames plus `decision_point` events. Pitch geometry, fixed by the sample format:

- origin at the centre spot
- metres
- pitch 105 × 68
- `attack_dir` is +1 or −1 on every frame (+1 means HOME attacks toward +x; AWAY is the opposite)

Consumption follows FORMAT section 6 (copied next to the slice):

```python
frame = frames[round(event["available_at_ms"] * frame_hz / 1000)]
d = frame["attack_dir"] if event["team_id"] == "HOME" else -frame["attack_dir"]
```

`d` is the flip that makes the acting team attack toward +x. Player `(x, y, vx, vy)` is multiplied by `d`. Facing is `atan2(sin(facing) * d, cos(facing) * d)`. Only events with `available_at_ms` at or before the decision are legal inputs. The implementation reads that one frame and that one decision.

The six softmax features are still `ball_x`, `ball_y`, `centrality`, `pressure`, `minute`, `goal_diff`, with `ball_x` = 0 at the acting team's own goal and 1 at the goal they are attacking.

## Output

The decision object does not replace the four probabilities. It adds the geometry the pitch already expected:

- `probabilities`: pass, shoot, dribble, hold, summing to 1
- `primary_pass` and `secondary_pass`
- `carry`

Pass targets and the carry are pitch metres in the **centre-spot** frame (not the attack-flipped frame), each:

```json
{"target_id": "H08", "path": [[8.556, 3.839], [20.1, 1.2]], "score": 0.042}
```

The softmax chooses the class. It does not choose the receiver. Pass targets are the decision's own pass options with `offside: false`, ranked by the completion score. The carry `target_id` is the player on the ball, because a carry option has no receiver. The path is a polyline from that player to the carry end.

## Completion scoring

**Pitch control × xT**, in numpy, no paid API. One decision scores the candidate ends and is under 50 ms.

- Pitch control at a point is that team's share of Gaussian player influence (σ = 7 m), with a small reduction in effective distance when a player is running toward the point.
- xT is a static surface on the attack-flipped plane: it rises toward the attacked goal, rises toward the centre, and has a floor inside the penalty box (16.5 m from the goal line, half-width 20.16 m). It is not a transition matrix fit on a real match.
- The score is the product of those two numbers at the end of the path.

Code: `inside_the_game.system1.completion`. The `score-completion` tool recomputes the same product for the paths `decide` already chose.

## Narration

**Azure AI Foundry, deployment `gpt-4o-mini`** (the budget deployment).

The request is structured JSON only: the four probabilities, the two pass targets, and the carry path. No tracking dump, no video, no match prose. `inside_the_game.system2.foundry.foundry_narration_request` builds that body and sets `sent` to false. This package does not call Foundry.

## Agent Framework

The Microsoft Agent Framework run orchestrates four tools, in this order:

| Tool | Role |
| --- | --- |
| `read-frame` | Tracking frame at `available_at_ms`. No later event. |
| `decide` | Softmax probabilities, primary and secondary passes, carry path. |
| `score-completion` | Pitch-control × xT on those ends. No paid API. |
| `narrate` | Foundry `gpt-4o-mini` request from the decision JSON. Not sent here. |

`inside_the_game.system1.orchestrator.run_decision_tools` is that order in-process, so the tool boundary is testable without the hosted framework.

## Sample

The clip is `touchline/data/samples/sample_25hz_10min/` (15,001 frames at 25 Hz). Field definitions and the section 6 read pattern are in `touchline/scripts/synth/FORMAT.md`. How to regenerate the clip is in `touchline/data/samples/README.md`. The loader indexes frames by `frame_id`, which is `round(available_at_ms * frame_hz / 1000)`.

## StatsBomb fixtures

v1 weights do not read `fixtures/statsbomb/`. The open-data mapping tests still import that directory. Backend can remove `fixtures/statsbomb/` after this lands, once those mapping tests are dropped or pointed at a synthetic event stream. Do not refit the softmax on that tree.
