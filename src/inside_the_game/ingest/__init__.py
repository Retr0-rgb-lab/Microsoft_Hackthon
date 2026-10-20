"""Ingest match events (MVP step 1)."""

from inside_the_game.ingest.events import MatchEvent
from inside_the_game.ingest.loader import default_fixture_path, load_events
from inside_the_game.ingest.statsbomb import (
    MAPPING_RULE,
    load_statsbomb_events,
    map_statsbomb_type,
)
from inside_the_game.ingest.synthetic import generate_events

__all__ = [
    "MAPPING_RULE",
    "MatchEvent",
    "default_fixture_path",
    "generate_events",
    "load_events",
    "load_statsbomb_events",
    "map_statsbomb_type",
]
