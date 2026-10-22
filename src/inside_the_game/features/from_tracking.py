"""Map a SynthData tracking frame and decision_point onto System 1 features.

Pitch frame, from the sample FORMAT:

- origin at the centre spot, metres, 105 by 68
- ``attack_dir`` +1 means HOME attacks toward +x on that frame; AWAY is opposite

Section 6 of that FORMAT is the consumption rule. The frame is

``frames[round(available_at_ms * frame_hz / 1000)]``.

The acting team is rotated so they attack toward +x:

``d = attack_dir if team_id == "HOME" else -attack_dir``

and every player ``(x, y, vx, vy)`` is multiplied by ``d``. Facing follows
``atan2(sin(facing) * d, cos(facing) * d)``.

Only that frame and the decision_point itself are read. A later pass, shot,
or carry event is not an input. The six scaffold features are unchanged, so
``SoftmaxActionPolicy`` stays the four-way softmax. ``features_value_v1`` is a
separate eight-number vector and does not replace those six.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inside_the_game.features.extract import FeatureVector, extract_features
from inside_the_game.features.from_cv import pressure_from_distances
from inside_the_game.ingest.events import MatchEvent, zone_name
from inside_the_game.labels import ACTION_LABELS


PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
HALF_LENGTH_M = PITCH_LENGTH_M / 2.0
HALF_WIDTH_M = PITCH_WIDTH_M / 2.0

# The sample's pressure events use a 3 m distance threshold. A carry that
# does not break that press (under 4 m of forward progress) is a hold: the
# ball stays with the same player. Longer carries are dribbles. Pass and
# shot keep their option type. This is the only way the four softmax labels
# are read off decision_point events, which have no hold type of their own.
PRESSURE_RADIUS_M = 3.0
HOLD_CARRY_PROGRESS_M = 4.0

LABEL_RULE = (
    "decision_point chosen option: pass→pass, shot→shoot, "
    "carry→dribble, except a carry with progress_m < 4 and the nearest "
    "opponent within 3 m → hold. No other event type is a training row."
)

# Ten value_v1 inputs. Not the six scaffold names: no centrality, minute,
# or goal_diff. Order is the training column order.
VALUE_V1_FEATURE_NAMES: tuple[str, ...] = (
    "ball_x",
    "ball_y",
    "nearest_opponent_m",
    "opponents_within_5m",
    "best_onside_pass_success",
    "best_onside_pass_progress_m",
    "carry_progress_m",
    "shot_xg",
    "best_pass_value",
    "carry_value",
)

# Scales for features_value_v1. The comment on that function is the contract.
_VALUE_V1_NEAREST_SCALE_M = 30.0
_VALUE_V1_WITHIN_M = 5.0
_VALUE_V1_WITHIN_SCALE = 4.0
_VALUE_V1_PASS_PROGRESS_M = 40.0
_VALUE_V1_CARRY_PROGRESS_M = 20.0
_VALUE_V1_OPTION_VALUE_M = 20.0
_VALUE_V1_OPTION_VALUE_CLIP = 2.0

VALUE_V1_LABEL_RULE = (
    "value_v1 decision_point: the training label is the event label_class. "
    "A file whose policy is heuristic_v0 is refused and is not mixed into the fit."
)

HOLDOUT_MATCH_IDS = frozenset({"SYN-HOLDOUT-0001", "SYN-HOLDOUT-0002"})
HOLDOUT_SEEDS = frozenset({9001, 9002})


def default_sample_dir() -> Path:
    """Checked-in SynthData clip ``sample_25hz_10min`` (match ``SYN-SINGLE-0001``)."""
    return (
        Path(__file__).resolve().parents[3]
        / "touchline"
        / "data"
        / "samples"
        / "sample_25hz_10min"
    )


@dataclass(frozen=True)
class SynthMatch:
    """One synthetic match. Tracking may be a sparse decision-point slice."""

    root: Path
    metadata: dict[str, Any]
    frames_by_id: dict[int, dict[str, Any]]
    events: tuple[dict[str, Any], ...]

    @property
    def frame_hz(self) -> int:
        return int(self.metadata["frame_hz"])

    @property
    def match_id(self) -> str:
        return str(self.metadata["match_id"])

    @property
    def team_of(self) -> dict[str, str]:
        return {player["player_id"]: player["team_id"] for player in self.metadata["players"]}


def load_synth_match(root: Path | None = None) -> SynthMatch:
    """Load metadata, events, and tracking. Refuses a non-synthetic match."""
    sample = Path(root) if root is not None else default_sample_dir()
    metadata = json.loads((sample / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("synthetic") is not True or metadata.get("fictional_entities") is not True:
        raise ValueError(f"{sample} is not a synthetic fictional match")
    coordinate = metadata.get("coordinate_system") or {}
    if coordinate.get("origin") != "centre_spot":
        raise ValueError(f"{sample} origin must be centre_spot")
    if coordinate.get("pitch_length_m") != 105 or coordinate.get("pitch_width_m") != 68:
        raise ValueError(f"{sample} pitch must be 105 by 68 metres")
    events = tuple(_read_jsonl(sample / "events.jsonl"))
    frames = {int(frame["frame_id"]): frame for frame in _read_jsonl(sample / "tracking.jsonl")}
    return SynthMatch(root=sample, metadata=metadata, frames_by_id=frames, events=events)


def attack_multiplier(attack_dir: int, team_id: str) -> int:
    """+1 when ``team_id`` attacks toward +x on this frame. FORMAT section 6."""
    if attack_dir not in (1, -1):
        raise ValueError(f"attack_dir must be +1 or -1, got {attack_dir}")
    if team_id == "HOME":
        return int(attack_dir)
    if team_id == "AWAY":
        return -int(attack_dir)
    raise ValueError(f"team_id must be HOME or AWAY, got {team_id!r}")


def attack_player_state(
    players: list[list[Any]],
    multiplier: int,
) -> list[tuple[str, float, float, float, float, float]]:
    """Section 6 player tuple: id, x, y, vx, vy, facing, flipped onto +x attack."""
    state: list[tuple[str, float, float, float, float, float]] = []
    for player_id, x, y, vx, vy, facing in players:
        state.append(
            (
                str(player_id),
                float(x) * multiplier,
                float(y) * multiplier,
                float(vx) * multiplier,
                float(vy) * multiplier,
                math.atan2(math.sin(float(facing)) * multiplier, math.cos(float(facing)) * multiplier),
            )
        )
    return state


def frame_id_for_event(event: Mapping[str, Any], frame_hz: int) -> int:
    """``round(available_at_ms * frame_hz / 1000)``, the section 6 index."""
    return int(round(float(event["available_at_ms"]) * frame_hz / 1000.0))


def frame_for_decision(match: SynthMatch, event: Mapping[str, Any]) -> dict[str, Any]:
    """Tracking frame at the decision. Raises if that frame was not sliced in."""
    _require_decision_point(event)
    index = frame_id_for_event(event, match.frame_hz)
    frame = match.frames_by_id.get(index)
    if frame is None:
        raise KeyError(
            f"no tracking frame {index} for {event.get('event_id')} "
            f"at {event.get('available_at_ms')} ms"
        )
    if int(frame["t_ms"]) > int(event["available_at_ms"]):
        raise ValueError("tracking frame is after available_at_ms")
    return frame


def features_from_tracking(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    team_of: Mapping[str, str],
) -> FeatureVector:
    """Six training features for one decision_point.

    After the attack flip the acting team is stored as home attacking toward
    x = 105, which is what ``extract_features`` already assumes. The flip is
    not applied a second time.
    """
    _require_decision_point(event)
    multiplier = attack_multiplier(int(frame["attack_dir"]), str(event["team_id"]))
    ball = frame["ball"]
    x_attack = float(ball[0]) * multiplier
    y_attack = float(ball[1]) * multiplier
    ball_x = _clamp(x_attack + HALF_LENGTH_M, 0.0, PITCH_LENGTH_M)
    ball_y = _clamp(y_attack + HALF_WIDTH_M, 0.0, PITCH_WIDTH_M)
    team_id = str(event["team_id"])
    if team_id == "HOME":
        score_for, score_against = int(frame["score"][0]), int(frame["score"][1])
    else:
        score_for, score_against = int(frame["score"][1]), int(frame["score"][0])
    elapsed_ms = int(frame["t_ms"])
    minute = min(120, elapsed_ms // 60_000)
    second = (elapsed_ms // 1000) % 60
    pressure = pressure_from_distances(
        opponent_distances_m(frame, str(event["player_id"]), team_id, team_of)
    )
    observed = MatchEvent(
        event_id=str(event["event_id"]),
        match_id=str(event.get("match_id") or frame.get("match_id") or "synth"),
        minute=minute,
        second=int(second),
        team="home",
        player=str(event["player_id"]),
        ball_x=ball_x,
        ball_y=ball_y,
        score_home=score_for,
        score_away=score_against,
        possession_team="home",
        pressure=pressure,
        zone=zone_name(ball_x, ball_y, "home"),
        context="",
    )
    return extract_features(observed)


def label_decision_point(
    event: Mapping[str, Any],
    frame: Mapping[str, Any],
    team_of: Mapping[str, str],
) -> str:
    """Map the chosen option onto pass / shoot / dribble / hold.

    The label is the decision itself, not the later resolved pass or shot.
    """
    _require_decision_point(event)
    chosen = _chosen_option(event)
    kind = chosen["type"]
    if kind == "shot":
        return "shoot"
    if kind == "pass":
        return "pass"
    if kind != "carry":
        raise ValueError(f"{event.get('event_id')}: option type {kind!r} is not pass, carry, or shot")
    distance = min(
        opponent_distances_m(frame, str(event["player_id"]), str(event["team_id"]), team_of)
    )
    if float(chosen["progress_m"]) < HOLD_CARRY_PROGRESS_M and distance <= PRESSURE_RADIUS_M:
        return "hold"
    return "dribble"


def decision_point_rows(
    match: SynthMatch,
) -> list[tuple[tuple[float, float, float, float, float, float], str]]:
    """One training row per decision_point, in file order. No other events."""
    rows: list[tuple[tuple[float, float, float, float, float, float], str]] = []
    for event in match.events:
        if event.get("type") != "decision_point":
            continue
        frame = frame_for_decision(match, event)
        features = features_from_tracking(frame, event, match.team_of)
        label = label_decision_point(event, frame, match.team_of)
        if label not in ACTION_LABELS:
            raise ValueError(label)
        rows.append((features.as_tuple(), label))
    if not rows:
        raise ValueError(f"{match.root} has no decision_point events")
    return rows


# value_v1 normalization, after the section 6 attack flip (centre spot, metres).
# This frame at available_at_ms and this decision's options only. Later events
# are not read. centrality, minute, and goal_diff are not in the vector.
# ball_x: own goal line 0, opponent goal line 1 (attack-flipped metres / 105)
# ball_y: attack-flipped width fraction in [0, 1] (metres / 68)
# nearest_opponent_m: nearest opponent metres / 30, clipped to [0, 1]
# opponents_within_5m: opponents with distance < 5 m, divided by 4, clipped to [0, 1]
# best_onside_pass_success: max success_prob among passes with offside false, else 0
# best_onside_pass_progress_m: max(progress_m, 0) of those passes / 40, clipped to [0, 1], else 0
# carry_progress_m: max(carry progress_m, 0) / 20, clipped to [0, 1], else 0
# shot_xg: max shot success_prob, else 0
# best_pass_value: max over onside passes of success_prob * max(progress_m, 0) / 20, clipped to [0, 2]
# carry_value: that carry's success_prob * max(progress_m, 0) / 20, clipped to [0, 2]
# The products are what value_v1 compares. A linear softmax cannot form them
# from the separate success and progress columns.
def features_value_v1(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    team_of: Mapping[str, str],
) -> tuple[float, ...]:
    """Ten value_v1 numbers. See the normalization comment above."""
    _require_decision_point(event)
    ball_x, ball_y = _attack_ball_units(frame, str(event["team_id"]))
    distances = opponent_distances_m(frame, str(event["player_id"]), str(event["team_id"]), team_of)
    nearest = min(distances) / _VALUE_V1_NEAREST_SCALE_M
    within = sum(1 for distance in distances if distance < _VALUE_V1_WITHIN_M) / _VALUE_V1_WITHIN_SCALE
    successes: list[float] = []
    progresses: list[float] = []
    carries: list[float] = []
    shots: list[float] = []
    for option in event["options"]:
        kind = option.get("type")
        if kind == "pass" and not option.get("offside"):
            successes.append(float(option["success_prob"]))
            progresses.append(max(float(option["progress_m"]), 0.0))
        elif kind == "carry":
            carries.append(max(float(option["progress_m"]), 0.0))
        elif kind == "shot":
            shots.append(float(option["success_prob"]))
    best_success = max(successes) if successes else 0.0
    best_progress = (max(progresses) / _VALUE_V1_PASS_PROGRESS_M) if progresses else 0.0
    carry = (max(carries) / _VALUE_V1_CARRY_PROGRESS_M) if carries else 0.0
    shot_xg = max(shots) if shots else 0.0
    pass_values = [
        float(option["success_prob"]) * max(float(option["progress_m"]), 0.0)
        for option in event["options"]
        if option.get("type") == "pass" and not option.get("offside")
    ]
    carry_values = [
        float(option["success_prob"]) * max(float(option["progress_m"]), 0.0)
        for option in event["options"]
        if option.get("type") == "carry"
    ]
    best_pass_value = (max(pass_values) / _VALUE_V1_OPTION_VALUE_M) if pass_values else 0.0
    carry_value = (max(carry_values) / _VALUE_V1_OPTION_VALUE_M) if carry_values else 0.0
    return (
        ball_x,
        ball_y,
        _clamp(nearest, 0.0, 1.0),
        _clamp(within, 0.0, 1.0),
        best_success,
        _clamp(best_progress, 0.0, 1.0),
        _clamp(carry, 0.0, 1.0),
        shot_xg,
        _clamp(best_pass_value, 0.0, _VALUE_V1_OPTION_VALUE_CLIP),
        _clamp(carry_value, 0.0, _VALUE_V1_OPTION_VALUE_CLIP),
    )


def label_value_v1(event: Mapping[str, Any]) -> str:
    """Training label for a value_v1 decision_point: the event's ``label_class``."""
    _require_decision_point(event)
    policy = event.get("policy")
    if policy != "value_v1":
        raise ValueError(
            f"{event.get('event_id')}: value_v1 training reads label_class only when "
            f"policy is value_v1, got {policy!r}"
        )
    label = event.get("label_class")
    if label not in ACTION_LABELS:
        raise ValueError(
            f"{event.get('event_id')}: label_class {label!r} is outside {ACTION_LABELS}"
        )
    return str(label)


def value_v1_rows(
    match: SynthMatch,
) -> list[tuple[tuple[float, ...], str]]:
    """One value_v1 row per decision_point. The label is ``label_class``."""
    rows: list[tuple[tuple[float, ...], str]] = []
    for event in match.events:
        if event.get("type") != "decision_point":
            continue
        frame = frame_for_decision(match, event)
        rows.append((features_value_v1(frame, event, match.team_of), label_value_v1(event)))
    if not rows:
        raise ValueError(f"{match.root} has no decision_point events")
    return rows


def guard_value_v1_sample(match: SynthMatch) -> None:
    """Refuse a sample that must not be fit as value_v1.

    Refuses match ids ``SYN-HOLDOUT-0001`` and ``SYN-HOLDOUT-0002``, seeds
    9001 and 9002, any path with a ``holdout`` directory, and a file whose
    decision_point policy is ``heuristic_v0``.
    """
    if _path_has_holdout(match.root):
        raise ValueError(f"{match.root} is inside a holdout directory; refusing to fit value_v1")
    match_id = match.match_id
    if match_id in HOLDOUT_MATCH_IDS:
        raise ValueError(f"{match_id} is a holdout match; refusing to fit value_v1")
    seed = _optional_int(match.metadata.get("seed"))
    if seed in HOLDOUT_SEEDS:
        raise ValueError(f"seed {seed} is a holdout seed; refusing to fit value_v1")
    decisions = [event for event in match.events if event.get("type") == "decision_point"]
    if not decisions:
        raise ValueError(f"{match.root} has no decision_point events to fit value_v1")
    for event in decisions:
        policy = event.get("policy")
        if policy == "heuristic_v0":
            raise ValueError(
                f"{match.root} policy is heuristic_v0; refusing to fit value_v1 on that file"
            )
        if policy != "value_v1":
            raise ValueError(
                f"{match.root} decision {event.get('event_id')} policy is {policy!r}, not value_v1"
            )
        label_value_v1(event)


def path_has_holdout_dir(path: Path) -> bool:
    """True when any directory in ``path`` is named holdout."""
    return _path_has_holdout(path)


def opponent_distances_m(
    frame: Mapping[str, Any],
    player_id: str,
    team_id: str,
    team_of: Mapping[str, str],
) -> list[float]:
    """Metres from ``player_id`` to each opponent on this frame."""
    origin = _player_xy(frame, player_id)
    distances: list[float] = []
    for row in frame["players"]:
        other_id = str(row[0])
        if other_id == player_id:
            continue
        other_team = team_of.get(other_id)
        if other_team is None or other_team == team_id:
            continue
        x, y = float(row[1]), float(row[2])
        distances.append(math.hypot(x - origin[0], y - origin[1]))
    if not distances:
        raise ValueError(f"{player_id} has no opponents on the frame")
    return distances


def _chosen_option(event: Mapping[str, Any]) -> Mapping[str, Any]:
    options = event["options"]
    index = int(event["chosen_index"])
    if index < 0 or index >= len(options):
        raise ValueError(f"{event.get('event_id')}: chosen_index {index} is outside the options")
    return options[index]


def _require_decision_point(event: Mapping[str, Any]) -> None:
    if event.get("type") != "decision_point":
        raise ValueError(f"expected a decision_point, got {event.get('type')!r}")


def _player_xy(frame: Mapping[str, Any], player_id: str) -> tuple[float, float]:
    for row in frame["players"]:
        if str(row[0]) == player_id:
            return (float(row[1]), float(row[2]))
    raise KeyError(f"{player_id} is not on the tracking frame")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _attack_ball_units(frame: Mapping[str, Any], team_id: str) -> tuple[float, float]:
    """``ball_x`` and ``ball_y`` in the same units as the six-feature scaffold.

    Section 6 flips the acting team onto +x, then own goal line is 0 and the
    opponent goal line is 1. ``ball_y`` is the width fraction in [0, 1].
    """
    multiplier = attack_multiplier(int(frame["attack_dir"]), team_id)
    ball = frame["ball"]
    x_attack = float(ball[0]) * multiplier
    y_attack = float(ball[1]) * multiplier
    ball_x_m = _clamp(x_attack + HALF_LENGTH_M, 0.0, PITCH_LENGTH_M)
    ball_y_m = _clamp(y_attack + HALF_WIDTH_M, 0.0, PITCH_WIDTH_M)
    return (ball_x_m / PITCH_LENGTH_M, ball_y_m / PITCH_WIDTH_M)


def _path_has_holdout(path: Path) -> bool:
    return any(part.lower() == "holdout" for part in Path(path).parts)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
