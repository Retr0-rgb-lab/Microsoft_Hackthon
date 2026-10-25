# Coach board ghost v1: a four-class distribution, plus one route

While paused on the three-dimensional pitch, the ghost delivers two things under `ghost_simple`. The first is a distribution over the four classes pass, shot, carry and hold; all four are shown, and the class with the highest probability is not called optimal. The second is one route: a pass receiver, or a carry's direction and endpoint, or a shot's direction. Pass curvature, ground or lofted, and shot technique are the coach's annotations on that straight line; the model does not predict them.

This document defines only this model. It changes no code, trains nothing, downloads no weights and calls no Azure.

## 1. Problems with the existing model relative to ghost_simple

The checks came out as follows.

`fit_on` in `src/inside_the_game/system1/weights.json` is `synthdata:SYN-SINGLE-0001:decision_point`, and the sample directory is `touchline/data/samples/sample_25hz_10min`. `training.counts` is pass 73, dribble 41, hold 8, shoot 2, 124 rows in total. `scripts/train_softmax.py` reads only that match. There is no held-out match. The `policy` on every event is `heuristic_v0`. The score stays `[0, 0]` throughout those 10 minutes.

The six features are `ball_x`, `ball_y`, `centrality`, `pressure`, `minute`, `goal_diff`. The `goal_diff` weight is `0.0` for all four classes. The fit starts from 0, this column is constant 0 in the sample, so the gradient is 0 and L2 cannot move it either. `centrality` is uniquely determined by `ball_y`. `pressure` squashes the nearest opponent's distance into 0.18 to 0.82: saturating at 0.82 within 3 metres and at 0.18 beyond 12 metres. `minute` is then divided by 90, and this match only reaches minute 10.

`fit_softmax` turns on class weights. A class's weight is `rows / (4 × rows of that class)`. The shot row is `124 / 8 = 15.5`, and the pass row about `0.42`. The two shot samples are pulling the shot plane.

The label rule is written in `label_rule` in `weights.json` and implemented by `label_decision_point`. A selected pass or shot is recorded as pass or shoot. A selected carry with `progress_m < 4` and the nearest opponent no more than 3 metres away is recorded as hold, otherwise as dribble. The generator has no hold option; hold is a rename applied after the fact to a short carry.

`choose_action` in `touchline/scripts/synth/generate.py` draws like this. The goalkeeper (`number == 1`) enters only the pass branch. For anyone else: when the progression `progress0 > 78` and `|y − 34| < 24`, a shot is chosen with probability `0.06`; otherwise a carry is chosen with probability `0.36`; failing that, a pass is drawn weighted by distance, forward progression, success probability and offside. The 124 rows of labels imitate this draw.

The distribution does not choose the route. `decide_from_tracking` yields `primary_pass`, `secondary_pass` and `carry` together. The pass target comes from the passes with `offside` false among that decision's options, ranked by possession control × xT from `completion.py`. The softmax takes no part. The decision object has no shot direction. The scene draws the pass line and the carry line together. `touchline/scene/src/panel.ts` uses `topAction` to mark the class with the highest probability as `top`.

So the existing model is: position features on one synthetic match, imitating one draw of 0.06 / 0.36 / the remaining passes, and then laying out the pass and carry geometry at the same time. It has no single ghost route, and no four-class probability read purely as a distribution.

## 2. v1 architecture

Only the four-class distribution is learned. Routes still use analytic ranking, and route scores are not learned.

The learned part stays the same model family as now: linear softmax, full-batch gradient, L2, standard library, local CPU. The current `weights.json` fit is this order of magnitude. Once the labels are replaced with the value labels of the next section, a few thousand rows, eight features and a few hundred steps should still land in seconds to minutes. If it runs past a few minutes, cut steps or cut features; do not change model family. The output is four class probabilities summing to 1. The weights file does not record a winning class.

Scores on candidate routes are not learned. Of the 124 rows only 2 are shots. A route model would have to pick out a positive sample among the dozen or so candidates at each decision, and the shot line has no recognisable positive samples. `completion_value` already scores a handful of endpoints analytically within a single decision, with a target under 50 milliseconds and no paid API calls.

A route is chosen by analytic score, not by the class with the highest probability.

- Candidates and labels use the same eligibility: passes with `offside` false, the carry option, the shot option. When the goalkeeper has no carry and no shot, the only candidates are passes.
- Pass endpoints and carry endpoints call the existing `completion_value` (possession control × static xT). The path is a straight line from start to end. The carry's `target_id` is still the ball carrier.
- A shot does not send the goal centre into possession control. The goalkeeper stands in the goal mouth, and control would push every shot to last place. The shot score equals the option's existing `success_prob` (the xG written by the generator) multiplied by the value of static xT at the goal centre, with no possession control. Under the box formula of `expected_threat`, the xT at the goal-line centre (`x = 52.5`, `y = 0`) in the attacking coordinate frame is `0.25 + 0.55 = 0.80`. A shot with xG 0.30 scores 0.24, and one with xG 0.02 scores 0.016. This 0.80 comes from the existing surface and is not trained separately.
- The three kinds of candidate go into one sequence and the largest is taken, and only that one is drawn. A pass is drawn to the receiver, a carry to its endpoint, a shot as a straight line from the ball in the direction of the goal.
- When the label class is hold, no line is drawn. The hold share of the distribution is still displayed.

The distribution answers "which class the value label falls into". The route answers "under the declared analytic score, which option ranks first". Both are shown. Interface wording uses class names and percentages, never optimal, best or recommended decision. The route is not called an optimal action either; it is the first place under this declared score.

## 3. Features the learned part needs

Eight numbers, all from the frame at `available_at_ms` and from that decision's own options. The coordinate system stays centre spot, metres, 105×68; first flip the attacking direction to +x per FORMAT section 6, then normalise. No pass, shot or carry event after that moment is read.

| Feature | Algorithm |
| --- | --- |
| `ball_x` | existing definition. Own goal line is 0, opponent goal line is 1 |
| `ball_y` | existing definition, range 0 to 1 |
| `nearest_opponent_m` | the nearest opponent in metres, divided by 30, clipped to [0, 1] |
| `opponents_within_5m` | the number of opponents within 5 metres, divided by 4, clipped to [0, 1]. The generator's pressure count uses exactly 5 metres |
| `best_onside_pass_success` | the largest `success_prob` among onside passes. 0 if there are none |
| `best_onside_pass_progress_m` | the largest `progress_m` among those passes. Negative values count as 0, divided by 40, clipped to [0, 1] |
| `carry_progress_m` | the carry option's `progress_m`. Negative values count as 0, divided by 20, clipped to [0, 1]. 0 when there is no carry |
| `shot_xg` | the shot option's `success_prob`. 0 when there is no shot |

The learned head drops three columns. `centrality` is a function of `ball_y`. `minute` only covers the first ten minutes of a 90-minute scale. `goal_diff` is constant 0 on `SYN-SINGLE-0001` and all six weights are 0; the value rule does not read the score either. Until the score varies within a sample, this column stays out of the weights file.

No player identity, no 22-player velocity expansion, no image features. 124 rows cannot identify those columns. Once the matches of section 5 are in place, these eight columns are still used; if a column contributes nothing to holdout log loss, drop it rather than adding another.

## 4. Labels the data side must produce

`choose_action` changes to selecting by value. The 0.06 and 0.36 draws are deleted from the option targets. Every `decision_point` writes the fields in the table below. Training reads only these fields.

Eligibility is as in section 2: onside passes, carries, shots.

The value of each eligible option:

- Passes and carries: `value = success_prob × max(progress_m, 0)`
- Shots: `value = success_prob × shot_gain_m`, where `shot_gain_m = 20`. The metres of progression up to the goal centre are not used. A long shot's metres would outweigh the chances inside the box. 20 is a constant written into the event, not a fitted result. A shot with xG 0.30 has value 6, the same as a pass with success probability 0.75 and 8 metres of progression.

Take the option with the highest value. On a tie the higher `success_prob` wins, then `option_id` in lexicographic order. The selection process no longer calls a random number generator.

The class is determined by this winning option:

- pass → `pass`
- shot → `shoot`
- carry with `progress_m < 4` and the nearest opponent ≤ 3 metres on that frame → `hold`
- any other carry → `dribble`
- all eligible option values 0 → `hold`, with an empty route

The event contains at least: `policy` (always written as `value_v1`), `chosen_index`, `chosen_option_id`, `label_class`, `label_value`, `shot_gain_m`, `route_kind` (`pass`, `dribble`, `shoot`, an empty string for hold), `route_target_id` (the receiver for a pass, the ball carrier for a carry, empty for a shot and for hold), `route_end` (the endpoint in centre-circle coordinates; for a shot a point in the goal direction; empty for hold).

Curvature, pass `height` and the shot outcome (goal, saved, off target) are not written into the label. A match whose `policy` is still `heuristic_v0` should be refused by the training script, so that it is not mixed into the same fit as the old 124 rows.

## 5. Training and holdout

Data still comes from the v0.1 centre-spot generator in `touchline/scripts/synth/generate.py`. The league generator is out of scope. First swap in the labels of section 4, then refit from a 0 initialisation. The existing `weights.json` is not used as an initial value, and training does not continue on those 124 rows.

Start from 10 seeds, each still a 10-minute clip of the current kind. 8 matches for training, 2 whole matches held out. The held-out unit is a match. Decision points within the same attack are correlated, so splitting rows out of `SYN-SINGLE-0001` does not count as a holdout.

Shots in the current single match number only 2. While the training matches contain fewer than 30 `shoot`, and the holdout matches fewer than 15, keep adding seeds with the same generator. Until both numbers are reached the four classes can be fitted, but the shot cell is not presented to the coach as calibrated. `fit_softmax` raises an error when a class is missing, so all four classes must appear in each split.

Displayed probabilities come from an unweighted fit. Class weights lift the share of rare classes above their frequency of occurrence, and the percentages the coach sees would drift away from the proportions on the pitch. The existing file's `class_weighted: true` is kept only as a comparison run, not as the distribution on the ghost. L2 and full batch stay as they are.

Two numbers are computed over the held-out whole matches.

1. Four-class log loss, using natural logarithms, equally weighted per decision. The comparison is the training set's class frequency vector, evaluated once more on the holdout matches as a log loss. Pass line: holdout log loss ≤ 0.65, and at least 0.20 below that frequency comparison. The entropy of the current 73 / 41 / 8 / 2 frequencies is about 0.92, so a 0.20 drop requires the model to use this frame's features. Accuracy is not used as a threshold. With passes around six in ten, always predicting pass also gives about 0.59 accuracy.
2. Route agreement: the proportion of decisions where the `option_id` chosen by the analytic ranking equals `chosen_option_id`. Pass line ≥ 0.70. At least seven of every ten frozen decisions then draw the option the value label selected.

Only when both pass does this fit replace the ghost in front of the coach. If log loss passes but the route figure is below 0.70, the new fit shows only the four class shares and draws no arrow. If the route passes but log loss does not, neither the distribution nor the arrow from this fit is shown. Until they pass, the board still displays the checked-in `weights.json` offline and marks it as an uncalibrated preview, without calling the largest class optimal.

## 6. If the labels are still heuristic_v0

The distribution learns the draw. Inside the shooting zone the shot share would settle near 0.06: a rising xG would not lift it, and a better pass in view would not lower it. The carry share would settle near 0.36 (the goalkeeper aside), almost regardless of that carry's progression. The weighted randomness among pass receivers changes only the route, not the class, and the softmax cannot see the receiver.

On such labels, holdout log loss can fall below the frequency comparison while the ghost is still wrong. That only shows the model memorised the coin. The possession control × xT arrow is matched against that coin, and route agreement will not clear 0.70. Do not lower that line for the sake of the existing 124 rows.

`goal_diff` stays all 0. Class weights would keep inflating those two shots. hold would remain an after-the-fact rename of a short carry, unable to express "the eligible passes are all worth 0, so hold".

## 7. What is explicitly not done

- No Azure GPU, no managed fine-tuning, no downloading football pretrained models. Whatever fitting can be done locally stays on CPU. Subscription credit does not enter this training plan. The Foundry narration already in the repository is a separate path, and this model does not depend on it.
- Do not imitate `heuristic_v0`. Do not call the existing `weights.json` v1.
- Do not predict pass curvature, ground or lofted, or shot technique. These are coach annotations.
- Do not call the class with the highest probability optimal. All four shares are shown.
- Do not call the analytic route an optimal action. It is the first place under the score of section 2.
- Do not refit on StatsBomb, do not connect the league generator, and do not feed video or image features into this softmax.

## 8. Minimum code paths to touch later

This time only file names are listed.

Labels are in `touchline/scripts/synth/generate.py`.

Features and fitting for the distribution: `src/inside_the_game/features/extract.py`, `src/inside_the_game/features/from_tracking.py`, `src/inside_the_game/features/from_cv.py`, `src/inside_the_game/system1/fit.py`, `src/inside_the_game/system1/policy.py`, `src/inside_the_game/system1/weights.json`, `scripts/train_softmax.py`.

A route is in `src/inside_the_game/system1/tracking.py`. It keeps calling `src/inside_the_game/system1/completion.py` to score pass endpoints and carry endpoints. The shot score is computed in `tracking.py` per section 2, without sending the goal centre into possession control.

Ghost surface: `touchline/scene/src/decisions.ts`, `touchline/scene/src/overlay.ts`, `touchline/scene/src/panel.ts`. The `topAction` highlight of the largest class is removed there.

After the decision dictionary changes from `primary_pass`, `secondary_pass`, `carry` to one route, the following callers must follow the key rename: `src/inside_the_game/system1/orchestrator.py`, `src/inside_the_game/system1/agent_workflow.py`, `src/inside_the_game/system2/foundry.py`.
