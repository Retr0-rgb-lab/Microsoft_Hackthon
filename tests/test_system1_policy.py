"""System 1 must return a full distribution on the synthetic fixtures."""

from pathlib import Path

from inside_the_game.ingest.loader import load_events
from inside_the_game.labels import ACTION_LABELS, PROBABILITY_TOLERANCE
from inside_the_game.system1.policy import SoftmaxActionPolicy


def test_softmax_policy_on_synthetic_fixtures() -> None:
    events = load_events()
    assert len(events) >= 1
    policy = SoftmaxActionPolicy()
    assert policy.weight_source == "file"

    for event in events:
        _assert_distribution(policy.predict(event).probabilities)


def test_loaded_weights_and_missing_file_stub_are_valid() -> None:
    events = load_events()
    loaded = SoftmaxActionPolicy()
    missing = SoftmaxActionPolicy(weights_path=Path("fixtures/no-such-weights.json"))
    stub = SoftmaxActionPolicy.stub()
    assert loaded.weight_source == "file"
    assert missing.weight_source == "stub"
    assert stub.weight_source == "stub"
    assert missing.predict(events[0]).as_dict() == stub.predict(events[0]).as_dict()
    assert loaded.predict(events[0]).as_dict() != stub.predict(events[0]).as_dict()
    for event in events:
        _assert_distribution(loaded.predict(event).probabilities)
        _assert_distribution(missing.predict(event).probabilities)


def _assert_distribution(probabilities: dict[str, float]) -> None:
    labels = tuple(probabilities)
    values = list(probabilities.values())
    assert labels == ACTION_LABELS
    assert all(value >= 0.0 for value in values)
    assert abs(sum(values) - 1.0) <= PROBABILITY_TOLERANCE
