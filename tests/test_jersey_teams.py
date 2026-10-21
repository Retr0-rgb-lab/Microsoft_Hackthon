"""Jersey sampling and the pass colour gate.

The home-kit lock lives on ``TeamBook(home_jersey=...)``. These tests cover
the torso sample (neon must survive the grass mask) and the rule that a pass
may not pin a shirt that is not the possessor's kit.
"""

from __future__ import annotations

import numpy as np

from demo.options import PRIMARY_ALPHA, OptionPlayer, build_options
from demo.pipeline import _jersey_colors
from demo.stabilize import OverlayMemory
from demo.teams import TeamBook, is_pitch_grass, jerseys_match, parse_home_jersey, summarize_jersey
from demo.tracking import TrackState


WHITE = (220.0, 220.0, 220.0)
BLACK = (28.0, 28.0, 30.0)
GRAY = (120.0, 120.0, 122.0)
NEON = (45.0, 230.0, 55.0)
NEON_DARK = (25.0, 185.0, 40.0)
NEON_2 = (70.0, 245.0, 80.0)
GRASS = (96.0, 162.0, 72.0)
GRASS_BRIGHT = (140.0, 210.0, 100.0)
GRASS_HOT = (105.0, 195.0, 75.0)
BLUE = (20.0, 40.0, 180.0)
BLUE_SHADE = (30.0, 55.0, 160.0)
RED = (180.0, 30.0, 30.0)

# Same anchors the home-jersey lock compares. A stripe median has to land
# near one of them or the lock opens a second cluster for the home kit.
STRIPE_WHITE = (250.0, 250.0, 250.0)
STRIPE_BLACK = (12.0, 12.0, 12.0)
BROADCAST_NEON = (40.0, 240.0, 30.0)


def _legacy_grass(rgb: tuple[float, float, float]) -> bool:
    red, green, blue = rgb
    return green > 70.0 and green > red + 25.0 and green > blue + 25.0


def _pass(players: list[OptionPlayer]):
    return build_options(
        (50.0, 34.0),
        players,
        possessor_id=1,
        possessor_team="home",
        recommended="pass",
        bounds=(105.0, 68.0),
        attacking_positive=True,
        space="pitch",
    )


def test_hsv_chroma_gate_keeps_neon_and_drops_pitch_green() -> None:
    assert _legacy_grass(NEON) and _legacy_grass(GRASS)
    assert not is_pitch_grass(NEON)
    assert not is_pitch_grass(NEON_2)
    assert is_pitch_grass(GRASS)
    assert is_pitch_grass(GRASS_BRIGHT)
    assert is_pitch_grass(GRASS_HOT)
    assert not is_pitch_grass(WHITE)
    assert not is_pitch_grass(BLACK)

    neon_crop = [NEON] * 48 + [WHITE] * 10 + [GRASS] * 36
    summary = summarize_jersey(neon_crop)
    assert summary is not None
    assert jerseys_match(summary, NEON)
    assert not jerseys_match(summary, WHITE)
    legacy_kept = [pixel for pixel in neon_crop if not _legacy_grass(pixel)]
    assert legacy_kept == [WHITE] * 10

    stripes = summarize_jersey([WHITE] * 25 + [BLACK] * 15 + [GRASS] * 30)
    assert stripes is not None
    assert jerseys_match(stripes, WHITE)
    assert jerseys_match(stripes, BLACK)
    assert not jerseys_match(stripes, NEON)
    assert summarize_jersey([GRASS] * 40) is None


def test_lab_chroma_gate_matches_stripes_and_rejects_neon() -> None:
    assert jerseys_match(WHITE, BLACK)
    assert jerseys_match(WHITE, GRAY)
    assert jerseys_match(GRAY, BLACK)
    assert jerseys_match(NEON, NEON_DARK)
    assert jerseys_match(BLUE, BLUE_SHADE)
    assert not jerseys_match(WHITE, NEON)
    assert not jerseys_match(BLACK, NEON)
    assert not jerseys_match(GRAY, NEON)
    assert not jerseys_match(WHITE, GRASS)
    assert not jerseys_match(BLUE, RED)
    assert not jerseys_match(WHITE, None)
    assert not jerseys_match(None, NEON)
    assert jerseys_match(None, None)


def test_pass_rejects_a_mislabeled_neon_and_keeps_the_stripe() -> None:
    options = _pass(
        [
            OptionPlayer(1, (50.0, 34.0), "home", jersey=WHITE),
            OptionPlayer(8, (62.0, 34.0), "home", jersey=NEON),
            OptionPlayer(2, (72.0, 46.0), "home", jersey=GRAY),
            OptionPlayer(9, (90.0, 20.0), "away", jersey=NEON),
        ]
    )
    assert len(options) == 1
    assert options[0].target_id == 2
    assert options[0].primary
    assert options[0].alpha == PRIMARY_ALPHA
    assert options[0].target == (72.0, 46.0)


def test_secondary_passes_skip_the_other_kit() -> None:
    options = _pass(
        [
            OptionPlayer(1, (40.0, 34.0), "home", jersey=WHITE),
            OptionPlayer(2, (52.0, 24.0), "home", jersey=GRAY),
            OptionPlayer(3, (58.0, 40.0), "home", jersey=BLACK),
            OptionPlayer(8, (70.0, 30.0), "home", jersey=NEON),
            OptionPlayer(9, (90.0, 34.0), "away", jersey=NEON),
        ]
    )
    assert options
    assert options[0].primary
    assert all(item.kind == "pass" for item in options)
    assert all(item.target_id in {2, 3} for item in options)
    assert all(item.target_id != 8 for item in options)
    assert sum(not item.primary for item in options) <= 2


def test_dribble_secondary_pass_obeys_the_jersey_gate() -> None:
    options = build_options(
        (30.0, 34.0),
        [
            OptionPlayer(1, (30.0, 34.0), "home", jersey=WHITE),
            OptionPlayer(2, (44.0, 22.0), "home", jersey=NEON),
            OptionPlayer(3, (48.0, 46.0), "home", jersey=GRAY),
            OptionPlayer(7, (60.0, 34.0), "away", jersey=NEON),
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
    assert len(carries) == 1 and carries[0].primary
    assert len(passes) == 1
    assert not passes[0].primary
    assert passes[0].target_id == 3


def test_pass_is_empty_when_every_in_range_shirt_is_the_other_kit() -> None:
    options = _pass(
        [
            OptionPlayer(1, (50.0, 34.0), "home", jersey=WHITE),
            OptionPlayer(8, (62.0, 34.0), "home", jersey=NEON),
            OptionPlayer(2, (52.5, 34.0), "home", jersey=GRAY),
        ]
    )
    assert options == []


def test_unsampled_receiver_is_rejected_once_the_possessor_shirt_is_known() -> None:
    options = _pass(
        [
            OptionPlayer(1, (50.0, 34.0), "home", jersey=WHITE),
            OptionPlayer(4, (64.0, 34.0), "home", jersey=None),
            OptionPlayer(2, (78.0, 40.0), "home", jersey=GRAY),
        ]
    )
    assert [item.target_id for item in options] == [2]


def test_own_goalkeeper_stays_legal_when_the_shirt_does_not_match() -> None:
    options = _pass(
        [
            OptionPlayer(1, (50.0, 34.0), "home", jersey=WHITE),
            OptionPlayer(7, (22.0, 34.0), "home", role="goalkeeper", jersey=NEON),
            OptionPlayer(8, (58.0, 36.0), "home", jersey=NEON),
        ]
    )
    assert {item.target_id for item in options} == {7}
    assert options[0].target == (22.0, 34.0)


def test_missing_shirts_keep_the_team_label_path() -> None:
    options = _pass(
        [
            OptionPlayer(1, (50.0, 34.0), "home"),
            OptionPlayer(2, (64.0, 34.0), "home"),
            OptionPlayer(3, (70.0, 20.0), "away"),
        ]
    )
    assert len(options) == 1
    assert options[0].target_id == 2


def test_held_pass_drops_when_the_receiver_shirt_is_the_other_kit() -> None:
    players = [
        OptionPlayer(1, (50.0, 34.0), "home", jersey=WHITE),
        OptionPlayer(2, (64.0, 34.0), "home", jersey=GRAY),
    ]
    probs = {"pass": 0.7, "dribble": 0.1, "shoot": 0.1, "hold": 0.1}
    options = _pass(players)
    memory = OverlayMemory()
    _, _, first = memory.apply(
        1, probs, options, players, (50.0, 34.0), "home", (105.0, 68.0), True, "pitch"
    )
    assert len(first) == 1
    assert first[0].target_id == 2
    poisoned = [
        OptionPlayer(1, (50.0, 34.0), "home", jersey=WHITE),
        OptionPlayer(2, (64.0, 34.0), "home", jersey=NEON),
    ]
    _, _, second = memory.apply(
        1, probs, options, poisoned, (50.0, 34.0), "home", (105.0, 68.0), True, "pitch"
    )
    assert second == []


def test_sampled_stripes_stay_on_the_locked_home_cluster() -> None:
    stripes = summarize_jersey([STRIPE_WHITE] * 25 + [STRIPE_BLACK] * 15 + [GRASS] * 30)
    neon = summarize_jersey([BROADCAST_NEON] * 48 + [STRIPE_WHITE] * 10 + [GRASS] * 36)
    assert stripes is not None and neon is not None
    assert all(channel > 200.0 for channel in stripes)
    assert not jerseys_match(stripes, neon)
    book = TeamBook(min_separation=20.0, home_jersey=parse_home_jersey("white-black"))
    labels = book.update(
        [
            (1, "player", stripes, 80.0),
            (2, "player", stripes, 88.0),
            (3, "player", neon, 18.0),
            (4, "player", neon, 24.0),
        ]
    )
    assert labels[1] == "home"
    assert labels[2] == "home"
    assert labels[3] == "away"
    assert labels[4] == "away"
    assert book.cluster_of[1] == 0
    assert book.cluster_of[3] == 1


def test_torso_crop_reports_neon_and_skips_a_grass_only_box() -> None:
    frame = np.zeros((120, 100, 3), dtype=np.uint8)
    frame[:, :] = (72, 162, 96)  # BGR grass
    frame[22:42, 38:62] = (55, 230, 45)  # BGR neon
    frame[22:26, 38:42] = (250, 250, 250)
    neon = TrackState(track_id=1, bbox=(0.0, 0.0, 100.0, 100.0))
    grass = TrackState(track_id=2, bbox=(0.0, 70.0, 100.0, 120.0))
    colors = _jersey_colors(frame, [neon, grass, TrackState(3, (0.0, 0.0, 100.0, 100.0), role="referee")])
    assert 2 not in colors
    assert 3 not in colors
    assert jerseys_match(colors[1], NEON)
    assert not jerseys_match(colors[1], WHITE)
