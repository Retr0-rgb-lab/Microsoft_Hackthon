"""StatsBomb open-data events map onto the scaffold action set."""

from __future__ import annotations

from inside_the_game.features.extract import FEATURE_NAMES, extract_features
from inside_the_game.ingest.statsbomb import (
    MAPPING_RULE,
    TYPE_TO_ACTION,
    load_statsbomb_labeled,
    map_statsbomb_match,
    map_statsbomb_type,
)
from inside_the_game.labels import ACTION_LABELS
from inside_the_game.pipeline import run_mvp


def test_mapping_rule_is_explicit() -> None:
    assert map_statsbomb_type("Pass") == "pass"
    assert map_statsbomb_type("Shot") == "shoot"
    assert map_statsbomb_type("Carry") == "dribble"
    assert map_statsbomb_type("Dribble") == "dribble"
    for type_name in (
        "Starting XI",
        "Half Start",
        "Half End",
        "Pressure",
        "Ball Receipt*",
        "Substitution",
        "Foul Committed",
        "Shield",
        "Own Goal Against",
    ):
        assert map_statsbomb_type(type_name) is None
    assert "skipped" in MAPPING_RULE
    assert set(TYPE_TO_ACTION) == {"Pass", "Shot", "Carry", "Dribble"}


def test_context_events_are_skipped_and_goals_update_the_score() -> None:
    match = {
        "match_id": 7,
        "home_team": {"id": 1, "name": "Home"},
        "away_team": {"id": 2, "name": "Away"},
    }
    raw = [
        _event("Starting XI", index=1, minute=0, team=1),
        _event("Pass", index=2, minute=3, team=1, location=[60, 40], player="A. Player"),
        _event(
            "Shot",
            index=3,
            minute=10,
            team=1,
            location=[110, 40],
            player="A. Shooter",
            shot_outcome="Goal",
        ),
        _event("Pressure", index=4, minute=10, team=2, location=[10, 40]),
        _event("Carry", index=5, minute=11, team=2, location=[30, 20], player="B. Carrier"),
        _event("Dribble", index=6, minute=12, team=2, location=[80, 40], player="B. Dribbler"),
        _event("Pass", index=7, minute=127, team=1, location=[120, 80], player="A. Late"),
    ]
    mapped = map_statsbomb_match(raw, match)
    actions = [item.action for item in mapped.events]
    source_types = [item.source_type for item in mapped.events]
    assert actions == ["pass", "shoot", "dribble", "dribble", "pass"]
    assert source_types == ["Pass", "Shot", "Carry", "Dribble", "Pass"]
    assert mapped.skipped == 2
    assert mapped.final_score == (1, 0)
    assert mapped.events[0].event.score_home == 0
    assert mapped.events[1].event.score_home == 0
    assert mapped.events[2].event.score_home == 1
    late = mapped.events[-1].event
    assert late.minute == 120
    assert late.ball_x == 105.0
    assert late.ball_y == 68.0
    assert late.action == "pass"


def test_away_locations_flip_into_the_home_frame() -> None:
    match = {
        "match_id": 7,
        "home_team": {"id": 1, "name": "Home"},
        "away_team": {"id": 2, "name": "Away"},
    }
    raw = [_event("Pass", index=1, minute=5, team=2, location=[0, 0], player="B. Keeper")]
    event = map_statsbomb_match(raw, match).events[0].event
    assert event.team == "away"
    assert event.possession_team == "away"
    assert event.ball_x == 105.0
    assert event.ball_y == 68.0
    features = extract_features(event)
    assert features.as_tuple()[0] == 0.0


def test_vendored_match_maps_offline_onto_scaffold_features() -> None:
    mapped = load_statsbomb_labeled()
    assert mapped.match_id == "69284"
    assert mapped.final_score == (1, 0)
    assert mapped.events
    assert mapped.skipped > 0
    labels = {item.action for item in mapped.events}
    assert labels == {"pass", "shoot", "dribble"}
    assert "hold" not in labels
    shot_x = [
        extract_features(item.event).ball_x
        for item in mapped.events
        if item.action == "shoot"
    ]
    assert shot_x
    assert sum(shot_x) / len(shot_x) > 0.7
    for item in mapped.events:
        assert item.action in ACTION_LABELS
        values = extract_features(item.event).as_tuple()
        assert len(values) == len(FEATURE_NAMES)
        assert all(0.0 <= value <= 1.0 for value in values[:5])
        assert -1.0 <= values[5] <= 1.0
        assert 0.0 <= item.event.ball_x <= 105.0
        assert 0.0 <= item.event.ball_y <= 68.0
        assert 0 <= item.event.minute <= 120
        assert 0.0 <= item.event.pressure <= 1.0
    frames = run_mvp(events=tuple(item.event for item in mapped.events[:5]))
    assert len(frames) == 5


def _event(
    type_name: str,
    *,
    index: int,
    minute: int,
    team: int,
    location: list[float] | None = None,
    player: str | None = None,
    shot_outcome: str | None = None,
) -> dict:
    payload: dict = {
        "id": f"evt-{index}",
        "index": index,
        "period": 1,
        "minute": minute,
        "second": 0,
        "type": {"id": index, "name": type_name},
        "team": {"id": team, "name": "Home" if team == 1 else "Away"},
        "possession_team": {"id": team, "name": "Home" if team == 1 else "Away"},
        "play_pattern": {"id": 1, "name": "Regular Play"},
    }
    if location is not None:
        payload["location"] = location
    if player is not None:
        payload["player"] = {"id": index, "name": player}
    if shot_outcome is not None:
        payload["shot"] = {"outcome": {"id": 97, "name": shot_outcome}}
    return payload
