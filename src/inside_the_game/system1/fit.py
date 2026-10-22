"""Fit and load the System 1 linear softmax.

Training is multinomial logistic regression on the six scaffold features.
It uses the standard library only, so CI does not install a numerical stack
and does not call a hosted model. Missing weight files are not loaded here;
``SoftmaxActionPolicy`` falls back to the hand-set stub.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inside_the_game.features.extract import FEATURE_NAMES
from inside_the_game.labels import ACTION_LABELS


DEFAULT_STEPS = 500
DEFAULT_LEARNING_RATE = 1.2
DEFAULT_L2 = 0.02


@dataclass(frozen=True)
class LinearSoftmaxWeights:
    """Bias and per-class weights in ``feature_names`` order.

    The default names are the six scaffold features. A value_v1 fit passes
    its own ten names and does not reuse this default.
    """

    bias: dict[str, float]
    weights: dict[str, tuple[float, ...]]
    metadata: dict[str, Any]
    feature_names: tuple[str, ...] = FEATURE_NAMES

    def as_dict(self) -> dict[str, Any]:
        document = {
            "version": 1,
            "feature_names": list(self.feature_names),
            "labels": list(ACTION_LABELS),
            "bias": {label: self.bias[label] for label in ACTION_LABELS},
            "weights": {label: list(self.weights[label]) for label in ACTION_LABELS},
        }
        document.update(self.metadata)
        return document


def default_weights_path() -> Path:
    """Checked-in six-feature weights next to the System 1 policy."""
    return Path(__file__).resolve().with_name("weights.json")


def default_value_v1_weights_path() -> Path:
    """Separate value_v1 file. This is not ``weights.json``."""
    return Path(__file__).resolve().with_name("weights_value_v1.json")


def fit_softmax(
    samples: Sequence[tuple[Sequence[float], str]],
    *,
    steps: int = DEFAULT_STEPS,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    l2: float = DEFAULT_L2,
    class_weighted: bool = True,
    feature_names: Sequence[str] | None = None,
) -> LinearSoftmaxWeights:
    """L2-regularized multinomial logistic regression. Full-batch gradient descent.

    Class weights are inverse frequency so shot and hold are not drowned by
    passes. Bias is not regularized. Initialization is zero, so the fit is
    deterministic for a given sample order. The default names are the six
    scaffold features and ``class_weighted`` stays on, which is the checked-in
    fit. A value_v1 fit passes its ten names and ``class_weighted=False``.
    """
    if not samples:
        raise ValueError("fit_softmax needs at least one labeled sample")
    if steps < 1:
        raise ValueError("steps must be positive")
    names = tuple(feature_names) if feature_names is not None else FEATURE_NAMES
    if not names:
        raise ValueError("feature_names must not be empty")
    feature_count = len(names)
    rows: list[tuple[tuple[float, ...], int]] = []
    labels: list[str] = []
    for values, label in samples:
        if label not in ACTION_LABELS:
            raise ValueError(f"label {label!r} is outside {ACTION_LABELS}")
        if len(values) != feature_count:
            raise ValueError(f"expected {feature_count} features, got {len(values)}")
        rows.append((tuple(float(value) for value in values), ACTION_LABELS.index(label)))
        labels.append(label)
    counts = Counter(labels)
    missing = [label for label in ACTION_LABELS if counts[label] == 0]
    if missing:
        raise ValueError(f"training sample is missing labels: {missing}")
    class_count = len(ACTION_LABELS)
    if class_weighted:
        sample_weight = {
            index: len(rows) / (class_count * counts[label])
            for index, label in enumerate(ACTION_LABELS)
        }
    else:
        sample_weight = {index: 1.0 for index in range(class_count)}

    bias = [0.0] * class_count
    weight = [[0.0] * feature_count for _ in range(class_count)]
    for _ in range(steps):
        grad_bias = [0.0] * class_count
        grad_weight = [[0.0] * feature_count for _ in range(class_count)]
        weight_sum = 0.0
        for values, class_index in rows:
            logits = [
                bias[index] + _dot(weight[index], values) for index in range(class_count)
            ]
            probabilities = _softmax(logits)
            for index in range(class_count):
                weighted = sample_weight[class_index] * (
                    probabilities[index] - (1.0 if index == class_index else 0.0)
                )
                grad_bias[index] += weighted
                for feature_index, value in enumerate(values):
                    grad_weight[index][feature_index] += weighted * value
            weight_sum += sample_weight[class_index]
        scale = 1.0 / weight_sum
        for index in range(class_count):
            bias[index] -= learning_rate * (grad_bias[index] * scale)
            for feature_index in range(feature_count):
                gradient = grad_weight[index][feature_index] * scale
                penalty = l2 * weight[index][feature_index]
                weight[index][feature_index] -= learning_rate * (gradient + penalty)

    return LinearSoftmaxWeights(
        bias={label: round(bias[index], 6) for index, label in enumerate(ACTION_LABELS)},
        weights={
            label: tuple(round(value, 6) for value in weight[index])
            for index, label in enumerate(ACTION_LABELS)
        },
        metadata={
            "training": {
                "steps": steps,
                "learning_rate": learning_rate,
                "l2": l2,
                "class_weighted": class_weighted,
                "counts": {label: counts[label] for label in ACTION_LABELS},
            }
        },
        feature_names=names,
    )


def load_linear_weights(path: Path) -> LinearSoftmaxWeights:
    """Read a weight document. Raises if the file is not this softmax schema."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("weight file must be a JSON object")
    feature_names = document.get("feature_names")
    labels = document.get("labels")
    if list(feature_names or []) != list(FEATURE_NAMES):
        raise ValueError(f"weight file features must be {FEATURE_NAMES}")
    if list(labels or []) != list(ACTION_LABELS):
        raise ValueError(f"weight file labels must be {ACTION_LABELS}")
    bias = _named_floats(document.get("bias"), "bias")
    raw_weights = document.get("weights")
    if not isinstance(raw_weights, dict):
        raise ValueError("weight file is missing weights")
    weights: dict[str, tuple[float, ...]] = {}
    for label in ACTION_LABELS:
        row = raw_weights.get(label)
        if not isinstance(row, list) or len(row) != len(FEATURE_NAMES):
            raise ValueError(f"weights[{label}] must have {len(FEATURE_NAMES)} numbers")
        weights[label] = tuple(float(value) for value in row)
    metadata = {
        key: value
        for key, value in document.items()
        if key not in {"version", "feature_names", "labels", "bias", "weights"}
    }
    return LinearSoftmaxWeights(bias=bias, weights=weights, metadata=metadata)


def save_linear_weights(path: Path, fitted: LinearSoftmaxWeights, *, extra: Mapping[str, Any] | None = None) -> Path:
    """Write weights as JSON. ``extra`` is merged into the document metadata."""
    document = fitted.as_dict()
    if extra:
        document.update(dict(extra))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def _named_floats(value: Any, field: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"weight file is missing {field}")
    parsed: dict[str, float] = {}
    for label in ACTION_LABELS:
        if label not in value:
            raise ValueError(f"{field} is missing {label}")
        parsed[label] = float(value[label])
    return parsed


def _dot(weights: Sequence[float], values: Sequence[float]) -> float:
    return sum(weight * value for weight, value in zip(weights, values, strict=True))


def _softmax(logits: Sequence[float]) -> list[float]:
    peak = max(logits)
    shifted = [math.exp(logit - peak) for logit in logits]
    total = sum(shifted)
    return [item / total for item in shifted]
