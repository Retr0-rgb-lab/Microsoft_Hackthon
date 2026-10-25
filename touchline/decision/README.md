# Decision Coach research baseline

Run `python3 server.py` at the repository root; open http://127.0.0.1:5173/coach.html.
No new packages or model credentials are required. Choose a preview moment, analyze,
select a legal pass, simulate, choose a scenario and play the hypothetical sequence.
Changing match, snapshot, audience or pass invalidates associated results. Export
includes the source snapshot, computed evidence, parameters and rollout assumptions.

## What is implemented

- Snapshot-only candidate ground-pass evaluation, interception margins and offside
  check at release (not at the destination).
- Expected spatial utility gain, with explicit success and turnover branches.
- Four deterministic counterfactual cases: 0.1/0.3/0.65 second defender reactions,
  and a 1.5 m lateral pass error at the baseline reaction time.
- 50 ms motion steps, 4 second maximum horizon, bounded player speed/acceleration,
  first-touch termination, 2D playback and separate hypothesis timeline.
- `POST /api/decision`: `{frame, metadata, mode: "fan" | "analyst"}`.
- `POST /api/rollout`: `{frame, metadata, action_id}`. Offside passes rejected.

Metadata needs `players: [{player_id, team_id}]`; a frame has period, t_ms, in_play,
ball_owner_id, and players `[id, x, y, vx, vy]`, in metres and metres/second.
The UI uses the existing synthetic preview files. An authorized real tracking-data
adapter may supply this contract later; the engine does not need future frames.

## Scientific basis versus implementation assumptions

un-xPass (Robberechts et al., KDD 2023), section 2.1, motivates expectation over
outcomes and the pre/post state-value difference:
https://people.cs.kuleuven.be/~pieter.robberechts/repo/robberechts-kdd23-unxpass.pdf

Pitch-control and EPV educational reference:
https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking

We do not bundle their trained models or claim to reproduce their results. Spatial
utility, arrival-time approximations and sigmoid coefficients are hand-defined.
Scores are not calibrated success probabilities, xG, VAEP or trained xT.
Scenario counts are not outcome probabilities. Rollouts do not update the static
pass ranking; they expose sensitivity and may disagree with its simplified model.

No full match engine, heading/chip trajectories, collisions, tackle skill, body
orientation, foot preference, goalkeeper behavior or subsequent actions are modeled.
Velocity is capped by the rollout model; input speeds above its 7.2 m/s limit are
normalized on movement. Boundaries use geometric clamping. Arrival estimates for
choosing defender intercept points ignore acceleration; playback itself limits it.
“Received” means first model contact, not a professionally validated successful pass.
The baseline review is deterministic. Optional live model agents now run through `/api/agent-review`; they are never substituted with deterministic prose and labeled as live.

## Remaining development

1. Fit/calibrate feasibility and state value on separate matches; compare nearest
   teammate and forward-pass baselines, test feature ablations and uncertainty.
2. Add ball ownership transitions, dribbling/shooting and defensive action candidates.
3. Add sourced or explicitly synthetic player profiles; unknown is not zero ability.
4. Expose evaluation and rollout as tools for attack/defense/evidence agents using
   a real provider, bounded handoffs, failure recovery and source references.
5. Compare single-agent and multi-agent factual accuracy, latency and cost before
   claiming orchestration improves the outcome.
6. Validate with independent football review and appropriately authorized real data.

## Tests

`python3 -m unittest discover -s tests -p 'test_*.py'` (HTTP tests require loopback).
Existing JS tests: `node --test tests/*.test.js`.
Rollout tests cover blocked versus clear lanes, bounded movement, horizon limits,
offside rejection, reproducibility and independence from future events.

## Live tool-calling agent team

Use Touchline Settings to save an HTTPS Responses-compatible base URL, model name
and API key (server-side only). In Decision Coach select a snapshot, analyze, choose
a route and click **Run model agents**. This sends the synthetic snapshot/question
and calculated evidence to your configured provider and can incur API charges.
Provider support for function calling and strict JSON-schema output is required.
No new model is selected automatically. Missing settings returns `not_configured`.

`agents.py` implements separate coordinator, attack, defense and audit model
contexts. The coordinator calls a `delegate` function in a bounded sequence;
colleague outputs share a hash-identified snapshot. Attack must call
`evaluate_options`, defense must call `simulate_pass`, and audit must call
`check_evidence`. Each role can decline to recommend a candidate. Runtime checks
reject unknown evidence references, illegal candidates, missing tool use and early
coordinator answers. These checks do NOT prove all natural-language claims true.

The adapter uses the documented Responses function_call/function_call_output loop:
https://developers.openai.com/api/docs/guides/function-calling

Limits: 14 model requests, 150 seconds overall checked between operations, 25-second
maximum per network call, 3 rounds per specialist and 5 coordinator rounds. Only one
team request runs at once. No shell, network search, arbitrary code, provider secrets,
or future tracking is exposed as an agent tool. Partial specialist failures are
passed to later roles. Overall failure keeps the independent computed baseline.
Trace contains handoffs, actual tool completion/rejection, request counts and cited
IDs; it contains no chain of thought or raw provider errors. Export includes trace.

This is a custom four-context orchestration, not an Agent Framework/Foundry SDK
integration, not an A/B-validated improvement over a single agent. API-provider
compatibility and football quality must be tested with a configured live model.
Tests use a clearly scripted provider, not credentials or live API requests.

## Outcome-oriented action review (v0.1)

`/action-review.html` is the new comparison view. The original pass-only engine,
agent tools and their validation remain intact; no silent change to old scores.

- `python3 -m decision.train_value` fits an 8×5, ten-action finite-horizon
  location-value model using **training matches only** from the cached real data.
  Observed goals and successful transitions define its target; failed moves and
  non-goal shots terminate the simplified possession. This is a small original
  xT-inspired model, not a pretrained xT/VAEP model.
- `decision/value-model.json` stores values for each horizon, cell sample counts,
  train/test match IDs, source revision and validation. The existing eight test
  matches have been inspected previously; this is not new blind evidence.
- `compare(frame, metadata)` receives no actual endpoint, outcome, future frames
  or selected action. It compares passes, three carry targets, shots within 35 m,
  and waiting. A common net-threat proxy weighs own value after success and
  assumed opponent value after turnover, minus current value.
- Pass and shot base rates come from real events. Lane adjustments, carry/hold
  retention and turnover/rebound locations remain **unvalidated assumptions**.
  Three weight settings form a sensitivity envelope, not a statistical interval.
- Actual execution is a separate section gated by `available_at_ms`. It reports
  outcome, displacement and duration. It does **not** invent technique grades,
  intended target accuracy, foot preference or body orientation. Movement heading
  is not body orientation. Revealing the result never changes pre-action scores.
- Actual carries match an action-type proxy; their unseen intended trajectory is
  not reconstructed. The page uses the existing synthetic 40-match replay files,
  while location value is fitted on real match events.
- `POST /api/action-review`: `{dataset, match_id, decision_id, replay_at_ms?}`.
  Omitting replay time keeps outcome hidden. Paths are restricted to known data
  roots and validated identifiers. This route does not call an LLM.

Source/method: https://karun.in/blog/expected-threat.html and
https://github.com/statsbomb/open-data. Test target: goal within ten eligible
on-ball actions of the same simplified possession. Overlapping windows are not
independent goals; the small sample does not validate counterfactual action ranks.
