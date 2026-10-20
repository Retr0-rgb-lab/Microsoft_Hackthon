"""Ingest synthetic match events (MVP step 1)."""

from inside_the_game.ingest.events import MatchEvent
from inside_the_game.ingest.loader import default_fixture_path, load_events

__all__ = ["MatchEvent", "default_fixture_path", "load_events"]
