"""The synthetic generator emits labeled sequences and can train the softmax."""

from __future__ import annotations

from pathlib import Path

from inside_the_game.features.extract import extract_features
from inside_the_game.ingest.loader import load_events
from inside_the_game.ingest.synthetic import generate_events, generate_fixture
from inside_the_game.labels import ACTION_LABELS, PROBABILITY_TOLERANCE
from inside_the_game.system1.fit import fit_softmax, save_linear_weights
from inside_the_game.system1.policy import SoftmaxActionPolicy


FIXTURE = Path("fixtures/synthetic_labeled_sequences.json")


def test_generator_emits_only_the_four_actions() -> None:
    events = generate_events(seed=7)
    assert len(events) >= 40
    labels = [event.action for event in events]
    assert set(labels) == set(ACTION_LABELS)
    for event in events:
        assert event.action in ACTION_LABELS
        features = extract_features(event)
        assert len(features.as_tuple()) == 6
    again = generate_events(seed=7)
    assert [(event.event_id, event.action, event.ball_x, event.minute) for event in events] == [
        (event.event_id, event.action, event.ball_x, event.minute) for event in again
    ]


def test_checked_in_synthetic_fixture_matches_the_generator() -> None:
    payload = generate_fixture(seed=7)
    loaded = load_events(FIXTURE)
    assert loaded
    assert [event.action for event in loaded] == [event["action"] for event in payload["events"]]
    assert [event.event_id for event in loaded] == [event["event_id"] for event in payload["events"]]
    assert set(event.action for event in loaded) == set(ACTION_LABELS)


def test_synthetic_labels_can_train_a_softmax(tmp_path: Path) -> None:
    rows = [
        (extract_features(event).as_tuple(), event.action)
        for event in generate_events(seed=7)
        if event.action is not None
    ]
    fitted = fit_softmax(rows, steps=80, learning_rate=1.0, l2=0.02)
    path = tmp_path / "weights.json"
    save_linear_weights(path, fitted)
    policy = SoftmaxActionPolicy(weights_path=path)
    assert policy.weight_source == "file"
    for event in generate_events(seed=7)[:8]:
        values = list(policy.predict(event).probabilities.values())
        assert all(value >= 0.0 for value in values)
        assert abs(sum(values) - 1.0) <= PROBABILITY_TOLERANCE
