"""Fit the System 1 softmax on synthetic decision_point events.

The checked-in ``weights.json`` is this fit. Rows come from the SynthData
clip ``touchline/data/samples/sample_25hz_10min`` (match ``SYN-SINGLE-0001``).
Each row is one ``decision_point`` and the tracking frame at
``available_at_ms``. Pass, shot, and carry outcomes that happen later are
not rows. Real-club event feeds are not read.

    python scripts/train_softmax.py
    python scripts/train_softmax.py --output /tmp/synth-weights.json --steps 100

No download and no hosted inference.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inside_the_game.features.from_tracking import (  # noqa: E402
    LABEL_RULE,
    decision_point_rows,
    load_synth_match,
)
from inside_the_game.labels import ACTION_LABELS  # noqa: E402
from inside_the_game.system1.fit import (  # noqa: E402
    DEFAULT_L2,
    DEFAULT_LEARNING_RATE,
    DEFAULT_STEPS,
    default_weights_path,
    fit_softmax,
    save_linear_weights,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train the System 1 softmax on synthetic decision points.")
    parser.add_argument(
        "--sample",
        type=Path,
        default=None,
        help="SynthData match directory (metadata, events, tracking). Defaults to the checked-in slice.",
    )
    parser.add_argument("--output", type=Path, default=default_weights_path())
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--learning-rate", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument("--l2", type=float, default=DEFAULT_L2)
    args = parser.parse_args(argv)
    match = load_synth_match(args.sample)
    rows = decision_point_rows(match)
    fitted = fit_softmax(
        rows,
        steps=args.steps,
        learning_rate=args.learning_rate,
        l2=args.l2,
    )
    fit_on = f"synthdata:{match.match_id}:decision_point"
    path = save_linear_weights(
        args.output,
        fitted,
        extra={
            "fit_on": fit_on,
            "sample": "touchline/data/samples/sample_25hz_10min",
            "event_types": ["decision_point"],
            "label_rule": LABEL_RULE,
            "coordinate_system": (
                "centre_spot metres, pitch 105x68, attack_dir ±1; "
                "FORMAT section 6 flip so the acting team attacks +x"
            ),
        },
    )
    counts = {label: 0 for label in ACTION_LABELS}
    for _features, label in rows:
        counts[label] += 1
    print(f"wrote {path}")
    print(f"rows {len(rows)} counts {counts}")
    print(f"fit_on {fit_on}")


if __name__ == "__main__":
    main()
