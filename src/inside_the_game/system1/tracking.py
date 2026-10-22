"""System 1 decision from a tracking frame and one decision_point.

The softmax still answers pass / shoot / dribble / hold. It does not pick a
receiver. Pass targets and the carry path are geometry on the same frame,
scored by pitch-control × xT, in centre-spot metres:

``{"target_id", "path": [[x, y], ...], "score"}``

``ghost_route`` returns one of those geometries for a suggested class. A shot
is scored as ``success_prob * 0.80`` and is not sent through pitch control.
``decide_from_tracking`` still returns primary_pass, secondary_pass, and carry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from inside_the_game.features.from_tracking import (
    HALF_LENGTH_M,
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    attack_multiplier,
)
from inside_the_game.system1.completion import completion_value
from inside_the_game.system1.policy import SoftmaxActionPolicy


CARRY_STEPS = 5
FALLBACK_CARRY_M = 6.0

# Static xT at the goal mouth in the attack frame (x = 52.5, y = 0).
# expected_threat's box formula there is 0.25 + 0.55 = 0.80. Shot routes
# multiply success_prob by this constant and do not call pitch control.
GOAL_MOUTH_XT = 0.80


@dataclass(frozen=True)
class PitchPath:
    """A pass or a carry drawn in centre-spot metres."""

    target_id: str
    path: tuple[tuple[float, float], ...]
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "path": [[round(x, 3), round(y, 3)] for x, y in self.path],
            "score": round(self.score, 6),
        }


def decide_from_tracking(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    team_of: Mapping[str, str],
    policy: SoftmaxActionPolicy | None = None,
) -> dict[str, Any]:
    """Four-class probabilities, two pass targets, and one carry path.

    ``policy`` defaults to the checked-in softmax. Pass and carry geometry
    uses the decision_point options that are already available at
    ``available_at_ms`` (a pass marked offside is dropped). It does not read
    a later resolved event.
    """
    model = policy or SoftmaxActionPolicy()
    distribution = model.predict_tracking(frame, event, team_of)
    start = _player_xy(frame, str(event["player_id"]))
    primary, secondary = _pass_targets(frame, event, team_of, start)
    carry = _carry_path(frame, event, team_of, start)
    return {
        "event_id": str(event["event_id"]),
        "probabilities": distribution.as_dict(),
        "primary_pass": None if primary is None else primary.as_dict(),
        "secondary_pass": None if secondary is None else secondary.as_dict(),
        "carry": carry.as_dict(),
    }


def ghost_route(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    team_of: Mapping[str, str],
    suggested_class: str,
) -> dict[str, Any] | None:
    """One route for ``suggested_class``.

    ``pass`` is the primary onside pass (pitch-control × xT). ``dribble`` is
    the carry path. ``shoot`` is a straight segment to the shot option's end,
    scored ``success_prob * 0.80`` (static xT at the goal mouth), not pitch
    control at the goal. ``hold`` returns no route.
    """
    label = str(suggested_class)
    if label == "hold":
        return None
    start = _player_xy(frame, str(event["player_id"]))
    if label == "pass":
        chosen = _value_pass(start, event)
        return None if chosen is None else chosen.as_dict()
    if label == "dribble":
        return _carry_path(frame, event, team_of, start).as_dict()
    if label == "shoot":
        shot = _shot_segment(frame, event, start)
        return None if shot is None else shot.as_dict()
    raise ValueError(f"suggested class {suggested_class!r} is not pass, shoot, dribble, or hold")


def score_paths(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    team_of: Mapping[str, str],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute pitch-control × xT on the ends already chosen.

    This is the score-completion tool. It does not change the softmax and it
    does not call a network. The numbers match ``decide_from_tracking``.
    """
    ends: list[tuple[float, float]] = []
    slots: list[str] = []
    for name in ("primary_pass", "secondary_pass", "carry"):
        item = decision.get(name)
        if not item:
            continue
        tip = item["path"][-1]
        ends.append((float(tip[0]), float(tip[1])))
        slots.append(name)
    values = completion_value(ends, frame, str(event["team_id"]), team_of)
    scored = {
        "method": "pitch_control_x_xt",
        "paid_api": False,
    }
    for name, value in zip(slots, values, strict=True):
        scored[name] = round(float(value), 6)
    return scored


def _pass_targets(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    team_of: Mapping[str, str],
    start: tuple[float, float],
) -> tuple[PitchPath | None, PitchPath | None]:
    candidates: list[tuple[str, tuple[float, float]]] = []
    for option in event["options"]:
        if option.get("type") != "pass" or option.get("offside"):
            continue
        target_id = option.get("target_player_id")
        if not target_id:
            continue
        end = _xy(option["end_location"])
        candidates.append((str(target_id), end))
    if not candidates:
        return (None, None)
    # One option list can name the same teammate twice. Keep each target once
    # before scoring so the secondary is a different player.
    unique: dict[str, tuple[float, float]] = {}
    for target_id, end in candidates:
        unique.setdefault(target_id, end)
    ends = list(unique.values())
    scores = completion_value(ends, frame, str(event["team_id"]), team_of)
    ranked = sorted(
        (
            PitchPath(target_id=target_id, path=_segment(start, end), score=score)
            for (target_id, end), score in zip(unique.items(), scores, strict=True)
        ),
        key=lambda item: (-item.score, item.target_id),
    )
    primary = ranked[0]
    secondary = ranked[1] if len(ranked) > 1 else None
    return primary, secondary


def _carry_path(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    team_of: Mapping[str, str],
    start: tuple[float, float],
) -> PitchPath:
    """Polyline for the on-ball player. ``target_id`` is that player.

    Carry options in this format leave ``target_player_id`` null: the ball
    stays with the carrier. When the decision lists a carry, the path ends
    at that option. Otherwise it is a short step along the attack.
    """
    carrier = str(event["player_id"])
    ends = [_xy(option["end_location"]) for option in event["options"] if option.get("type") == "carry"]
    if not ends:
        multiplier = attack_multiplier(int(frame["attack_dir"]), str(event["team_id"]))
        raw_end = (
            start[0] + FALLBACK_CARRY_M * multiplier,
            start[1],
        )
        ends = [
            (
                _clamp(raw_end[0], -PITCH_LENGTH_M / 2.0, PITCH_LENGTH_M / 2.0),
                _clamp(raw_end[1], -PITCH_WIDTH_M / 2.0, PITCH_WIDTH_M / 2.0),
            )
        ]
    scores = completion_value(ends, frame, str(event["team_id"]), team_of)
    end, score = max(zip(ends, scores, strict=True), key=lambda item: item[1])
    return PitchPath(target_id=carrier, path=_segment(start, end, CARRY_STEPS), score=score)


def _value_pass(start: tuple[float, float], event: Mapping[str, Any]) -> PitchPath | None:
    """Onside pass with the highest value_v1 score.

    Value is ``success_prob * max(progress_m, 0)``, the same comparison the
    generator uses when it picks. Ties break toward a higher success
    probability, then a smaller ``option_id``. Pitch-control ranking stays
    on ``decide_from_tracking``; this path is only the ghost.
    """
    ranked: list[tuple[float, float, str, str, tuple[float, float]]] = []
    for option in event["options"]:
        if option.get("type") != "pass" or option.get("offside"):
            continue
        target_id = option.get("target_player_id")
        if not target_id:
            continue
        success = float(option["success_prob"])
        value = success * max(float(option["progress_m"]), 0.0)
        ranked.append((value, success, str(option.get("option_id") or ""), str(target_id), _xy(option["end_location"])))
    if not ranked:
        return None
    _value, _success, _option_id, target_id, end = min(
        ranked,
        key=lambda item: (-item[0], -item[1], item[2]),
    )
    return PitchPath(target_id=target_id, path=_segment(start, end), score=_value)


def _shot_segment(
    frame: Mapping[str, Any],
    event: Mapping[str, Any],
    start: tuple[float, float],
) -> PitchPath | None:
    """Straight line toward the shot end. Score is xG times goal-mouth xT.

    The goal mouth is not passed to ``completion_value``. Pitch control in
    front of the goalkeeper would bury every shot.
    """
    shots = [option for option in event["options"] if option.get("type") == "shot"]
    if not shots:
        return None
    chosen = min(
        shots,
        key=lambda option: (
            -float(option.get("success_prob") or 0.0),
            str(option.get("option_id") or ""),
        ),
    )
    end_location = chosen.get("end_location")
    if end_location:
        end = _xy(end_location)
    else:
        multiplier = attack_multiplier(int(frame["attack_dir"]), str(event["team_id"]))
        end = (HALF_LENGTH_M * multiplier, 0.0)
    score = float(chosen["success_prob"]) * GOAL_MOUTH_XT
    return PitchPath(target_id="", path=_segment(start, end), score=score)


def _segment(
    start: tuple[float, float],
    end: tuple[float, float],
    steps: int = 2,
) -> tuple[tuple[float, float], ...]:
    if steps < 2:
        raise ValueError("a path needs a start and an end")
    points: list[tuple[float, float]] = []
    for index in range(steps):
        blend = index / (steps - 1)
        points.append(
            (
                start[0] + (end[0] - start[0]) * blend,
                start[1] + (end[1] - start[1]) * blend,
            )
        )
    return tuple(points)


def _player_xy(frame: Mapping[str, Any], player_id: str) -> tuple[float, float]:
    for row in frame["players"]:
        if str(row[0]) == player_id:
            return (float(row[1]), float(row[2]))
    raise KeyError(player_id)


def _xy(location: list[float] | tuple[float, float]) -> tuple[float, float]:
    return (float(location[0]), float(location[1]))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
