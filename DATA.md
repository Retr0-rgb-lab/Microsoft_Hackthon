# Data

System 1 stays a four-way softmax over **pass**, **shoot**, **dribble**, and **hold**. The demo and the weight fit are offline. They do not call TypeSafe, Foundry, or any other hosted inference API. The optional Jev hook stays off unless something else imports it; `run_mvp` does not.

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

If `weights.json` is missing, `SoftmaxActionPolicy` keeps the original hand-set stub.

## Not ingested

Wyscout and SoccerNet are optional later computer-vision sources. They are not downloaded or parsed in this repository.

socceraction is not a dependency. xT / VAEP stays an explanation sidecar stub (`TODO` in `src/inside_the_game/system2/sidecar.py`). The rationale mentions that status and does not download a model.

No third-party inference APIs. System 2's default `explain` path is a local template. A local model is used only when the caller passes `local_llm`.
