"""Replay overlay: probability bars and arrow placeholders for every action."""

from __future__ import annotations

from dataclasses import dataclass

from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH, MatchEvent
from inside_the_game.labels import ACTION_LABELS
from inside_the_game.system1.policy import ActionDistribution


DECISION_AID_NOTE = (
    "Decision aid. Full distribution over pass, shoot, dribble, and hold."
)

_GLYPH = {
    "pass": "→",
    "shoot": "→",
    "dribble": "↗",
    "hold": "•",
}
_ARROW_NOTE = {
    "pass": "teammate lane placeholder",
    "shoot": "goalmouth placeholder",
    "dribble": "carry lane placeholder",
    "hold": "stay placeholder",
}
_BAR_WIDTH = 10


@dataclass(frozen=True)
class ArrowPlaceholder:
    """Display hint for one action. Every action gets one; none is selected."""

    action: str
    glyph: str
    origin: tuple[float, float]
    target: tuple[float, float]
    note: str


@dataclass(frozen=True)
class ActionOverlay:
    action: str
    probability: float
    bar: str
    arrow: ArrowPlaceholder


@dataclass(frozen=True)
class ReplayOverlay:
    event_id: str
    minute: int
    second: int
    team: str
    player: str
    actions: tuple[ActionOverlay, ...]
    disclaimer: str


def render_overlay(event: MatchEvent, distribution: ActionDistribution) -> ReplayOverlay:
    """Build bars and arrows for all four actions, in label order."""
    targets = _arrow_targets(event)
    actions = []
    for label in ACTION_LABELS:
        probability = distribution.probabilities[label]
        actions.append(
            ActionOverlay(
                action=label,
                probability=probability,
                bar=_bar(probability),
                arrow=ArrowPlaceholder(
                    action=label,
                    glyph=_GLYPH[label],
                    origin=(event.ball_x, event.ball_y),
                    target=targets[label],
                    note=_ARROW_NOTE[label],
                ),
            )
        )
    return ReplayOverlay(
        event_id=event.event_id,
        minute=event.minute,
        second=event.second,
        team=event.team,
        player=event.player,
        actions=tuple(actions),
        disclaimer=DECISION_AID_NOTE,
    )


def format_overlay(overlay: ReplayOverlay) -> str:
    """Plain-text overlay for the stub CLI."""
    lines = [
        f"{overlay.event_id}  {overlay.minute}:{overlay.second:02d}  {overlay.team}  {overlay.player}",
        overlay.disclaimer,
    ]
    for item in overlay.actions:
        target_x, target_y = item.arrow.target
        lines.append(
            f"  {item.action:<7} {item.probability:0.3f}  {item.bar}  "
            f"arrow {item.arrow.glyph} ({target_x:.1f}, {target_y:.1f}) {item.arrow.note}"
        )
    return "\n".join(lines)


def _bar(probability: float) -> str:
    filled = max(0, min(_BAR_WIDTH, round(probability * _BAR_WIDTH)))
    return ("█" * filled) + ("░" * (_BAR_WIDTH - filled))


def _arrow_targets(event: MatchEvent) -> dict[str, tuple[float, float]]:
    x, y = event.ball_x, event.ball_y
    toward_goal = 1.0 if event.possession_team == "home" else -1.0
    goal_x = PITCH_LENGTH if toward_goal > 0 else 0.0
    return {
        "pass": (_clamp(x + 8.0 * toward_goal, PITCH_LENGTH), _clamp(y + 12.0, PITCH_WIDTH)),
        "shoot": (goal_x, PITCH_WIDTH / 2.0),
        "dribble": (_clamp(x + 12.0 * toward_goal, PITCH_LENGTH), y),
        "hold": (x, y),
    }


def _clamp(value: float, upper: float) -> float:
    return max(0.0, min(upper, value))
