"""Match-event state. JSON and text only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inside_the_game.labels import ACTION_LABELS


PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


@dataclass(frozen=True)
class MatchEvent:
    """One on-ball decision state.

    ``action`` is the training label when the event came from a labeled
    source. System 1 does not read it. Unlabeled fixtures leave it unset.
    """

    event_id: str
    match_id: str
    minute: int
    second: int
    team: str
    player: str
    ball_x: float
    ball_y: float
    score_home: int
    score_away: int
    possession_team: str
    pressure: float
    zone: str
    context: str
    action: str | None = None

    def __post_init__(self) -> None:
        if self.action is not None and self.action not in ACTION_LABELS:
            raise ValueError(f"{self.event_id}: action must be one of {ACTION_LABELS}")
        _validate_ranges(self)

    def to_json_state(self) -> dict[str, Any]:
        """Serializable state for System 1. No image or frame fields."""
        payload: dict[str, Any] = {
            "event_id": self.event_id,
            "match_id": self.match_id,
            "minute": self.minute,
            "second": self.second,
            "team": self.team,
            "player": self.player,
            "ball": {"x": self.ball_x, "y": self.ball_y},
            "score": {"home": self.score_home, "away": self.score_away},
            "possession_team": self.possession_team,
            "pressure": self.pressure,
            "zone": self.zone,
            "context": self.context,
        }
        if self.action is not None:
            payload["action"] = self.action
        return payload


def event_from_dict(payload: dict[str, Any], *, match_id: str) -> MatchEvent:
    """Build a match event from one fixture object."""
    ball = payload.get("ball")
    score = payload.get("score") or {}
    if not isinstance(ball, dict) or "x" not in ball or "y" not in ball:
        raise ValueError(f"{payload.get('event_id', '?')}: ball.x and ball.y are required")
    event = MatchEvent(
        event_id=_require_str(payload, "event_id"),
        match_id=str(payload.get("match_id") or match_id),
        minute=_require_int(payload, "minute"),
        second=int(payload.get("second") or 0),
        team=_require_str(payload, "team"),
        player=_require_str(payload, "player"),
        ball_x=float(ball["x"]),
        ball_y=float(ball["y"]),
        score_home=int(score.get("home") or 0),
        score_away=int(score.get("away") or 0),
        possession_team=str(payload.get("possession_team") or payload["team"]),
        pressure=float(payload.get("pressure", 0.0)),
        zone=str(payload.get("zone") or ""),
        context=str(payload.get("context") or ""),
        action=_optional_action(payload),
    )
    return event


def zone_name(ball_x: float, ball_y: float, possession_team: str) -> str:
    """Coarse pitch zone in the possession team's attacking direction."""
    attacking_right = possession_team == "home"
    attack_x = ball_x if attacking_right else PITCH_LENGTH - ball_x
    attack_y = ball_y if attacking_right else PITCH_WIDTH - ball_y
    in_wide = attack_y < 14.0 or attack_y > PITCH_WIDTH - 14.0
    if attack_x >= 88.5 and 14.0 <= attack_y <= PITCH_WIDTH - 14.0:
        return "attacking_box"
    if attack_x >= 70.0 and in_wide:
        return "attacking_wide"
    if attack_x >= 70.0:
        return "attacking_third"
    if attack_x >= 35.0:
        return "middle_third"
    return "defensive_third"


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"event field {key} must be a non-empty string")
    return value


def _optional_action(payload: dict[str, Any]) -> str | None:
    if "action" not in payload or payload["action"] is None:
        return None
    action = payload["action"]
    if action not in ACTION_LABELS:
        raise ValueError(f"action must be one of {ACTION_LABELS}")
    return str(action)


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"event field {key} must be an integer")
    return value


def _validate_ranges(event: MatchEvent) -> None:
    if not 0 <= event.minute <= 120:
        raise ValueError(f"{event.event_id}: minute out of range")
    if not 0 <= event.second <= 59:
        raise ValueError(f"{event.event_id}: second out of range")
    if not 0.0 <= event.ball_x <= PITCH_LENGTH:
        raise ValueError(f"{event.event_id}: ball.x must be in [0, {PITCH_LENGTH}]")
    if not 0.0 <= event.ball_y <= PITCH_WIDTH:
        raise ValueError(f"{event.event_id}: ball.y must be in [0, {PITCH_WIDTH}]")
    if not 0.0 <= event.pressure <= 1.0:
        raise ValueError(f"{event.event_id}: pressure must be in [0, 1]")
