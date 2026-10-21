"""Completion value: pitch control times a static xT surface.

Both pieces are analytic. Nothing is fit on a real match, and nothing calls
a paid API. Pitch control is a Gaussian influence of the 22 tracked players
(numpy). xT is a smooth function of attack-frame position: higher toward the
goal being attacked, higher in the centre, with a floor inside the penalty box.

A single decision scores a handful of pass ends and one carry end. That call
is meant to stay under 50 ms.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from inside_the_game.features.from_tracking import HALF_LENGTH_M, HALF_WIDTH_M, attack_multiplier


SIGMA_M = 7.0
VELOCITY_LEAD_S = 0.15
BOX_DEPTH_M = 16.5
BOX_HALF_WIDTH_M = 20.16


def completion_value(
    points: Sequence[tuple[float, float]],
    frame: Mapping[str, Any],
    team_id: str,
    team_of: Mapping[str, str],
) -> list[float]:
    """``pitch_control(point) * xT(point)`` for each centre-spot point.

    ``points`` are metres in the tracking frame (origin at the centre spot).
    xT is evaluated after the section 6 attack flip, so both teams share one
    surface with +x toward the goal they are attacking.
    """
    if not points:
        return []
    multiplier = attack_multiplier(int(frame["attack_dir"]), team_id)
    control = pitch_control(points, frame, team_id, team_of)
    attack = np.asarray(points, dtype=float) * float(multiplier)
    threat = expected_threat(attack[:, 0], attack[:, 1])
    return [float(value) for value in (control * threat)]


def pitch_control(
    points: Sequence[tuple[float, float]],
    frame: Mapping[str, Any],
    team_id: str,
    team_of: Mapping[str, str],
) -> np.ndarray:
    """Share of Gaussian influence belonging to ``team_id`` at each point.

    Influence uses distance, shortened when the player is running toward the
    point. The result is in ``(0, 1)``.
    """
    xy, velocity, teams = _players(frame, team_of)
    target = np.asarray(points, dtype=float)
    delta = target[:, None, :] - xy[None, :, :]
    distance = np.linalg.norm(delta, axis=-1)
    unit = delta / np.clip(distance[..., None], 1e-6, None)
    closing = np.sum(velocity[None, :, :] * unit, axis=-1)
    effective = np.maximum(0.3, distance - VELOCITY_LEAD_S * np.maximum(closing, 0.0))
    influence = np.exp(-0.5 * (effective / SIGMA_M) ** 2)
    attacking = teams == team_id
    if not np.any(attacking) or np.all(attacking):
        raise ValueError(f"{team_id} does not split the frame into two teams")
    own = influence[:, attacking].sum(axis=1)
    other = influence[:, ~attacking].sum(axis=1)
    return own / (own + other)


def expected_threat(x_attack: np.ndarray, y_attack: np.ndarray) -> np.ndarray:
    """Static xT in the attack frame. +x is the goal being attacked.

    ``x_attack`` is metres from the centre spot, in ``[-52.5, 52.5]``.
    The surface is not a fitted transition matrix.
    """
    x = np.asarray(x_attack, dtype=float)
    y = np.asarray(y_attack, dtype=float)
    progress = np.clip((x + HALF_LENGTH_M) / (2.0 * HALF_LENGTH_M), 0.0, 1.0)
    centrality = 1.0 - np.clip(np.abs(y) / HALF_WIDTH_M, 0.0, 1.0)
    channel = 0.55 + 0.45 * centrality
    surface = (0.015 + 0.20 * progress**3) * channel
    depth = np.clip((x - (HALF_LENGTH_M - BOX_DEPTH_M)) / BOX_DEPTH_M, 0.0, 1.0)
    box_value = 0.25 + 0.55 * depth * channel
    in_box = (x >= HALF_LENGTH_M - BOX_DEPTH_M) & (np.abs(y) <= BOX_HALF_WIDTH_M)
    return np.where(in_box, np.maximum(surface, box_value), surface)


def _players(
    frame: Mapping[str, Any],
    team_of: Mapping[str, str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xy: list[list[float]] = []
    velocity: list[list[float]] = []
    teams: list[str] = []
    for row in frame["players"]:
        player_id = str(row[0])
        team_id = team_of.get(player_id)
        if team_id is None:
            raise KeyError(f"{player_id} is missing from the team map")
        xy.append([float(row[1]), float(row[2])])
        velocity.append([float(row[3]), float(row[4])])
        teams.append(team_id)
    return (
        np.asarray(xy, dtype=float),
        np.asarray(velocity, dtype=float),
        np.asarray(teams),
    )
