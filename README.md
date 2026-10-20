# Inside the Game

Microsoft × Premier League Developer Hackathon MVP scaffold (`inside_the_game`).

This is a decision aid. For each synthetic on-ball state it shows the full probability distribution over **pass**, **shoot**, **dribble**, and **hold**, with a bar and an arrow placeholder for every action. It does not mark a single action as optimal.

## Locked architecture

1. **Ingest** synthetic match events (JSON/text state).
2. **System 1** maps that state to `P(pass | shoot | dribble | hold)`. The default backend is a lightweight linear softmax over numeric features. It loads `src/inside_the_game/system1/weights.json` when that file is present and otherwise uses the hand-set stub. An optional [TypeSafe Jev Choice](https://docs.typesafe.ai/primitives/choice) hook accepts the same JSON/text state and is unused when `typesafe-sdk` is not installed. No images. Jev stays off on the MVP path.
3. **Optional CV late-fusion** would be overlay-only. It is **deferred** and is not in this repository path.
4. **System 2** takes a match event plus the System 1 distribution and returns a short football rationale (`explain`). The default is an offline template: no network and no API key. An optional local model implements the same call only when the caller passes `local_llm`; `load_local_llm()` is `None`, so the hook stays off. A Foundry-shaped chat body is still built in memory and is not sent. socceraction xT / VAEP stays a stub sidecar (`TODO`) and is named in the rationale without a fitted value.
5. **Present** emits replay overlay arrows, probability bars for all four actions, and the System 2 explanation in the same overlay.

MVP path in this pull request: **1 → 2 → 4 → 5**.

```
fixtures → ingest → features → system1 softmax → system2 explain → present
                                    ↘ optional Jev Choice (text/JSON, not required)
system2 sidecar: socceraction xT/VAEP TODO (named in the rationale, not fitted)
CV late-fusion: deferred
```

## Install

Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The Jev extra is optional and is not required for the stub or the tests:

```bash
pip install -e ".[dev,jev]"
```

## Run the stub

From the repository root, after install:

```bash
python -m inside_the_game
```

The same entry point is available as `inside-the-game`. It loads `fixtures/synthetic_match_events.json` and prints, for each event, probability bars and arrow placeholders for pass, shoot, dribble, and hold, with the offline explanation on the same overlay. No network calls.

Pass a local model only if you want to replace the template. It must provide `rationale(event, distribution, profile) -> str` and it must not call a hosted API:

```python
from inside_the_game.system2 import explain

explain(event, distribution, local_llm=MyLocalModel())
```

`load_local_llm()` returns `None`. Setting an API key or `INSIDE_THE_GAME_LOCAL_LLM` does not enable a model.

## Tests

```bash
pytest
```

`pytest` checks the four-way distribution with the checked-in weights and with the stub fallback, the offline System 2 rationale (synthetic and StatsBomb states, with the network blocked), the overlay explanation beside all four probabilities, the StatsBomb event-type mapping, and the synthetic generator's labels. See [DATA.md](DATA.md) for the open-data license, the mapping rule, and the commands that regenerate fixtures or fetch more matches.

## Layout

```
fixtures/synthetic_match_events.json
fixtures/synthetic_labeled_sequences.json
fixtures/statsbomb/69284/          one vendored StatsBomb open-data match
src/inside_the_game/
  ingest/          match-event schema, JSON loader, StatsBomb map, synthetic generator
  features/        event → numeric features
  system1/         softmax policy, fitted weights.json, optional Jev Choice hook
  system2/         offline explain template, optional local model hook, xT/VAEP sidecar stub
  present/         bars, arrow placeholders, and the explanation for all four actions
  pipeline.py      1 → 2 → 4 → 5
scripts/           download_statsbomb, generate_synthetic, train_softmax
tests/
DATA.md
```

Public entry points other threads can implement against:

- `inside_the_game.ingest.load_events`
- `inside_the_game.features.extract_features`
- `inside_the_game.system1.SoftmaxActionPolicy.predict`
- `inside_the_game.system1.load_jev_choice` / `build_choice_request`
- `inside_the_game.system2.explain` / `load_local_llm` (the loader stays `None`)
- `inside_the_game.present.render_overlay`
- `inside_the_game.run_mvp`

Pitch coordinates in the fixture are meters, x in `[0, 105]` and y in `[0, 68]`, with home attacking toward x = 105.
