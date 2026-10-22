"""Lightweight System 1 policy: features to a four-way softmax."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from inside_the_game.features.extract import FeatureVector, extract_features
from inside_the_game.features.from_tracking import features_from_tracking
from inside_the_game.ingest.events import MatchEvent
from inside_the_game.labels import ACTION_LABELS, validate_distribution
from inside_the_game.system1.fit import default_weights_path, load_linear_weights


# Hand-set linear stub. Used when ``weights.json`` is missing. Order matches
# FEATURE_NAMES: ball_x, ball_y, centrality, pressure, minute, goal_diff.
_STUB_BIAS: dict[str, float] = {
    "pass": 0.55,
    "shoot": -2.05,
    "dribble": -0.35,
    "hold": 0.25,
}
_STUB_WEIGHTS: dict[str, tuple[float, float, float, float, float, float]] = {
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
    """Default System 1. Event to features to softmax. No images, no network.

    A weight file next to this module is the fitted policy. If that file is
    absent, or ``weights_path`` points at a missing file, prediction uses the
    hand-set stub. A present file that fails to parse is an error.
    """

    def __init__(self, weights_path: Path | None = None, *, force_stub: bool = False) -> None:
        if force_stub:
            self._use_stub()
            return
        path = default_weights_path() if weights_path is None else Path(weights_path)
        if not path.is_file():
            self._use_stub()
            return
        loaded = load_linear_weights(path)
        self._bias = dict(loaded.bias)
        self._weights = {label: tuple(loaded.weights[label]) for label in ACTION_LABELS}
        self.weight_source = "file"
        self.weights_path: Path | None = path

    @classmethod
    def stub(cls) -> SoftmaxActionPolicy:
        """The original hand-set softmax, ignoring any weight file."""
        return cls(force_stub=True)

    def _use_stub(self) -> None:
        self._bias = dict(_STUB_BIAS)
        self._weights = {label: tuple(_STUB_WEIGHTS[label]) for label in ACTION_LABELS}
        self.weight_source = "stub"
        self.weights_path = None

    def predict(self, event: MatchEvent) -> ActionDistribution:
        return self.predict_features(extract_features(event))

    def predict_tracking(
        self,
        frame: Mapping[str, Any],
        event: Mapping[str, Any],
        team_of: Mapping[str, str],
    ) -> ActionDistribution:
        """Distribution for one SynthData decision_point and its tracking frame.

        The frame replaces a video or CV observation. Coordinates stay in the
        sample pitch (centre spot, metres, ``attack_dir`` ±1) until
        ``features_from_tracking`` applies the section 6 attack flip. The
        returned distribution is still pass, shoot, dribble, and hold.

        The checked-in ``weights.json`` is the six-feature softmax. This
        method keeps using that vector. The ten-feature value_v1 fit lives
        in a separate file and is not loaded here.
        """
        if event.get("type") != "decision_point":
            raise ValueError("predict_tracking expects a decision_point event")
        return self.predict_features(features_from_tracking(frame, event, team_of))

    def predict_features(self, features: FeatureVector) -> ActionDistribution:
        values = features.as_tuple()
        logits = [
            self._bias[label] + _dot(self._weights[label], values)
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
