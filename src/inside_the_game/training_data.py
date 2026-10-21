"""Assemble offline training rows for the System 1 softmax.

Rows are ``(feature tuple, action label)`` using the same ``extract_features``
path as inference. The source is the synthetic generator. Nothing here
downloads data or calls an inference API. The checked-in softmax is fit
separately, on synthetic ``decision_point`` rows, by ``scripts/train_softmax.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from inside_the_game.features.extract import extract_features
from inside_the_game.ingest.synthetic import DEFAULT_SEED, generate_events


def collect_rows(
    source: str = "synthetic",
    *,
    seed: int = DEFAULT_SEED,
) -> list[tuple[tuple[float, float, float, float, float, float], str]]:
    """Feature rows from the synthetic generator."""
    if source != "synthetic":
        raise ValueError("source must be synthetic")
    rows: list[tuple[tuple[float, float, float, float, float, float], str]] = []
    for event in generate_events(seed=seed):
        if event.action is None:
            raise ValueError(f"{event.event_id} is missing a synthetic label")
        rows.append((extract_features(event).as_tuple(), event.action))
    return rows


def count_labels(rows: Sequence[tuple[Sequence[float], str]]) -> dict[str, int]:
    counts = {"pass": 0, "shoot": 0, "dribble": 0, "hold": 0}
    for _features, label in rows:
        counts[label] += 1
    return counts
