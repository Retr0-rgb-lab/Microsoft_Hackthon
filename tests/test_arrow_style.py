"""Only the primary pass or carry is drawable."""

from demo.render import ArrowDraw, arrows_to_draw


def test_secondary_shoot_and_hold_are_not_drawn() -> None:
    arrows = [
        ArrowDraw("pass", ((0.0, 0.0), (10.0, 0.0)), True, "pass"),
        ArrowDraw("pass", ((0.0, 0.0), (4.0, 2.0)), False, "pass"),
        ArrowDraw("dribble", ((0.0, 0.0), (3.0, 1.0)), True, "carry"),
        ArrowDraw("shoot", ((0.0, 0.0), (20.0, 0.0)), True, "shot"),
        ArrowDraw("hold", ((0.0, 0.0), (0.0, 0.0)), True, "hold"),
        ArrowDraw("pass", ((0.0, 0.0),), True, "pass"),
    ]
    drawn = arrows_to_draw(arrows)
    assert [arrow.kind for arrow in drawn] == ["pass", "dribble"]
    assert all(arrow.primary for arrow in drawn)
