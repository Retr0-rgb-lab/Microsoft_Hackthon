"""Pitch arrows: one bright primary, at most two dim passes, no shot or hold."""

from demo.render import ArrowDraw, arrows_to_draw


def test_pass_keeps_primary_and_at_most_two_secondaries() -> None:
    arrows = [
        ArrowDraw("pass", ((0.0, 0.0), (10.0, 0.0)), True, "pass", 0.95),
        ArrowDraw("pass", ((0.0, 0.0), (4.0, 2.0)), False, "pass", 0.34),
        ArrowDraw("pass", ((0.0, 0.0), (6.0, -2.0)), False, "pass", 0.34),
        ArrowDraw("pass", ((0.0, 0.0), (8.0, 4.0)), False, "pass", 0.34),
        ArrowDraw("dribble", ((0.0, 0.0), (3.0, 1.0)), False, "carry", 0.34),
        ArrowDraw("shoot", ((0.0, 0.0), (20.0, 0.0)), True, "shot", 0.95),
        ArrowDraw("hold", ((0.0, 0.0), (0.0, 0.0)), True, "hold", 0.95),
        ArrowDraw("pass", ((0.0, 0.0),), False, "pass", 0.34),
    ]
    drawn = arrows_to_draw(arrows)
    assert [arrow.kind for arrow in drawn] == ["pass", "pass", "pass"]
    assert drawn[0].primary
    assert sum(not arrow.primary for arrow in drawn) == 2
    assert all(arrow.kind != "dribble" for arrow in drawn)
    assert all(arrow.kind not in {"shoot", "hold"} for arrow in drawn)


def test_dribble_keeps_one_carry_and_one_pass() -> None:
    arrows = [
        ArrowDraw("dribble", ((0.0, 0.0), (3.0, 1.0)), True, "carry", 0.95),
        ArrowDraw("dribble", ((0.0, 0.0), (2.0, -2.0)), False, "carry", 0.34),
        ArrowDraw("pass", ((0.0, 0.0), (12.0, 4.0)), False, "pass", 0.34),
        ArrowDraw("pass", ((0.0, 0.0), (9.0, 6.0)), False, "pass", 0.34),
        ArrowDraw("shoot", ((0.0, 0.0), (20.0, 0.0)), False, "shot", 0.95),
        ArrowDraw("hold", ((0.0, 0.0), (1.0, 1.0)), False, "hold", 0.95),
    ]
    drawn = arrows_to_draw(arrows)
    assert [arrow.kind for arrow in drawn] == ["dribble", "pass"]
    assert drawn[0].primary and drawn[0].alpha == 0.95
    assert not drawn[1].primary and drawn[1].alpha == 0.34
    assert sum(arrow.kind == "dribble" for arrow in drawn) == 1
    assert all(arrow.kind not in {"shoot", "hold"} for arrow in drawn)


def test_secondaries_without_a_primary_are_not_drawn() -> None:
    arrows = [
        ArrowDraw("pass", ((0.0, 0.0), (10.0, 0.0)), False, "pass", 0.34),
        ArrowDraw("shoot", ((0.0, 0.0), (20.0, 0.0)), True, "shot", 0.95),
        ArrowDraw("hold", ((0.0, 0.0), (0.0, 0.0)), True, "hold", 0.95),
    ]
    assert arrows_to_draw(arrows) == []
