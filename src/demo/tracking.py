"""Constant-velocity fill between detector frames.

ByteTrack (via Ultralytics) assigns ids on detection frames. Frames the
detector skips advance each box by the per-frame velocity measured across
the last stride.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackState:
    track_id: int
    bbox: tuple[float, float, float, float]
    vx: float = 0.0
    vy: float = 0.0
    role: str = "player"
    confidence: float = 0.0
    team: str = "unknown"

    @property
    def foot(self) -> tuple[float, float]:
        x1, _y1, x2, y2 = self.bbox
        return ((x1 + x2) * 0.5, y2)


def predict_tracks(tracks: list[TrackState], steps: int) -> list[TrackState]:
    """Advance boxes by ``steps`` frames of their stored velocity."""
    if steps <= 0:
        return list(tracks)
    moved: list[TrackState] = []
    for track in tracks:
        dx = track.vx * steps
        dy = track.vy * steps
        x1, y1, x2, y2 = track.bbox
        moved.append(
            TrackState(
                track_id=track.track_id,
                bbox=(x1 + dx, y1 + dy, x2 + dx, y2 + dy),
                vx=track.vx,
                vy=track.vy,
                role=track.role,
                confidence=track.confidence,
                team=track.team,
            )
        )
    return moved


def velocities_from_previous(
    previous: list[TrackState],
    current: list[TrackState],
    frame_delta: int,
) -> list[TrackState]:
    """Replace velocity using the centre motion since the previous detection."""
    delta = max(1, frame_delta)
    prior = {track.track_id: track for track in previous}
    updated: list[TrackState] = []
    for track in current:
        before = prior.get(track.track_id)
        if before is None:
            updated.append(track)
            continue
        old = _center(before.bbox)
        new = _center(track.bbox)
        updated.append(
            TrackState(
                track_id=track.track_id,
                bbox=track.bbox,
                vx=(new[0] - old[0]) / delta,
                vy=(new[1] - old[1]) / delta,
                role=track.role,
                confidence=track.confidence,
                team=track.team,
            )
        )
    return updated


def _center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) * 0.5, (y1 + y2) * 0.5)
