# NextPlay data contract v1

Corresponds to sections 4 and 5.1 of the development document, so that A/B/C/D integrate against the same set of fixed samples.
The JSON Schema uses Draft 2020-12; the validator loads only in-repo files, with no remote references.

## Entry points and boundaries

| File / definition | Data |
| --- | --- |
| `schema.json#/$defs/match` | Existing `metadata.json`: teams, players, seed, generator, policy parameters, pitch, periods and direction |
| `schema.json#/$defs/event` | `events.jsonl`: 16 event kinds, each requiring fields such as action, participant and result according to its kind |
| `schema.json#/$defs/tracking` / `state` / `preview` | Frames, statistic snapshots, 60-second preview |
| `schema.json#/$defs/match_player` / `roster_player` / `squads` | Match roster, anonymous players in the raw roster, full squads file |
| `schema.json#/$defs/sofascore_profile` | Source attributes, with outfield and goalkeeper radars kept separate; unknown values are `null` |
| `contracts/schema.json#/$defs/match` / `snapshot` | Match envelope carrying `data_version`, fixed snapshot carrying a hash |
| `contracts/schema.json#/$defs/simulated_profile` | Hypothetical profile with `kind: simulated` |
| `contracts/schema.json#/$defs/analysis_request` / `analysis_response` | The analysis request and response from the document |

The root of the top-level Schema still matches the three JSONL record kinds tracking/event/state; other types are selected through `$defs`.
`$defs/player` keeps the old tracking five-tuple meaning; player profiles use `match_player`.
The generator's `metadata.schema_version: 1.0.0`, the existing files, and the team and player counts and values are all left unmigrated.
The new envelope version is `schema_version: contract-1`, constructed via `make_match()` / `make_snapshot()`.
Both `metadata.seed` in the match envelope and the top-level `seed` of a snapshot are generation seeds.

This delivery provides the contract, the validator, the envelope functions and the fixed samples. The existing `server.py`, `outcome.compare()`,
`agents.py` and the browser still use the old interface; the response examples do not mean the online API is already wired up.
B/C/D must subsequently connect the computation, the agents and the frontend to these fields and checks, especially candidate-set validation and model-failure degradation.
The Schema does not replace natural-language review: it cannot judge whether every number in an explanation is genuinely grounded, and it cannot automatically check success percentages in the text.

## Units, identifiers, time and missing values

- Match player IDs keep the `H01..H14` / `A01..A14` form, and teams are `HOME` / `AWAY`.
  `HOME-08` in the document is illustrative; this repository does not need rewriting into that format. IDs are unique only within one match, so cross-match references must carry `match_id`.
  Squad IDs (such as `ARS-01`) and shirt numbers are two other fields and are not interchangeable.
- The pitch is fixed at 105×68 m, origin at the top-left corner, x to the right, y downwards, z upwards; speeds are in metres per second.
  tracking.players is `[player_id,x,y,vx,vy]`, ball is `[x,y,z,vx,vy,vz]`.
- `t_ms` is accumulated match milliseconds, excluding half-time; `period_ms = t_ms - period.start_ms`.
  Existing matches are 45+5 minutes per half, and period-boundary frames follow the `period` recorded in the record.
  An event's `period_ms` corresponds to the moment the event ends; `start_ms <= end_ms <= available_at_ms`.
  Replay may only show the results of events with `available_at_ms <= current replay time`.
- `periods[].home_attacks` gives the home attacking direction; a snapshot's `attacking_direction` states the two teams' opposite directions explicitly.
  Do not infer the attacking direction from screen left/right, body orientation or movement velocity.
- A simulated profile must contain `profile_version: sim-1`, `kind: simulated`, `preferred_foot` and `weak_foot`.
  Preferred foot is `left/right/both/null`; weak foot follows the **1–5 integer or null** explicitly agreed in this contract (the document does not specify a scale).
  `null` means unknown and must not be auto-filled as right-footed or with a default ability value; mark `preferred_foot_not_considered` and fall back.
- SofaScore is a source observation, not a simulated profile; ATT/DEF/CRE/TEC/TAC and SAV/ANT/TAC/BAL/AER are not mixed.
  The five dimensions are 0–100 or null; height is in cm and weight in kg. An unknown weight stays null.
  `complete` requires the five dimensions, height and preferred foot, and does not require weight; `partial` keeps the unknown items.
  `needs_review/unmatched` may contain only schema_version and status. Source conflicts keep both values.
  A simulated profile never substitutes the source profile directly, and changing simulation parameters never writes back to the source data.

## Versions and hashes

`contracts/model.py` is the reference implementation; consumers should prefer the IDs returned by the server and need not implement hashing themselves.

1. `data_version = "gen-" + sha256(canonical JSON of metadata)[:16]`.
   It binds the seed, generator version, action policy parameters and roster attributes; it is the content version of the generation input metadata,
   **not an overall checksum of all output files**. When the generation algorithm or another dependency not written into metadata changes, the generator / policy revision must be bumped.
2. `snapshot_id = sha256(full snapshot envelope excluding snapshot_id)[:16]`.
   It covers the data version, match, seed, time, direction and current frame, and excludes the question, the actual action, event outcomes and future frames.
3. `candidate_set_id = outcome-<version>:<16-char hash>`.
   The hash input is `{snapshot_id, data_version, profile, candidates, evidence}`,
   with `is_actual` removed from candidates. It is invalidated when profile content changes (even if profile_version did not change), and when candidates or evidence change;
   merely revealing the actual action does not change the ID. Any change to the calculator must bump the prefix version.

Canonical JSON uses Python `json.dumps(sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)`,
first normalising integer-valued floats (including -0.0) to int; UTF-8 encoded, array order preserved. This is the project's encoding convention, not RFC 8785.
NaN/Infinity are forbidden. The fixed samples carry reference hashes; snapshot hashes internal to the old agent must not be mixed with this contract.

## Analysis response and cross-record rules

Modes reuse the existing `fan/analyst`, and languages are `en/zh`.
Candidate types are `pass/carry/shot/hold`; the action_id prefix must match the type.
Eligible candidates have ranks that are consecutive from 1 and unique; ineligible candidates have a null rank and cannot be rolled out.
Currently only an eligible pass may have `rollout_supported: true`; the other three types must be false.
Candidates may only expose textual opportunity, risk and ordering; the Schema rejects extra fields such as `value_gain` and `scenario_weight`.
Numerical scores may stay inside the calculator; an internal candidate object must not be returned directly as a public candidate.

Every status returns the complete response fields from the document:

| status | candidates / evidence | explanation |
| --- | --- | --- |
| ready | non-empty | has an explanation object |
| partial | non-empty | may be null |
| model_unavailable | keeps the non-empty computed result | null |
| unknown / error | may be empty | null |

agent_trace may be empty when no model was called; an actual call records coordinator/attack/defense/reviewer, tool, ms, ok, and must never contain secrets.
After structural validation, call `check_exchange(request,response,snapshot,metadata)` to check:

- snapshot hash, data version, time, direction, seed, current ball carrier and active roster agree;
- the candidate-set ID is bound to the current profile and computed result; on mismatch, discard the agent answer and prompt a retry;
- action_id/evidence_id are unique, every evidence reference exists, and ranks are consecutive;
- a pass recipient is an on-pitch player of the same team, at most one action is actual, and the explanation mode matches the request.

Structural and reference validation cannot prove that a model never read future data. Callers must pass only the current frame + metadata to the comparator;
the actual action and future events enter only the separate replay display path. For an HTTP error where a match/snapshot is not found, the transport-level error may be returned directly;
do not fabricate a valid snapshot_id to satisfy the analysis response.

## Fixed cases and validation

`tests/fixtures/contracts/match.json` and `case-a/b/c/` are fixed samples that can be read directly.
The source is one locally synthesised match with seed=20261019, and the source decisions are d000001 / d000322 / d000029.

| Case | Fixed condition |
| --- | --- |
| A | The receiver who looks unmarked is more than 5 m from the nearest defender, but the defender reaches the passing lane first; at least one hypothetical rollout results in an interception |
| B | The actual choice is a shot, and an eligible pass candidate also exists, so a pass rollout can be shown |
| C | The carrier is pressed within 3 m; the actual choice is a back pass, the forward lane is closed, and the back-pass lane has the better arrival-time margin |

Each case has `snapshot.json`, `request.json`, `response.example.json`, `context.json`.
context exists only to display the actual action / decision question and is not a computation input.
response.example is an example of the public fields projected deterministically from the current calculator; it uses model_unavailable
and makes clear that no model was called; it does not fabricate an Agent trace and does not claim a real model answer exists.
The case tests check the actual geometric conditions and the pass rollout; results filtered through the cases cannot be used to estimate the model's overall accuracy.

```sh
npm ci                  # development validation dependencies only; running the app still needs only the Python standard library
npm run test:contract   # fields / error status / fixed hashes / mismatches / references / case conditions / short-horizon seed reproduction
npm test                # includes tests/test_contract.py
npm run validate:schema # every existing core data record in data and data/league

# single file, or a custom data directory:
node scripts/validate_contracts.mjs --file contract.snapshot tests/fixtures/contracts/case-a/snapshot.json
node scripts/validate_contracts.mjs --dataset data/league-validated data/realism-sample

# requires a local full decisions.jsonl; re-export and review the diff only when deliberately upgrading the fixed cases:
python3 -m contracts.export_fixtures
```

Full validation covers metadata, events, states, the existing complete tracking, the snapshots inside decisions, preview and squads.
data.tracking in the report includes decision snapshots, and decision_snapshots is the subset of those; preview is counted as complete objects.
Complete tracking and decisions are optional generation caches and are not passed off as validated when absent; missing events/states fail.
Post-match reports, leaderboards, compressed demo packages and other derived display files are not part of this core Schema;
their aggregation and their track/event consistency remain the responsibility of the existing `validate.py`, `validate_league.py` and the per-module tests.
Fixed snapshots do not depend on gitignored large files, so a fresh clone can run the contract tests.

## Current-generator decision-analysis extension

The integrated dashboard now calls `/api/decision-analysis/*`. The original contract above remains rank/text-only with pass-only rollout semantics. Full numerical diagnostics and pass/carry/shot counterfactuals use a separately versioned extension, not extra fields on the original response. See [the dedicated contract](decision-analysis/README.md), its Schema, tool catalog and real examples. Existing legacy HTTP endpoints keep their behavior.
