# Decision-analysis integration on the current generator

## Versions and change boundaries

- Project / data baseline: `96d13a377e98602c9998e3ebb82186843762febf`.
- Decision module source: Hackthon `84251bbdf1a8102ab4d6113c80da986adb38a461`.
- The target is the current NextPlay-AI repository; no changes were pushed to Hackthon or to a remote.
- The current A generator, matches, fixtures, statistics, standings, reports and existing APIs are kept; matches are not re-simulated.
- B's old league or enriched-v1 is not connected. The new analysis sidecar is entirely tied to the current `data/league`.

This work checked the hashes of 330 source files, exactly matching the A source that B's new data module used at the time; therefore the four-fold xT, temperature and B0/B1 passing baselines already fitted on that source are ported, and a new-version full scoring, selection and binding pass was run. The old model is not passed off as a retrained result on a new source, and the main probability formula is not claimed to be a newly trained neural network.

## Model

The main model is still B's two-step Q2: candidate → current geometry → tactical outcome probability → one-step predicted successor → compare one more action → 12×8 xT tail value. The immediate reward for a goal is currently 1; continuation by our own team adds and continuation by the opponent subtracts; the time discount is exp(−action seconds/120).

Q = immediate + continuation − risk. Branch probabilities are rule assumptions; xT is the spatial tail value of events in the current synthetic source. The B0/B1 trees only distil the source passing rules as a control and do not replace the main probabilities. No FQI or complete autonomous playing policy was trained.

The compatibility layer reads the explicit attacking direction, period endpoints, the active roster and the actual goalkeeper role. A canonical pass uses the ball's starting point, the recipient's 0.25-second velocity lead and a 14 m/s ground ball, matching the rollout template; offside, lofted balls and the pitch-support mask apply in both steps. Lofted balls and hold are still unranked, with no fabricated zero value.

Internal Softmax scores sum to 100, and the top item is not forced to 100; they are not success rates or player ability. As requested, the new main table replaces net-gain numbers with a reason and a risk. The full numerical values remain in the explicit diagnostics extension JSON.

The SofaScore source is used only for the source profile and quality hints; preferred foot / weak foot stay neutral. Movement direction differs from body orientation, and line of sight, fatigue and individual technical quality are not recovered.

## Page integration

The original Analysis page gains Match report / Decision analysis sub-pages; the original player post-match report, heatmaps and model summary stay in Match report.

Decision analysis uses the layout of B's original research page: team / player / action / range filters, a summary, a decision timeline, the snapshot, Player action conditions, candidate ranking / reason / risk, and source and evidence details.

- By default at most 20 representative nodes: ≤2 per player, ≤10 per team, ≤1 per possession sequence, ≥30 seconds apart for the same player; rotation is by pitch zone and team, with no balancing of recommended-action proportions.
- All decisions shows every snapshot, Largest value losses is used separately for mistake review, and Unavailable / coverage shows the states that cannot be analysed.
- Opportunity loss is matched by actual type / recipient, not by picking the key moments from whether a goal was eventually scored. When there is no pre-action carry direction it is not forced to map forward.
- Positions without a complete animation can still show the exact snapshot. Open in replay is enabled only under complete trajectory or preview coverage of the same current match.
- There is no separate decision home page in a style different from the main page.

`pitch-renderer.js` is extracted from the current Replay and shared by Replay, Decision analysis and Counterfactual lab. Grass stripes, white lines, home orange / away blue, numbers, ball and selection ring are the same; candidate lanes are an extra overlay only and do not replace team colours.

The main page stays minimal, and a rollout opens `decision-counterfactual.html?match=...&decision=...&action=...`. The back link restores the same match, decision and local filters. Main asset URLs are bumped to avoid stale module caches; the main page's initialisation swallowing the match deep link was also fixed.

## Counterfactual capabilities and limits

Every supported pass/carry/shot at every analyzable node can open the detail page and run a rollout; it is no longer limited to a few fixed cases.

Pass reuses A's original physics loop and injects the exact target ranked by B. Carry and shot add simplified playback with explicit bounds: top speed 7.2 m/s, acceleration 3.5 m/s², 50 ms steps, at most 4 seconds, truncated at the current period boundary. Carry chases the target and approximates ball loss by close-range contact; shot is a 24 m/s straight ground ball with close-range block / goalkeeper-contact decisions, no rebounds and no individual ability.

The four reaction / error assumptions are not probability samples; 3/4 or 4/4 successes do not equal a real success rate. Q2 and playback use different successor approximations; playback does not change Q, the ranking or the real match in reverse. Lofted balls, hold, offside and non-analyzable nodes degrade explicitly.

## Interfaces and the follow-up Agent

Complete dedicated contract: `contracts/decision-analysis/README.md`.

- The original public contract is unchanged; the new `/api/decision-analysis/compare` outputs the original rank/text-only form.
- `/analyze` returns `decision-analysis-1`: the complete canonical request/snapshot, the original public object, player conditions, the source profile, the 30 features and their units, branch probabilities, Q1/Q2, Softmax, risk decomposition, judgment, evidence and versions.
- `/counterfactual` is the extended pass / carry / shot interface; the original rollout support field and `/api/rollout` keep pass semantics.
- `/context` returns only registered current states; the client cannot submit arbitrary future frames.
- `/actual` reveals the historical type / recipient separately after the computation and is not an input to the main comparison.
- An Agent may read the metrics and cite evidence_ids; it may not change the ranking or present assumptions as observations. There is currently no real Agent call, and no trace is fabricated.

Schema, tool catalog and real examples all live in `contracts/decision-analysis/`. Changed source files, model mismatches, stale candidate sets and requests that are not from the same source are rejected. Source file signatures are also checked while the server runs, and hashes are re-verified on change rather than continuing to serve cached old metadata.

## Running

The original entry point is unchanged: `python3 server.py`, open `/`, pick a match → Analysis → Decision analysis.

Deep link: `/?match=PL26-W01-MCI-CHE&view=stats&analysis=decisions`.

The local repository has only one set of current match data, so no Original/Enriched toggle is added. The earlier desktop `启动NextPlay-AI.command` had already opened the full home page; new code needs to start a new server process, because an old Python process does not re-import code automatically. The launcher picks a free port automatically, so trust the address actually printed in the terminal.

## Reproduction and resources

`decision_analysis.pipeline` keeps audit/train/score/validate, but its input is current-generator decision snapshots, with no fallback to inferring from an old event chain. By default score samples only; `score --all-decisions` is the full pass, and this delivery is the full pass.

See `docs/decision-source-lock.json` for the source lock; metadata, events, tracking, player data and the generator are all protected. Models, snapshots and results are placed in `data/decision-analysis` and do not overwrite the source. Development dependencies can be installed from requirements-decision-analysis.txt; running the web pages needs only the Python standard library.

For measured counts, timings, compatibility with the original tests and limits, see `decision-analysis-validation.md`. The source repository's tracked node_modules lacks the AJV dist, so the development tests used a separately installed AJV 8.17.1/ajv-formats 3.0.1 in a temporary copy and did not modify the target node_modules; running the demo itself does not need those dependencies.
