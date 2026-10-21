# Data

System 1 stays a four-way softmax over **pass**, **shoot**, **dribble**, and **hold**. Both paths below are offline. They do not call TypeSafe, Foundry, or any other hosted inference API. The optional Jev hook stays off unless something else imports it; `run_mvp` does not.

## StatsBomb open data

StatsBomb open data is the primary free real-event path.

- Source: [statsbomb/open-data](https://github.com/statsbomb/open-data) only.
- No paid StatsBomb API and no other commercial event feed.

### License

StatsBomb open data is [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). That is fine for this hackathon demo. Commercial use needs separate permission from StatsBomb. The vendored match is a reduced copy of their events: fields this repository does not read were dropped, and the values that remain are theirs.

### Vendored match

`fixtures/statsbomb/69284/` is Women's World Cup 2019 semi-final, match 69284, Netherlands Women's 1–0 Sweden Women's (3 July 2019). Tests and the default fit read this directory from disk. They do not download the dataset.

### Mapping rule

| StatsBomb `type.name` | Action |
| --- | --- |
| Pass | pass |
| Shot | shoot |
| Carry, Dribble | dribble |
| Anything else | skipped |

Skipped events are not labeled **hold**. A Pass, Shot, Carry, or Dribble with no player or no location is skipped as well. Hold labels come from the synthetic generator.

Locations are on StatsBomb's 120 by 80 grid, with the team performing the event attacking toward x = 120. Ingest scales that grid onto the scaffold pitch (105 by 68 meters, home attacking toward x = 105) and flips away events into that frame. `under_pressure` becomes pressure 0.82, otherwise 0.18. Minutes above 120 are clamped to 120. Goals update the running score even when the event itself is skipped.

Mapped events are `MatchEvent` rows, so they use the same `extract_features` vector as the stub: `ball_x`, `ball_y`, `centrality`, `pressure`, `minute`, `goal_diff`.

### Fetch more matches

This hits GitHub on purpose. Do not run it from tests.

```bash
python scripts/download_statsbomb.py --list --competition-id 72 --season-id 30
python scripts/download_statsbomb.py --competition-id 72 --season-id 30 --match-id 69284
```

The second command writes `data/statsbomb/69284/` (`data/` is gitignored). Point training at that directory with `--statsbomb-dir` if you want a different match than the vendored one:

```bash
python scripts/train_softmax.py --source both --statsbomb-dir data/statsbomb/69284
```

The checked-in sample was written with:

```bash
python scripts/download_statsbomb.py --competition-id 72 --season-id 30 \
    --match-id 69284 --output fixtures/statsbomb/69284
```

## Synthetic sequences

The generator is a first-class demo and training source. It builds possessions (goal kick, pressured hold, progression, dribble, shot) and labels every event with only pass, shoot, dribble, or hold. It does not use the network.

```bash
python scripts/generate_synthetic.py --output fixtures/synthetic_labeled_sequences.json --seed 7
```

`fixtures/synthetic_match_events.json` is still the short unlabeled demo the CLI loads by default. The longer labeled file is the one training and the generator tests use.

## Weights

Checked-in file: `src/inside_the_game/system1/weights.json`.

That file is the v1 fit: multinomial logistic regression on the six scaffold features, class-weighted, using only synthetic `decision_point` events from `touchline/data/samples/sample_25hz_10min` (match `SYN-SINGLE-0001`). It does not read StatsBomb or any real-club feed. Counts are pass 73, shoot 2, dribble 41, hold 8. Hold is a short carry (progress under 4 m) with an opponent inside 3 m. See [docs/v1-model-selection.md](docs/v1-model-selection.md).

```bash
python scripts/train_softmax.py
python scripts/train_softmax.py --output /tmp/synth-weights.json --steps 100
```

`fixtures/statsbomb/` is still on disk for the open-data mapping tests. The weight fit does not open it. Backend can remove that tree after this lands, once those tests no longer need it.

If `weights.json` is missing, `SoftmaxActionPolicy` keeps the original hand-set stub.

## Not ingested

Wyscout and SoccerNet are optional later computer-vision sources. They are not downloaded or parsed in this repository.

socceraction is not a dependency. xT / VAEP stays an explanation sidecar stub (`TODO` in `src/inside_the_game/system2/sidecar.py`). The rationale mentions that status and does not download a model.

No third-party inference APIs. System 2's default `explain` path is a local template. A local model is used only when the caller passes `local_llm`.
