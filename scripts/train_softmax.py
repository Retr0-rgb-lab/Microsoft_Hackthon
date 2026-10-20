"""Fit the System 1 softmax on offline rows and write weights JSON.

The checked-in file was fit with ``--source both`` (vendored StatsBomb match
69284 plus synthetic sequences at seed 7). Other sources::

    python scripts/train_softmax.py --source statsbomb --output /tmp/statsbomb-weights.json
    python scripts/train_softmax.py --source synthetic --output /tmp/synthetic-weights.json
    python scripts/train_softmax.py --source both

No download and no hosted inference. StatsBomb rows use the mapping rule in
``inside_the_game.ingest.statsbomb``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inside_the_game.ingest.statsbomb import MAPPING_RULE, VENDORED_MATCH_ID  # noqa: E402
from inside_the_game.ingest.synthetic import DEFAULT_SEED  # noqa: E402
from inside_the_game.system1.fit import (  # noqa: E402
    DEFAULT_L2,
    DEFAULT_LEARNING_RATE,
    DEFAULT_STEPS,
    default_weights_path,
    fit_softmax,
    save_linear_weights,
)
from inside_the_game.training_data import collect_rows, count_labels  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train the System 1 tabular softmax.")
    parser.add_argument("--source", choices=("statsbomb", "synthetic", "both"), default="both")
    parser.add_argument("--output", type=Path, default=default_weights_path())
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--learning-rate", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument("--l2", type=float, default=DEFAULT_L2)
    parser.add_argument(
        "--statsbomb-dir",
        type=Path,
        default=None,
        help="Match directory with match.json and events.json. Defaults to the vendored match.",
    )
    args = parser.parse_args(argv)
    rows = collect_rows(args.source, seed=args.seed, statsbomb_dir=args.statsbomb_dir)
    try:
        fitted = fit_softmax(
            rows,
            steps=args.steps,
            learning_rate=args.learning_rate,
            l2=args.l2,
        )
    except ValueError as exc:
        if args.source == "statsbomb" and "hold" in str(exc):
            raise SystemExit(
                "The StatsBomb mapping skips non-action events, so this sample has no hold "
                "labels. Use --source both (StatsBomb plus synthetic hold) or --source synthetic."
            ) from exc
        raise
    sources: list[str] = []
    if args.source in ("statsbomb", "both"):
        sources.append(f"statsbomb-open-data:{VENDORED_MATCH_ID}")
    if args.source in ("synthetic", "both"):
        sources.append(f"synthetic:seed-{args.seed}")
    path = save_linear_weights(
        args.output,
        fitted,
        extra={
            "fit_on": " + ".join(sources),
            "mapping_rule": MAPPING_RULE,
            "hold_labels": (
                "Synthetic sequences only. StatsBomb context events are skipped, not labeled hold."
            ),
        },
    )
    print(f"wrote {path}")
    print(f"rows {len(rows)} counts {count_labels(rows)}")
    print(f"fit_on {' + '.join(sources)}")


if __name__ == "__main__":
    main()
