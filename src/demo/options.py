"""On-ball arrows for the softmax class: one bright primary, a few dim alternatives.

Softmax chooses the action class (pass, dribble, shoot, hold). It does not
choose a receiver. A pass recommendation draws the best visible teammate bright
and up to two next-best teammates dimmer. Every pass receiver's shirt must
match the possessor in Lab and chroma. A dribble recommendation draws one
short carry into open space, plus at most one dim pass. Shoot and hold stay in
the probability bars. Coordinates are pitch meters or image pixels; thresholds
scale with the frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from demo.teams import jerseys_match
from inside_the_game.labels import ACTION_LABELS


PRIMARY_ALPHA = 0.95
SECONDARY_ALPHA = 0.40
MAX_SECONDARIES = 2


@dataclass(frozen=True)
class OptionPlayer:
    track_id: int
    xy: tuple[float, float]
    team: str
    role: str = "player"
    jersey: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class TacticalOption:
    kind: str
    origin: tuple[float, float]
    target: tuple[float, float]
    score: float
    primary: bool
    alpha: float
    label: str
    target_id: int | None = None
    slot: str = ""


def attacking_positive_for(team: str) -> bool:
    """Home defends x = 0, so home attacks toward the far goal."""
    return team != "away"


def opponent_goal(
    bounds: tuple[float, float],
    attacking_positive: bool,
) -> tuple[float, float]:
    """Centre of the goal the on-ball team is attacking, on ``bounds``."""
    length, width = bounds
    goal_x = length if attacking_positive else 0.0
    return (goal_x, width / 2.0)


def pass_window(bounds: tuple[float, float], space: str) -> tuple[float, float]:
    """Minimum and maximum pass length on this plane."""
    limits = _thresholds(bounds, space)
    return (limits["pass_min"], limits["pass_max"])


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
    """Primary arrow for ``recommended``, plus at most two dimmer alternatives.

    ``recommended`` is the System 1 class. Pass targets come from the geometric
    ranking below, never from the softmax itself. Shoot and hold draw nothing.
    """
    if recommended not in ACTION_LABELS:
        raise ValueError(f"recommended must be one of {ACTION_LABELS}")
    if recommended == "pass":
        return _display_passes(
            origin, players, possessor_id, possessor_team, bounds, attacking_positive, space
        )
    if recommended == "dribble":
        return _display_carry(
            origin, players, possessor_id, possessor_team, bounds, attacking_positive, space
        )
    return []


def compose_drawn(
    recommended: str,
    held: list[TacticalOption],
    fresh: list[TacticalOption],
    teammates: dict[int, tuple[float, float]] | None = None,
) -> list[TacticalOption]:
    """Held primary, plus this frame's limited alternatives.

    ``held`` is the temporally locked arrow. ``fresh`` is ``build_options`` for
    the same class. When ``teammates`` is given, every pass is re-pinned to that
    live position and a pass with no entry there is dropped.
    """
    if recommended == "pass":
        return _compose_passes(held, fresh, teammates)
    if recommended == "dribble":
        return _compose_carry(held, fresh, teammates)
    return []


def _display_passes(origin, players, possessor_id, possessor_team, bounds, attacking_positive, space):
    limits = _thresholds(bounds, space)
    mates = eligible_receivers(players, possessor_id, possessor_team, attacking_positive, bounds)
    found = _passes(origin, mates, players, possessor_team, bounds, attacking_positive, limits)
    shown: list[TacticalOption] = []
    for item in found:
        mate = mates.get(item.target_id) if item.target_id is not None else None
        if mate is None:
            continue
        primary = not shown
        shown.append(
            replace(
                item,
                target=mate.xy,
                primary=primary,
                alpha=PRIMARY_ALPHA if primary else SECONDARY_ALPHA,
                label="pass",
                target_id=mate.track_id,
            )
        )
        if len(shown) >= 1 + MAX_SECONDARIES:
            break
    return shown


def _display_carry(origin, players, possessor_id, possessor_team, bounds, attacking_positive, space):
    limits = _thresholds(bounds, space)
    found = _carries(
        origin, players, possessor_id, possessor_team, bounds, attacking_positive, limits
    )
    if not found:
        return []
    best = max(found, key=lambda item: item.score)
    carry = replace(best, primary=True, alpha=PRIMARY_ALPHA, label="carry", target_id=None)
    mates = eligible_receivers(players, possessor_id, possessor_team, attacking_positive, bounds)
    passes = _passes(origin, mates, players, possessor_team, bounds, attacking_positive, limits)
    if not passes:
        return [carry]
    alt = passes[0]
    mate = mates.get(alt.target_id) if alt.target_id is not None else None
    if mate is None:
        return [carry]
    return [
        carry,
        replace(
            alt,
            target=mate.xy,
            primary=False,
            alpha=SECONDARY_ALPHA,
            label="pass",
            target_id=mate.track_id,
        ),
    ]


def _compose_passes(held, fresh, teammates):
    primary = next((item for item in held if item.primary and item.kind == "pass"), None)
    if primary is None:
        primary = next((item for item in fresh if item.primary and item.kind == "pass"), None)
    if primary is None:
        return []
    pinned = _pin_pass(replace(primary, primary=True, alpha=PRIMARY_ALPHA, label="pass"), teammates)
    if pinned is None:
        return []
    secondaries: list[TacticalOption] = []
    for item in _pass_pool(fresh):
        if item.target_id == pinned.target_id:
            continue
        alt = _pin_pass(replace(item, primary=False, alpha=SECONDARY_ALPHA, label="pass"), teammates)
        if alt is None:
            continue
        secondaries.append(alt)
        if len(secondaries) >= MAX_SECONDARIES:
            break
    return [pinned, *secondaries]


def _compose_carry(held, fresh, teammates):
    primary = next((item for item in held if item.kind == "dribble"), None)
    if primary is None:
        primary = next((item for item in fresh if item.kind == "dribble" and item.primary), None)
    if primary is None:
        return []
    carry = replace(primary, kind="dribble", primary=True, alpha=PRIMARY_ALPHA, label="carry", target_id=None)
    for item in _pass_pool(fresh):
        alt = _pin_pass(replace(item, primary=False, alpha=SECONDARY_ALPHA, label="pass"), teammates)
        if alt is None:
            continue
        return [carry, alt]
    return [carry]


def _pass_pool(options: list[TacticalOption]) -> list[TacticalOption]:
    best: dict[int, TacticalOption] = {}
    for item in options:
        if item.kind != "pass" or item.target_id is None:
            continue
        current = best.get(item.target_id)
        if current is None or item.score > current.score:
            best[item.target_id] = item
    return sorted(best.values(), key=lambda item: item.score, reverse=True)


def _pin_pass(
    item: TacticalOption,
    teammates: dict[int, tuple[float, float]] | None,
) -> TacticalOption | None:
    """Drop a pass that does not end on a teammate still in this frame."""
    if item.kind != "pass":
        return item
    if item.target_id is None:
        return None
    if teammates is None:
        return item
    xy = teammates.get(item.target_id)
    if xy is None:
        return None
    return replace(item, target=xy, target_id=item.target_id)


def _teammates(
    players: list[OptionPlayer],
    possessor_id: int,
    possessor_team: str,
    attacking_positive: bool,
    bounds: tuple[float, float],
) -> dict[int, OptionPlayer]:
    """Same-team receivers. Never the opponent keeper, even if mislabelled."""
    if possessor_team not in ("home", "away"):
        return {}
    mates: dict[int, OptionPlayer] = {}
    for player in players:
        if player.track_id == possessor_id or player.role == "referee":
            continue
        if player.team != possessor_team:
            continue
        if is_opponent_goalkeeper(player, attacking_positive, bounds):
            continue
        mates[player.track_id] = player
    return mates


def eligible_receivers(
    players: list[OptionPlayer],
    possessor_id: int,
    possessor_team: str,
    attacking_positive: bool,
    bounds: tuple[float, float],
) -> dict[int, OptionPlayer]:
    """Same-team receivers whose shirt is close enough to the possessor.

    The geometric ranking still picks the arrow. This gate drops a body the
    team label called a teammate when the shirt is the other kit. Own
    goalkeepers are exempt: their team comes from the goal they stand in, so
    a keeper shirt must not wipe outfield passes either. Once the possessor
    shirt is known, a receiver with no sample is rejected.
    """
    mates = _teammates(players, possessor_id, possessor_team, attacking_positive, bounds)
    possessor = next((player for player in players if player.track_id == possessor_id), None)
    if possessor is not None and possessor.role == "goalkeeper":
        return mates
    possessor_jersey = None if possessor is None else possessor.jersey
    return {
        track_id: player
        for track_id, player in mates.items()
        if player.role == "goalkeeper" or jerseys_match(possessor_jersey, player.jersey)
    }


def _passes(origin, mates, players, possessor_team, bounds, attacking_positive, limits):
    if not mates:
        return []
    found: list[TacticalOption] = []
    opponents = [
        player
        for player in players
        if player.team not in (possessor_team, "unknown", "referee") and player.role != "referee"
    ]
    for player in mates.values():
        distance = _dist(origin, player.xy)
        if not limits["pass_min"] <= distance <= limits["pass_max"]:
            continue
        if _lane_blocked(origin, player.xy, opponents, limits["lane"]):
            continue
        score = _pass_score(origin, player.xy, opponents, bounds, attacking_positive, limits)
        found.append(
            TacticalOption(
                kind="pass",
                origin=origin,
                target=player.xy,
                score=score,
                primary=False,
                alpha=SECONDARY_ALPHA,
                label="pass",
                target_id=player.track_id,
                slot=f"pass:{player.track_id}",
            )
        )
    found.sort(key=lambda item: item.score, reverse=True)
    return found


def _pass_score(origin, target, opponents, bounds, attacking_positive, limits) -> float:
    """Advance and space, minus intercept risk. Length is only a light tax.

    A longer pass into a clear lane can outrank a short dump into traffic.
    ``limits['pass_max']`` is what rejects an absurd length, not this tax.
    """
    distance = _dist(origin, target)
    advance = _attack(target, bounds, attacking_positive) - _attack(origin, bounds, attacking_positive)
    lane_clearance = _clearance(origin, target, opponents)
    if opponents:
        local_space = min(_dist(target, player.xy) for player in opponents)
    else:
        local_space = limits["open_space"]
    intercept = _intercept_risk(origin, target, opponents, limits["threat"])
    return (
        0.55 * advance
        + 0.35 * local_space
        + 0.25 * lane_clearance
        - 1.6 * intercept
        - 0.04 * distance
    )


def _carries(origin, players, possessor_id, possessor_team, bounds, attacking_positive, limits):
    """Search a forward fan and keep the direction with the best open space.

    The arrow is short and must not finish on a player, so a carry never reads
    as a pass into empty air.
    """
    opponents = [
        player
        for player in players
        if player.track_id != possessor_id
        and player.role != "referee"
        and player.team not in (possessor_team, "unknown", "referee")
    ]
    bodies = [
        player.xy
        for player in players
        if player.track_id != possessor_id and player.role != "referee"
    ]
    length, width = bounds
    step = limits["dribble"] * 0.58
    sign = 1.0 if attacking_positive else -1.0
    found: list[TacticalOption] = []
    for angle in range(-80, 81, 10):
        radians = math.radians(angle)
        direction = (sign * math.cos(radians), math.sin(radians))
        raw = (origin[0] + step * direction[0], origin[1] + step * direction[1])
        target = (_clamp(raw[0], 0.0, length), _clamp(raw[1], 0.0, width))
        cleared = _shorten_clear(origin, target, bodies, limits["body"], step * 0.35)
        # A crowded lane still gets a short stub. The arrow must not vanish,
        # and it must not be stretched out to a nearby player.
        if cleared is None:
            stub = step * 0.42
            target = (
                _clamp(origin[0] + stub * direction[0], 0.0, length),
                _clamp(origin[1] + stub * direction[1], 0.0, width),
            )
        else:
            target = cleared
        if _dist(origin, target) < step * 0.28:
            continue
        end_clear = min((_dist(target, player.xy) for player in opponents), default=limits["open_space"])
        lane_clear = _clearance(origin, target, opponents)
        forward = _attack(target, bounds, attacking_positive) - _attack(origin, bounds, attacking_positive)
        nearest_body = min((_dist(target, body) for body in bodies), default=limits["open_space"])
        crowd = max(0.0, limits["body"] * 2.6 - nearest_body)
        score = 1.0 * forward + 0.55 * end_clear + 0.30 * lane_clear - 0.85 * crowd
        found.append(
            TacticalOption(
                kind="dribble",
                origin=origin,
                target=target,
                score=score,
                primary=False,
                alpha=SECONDARY_ALPHA,
                label="carry",
                slot=f"dribble:{angle}",
            )
        )
    found.sort(key=lambda item: item.score, reverse=True)
    return found[:1]


def is_opponent_goalkeeper(
    player: OptionPlayer,
    attacking_positive: bool,
    bounds: tuple[float, float],
) -> bool:
    """True when this keeper is standing in the goal being attacked."""
    if player.role != "goalkeeper":
        return False
    goal_x, _goal_y = opponent_goal(bounds, attacking_positive)
    reach = max(16.0, 0.12 * bounds[0])
    return abs(player.xy[0] - goal_x) <= reach


def _thresholds(bounds: tuple[float, float], space: str) -> dict[str, float]:
    length, _width = bounds
    if space == "pitch":
        return {
            "pass_min": 4.0,
            "pass_max": 36.0,
            "shot_min_attack": 62.0,
            "dribble": 11.0,
            "lane": 2.4,
            "threat": 8.0,
            "body": 3.2,
            "open_space": 18.0,
        }
    return {
        "pass_min": 0.04 * length,
        "pass_max": 0.45 * length,
        "shot_min_attack": 0.58 * length,
        "dribble": 0.12 * length,
        "lane": 0.035 * length,
        "threat": 0.08 * length,
        "body": 0.035 * length,
        "open_space": 0.18 * length,
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


def _intercept_risk(start, end, opponents, threat: float) -> float:
    """How easily a defender steps onto the pass. 0 is a free lane."""
    if not opponents or threat <= 1e-6:
        return 0.0
    risk = 0.0
    for player in opponents:
        along = _segment_param(player.xy, start, end)
        if along < 0.08 or along > 0.92:
            continue
        distance = _point_segment_distance(player.xy, start, end)
        risk += max(0.0, 1.0 - distance / threat)
    return risk


def _shorten_clear(origin, target, bodies, body_radius: float, min_length: float):
    """Pull a carry back until its tip is not sitting on a player."""
    point = target
    for _ in range(6):
        if all(_dist(point, body) >= body_radius for body in bodies):
            break
        point = (
            origin[0] + 0.72 * (point[0] - origin[0]),
            origin[1] + 0.72 * (point[1] - origin[1]),
        )
    if _dist(origin, point) < min_length:
        return None
    if any(_dist(point, body) < body_radius * 0.8 for body in bodies):
        return None
    return point


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
