"""Homography failure drops the overlay to image coordinates."""

import pytest

from demo.geometry import (
    apply_homography,
    assess_homography,
    invert_homography,
    is_detection_frame,
    pitch_vertices_m,
    project_segment,
    resolve_plane,
    scene_cut,
)
from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH


def test_pitch_template_matches_the_training_frame() -> None:
    vertices = pitch_vertices_m()
    assert len(vertices) == 32
    assert vertices[0] == (0.0, 0.0)
    assert vertices[5] == pytest.approx((0.0, PITCH_WIDTH))
    assert vertices[24] == pytest.approx((PITCH_LENGTH, 0.0))
    assert vertices[29] == pytest.approx((PITCH_LENGTH, PITCH_WIDTH))
    # Left penalty spot stays on the halfway line in y and inside the box in x.
    assert vertices[8][1] == pytest.approx(PITCH_WIDTH / 2.0)
    assert 0.0 < vertices[8][0] < 20.0


def test_too_few_points_or_a_bad_fit_is_rejected() -> None:
    assert assess_homography(3, 3, 1.0) == (False, "too_few_keypoints")
    assert assess_homography(8, 3, 1.0) == (False, "too_few_keypoints")
    assert assess_homography(8, 6, 40.0) == (False, "reprojection_error")
    assert assess_homography(8, 4, 12.0) == (False, "weak_fit")
    assert assess_homography(10, 8, 6.0) == (True, "ok")


def test_failed_homography_falls_back_after_a_short_hold() -> None:
    assert resolve_plane(True, 0, False) == "current"
    assert resolve_plane(False, 4, False, max_hold=12) == "held"
    assert resolve_plane(False, 20, False, max_hold=12) == "image"
    assert resolve_plane(False, 2, True, max_hold=12) == "image"
    assert scene_cut(31.0) is True
    assert scene_cut(8.0) is False


def test_projection_roundtrip_and_exploding_segment() -> None:
    # Image x = 10 * pitch x, image y = 5 * pitch y.
    matrix = (
        (10.0, 0.0, 0.0),
        (0.0, 5.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    assert apply_homography(matrix, 4.0, 6.0) == pytest.approx((40.0, 30.0))
    inverse = invert_homography(matrix)
    assert inverse is not None
    assert apply_homography(inverse, 40.0, 30.0) == pytest.approx((4.0, 6.0))
    segment = project_segment(matrix, (0.0, 0.0), (2.0, 0.0), samples=3)
    assert segment is not None
    assert segment[0] == pytest.approx((0.0, 0.0))
    assert segment[1] == pytest.approx((10.0, 0.0))
    assert segment[2] == pytest.approx((20.0, 0.0))
    # A homography that sends the segment through infinity is dropped.
    singular = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (1.0, 0.0, -1.0),
    )
    assert project_segment(singular, (0.0, 0.0), (2.0, 0.0), samples=5) is None


def test_stride_selects_every_nth_frame() -> None:
    assert [is_detection_frame(index, 2) for index in range(6)] == [
        True,
        False,
        True,
        False,
        True,
        False,
    ]
    with pytest.raises(ValueError):
        is_detection_frame(0, 0)
