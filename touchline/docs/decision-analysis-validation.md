# Decision-analysis port acceptance record

## Baseline and source

Target project starting point: `96d13a377e98602c9998e3ebb82186843762febf`. Module source: Hackthon `84251bbdf1a8102ab4d6113c80da986adb38a461`. Only the implementation and the same-source analysis sidecar were committed to the desktop NextPlay-AI; Hackthon was not modified and nothing was pushed to a remote.

Before porting, all 330 A source files were verified one by one, and all were identical to the manifest of B's new data model. The same-source fitted four-fold xT, temperature and B0/B1 baselines were ported; the new `outcome-3.0` comparator re-ran full scoring and representative selection. No match engine was run, and B's old league/enriched-v1 was not brought in. The current generator, data/league, league-validated, the original reports and replay were not changed.

## Actual data

| Item | Result |
|---|---:|
| Matches | 40 |
| Canonical exact snapshots | 91,031 |
| Full public responses | 91,031 |
| Ranked / unknown | 91,029 / 2 |
| Recommended across all, pass / carry / shot | 62,004 / 24,512 / 4,513 |
| Representative nodes | 800, 20 for each of the 40 matches |
| Representative players per match | 19–20 |
| Recommended at representative nodes, pass / carry / shot | 652 / 76 / 72 |
| New sidecar release size | 97,293,829 bytes, about 97.29 MB / 92.79 MiB |
| Full scoring time | 372.64 seconds on this machine |
| Online / precomputed comparison | 80 nodes (first and last of each of the 40 matches), identical item by item; the desktop target copy was re-checked separately and passed |

The two unknown nodes are final nodes that do not meet the normal in-match possession conditions; they are not given a fake ranking or rollout. A historical carry with no pre-action direction stays unmatched. Only four matches in the source have complete tracking, and the per-decision snapshots are available for the rest; replay jumps must be constrained by actual trajectory coverage.

These proportions are descriptive statistics, not accuracy scores; the share of shot recommendations was not deliberately suppressed. The representativeness constraints are ≤2 per player, ≤10 per team, ≤1 per possession sequence, and ≥30 seconds between the same player. Rotation is by pitch zone and team, with no fabricated missing players.

## Automated validation

| Check | Result |
|---|---|
| Full original plus new Python suite | 107 passed; the final 8 new integration tests passed again |
| Full JavaScript suite | 24 passed |
| Original canonical-contract regression | Includes the original tests and 14 dedicated ported regressions, passed |
| Original Schema for source data | All core records in root data and league passed; league: 40 metadata, 40 previews, 150,466 events, 240,040 states, 211,035 tracking (including 91,031 decision frames) |
| New sidecar semantic validation | 40 matches, 91,031 snapshots, 91,031 public responses; source protection, hashes, references and held-out fold isolation passed |
| New extension Schema | Compilation and the real context/analyze/counterfactual examples passed; catalog/index passed in the HTTP tests |
| Full sidecar Schema | metadata, index, snapshot and public response all passed; exact counts are in the run log |
| Pass / carry / shot rollouts | Repeatable for the same state / action / version; frame zero keeps the observation, later speeds ≤7.2 m/s, positions bounded, four scenarios ≤4 seconds, truncated at the half endpoint |
| Stale / invalid requests | Wrong candidate ID, unknown path, out-of-scope source, future-outcome input and unsupported action are rejected |
| Protection against data mixing after a source update | Start-up hashes plus runtime file signatures / post-change hash checks; a regenerated source is not ignored because of an in-memory metadata cache |
| Original API regression | The old decision/rollout, model settings, post-match summary and Agent APIs stay independent; the canonical Schema is unchanged |

Schema validation and numerical regression do not prove that real-football counterfactuals are accurate. Q2's tactical branches are still rule assumptions, and the passing tree is still only a baseline distilled from the source mechanism.

## Page integration checks

- The original home page, Analysis/Match report, Decision analysis, and the Replay entry for the same match all work.
- The new page uses the original research page's timeline / filter layout, keeps Player action conditions, and the main table shows reason and risk.
- The same `pitch-renderer.js` serves Replay, decisions and rollouts: the original grass stripes, lines, home orange / away blue, player numbers and ball are preserved.
- The 40-match index is complete; fast selection cancels / discards the old state, and the version-binding check remains.
- Counterfactual sub-page: pass, carry and shot all complete compute / playback / reset; going back returns to the same match and the same decision.
- Checked at 1280 desktop and 390 mobile; in both new pages the mobile full-page width is 390 with no full-page horizontal overflow, and the candidate table scrolls inside its own container.
- New asset version parameters are bumped to avoid mixing with old project scripts; after restarting Python, use the new process port.

## Test environment and honest limits

The full Python test run used a separate Python 3.12 environment; the web preview and the new dedicated regressions also ran on the system Python 3.9. Running the demo needs no scikit-learn, Node or API key; only offline refitting needs the training dependencies.

The A repository's tracked node_modules lacks the AJV dist. After an offline install attempt in a temporary development copy failed to obtain the required cache, the development tests were completed with an isolated installed AJV 8.17.1 / ajv-formats 3.0.1, and no node_modules changes were copied back into the target repository. Schema subprocesses ran after Node was added to PATH; there is no claim that the original environment would pass without dependency preparation.

No real explanation agent is configured or called; it returns model_unavailable, a null explanation and an empty trace, while the numbers and the reason/risk remain usable. The new numbers are an explicit research extension, and the original public object still has no Q/Softmax. hold, lofted balls, aerial duels, individual skill, real body posture and long-horizon complete policy are not implemented.

The carry / shot counterfactuals are bounded simplified playback added in this work, not a complete physics match engine. They do not fully agree with Q2's successor approximation, and the four animated scenarios cannot be used to certify the main model in reverse. Later Agent wiring should cite fields per the dedicated contract, declare its assumptions and reject stale candidates, without tampering with the ranking.

## Main commands

```sh
node --test tests/*.test.js
python3 -m unittest discover -s tests -p 'test_*.py'
node scripts/validate_contracts.mjs --dataset data data/league
node scripts/validate_decision_analysis.mjs
node scripts/validate_decision_dataset.mjs
python3 -m decision_analysis.pipeline validate
```

Machine-readable copy of the statistics: `decision-analysis-metrics.json`. All source-code / source-data change checks were verified before the final commit.

Desktop target copy re-check: system Python 3.9.6 can load the full metrics and compute all three rollout types; 24 JavaScript tests passed; 80 online / precomputed boundary responses at the target location are identical, and the original source file hashes are unchanged. The final preview is served from a new process of the target repository, not by reusing an old process.
