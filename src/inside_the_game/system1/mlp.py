"""One hidden layer for the value_v1 four-class distribution.

The linear softmax adds option values. The hold label is a kink on top of
that sum: a short carry with an opponent inside 3 m. A ReLU layer can bend
there. Training stays on numpy, on this machine, and never writes
``weights.json``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from inside_the_game.labels import ACTION_LABELS


DEFAULT_HIDDEN = 32
DEFAULT_EPOCHS = 80
DEFAULT_BATCH = 256
DEFAULT_LEARNING_RATE = 1e-2
DEFAULT_L2 = 1e-4
DEFAULT_PATIENCE = 8
DEFAULT_SEED = 0


def default_mlp_weights_path() -> Path:
    """Separate from the linear ``weights.json`` and ``weights_value_v1.json``."""
    return Path(__file__).resolve().with_name("weights_value_v1_mlp.json")


def fit_mlp(
    samples: list[tuple[tuple[float, ...], str]],
    *,
    validation: list[tuple[tuple[float, ...], str]] | None = None,
    hidden: int = DEFAULT_HIDDEN,
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = DEFAULT_BATCH,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    l2: float = DEFAULT_L2,
    patience: int = DEFAULT_PATIENCE,
    seed: int = DEFAULT_SEED,
    feature_names: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Adam on one ReLU layer. Returns the checkpoint with the best validation loss.

    With no validation split the checkpoint is the last epoch. Labels outside
    the four action names raise. Every class must appear in ``samples``.
    """
    if hidden < 1:
        raise ValueError("hidden must be positive")
    if not samples:
        raise ValueError("fit_mlp needs at least one labeled sample")
    features, labels = _matrix(samples)
    names = tuple(feature_names) if feature_names is not None else tuple(
        f"f{index}" for index in range(features.shape[1])
    )
    if len(names) != features.shape[1]:
        raise ValueError(f"expected {features.shape[1]} feature names, got {len(names)}")
    counts = {label: int(np.sum(labels == index)) for index, label in enumerate(ACTION_LABELS)}
    missing = [label for label, count in counts.items() if count == 0]
    if missing:
        raise ValueError(f"training sample is missing labels: {missing}")

    val_features = val_labels = None
    if validation:
        val_features, val_labels = _matrix(validation)

    rng = np.random.default_rng(seed)
    width_in = features.shape[1]
    width_out = len(ACTION_LABELS)
    weights_in = rng.normal(0.0, math.sqrt(2.0 / width_in), size=(width_in, hidden))
    bias_in = np.zeros(hidden)
    weights_out = rng.normal(0.0, math.sqrt(2.0 / hidden), size=(hidden, width_out))
    frequency = np.array([counts[label] for label in ACTION_LABELS], dtype=np.float64)
    frequency /= frequency.sum()
    bias_out = np.log(frequency)

    moment = _zeros_like(weights_in, bias_in, weights_out, bias_out)
    velocity = _zeros_like(weights_in, bias_in, weights_out, bias_out)
    best_loss = math.inf
    best_epoch = 0
    stall = 0
    best_state: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None
    step = 0
    order = np.arange(features.shape[0])

    for epoch in range(epochs):
        rng.shuffle(order)
        for start in range(0, features.shape[0], batch_size):
            batch = order[start : start + batch_size]
            step += 1
            gradients = _gradients(
                features[batch],
                labels[batch],
                weights_in,
                bias_in,
                weights_out,
                bias_out,
                l2,
            )
            updated = _adam(
                (weights_in, bias_in, weights_out, bias_out),
                gradients,
                moment,
                velocity,
                step,
                learning_rate,
            )
            weights_in, bias_in, weights_out, bias_out = updated
        score_x = features if val_features is None else val_features
        score_y = labels if val_labels is None else val_labels
        loss = log_loss(predict_proba(score_x, weights_in, bias_in, weights_out, bias_out), score_y)
        if loss < best_loss - 1e-4:
            best_loss = loss
            best_epoch = epoch + 1
            stall = 0
            best_state = (
                weights_in.copy(),
                bias_in.copy(),
                weights_out.copy(),
                bias_out.copy(),
            )
        else:
            stall += 1
            if validation and stall >= patience:
                break

    if best_state is None:
        best_state = (weights_in, bias_in, weights_out, bias_out)
    weights_in, bias_in, weights_out, bias_out = best_state
    return {
        "version": 1,
        "kind": "mlp",
        "feature_names": list(names),
        "labels": list(ACTION_LABELS),
        "hidden": hidden,
        "activation": "relu",
        "W1": weights_in.tolist(),
        "b1": bias_in.tolist(),
        "W2": weights_out.tolist(),
        "b2": bias_out.tolist(),
        "training": {
            "epochs_ran": best_epoch,
            "hidden": hidden,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "l2": l2,
            "patience": patience,
            "seed": seed,
            "class_weighted": False,
            "counts": counts,
            "selection_loss": round(best_loss, 6),
            "selection": "validation" if validation else "last_epoch",
        },
    }


def predict_proba(
    features: np.ndarray,
    weights_in: np.ndarray,
    bias_in: np.ndarray,
    weights_out: np.ndarray,
    bias_out: np.ndarray,
) -> np.ndarray:
    """Class probabilities, columns in ``ACTION_LABELS`` order."""
    hidden = np.maximum(features @ weights_in + bias_in, 0.0)
    return _softmax(hidden @ weights_out + bias_out)


def log_loss(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """Mean natural-log loss. One row per decision, equal weight."""
    chosen = probabilities[np.arange(labels.shape[0]), labels]
    return float(-np.mean(np.log(np.clip(chosen, 1e-12, 1.0))))


def save_mlp(path: Path, document: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return destination


def _matrix(samples: list[tuple[tuple[float, ...], str]]) -> tuple[np.ndarray, np.ndarray]:
    features = np.asarray([row for row, _label in samples], dtype=np.float64)
    index = {label: position for position, label in enumerate(ACTION_LABELS)}
    try:
        labels = np.asarray([index[label] for _row, label in samples], dtype=np.int64)
    except KeyError as exc:
        raise ValueError(f"label {exc.args[0]!r} is outside {ACTION_LABELS}") from exc
    return features, labels


def _gradients(
    features: np.ndarray,
    labels: np.ndarray,
    weights_in: np.ndarray,
    bias_in: np.ndarray,
    weights_out: np.ndarray,
    bias_out: np.ndarray,
    l2: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pre = features @ weights_in + bias_in
    hidden = np.maximum(pre, 0.0)
    probabilities = _softmax(hidden @ weights_out + bias_out)
    residual = probabilities.copy()
    residual[np.arange(labels.shape[0]), labels] -= 1.0
    residual /= labels.shape[0]
    grad_w2 = hidden.T @ residual + l2 * weights_out
    grad_b2 = residual.sum(axis=0)
    backward = residual @ weights_out.T
    backward *= pre > 0.0
    grad_w1 = features.T @ backward + l2 * weights_in
    grad_b1 = backward.sum(axis=0)
    return grad_w1, grad_b1, grad_w2, grad_b2


def _adam(
    params: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    gradients: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    moment: list[np.ndarray],
    velocity: list[np.ndarray],
    step: int,
    learning_rate: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    beta1 = 0.9
    beta2 = 0.999
    epsilon = 1e-8
    updated: list[np.ndarray] = []
    for index, (param, grad) in enumerate(zip(params, gradients, strict=True)):
        moment[index] = beta1 * moment[index] + (1.0 - beta1) * grad
        velocity[index] = beta2 * velocity[index] + (1.0 - beta2) * np.square(grad)
        moment_hat = moment[index] / (1.0 - beta1**step)
        velocity_hat = velocity[index] / (1.0 - beta2**step)
        param = param - learning_rate * moment_hat / (np.sqrt(velocity_hat) + epsilon)
        updated.append(param)
    return updated[0], updated[1], updated[2], updated[3]


def _zeros_like(*arrays: np.ndarray) -> list[np.ndarray]:
    return [np.zeros_like(array) for array in arrays]


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)
