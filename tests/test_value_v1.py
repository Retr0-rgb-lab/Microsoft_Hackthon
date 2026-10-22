"""value_v1 features, trainer guard, and the one-route helper.

Hand-built decision points only. No generator run and no long fit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from inside_the_game.features.extract import FEATURE_NAMES
from inside_the_game.features.from_tracking import (
    VALUE_V1_FEATURE_NAMES,
    SynthMatch,
    features_from_tracking,
    features_value_v1,
    guard_value_v1_sample,
    label_decision_point,
    label_value_v1,
)
from inside_the_game.labels import ACTION_LABELS
from inside_the_game.system1.completion import completion_value, expected_threat
from inside_the_game.system1.fit import default_value_v1_weights_path, default_weights_path
from inside_the_game.system1.tracking import ghost_route, decide_from_tracking


ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "src" / "inside_the_game" / "system1" / "weights.json"


@pytest.fixture(scope="module")
def train_main():
    sys.path.insert(0, str(ROOT / "scripts"))
    import train_softmax

    return train_softmax.main


def test_value_v1_features_have_length_10_and_the_documented_scales() -> None:
    assert len(VALUE_V1_FEATURE_NAMES) == 10
    assert VALUE_V1_FEATURE_NAMES[-2:] == ("best_pass_value", "carry_value")
    assert "centrality" not in VALUE_V1_FEATURE_NAMES
    assert "minute" not in VALUE_V1_FEATURE_NAMES
    assert "goal_diff" not in VALUE_V1_FEATURE_NAMES
    assert VALUE_V1_FEATURE_NAMES[:2] == ("ball_x", "ball_y")

    team_of = {"H10": "HOME", "A01": "AWAY", "A02": "AWAY", "A03": "AWAY"}
    frame = _frame(1, 0.0, 0.0, opponents=[("A01", 3.0, 0.0), ("A02", 0.0, 6.0), ("A03", 12.0, 9.0)])
    event = _event(
        policy="value_v1",
        label_class="pass",
        options=[
            _pass("H08", 0.40, 10.0, offside=False),
            _pass("H07", 0.90, -5.0, offside=False),
            _pass("H06", 0.99, 80.0, offside=True),
            _carry(8.0),
            _shot(0.30),
        ],
    )
    # A later event and a decoy location must not move the vector.
    event["location"] = [40.0, 20.0]
    values = features_value_v1(frame, event, team_of)
    assert len(values) == 10
    assert values == pytest.approx((0.5, 0.5, 0.1, 0.25, 0.90, 0.25, 0.4, 0.30, 0.20, 0.28))
    scaffold = features_from_tracking(frame, event, team_of)
    assert values[0] == pytest.approx(scaffold.ball_x)
    assert values[1] == pytest.approx(scaffold.ball_y)

    later = dict(frame, t_ms=80 * 60_000, score=[3, 0])
    assert features_value_v1(later, event, team_of) == pytest.approx(values)

    home_defending = features_value_v1(
        _frame(-1, 10.0, 4.0, opponents=[("A01", 13.0, 4.0)]),
        dict(event, team_id="HOME", player_id="H10"),
        team_of,
    )
    away_frame = {
        "attack_dir": 1,
        "t_ms": 60_000,
        "score": [0, 0],
        "ball": [10.0, 4.0, 0.0, 0.0, 0.0, 0.0],
        "players": [
            ["A01", 10.0, 4.0, 0.0, 0.0, 0.0],
            ["H10", 13.0, 4.0, 0.0, 0.0, 0.0],
        ],
    }
    away_attacking = features_value_v1(
        away_frame,
        dict(event, team_id="AWAY", player_id="A01"),
        {"H10": "HOME", "A01": "AWAY"},
    )
    assert home_defending[0] == pytest.approx(away_attacking[0])
    assert home_defending[1] == pytest.approx(away_attacking[1])
    assert home_defending[0] == pytest.approx(42.5 / 105.0)
    assert home_defending[1] == pytest.approx(30.0 / 68.0)

    bare = features_value_v1(
        frame,
        _event(policy="value_v1", label_class="hold", options=[_pass("H08", 0.2, -3.0, offside=True)]),
        team_of,
    )
    assert bare[4:] == pytest.approx((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    long_event = _event(
        policy="value_v1",
        label_class="dribble",
        options=[_pass("H08", 0.5, 100.0, offside=False), _carry(50.0), _shot(0.02)],
    )
    far = features_value_v1(
        _frame(1, 0.0, 0.0, opponents=[("A01", 45.0, 0.0)]),
        long_event,
        {"H10": "HOME", "A01": "AWAY"},
    )
    assert far[2] == pytest.approx(1.0)
    assert far[5] == pytest.approx(1.0)
    assert far[6] == pytest.approx(1.0)
    on_radius = features_value_v1(
        _frame(1, 0.0, 0.0, opponents=[("A01", 5.0, 0.0)]),
        long_event,
        {"H10": "HOME", "A01": "AWAY"},
    )
    assert on_radius[2] == pytest.approx(5.0 / 30.0)
    assert on_radius[3] == pytest.approx(0.0)
    close_ids = [f"A{index:02d}" for index in range(1, 6)]
    crowded = _frame(
        1,
        0.0,
        0.0,
        opponents=[(player_id, 0.4 * (index + 1), 0.0) for index, player_id in enumerate(close_ids)],
    )
    packed = features_value_v1(
        crowded,
        long_event,
        {"H10": "HOME", **{player_id: "AWAY" for player_id in close_ids}},
    )
    assert packed[3] == pytest.approx(1.0)


def test_value_v1_label_is_label_class_not_the_heuristic() -> None:
    team_of = {"H10": "HOME", "A01": "AWAY"}
    frame = _frame(1, 0.0, 0.0, opponents=[("A01", 10.0, 0.0)])
    event = _event(
        policy="value_v1",
        label_class="hold",
        chosen_index=0,
        options=[_carry(12.0)],
    )
    assert label_value_v1(event) == "hold"
    assert label_decision_point(event, frame, team_of) == "dribble"
    heuristic = dict(event, policy="heuristic_v0")
    heuristic.pop("label_class")
    with pytest.raises(ValueError, match="heuristic_v0"):
        label_value_v1(heuristic)


def test_value_v1_trainer_guard_refuses_heuristic_v0() -> None:
    match = _guard_match(
        "train/seed-1001",
        match_id="SYN-VALUE-1001",
        seed=1001,
        policy="heuristic_v0",
    )
    with pytest.raises(ValueError, match="heuristic_v0"):
        guard_value_v1_sample(match)


def test_value_v1_trainer_guard_refuses_holdout_ids_seeds_and_paths() -> None:
    base = _guard_match("train/seed-1001", match_id="SYN-VALUE-1001", seed=1001, policy="value_v1", label_class="pass")
    with pytest.raises(ValueError, match="SYN-HOLDOUT-0001"):
        guard_value_v1_sample(
            SynthMatch(base.root, dict(base.metadata, match_id="SYN-HOLDOUT-0001"), base.frames_by_id, base.events)
        )
    with pytest.raises(ValueError, match="SYN-HOLDOUT-0002"):
        guard_value_v1_sample(
            SynthMatch(base.root, dict(base.metadata, match_id="SYN-HOLDOUT-0002"), base.frames_by_id, base.events)
        )
    with pytest.raises(ValueError, match="9001"):
        guard_value_v1_sample(
            SynthMatch(base.root, dict(base.metadata, seed=9001), base.frames_by_id, base.events)
        )
    with pytest.raises(ValueError, match="9002"):
        guard_value_v1_sample(
            SynthMatch(base.root, dict(base.metadata, seed=9002), base.frames_by_id, base.events)
        )
    held = SynthMatch(
        Path("touchline/scripts/synth/data/holdout/seed-1001"),
        dict(base.metadata),
        base.frames_by_id,
        base.events,
    )
    with pytest.raises(ValueError, match="holdout"):
        guard_value_v1_sample(held)


def test_ghost_route_returns_the_pass_path_and_nothing_for_hold() -> None:
    team_of = {"H10": "HOME", "H08": "HOME", "H09": "HOME", "A04": "AWAY", "A05": "AWAY"}
    frame = {
        "attack_dir": 1,
        "t_ms": 1000,
        "score": [0, 0],
        "ball": [10.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "players": [
            ["H10", 10.0, 0.0, 0.0, 0.0, 0.0],
            ["H08", 22.0, 4.0, 0.0, 0.0, 0.0],
            ["H09", 18.0, -6.0, 0.0, 0.0, 0.0],
            ["A04", 50.0, 0.0, 0.0, 0.0, 0.0],
            ["A05", 14.0, 5.0, 0.0, 0.0, 0.0],
        ],
    }
    event = _event(
        policy="value_v1",
        label_class="pass",
        player_id="H10",
        options=[
            _pass("H08", 0.80, 12.0, offside=False, end=(22.0, 4.0), option_id="o1"),
            _pass("H09", 0.55, 6.0, offside=False, end=(18.0, -6.0), option_id="o2"),
            _pass("H08", 0.99, 30.0, offside=True, end=(40.0, 0.0), option_id="o-off"),
            _carry(5.0, end=(16.0, 1.0)),
            _shot(0.25, end=(52.5, 0.0)),
        ],
    )
    decision = decide_from_tracking(frame, event, team_of)
    assert set(decision) >= {"primary_pass", "secondary_pass", "carry"}
    assert decision["primary_pass"] is not None
    ghost_pass = ghost_route(frame, event, team_of, "pass")
    assert ghost_pass is not None
    assert ghost_pass["target_id"] == "H08"
    assert ghost_pass["score"] == pytest.approx(0.80 * 12.0)
    assert ghost_route(frame, event, team_of, "hold") is None
    assert ghost_route(frame, event, team_of, "dribble") == decision["carry"]

    shot = ghost_route(frame, event, team_of, "shoot")
    assert shot is not None
    assert shot["path"][0] == [10.0, 0.0]
    assert shot["path"][-1] == [52.5, 0.0]
    assert shot["score"] == pytest.approx(0.25 * 0.80)
    mouth = float(expected_threat(np.asarray([52.5]), np.asarray([0.0]))[0])
    assert mouth == pytest.approx(0.80)
    controlled = completion_value([(52.5, 0.0)], frame, "HOME", team_of)[0]
    assert shot["score"] != pytest.approx(controlled)


def test_value_v1_cli_refuses_a_missing_directory(tmp_path: Path, train_main, capsys: pytest.CaptureFixture[str]) -> None:
    before = WEIGHTS.read_bytes()
    value_path = default_value_v1_weights_path()
    before_value = value_path.stat().st_mtime if value_path.exists() else None
    missing = tmp_path / "no-such-value-v1"
    with pytest.raises(SystemExit) as caught:
        train_main(["--value-v1", "--sample", str(missing), "--steps", "500"])
    assert caught.value.code == 2
    error = capsys.readouterr().err
    assert "does not exist" in error
    assert "No weights were written" in error
    assert WEIGHTS.read_bytes() == before
    value_path = default_value_v1_weights_path()
    if value_path.exists():
        assert value_path.stat().st_mtime == before_value
    assert value_path != default_weights_path()


def test_value_v1_cli_refuses_heuristic_v0_without_writing(
    tmp_path: Path,
    train_main,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = WEIGHTS.read_bytes()
    sample = tmp_path / "heuristic-clip"
    _write_match(sample, match_id="SYN-VALUE-1001", seed=1001, rows=[("heuristic_v0", "pass", 0)])
    output = tmp_path / "should-not-exist.json"
    with pytest.raises(SystemExit) as caught:
        train_main(["--value-v1", "--sample", str(sample), "--output", str(output), "--steps", "1"])
    assert caught.value.code == 2
    assert "heuristic_v0" in capsys.readouterr().err
    assert not output.exists()
    assert WEIGHTS.read_bytes() == before


def test_value_v1_cli_fits_unweighted_eight_features_away_from_weights_json(
    tmp_path: Path,
    train_main,
) -> None:
    before = WEIGHTS.read_bytes()
    sample = tmp_path / "value-clip"
    _write_match(
        sample,
        match_id="SYN-VALUE-1001",
        seed=1001,
        rows=[("value_v1", label, index * 1000) for index, label in enumerate(ACTION_LABELS)],
    )
    output = tmp_path / "weights_value_v1.json"
    train_main(["--value-v1", "--sample", str(sample), "--output", str(output), "--steps", "2"])
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["feature_names"] == list(VALUE_V1_FEATURE_NAMES)
    assert document["feature_names"] != list(FEATURE_NAMES)
    assert document["training"]["class_weighted"] is False
    assert document["policy"] == "value_v1"
    assert all(len(document["weights"][label]) == len(VALUE_V1_FEATURE_NAMES) for label in ACTION_LABELS)
    assert WEIGHTS.read_bytes() == before
    assert output.resolve() != WEIGHTS.resolve()


def _guard_match(
    root: str,
    *,
    match_id: str,
    seed: int,
    policy: str,
    label_class: str | None = None,
) -> SynthMatch:
    event: dict = {
        "type": "decision_point",
        "event_id": "e1",
        "policy": policy,
        "team_id": "HOME",
        "player_id": "H10",
    }
    if label_class is not None:
        event["label_class"] = label_class
    return SynthMatch(
        root=Path(root),
        metadata={"match_id": match_id, "seed": seed, "frame_hz": 10},
        frames_by_id={},
        events=(event,),
    )


def _frame(
    attack_dir: int,
    ball_x: float,
    ball_y: float,
    *,
    opponents: list[tuple[str, float, float]],
) -> dict:
    players = [["H10", ball_x, ball_y, 0.0, 0.0, 0.0]]
    players.extend([player_id, x, y, 0.0, 0.0, 0.0] for player_id, x, y in opponents)
    return {
        "attack_dir": attack_dir,
        "t_ms": 60_000,
        "score": [0, 0],
        "ball": [ball_x, ball_y, 0.0, 0.0, 0.0, 0.0],
        "players": players,
    }


def _event(
    *,
    policy: str,
    label_class: str,
    options: list[dict],
    player_id: str = "H10",
    chosen_index: int = 0,
) -> dict:
    return {
        "type": "decision_point",
        "event_id": "e-hand",
        "match_id": "hand",
        "policy": policy,
        "label_class": label_class,
        "team_id": "HOME",
        "player_id": player_id,
        "available_at_ms": 60_000,
        "chosen_index": chosen_index,
        "options": options,
    }


def _pass(
    target: str,
    success: float,
    progress: float,
    *,
    offside: bool,
    end: tuple[float, float] = (1.0, 0.0),
    option_id: str = "pass",
) -> dict:
    return {
        "option_id": option_id,
        "type": "pass",
        "target_player_id": target,
        "end_location": [end[0], end[1]],
        "success_prob": success,
        "progress_m": progress,
        "offside": offside,
    }


def _carry(progress: float, *, end: tuple[float, float] = (2.0, 0.0)) -> dict:
    return {
        "option_id": "carry",
        "type": "carry",
        "target_player_id": None,
        "end_location": [end[0], end[1]],
        "success_prob": 0.7,
        "progress_m": progress,
        "offside": False,
    }


def _shot(xg: float, *, end: tuple[float, float] = (52.5, 0.0)) -> dict:
    return {
        "option_id": "shot",
        "type": "shot",
        "target_player_id": None,
        "end_location": [end[0], end[1]],
        "success_prob": xg,
        "progress_m": 20.0,
        "offside": False,
    }


def _write_match(root: Path, *, match_id: str, seed: int, rows: list[tuple[str, str, int]]) -> None:
    root.mkdir(parents=True)
    metadata = {
        "synthetic": True,
        "fictional_entities": True,
        "match_id": match_id,
        "seed": seed,
        "frame_hz": 10,
        "coordinate_system": {
            "origin": "centre_spot",
            "pitch_length_m": 105,
            "pitch_width_m": 68,
        },
        "players": [
            {"player_id": "H10", "team_id": "HOME"},
            {"player_id": "A01", "team_id": "AWAY"},
        ],
    }
    events: list[str] = []
    frames: list[str] = []
    for index, (policy, label, t_ms) in enumerate(rows):
        frame_id = int(round(t_ms * 10 / 1000.0))
        event = {
            "type": "decision_point",
            "event_id": f"e{index}",
            "policy": policy,
            "label_class": label,
            "team_id": "HOME",
            "player_id": "H10",
            "available_at_ms": t_ms,
            "chosen_index": 0,
            "options": [],
        }
        frame = {
            "frame_id": frame_id,
            "t_ms": t_ms,
            "attack_dir": 1,
            "score": [0, 0],
            "ball": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "players": [
                ["H10", 0.0, 0.0, 0.0, 0.0, 0.0],
                ["A01", 4.0, 0.0, 0.0, 0.0, 0.0],
            ],
        }
        events.append(json.dumps(event))
        frames.append(json.dumps(frame))
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "events.jsonl").write_text("\n".join(events) + "\n", encoding="utf-8")
    (root / "tracking.jsonl").write_text("\n".join(frames) + "\n", encoding="utf-8")
