# Source

Two upstream repositories were imported into `touchline/`, without forking either
one and without their git history.

| Field | Value |
| --- | --- |
| Data generator | https://github.com/LiNTe912/NextPlay-AI |
| Data generator commit | `a964c71031b0f32a8ed5226d77db5ce24f16e2b4` (2026-10-21 11:45:17 +0100) |
| Trained model layer | https://github.com/tigerguoyi/NextPlay-AI (a fork of the repository above) |
| Import date | 2026-10-21 |
| Original license | None. The source commit has no `LICENSE` file and the GitHub metadata reports `license: null`. No SPDX license was copied because none was published. |
| Authorization | The upstream authors granted permission to use this code in this hackathon project. |

`data/` was not copied wholesale. The checked-in league is the trimmed sample
described in `README.md`; full tracking stays gitignored, and the only tracked
`tracking.jsonl` is the SynthData 25 Hz clip.

## Name replacement

Upstream code, UI copy, and `data/league/squads.json` identified 20 real
2026/27 clubs, their grounds, and 566 real players (names, shirt numbers,
nationalities, dates of birth, and external player ids). That squad file was not
imported.

What ships today:

- **Club, ground and player names are fictional.** The 20 clubs are Aster FC,
  Beacon FC, Cedar FC, Driftwood FC, Ember FC, Fairhaven FC, Glenvale FC,
  Highridge FC, Ivory FC, Juniper FC, Kingswell FC, Larkspur FC, Meadow FC,
  Northstar FC, Oakmere FC, Pinecrest FC, Quartz FC, Rivermist FC, Silverbrook
  FC and Thornvale FC, each with a fictional ground. `data/league/squads.json`
  holds the mapping; the interface only ever renders these names.
- **Player names are procedural.** `generate.py` builds 560 players (28 per
  club) from fixed given-name and family-name lists. Nationalities and dates of
  birth are procedural. There is no per-player mapping from a real player.
- **Three-letter club codes are opaque identifiers, not names.** The codes
  (`ARS`, `TOT`, `LIV`, …) and the `PL26` match-id prefix are carried over from
  upstream as stable keys. Nothing renders them, and they are not club names.
  The upstream code-to-name table is deliberately not reproduced here: keeping
  it would publish the real club names this document exists to replace.
- **Kit colours are upstream values.** They are not a new palette. Colours are
  not protected by the naming rule, but no club badge, crest, logo or Premier
  League mark is reproduced anywhere in the data or the interface.
- **Roster attributes come from a public scouting source.** Each player carries a
  descriptive index set (attack, technique, tactical, creativity, or the
  goalkeeper equivalents). These are descriptive, not success probabilities, and
  `realism/player_actions.py` uses them only as a style multiplier.
  `data/league/squads.json` is the roster of record.

## What the interface is allowed to see

The committed roster records also carry, straight from the same source, the
player's birth date, nationality code, shirt number, source identifier, a
capture fingerprint, and the conflict records that restate them. Those fields
identify a real person once the name alias is reversed, and they are not model
inputs.

`decision_analysis.input_adapter.public_profile()` keeps only the football
fields, and the server applies it on the way out:

- `POST /api/decision-analysis/analyze` and `/agents` serve the trimmed profile
  in `player_source_profile`.
- `GET /data/league/squads.json` and `GET /data/league/matches/*/metadata.json`
  are rewritten by `server.Handler.send_redacted()` before they reach the
  browser.

The bytes on disk still contain those fields, because `data_version()` digests
the whole match metadata: stripping them at rest changes every snapshot digest
in the 91,031-record decision dataset, which would require regenerating the
dataset and its source lock. That is a team decision, not something to change
silently the day before submission. Until it is taken, the served product is
clean and the repository is not.


Two tracked files still contain real club names on purpose:

- `scripts/synth/forbidden_terms.txt` — the scrub blocklist the generator and
  `scripts/synth/validate.py` use to fail the build if a real club, ground,
  competition, brand or player name reaches generated data. Removing it would
  remove the check.
- The club-code prefix described above, which carries no name.

`tests/post-match-report-preview.png` was removed. It was an upstream screenshot
of a report that named real clubs and players. No test referenced the file.

## Not replaced

- Optional narration still targets the OpenAI Responses API
  (`https://api.openai.com/v1`, mode `openai`) in `analysis_agent.py`, and the
  settings form in `index.html`. `model_service.py` and `server.py` now use
  `ITG_MODEL_BASE_URL`, `ITG_MODEL_NAME` and `ITG_MODEL_API_KEY`, defaulting to
  an Azure AI Foundry deployment. Those strings name the service, not a club,
  player or competition.
- Fictional players are assigned real country names as nationalities. Those are
  countries, not copied player biographies.
- Kick-off times use the IANA zone `Europe/London`.
- `analysis_agent.py` still says the demo impact score is "not an official
  rating." That sentence does not name a competition.

## Competition naming

The competition is **NextPlay League**, season 2026/27, synthetic matches
(`data/league/squads.json` records `competition: "NextPlay League"` and
`synthetic_matches: true`). Match identifiers keep the upstream `PL26-Wnn-XXX-YYY`
form as opaque keys. `README.md` refers to the same competition by this name.

## Regenerate

From `touchline/`:

```sh
python3 generate.py --weeks 4 --tracking none --retain-matches 2
python3 generate.py --mode single --output data
```

`--retain-matches` simulates every fixture, writes the league index, and then
keeps the week-1 opener and the week-3 featured match (the explorer default when
no home club is selected). Omit the flag to keep all match directories. League
`tracking.jsonl` files and `data/league-alt/` are gitignored. The one exception
is the SynthData clip below. Details are in `README.md`.

The decision-analysis model layer is rebuilt separately. `decision_analysis/pipeline.py`
has `audit`, `train`, `score` and `validate` subcommands; `validate` re-checks
the committed 40-match dataset against the contract without writing to it.

## SynthData 25 Hz sample

`data/samples/sample_25hz_10min/` is a separate checked-in clip from the v0.1
single-match generator in `scripts/synth/`. It is not produced by `generate.py`
and it does not replace the league sample above.

- Frame rate 25 Hz, 10 minutes (15,001 frames). Pitch 105 × 68 m. Origin is the
  centre spot.
- Fictional Harbor FC (HOME) vs Mountain FC (AWAY), played at fictional Harbor
  Park.
- `data/samples/sample_25hz_10min/tracking.jsonl` is tracked on purpose. Every
  other `tracking.jsonl` under `data/`, other league match directories,
  `data/league-alt/`, and the generator default `scripts/synth/data/` stay
  gitignored.

Regenerate steps and the notes for Frontend and SysModel are in
`data/samples/README.md`.
