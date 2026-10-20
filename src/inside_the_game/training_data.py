"""Assemble offline training rows for the System 1 softmax.

Rows are ``(feature tuple, action label)`` using the same ``extract_features``
path as inference. Sources are the vendored StatsBomb match and the synthetic
generator. Nothing here downloads data or calls an inference API.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from inside_the_game.features.extract import extract_features
from inside_the_game.ingest.statsbomb import load_statsbomb_labeled
from inside_the_game.ingest.synthetic import DEFAULT_SEED, generate_events


SOURCES = ("statsbomb", "synthetic", "both")


def collect_rows(
    source: str = "both",
    *,
    seed: int = DEFAULT_SEED,
    statsbomb_dir: Path | None = None,
) -> list[tuple[tuple[float, float, float, float, float, float], str]]:
    """Feature rows for ``source`` (statsbomb, synthetic, or both)."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    rows: list[tuple[tuple[float, float, float, float, float, float], str]] = []
    if source in ("statsbomb", "both"):
        mapped = load_statsbomb_labeled(statsbomb_dir)
        for item in mapped.events:
            rows.append((extract_features(item.event).as_tuple(), item.action))
    if source in ("synthetic", "both"):
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
