"""Home-jersey lock: striped kits keep a stable home team id."""

from __future__ import annotations

import pytest

from demo.pipeline import DemoConfig, _team_book
from demo.run import build_config, main
from demo.teams import HOME_JERSEY_ENV, TeamBook, parse_home_jersey


BLACK = (12.0, 12.0, 12.0)
WHITE = (250.0, 250.0, 250.0)
GREEN = (40.0, 240.0, 30.0)
GREEN_2 = (36.0, 230.0, 48.0)
BLUE = (20.0, 40.0, 180.0)
RED = (180.0, 30.0, 30.0)


def _stripe_frame(frame: int) -> list[tuple[int, str, tuple[float, float, float], float]]:
    """Home stripes attack on the right. Neon green defends the left goal.

    The defensive tail would call green ``home``. The colour lock must not.
    """
    stripe_a = WHITE if frame % 2 == 0 else BLACK
    stripe_b = BLACK if frame % 2 == 0 else WHITE
    return [
        (1, "player", stripe_a, 80.0 + (frame % 3)),
        (2, "player", stripe_b, 90.0),
        (3, "player", GREEN, 18.0),
        (4, "player", GREEN_2, 24.0),
    ]


def test_parse_home_jersey_presets_and_rgb() -> None:
    assert parse_home_jersey("white-black") == ((245.0, 245.0, 245.0), (16.0, 16.0, 16.0))
    assert parse_home_jersey("black-white") == ((16.0, 16.0, 16.0), (245.0, 245.0, 245.0))
    assert parse_home_jersey("rgb:10,20,30") == ((10.0, 20.0, 30.0),)
    assert parse_home_jersey("10,20,30") == ((10.0, 20.0, 30.0),)
    assert parse_home_jersey("rgb:1,2,3+rgb:4,5,6") == ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
    assert parse_home_jersey("rgb:1,2,3;white") == ((1.0, 2.0, 3.0), (245.0, 245.0, 245.0))
    assert parse_home_jersey("white+black") == ((245.0, 245.0, 245.0), (16.0, 16.0, 16.0))


def test_parse_home_jersey_rejects_bad_specs() -> None:
    with pytest.raises(ValueError):
        parse_home_jersey("neon")
    with pytest.raises(ValueError):
        parse_home_jersey("rgb:1,2")
    with pytest.raises(ValueError):
        parse_home_jersey("rgb:1,2,300")
    with pytest.raises(ValueError):
        parse_home_jersey("")


def test_locked_stripe_home_id_stays_stable_while_attacking() -> None:
    book = TeamBook(min_separation=20.0, home_jersey=parse_home_jersey("white-black"))
    assert book.home_index == 0
    for frame in range(12):
        labels = book.update(_stripe_frame(frame))
        assert labels[1] == "home"
        assert labels[2] == "home"
        assert labels[3] == "away"
        assert labels[4] == "away"
        assert book.cluster_of[1] == 0
        assert book.cluster_of[2] == 0
        assert book.cluster_of[3] == 1
        assert book.cluster_of[4] == 1
        assert book.home_index == 0


def test_single_rgb_lock_keeps_that_colour_home_on_the_right() -> None:
    samples = [
        (1, "player", BLUE, 90.0),
        (2, "player", BLUE, 92.0),
        (3, "player", RED, 18.0),
        (4, "player", RED, 22.0),
    ]
    book = TeamBook(min_separation=20.0, home_jersey=parse_home_jersey("rgb:20,40,180"))
    labels = book.update(samples)
    assert labels[1] == "home"
    assert labels[2] == "home"
    assert labels[3] == "away"
    assert labels[4] == "away"
    assert book.cluster_of[1] == 0
    assert book.home_index == 0


def test_without_lock_defensive_tail_is_unchanged() -> None:
    """The same stripe fixture still follows the left tail when the lock is unset."""
    samples = _stripe_frame(0)
    unlocked = TeamBook(min_separation=20.0)
    explicit_empty = TeamBook(min_separation=20.0, home_jersey=())
    assert unlocked.home_jersey == ()
    assert explicit_empty.home_jersey == ()
    left = unlocked.update(samples)
    right = explicit_empty.update(samples)
    assert left == right
    # Green is the deeper left side, so the tail rule calls it home.
    assert left[3] == "home"
    assert left[4] == "home"
    # White and black are not forced onto one home id.
    assert left[1] != "home" or left[2] != "home"
    locked = TeamBook(min_separation=20.0, home_jersey=parse_home_jersey("white-black"))
    pinned = locked.update(samples)
    assert pinned[1] == "home" and pinned[2] == "home" and pinned[3] == "away"
    assert pinned != left


def test_without_lock_left_side_colour_is_still_home() -> None:
    book = TeamBook(min_separation=20.0)
    samples = [
        (1, "player", BLUE, 20.0),
        (2, "player", BLUE, 24.0),
        (3, "player", RED, 80.0),
        (4, "player", RED, 90.0),
    ]
    labels = book.update(samples)
    assert labels[1] == "home"
    assert labels[3] == "away"
    assert book.home_jersey == ()


def test_cli_home_jersey_flag_env_and_help(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"not a real mp4")
    output = tmp_path / "out.mp4"
    base = ["--input", str(source), "--output", str(output)]

    config = build_config([*base, "--home-jersey", "white-black"])
    assert config.home_jersey == parse_home_jersey("white-black")
    assert _team_book(config).home_jersey == config.home_jersey
    assert _team_book(config).home_index == 0

    paired = build_config(
        [*base, "--home-jersey", "rgb:245,245,245", "--home-jersey", "rgb:16,16,16"]
    )
    assert paired.home_jersey == ((245.0, 245.0, 245.0), (16.0, 16.0, 16.0))

    monkeypatch.setenv(HOME_JERSEY_ENV, "rgb:9,8,7")
    from_env = build_config(base)
    assert from_env.home_jersey == ((9.0, 8.0, 7.0),)
    # The flag wins over the environment.
    override = build_config([*base, "--home-jersey", "black"])
    assert override.home_jersey == parse_home_jersey("black")

    monkeypatch.delenv(HOME_JERSEY_ENV)
    unset = build_config(base)
    assert unset.home_jersey == ()
    assert DemoConfig(input_path=source, output_path=output).home_jersey == ()
    assert _team_book(unset).home_index is None

    with pytest.raises(SystemExit):
        build_config([*base, "--home-jersey", "not-a-colour"])

    with pytest.raises(SystemExit) as help_exit:
        main(["--help"])
    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    assert "--home-jersey" in help_text
    assert "white-black" in help_text
    assert HOME_JERSEY_ENV in help_text
