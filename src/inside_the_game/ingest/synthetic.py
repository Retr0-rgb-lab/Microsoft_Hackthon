"""Offline generator of labeled football event sequences.

Each sequence is a chain of possessions. Within a possession the ball moves
through build-up, a pressured hold, progression, and a shot. Labels are only
pass, shoot, dribble, and hold. No network and no learned video model.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH, MatchEvent, zone_name
from inside_the_game.labels import ACTION_LABELS


DEFAULT_SEED = 7
DEFAULT_CYCLES = 2

_SQUADS: dict[str, tuple[str, ...]] = {
    "home": (
        "A. Okonkwo",
        "L. Berg",
        "M. Diallo",
        "R. Santos",
        "I. Novak",
        "C. Adeyemi",
    ),
    "away": (
        "S. Rahman",
        "N. Costa",
        "E. Walsh",
        "H. Klein",
        "P. Moreau",
        "J. Silva",
    ),
}

# Attacking-frame meters: x from the team's own goal line, y across the pitch.
_POSSESSIONS: tuple[tuple[dict[str, Any], ...], ...] = (
    (
        {
            "action": "pass",
            "x": 16.0,
            "y": 34.0,
            "pressure": 0.16,
            "context": "Goal kick to the centre-back in space.",
        },
        {
            "action": "pass",
            "x": 31.0,
            "y": 22.0,
            "pressure": 0.24,
            "context": "Square pass to the full-back along the touchline.",
        },
        {
            "action": "pass",
            "x": 44.0,
            "y": 34.0,
            "pressure": 0.31,
            "context": "Pass into the holding midfielder.",
        },
        {
            "action": "hold",
            "x": 46.0,
            "y": 36.0,
            "pressure": 0.78,
            "context": "Pressed from behind, the midfielder shields the ball.",
        },
        {
            "action": "pass",
            "x": 55.0,
            "y": 50.0,
            "pressure": 0.36,
            "context": "Switch of play toward the far half-space.",
        },
        {
            "action": "dribble",
            "x": 67.0,
            "y": 58.0,
            "pressure": 0.33,
            "context": "Carry into space down the wing.",
        },
        {
            "action": "pass",
            "x": 79.0,
            "y": 62.0,
            "pressure": 0.41,
            "context": "Pass down the line to the winger.",
        },
        {
            "action": "dribble",
            "x": 88.0,
            "y": 54.0,
            "pressure": 0.48,
            "context": "Dribble inside off the full-back.",
        },
        {
            "action": "pass",
            "x": 90.0,
            "y": 38.0,
            "pressure": 0.44,
            "context": "Cut-back toward the penalty spot.",
        },
        {
            "action": "shoot",
            "x": 97.0,
            "y": 36.0,
            "pressure": 0.37,
            "context": "Shot from inside the box.",
            "scores": True,
        },
    ),
    (
        {
            "action": "pass",
            "x": 20.0,
            "y": 40.0,
            "pressure": 0.22,
            "context": "Short restart to the right centre-back.",
        },
        {
            "action": "dribble",
            "x": 28.0,
            "y": 46.0,
            "pressure": 0.27,
            "context": "Centre-back steps out with the ball.",
        },
        {
            "action": "hold",
            "x": 30.0,
            "y": 44.0,
            "pressure": 0.74,
            "context": "A striker closes down and the centre-back holds.",
        },
        {
            "action": "pass",
            "x": 42.0,
            "y": 18.0,
            "pressure": 0.29,
            "context": "Pass into the wide midfielder.",
        },
        {
            "action": "pass",
            "x": 58.0,
            "y": 24.0,
            "pressure": 0.34,
            "context": "Progressive pass into the half-space.",
        },
        {
            "action": "pass",
            "x": 71.0,
            "y": 30.0,
            "pressure": 0.42,
            "context": "Ball into the attacking midfielder.",
        },
        {
            "action": "dribble",
            "x": 80.0,
            "y": 28.0,
            "pressure": 0.46,
            "context": "Touch away from the marker toward the byline.",
        },
        {
            "action": "hold",
            "x": 84.0,
            "y": 16.0,
            "pressure": 0.81,
            "context": "The winger is doubled and holds the ball up.",
        },
        {
            "action": "pass",
            "x": 86.0,
            "y": 32.0,
            "pressure": 0.50,
            "context": "Lay-off to the onrushing midfielder.",
        },
        {
            "action": "shoot",
            "x": 92.0,
            "y": 40.0,
            "pressure": 0.55,
            "context": "Shot from the edge of the box.",
            "scores": False,
        },
    ),
    (
        {
            "action": "pass",
            "x": 25.0,
            "y": 34.0,
            "pressure": 0.20,
            "context": "Play out from the back after a goal kick.",
        },
        {
            "action": "pass",
            "x": 38.0,
            "y": 34.0,
            "pressure": 0.26,
            "context": "Central pass through the first line.",
        },
        {
            "action": "dribble",
            "x": 52.0,
            "y": 36.0,
            "pressure": 0.30,
            "context": "Midfielder drives at the defence.",
        },
        {
            "action": "pass",
            "x": 63.0,
            "y": 14.0,
            "pressure": 0.28,
            "context": "Release to the overlapping full-back.",
        },
        {
            "action": "pass",
            "x": 74.0,
            "y": 12.0,
            "pressure": 0.39,
            "context": "Pass along the touchline.",
        },
        {
            "action": "dribble",
            "x": 86.0,
            "y": 18.0,
            "pressure": 0.47,
            "context": "Full-back drives to the byline.",
        },
        {
            "action": "pass",
            "x": 93.0,
            "y": 30.0,
            "pressure": 0.52,
            "context": "Low cross into the six-yard area.",
        },
        {
            "action": "shoot",
            "x": 99.0,
            "y": 34.0,
            "pressure": 0.62,
            "context": "Close-range shot.",
            "scores": False,
        },
    ),
    (
        {
            "action": "pass",
            "x": 18.0,
            "y": 50.0,
            "pressure": 0.21,
            "context": "Keeper throws to the left-sided centre-back.",
        },
        {
            "action": "hold",
            "x": 22.0,
            "y": 52.0,
            "pressure": 0.70,
            "context": "A forward presses and the centre-back pauses.",
        },
        {
            "action": "pass",
            "x": 36.0,
            "y": 60.0,
            "pressure": 0.25,
            "context": "Pass out to the full-back.",
        },
        {
            "action": "dribble",
            "x": 49.0,
            "y": 62.0,
            "pressure": 0.32,
            "context": "Full-back carries past the first press.",
        },
        {
            "action": "pass",
            "x": 60.0,
            "y": 40.0,
            "pressure": 0.30,
            "context": "Pass inside to the number eight.",
        },
        {
            "action": "pass",
            "x": 72.0,
            "y": 36.0,
            "pressure": 0.38,
            "context": "Vertical pass splitting the lines.",
        },
        {
            "action": "hold",
            "x": 76.0,
            "y": 34.0,
            "pressure": 0.77,
            "context": "Back to goal, the forward holds off the centre-back.",
        },
        {
            "action": "pass",
            "x": 82.0,
            "y": 44.0,
            "pressure": 0.48,
            "context": "Lay-off into the runner.",
        },
        {
            "action": "dribble",
            "x": 90.0,
            "y": 42.0,
            "pressure": 0.51,
            "context": "Touch into the box.",
        },
        {
            "action": "shoot",
            "x": 98.0,
            "y": 38.0,
            "pressure": 0.44,
            "context": "Shot across the goalkeeper.",
            "scores": True,
        },
    ),
)


def generate_events(*, seed: int = DEFAULT_SEED, cycles: int = DEFAULT_CYCLES) -> tuple[MatchEvent, ...]:
    """Build a labeled match. ``seed`` only jitters location, pressure, and the clock."""
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    rng = random.Random(seed)
    score = {"home": 0, "away": 0}
    minute = 1
    second = 12
    events: list[MatchEvent] = []
    templates = _POSSESSIONS * cycles
    for possession_index, template in enumerate(templates):
        team = "home" if possession_index % 2 == 0 else "away"
        squad = _SQUADS[team]
        for step_index, step in enumerate(template):
            action = str(step["action"])
            if action not in ACTION_LABELS:
                raise ValueError(f"template action {action!r} is outside {ACTION_LABELS}")
            attack_x = _clamp(float(step["x"]) + rng.uniform(-1.2, 1.2), 1.0, PITCH_LENGTH - 1.0)
            attack_y = _clamp(float(step["y"]) + rng.uniform(-1.2, 1.2), 1.0, PITCH_WIDTH - 1.0)
            pressure = _clamp(float(step["pressure"]) + rng.uniform(-0.03, 0.03), 0.0, 1.0)
            if team == "home":
                ball_x, ball_y = attack_x, attack_y
            else:
                ball_x, ball_y = PITCH_LENGTH - attack_x, PITCH_WIDTH - attack_y
            ball_x = round(ball_x, 2)
            ball_y = round(ball_y, 2)
            pressure = round(pressure, 2)
            player = squad[(possession_index + step_index) % len(squad)]
            events.append(
                MatchEvent(
                    event_id=f"syn-seq-{seed}-{len(events):03d}",
                    match_id=f"syn-labeled-{seed}",
                    minute=minute,
                    second=second,
                    team=team,
                    player=player,
                    ball_x=ball_x,
                    ball_y=ball_y,
                    score_home=score["home"],
                    score_away=score["away"],
                    possession_team=team,
                    pressure=pressure,
                    zone=zone_name(ball_x, ball_y, team),
                    context=str(step["context"]),
                    action=action,
                )
            )
            if action == "shoot" and step.get("scores"):
                score[team] += 1
            second += rng.randint(25, 70)
            minute += second // 60
            second = second % 60
            if minute > 120:
                minute = 120
                second = 0
    return tuple(events)


def generate_fixture(*, seed: int = DEFAULT_SEED, cycles: int = DEFAULT_CYCLES) -> dict[str, Any]:
    """Fixture object accepted by ``load_events``, with an action on every event."""
    events = generate_events(seed=seed, cycles=cycles)
    return {
        "match_id": f"syn-labeled-{seed}",
        "source": "synthetic",
        "seed": seed,
        "cycles": cycles,
        "note": (
            "Labeled synthetic sequences for demo and training. "
            "Actions are only pass, shoot, dribble, and hold. "
            "JSON/text state only."
        ),
        "events": [event_to_fixture(event) for event in events],
    }


def event_to_fixture(event: MatchEvent) -> dict[str, Any]:
    """One event in the checked-in fixture shape."""
    payload: dict[str, Any] = {
        "event_id": event.event_id,
        "minute": event.minute,
        "second": event.second,
        "team": event.team,
        "player": event.player,
        "ball": {"x": event.ball_x, "y": event.ball_y},
        "score": {"home": event.score_home, "away": event.score_away},
        "possession_team": event.possession_team,
        "pressure": event.pressure,
        "zone": event.zone,
        "context": event.context,
    }
    if event.action is not None:
        payload["action"] = event.action
    return payload


def write_fixture(
    path: Path,
    *,
    seed: int = DEFAULT_SEED,
    cycles: int = DEFAULT_CYCLES,
) -> Path:
    """Write ``generate_fixture`` as UTF-8 JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = generate_fixture(seed=seed, cycles=cycles)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
