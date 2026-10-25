# Coach board data v1

The free rollout is this generator. Training rows and the clip the coach watches at the time use the same output: centre-circle origin, metres, `decision_point`. The factory is still `touchline/scripts/synth/generate.py` (format 0.1.0, generator `3.0.0-draft`). No neural network is swapped in to attach labels, and Azure credit is not spent on producing data.

League files stay outside the pipeline. `touchline/generate.py` (v2.1.0) writes a different replay: origin at the top left, y downward, 5 Hz, player columns without facing, no `attack_dir`, `choose_action` kicks off or passes immediately, the event stream has no `decision_point`, and there is no candidate list carrying `success_prob`. The format's lower bound is 10 Hz, and system 1 reads centre coordinates per FORMAT section 6. Those 40 NextPlay League matches cannot serve as training rows and do not enter a rollout.

## 1. How one frame and one decision point are produced today

A match constructs `random.Random` from the seed. The 22 players start from the same 4-3-3 template `BASE`: HOME uses the template coordinates, and AWAY folds x into `105 - x`. The ball sits at internal coordinates `(52.5, 34)`, which is the centre circle in output coordinates. The kick-off lasts at least 12 seconds and puts the ball with the HOME centre forward (slot 9).

Each frame's `step` does four things: set the simulation clock to `frame / hz`; `move_players` moves the 22 players one step towards their targets; `update_ball` interpolates the ball according to the current action; and when the action expires, `finish_action`. `choose_action` is called only once a carry ends. The first carry after a restart has no decision point (`decision=None`); the decision comes after the carry.

`choose_action` first builds one pass option for each of the 10 outfield players on its own side (the goalkeeper excluded), and a ball carrier other than the goalkeeper additionally gets one carry and one shot. Each option's success probability, progression, xT and offside flag are computed at that moment. Then `heuristic_v0` draws one, writing a `decision_point` whose `available_at_ms` equals the `start_ms` of the action that follows. The outcomes of a pass, carry or shot are written to the event stream only after the action completes, so whoever reads a training row may use only events whose `available_at_ms` is no later than the current moment.

On output the internal coordinates `(x from left to right 0..105, y downward 0..68)` become the centre-circle origin: `x_out = x - 52.5`, `y_out = 34 - y`, and vy is negated. The checked-in sample `sample_25hz_10min` (seed 8, 25 Hz, 10 minutes) has 15,001 frames and 124 `decision_point`s.

## 2. What looks like football, and what makes the coach distrust it

The parts that look like football are all geometry fixed in the code, not explanations added afterwards:

- Pitch 105 × 68, a goal centre at each end, and a 7.32 goal width that enters the xG subtended angle.
- In the first half HOME attacks +x; in the second half `direction` changes sign, players walk to targets at the other end, and coordinates do not jump. A half is 50 minutes (45+5), and half-time is not simulated.
- Offside is judged at the instant of the pass: the receiver is in the opponent's half, closer to the opponent's goal than the ball, and closer to the opponent's goal than the second-last opponent. The opponent list includes the goalkeeper, and the way the second-last player is taken matches the simplification of Law 11.
- Pass success measures opponent distance along the pass segment: `pass_prob = clamp(0.95 - risk - 0.006 * max(0, length - 15), 0.05, 0.97)`; on failure the ball is mostly picked up by an opponent near the receiving point, and about 15% of the time it flies out of play along the passing direction.
- Throw-ins, corners, goal kicks, indirect free kicks and the goalkeeper taking the ball all hand the ball back to the nearest player to restart. Pressure is a distance label at 3 metres, refreshed at most once every 6 seconds for the same pair of players.

The parts that would make the coach distrust it:

- Speed caps: the ball carrier 6.5 m/s, everyone else 7.2 m/s, acceleration capped at 3.5 m/s². The ball carrier is slower than the players chasing him, so they catch him in a straight line. 7.2 m/s is below in-match sprinting, and FORMAT section 7 already notes that it is low. A player near the touchline is pulled about 1.5 metres inside by the braking model, so throw-ins and corners restart 1.5 metres inside the pitch and a player cannot reach the line.
- There is only one 4-3-3 across the whole match. Off-ball targets are the `BASE` slots, plus an overall shift of `0.35 * (ball progression - 52.5)` and a sway of `1.4 * sin(...)` in x and `1.5 * sin(...)` in y. When the team is in possession and `sin(t * 0.11 + index * 2.1) > 0.55`, the target x of the left winger, centre forward and right winger is pulled to 1.5 metres in front of the second-last opponent (and then clamped to 55..100). This is a metronome pushing up, not running that reads the timing of a pass.
- No duels, fouls or cards. On the opposing side only the two outfield players nearest the ball carrier go and stand 1.0 metre and 2.4 metres to his front side, and the ball is never knocked away during a carry. The success probability on the carry option, `clamp(0.95 - 0.12 * opponents within 5 m, 0.4, 0.95)`, is only written into the event; in `finish_action` a carry always succeeds.
- Shot outcomes ignore xG. The option's `success_prob` is the analytic xG, yet `start_shot` draws `goal / saved / off_target = 0.12 / 0.43 / 0.45` with fixed weights. The y of the shot's landing point is randomised only after the decision, so the endpoint inside the option is always the goal centre.
- xT and xG are both closed-form formulas, not transition matrices fitted on matches. xT: `0.02 + 0.40 * exp(-distance to the opponent's goal centre / 12)`, with the goal centre at 0.42. xG: a logistic in subtended angle and distance, clamped between 0.01 and 0.7. There is no extra plateau inside the box.
- What picks the action is a coin, not these numbers. When the ball carrier is not the goalkeeper, the progression coordinate is `> 78` (within 27 metres of the opponent's goal line) and `|y - 34| < 24`, the shot is chosen with probability 0.06. Otherwise a carry is chosen with probability 0.36. The remaining mass goes to passes drawn weighted at random: a preference around 17 metres, a bonus for progression, multiplied by `(0.5 + success probability)`, and offside only scales the weight down to 0.2× rather than removing it. `xt_gain` does not enter the weights. The goalkeeper has no carry or shot option, and there is no candidate for a pass back to the goalkeeper (the loop starts at slot 1). The current softmax imitates exactly this draw. The `policy` field is `heuristic_v0`.

## 3. v1 changes, in this order

The label is still "the option that was selected". First make that option defensible, then let the rollout draw that moment, then separate volume generation from the holdout set. No separate network is trained to relabel.

**(a) Select by value, dropping 0.36 / 0.06.** How candidates are generated does not change yet (pass targets are still opponents extrapolated 0.25 s ahead, and carry endpoints are still random 3–12 metres ahead with ±7 metres laterally). What changes is the selection. Offside passes take no part in the comparison. The formula follows `value_v1` in `docs/coach-board-model.md` and uses no penalty for losing the ball:

```
pass, carry:  value = success_prob * max(progress_m, 0)
shot:         value = success_prob * 20
```

20 metres is a constant written into the event. A shot with xG 0.30 has value 6, the same as a pass with success probability 0.75 and 8 metres of progression. A long shot no longer raises itself through its distance to the goal. Take the one with the highest value. On a tie the higher `success_prob` wins, then `option_id`. `policy` is written as `value_v1`. For a short carry with an opponent within 3 metres, the class is recorded as `hold`.

Immediately following this, and still part of the selection rule: carry outcomes change to follow that option's `success_prob`, and on failure possession goes to the nearest opponent within 5 metres, with a single change of possession and no physical duel. Whether a shot scores changes to use that option's xG as the probability, and when it does not score it is split into saved and off target by the current 0.43 : 0.45. That way the frequency the coach sees in a clip is the number written on the decision.

**(b) Fill in the fields the ghost route needs.** Every option already has `end_location` and `target_player_id`, but the decision point has no separate route, and the shot endpoint is always the goal centre while the real shot y is drawn only inside `start_shot`. Add the selected one to the `decision_point`:

```
route: {
  type,                  // pass | carry | shot
  target_player_id,      // pass receiver; null for carry; null for shot
  end_location,          // centre-spot origin, metres
  direction_rad          // in the output frame, from the ball toward end_location
}
```

A ghost is a polyline from the ball carrier at the moment of the decision to `end_location`, and does not need dense samples stored. A shot's `end_location` is fixed on the goal line while the options are built, and `start_shot` must fly to the same point. A pass ghost draws the selected intention; after an interception the ball may end up at someone else's feet, and the ghost is not rewritten as an interception route.

**(c) Play a few more matches locally with different seeds.** Today `match_id` is hard-coded to `SYN-SINGLE-0001`, and the command line only offers `--hz --minutes --seed --output`. In a batch, each match's `match_id` must carry its seed, otherwise the 20 directories are the same match in the index. Use seeds 1001–1020. Write output into the gitignored `touchline/scripts/synth/data/train/seed-<seed>/`. Do not regenerate the league, and do not overwrite `sample_25hz_10min` (that is the `heuristic_v0` demonstration slice, seed 8, on which the softmax has already been fitted).

**(d) Two holdout matches, which training must not read.** Seeds 9001 and 9002, with `match_id` `SYN-HOLDOUT-0001` and `SYN-HOLDOUT-0002`, in the directory `touchline/scripts/synth/data/holdout/`. Same length, same 10 Hz, same `value_v1` as the training matches. From then on `scripts/train_softmax.py` refuses when it sees these two `match_id`s, these two seeds or this path. The seed 8 slice cannot serve as a holdout. While training contains fewer than 30 shots, and the holdout fewer than 15, keep adding matches with new seeds, without adding them to the holdout directory.

After these four, only two things are done to make the formation stand up, see section 4: replace `BASE` with the 22 points the coach supplies, and anchor off-ball targets on those points. The analytic xT / xG keep their original formulas.

v1 does not simulate: fouls, yellow cards, red cards; set-piece routines for corners, free kicks and throw-ins (walls, short corners, second balls). These dead balls still work as they do today: the ball is placed at the restart point, the nearest player walks over, and then carries. Nor does it do substitutions, fatigue, injuries, formation changes mid-half, or offside details such as "interfering with play".

## 4. How the coach's 22 positions become the rollout's initial state

The coach board supplies 22 points, in the same coordinate system as FORMAT section 1: centre-circle origin, x along the length, y up. 11 players per team, in the fixed order of the current `POSITIONS`: GK, LB, LCB, RCB, RB, LCM, DM, RCM, LW, ST, RW. Each point has at least `team_id`, `player_id`, `x`, `y`.

When writing the simulator's internal coordinates, use the inverse of `out_xy` and clamp to within 0.5 metres of the boundary:

```
internal_x = x + 52.5
internal_y = 34 - y
```

The AWAY points are already on the coach board. The `105 - x` in `__init__` must not be applied again, or AWAY would overlap back into HOME's half. Initial velocity is 0. In the first half HOME faces 0 (+x) and AWAY faces π.

Changing only the coordinates of frame 0 is not enough. `target_position` reads `BASE[slot]` every frame, so within seconds players walk back to that 4-3-3. v1 replaces each slot's anchor with local coordinates in which "this team's attacking direction is +x": for HOME the local coordinates are the internal coordinates; for AWAY `local_x = 105 - internal_x`, with `local_y` unchanged. Later, when `direction == -1`, they fold back to `105 - x`, so the anchors still work when the teams swap attacking directions at half-time. The ball's 0.35 shift and the two defenders closing on the ball carrier are kept, and the sway sines can stay, with amplitudes still 1.4 metres and 1.5 metres. The formation string in `metadata` is written as `custom` when the anchors are not `BASE`.

The ball's default is still a centre-circle kick-off, taken by the HOME centre forward. If the coach designates a `ball_owner_id`, the ball is placed at that player's feet, possession is credited to his team, the action is one short carry forward, and the other 21 players stay on the given points without staging a kick-off first. Rollout length uses the existing whole-minute argument: `--minutes 1`. When shorter than 100 minutes, `clip` in the metadata is already true.

## 5. Size (laptop, CPU only)

The checked-in 10-minute, 25 Hz, seed 8 sample: 124 `decision_point`s, about 12.4 per minute. Decisions happen when a carry ends, and carry duration is uniform random over 1.6–4.8 seconds, so dropping to 10 Hz barely reduces the number of decisions. 10 Hz is the lower bound the format allows.

Measured once on this machine: `python touchline/scripts/synth/generate.py --hz 10 --minutes 1 --seed 1`, 0.35 s wall clock, 601 frames, `tracking.jsonl` 702,119 bytes (about 1.17 KB/frame), 5 decision points. The first minute contains at least 12 seconds of kick-off and two dead balls, so it has fewer decisions than steady state. Steady state is estimated from the 12.4 per minute above.

| Purpose | Matches | Per match | Rate | Seed | Decision points (approx.) | Frames | tracking |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Training | 20 | 20 minutes | 10 Hz | 1001–1020 | 4,000–6,000, centred on about 5,000 | 240,020 | about 280 MB |
| Holdout | 2 | 20 minutes | 10 Hz | 9001–9002 | about 500 | 24,002 | about 28 MB |
| The one rollout the coach watches | 1 | 1 minute | 25 Hz | that rollout's seed | fewer in the kick-off minute, on the order of 10 | 1,501 | about 2 MB |

Training plus holdout is 420 simulated minutes. Extrapolating from the measured 0.35 s per simulated minute gives roughly two to three minutes of CPU; allowing for 20 process starts and disk writes, budget 10 minutes. A one-minute 25 Hz rollout has 2.5 times the frames of 10 Hz, so about 1 second by frame count; this tier was not measured separately. Do not run a 100-minute full match at 25 Hz just to add volume, and do not touch the league generator.

## 6. Hugging Face

There is no public pretrained model that directly emits 22-player tracking plus one defendable decision, so the data factory still uses the rule simulator. The [`martinjolif` three YOLO models](https://huggingface.co/martinjolif/yolo-football-player-detection) in the repository only detect the people, the ball and pitch keypoints in the picture, and do not produce match state. TacticGen generates the ball and the 22 players' following 5.4 seconds in its paper, but the authors' repository states that the code, weights and dataset have not been released ([Jasonxu1225/TacticGen](https://github.com/Jasonxu1225/TacticGen)). GenTac is the paper page for a diffusion model of trajectories and events ([GenTac](https://huggingface.co/papers/2604.11786)); no downloadable weights were found this time. The diffusion kernel in `po03087/sra-trajectory-data` only forecasts about 4 seconds of xy over 23 points, with no pass or shot decision ([dataset card](https://huggingface.co/datasets/po03087/sra-trajectory-data)). `cemrtkn/llm-football-simulator` is an adapter on Mistral-7B that continues textual event lines, needs a GPU, and does not emit 22-player coordinates ([model card](https://huggingface.co/cemrtkn/llm-football-simulator)). Google Research Football is a reinforcement-learning environment, not a data factory that writes files in this format. None of these meet the constraint of "local, no downloads, standard library, value labels". Do not spend the 100 USD of Azure credit here; the narration model is a separate pipeline and is not responsible for producing tracking.

Sources:

- [TacticGen paper](https://arxiv.org/html/2604.18210)
- [TacticGen repository](https://github.com/Jasonxu1225/TacticGen)
- [GenTac paper page](https://huggingface.co/papers/2604.11786)
- [sra-trajectory-data](https://huggingface.co/datasets/po03087/sra-trajectory-data)
- [cemrtkn/llm-football-simulator](https://huggingface.co/cemrtkn/llm-football-simulator)
- [martinjolif/yolo-football-player-detection](https://huggingface.co/martinjolif/yolo-football-player-detection)

## 7. Files that will only change later

None of them change now.

- `touchline/scripts/synth/generate.py`: `value_v1`, carries and shots aligned with their probabilities, `route`, `match_id` generated from the seed, the 22-point anchors, a batch-callable entry point.
- `touchline/scripts/synth/FORMAT.md`: `route`, `policy: value_v1`, `formation: custom`.
- `touchline/scripts/synth/schema.json`: `route` on the decision point, and `value_v1` added to `policy` if it is enumerated.
- `touchline/scripts/synth/validate.py`: the selected option is the one with the highest value; `route` agrees with that option; a shot's flight endpoint agrees with `route.end_location`.
- `scripts/train_softmax.py`: read several matches under `touchline/scripts/synth/data/train/`; reject `SYN-HOLDOUT-0001`.
- `src/inside_the_game/features/from_tracking.py`: labels still come from the selected option; the ghost polyline can be read from `route`.
- `src/inside_the_game/system1/weights.json`: fitted after the new labels are generated. Until then the current weights keep standing for `heuristic_v0`.
- `touchline/data/samples/README.md`: state that the seed 8 slice is a demonstration of the old policy and that new training rows live in the gitignored `touchline/scripts/synth/data/`.
- Tests that lock the old decision counts or `heuristic_v0`, mainly `tests/test_from_tracking.py`. The 30-second `clip.jsonl` used by the scene player stays untouched until the slice is replaced.

Do not change `touchline/generate.py`, do not change `touchline/data/league/`, do not change the YOLO weights path, and do not call Foundry anywhere in this pipeline.
