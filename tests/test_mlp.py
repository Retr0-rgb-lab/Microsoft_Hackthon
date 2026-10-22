"""The value_v1 network fits a separable sample and does not touch weights.json."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from inside_the_game.labels import ACTION_LABELS
from inside_the_game.system1.fit import default_weights_path
from inside_the_game.system1.mlp import fit_mlp, log_loss, predict_proba


def test_mlp_learns_a_one_hot_pattern_and_sums_to_one() -> None:
    samples: list[tuple[tuple[float, ...], str]] = []
    for index, label in enumerate(ACTION_LABELS):
        for _repeat in range(12):
            row = [0.0, 0.0, 0.0, 0.0]
            row[index] = 1.0
            samples.append((tuple(row), label))
    document = fit_mlp(
        samples,
        hidden=8,
        epochs=40,
        batch_size=16,
        feature_names=("a", "b", "c", "d"),
        seed=1,
    )
    weights_in = np.asarray(document["W1"])
    bias_in = np.asarray(document["b1"])
    weights_out = np.asarray(document["W2"])
    bias_out = np.asarray(document["b2"])
    features = np.eye(4)
    probabilities = predict_proba(features, weights_in, bias_in, weights_out, bias_out)
    assert probabilities.shape == (4, 4)
    assert probabilities.sum(axis=1) == pytest.approx(1.0)
    labels = np.arange(4)
    assert log_loss(probabilities, labels) < 0.4
    assert probabilities.argmax(axis=1).tolist() == labels.tolist()


def test_mlp_refuses_a_missing_class(tmp_path: Path) -> None:
    samples = [((1.0, 0.0), "pass"), ((0.0, 1.0), "shoot")]
    with pytest.raises(ValueError, match="missing labels"):
        fit_mlp(samples, epochs=1, feature_names=("a", "b"))
    assert default_weights_path().exists()
    assert not (tmp_path / "weights.json").exists()
