"""Offline football rationale. No model, no network."""

from __future__ import annotations

from inside_the_game.ingest.events import MatchEvent
from inside_the_game.labels import ACTION_LABELS
from inside_the_game.system1.policy import ActionDistribution
from inside_the_game.system2.sidecar import XTVAEPSidecar, sidecar_narrative


# What each action is doing in that part of the pitch. Descriptive only:
# the sentence names all four actions and does not pick one.
_ZONE_RATIONALE: dict[str, str] = {
    "defensive_third": (
        "In the defensive third a pass plays out from the back, a dribble carries "
        "away from goal, a hold rides the press or resets the shape, and a shot "
        "is a long attempt from deep."
    ),
    "middle_third": (
        "In midfield a pass keeps the move circulating, a dribble looks to break "
        "a line, a hold waits for a teammate to show, and a shot is a strike from range."
    ),
    "attacking_third": (
        "In the attacking third a pass can find a runner, a dribble carries toward "
        "the box, a shot is an effort from outside the area, and a hold keeps the "
        "ball while the move arrives."
    ),
    "attacking_wide": (
        "Out wide a pass is a cross or a cut-back, a dribble takes the touchline, "
        "a shot is an attempt from an angle, and a hold waits for support in the box."
    ),
    "attacking_box": (
        "Inside the box a shot is an attempt on goal, a pass looks for a teammate "
        "in the area, a dribble takes on the covering defender, and a hold pauses "
        "the move before the next touch."
    ),
}
_FALLBACK_RATIONALE = (
    "A pass moves the ball to a teammate, a dribble carries it, a shot is an "
    "attempt on goal, and a hold keeps it at the feet."
)


def template_rationale(
    event: MatchEvent,
    distribution: ActionDistribution,
    sidecar: XTVAEPSidecar,
) -> str:
    """Short rationale from match state and the four-way distribution."""
    zone = event.zone.replace("_", " ") if event.zone else "open pitch"
    context = event.context.strip()
    context_sentence = f" {context}" if context else ""
    if context and not context.endswith("."):
        context_sentence += "."
    shares = ", ".join(
        f"{label} {distribution.probabilities[label]:.1%}" for label in ACTION_LABELS
    )
    return (
        f"At {event.minute}:{event.second:02d}, {event.player} ({event.team}) "
        f"has the ball in the {zone} ({event.ball_x:.0f}, {event.ball_y:.0f}). "
        f"{_pressure_phrase(event.pressure)} {_score_phrase(event)}.{context_sentence} "
        f"System 1 gives the full distribution: {shares}. "
        f"{_ZONE_RATIONALE.get(event.zone, _FALLBACK_RATIONALE)} "
        f"{sidecar_narrative(sidecar)} "
        "Decision aid only: pass, shoot, dribble, and hold stay on screen together."
    )


def _pressure_phrase(pressure: float) -> str:
    if pressure >= 0.7:
        return "A defender is tight to the ball."
    if pressure >= 0.4:
        return "Pressure on the ball is moderate."
    return "There is space around the ball."


def _score_phrase(event: MatchEvent) -> str:
    if event.possession_team == "home":
        ours, theirs = event.score_home, event.score_away
    else:
        ours, theirs = event.score_away, event.score_home
    if ours == theirs:
        return f"The score is level at {event.score_home}-{event.score_away}"
    if ours > theirs:
        return f"The possession side leads {ours}-{theirs}"
    return f"The possession side trails {ours}-{theirs}"
