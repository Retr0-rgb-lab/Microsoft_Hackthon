"""The softmax class picks the arrow. Geometry picks the one receiver or carry."""

from demo.options import PRIMARY_ALPHA, OptionPlayer, build_options, opponent_goal
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


def test_passes_go_to_one_visible_teammate() -> None:
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
    assert len(options) == 1
    arrow = options[0]
    assert arrow.kind == "pass"
    assert arrow.primary
    assert arrow.alpha == PRIMARY_ALPHA
    assert arrow.target_id in {2, 3, 6}
    assert arrow.target != (88.0, 34.0)
    assert arrow.target != (84.0, 20.0)
    assert arrow.target_id != 4


def test_shoot_and_hold_draw_no_lines() -> None:
    for recommended in ("shoot", "hold"):
        options = build_options(
            (78.0, 34.0),
            _players(),
            possessor_id=1,
            possessor_team="home",
            recommended=recommended,
            bounds=(105.0, 68.0),
            attacking_positive=True,
            space="pitch",
        )
        assert options == []
    assert opponent_goal((105.0, 68.0), True) == (105.0, 34.0)
    assert opponent_goal((105.0, 68.0), False) == (0.0, 34.0)


def test_dribble_is_one_short_carry_toward_the_attack() -> None:
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
    assert len(options) == 1
    carry = options[0]
    assert carry.kind == "dribble"
    assert carry.primary
    assert carry.target_id is None
    assert carry.target[0] < 20.0
    length = ((carry.target[0] - 20.0) ** 2 + (carry.target[1] - 34.0) ** 2) ** 0.5
    assert length < 9.0
    # Not a pass drawn at the teammate standing on the left.
    assert abs(carry.target[0] - 12.0) > 1.0 or abs(carry.target[1] - 40.0) > 1.0


def test_image_fallback_options_stay_in_the_frame() -> None:
    width, height = 1920.0, 1080.0
    players = [
        OptionPlayer(1, (400.0, 700.0), "home"),
        OptionPlayer(2, (900.0, 500.0), "home"),
        OptionPlayer(3, (700.0, 800.0), "away"),
    ]
    for recommended in ("pass", "dribble"):
        options = build_options(
            (400.0, 700.0),
            players,
            possessor_id=1,
            possessor_team="home",
            recommended=recommended,
            bounds=(width, height),
            attacking_positive=True,
            space="image",
        )
        assert len(options) == 1
        item = options[0]
        assert item.kind == recommended
        assert 0.0 <= item.target[0] <= width
        assert 0.0 <= item.target[1] <= height
        assert item.origin == (400.0, 700.0)
    passed = build_options(
        (400.0, 700.0),
        players,
        possessor_id=1,
        possessor_team="home",
        recommended="pass",
        bounds=(width, height),
        attacking_positive=True,
        space="image",
    )
    assert passed[0].target_id == 2


def test_pass_is_pinned_to_a_teammate_and_not_the_keeper_in_the_goal() -> None:
    options = build_options(
        (80.0, 34.0),
        [
            OptionPlayer(1, (80.0, 34.0), "home"),
            OptionPlayer(2, (96.0, 34.0), "home"),
            OptionPlayer(3, (100.0, 34.0), "home", role="goalkeeper"),
            OptionPlayer(4, (90.0, 40.0), "away"),
        ],
        possessor_id=1,
        possessor_team="home",
        recommended="pass",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    assert len(options) == 1
    arrow = options[0]
    assert arrow.kind == "pass"
    assert arrow.primary
    assert arrow.target_id == 2
    assert arrow.target == (96.0, 34.0)


def test_open_progressive_pass_beats_a_tiny_dump() -> None:
    """Clearance, not raw shortness, picks the receiver. Both passes are legal."""
    options = build_options(
        (50.0, 34.0),
        [
            OptionPlayer(1, (50.0, 34.0), "home"),
            OptionPlayer(2, (56.0, 42.0), "home"),
            OptionPlayer(3, (76.0, 34.0), "home"),
            OptionPlayer(8, (58.0, 44.0), "away"),
            OptionPlayer(9, (20.0, 10.0), "away"),
        ],
        possessor_id=1,
        possessor_team="home",
        recommended="pass",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    assert len(options) == 1
    arrow = options[0]
    dump = ((56.0 - 50.0) ** 2 + (42.0 - 34.0) ** 2) ** 0.5
    progressive = 76.0 - 50.0
    assert progressive > dump + 10.0
    assert arrow.target_id == 3
    assert arrow.target == (76.0, 34.0)
    assert arrow.primary


def test_dribble_aims_at_open_space_instead_of_a_player() -> None:
    options = build_options(
        (40.0, 34.0),
        [
            OptionPlayer(1, (40.0, 34.0), "home"),
            OptionPlayer(2, (62.0, 34.0), "home"),
            OptionPlayer(4, (49.0, 34.0), "away"),
            OptionPlayer(5, (51.0, 33.0), "away"),
            OptionPlayer(6, (51.0, 35.0), "away"),
        ],
        possessor_id=1,
        possessor_team="home",
        recommended="dribble",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    assert len(options) == 1
    carry = options[0]
    assert carry.kind == "dribble"
    assert carry.target_id is None
    assert carry.target[0] > 40.0
    # Straight ahead is a wall of opponents, so the carry leaves that line.
    assert abs(carry.target[1] - 34.0) > 2.0
    for player_xy in ((62.0, 34.0), (49.0, 34.0), (51.0, 33.0), (51.0, 35.0)):
        gap = ((carry.target[0] - player_xy[0]) ** 2 + (carry.target[1] - player_xy[1]) ** 2) ** 0.5
        assert gap > 3.2


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
