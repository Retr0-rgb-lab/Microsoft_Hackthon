"""Synthetic match-event state. JSON and text only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


@dataclass(frozen=True)
class MatchEvent:
    """One on-ball decision state from a synthetic match."""

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

    def to_json_state(self) -> dict[str, Any]:
        """Serializable state for System 1. No image or frame fields."""
        return {
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
    )
    _validate_ranges(event)
    return event


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"event field {key} must be a non-empty string")
    return value


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
