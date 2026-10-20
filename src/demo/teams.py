"""Jersey-colour teams, with the defensive tail locking the goals.

Outfield players are two running colour means. A track keeps its cluster
until a new colour is clearly closer for several observations, so one muddy
frame cannot swap friend and foe.

Which cluster is ``home`` is not the mean of every shirt. The mean slides
into the opponent half during an attack and flips the labels. The lock uses
the left tail instead: the deepest outfield players, the ones who stay near
their own goal. ``home`` defends x = 0 and attacks toward x = 105, which is
the frame ``extract_features`` already uses. A goalkeeper is assigned from
the goal they are standing in, not from the outfield average, so the
opponent keeper is never labelled as a teammate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from inside_the_game.ingest.events import PITCH_LENGTH


HOME = "home"
AWAY = "away"
UNKNOWN = "unknown"
REFEREE = "referee"

_SWITCH_MARGIN = 28.0
_SWITCH_FRAMES = 6
_FLIP_FRAMES = 10
_FLIP_GAP_M = 6.0


@dataclass
class _Cluster:
    color: tuple[float, float, float]
    count: int = 1
    ema_x: float | None = None
    left_tail: float | None = None
    right_tail: float | None = None


@dataclass
class TeamBook:
    """Online 2-means over torso colours, with a sticky cluster id per track."""

    min_separation: float = 28.0
    clusters: list[_Cluster] = field(default_factory=list)
    cluster_of: dict[int, int] = field(default_factory=dict)
    pending: dict[int, tuple[int, int]] = field(default_factory=dict)
    home_index: int | None = None
    _flip_streak: int = 0

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
            if role == "goalkeeper":
                continue
            index = self._index_for(track_id, role, color, pitch_x)
            if index is None:
                assigned[track_id] = UNKNOWN
                continue
            self.cluster_of[track_id] = index
            assigned[track_id] = index
        self._refresh_tails(samples)
        self._refresh_side()
        for track_id, role, _color, pitch_x in samples:
            if role != "goalkeeper":
                continue
            if pitch_x is None or len(self.clusters) < 2:
                assigned[track_id] = UNKNOWN
                continue
            index = self._goalkeeper_index(pitch_x)
            self.cluster_of[track_id] = index
            assigned[track_id] = index
        resolved: dict[int, str] = {}
        for track_id, label in assigned.items():
            if isinstance(label, str):
                resolved[track_id] = label
            else:
                resolved[track_id] = self.label_for(label)
        return resolved

    def label_for(self, index: int | None) -> str:
        """Home/away for a cluster index, using the locked defensive side."""
        if index is None or len(self.clusters) < 2:
            return UNKNOWN
        if self.home_index is None:
            return _cluster_side(self.clusters, index)
        return HOME if index == self.home_index else AWAY

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
            return self._goalkeeper_index(pitch_x)
        if color is None:
            return self.cluster_of.get(track_id)
        nearest = _nearest(color, self.clusters)
        sticky = self.cluster_of.get(track_id)
        if sticky is None or sticky == nearest:
            self.pending.pop(track_id, None)
            return nearest
        if sticky >= len(self.clusters):
            return nearest
        nearer = _rgb_dist(color, self.clusters[nearest].color) + _SWITCH_MARGIN < _rgb_dist(
            color, self.clusters[sticky].color
        )
        if not nearer:
            self.pending.pop(track_id, None)
            return sticky
        previous = self.pending.get(track_id)
        count = previous[1] + 1 if previous is not None and previous[0] == nearest else 1
        if count >= _SWITCH_FRAMES:
            self.pending.pop(track_id, None)
            return nearest
        self.pending[track_id] = (nearest, count)
        return sticky

    def _goalkeeper_index(self, pitch_x: float) -> int:
        """Keeper in the left goal is home's. The right goal is away's."""
        home = self.home_index
        if home is None or len(self.clusters) < 2:
            return _index_for_side(pitch_x, self.clusters)
        if pitch_x <= PITCH_LENGTH / 2.0:
            return home
        return 1 - home

    def _refresh_tails(
        self,
        samples: list[tuple[int, str, tuple[float, float, float] | None, float | None]],
    ) -> None:
        if not self.clusters:
            return
        grouped: dict[int, list[float]] = {index: [] for index in range(len(self.clusters))}
        for track_id, role, color, pitch_x in samples:
            if role != "player" or pitch_x is None:
                continue
            index = self.cluster_of.get(track_id)
            if index is None and color is not None:
                index = _nearest(color, self.clusters)
            if index is None or index not in grouped:
                continue
            grouped[index].append(pitch_x)
        for index, cluster in enumerate(self.clusters):
            xs = grouped[index]
            if not xs:
                continue
            mean_x = sum(xs) / len(xs)
            if cluster.ema_x is None:
                cluster.ema_x = mean_x
            else:
                cluster.ema_x = 0.98 * cluster.ema_x + 0.02 * mean_x
            ordered = sorted(xs)
            tail_n = max(1, (len(ordered) + 2) // 5)
            left = sum(ordered[:tail_n]) / tail_n
            right = sum(ordered[-tail_n:]) / tail_n
            cluster.left_tail = left if cluster.left_tail is None else 0.85 * cluster.left_tail + 0.15 * left
            cluster.right_tail = right if cluster.right_tail is None else 0.85 * cluster.right_tail + 0.15 * right

    def _refresh_side(self) -> None:
        if len(self.clusters) < 2:
            return
        anchors = [
            cluster.left_tail if cluster.left_tail is not None else cluster.ema_x
            for cluster in self.clusters
        ]
        if any(value is None for value in anchors):
            return
        proposed = 0 if anchors[0] <= anchors[1] else 1
        if self.home_index is None:
            self.home_index = proposed
            self._flip_streak = 0
            return
        if proposed == self.home_index:
            self._flip_streak = 0
            return
        if abs(anchors[0] - anchors[1]) < _FLIP_GAP_M:
            return
        self._flip_streak += 1
        if self._flip_streak >= _FLIP_FRAMES:
            self.home_index = proposed
            self._flip_streak = 0


def _cluster_side(clusters: list[_Cluster], index: int) -> str:
    """The cluster with the deeper left-side tail defends the left goal."""
    if len(clusters) < 2:
        return UNKNOWN
    xs = [
        cluster.left_tail if cluster.left_tail is not None else cluster.ema_x
        for cluster in clusters
    ]
    if any(value is None for value in xs):
        return HOME if index == 0 else AWAY
    left = 0 if xs[0] <= xs[1] else 1
    return HOME if index == left else AWAY


def _index_for_side(pitch_x: float, clusters: list[_Cluster]) -> int:
    home = 0
    anchors = [
        cluster.left_tail if cluster.left_tail is not None else cluster.ema_x
        for cluster in clusters
    ]
    if len(clusters) >= 2 and all(value is not None for value in anchors):
        home = 0 if anchors[0] <= anchors[1] else 1
    elif len(clusters) >= 2:
        xs = [cluster.ema_x for cluster in clusters]
        if all(value is not None for value in xs):
            home = 0 if xs[0] <= xs[1] else 1
        else:
            home = 0 if pitch_x <= PITCH_LENGTH / 2.0 else 1
    if pitch_x <= PITCH_LENGTH / 2.0:
        return home
    return 1 - home if len(clusters) >= 2 else home


def _nearest(color: tuple[float, float, float], clusters: list[_Cluster]) -> int:
    return min(range(len(clusters)), key=lambda index: _rgb_dist(color, clusters[index].color))


def _rgb_dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum((left - right) ** 2 for left, right in zip(a, b, strict=True)) ** 0.5
