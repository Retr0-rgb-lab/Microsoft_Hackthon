"""The Jev Choice hook is optional and stays on JSON/text state."""

from inside_the_game.ingest.loader import load_events
from inside_the_game.labels import ACTION_LABELS
from inside_the_game.system1.jev import build_choice_request, load_jev_choice


def test_choice_request_uses_text_state_and_four_labels() -> None:
    event = load_events()[0]
    body = build_choice_request(event).to_dict()
    question = body["questions"]["action"]
    assert question["type"] == "choice"
    assert tuple(question["criteria"]) == ACTION_LABELS
    assert isinstance(body["state"], str)
    assert "image" not in body["state"]
    assert "frame" not in body["state"]


def test_missing_jev_sdk_does_not_break_the_hook() -> None:
    hook = load_jev_choice()
    assert hook is None or hasattr(hook, "predict")
