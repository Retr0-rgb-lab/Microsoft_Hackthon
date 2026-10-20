"""System 1 must return a full distribution on the synthetic fixtures."""

from inside_the_game.ingest.loader import load_events
from inside_the_game.labels import ACTION_LABELS, PROBABILITY_TOLERANCE
from inside_the_game.system1.policy import SoftmaxActionPolicy


def test_softmax_policy_on_synthetic_fixtures() -> None:
    events = load_events()
    assert len(events) >= 1
    policy = SoftmaxActionPolicy()

    for event in events:
        distribution = policy.predict(event)
        labels = tuple(distribution.probabilities)
        values = list(distribution.probabilities.values())
        assert labels == ACTION_LABELS
        assert all(value >= 0.0 for value in values)
        assert abs(sum(values) - 1.0) <= PROBABILITY_TOLERANCE
