"""Possessor identity stays put when the ball disappears or jitters."""

from demo.possessor import BallSmoother, PlayerFix, PossessorTracker
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


def test_visible_loose_ball_does_not_keep_the_old_possessor() -> None:
    tracker = PossessorTracker(max_distance=5.0, hold_frames=5)
    tracker.update(_players(), (20.5, 34.0), ball_visible=True)
    loose = tracker.update(_players(), (80.0, 10.0), ball_visible=True)
    assert loose.source == "loose"
    assert loose.track_id is None


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


def test_tracks_advance_between_detections() -> None:
    previous = [TrackState(7, (0.0, 0.0, 10.0, 20.0), role="player")]
    current = [TrackState(7, (10.0, 4.0, 20.0, 24.0), role="player")]
    updated = velocities_from_previous(previous, current, frame_delta=2)
    assert updated[0].vx == 5.0
    assert updated[0].vy == 2.0
    moved = predict_tracks(updated, steps=1)
    assert moved[0].bbox == (15.0, 6.0, 25.0, 26.0)
    assert moved[0].foot == (20.0, 26.0)
