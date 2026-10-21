"""Map a computer-vision observation onto the System 1 feature vector.

The fitted softmax reads exactly ``FEATURE_NAMES``:
``ball_x``, ``ball_y``, ``centrality``, ``pressure``, ``minute``, ``goal_diff``.

``features_from_cv`` builds a ``MatchEvent`` and calls ``extract_features``,
so a pitch-meter observation uses the same count, order, and units as
training. Image-plane fallbacks are converted into that 105 by 68 meter
frame first; they are a stand-in, not a calibrated pitch.
"""

from __future__ import annotations

from inside_the_game.features.extract import FEATURE_NAMES, FeatureVector, extract_features
from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH, MatchEvent, zone_name


# Same two levels the StatsBomb ingest writes for ``under_pressure``.
PRESSURE_TIGHT = 0.82
PRESSURE_LOOSE = 0.18
CV_FEATURE_NAMES = FEATURE_NAMES


def features_from_cv(
    *,
    ball_x_m: float,
    ball_y_m: float,
    possession_team: str,
    pressure: float,
    minute: int,
    score_home: int = 0,
    score_away: int = 0,
    second: int = 0,
) -> FeatureVector:
    """Return the six training features for one on-ball observation.

    ``ball_x_m`` / ``ball_y_m`` are absolute pitch meters (home attacks toward
    x = 105), the same frame as ``MatchEvent``. ``pressure`` is in ``[0, 1]``.
    ``minute`` is a match minute; the vector stores ``minute / 90``.
    ``goal_diff`` is ``(own - other) / 5`` from the possession team's view.
    """
    team = possession_team if possession_team in ("home", "away") else "home"
    ball_x = _clamp(float(ball_x_m), 0.0, PITCH_LENGTH)
    ball_y = _clamp(float(ball_y_m), 0.0, PITCH_WIDTH)
    event = MatchEvent(
        event_id="cv",
        match_id="cv",
        minute=int(_clamp(float(minute), 0.0, 120.0)),
        second=int(_clamp(float(second), 0.0, 59.0)),
        team=team,
        player="on-ball",
        ball_x=ball_x,
        ball_y=ball_y,
        score_home=int(score_home),
        score_away=int(score_away),
        possession_team=team,
        pressure=_clamp(float(pressure), 0.0, 1.0),
        zone=zone_name(ball_x, ball_y, team),
        context="",
    )
    return extract_features(event)


def image_xy_to_pitch_meters(
    x: float,
    y: float,
    width: float,
    height: float,
) -> tuple[float, float]:
    """Stand-in pitch meters when no homography is available.

    The image is stretched onto the training pitch: x to the right maps to
    ``[0, 105]``, y downward maps to ``[0, 68]``. Callers still pass the
    result through ``features_from_cv``, so the softmax sees the usual units.
    """
    if width <= 0 or height <= 0:
        return (0.0, 0.0)
    return (
        _clamp(x / width * PITCH_LENGTH, 0.0, PITCH_LENGTH),
        _clamp(y / height * PITCH_WIDTH, 0.0, PITCH_WIDTH),
    )


def pressure_from_distances(
    distances_m: list[float],
    *,
    near_m: float = 3.0,
    far_m: float = 12.0,
) -> float:
    """Opponent distance to the StatsBomb pressure scale.

    A marker inside ``near_m`` is ``0.82`` (the ingest value for
    ``under_pressure``). Beyond ``far_m`` the value is ``0.18``. Distances
    in between are linear in that same ``[0.18, 0.82]`` band.
    """
    if not distances_m:
        return PRESSURE_LOOSE
    distance = min(distances_m)
    if distance <= near_m:
        return PRESSURE_TIGHT
    if distance >= far_m:
        return PRESSURE_LOOSE
    span = far_m - near_m
    if span <= 0:
        return PRESSURE_TIGHT
    blend = (distance - near_m) / span
    return PRESSURE_TIGHT + blend * (PRESSURE_LOOSE - PRESSURE_TIGHT)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
