"""Reasonable on-ball options: passes, carries, and a shot.

The highlighted arrow is the best geometric option of the action the softmax
recommends. The other options stay on screen at a lower alpha. Coordinates
are either pitch meters or image pixels; thresholds scale with the frame.
"""

from __future__ import annotations

from dataclasses import dataclass

from inside_the_game.labels import ACTION_LABELS


PRIMARY_ALPHA = 0.95
SECONDARY_ALPHA = 0.34


@dataclass(frozen=True)
class OptionPlayer:
    track_id: int
    xy: tuple[float, float]
    team: str
    role: str = "player"


@dataclass(frozen=True)
class TacticalOption:
    kind: str
    origin: tuple[float, float]
    target: tuple[float, float]
    score: float
    primary: bool
    alpha: float
    label: str


def build_options(
    origin: tuple[float, float],
    players: list[OptionPlayer],
    possessor_id: int,
    possessor_team: str,
    recommended: str,
    *,
    bounds: tuple[float, float],
    attacking_positive: bool,
    space: str = "pitch",
) -> list[TacticalOption]:
    """Options for one on-ball player. ``recommended`` is a System 1 label."""
    if recommended not in ACTION_LABELS:
        raise ValueError(f"recommended must be one of {ACTION_LABELS}")
    limits = _thresholds(bounds, space)
    passes = _passes(origin, players, possessor_id, possessor_team, bounds, attacking_positive, limits)
    carries = _carries(
        origin, players, possessor_id, possessor_team, bounds, attacking_positive, limits
    )
    shots = _shots(origin, bounds, attacking_positive, limits)
    hold = TacticalOption(
        kind="hold",
        origin=origin,
        target=origin,
        score=0.15,
        primary=False,
        alpha=SECONDARY_ALPHA,
        label="hold",
    )
    pool = passes + carries + shots + [hold]
    pool = _ensure_recommended(pool, origin, players, possessor_id, possessor_team, recommended, bounds, attacking_positive, limits)
    return _mark_primary(pool, recommended)


def _passes(origin, players, possessor_id, possessor_team, bounds, attacking_positive, limits):
    if possessor_team not in ("home", "away"):
        return []
    found: list[TacticalOption] = []
    opponents = [player for player in players if player.team not in (possessor_team, "unknown", "referee") and player.role != "referee"]
    for player in players:
        if player.track_id == possessor_id or player.role == "referee":
            continue
        if player.team != possessor_team:
            continue
        distance = _dist(origin, player.xy)
        if not limits["pass_min"] <= distance <= limits["pass_max"]:
            continue
        if _lane_blocked(origin, player.xy, opponents, limits["lane"]):
            continue
        forward = _attack(player.xy, bounds, attacking_positive) - _attack(origin, bounds, attacking_positive)
        openness = _clearance(origin, player.xy, opponents)
        score = 0.015 * forward + 0.04 * openness - 0.01 * distance
        found.append(
            TacticalOption(
                kind="pass",
                origin=origin,
                target=player.xy,
                score=score,
                primary=False,
                alpha=SECONDARY_ALPHA,
                label="pass",
            )
        )
    found.sort(key=lambda item: item.score, reverse=True)
    return found[:3]


def _carries(origin, players, possessor_id, possessor_team, bounds, attacking_positive, limits):
    opponents = [
        player
        for player in players
        if player.track_id != possessor_id
        and player.role != "referee"
        and player.team not in (possessor_team, "unknown", "referee")
    ]
    length, width = bounds
    step = limits["dribble"]
    directions = ((1.0, 0.0), (0.72, 0.55), (0.72, -0.55))
    sign = 1.0 if attacking_positive else -1.0
    found: list[TacticalOption] = []
    for along, across in directions:
        raw = (origin[0] + sign * step * along, origin[1] + step * across * 0.65)
        target = (_clamp(raw[0], 0.0, length), _clamp(raw[1], 0.0, width))
        if _dist(origin, target) < step * 0.35:
            continue
        clearance = min((_dist(target, player.xy) for player in opponents), default=step)
        forward = _attack(target, bounds, attacking_positive) - _attack(origin, bounds, attacking_positive)
        score = 0.02 * forward + 0.03 * clearance
        found.append(
            TacticalOption(
                kind="dribble",
                origin=origin,
                target=target,
                score=score,
                primary=False,
                alpha=SECONDARY_ALPHA,
                label="carry",
            )
        )
    found.sort(key=lambda item: item.score, reverse=True)
    return found[:2]


def _shots(origin, bounds, attacking_positive, limits):
    attack = _attack(origin, bounds, attacking_positive)
    if attack < limits["shot_min_attack"]:
        return []
    length, width = bounds
    goal_x = length if attacking_positive else 0.0
    return [
        TacticalOption(
            kind="shoot",
            origin=origin,
            target=(goal_x, width / 2.0),
            score=0.02 * attack,
            primary=False,
            alpha=SECONDARY_ALPHA,
            label="shot",
        )
    ]


def _ensure_recommended(pool, origin, players, possessor_id, possessor_team, recommended, bounds, attacking_positive, limits):
    if any(item.kind == recommended for item in pool):
        return pool
    if recommended == "shoot":
        length, width = bounds
        goal_x = length if attacking_positive else 0.0
        extra = TacticalOption(
            kind="shoot",
            origin=origin,
            target=(goal_x, width / 2.0),
            score=0.01,
            primary=False,
            alpha=SECONDARY_ALPHA,
            label="shot",
        )
        return pool + [extra]
    if recommended == "pass":
        mates = [
            player for player in players
            if player.track_id != possessor_id and player.team == possessor_team and player.role != "referee"
        ]
        if not mates:
            return pool
        target = min(mates, key=lambda player: _dist(origin, player.xy))
        extra = TacticalOption(
            kind="pass",
            origin=origin,
            target=target.xy,
            score=0.01,
            primary=False,
            alpha=SECONDARY_ALPHA,
            label="pass",
        )
        return pool + [extra]
    if recommended == "dribble":
        sign = 1.0 if attacking_positive else -1.0
        step = limits["dribble"]
        target = (
            _clamp(origin[0] + sign * step, 0.0, bounds[0]),
            _clamp(origin[1], 0.0, bounds[1]),
        )
        extra = TacticalOption(
            kind="dribble",
            origin=origin,
            target=target,
            score=0.01,
            primary=False,
            alpha=SECONDARY_ALPHA,
            label="carry",
        )
        return pool + [extra]
    return pool


def _mark_primary(pool: list[TacticalOption], recommended: str) -> list[TacticalOption]:
    of_kind = [item for item in pool if item.kind == recommended]
    if not of_kind:
        return pool
    best = max(of_kind, key=lambda item: item.score)
    marked: list[TacticalOption] = []
    for item in pool:
        primary = item is best
        marked.append(
            TacticalOption(
                kind=item.kind,
                origin=item.origin,
                target=item.target,
                score=item.score,
                primary=primary,
                alpha=PRIMARY_ALPHA if primary else SECONDARY_ALPHA,
                label=item.label,
            )
        )
    marked.sort(key=lambda item: item.primary)
    return marked


def _thresholds(bounds: tuple[float, float], space: str) -> dict[str, float]:
    length, _width = bounds
    if space == "pitch":
        return {
            "pass_min": 4.0,
            "pass_max": 36.0,
            "shot_min_attack": 62.0,
            "dribble": 11.0,
            "lane": 2.4,
        }
    return {
        "pass_min": 0.04 * length,
        "pass_max": 0.45 * length,
        "shot_min_attack": 0.58 * length,
        "dribble": 0.12 * length,
        "lane": 0.035 * length,
    }


def _attack(xy: tuple[float, float], bounds: tuple[float, float], attacking_positive: bool) -> float:
    if attacking_positive:
        return xy[0]
    return bounds[0] - xy[0]


def _lane_blocked(start, end, opponents, lane: float) -> bool:
    for player in opponents:
        if _point_segment_distance(player.xy, start, end) > lane:
            continue
        along = _segment_param(player.xy, start, end)
        if 0.12 <= along <= 0.88:
            return True
    return False


def _clearance(start, end, opponents) -> float:
    if not opponents:
        return 20.0
    return min(_point_segment_distance(player.xy, start, end) for player in opponents)


def _point_segment_distance(point, start, end) -> float:
    param = _segment_param(point, start, end)
    projected = (
        start[0] + param * (end[0] - start[0]),
        start[1] + param * (end[1] - start[1]),
    )
    return _dist(point, projected)


def _segment_param(point, start, end) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denom))


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
