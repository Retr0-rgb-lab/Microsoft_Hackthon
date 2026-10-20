"""Lightweight System 1 policy: features to a four-way softmax."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from inside_the_game.features.extract import FeatureVector, extract_features
from inside_the_game.ingest.events import MatchEvent
from inside_the_game.labels import ACTION_LABELS, validate_distribution


# Hand-set linear stub. Another thread can replace these weights with a fitted
# classifier without changing ``predict``. Order matches FEATURE_NAMES:
# ball_x, ball_y, centrality, pressure, minute, goal_diff.
_BIAS: dict[str, float] = {
    "pass": 0.55,
    "shoot": -2.05,
    "dribble": -0.35,
    "hold": 0.25,
}
_WEIGHTS: dict[str, tuple[float, float, float, float, float, float]] = {
    "pass": (0.10, 0.00, 0.45, -0.35, 0.00, 0.00),
    "shoot": (3.60, 0.00, 1.70, -1.40, 0.00, 0.00),
    "dribble": (1.70, 0.00, -1.35, -1.20, 0.00, 0.00),
    "hold": (-1.90, 0.00, 0.00, 2.50, 0.00, 0.00),
}


class ActionPolicy(Protocol):
    """System 1 contract: JSON/text match state to a full action distribution."""

    def predict(self, event: MatchEvent) -> "ActionDistribution":
        """Return P(pass), P(shoot), P(dribble), and P(hold)."""


@dataclass(frozen=True)
class ActionDistribution:
    """Full distribution over ``ACTION_LABELS``. No winning action is stored."""

    probabilities: dict[str, float]

    def __post_init__(self) -> None:
        ordered = validate_distribution(self.probabilities)
        object.__setattr__(self, "probabilities", ordered)

    def as_dict(self) -> dict[str, float]:
        return dict(self.probabilities)


class SoftmaxActionPolicy:
    """Default System 1. Event to features to softmax. No images, no network."""

    def predict(self, event: MatchEvent) -> ActionDistribution:
        return self.predict_features(extract_features(event))

    def predict_features(self, features: FeatureVector) -> ActionDistribution:
        values = features.as_tuple()
        logits = [
            _BIAS[label] + _dot(_WEIGHTS[label], values)
            for label in ACTION_LABELS
        ]
        return ActionDistribution(dict(zip(ACTION_LABELS, _softmax(logits), strict=True)))


def _dot(weights: tuple[float, ...], values: tuple[float, ...]) -> float:
    return sum(weight * value for weight, value in zip(weights, values, strict=True))


def _softmax(logits: list[float]) -> list[float]:
    peak = max(logits)
    shifted = [math.exp(logit - peak) for logit in logits]
    total = sum(shifted)
    return [item / total for item in shifted]
