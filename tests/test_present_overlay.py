"""The overlay shows every action. It does not crown one of them."""

from inside_the_game.labels import ACTION_LABELS
from inside_the_game.pipeline import run_mvp
from inside_the_game.present.overlay import format_overlay


def test_overlay_lists_all_four_actions() -> None:
    frames = run_mvp()
    assert frames
    for frame in frames:
        actions = tuple(item.action for item in frame.overlay.actions)
        assert actions == ACTION_LABELS
        rendered = format_overlay(frame.overlay).lower()
        assert frame.overlay.disclaimer in format_overlay(frame.overlay)
        assert "optimal" not in rendered
        assert "best action" not in rendered
        for label in ACTION_LABELS:
            assert label in rendered
            assert "arrow" in rendered


def test_overlay_includes_explanation_beside_all_four_probabilities() -> None:
    frames = run_mvp()
    assert frames
    for frame in frames:
        rendered = format_overlay(frame.overlay)
        assert frame.explanation.text.strip()
        assert frame.overlay.explanation == frame.explanation.text
        assert f"explanation: {frame.explanation.text}" in rendered
        for label in ACTION_LABELS:
            probability = frame.distribution.probabilities[label]
            assert f"{label:<7} {probability:0.3f}" in rendered
        lowered = rendered.lower()
        assert "optimal" not in lowered
        assert "best action" not in lowered
        assert "the best" not in lowered
