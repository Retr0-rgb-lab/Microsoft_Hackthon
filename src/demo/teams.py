"""Jersey-colour teams. Two running means, then a slow pitch-side lock.

Goalkeepers are not used to update the colour means (their kit is a third
colour). Referees stay a separate role. Which colour defends the left goal
is a slow average of pitch x, so a single attack does not swap the labels.
``home`` is the side defending x = 0 and therefore attacking toward x = 105,
which is the frame ``extract_features`` already uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field


HOME = "home"
AWAY = "away"
UNKNOWN = "unknown"
REFEREE = "referee"


@dataclass
class _Cluster:
    color: tuple[float, float, float]
    count: int = 1
    ema_x: float | None = None


@dataclass
class TeamBook:
    """Online 2-means over torso colours, with a sticky cluster id per track."""

    min_separation: float = 28.0
    clusters: list[_Cluster] = field(default_factory=list)
    cluster_of: dict[int, int] = field(default_factory=dict)

    def update(
        self,
        samples: list[tuple[int, str, tuple[float, float, float] | None, float | None]],
    ) -> dict[int, str]:
        """Update from ``(track_id, role, rgb, pitch_x)`` rows."""
        for _track_id, role, color, pitch_x in samples:
            if role == "player" and color is not None:
                self._observe_color(color, pitch_x)
        assigned: dict[int, int | str] = {}
        for track_id, role, color, pitch_x in samples:
            if role == "referee":
                assigned[track_id] = REFEREE
                continue
            index = self._index_for(track_id, role, color, pitch_x)
            if index is None:
                assigned[track_id] = UNKNOWN
                continue
            self.cluster_of[track_id] = index
            assigned[track_id] = index
        self._refresh_ema(samples)
        resolved: dict[int, str] = {}
        for track_id, label in assigned.items():
            if isinstance(label, str):
                resolved[track_id] = label
            else:
                resolved[track_id] = _cluster_side(self.clusters, label)
        return resolved

    def _observe_color(
        self,
        color: tuple[float, float, float],
        pitch_x: float | None,
    ) -> None:
        if not self.clusters:
            self.clusters.append(_Cluster(color=color, ema_x=pitch_x))
            return
        if len(self.clusters) == 1 and _rgb_dist(color, self.clusters[0].color) >= self.min_separation:
            self.clusters.append(_Cluster(color=color, ema_x=pitch_x))
            return
        index = _nearest(color, self.clusters)
        cluster = self.clusters[index]
        weight = min(0.15, 1.0 / (cluster.count + 1))
        cluster.color = tuple(
            (1.0 - weight) * old + weight * new
            for old, new in zip(cluster.color, color, strict=True)
        )
        cluster.count += 1

    def _index_for(
        self,
        track_id: int,
        role: str,
        color: tuple[float, float, float] | None,
        pitch_x: float | None,
    ) -> int | None:
        if len(self.clusters) < 2:
            return None
        if role == "goalkeeper" and pitch_x is not None:
            return _index_for_side(pitch_x, self.clusters)
        if color is None:
            return self.cluster_of.get(track_id)
        nearest = _nearest(color, self.clusters)
        sticky = self.cluster_of.get(track_id)
        if sticky is None:
            return nearest
        if _rgb_dist(color, self.clusters[nearest].color) + 18.0 < _rgb_dist(
            color, self.clusters[sticky].color
        ):
            return nearest
        return sticky

    def _refresh_ema(
        self,
        samples: list[tuple[int, str, tuple[float, float, float] | None, float | None]],
    ) -> None:
        if len(self.clusters) < 1:
            return
        sums = [0.0 for _ in self.clusters]
        counts = [0 for _ in self.clusters]
        for track_id, role, color, pitch_x in samples:
            if role != "player" or color is None or pitch_x is None:
                continue
            index = self.cluster_of.get(track_id)
            if index is None:
                index = _nearest(color, self.clusters)
            sums[index] += pitch_x
            counts[index] += 1
        for index, cluster in enumerate(self.clusters):
            if counts[index] == 0:
                continue
            mean_x = sums[index] / counts[index]
            if cluster.ema_x is None:
                cluster.ema_x = mean_x
            else:
                cluster.ema_x = 0.98 * cluster.ema_x + 0.02 * mean_x


def _cluster_side(clusters: list[_Cluster], index: int) -> str:
    """The cluster with the smaller pitch-x average defends the left goal."""
    if len(clusters) < 2:
        return UNKNOWN
    xs = [cluster.ema_x for cluster in clusters]
    if any(value is None for value in xs):
        return HOME if index == 0 else AWAY
    left = 0 if xs[0] <= xs[1] else 1
    return HOME if index == left else AWAY


def _index_for_side(pitch_x: float, clusters: list[_Cluster]) -> int:
    xs = [cluster.ema_x for cluster in clusters]
    if any(value is None for value in xs):
        return 0 if pitch_x <= 52.5 else 1
    left = 0 if xs[0] <= xs[1] else 1
    right = 1 - left
    midpoint = (xs[0] + xs[1]) / 2.0
    return left if pitch_x <= midpoint else right


def _nearest(color: tuple[float, float, float], clusters: list[_Cluster]) -> int:
    return min(range(len(clusters)), key=lambda index: _rgb_dist(color, clusters[index].color))


def _rgb_dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum((left - right) ** 2 for left, right in zip(a, b, strict=True)) ** 0.5
