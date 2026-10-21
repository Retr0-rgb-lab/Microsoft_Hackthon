"""Possessor identity stays put when the ball disappears or jitters."""

from demo.possessor import (
    CONTESTED,
    LOOSE,
    ON_BALL,
    PASS_IN_FLIGHT,
    BallMark,
    BallSmoother,
    FootTrail,
    PlayerFix,
    PossessorTracker,
)
from demo.tracking import TrackState, predict_tracks, velocities_from_previous


def _players() -> list[PlayerFix]:
    return [
        PlayerFix(1, (20.0, 34.0), "home"),
        PlayerFix(2, (40.0, 20.0), "home"),
        PlayerFix(3, (30.0, 40.0), "away"),
    ]


def test_nearest_player_with_hysteresis() -> None:
    tracker = PossessorTracker(max_distance=20.0, switch_ratio=1.35)
    first = tracker.update(_players(), (21.0, 34.0), ball_visible=True)
    assert first.track_id == 1
    assert first.held is False
    # Player 2 is nearer here, but not by enough to take the ball.
    sticky = tracker.update(_players(), (31.0, 28.0), ball_visible=True)
    assert sticky.track_id == 1
    stolen = tracker.update(_players(), (39.0, 20.5), ball_visible=True)
    assert stolen.track_id == 2


def test_a_nearby_opponent_does_not_steal_the_ball_in_one_frame() -> None:
    players = [
        PlayerFix(1, (20.0, 34.0), "home"),
        PlayerFix(2, (40.0, 20.0), "home"),
        PlayerFix(3, (32.0, 40.0), "away"),
    ]
    tracker = PossessorTracker(max_distance=20.0, switch_ratio=1.35, switch_frames=3, commit_distance=1.0)
    assert tracker.update(players, (21.0, 34.0), ball_visible=True).track_id == 1
    # Away is clearly closer, but not on top of the ball, so the arrows stay.
    for _ in range(2):
        held = tracker.update(players, (30.0, 39.0), ball_visible=True)
        assert held.track_id == 1
        assert held.team == "home"
    stolen = tracker.update(players, (30.0, 39.0), ball_visible=True)
    assert stolen.track_id == 3
    assert stolen.team == "away"


def test_missed_ball_holds_then_expires() -> None:
    tracker = PossessorTracker(max_distance=8.0, hold_frames=3)
    assert tracker.update(_players(), (21.0, 34.0), ball_visible=True).track_id == 1
    for _ in range(3):
        held = tracker.update(_players(), None, ball_visible=False)
        assert held.track_id == 1
        assert held.held is True
        assert held.source == "held"
        assert held.xy == (20.0, 34.0)
    expired = tracker.update(_players(), None, ball_visible=False)
    assert expired.track_id is None
    assert expired.source == "none"


def test_velocity_match_beats_a_slightly_closer_bystander() -> None:
    tracker = PossessorTracker(
        max_distance=15.0,
        velocity_weight=0.8,
        switch_ratio=1.05,
        commit_distance=0.4,
        flight_speed=8.0,
        touch_rel_speed=1.2,
    )
    players = [
        PlayerFix(1, (10.0, 10.0), "home", velocity=(0.0, 0.0)),
        PlayerFix(2, (10.0, 13.0), "home", velocity=(5.0, 0.0)),
    ]
    # Player 1 is closer (1.4 vs 1.6) but the ball is moving with player 2.
    fix = tracker.update(players, (10.0, 11.4), ball_visible=True, ball_velocity=(5.0, 0.0))
    assert fix.track_id == 2
    assert fix.state == ON_BALL
    assert fix.team == "home"


def test_pass_in_flight_picks_a_teammate_intercept_not_the_nearest_body() -> None:
    tracker = PossessorTracker(
        max_distance=12.0,
        commit_distance=2.5,
        flight_speed=4.0,
        touch_rel_speed=1.5,
        receiver_speed=3.0,
        control_scale=2.0,
    )
    players = [
        PlayerFix(1, (0.0, 0.0), "home"),
        PlayerFix(2, (30.0, 0.0), "home"),
        PlayerFix(3, (14.0, 8.0), "away"),
    ]
    owned = tracker.update(players, (1.0, 0.0), ball_visible=True, ball_velocity=(0.0, 0.0))
    assert owned.track_id == 1
    assert owned.state == ON_BALL
    # The away player is the nearest body and inside the old nearest-player
    # radius, but the ball is clear of every foot and still moving quickly.
    flight = tracker.update(players, (14.0, 0.0), ball_visible=True, ball_velocity=(8.0, 0.0))
    assert flight.state == PASS_IN_FLIGHT
    assert flight.source == "pass"
    assert flight.predicted_id == 2
    assert flight.track_id == 2
    assert flight.team == "home"
    arrived = [
        PlayerFix(1, (0.0, 0.0), "home"),
        PlayerFix(2, (30.0, 0.0), "home", velocity=(0.3, 0.0)),
        PlayerFix(3, (14.0, 8.0), "away"),
    ]
    touch = tracker.update(arrived, (29.4, 0.0), ball_visible=True, ball_velocity=(0.3, 0.0))
    assert touch.track_id == 2
    assert touch.state == ON_BALL
    assert touch.source == "ball"
    assert touch.predicted_id is None


def test_fast_jitter_beside_the_possessor_does_not_launch_a_pass() -> None:
    tracker = PossessorTracker(
        max_distance=20.0,
        commit_distance=4.0,
        flight_speed=3.0,
        touch_rel_speed=1.0,
        velocity_weight=0.55,
    )
    players = [
        PlayerFix(1, (10.0, 10.0), "home"),
        PlayerFix(2, (30.0, 10.0), "home"),
    ]
    assert tracker.update(players, (10.4, 10.0), ball_visible=True, ball_velocity=(0.0, 0.0)).track_id == 1
    held = tracker.update(players, (12.0, 10.4), ball_visible=True, ball_velocity=(8.0, 0.0))
    assert held.track_id == 1
    assert held.state == ON_BALL
    assert held.team == "home"


def test_failed_intercept_keeps_the_passer_instead_of_a_near_opponent() -> None:
    tracker = PossessorTracker(
        max_distance=18.0,
        commit_distance=2.0,
        flight_speed=3.0,
        touch_rel_speed=1.0,
        receiver_speed=0.4,
        flight_horizon=4.0,
    )
    players = [
        PlayerFix(1, (0.0, 0.0), "home"),
        PlayerFix(2, (6.0, 40.0), "home"),
        PlayerFix(3, (14.0, 7.0), "away"),
    ]
    assert tracker.update(players, (0.5, 0.0), ball_visible=True).track_id == 1
    kept = tracker.update(players, (12.0, 0.0), ball_visible=True, ball_velocity=(8.0, 0.0))
    assert kept.track_id == 1
    assert kept.team == "home"
    assert kept.state != PASS_IN_FLIGHT


def test_fast_ball_with_no_teammate_on_the_ray_stays_loose() -> None:
    tracker = PossessorTracker(
        max_distance=8.0,
        commit_distance=1.5,
        flight_speed=3.0,
        touch_rel_speed=1.0,
        receiver_speed=1.0,
        flight_horizon=6.0,
    )
    players = [
        PlayerFix(1, (0.0, 0.0), "home"),
        PlayerFix(2, (4.0, 40.0), "home"),
        PlayerFix(3, (18.0, 6.0), "away"),
    ]
    tracker.update(players, (0.4, 0.0), ball_visible=True, ball_velocity=(0.0, 0.0))
    loose = tracker.update(players, (16.0, 0.0), ball_visible=True, ball_velocity=(7.0, 0.0))
    assert loose.state == LOOSE
    assert loose.track_id is None
    assert loose.source == "loose"


def test_two_players_on_the_ball_are_contested_until_the_touch_sticks() -> None:
    tracker = PossessorTracker(
        max_distance=20.0,
        switch_ratio=1.35,
        switch_frames=3,
        commit_distance=1.0,
        flight_speed=10.0,
    )
    players = [
        PlayerFix(1, (20.0, 34.0), "home"),
        PlayerFix(3, (21.2, 34.0), "away"),
    ]
    first = tracker.update(players, (20.4, 34.0), ball_visible=True, ball_velocity=(0.0, 0.0))
    assert first.track_id == 1
    assert first.state == CONTESTED
    nudged = tracker.update(players, (21.0, 34.0), ball_visible=True, ball_velocity=(0.2, 0.0))
    assert nudged.track_id == 1
    assert nudged.state == CONTESTED
    assert nudged.team == "home"


def test_visible_loose_ball_does_not_keep_the_old_possessor() -> None:
    tracker = PossessorTracker(max_distance=5.0, hold_frames=5)
    tracker.update(_players(), (20.5, 34.0), ball_visible=True)
    loose = tracker.update(_players(), (80.0, 10.0), ball_visible=True)
    assert loose.source == "loose"
    assert loose.track_id is None
    assert loose.state == LOOSE


def test_ball_smoother_coasts_and_rejects_a_jump() -> None:
    smoother = BallSmoother(hold_frames=2)
    seen = smoother.update((10.0, 10.0), visible=True, confidence=0.9)
    assert seen.held is False
    coast = smoother.update(None, visible=False)
    assert coast.held is True
    assert coast.xy == (10.0, 10.0)
    rejected = smoother.update((40.0, 10.0), visible=True, confidence=0.2, max_jump=5.0)
    assert rejected.held is True
    trusted = smoother.update((11.0, 10.0), visible=True, confidence=0.9, max_jump=5.0)
    assert trusted.held is False
    assert trusted.xy == (11.0, 10.0)


def test_ball_mark_hides_a_jump_and_a_detection_far_from_the_feet() -> None:
    mark = BallMark(max_jump=30.0, max_foot_gap=40.0, stable_needed=3)
    foot = (100.0, 200.0)
    assert mark.update((102.0, 198.0), visible=True, possessor_foot=foot) is None
    assert mark.update((104.0, 202.0), visible=True, possessor_foot=foot) is None
    shown = mark.update((103.0, 201.0), visible=True, possessor_foot=foot)
    assert shown is not None
    assert abs(shown[0] - 103.0) < 5.0
    frozen = mark.update(None, visible=False, possessor_foot=foot)
    assert frozen == shown
    for _ in range(mark.hold_gaps):
        frozen = mark.update(None, visible=False, possessor_foot=foot)
    assert frozen is None
    wild = BallMark(max_jump=30.0, max_foot_gap=40.0, stable_needed=2)
    wild.update((10.0, 10.0), visible=True, possessor_foot=(12.0, 10.0))
    assert wild.update((80.0, 10.0), visible=True, possessor_foot=(12.0, 10.0)) is None
    far = BallMark(max_jump=30.0, max_foot_gap=15.0, stable_needed=1)
    assert far.update((50.0, 10.0), visible=True, possessor_foot=(10.0, 10.0)) is None


def test_foot_trail_stays_near_the_foot_instead_of_snapping_around() -> None:
    trail = FootTrail(alpha=0.5)
    first = trail.smooth(1, (0.0, 0.0), snap_at=50.0)
    second = trail.smooth(1, (10.0, 0.0), snap_at=50.0)
    assert first == (0.0, 0.0)
    assert second == (5.0, 0.0)
    snapped = trail.smooth(1, (400.0, 0.0), snap_at=50.0)
    assert snapped == (400.0, 0.0)


def test_tracks_advance_between_detections() -> None:
    previous = [TrackState(7, (0.0, 0.0, 10.0, 20.0), role="player")]
    current = [TrackState(7, (10.0, 4.0, 20.0, 24.0), role="player")]
    updated = velocities_from_previous(previous, current, frame_delta=2)
    assert updated[0].vx == 5.0
    assert updated[0].vy == 2.0
    moved = predict_tracks(updated, steps=1)
    assert moved[0].bbox == (15.0, 6.0, 25.0, 26.0)
    assert moved[0].foot == (20.0, 26.0)
