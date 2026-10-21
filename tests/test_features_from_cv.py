"""CV observations must hit the same six features the softmax was trained on."""

import json
from pathlib import Path

from inside_the_game.features.extract import FEATURE_NAMES, extract_features
from inside_the_game.features.from_cv import (
    PRESSURE_LOOSE,
    PRESSURE_TIGHT,
    features_from_cv,
    image_xy_to_pitch_meters,
    pressure_from_distances,
)
from inside_the_game.ingest.events import MatchEvent
from inside_the_game.system1.policy import SoftmaxActionPolicy


WEIGHTS = Path("src/inside_the_game/system1/weights.json")


def _event(**overrides) -> MatchEvent:
    payload = dict(
        event_id="cv-check",
        match_id="cv-check",
        minute=45,
        second=0,
        team="home",
        player="on-ball",
        ball_x=52.5,
        ball_y=34.0,
        score_home=0,
        score_away=0,
        possession_team="home",
        pressure=0.18,
        zone="",
        context="",
    )
    payload.update(overrides)
    return MatchEvent(**payload)


def test_cv_features_match_training_vector_and_weights_file() -> None:
    document = json.loads(WEIGHTS.read_text(encoding="utf-8"))
    assert list(FEATURE_NAMES) == document["feature_names"]
    assert len(FEATURE_NAMES) == 6
    cases = [
        _event(),
        _event(
            ball_x=84.0,
            ball_y=17.0,
            minute=90,
            second=12,
            team="away",
            possession_team="away",
            pressure=0.82,
            score_home=2,
            score_away=0,
        ),
        _event(ball_x=10.0, ball_y=60.0, minute=0, pressure=0.4, score_home=0, score_away=3),
    ]
    policy = SoftmaxActionPolicy()
    for event in cases:
        trained = extract_features(event)
        observed = features_from_cv(
            ball_x_m=event.ball_x,
            ball_y_m=event.ball_y,
            possession_team=event.possession_team,
            pressure=event.pressure,
            minute=event.minute,
            second=event.second,
            score_home=event.score_home,
            score_away=event.score_away,
        )
        assert observed.as_tuple() == trained.as_tuple()
        assert len(observed.as_tuple()) == len(document["weights"]["pass"])
        assert tuple(observed.__dict__) == FEATURE_NAMES
        for value, name in zip(observed.as_tuple(), FEATURE_NAMES, strict=True):
            if name == "goal_diff":
                assert -1.0 <= value <= 1.0
            else:
                assert 0.0 <= value <= 1.0
        assert policy.predict(event).as_dict() == policy.predict_features(observed).as_dict()


def test_feature_units_are_pinned() -> None:
    home = features_from_cv(
        ball_x_m=52.5,
        ball_y_m=34.0,
        possession_team="home",
        pressure=0.18,
        minute=45,
    )
    assert home.as_tuple() == (0.5, 0.5, 1.0, 0.18, 0.5, 0.0)
    away = features_from_cv(
        ball_x_m=84.0,
        ball_y_m=17.0,
        possession_team="away",
        pressure=0.82,
        minute=90,
        score_home=2,
        score_away=0,
    )
    assert away.ball_x == 21.0 / 105.0
    assert away.ball_y == 51.0 / 68.0
    assert away.centrality == 0.5
    assert away.pressure == 0.82
    assert away.minute == 1.0
    assert away.goal_diff == -0.4


def test_image_fallback_stays_on_the_training_pitch() -> None:
    ball_x, ball_y = image_xy_to_pitch_meters(960, 540, 1920, 1080)
    assert ball_x == 52.5
    assert ball_y == 34.0
    observed = features_from_cv(
        ball_x_m=ball_x,
        ball_y_m=ball_y,
        possession_team="home",
        pressure=PRESSURE_LOOSE,
        minute=10,
    )
    trained = extract_features(
        _event(ball_x=ball_x, ball_y=ball_y, minute=10, pressure=PRESSURE_LOOSE)
    )
    assert observed.as_tuple() == trained.as_tuple()
    corner = image_xy_to_pitch_meters(-20, 5000, 1920, 1080)
    assert corner == (0.0, 68.0)


def test_pressure_uses_the_statsbomb_scale() -> None:
    assert pressure_from_distances([]) == PRESSURE_LOOSE
    assert pressure_from_distances([1.0, 8.0]) == PRESSURE_TIGHT
    assert pressure_from_distances([20.0]) == PRESSURE_LOOSE
    mid = pressure_from_distances([7.5])
    assert PRESSURE_LOOSE < mid < PRESSURE_TIGHT
