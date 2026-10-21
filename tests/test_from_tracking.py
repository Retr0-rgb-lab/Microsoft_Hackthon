"""System 1 on a SynthData decision_point: four classes, passes, carry path."""

from __future__ import annotations

import json
import math
import time

import pytest

from inside_the_game.features.extract import FeatureVector
from inside_the_game.features.from_tracking import (
    attack_multiplier,
    attack_player_state,
    features_from_tracking,
    frame_for_decision,
    label_decision_point,
    load_synth_match,
)
from inside_the_game.labels import ACTION_LABELS, PROBABILITY_TOLERANCE
from inside_the_game.system1.completion import completion_value
from inside_the_game.system1.orchestrator import TOOL_NAMES, run_decision_tools
from inside_the_game.system1.policy import SoftmaxActionPolicy
from inside_the_game.system1.tracking import decide_from_tracking
from inside_the_game.system2.foundry import FOUNDRY_DEPLOYMENT


def test_decide_from_tracking_returns_four_class_probs_and_paths() -> None:
    match = load_synth_match()
    event = next(item for item in match.events if item["type"] == "decision_point")
    frame = frame_for_decision(match, event)
    assert frame["t_ms"] == event["available_at_ms"]
    assert int(frame["attack_dir"]) in (1, -1)

    policy = SoftmaxActionPolicy()
    decision = decide_from_tracking(frame, event, match.team_of, policy)
    probabilities = decision["probabilities"]
    assert tuple(probabilities) == ACTION_LABELS
    assert all(value >= 0.0 for value in probabilities.values())
    assert abs(sum(probabilities.values()) - 1.0) <= PROBABILITY_TOLERANCE
    assert probabilities == policy.predict_tracking(frame, event, match.team_of).as_dict()

    primary = decision["primary_pass"]
    secondary = decision["secondary_pass"]
    assert primary is not None and secondary is not None
    assert primary["target_id"] != secondary["target_id"]
    _assert_pitch_path(primary)
    _assert_pitch_path(secondary)
    carry = decision["carry"]
    _assert_pitch_path(carry)
    assert len(carry["path"]) >= 5
    assert carry["target_id"] == event["player_id"]
    assert primary["score"] >= secondary["score"]


def test_section6_flip_points_the_acting_team_toward_positive_x() -> None:
    players = [["H10", 10.0, -4.0, 1.5, -0.5, math.pi / 2]]
    away = attack_multiplier(1, "AWAY")
    assert away == -1
    state = attack_player_state(players, away)
    assert state[0][0] == "H10"
    assert state[0][1] == -10.0
    assert state[0][2] == 4.0
    assert state[0][3] == -1.5
    assert state[0][4] == 0.5
    assert math.isclose(state[0][5], -math.pi / 2, abs_tol=1e-12)

    team_of = {"H10": "HOME", "A01": "AWAY"}
    event = {
        "type": "decision_point",
        "event_id": "e-flip",
        "match_id": "flip",
        "team_id": "HOME",
        "player_id": "H10",
    }
    attacking = features_from_tracking(_frame(1, 10.0, -4.0), event, team_of)
    defending = features_from_tracking(_frame(-1, 10.0, -4.0), event, team_of)
    assert attacking.ball_x == (10.0 + 52.5) / 105.0
    assert defending.ball_x == (-10.0 + 52.5) / 105.0
    assert attacking.ball_x > defending.ball_x
    away_event = dict(event, team_id="AWAY", player_id="A01")
    away_features = features_from_tracking(_frame(1, 10.0, -4.0), away_event, team_of)
    assert away_features.ball_x == defending.ball_x


def test_later_events_are_not_labels_or_inputs() -> None:
    match = load_synth_match()
    decisions = [item for item in match.events if item["type"] == "decision_point"]
    resolved = [item for item in match.events if item["type"] in {"pass", "shot", "carry"}]
    assert resolved
    frame = frame_for_decision(match, decisions[0])
    with pytest.raises(ValueError, match="decision_point"):
        label_decision_point(resolved[0], frame, match.team_of)


def test_completion_score_is_local_and_under_50ms() -> None:
    match = load_synth_match()
    event = next(item for item in match.events if item["type"] == "decision_point")
    frame = frame_for_decision(match, event)
    points = [(float(option["end_location"][0]), float(option["end_location"][1])) for option in event["options"]]
    started = time.perf_counter()
    repeats = 30
    for _ in range(repeats):
        scored = completion_value(points, frame, event["team_id"], match.team_of)
    elapsed = (time.perf_counter() - started) / repeats
    assert elapsed < 0.050
    assert len(scored) == len(points)
    assert all(0.0 <= value <= 1.0 for value in scored)


def test_tools_read_decide_score_and_build_foundry_json() -> None:
    match = load_synth_match()
    event = next(item for item in match.events if item["type"] == "decision_point")
    result = run_decision_tools(match, event)
    assert tuple(step["tool"] for step in result["tools"]) == TOOL_NAMES
    assert result["tools"][0]["t_ms"] == event["available_at_ms"]
    assert result["completion"]["paid_api"] is False
    assert result["completion"]["method"] == "pitch_control_x_xt"
    assert result["completion"]["primary_pass"] == result["decision"]["primary_pass"]["score"]
    assert result["completion"]["secondary_pass"] == result["decision"]["secondary_pass"]["score"]
    assert result["completion"]["carry"] == result["decision"]["carry"]["score"]
    narration = result["narration"]
    assert narration["deployment"] == FOUNDRY_DEPLOYMENT
    assert narration["sent"] is False
    body = json.loads(narration["messages"][1]["content"])
    assert set(body) == {"probabilities", "primary_pass", "secondary_pass", "carry"}
    assert body["probabilities"] == result["decision"]["probabilities"]


def test_fitted_softmax_still_raises_shoot_closer_to_goal() -> None:
    policy = SoftmaxActionPolicy()
    deep = FeatureVector(0.12, 0.5, 1.0, 0.18, 0.5, 0.0)
    box = FeatureVector(0.92, 0.5, 1.0, 0.18, 0.5, 0.0)
    assert policy.predict_features(box).probabilities["shoot"] > policy.predict_features(deep).probabilities["shoot"]


def _frame(attack_dir: int, ball_x: float, ball_y: float) -> dict:
    return {
        "attack_dir": attack_dir,
        "t_ms": 60_000,
        "score": [1, 0],
        "ball": [ball_x, ball_y, 0.0, 0.0, 0.0, 0.0],
        "players": [
            ["H10", ball_x, ball_y, 0.0, 0.0, 0.0],
            ["A01", ball_x + 2.0, ball_y, 0.0, 0.0, 0.0],
        ],
    }


def _assert_pitch_path(path: dict) -> None:
    assert path["target_id"]
    assert len(path["path"]) >= 2
    for point in path["path"]:
        x, y = point
        assert -55.5 <= x <= 55.5
        assert -37.0 <= y <= 37.0
    assert isinstance(path["score"], float)
