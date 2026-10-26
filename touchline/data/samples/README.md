# Samples

Checked-in clips for Frontend and SysModel. This is the v0.1 centre-origin format from `touchline/scripts/synth/`. It is separate from the NextPlay League files under `touchline/data/league/` and from the legacy single match written by `touchline/generate.py`.

## `sample_25hz_10min/`

| Item | Value |
| --- | --- |
| Match | Fictional Harbor FC (HOME, `HBR`) vs Mountain FC (AWAY, `MTN`) |
| Venue | Harbor Park (fictional) |
| `frame_hz` | 25 (minimum the format allows is 10) |
| Duration | 10 minutes (`duration_ms` 600000), period 1 only |
| Frames | 15001 (`tracking.jsonl`, one JSON object per line) |
| Pitch | 105 × 68 m |
| Origin | Centre spot (centre circle). `x` along the length, `[-52.5, 52.5]`; `y` along the width, `[-34, 34]`; `z` up, ground = 0 |
| `attack_dir` | `+1` means HOME attacks toward `+x` on that frame |
| Seed | 8 (`generate.py` v3.0.0-draft, format `0.1.0`) |
| Score | 0–0 |

Files in the directory:

- `metadata.json` — frame rate, pitch, teams, players, column layout
- `tracking.jsonl` — player and ball state per frame
- `events.jsonl` — events in `available_at_ms` order, including `decision_point`
- `states.jsonl` — one score and running-stat snapshot per second
- `summary.json` — final score, event counts, distances
- `validation_report.json` — last `validate.py` report
- `validate_output.txt` — captured stdout of that run, ending in `rc=0`

Field definitions, the three.js read example, and the Python read example are in `touchline/scripts/synth/FORMAT.md`. Use only events whose `available_at_ms` is at or before the current time.

## Regenerate

From the repository root. `--seed 8` is required; the script default is a different seed. The default length is 100 minutes, so pass `--minutes 10`.

```sh
python3 touchline/scripts/synth/generate.py \
  --hz 25 --minutes 10 --seed 8 \
  --output touchline/data/samples/sample_25hz_10min

python3 touchline/scripts/synth/validate.py \
  touchline/data/samples/sample_25hz_10min
```

`validate.py` rewrites `validation_report.json` and prints the same report. It needs only the Python 3.9+ standard library and reads `touchline/scripts/synth/forbidden_terms.txt` unless `--forbidden` is set.

Optional record check (needs `jsonschema`):

```sh
python3 touchline/scripts/synth/check_schema.py \
  touchline/data/samples/sample_25hz_10min
```

A bare `python3 touchline/scripts/synth/generate.py` writes a full match into `touchline/scripts/synth/data/`. That directory is gitignored.

## What stays gitignored

Full league tracking stays out of git. `touchline/data/**/tracking.jsonl` is ignored, and `touchline/.gitignore` repeats that rule for `data/**/tracking.jsonl`. The only exception is `sample_25hz_10min/tracking.jsonl`.

Also still ignored:

- league match directories other than `NW26-W01-THF-HBR` and `NW26-W03-ASH-MTN`
- `touchline/data/league-alt/`
- `touchline/scripts/synth/data/` (accidental default generator output)

Do not commit a second full-resolution tracking file. Generate it locally and leave it untracked.
