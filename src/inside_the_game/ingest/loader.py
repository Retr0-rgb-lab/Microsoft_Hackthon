"""Load synthetic match events from JSON fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from inside_the_game.ingest.events import MatchEvent, event_from_dict


def default_fixture_path() -> Path:
    """Repo fixture checked in at ``fixtures/synthetic_match_events.json``."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "fixtures" / "synthetic_match_events.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("synthetic_match_events.json fixture not found")


def load_events(path: Path | None = None) -> tuple[MatchEvent, ...]:
    """Read a fixture file and return match events in file order."""
    fixture = Path(path) if path is not None else default_fixture_path()
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture root must be an object")
    match_id = str(payload.get("match_id") or "synthetic")
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("fixture events must be a non-empty list")
    events: list[MatchEvent] = []
    for item in raw_events:
        if not isinstance(item, dict):
            raise ValueError("each event must be a JSON object")
        events.append(event_from_dict(item, match_id=match_id))
    return tuple(events)
