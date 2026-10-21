"""Arrows and the highlighted action stay put across adjacent frames."""

from demo.options import OptionPlayer, build_options
from demo.stabilize import OverlayMemory


def _players() -> list[OptionPlayer]:
    return [
        OptionPlayer(1, (70.0, 34.0), "home"),
        OptionPlayer(2, (84.0, 28.0), "home"),
        OptionPlayer(3, (78.0, 46.0), "home"),
        OptionPlayer(4, (88.0, 34.0), "away"),
        OptionPlayer(5, (6.0, 34.0), "home", role="goalkeeper"),
        OptionPlayer(6, (101.0, 34.0), "away", role="goalkeeper"),
    ]


def _frame(recommended: str, nudge: float = 0.0) -> list:
    players = [
        OptionPlayer(player.track_id, (player.xy[0], player.xy[1] + nudge), player.team, player.role)
        for player in _players()
    ]
    return build_options(
        (70.0, 34.0 + nudge),
        players,
        possessor_id=1,
        possessor_team="home",
        recommended=recommended,
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )


def test_recommendation_does_not_flip_on_a_one_frame_lead() -> None:
    memory = OverlayMemory(switch_frames=6, lead_margin=0.08, ema=0.3)
    pass_heavy = {"pass": 0.62, "dribble": 0.2, "shoot": 0.1, "hold": 0.08}
    dribble_heavy = {"pass": 0.28, "dribble": 0.5, "shoot": 0.12, "hold": 0.1}
    players = _players()
    options = _frame("pass")
    first, _, arrows = memory.apply(
        1, pass_heavy, options, players, (70.0, 34.0), "home", (105.0, 68.0), True, "pitch"
    )
    assert first == "pass"
    for _ in range(4):
        label, _, arrows = memory.apply(
            1, dribble_heavy, _frame("dribble"), players, (70.0, 34.0), "home", (105.0, 68.0), True, "pitch"
        )
        assert label == "pass"
        assert len(arrows) == 1
        assert arrows[0].primary and arrows[0].kind == "pass"
        assert arrows[0].target_id not in {4, 5, 6}


def test_pass_arrows_keep_the_same_teammates_when_a_new_one_appears() -> None:
    memory = OverlayMemory(enter_frames=4, grace_frames=8)
    players = _players()
    probs = {"pass": 0.7, "dribble": 0.15, "shoot": 0.1, "hold": 0.05}
    options = _frame("pass")
    _, _, first = memory.apply(
        1, probs, options, players, (70.0, 34.0), "home", (105.0, 68.0), True, "pitch"
    )
    assert len(first) == 1
    assert first[0].kind == "pass"
    original = first[0].target_id
    assert original in {2, 3}
    extra = players + [OptionPlayer(9, (86.0, 20.0), "home")]
    intruder = build_options(
        (70.0, 34.0),
        extra,
        possessor_id=1,
        possessor_team="home",
        recommended="pass",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )
    _, _, second = memory.apply(
        1, probs, intruder, extra, (70.0, 34.0), "home", (105.0, 68.0), True, "pitch"
    )
    assert len(second) == 1
    assert second[0].kind == "pass"
    assert second[0].target_id == original
    assert second[0].primary


def test_held_dribble_still_draws_when_this_frame_was_scored_as_a_pass() -> None:
    """The displayed class can lag the raw argmax. The arrow follows the class on screen."""
    memory = OverlayMemory(switch_frames=6, lead_margin=0.08, ema=0.3)
    players = _players()
    dribble_heavy = {"pass": 0.2, "dribble": 0.6, "shoot": 0.1, "hold": 0.1}
    label, _, arrows = memory.apply(
        1, dribble_heavy, _frame("pass"), players, (70.0, 34.0), "home", (105.0, 68.0), True, "pitch"
    )
    assert label == "dribble"
    assert len(arrows) == 1
    assert arrows[0].kind == "dribble"
    assert arrows[0].primary
    assert arrows[0].target_id is None


def test_nearby_frames_keep_the_same_primary_pass() -> None:
    memory = OverlayMemory()
    probs = {"pass": 0.55, "dribble": 0.25, "shoot": 0.12, "hold": 0.08}
    players = _players()
    roster = _players()
    _, _, first = memory.apply(
        1, probs, _frame("pass", 0.0), roster, (70.0, 34.0), "home", (105.0, 68.0), True, "pitch"
    )
    primary = next(item for item in first if item.primary)
    nudged = [
        OptionPlayer(player.track_id, (player.xy[0], player.xy[1] + 0.4), player.team, player.role)
        for player in roster
    ]
    _, _, second = memory.apply(
        1, probs, _frame("pass", 0.4), nudged, (70.0, 34.4), "home", (105.0, 68.0), True, "pitch"
    )
    again = next(item for item in second if item.primary)
    assert again.slot == primary.slot
    assert again.kind == primary.kind
    moved = abs(again.target[0] - primary.target[0]) + abs(again.target[1] - primary.target[1])
    assert moved < 2.0
