"""Shared action labels for System 1 and the replay overlay."""

from __future__ import annotations

from collections.abc import Mapping

ACTION_LABELS: tuple[str, ...] = ("pass", "shoot", "dribble", "hold")
PROBABILITY_TOLERANCE = 1e-6


def validate_distribution(probabilities: Mapping[str, float]) -> dict[str, float]:
    """Return probabilities in label order, or raise if they are not a distribution."""
    missing = [label for label in ACTION_LABELS if label not in probabilities]
    extra = [key for key in probabilities if key not in ACTION_LABELS]
    if missing or extra:
        raise ValueError(
            f"distribution must cover {ACTION_LABELS}; missing={missing} extra={extra}"
        )
    ordered = {label: float(probabilities[label]) for label in ACTION_LABELS}
    if any(value < 0.0 for value in ordered.values()):
        raise ValueError("probabilities must be non-negative")
    total = sum(ordered.values())
    if abs(total - 1.0) > PROBABILITY_TOLERANCE:
        raise ValueError(f"probabilities must sum to 1 within {PROBABILITY_TOLERANCE} (got {total})")
    return ordered
