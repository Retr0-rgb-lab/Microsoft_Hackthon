"""Pitch template, homography gates, and image-plane fallback.

The 32 vertices follow the Roboflow / ``roboflow/sports`` pitch keypoint
order (centimetres on a 120 m by 70 m template) scaled onto the 105 m by
68 m frame the softmax was trained on. Estimation itself lives in the video
pipeline so this module stays free of OpenCV.
"""

from __future__ import annotations

from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH


_LENGTH_CM = 12000.0
_WIDTH_CM = 7000.0
_PENALTY_BOX_WIDTH_CM = 4100.0
_PENALTY_BOX_LENGTH_CM = 2015.0
_GOAL_BOX_WIDTH_CM = 1832.0
_GOAL_BOX_LENGTH_CM = 550.0
_CENTRE_CIRCLE_RADIUS_CM = 915.0
_PENALTY_SPOT_CM = 1100.0

# 1-indexed edges of the pitch skeleton, matching roboflow/sports.
PITCH_EDGES: tuple[tuple[int, int], ...] = (
    (1, 2), (2, 3), (3, 4), (4, 5), (5, 6),
    (7, 8),
    (10, 11), (11, 12), (12, 13),
    (14, 15), (15, 16), (16, 17),
    (18, 19), (19, 20), (20, 21),
    (23, 24),
    (25, 26), (26, 27), (27, 28), (28, 29), (29, 30),
    (1, 14), (2, 10), (3, 7), (4, 8), (5, 13), (6, 17),
    (14, 25), (18, 26), (23, 27), (24, 28), (21, 29), (17, 30),
)


def pitch_vertices_m() -> tuple[tuple[float, float], ...]:
    """32 pitch landmarks in meters, index 0 = keypoint 1."""
    width = _WIDTH_CM
    length = _LENGTH_CM
    penalty_w = _PENALTY_BOX_WIDTH_CM
    penalty_l = _PENALTY_BOX_LENGTH_CM
    goal_w = _GOAL_BOX_WIDTH_CM
    goal_l = _GOAL_BOX_LENGTH_CM
    radius = _CENTRE_CIRCLE_RADIUS_CM
    spot = _PENALTY_SPOT_CM
    raw = (
        (0, 0),
        (0, (width - penalty_w) / 2),
        (0, (width - goal_w) / 2),
        (0, (width + goal_w) / 2),
        (0, (width + penalty_w) / 2),
        (0, width),
        (goal_l, (width - goal_w) / 2),
        (goal_l, (width + goal_w) / 2),
        (spot, width / 2),
        (penalty_l, (width - penalty_w) / 2),
        (penalty_l, (width - goal_w) / 2),
        (penalty_l, (width + goal_w) / 2),
        (penalty_l, (width + penalty_w) / 2),
        (length / 2, 0),
        (length / 2, width / 2 - radius),
        (length / 2, width / 2 + radius),
        (length / 2, width),
        (length - penalty_l, (width - penalty_w) / 2),
        (length - penalty_l, (width - goal_w) / 2),
        (length - penalty_l, (width + goal_w) / 2),
        (length - penalty_l, (width + penalty_w) / 2),
        (length - spot, width / 2),
        (length - goal_l, (width - goal_w) / 2),
        (length - goal_l, (width + goal_w) / 2),
        (length, 0),
        (length, (width - penalty_w) / 2),
        (length, (width - goal_w) / 2),
        (length, (width + goal_w) / 2),
        (length, (width + penalty_w) / 2),
        (length, width),
        (length / 2 - radius, width / 2),
        (length / 2 + radius, width / 2),
    )
    return tuple((_xm(x), _ym(y)) for x, y in raw)


def centre_circle_m(*, samples: int = 16) -> tuple[tuple[float, float], ...]:
    """Centre-circle samples in pitch meters, for a projected wireframe."""
    import math

    radius_x = _CENTRE_CIRCLE_RADIUS_CM / _LENGTH_CM * PITCH_LENGTH
    radius_y = _CENTRE_CIRCLE_RADIUS_CM / _WIDTH_CM * PITCH_WIDTH
    points = []
    for index in range(samples):
        theta = 2.0 * math.pi * index / samples
        points.append(
            (
                PITCH_LENGTH / 2.0 + radius_x * math.cos(theta),
                PITCH_WIDTH / 2.0 + radius_y * math.sin(theta),
            )
        )
    return tuple(points)


def assess_homography(
    n_points: int,
    n_inliers: int,
    mean_error_px: float | None,
    *,
    min_points: int = 4,
    min_inliers: int = 4,
    max_error_px: float = 25.0,
    weak_inliers: int = 6,
    weak_error_px: float = 10.0,
) -> tuple[bool, str]:
    """Decide whether a fit may drive the pitch plane.

    Fewer than four correspondences cannot define a homography. A fit with
    only a handful of inliers is kept only when the reprojection error is tight.
    """
    if n_points < min_points or n_inliers < min_inliers:
        return False, "too_few_keypoints"
    if mean_error_px is None or mean_error_px > max_error_px:
        return False, "reprojection_error"
    if n_inliers < weak_inliers and mean_error_px > weak_error_px:
        return False, "weak_fit"
    return True, "ok"


def resolve_plane(
    current_ok: bool,
    frames_since_good: int,
    scene_cut: bool,
    *,
    max_hold: int = 12,
) -> str:
    """Choose ``current``, ``held``, or ``image``.

    A scene cut never reuses the previous homography. A short run of failed
    fits keeps the last good matrix. After that the overlay drops to image
    coordinates instead of blocking the frame.
    """
    if current_ok:
        return "current"
    if scene_cut or frames_since_good > max_hold:
        return "image"
    return "held"


def scene_cut(mean_abs_diff: float, *, threshold: float = 30.0) -> bool:
    """True when a downsampled frame difference looks like a hard cut."""
    return mean_abs_diff >= threshold


def is_detection_frame(frame_idx: int, stride: int) -> bool:
    """Detector runs on frame 0, ``stride``, ``2*stride``, ..."""
    if stride < 1:
        raise ValueError("stride must be >= 1")
    return frame_idx % stride == 0


def apply_homography(
    matrix: tuple[tuple[float, float, float], ...],
    x: float,
    y: float,
) -> tuple[float, float] | None:
    """Map one point through a 3x3 homography. ``None`` if it is at infinity."""
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, i, j = matrix[2]
    denom = g * x + i * y + j
    if abs(denom) < 1e-9:
        return None
    return ((a * x + b * y + c) / denom, (d * x + e * y + f) / denom)


def invert_homography(
    matrix: tuple[tuple[float, float, float], ...],
) -> tuple[tuple[float, float, float], ...] | None:
    """Inverse of a 3x3 homography, or ``None`` when it is singular."""
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, i, j = matrix[2]
    det = a * (e * j - f * i) - b * (d * j - f * g) + c * (d * i - e * g)
    if abs(det) < 1e-12:
        return None
    return (
        ((e * j - f * i) / det, (c * i - b * j) / det, (b * f - c * e) / det),
        ((f * g - d * j) / det, (a * j - c * g) / det, (c * d - a * f) / det),
        ((d * i - e * g) / det, (b * g - a * i) / det, (a * e - b * d) / det),
    )


def project_segment(
    matrix: tuple[tuple[float, float, float], ...],
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    samples: int = 14,
    max_jump_px: float = 800.0,
) -> tuple[tuple[float, float], ...] | None:
    """Sample a pitch segment and project it. Drop segments that explode."""
    if samples < 2:
        raise ValueError("samples must be >= 2")
    points: list[tuple[float, float]] = []
    for index in range(samples):
        blend = index / (samples - 1)
        x = start[0] + blend * (end[0] - start[0])
        y = start[1] + blend * (end[1] - start[1])
        projected = apply_homography(matrix, x, y)
        if projected is None:
            return None
        if points:
            jump = _hypot(projected[0] - points[-1][0], projected[1] - points[-1][1])
            if jump > max_jump_px:
                return None
        points.append(projected)
    return tuple(points)


def _xm(cm: float) -> float:
    return cm / _LENGTH_CM * PITCH_LENGTH


def _ym(cm: float) -> float:
    return cm / _WIDTH_CM * PITCH_WIDTH


def _hypot(dx: float, dy: float) -> float:
    return (dx * dx + dy * dy) ** 0.5
