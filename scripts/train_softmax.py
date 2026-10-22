"""Fit the System 1 softmax on synthetic decision_point events.

The checked-in ``weights.json`` is the six-feature fit on ``heuristic_v0``.
That command is unchanged:

    python scripts/train_softmax.py
    python scripts/train_softmax.py --output /tmp/synth-weights.json --steps 100

``--value-v1`` fits the unweighted ten-feature softmax. It requires a
sample directory of ``value_v1`` matches and writes somewhere other than
``weights.json``. If that directory is missing, it exits without writing
weights. Holdout matches and ``heuristic_v0`` files are refused.

    python scripts/train_softmax.py --value-v1 --sample path/to/value_v1_match

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
    VALUE_V1_FEATURE_NAMES,
    VALUE_V1_LABEL_RULE,
    decision_point_rows,
    guard_value_v1_sample,
    load_synth_match,
    path_has_holdout_dir,
    value_v1_rows,
)
from inside_the_game.labels import ACTION_LABELS  # noqa: E402
from inside_the_game.system1.fit import (  # noqa: E402
    DEFAULT_L2,
    DEFAULT_LEARNING_RATE,
    DEFAULT_STEPS,
    default_value_v1_weights_path,
    default_weights_path,
    fit_softmax,
    save_linear_weights,
)
from inside_the_game.system1.mlp import (  # noqa: E402
    default_mlp_weights_path,
    fit_mlp,
    save_mlp,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train the System 1 softmax on synthetic decision points.")
    parser.add_argument(
        "--sample",
        type=Path,
        default=None,
        help="SynthData match directory, or a directory of match directories. Defaults to the checked-in slice.",
    )
    parser.add_argument(
        "--value-v1",
        action="store_true",
        help="Fit the unweighted 10-feature value_v1 softmax. Requires --sample. Does not write weights.json.",
    )
    parser.add_argument(
        "--mlp",
        action="store_true",
        help="With --value-v1, fit a one-hidden-layer network instead of the linear softmax.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--learning-rate", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument("--l2", type=float, default=DEFAULT_L2)
    args = parser.parse_args(argv)
    if args.mlp and not args.value_v1:
        _fail("--mlp is only defined for --value-v1. No weights were written.")
    if args.value_v1:
        _fit_value_v1(args)
        return
    _fit_checked_in_softmax(args)


def _fit_checked_in_softmax(args: argparse.Namespace) -> None:
    output = default_weights_path() if args.output is None else args.output
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
        output,
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


def _fit_value_v1(args: argparse.Namespace) -> None:
    if args.sample is None:
        _fail(
            "value_v1 fit needs a sample directory of value_v1 matches. "
            "Pass --sample. No weights were written."
        )
    sample = Path(args.sample)
    if not sample.is_dir():
        _fail(f"value_v1 sample directory does not exist: {sample}. No weights were written.")
    if args.mlp:
        output = default_mlp_weights_path() if args.output is None else Path(args.output)
    else:
        output = default_value_v1_weights_path() if args.output is None else Path(args.output)
    if output.resolve() == default_weights_path().resolve():
        _fail(
            "value_v1 fit will not overwrite src/inside_the_game/system1/weights.json. "
            "That file is the checked-in 6-feature softmax. "
            "Pass a different --output. No weights were written."
        )
    if path_has_holdout_dir(sample):
        _fail(f"{sample} is inside a holdout directory; refusing to fit value_v1. No weights were written.")
    directories = _match_directories(sample)
    if not directories:
        _fail(f"{sample} has no value_v1 match (no metadata.json). No weights were written.")
    rows: list[tuple[tuple[float, ...], str]] = []
    per_match: list[tuple[str, list[tuple[tuple[float, ...], str]]]] = []
    for directory in directories:
        if path_has_holdout_dir(directory):
            _fail(
                f"{directory} is inside a holdout directory; refusing to fit value_v1. "
                "No weights were written."
            )
        match = load_synth_match(directory)
        try:
            guard_value_v1_sample(match)
        except ValueError as exc:
            _fail(str(exc))
        match_rows = value_v1_rows(match)
        rows.extend(match_rows)
        per_match.append((match.match_id, match_rows))
    if args.mlp:
        _fit_mlp(args, output, per_match, _display_path(sample))
        return
    match_ids = [match_id for match_id, _match_rows in per_match]
    fitted = fit_softmax(
        rows,
        steps=args.steps,
        learning_rate=args.learning_rate,
        l2=args.l2,
        class_weighted=False,
        feature_names=VALUE_V1_FEATURE_NAMES,
    )
    fit_on = "synthdata:" + "+".join(match_ids) + ":value_v1"
    path = save_linear_weights(
        output,
        fitted,
        extra={
            "fit_on": fit_on,
            "sample": _display_path(sample),
            "event_types": ["decision_point"],
            "label_rule": VALUE_V1_LABEL_RULE,
            "policy": "value_v1",
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


def _fit_mlp(
    args: argparse.Namespace,
    output: Path,
    per_match: list[tuple[str, list[tuple[tuple[float, ...], str]]]],
    sample_display: str,
) -> None:
    """Fit the network. The last two matches are the early-stop split when there are at least six."""
    if len(per_match) >= 6:
        train_matches = per_match[:-2]
        val_matches = per_match[-2:]
    else:
        train_matches = per_match
        val_matches = []
    rows = [row for _match_id, match_rows in train_matches for row in match_rows]
    validation = [row for _match_id, match_rows in val_matches for row in match_rows]
    document = fit_mlp(
        rows,
        validation=validation or None,
        feature_names=VALUE_V1_FEATURE_NAMES,
        learning_rate=args.learning_rate if args.learning_rate != DEFAULT_LEARNING_RATE else 1e-2,
        l2=args.l2 if args.l2 != DEFAULT_L2 else 1e-4,
    )
    train_ids = [match_id for match_id, _rows in train_matches]
    val_ids = [match_id for match_id, _rows in val_matches]
    document["fit_on"] = "synthdata:" + "+".join(train_ids) + ":value_v1:mlp"
    document["validation_matches"] = val_ids
    document["sample"] = sample_display
    document["event_types"] = ["decision_point"]
    document["label_rule"] = VALUE_V1_LABEL_RULE
    document["policy"] = "value_v1"
    path = save_mlp(output, document)
    counts = {label: 0 for label in ACTION_LABELS}
    for _features, label in rows:
        counts[label] += 1
    print(f"wrote {path}")
    print(f"rows {len(rows)} validation {len(validation)} counts {counts}")
    print(f"fit_on {document['fit_on']}")
    print(f"selection_loss {document['training']['selection_loss']}")


def _match_directories(sample: Path) -> list[Path]:
    if (sample / "metadata.json").is_file():
        return [sample]
    return sorted(
        child for child in sample.iterdir() if child.is_dir() and (child / "metadata.json").is_file()
    )


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
