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

That file was fit with `--source both`: the vendored StatsBomb match (pass, shoot, and dribble from real events) plus synthetic sequences at seed 7 (which supply hold, and more of the other three). Training is multinomial logistic regression on the six scaffold features, class-weighted, with no third-party model. Carry is common in this StatsBomb match, so the dribble class is large; the weight file records the counts (pass 1187, shoot 35, dribble 968, hold 10).

```bash
python scripts/train_softmax.py --source both
python scripts/train_softmax.py --source synthetic --output /tmp/synthetic-weights.json
```

`--source statsbomb` alone cannot fit the four-way softmax: the mapping skips non-actions, so the match has no hold labels. Use `--source both` when the fit should include the real-event sample.

If `weights.json` is missing, `SoftmaxActionPolicy` keeps the original hand-set stub.

## Not ingested

Wyscout and SoccerNet are optional later computer-vision sources. They are not downloaded or parsed in this repository.

No third-party inference APIs.
