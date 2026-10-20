"""Numeric features from JSON match state. No images."""

from __future__ import annotations

from dataclasses import dataclass

from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH, MatchEvent


FEATURE_NAMES: tuple[str, ...] = (
    "ball_x",
    "ball_y",
    "centrality",
    "pressure",
    "minute",
    "goal_diff",
)


@dataclass(frozen=True)
class FeatureVector:
    """Pitch-normalized features for the lightweight System 1 classifier."""

    ball_x: float
    ball_y: float
    centrality: float
    pressure: float
    minute: float
    goal_diff: float

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (
            self.ball_x,
            self.ball_y,
            self.centrality,
            self.pressure,
            self.minute,
            self.goal_diff,
        )


def extract_features(event: MatchEvent) -> FeatureVector:
    """Map one match event to a feature vector.

    ``ball_x`` is 0 at the team's own goal line and 1 at the opponent's goal,
    so both home and away attacks point the same way. Coordinates in the
    fixture stay in absolute pitch meters (home attacks toward x = 105).
    """
    attacking_right = event.possession_team == "home"
    x_meters = event.ball_x if attacking_right else PITCH_LENGTH - event.ball_x
    y_meters = event.ball_y if attacking_right else PITCH_WIDTH - event.ball_y
    ball_x = _unit(x_meters, PITCH_LENGTH)
    ball_y = _unit(y_meters, PITCH_WIDTH)
    centrality = 1.0 - min(1.0, abs(ball_y - 0.5) * 2.0)
    if event.possession_team == "home":
        raw_diff = event.score_home - event.score_away
    else:
        raw_diff = event.score_away - event.score_home
    goal_diff = max(-1.0, min(1.0, raw_diff / 5.0))
    return FeatureVector(
        ball_x=ball_x,
        ball_y=ball_y,
        centrality=centrality,
        pressure=event.pressure,
        minute=max(0.0, min(1.0, event.minute / 90.0)),
        goal_diff=goal_diff,
    )


def _unit(value: float, span: float) -> float:
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, value / span))
