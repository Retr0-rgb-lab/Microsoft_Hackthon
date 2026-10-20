"""Arrows are the reasonable options; the recommended one is the bright arrow."""

from demo.options import PRIMARY_ALPHA, SECONDARY_ALPHA, OptionPlayer, build_options
from demo.teams import TeamBook


def _players() -> list[OptionPlayer]:
    return [
        OptionPlayer(1, (80.0, 34.0), "home"),
        OptionPlayer(2, (92.0, 28.0), "home"),
        OptionPlayer(3, (70.0, 48.0), "home"),
        OptionPlayer(4, (88.0, 34.0), "away"),
        OptionPlayer(5, (84.0, 20.0), "referee", role="referee"),
        OptionPlayer(6, (60.0, 34.0), "home"),
    ]


def test_passes_go_to_teammates_and_the_shot_uses_the_attacking_goal() -> None:
    options = build_options(
        (78.0, 34.0),
        _players(),
        possessor_id=1,
        possessor_team="home",
        recommended="pass",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    passes = [item for item in options if item.kind == "pass"]
    assert passes
    assert all(target != (88.0, 34.0) for _kind, target in ((item.kind, item.target) for item in passes))
    assert all(item.target != (84.0, 20.0) for item in passes)
    shot = next(item for item in options if item.kind == "shoot")
    assert shot.target == (105.0, 34.0)
    primary = [item for item in options if item.primary]
    assert len(primary) == 1
    assert primary[0].kind == "pass"
    assert primary[0].alpha == PRIMARY_ALPHA
    assert all(item.alpha == SECONDARY_ALPHA for item in options if not item.primary)


def test_away_shot_points_at_the_left_goal_and_dribble_can_be_highlighted() -> None:
    options = build_options(
        (20.0, 34.0),
        [OptionPlayer(1, (20.0, 34.0), "away"), OptionPlayer(2, (12.0, 40.0), "away")],
        possessor_id=1,
        possessor_team="away",
        recommended="dribble",
        bounds=(105.0, 68.0),
        attacking_positive=False,
        space="pitch",
    )
    shot = next(item for item in options if item.kind == "shoot")
    assert shot.target[0] == 0.0
    primary = next(item for item in options if item.primary)
    assert primary.kind == "dribble"
    assert primary.target[0] < 20.0


def test_image_fallback_options_stay_in_the_frame() -> None:
    width, height = 1920.0, 1080.0
    options = build_options(
        (400.0, 700.0),
        [
            OptionPlayer(1, (400.0, 700.0), "home"),
            OptionPlayer(2, (900.0, 500.0), "home"),
            OptionPlayer(3, (700.0, 800.0), "away"),
        ],
        possessor_id=1,
        possessor_team="home",
        recommended="shoot",
        bounds=(width, height),
        attacking_positive=True,
        space="image",
    )
    assert any(item.kind == "shoot" and item.primary for item in options)
    for item in options:
        assert 0.0 <= item.target[0] <= width
        assert 0.0 <= item.target[1] <= height
        assert item.origin == (400.0, 700.0)


def test_shot_stays_on_the_opponent_goal_when_a_teammate_is_nearby() -> None:
    options = build_options(
        (80.0, 34.0),
        [
            OptionPlayer(1, (80.0, 34.0), "home"),
            OptionPlayer(2, (104.0, 34.0), "home"),
            OptionPlayer(3, (100.0, 34.0), "home", role="goalkeeper"),
            OptionPlayer(4, (90.0, 40.0), "away"),
        ],
        possessor_id=1,
        possessor_team="home",
        recommended="shoot",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    passes = [item for item in options if item.kind == "pass"]
    assert passes
    assert all(item.target_id == 2 for item in passes)
    assert all(item.target == (104.0, 34.0) for item in passes)
    shot = next(item for item in options if item.kind == "shoot")
    assert shot.target == (105.0, 34.0)
    assert shot.target not in {item.target for item in passes}
    assert shot.primary


def test_team_colours_lock_the_left_side_as_home() -> None:
    book = TeamBook(min_separation=20.0)
    blue = (20.0, 40.0, 180.0)
    red = (180.0, 30.0, 30.0)
    samples = [
        (1, "player", blue, 20.0),
        (2, "player", blue, 24.0),
        (3, "player", red, 80.0),
        (4, "player", red, 90.0),
        (9, "referee", (240.0, 220.0, 40.0), 50.0),
        (7, "goalkeeper", (10.0, 10.0, 10.0), 4.0),
    ]
    # One pass may only seed the first cluster; a second observation splits them.
    labels = book.update(samples)
    labels = book.update(samples)
    assert labels[9] == "referee"
    assert labels[1] == "home"
    assert labels[3] == "away"
    assert labels[7] == "home"
    assert labels[1] != labels[3]


def test_camped_attack_keeps_the_deep_side_and_the_keepers() -> None:
    """A side camped in the opponent half must not be given that half's goal.

    The mean pitch x of the blue shirts is further right than red, which used
    to label blue as away and aim their shot at their own goal. The deepest
    blue player is still the one beside the left goal.
    """
    book = TeamBook(min_separation=20.0)
    blue = (20.0, 40.0, 180.0)
    red = (180.0, 30.0, 30.0)
    samples = [
        (1, "player", blue, 22.0),
        (2, "player", blue, 90.0),
        (3, "player", blue, 92.0),
        (4, "player", blue, 94.0),
        (5, "player", red, 58.0),
        (6, "player", red, 62.0),
        (7, "player", red, 66.0),
        (8, "player", red, 70.0),
        (11, "goalkeeper", (8.0, 8.0, 8.0), 3.0),
        (12, "goalkeeper", (240.0, 240.0, 240.0), 102.0),
    ]
    labels = book.update(samples)
    assert labels[1] == "home"
    assert labels[5] == "away"
    assert labels[11] == "home"
    assert labels[12] == "away"
    blue_mean = (22.0 + 90.0 + 92.0 + 94.0) / 4.0
    red_mean = (58.0 + 62.0 + 66.0 + 70.0) / 4.0
    assert blue_mean > red_mean


def test_one_bad_colour_frame_does_not_swap_a_teammate() -> None:
    book = TeamBook(min_separation=20.0)
    blue = (20.0, 40.0, 180.0)
    red = (180.0, 30.0, 30.0)
    steady = [
        (1, "player", blue, 20.0),
        (2, "player", red, 85.0),
    ]
    for _ in range(4):
        labels = book.update(steady)
    assert labels[1] == "home"
    swapped = book.update([(1, "player", red, 20.0), (2, "player", red, 85.0)])
    assert swapped[1] == "home"
    assert swapped[2] == "away"
