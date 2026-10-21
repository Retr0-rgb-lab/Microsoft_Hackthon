"""On-ball identity with hysteresis and a hold across missed detections."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    # A different team has to be nearer for this many visible frames before
    # the arrows flip to their goal. One noisy ball box must not do it.
    switch_frames: int = 5
    commit_distance: float | None = None
    current_id: int | None = None
    missing: int = 0
    pending_id: int | None = None
    pending_count: int = 0

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
            self.pending_id = None
            self.pending_count = 0
            return nearest
        current_distance = _dist(current.xy, ball_xy)
        if current_distance <= self.max_distance and current_distance <= nearest_distance * self.switch_ratio:
            self.pending_id = None
            self.pending_count = 0
            return current
        if nearest.track_id == current.track_id:
            self.pending_id = None
            self.pending_count = 0
            return current
        cross_team = (
            nearest.team != current.team
            and nearest.team in ("home", "away")
            and current.team in ("home", "away")
        )
        commit = self.max_distance * 0.35 if self.commit_distance is None else self.commit_distance
        if cross_team and nearest_distance > commit:
            if self.pending_id == nearest.track_id:
                self.pending_count += 1
            else:
                self.pending_id = nearest.track_id
                self.pending_count = 1
            if self.pending_count < self.switch_frames:
                return current
        self.pending_id = None
        self.pending_count = 0
        return nearest


@dataclass
class FootTrail:
    """Image-space foot point for the possessor ring and arrow tails.

    A short average keeps the marker on the feet. A teleport (id reuse, a
    cut) snaps instead of sliding across the frame.
    """

    alpha: float = 0.30
    points: dict[int, tuple[float, float]] = field(default_factory=dict)

    def smooth(
        self,
        track_id: int,
        xy: tuple[float, float],
        *,
        snap_at: float,
    ) -> tuple[float, float]:
        previous = self.points.get(track_id)
        if previous is None or _dist(previous, xy) >= snap_at:
            self.points[track_id] = xy
            return xy
        blended = (
            (1.0 - self.alpha) * previous[0] + self.alpha * xy[0],
            (1.0 - self.alpha) * previous[1] + self.alpha * xy[1],
        )
        self.points[track_id] = blended
        return blended

    def retain(self, live: set[int]) -> None:
        for track_id in list(self.points):
            if track_id not in live:
                del self.points[track_id]


@dataclass
class BallMark:
    """Light ball graphic. Unstable or far-from-feet detections are hidden.

    The mark does not coast on velocity. Possession still uses
    ``BallSmoother``, which keeps the hold and the low-confidence jump reject.
    """

    max_jump: float = 80.0
    max_foot_gap: float = 90.0
    stable_needed: int = 3
    hold_gaps: int = 3
    alpha: float = 0.35
    xy: tuple[float, float] | None = None
    stable: int = 0
    missing: int = 0
    last: tuple[float, float] | None = None

    def reset(self) -> None:
        self.xy = None
        self.stable = 0
        self.missing = 0
        self.last = None

    def update(
        self,
        measured: tuple[float, float] | None,
        *,
        visible: bool,
        possessor_foot: tuple[float, float] | None,
    ) -> tuple[float, float] | None:
        """Return a display point, or ``None`` when the detection is not calm.

        A short gap (the frames ``--stride`` skips) keeps the last accepted
        point still. It does not extrapolate velocity. A jump or a detection
        far from the possessor's feet hides the mark.
        """
        if not visible or measured is None:
            self.missing += 1
            if self.missing > self.hold_gaps:
                self.stable = 0
                self.xy = None
                return None
            if self.xy is None or self.stable < self.stable_needed:
                return None
            return self.xy
        self.missing = 0
        if self.last is not None and _dist(measured, self.last) > self.max_jump:
            self.stable = 0
            self.last = measured
            self.xy = None
            return None
        self.last = measured
        if possessor_foot is not None and _dist(measured, possessor_foot) > self.max_foot_gap:
            self.stable = 0
            self.xy = None
            return None
        self.stable += 1
        if self.xy is None:
            self.xy = measured
        else:
            self.xy = (
                (1.0 - self.alpha) * self.xy[0] + self.alpha * measured[0],
                (1.0 - self.alpha) * self.xy[1] + self.alpha * measured[1],
            )
        if self.stable < self.stable_needed:
            return None
        return self.xy


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
