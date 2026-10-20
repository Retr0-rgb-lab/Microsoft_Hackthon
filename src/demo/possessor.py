"""On-ball identity with hysteresis and a hold across missed detections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerFix:
    """One player in the same coordinate space as the ball."""

    track_id: int
    xy: tuple[float, float]
    team: str
    role: str = "player"


@dataclass(frozen=True)
class BallFix:
    """Smoothed ball. ``held`` means this frame reused an earlier detection."""

    xy: tuple[float, float] | None
    visible: bool
    held: bool
    confidence: float


@dataclass(frozen=True)
class PossessorFix:
    track_id: int | None
    xy: tuple[float, float] | None
    team: str
    held: bool
    source: str


@dataclass
class BallSmoother:
    """Reject one-frame ball jumps and coast through short gaps."""

    hold_frames: int = 15
    xy: tuple[float, float] | None = None
    velocity: tuple[float, float] = (0.0, 0.0)
    missing: int = 0
    confidence: float = 0.0

    def update(
        self,
        xy: tuple[float, float] | None,
        *,
        visible: bool,
        confidence: float = 0.0,
        frame_gap: int = 1,
        max_jump: float | None = None,
    ) -> BallFix:
        gap = max(1, frame_gap)
        if visible and xy is not None and self._accept(xy, gap, max_jump, confidence):
            if self.xy is not None:
                self.velocity = ((xy[0] - self.xy[0]) / gap, (xy[1] - self.xy[1]) / gap)
            self.xy = xy
            self.missing = 0
            self.confidence = confidence
            return BallFix(xy=xy, visible=True, held=False, confidence=confidence)
        self.missing += gap
        if self.xy is None or self.missing > self.hold_frames:
            if self.missing > self.hold_frames:
                self.xy = None
                self.velocity = (0.0, 0.0)
            return BallFix(xy=None, visible=False, held=False, confidence=0.0)
        self.xy = (
            self.xy[0] + self.velocity[0] * gap,
            self.xy[1] + self.velocity[1] * gap,
        )
        return BallFix(xy=self.xy, visible=False, held=True, confidence=self.confidence)

    def _accept(
        self,
        xy: tuple[float, float],
        gap: int,
        max_jump: float | None,
        confidence: float,
    ) -> bool:
        if self.xy is None or max_jump is None or confidence >= 0.55:
            return True
        predicted = (
            self.xy[0] + self.velocity[0] * gap,
            self.xy[1] + self.velocity[1] * gap,
        )
        return _dist(xy, predicted) <= max_jump


@dataclass
class PossessorTracker:
    """Nearest teammate-or-player to the ball, sticky until someone is clearly closer.

    When the ball is absent, the last id is kept for ``hold_frames`` frames
    and the ball is placed at that player's feet.
    """

    max_distance: float = 6.0
    hold_frames: int = 15
    switch_ratio: float = 1.35
    current_id: int | None = None
    missing: int = 0

    def update(
        self,
        players: list[PlayerFix],
        ball_xy: tuple[float, float] | None,
        *,
        ball_visible: bool,
        frame_gap: int = 1,
    ) -> PossessorFix:
        gap = max(1, frame_gap)
        indexed = {player.track_id: player for player in players if player.role != "referee"}
        if ball_visible and ball_xy is not None:
            chosen = self._select(indexed, ball_xy)
            if chosen is not None:
                self.current_id = chosen.track_id
                self.missing = 0
                return PossessorFix(
                    track_id=chosen.track_id,
                    xy=ball_xy,
                    team=chosen.team,
                    held=False,
                    source="ball",
                )
            self.current_id = None
            self.missing = 0
            return PossessorFix(
                track_id=None,
                xy=ball_xy,
                team="home",
                held=False,
                source="loose",
            )
        self.missing += gap
        held = indexed.get(self.current_id) if self.current_id is not None else None
        if held is not None and self.missing <= self.hold_frames:
            return PossessorFix(
                track_id=held.track_id,
                xy=held.xy,
                team=held.team,
                held=True,
                source="held",
            )
        if self.missing > self.hold_frames:
            self.current_id = None
        return PossessorFix(track_id=None, xy=None, team="home", held=False, source="none")

    def _select(
        self,
        indexed: dict[int, PlayerFix],
        ball_xy: tuple[float, float],
    ) -> PlayerFix | None:
        ranked = sorted(
            (
                (_dist(player.xy, ball_xy), player)
                for player in indexed.values()
            ),
            key=lambda item: item[0],
        )
        if not ranked or ranked[0][0] > self.max_distance:
            return None
        nearest_distance, nearest = ranked[0]
        current = indexed.get(self.current_id) if self.current_id is not None else None
        if current is None:
            return nearest
        current_distance = _dist(current.xy, ball_xy)
        if current_distance <= self.max_distance and current_distance <= nearest_distance * self.switch_ratio:
            return current
        return nearest


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
