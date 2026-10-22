"""value_v1 decisions: the chosen option is the value winner, and formation anchors stick."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATE = ROOT / "touchline" / "scripts" / "synth" / "generate.py"
SHOT_GAIN_M = 20
SEED = 1001


def _load_generate():
    spec = importlib.util.spec_from_file_location("synth_generate", GENERATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(out: Path, *extra: str) -> None:
    subprocess.run(
        [sys.executable, str(GENERATE), "--hz", "10", "--seed", str(SEED), "--output", str(out), *extra],
        check=True,
        cwd=ROOT,
    )


def _events(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]


def _option_value(opt: dict) -> float:
    if opt["type"] == "shot":
        return opt["success_prob"] * SHOT_GAIN_M
    return opt["success_prob"] * max(opt["progress_m"], 0)


def _beats(left: dict, right: dict) -> bool:
    """True when left is strictly preferred: higher value, then success_prob, then smaller option_id."""
    lv, rv = _option_value(left), _option_value(right)
    if lv != rv:
        return lv > rv
    if left["success_prob"] != right["success_prob"]:
        return left["success_prob"] > right["success_prob"]
    return left["option_id"] < right["option_id"]


def _nearest_opponent(frame: dict, player_id: str) -> float:
    rows = {row[0]: row for row in frame["players"]}
    me = rows[player_id]
    side = player_id[0]
    best = float("inf")
    for pid, x, y, *_rest in frame["players"]:
        if pid[0] == side:
            continue
        best = min(best, math.hypot(x - me[1], y - me[2]))
    return best


def test_value_v1_selects_the_max_value_option(tmp_path: Path) -> None:
    out = tmp_path / "value_v1"
    _run(out, "--minutes", "2")
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["match_id"] == f"SYN-SINGLE-{SEED}"
    assert str(SEED) in meta["match_id"]
    assert meta["teams"][0]["formation"] == "4-3-3"
    assert meta["teams"][1]["formation"] == "4-3-3"

    events = _events(out)
    frames = {
        json.loads(line)["t_ms"]: json.loads(line)
        for line in (out / "tracking.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    }
    decisions = [event for event in events if event["type"] == "decision_point"]
    shots = {
        event["decision_event_id"]: event
        for event in events
        if event["type"] == "shot" and event.get("decision_event_id")
    }
    assert decisions, "a 2-minute clip should contain at least one decision_point"

    example = None
    for event in decisions:
        assert event["policy"] == "value_v1"
        assert event["match_id"] == meta["match_id"]
        assert event["shot_gain_m"] == SHOT_GAIN_M
        options = event["options"]
        chosen = options[event["chosen_index"]]
        assert chosen["option_id"] == event["chosen_option_id"]
        eligible = [opt for opt in options if not opt["offside"]]
        assert eligible, event["event_id"]
        assert not chosen["offside"]
        assert all(not _beats(other, chosen) for other in eligible)

        values = [_option_value(opt) for opt in eligible]
        all_zero = all(value == 0 for value in values)
        if all_zero:
            assert event["label_class"] == "hold"
            assert event["route_kind"] == ""
            assert event["route_target_id"] is None
            assert event["route_end"] is None
        elif chosen["type"] == "pass":
            assert event["label_class"] == "pass"
            assert event["route_kind"] == "pass"
            assert event["route_target_id"] == chosen["target_player_id"]
            assert event["route_end"] == chosen["end_location"]
        elif chosen["type"] == "shot":
            assert event["label_class"] == "shoot"
            assert event["route_kind"] == "shoot"
            assert event["route_target_id"] is None
            assert event["route_end"] == chosen["end_location"]
            assert abs(abs(event["route_end"][0]) - 52.5) < 1e-6
            shot = shots.get(event["event_id"])
            if shot is not None:
                assert abs(shot["end_location"][0] - event["route_end"][0]) < 0.02
                assert abs(shot["end_location"][1] - event["route_end"][1]) < 0.02
                assert shot["xg"] == chosen["success_prob"]
        else:
            assert chosen["type"] == "carry"
            if chosen["progress_m"] >= 4:
                assert event["label_class"] == "dribble"
            else:
                dist = _nearest_opponent(frames[event["available_at_ms"]], event["player_id"])
                if dist < 2.99:
                    assert event["label_class"] == "hold"
                elif dist > 3.01:
                    assert event["label_class"] == "dribble"
            if event["label_class"] == "hold":
                assert event["route_kind"] == ""
                assert event["route_target_id"] is None
                assert event["route_end"] is None
            else:
                assert event["route_kind"] == "dribble"
                assert event["route_target_id"] == event["player_id"]
                assert event["route_end"] == chosen["end_location"]

        if example is None:
            example = {
                "event_id": event["event_id"],
                "match_id": event["match_id"],
                "player_id": event["player_id"],
                "chosen_option_id": event["chosen_option_id"],
                "chosen_index": event["chosen_index"],
                "label_class": event["label_class"],
                "label_value": event["label_value"],
                "shot_gain_m": event["shot_gain_m"],
                "route_kind": event["route_kind"],
                "route_target_id": event["route_target_id"],
                "options": [
                    {
                        "option_id": opt["option_id"],
                        "type": opt["type"],
                        "offside": opt["offside"],
                        "success_prob": opt["success_prob"],
                        "progress_m": opt["progress_m"],
                        "value": round(_option_value(opt), 6),
                    }
                    for opt in options
                ],
            }
    print("EXAMPLE " + json.dumps(example, ensure_ascii=False))


def test_formation_anchors_are_not_mirrored_twice(tmp_path: Path) -> None:
    module = _load_generate()
    slots = []
    for team, prefix in ((0, "H"), (1, "A")):
        for number, (x, y) in enumerate(module.BASE, 1):
            cx, cy = module.out_xy(x, y)
            if team == 1:
                cx = -cx
            slots.append({
                "player_id": f"{prefix}{number:02d}",
                "team_id": "HOME" if team == 0 else "AWAY",
                "role": module.POSITIONS[number - 1],
                "x": cx,
                "y": cy,
            })
    base_h03 = slots[2]["x"]
    slots[2]["x"] = base_h03 + 15
    path = tmp_path / "formation.json"
    path.write_text(json.dumps({"slots": slots}), encoding="utf-8")

    out = tmp_path / "formation_match"
    _run(out, "--minutes", "1", "--formation", str(path))
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["teams"][0]["formation"] == "custom"
    assert meta["teams"][1]["formation"] == "custom"
    assert meta["match_id"] == f"SYN-SINGLE-{SEED}"

    frames = [json.loads(line) for line in (out / "tracking.jsonl").read_text(encoding="utf-8").splitlines() if line]
    by_id = lambda frame: {row[0]: row for row in frame["players"]}
    start = by_id(frames[0])
    assert start["H03"][1] == slots[2]["x"]
    assert start["A03"][1] == 25.5
    assert start["A03"][1] != start["H03"][1]

    later = by_id(frames[80])
    custom_x, base_x = slots[2]["x"], base_h03
    assert abs(later["H03"][1] - custom_x) < abs(later["H03"][1] - base_x)
