"""The softmax class picks the arrow. Geometry picks the one receiver or carry."""

from demo.options import (
    PRIMARY_ALPHA,
    SECONDARY_ALPHA,
    OptionPlayer,
    TacticalOption,
    build_options,
    compose_drawn,
    opponent_goal,
)
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
    assert 1 <= len(options) <= 3
    arrow = options[0]
    assert arrow.kind == "pass"
    assert arrow.primary
    assert arrow.alpha == PRIMARY_ALPHA
    assert sum(not item.primary for item in options) <= 2
    mates = {2: (92.0, 28.0), 3: (70.0, 48.0), 6: (60.0, 34.0)}
    seen: set[int] = set()
    for item in options:
        assert item.kind == "pass"
        assert item.target_id in mates
        assert item.target_id not in seen
        seen.add(item.target_id)
        assert item.target == mates[item.target_id]
        assert item.target != (88.0, 34.0)
        assert item.target != (84.0, 20.0)
        if item.primary:
            assert item.alpha == PRIMARY_ALPHA
        else:
            assert item.alpha == SECONDARY_ALPHA


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
    carries = [item for item in options if item.kind == "dribble"]
    passes = [item for item in options if item.kind == "pass"]
    assert len(carries) == 1
    assert len(passes) <= 1
    carry = carries[0]
    assert carry.primary
    assert carry.alpha == PRIMARY_ALPHA
    assert carry.target_id is None
    assert carry.target[0] < 20.0
    length = ((carry.target[0] - 20.0) ** 2 + (carry.target[1] - 34.0) ** 2) ** 0.5
    assert length < 9.0
    # Not a pass drawn at the teammate standing on the left.
    assert abs(carry.target[0] - 12.0) > 1.0 or abs(carry.target[1] - 40.0) > 1.0
    for alt in passes:
        assert not alt.primary
        assert alt.alpha == SECONDARY_ALPHA
        assert alt.target_id == 2
        assert alt.target == (12.0, 40.0)


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
        assert options
        assert options[0].primary
        assert options[0].kind == recommended
        assert sum(item.kind == "dribble" for item in options) <= 1
        for item in options:
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
    assert options
    arrow = options[0]
    dump = ((56.0 - 50.0) ** 2 + (42.0 - 34.0) ** 2) ** 0.5
    progressive = 76.0 - 50.0
    assert progressive > dump + 10.0
    assert arrow.target_id == 3
    assert arrow.target == (76.0, 34.0)
    assert arrow.primary
    assert all(item.target_id in {2, 3} for item in options)
    assert sum(item.kind == "dribble" for item in options) == 0


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
    carries = [item for item in options if item.kind == "dribble"]
    assert len(carries) == 1
    assert len(options) <= 2
    carry = carries[0]
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


def test_pass_primary_plus_at_most_two_teammate_secondaries() -> None:
    players = [
        OptionPlayer(1, (40.0, 34.0), "home"),
        OptionPlayer(2, (52.0, 24.0), "home"),
        OptionPlayer(3, (58.0, 40.0), "home"),
        OptionPlayer(4, (48.0, 48.0), "home"),
        OptionPlayer(5, (70.0, 30.0), "home"),
        OptionPlayer(8, (90.0, 34.0), "away"),
        OptionPlayer(9, (55.0, 10.0), "away", role="goalkeeper"),
    ]
    options = build_options(
        (40.0, 34.0),
        players,
        possessor_id=1,
        possessor_team="home",
        recommended="pass",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    assert len(options) == 3
    assert options[0].primary and options[0].alpha == PRIMARY_ALPHA
    assert sum(not item.primary for item in options) == 2
    mate_xy = {player.track_id: player.xy for player in players if player.team == "home" and player.track_id != 1}
    for item in options:
        assert item.kind == "pass"
        assert item.target_id in mate_xy
        assert item.target == mate_xy[item.target_id]
        assert item.target_id not in {8, 9}
    assert options[0].score >= options[1].score >= options[2].score


def test_dribble_draws_one_carry_and_at_most_one_visible_pass() -> None:
    options = build_options(
        (30.0, 34.0),
        [
            OptionPlayer(1, (30.0, 34.0), "home"),
            OptionPlayer(2, (44.0, 22.0), "home"),
            OptionPlayer(3, (48.0, 46.0), "home"),
            OptionPlayer(7, (60.0, 34.0), "away"),
        ],
        possessor_id=1,
        possessor_team="home",
        recommended="dribble",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    carries = [item for item in options if item.kind == "dribble"]
    passes = [item for item in options if item.kind == "pass"]
    assert len(carries) == 1
    assert carries[0].primary and carries[0].target_id is None
    assert len(passes) == 1
    assert not passes[0].primary
    assert passes[0].alpha == SECONDARY_ALPHA
    assert passes[0].target_id in {2, 3}
    assert passes[0].target == {2: (44.0, 22.0), 3: (48.0, 46.0)}[passes[0].target_id]


def test_compose_drops_passes_that_are_not_live_teammates() -> None:
    held = [
        TacticalOption("pass", (40.0, 34.0), (90.0, 34.0), 5.0, True, PRIMARY_ALPHA, "pass", 8, "pass:8"),
    ]
    fresh = [
        TacticalOption("pass", (40.0, 34.0), (52.0, 24.0), 4.0, True, PRIMARY_ALPHA, "pass", 2, "pass:2"),
        TacticalOption("pass", (40.0, 34.0), (70.0, 34.0), 3.0, False, SECONDARY_ALPHA, "pass", 4, "pass:4"),
        TacticalOption("shoot", (40.0, 34.0), (105.0, 34.0), 9.0, True, PRIMARY_ALPHA, "shot", None, "shoot"),
        TacticalOption("dribble", (40.0, 34.0), (46.0, 30.0), 2.0, False, SECONDARY_ALPHA, "carry", None, "dribble:10"),
    ]
    # The held id is an opponent. Nothing is drawn, including the fresh passes.
    assert compose_drawn("pass", held, fresh, teammates={2: (52.0, 24.0)}) == []
    redrawn = compose_drawn(
        "pass",
        [TacticalOption("pass", (40.0, 34.0), (1.0, 1.0), 5.0, True, 0.2, "pass", 2, "pass:2")],
        fresh,
        teammates={2: (52.0, 24.0)},
    )
    assert len(redrawn) == 1
    assert redrawn[0].primary
    assert redrawn[0].target_id == 2
    assert redrawn[0].target == (52.0, 24.0)
    assert redrawn[0].alpha == PRIMARY_ALPHA
    assert all(item.kind == "pass" for item in redrawn)


def test_compose_dribble_keeps_the_held_carry_and_one_pass() -> None:
    held = [
        TacticalOption("dribble", (30.0, 34.0), (38.0, 28.0), 3.0, True, PRIMARY_ALPHA, "carry", None, "dribble:-20"),
    ]
    fresh = [
        TacticalOption("dribble", (30.0, 34.0), (39.0, 40.0), 4.0, True, PRIMARY_ALPHA, "carry", None, "dribble:20"),
        TacticalOption("dribble", (30.0, 34.0), (36.0, 34.0), 1.0, False, SECONDARY_ALPHA, "carry", None, "dribble:0"),
        TacticalOption("pass", (30.0, 34.0), (44.0, 22.0), 6.0, False, SECONDARY_ALPHA, "pass", 2, "pass:2"),
        TacticalOption("pass", (30.0, 34.0), (99.0, 10.0), 5.0, False, SECONDARY_ALPHA, "pass", 7, "pass:7"),
        TacticalOption("hold", (30.0, 34.0), (30.0, 34.0), 1.0, True, PRIMARY_ALPHA, "hold", None, "hold"),
    ]
    drawn = compose_drawn("dribble", held, fresh, teammates={2: (44.0, 22.0)})
    assert [item.kind for item in drawn] == ["dribble", "pass"]
    assert drawn[0].primary and drawn[0].slot == "dribble:-20"
    assert drawn[0].target == (38.0, 28.0)
    assert not drawn[1].primary and drawn[1].target_id == 2 and drawn[1].target == (44.0, 22.0)
    assert compose_drawn("shoot", held, fresh, teammates={2: (44.0, 22.0)}) == []
    assert compose_drawn("hold", held, fresh, teammates={2: (44.0, 22.0)}) == []
