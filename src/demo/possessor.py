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
    velocity: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class BallFix:
    """Smoothed ball. ``held`` means this frame reused an earlier detection."""

    xy: tuple[float, float] | None
    visible: bool
    held: bool
    confidence: float


# Possession is a small state machine. Softmax never chooses the receiver.
ON_BALL = "ON_BALL"
CONTESTED = "CONTESTED"
PASS_IN_FLIGHT = "PASS_IN_FLIGHT"
LOOSE = "LOOSE"


@dataclass(frozen=True)
class PossessorFix:
    track_id: int | None
    xy: tuple[float, float] | None
    team: str
    held: bool
    source: str
    state: str = LOOSE
    predicted_id: int | None = None


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
    """Who the arrows belong to: on the ball, contested, in flight, or loose.

    On the ball, a player earns the touch with distance, how well their
    velocity matches the ball, and a continuity bonus. A pass in flight is a
    fast ball that is not stuck to a foot: teammates are ranked by the earliest
    plausible intercept, and that predicted receiver — not the nearest body the
    ball happens to fly past — owns the options. A touch (the ball-foot gap
    collapses and the relative speed drops) is what commits a switch.

    When the ball is absent, the last id is kept for ``hold_frames`` frames
    and the ball is placed at that player's feet. Ball smoothing itself stays
    in ``BallSmoother``.
    """

    max_distance: float = 6.0
    hold_frames: int = 15
    switch_ratio: float = 1.35
    # A different team has to be nearer for this many visible frames before
    # the arrows flip to their goal. One noisy ball box must not do it.
    switch_frames: int = 5
    commit_distance: float | None = None
    # How many commit-radii count as "still at this player's feet".
    control_scale: float = 2.0
    flight_speed: float | None = None
    touch_rel_speed: float | None = None
    velocity_weight: float = 0.55
    receiver_speed: float | None = None
    flight_horizon: float = 24.0
    current_id: int | None = None
    missing: int = 0
    pending_id: int | None = None
    pending_count: int = 0
    state: str = LOOSE
    predicted_id: int | None = None
    passer_id: int | None = None
    possession_team: str | None = None

    def resolved_flight_speed(self) -> float:
        if self.flight_speed is None:
            return self.max_distance * 0.22
        return self.flight_speed

    def update(
        self,
        players: list[PlayerFix],
        ball_xy: tuple[float, float] | None,
        *,
        ball_visible: bool,
        frame_gap: int = 1,
        ball_velocity: tuple[float, float] = (0.0, 0.0),
    ) -> PossessorFix:
        gap = max(1, frame_gap)
        indexed = {player.track_id: player for player in players if player.role != "referee"}
        if ball_visible and ball_xy is not None:
            self.missing = 0
            touch = self._touch_player(indexed, ball_xy, ball_velocity)
            if touch is not None:
                self.pending_id = None
                self.pending_count = 0
                return self._commit(touch, ball_xy, contested=self._others_close(indexed, touch, ball_xy))
            if self._should_fly(indexed, ball_xy, ball_velocity):
                return self._fly(indexed, ball_xy, ball_velocity)
            chosen, contested = self._select(indexed, ball_xy, ball_velocity)
            if chosen is not None:
                return self._commit(chosen, ball_xy, contested=contested)
            self._clear_identity()
            self.state = LOOSE
            return PossessorFix(
                track_id=None,
                xy=ball_xy,
                team=self.possession_team or "home",
                held=False,
                source="loose",
                state=LOOSE,
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
                state=self.state if self.state in (ON_BALL, CONTESTED, PASS_IN_FLIGHT) else ON_BALL,
                predicted_id=self.predicted_id,
            )
        if self.missing > self.hold_frames:
            self._clear_identity()
            self.state = LOOSE
        return PossessorFix(track_id=None, xy=None, team=self.possession_team or "home", held=False, source="none", state=LOOSE)

    def _clear_identity(self) -> None:
        self.current_id = None
        self.predicted_id = None
        self.passer_id = None
        self.pending_id = None
        self.pending_count = 0

    def _commit(self, player: PlayerFix, ball_xy: tuple[float, float], *, contested: bool) -> PossessorFix:
        self.current_id = player.track_id
        self.possession_team = player.team
        self.passer_id = None
        self.predicted_id = None
        self.state = CONTESTED if contested else ON_BALL
        return PossessorFix(
            track_id=player.track_id,
            xy=ball_xy,
            team=player.team,
            held=False,
            source="ball",
            state=self.state,
        )

    def _fly(
        self,
        indexed: dict[int, PlayerFix],
        ball_xy: tuple[float, float],
        ball_velocity: tuple[float, float],
    ) -> PossessorFix:
        if self.state != PASS_IN_FLIGHT:
            self.passer_id = self.current_id
        team = self.possession_team
        if team not in ("home", "away"):
            passer = indexed.get(self.passer_id) if self.passer_id is not None else None
            team = passer.team if passer is not None else None
        receiver = None if team not in ("home", "away") else self._predict_receiver(
            indexed, ball_xy, ball_velocity, team, self.passer_id
        )
        if receiver is None:
            passer = indexed.get(self.passer_id) if self.passer_id is not None else None
            if passer is not None and _dist(passer.xy, ball_xy) <= self.max_distance:
                # The ray did not find a teammate, and this player is still in range.
                self.predicted_id = None
                return self._commit(passer, ball_xy, contested=False)
            self.predicted_id = None
            self.current_id = None
            self.pending_id = None
            self.pending_count = 0
            self.state = LOOSE
            return PossessorFix(
                track_id=None,
                xy=ball_xy,
                team=team or self.possession_team or "home",
                held=False,
                source="loose",
                state=LOOSE,
            )
        self.state = PASS_IN_FLIGHT
        self.predicted_id = receiver.track_id
        self.current_id = receiver.track_id
        self.possession_team = team
        self.pending_id = None
        self.pending_count = 0
        return PossessorFix(
            track_id=receiver.track_id,
            xy=ball_xy,
            team=receiver.team,
            held=False,
            source="pass",
            state=PASS_IN_FLIGHT,
            predicted_id=receiver.track_id,
        )

    def _should_fly(
        self,
        indexed: dict[int, PlayerFix],
        ball_xy: tuple[float, float],
        ball_velocity: tuple[float, float],
    ) -> bool:
        """A fast ball that is far from every foot is in flight.

        Distance is the gate. A noisy velocity while the ball is still next to
        someone must not launch a pass and drop the possessor.
        """
        if _hypot(ball_velocity) < self.resolved_flight_speed():
            return False
        if not indexed:
            return True
        nearest = min(_dist(player.xy, ball_xy) for player in indexed.values())
        return nearest > self._control_radius()

    def _touch_player(
        self,
        indexed: dict[int, PlayerFix],
        ball_xy: tuple[float, float],
        ball_velocity: tuple[float, float],
    ) -> PlayerFix | None:
        """Foot gap collapsed and the ball has slowed relative to that player."""
        commit = self._commit_radius()
        touch_rel = self._touch_rel()
        found: list[tuple[float, float, PlayerFix]] = []
        for player in indexed.values():
            dist = _dist(player.xy, ball_xy)
            if dist > commit:
                continue
            rel = _rel(player, ball_velocity)
            if rel > touch_rel:
                continue
            found.append((self._cost(player, ball_xy, ball_velocity), dist, player))
        if not found:
            return None
        found.sort(key=lambda item: (item[0], item[1], item[2].track_id))
        # A player who still has the ball at their feet keeps it. Someone else
        # inside the same bubble makes the state contested; they do not steal
        # on the first overlapping frame.
        if self.current_id is not None:
            for _cost, _dist_value, player in found:
                if player.track_id == self.current_id:
                    return player
        return found[0][2]

    def _select(
        self,
        indexed: dict[int, PlayerFix],
        ball_xy: tuple[float, float],
        ball_velocity: tuple[float, float],
    ) -> tuple[PlayerFix | None, bool]:
        ranked: list[tuple[float, float, PlayerFix]] = []
        for player in indexed.values():
            dist = _dist(player.xy, ball_xy)
            if dist > self.max_distance:
                continue
            ranked.append((self._cost(player, ball_xy, ball_velocity), dist, player))
        ranked.sort(key=lambda item: (item[0], item[1], item[2].track_id))
        if not ranked:
            return None, False
        best_cost, best_dist, best = ranked[0]
        current = indexed.get(self.current_id) if self.current_id is not None else None
        if current is None:
            self.pending_id = None
            self.pending_count = 0
            return best, self._contested(ranked, best.track_id)
        current_dist = _dist(current.xy, ball_xy)
        if current_dist > self.max_distance:
            self.pending_id = None
            self.pending_count = 0
            return best, self._contested(ranked, best.track_id)
        current_cost = self._cost(current, ball_xy, ball_velocity)
        if current_cost <= best_cost * self.switch_ratio:
            self.pending_id = None
            self.pending_count = 0
            return current, self._contested(ranked, current.track_id)
        if best.track_id == current.track_id:
            self.pending_id = None
            self.pending_count = 0
            return current, False
        cross_team = (
            best.team != current.team
            and best.team in ("home", "away")
            and current.team in ("home", "away")
        )
        if cross_team and best_dist > self._commit_radius():
            if self.pending_id == best.track_id:
                self.pending_count += 1
            else:
                self.pending_id = best.track_id
                self.pending_count = 1
            if self.pending_count < self.switch_frames:
                return current, True
        self.pending_id = None
        self.pending_count = 0
        return best, self._contested(ranked, best.track_id)

    def _predict_receiver(
        self,
        indexed: dict[int, PlayerFix],
        ball_xy: tuple[float, float],
        ball_velocity: tuple[float, float],
        team: str,
        exclude_id: int | None,
    ) -> PlayerFix | None:
        """Earliest teammate who can meet the ball along its ray. Not an opponent."""
        ranked: list[tuple[float, int, PlayerFix]] = []
        for player in indexed.values():
            if player.team != team or player.track_id == exclude_id:
                continue
            intercept = self._intercept_time(player, ball_xy, ball_velocity)
            if intercept is None:
                continue
            ranked.append((intercept, player.track_id, player))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]))
        best_time, _track_id, best = ranked[0]
        if self.predicted_id is not None:
            for intercept, _track_id, player in ranked:
                if player.track_id == self.predicted_id and intercept <= best_time * 1.25 + 0.75:
                    return player
        return best

    def _intercept_time(
        self,
        player: PlayerFix,
        ball_xy: tuple[float, float],
        ball_velocity: tuple[float, float],
    ) -> float | None:
        """Earliest frame when a running player can reach the ball ray."""
        speed = max(_hypot(player.velocity), self._receiver_speed())
        reach = max(self._commit_radius(), 1e-3)
        horizon = self.flight_horizon
        steps = 20
        previous_gap: float | None = None
        for index in range(steps + 1):
            moment = horizon * index / steps
            point = (
                ball_xy[0] + ball_velocity[0] * moment,
                ball_xy[1] + ball_velocity[1] * moment,
            )
            gap = _dist(player.xy, point) - reach - speed * moment
            if gap <= 0.0:
                if index == 0 or previous_gap is None or previous_gap <= 0.0:
                    return moment
                span = previous_gap - gap
                fraction = 0.0 if span <= 1e-9 else previous_gap / span
                return horizon * (index - 1 + fraction) / steps
            previous_gap = gap
        return None

    def _cost(
        self,
        player: PlayerFix,
        ball_xy: tuple[float, float],
        ball_velocity: tuple[float, float],
    ) -> float:
        """Lower is a better on-ball candidate. Distance plus velocity mismatch."""
        return _dist(player.xy, ball_xy) + self.velocity_weight * _rel(player, ball_velocity)

    def _contested(self, ranked: list[tuple[float, float, PlayerFix]], owner_id: int) -> bool:
        control = self._control_radius() * 1.25
        return any(player.track_id != owner_id and dist <= control for _cost, dist, player in ranked)

    def _others_close(self, indexed: dict[int, PlayerFix], owner: PlayerFix, ball_xy: tuple[float, float]) -> bool:
        bubble = self._control_radius()
        for player in indexed.values():
            if player.track_id == owner.track_id:
                continue
            if _dist(player.xy, ball_xy) <= bubble:
                return True
        return False

    def _commit_radius(self) -> float:
        if self.commit_distance is None:
            return self.max_distance * 0.35
        return self.commit_distance

    def _control_radius(self) -> float:
        return self._commit_radius() * self.control_scale

    def _touch_rel(self) -> float:
        if self.touch_rel_speed is None:
            return max(0.75, self.max_distance * 0.08)
        return self.touch_rel_speed

    def _receiver_speed(self) -> float:
        if self.receiver_speed is None:
            return max(0.4, self.max_distance * 0.12)
        return self.receiver_speed


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
    return _hypot((a[0] - b[0], a[1] - b[1]))


def _hypot(vector: tuple[float, float]) -> float:
    return (vector[0] ** 2 + vector[1] ** 2) ** 0.5


def _rel(player: PlayerFix, ball_velocity: tuple[float, float]) -> float:
    return _hypot((player.velocity[0] - ball_velocity[0], player.velocity[1] - ball_velocity[1]))
