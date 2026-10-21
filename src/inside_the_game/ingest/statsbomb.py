"""Map StatsBomb open-data events onto the scaffold match state.

The pitch in this package is 105 by 68 meters, with home attacking toward
x = 105. StatsBomb locations are on a 120 by 80 grid, oriented so the team
performing the event attacks toward x = 120. This module scales that grid
into meters and flips away events into the home frame.

Mapping rule
------------
Pass → pass, Shot → shoot, Carry or Dribble → dribble.
Every other StatsBomb type is skipped. Skipped events are not labeled hold.
A Pass, Shot, Carry, or Dribble that has no player or no location is skipped
too. Hold labels are not produced here; the synthetic generator supplies them.

Minutes above 120 are clamped to 120 so the existing match-event range check
still holds. ``under_pressure`` becomes pressure 0.82, otherwise 0.18.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH, MatchEvent, zone_name


STATSBOMB_LENGTH = 120.0
STATSBOMB_WIDTH = 80.0
PRESSURE_MARKED = 0.82
PRESSURE_OPEN = 0.18

# StatsBomb ``type.name`` values. Matching is exact.
TYPE_TO_ACTION: dict[str, str] = {
    "Pass": "pass",
    "Shot": "shoot",
    "Carry": "dribble",
    "Dribble": "dribble",
}

MAPPING_RULE = (
    "Pass→pass, Shot→shoot, Carry/Dribble→dribble. "
    "Every other StatsBomb type is skipped and is not labeled hold. "
    "Mapped events missing a player or a location are skipped."
)


@dataclass(frozen=True)
class LabeledMatchEvent:
    """A scaffold event plus the action the mapper assigned."""

    event: MatchEvent
    action: str
    source_type: str


@dataclass(frozen=True)
class MappedStatsBombMatch:
    """Mapped on-ball events and the score after the last raw event."""

    match_id: str
    events: tuple[LabeledMatchEvent, ...]
    final_score: tuple[int, int]
    skipped: int


def map_statsbomb_type(type_name: str) -> str | None:
    """Return pass, shoot, or dribble, or None when the type is skipped."""
    return TYPE_TO_ACTION.get(type_name)


def load_statsbomb_labeled(match_dir: Path) -> MappedStatsBombMatch:
    """Read ``match.json`` and ``events.json`` from ``match_dir``.

    There is no checked-in match. Callers pass a directory they already have.
    """
    directory = Path(match_dir)
    match = json.loads((directory / "match.json").read_text(encoding="utf-8"))
    events = json.loads((directory / "events.json").read_text(encoding="utf-8"))
    if not isinstance(match, dict) or not isinstance(events, list):
        raise ValueError(f"{directory} is not a StatsBomb match directory")
    return map_statsbomb_match(events, match)


def load_statsbomb_events(match_dir: Path) -> tuple[MatchEvent, ...]:
    """Mapped events only, in kickoff order, ready for ``extract_features``."""
    mapped = load_statsbomb_labeled(match_dir)
    return tuple(item.event for item in mapped.events)


def map_statsbomb_match(
    raw_events: list[dict[str, Any]],
    match: dict[str, Any],
) -> MappedStatsBombMatch:
    """Apply the mapping rule. Score updates from goals even when an event is skipped."""
    home_id = _team_id(match["home_team"])
    away_id = _team_id(match["away_team"])
    match_id = str(match.get("match_id") or "statsbomb")
    score = {"home": 0, "away": 0}
    labeled: list[LabeledMatchEvent] = []
    skipped = 0
    ordered = sorted(raw_events, key=_event_sort_key)
    for raw in ordered:
        if not isinstance(raw, dict):
            raise ValueError("each StatsBomb event must be a JSON object")
        type_name = str((raw.get("type") or {}).get("name") or "")
        action = map_statsbomb_type(type_name)
        if action is None or "location" not in raw or "player" not in raw:
            skipped += 1
            _apply_score(raw, score, home_id, away_id)
            continue
        side = _side(raw.get("team") or {}, home_id, away_id)
        ball_x, ball_y = _to_home_frame(raw["location"], side)
        minute = _clamp_minute(raw.get("minute", 0))
        second = int(raw.get("second") or 0)
        player = str((raw.get("player") or {}).get("name") or "")
        if not player:
            skipped += 1
            _apply_score(raw, score, home_id, away_id)
            continue
        pattern = str((raw.get("play_pattern") or {}).get("name") or "Open play")
        event = MatchEvent(
            event_id=str(raw.get("id") or f"{match_id}-{raw.get('index', len(labeled))}"),
            match_id=match_id,
            minute=minute,
            second=second,
            team=side,
            player=player,
            ball_x=ball_x,
            ball_y=ball_y,
            score_home=score["home"],
            score_away=score["away"],
            possession_team=side,
            pressure=PRESSURE_MARKED if raw.get("under_pressure") else PRESSURE_OPEN,
            zone=zone_name(ball_x, ball_y, side),
            context=f"{type_name} ({pattern}).",
            action=action,
        )
        labeled.append(LabeledMatchEvent(event=event, action=action, source_type=type_name))
        _apply_score(raw, score, home_id, away_id)
    return MappedStatsBombMatch(
        match_id=match_id,
        events=tuple(labeled),
        final_score=(score["home"], score["away"]),
        skipped=skipped,
    )


def project_match(match: dict[str, Any]) -> dict[str, Any]:
    """Keep the match fields the mapper reads, plus attribution."""
    competition = match.get("competition") or {}
    season = match.get("season") or {}
    stage = match.get("competition_stage") or {}
    return {
        "match_id": match["match_id"],
        "match_date": match.get("match_date"),
        "competition_id": competition.get("competition_id"),
        "season_id": season.get("season_id"),
        "competition": competition.get("competition_name"),
        "season": season.get("season_name"),
        "competition_stage": stage.get("name"),
        "home_team": {
            "id": match["home_team"]["home_team_id"],
            "name": match["home_team"]["home_team_name"],
        },
        "away_team": {
            "id": match["away_team"]["away_team_id"],
            "name": match["away_team"]["away_team_name"],
        },
        "home_score": match.get("home_score"),
        "away_score": match.get("away_score"),
        "source": "https://github.com/statsbomb/open-data",
        "license": "CC BY-NC 4.0",
    }


def project_event(event: dict[str, Any]) -> dict[str, Any]:
    """Drop freeze-frames and related ids. Values that remain are unchanged."""
    projected: dict[str, Any] = {
        "id": event.get("id"),
        "index": event.get("index"),
        "period": event.get("period"),
        "minute": event.get("minute"),
        "second": event.get("second"),
        "type": {
            "id": (event.get("type") or {}).get("id"),
            "name": (event.get("type") or {}).get("name"),
        },
        "possession_team": _project_named(event.get("possession_team")),
        "team": _project_named(event.get("team")),
    }
    player = event.get("player")
    if isinstance(player, dict):
        projected["player"] = _project_named(player)
    if "location" in event:
        projected["location"] = event["location"]
    if event.get("under_pressure"):
        projected["under_pressure"] = True
    play_pattern = event.get("play_pattern")
    if isinstance(play_pattern, dict):
        projected["play_pattern"] = {
            "id": play_pattern.get("id"),
            "name": play_pattern.get("name"),
        }
    if (event.get("type") or {}).get("name") == "Shot" and isinstance(event.get("shot"), dict):
        outcome = event["shot"].get("outcome") or {}
        projected["shot"] = {"outcome": {"id": outcome.get("id"), "name": outcome.get("name")}}
    return projected


def _project_named(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"id": None, "name": ""}
    return {"id": value.get("id"), "name": value.get("name")}


def _team_id(team: dict[str, Any]) -> int:
    if "id" in team:
        return int(team["id"])
    if "home_team_id" in team:
        return int(team["home_team_id"])
    if "away_team_id" in team:
        return int(team["away_team_id"])
    raise ValueError("match team is missing an id")


def _side(team: dict[str, Any], home_id: int, away_id: int) -> str:
    team_id = int(team["id"])
    if team_id == home_id:
        return "home"
    if team_id == away_id:
        return "away"
    raise ValueError(f"team {team_id} is neither home {home_id} nor away {away_id}")


def _to_home_frame(location: list[Any] | tuple[Any, ...], side: str) -> tuple[float, float]:
    if len(location) < 2:
        raise ValueError("StatsBomb location must be [x, y]")
    length = max(0.0, min(STATSBOMB_LENGTH, float(location[0])))
    width = max(0.0, min(STATSBOMB_WIDTH, float(location[1])))
    x_meters = length / STATSBOMB_LENGTH * PITCH_LENGTH
    y_meters = width / STATSBOMB_WIDTH * PITCH_WIDTH
    if side == "away":
        x_meters = PITCH_LENGTH - x_meters
        y_meters = PITCH_WIDTH - y_meters
    return (
        max(0.0, min(PITCH_LENGTH, x_meters)),
        max(0.0, min(PITCH_WIDTH, y_meters)),
    )


def _clamp_minute(value: Any) -> int:
    minute = int(value)
    if minute < 0:
        return 0
    if minute > 120:
        return 120
    return minute


def _apply_score(
    raw: dict[str, Any],
    score: dict[str, int],
    home_id: int,
    away_id: int,
) -> None:
    type_name = str((raw.get("type") or {}).get("name") or "")
    if "team" not in raw:
        return
    try:
        side = _side(raw["team"], home_id, away_id)
    except (KeyError, ValueError, TypeError):
        return
    if type_name == "Shot":
        outcome = str(((raw.get("shot") or {}).get("outcome") or {}).get("name") or "")
        if outcome == "Goal":
            score[side] += 1
        return
    if type_name == "Own Goal Against":
        score["away" if side == "home" else "home"] += 1


def _event_sort_key(raw: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(raw.get("period") or 0),
        int(raw.get("minute") or 0),
        int(raw.get("second") or 0),
        int(raw.get("index") or 0),
    )
