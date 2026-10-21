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

An optional home-jersey lock (``TeamBook(home_jersey=...)``, the
``--home-jersey`` flag, or ``INSIDE_THE_GAME_HOME_JERSEY``) pins cluster 0
to those RGB samples and skips the tail flip. Leave it unset and the online
2-means above is unchanged. Striped kits pass both samples
(``white-black``); sampling in HSV or Lab is left to the colour model.
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

# Same 0–255 RGB space as ``_jersey_colors``. ``white-black`` is the striped
# home kit on the Fail-frame broadcast (black/white stripes vs neon green).
HOME_JERSEY_ENV = "INSIDE_THE_GAME_HOME_JERSEY"
_JERSEY_PRESETS: dict[str, tuple[tuple[float, float, float], ...]] = {
    "white": ((245.0, 245.0, 245.0),),
    "black": ((16.0, 16.0, 16.0),),
    "white-black": ((245.0, 245.0, 245.0), (16.0, 16.0, 16.0)),
    "black-white": ((16.0, 16.0, 16.0), (245.0, 245.0, 245.0)),
}


class HomeJerseySpecError(ValueError):
    """``--home-jersey`` or ``INSIDE_THE_GAME_HOME_JERSEY`` could not be parsed."""


def parse_home_jersey(spec: str) -> tuple[tuple[float, float, float], ...]:
    """Parse one home-kit spec into RGB samples.

    Accepts a preset (``white-black``, ``black-white``, ``white``, ``black``),
    ``rgb:R,G,B``, a bare ``R,G,B``, or several of those joined with ``+``
    or ``;``.
    """
    text = spec.strip().lower()
    if not text:
        raise HomeJerseySpecError("home jersey spec is empty")
    if text in _JERSEY_PRESETS:
        return _JERSEY_PRESETS[text]
    pieces = [piece.strip() for piece in text.replace(";", "+").split("+")]
    if any(not piece for piece in pieces):
        raise HomeJerseySpecError(f"expected white-black or rgb:R,G,B, got {spec!r}")
    colors: list[tuple[float, float, float]] = []
    for piece in pieces:
        if piece in _JERSEY_PRESETS:
            colors.extend(_JERSEY_PRESETS[piece])
        else:
            colors.append(_parse_rgb_token(piece))
    return tuple(colors)


def parse_home_jersey_specs(specs: list[str]) -> tuple[tuple[float, float, float], ...]:
    """Parse repeated ``--home-jersey`` values into one sample list."""
    colors: list[tuple[float, float, float]] = []
    for spec in specs:
        colors.extend(parse_home_jersey(spec))
    return tuple(colors)


def _parse_rgb_token(token: str) -> tuple[float, float, float]:
    body = token[4:] if token.startswith("rgb:") else token
    parts = [part.strip() for part in body.split(",")]
    if len(parts) != 3:
        raise HomeJerseySpecError(f"expected white-black or rgb:R,G,B, got {token!r}")
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise HomeJerseySpecError(f"expected white-black or rgb:R,G,B, got {token!r}") from exc
    if any(value < 0.0 or value > 255.0 for value in values):
        raise HomeJerseySpecError(f"RGB channels must be within 0..255, got {token!r}")
    return values


def _as_rgb(sample: object) -> tuple[float, float, float]:
    if isinstance(sample, (tuple, list)) and len(sample) == 3 and not any(
        isinstance(channel, (tuple, list)) for channel in sample
    ):
        try:
            channels = (float(sample[0]), float(sample[1]), float(sample[2]))
        except (TypeError, ValueError) as exc:
            raise HomeJerseySpecError(f"home jersey sample must be an RGB triple, got {sample!r}") from exc
        if any(channel < 0.0 or channel > 255.0 for channel in channels):
            raise HomeJerseySpecError(f"RGB channels must be within 0..255, got {sample!r}")
        return channels
    raise HomeJerseySpecError(f"home jersey sample must be an RGB triple, got {sample!r}")


def _normalize_home_jersey(value: object) -> tuple[tuple[float, float, float], ...]:
    if not value:
        return ()
    if isinstance(value, (tuple, list)) and len(value) == 3 and all(
        isinstance(channel, (int, float)) for channel in value
    ):
        return (_as_rgb(value),)
    if isinstance(value, (tuple, list)):
        return tuple(_as_rgb(sample) for sample in value)
    raise HomeJerseySpecError(f"home jersey sample must be an RGB triple, got {value!r}")


@dataclass
class _Cluster:
    color: tuple[float, float, float]
    count: int = 1
    ema_x: float | None = None
    left_tail: float | None = None
    right_tail: float | None = None


@dataclass
class TeamBook:
    """Online 2-means over torso colours, with a sticky cluster id per track.

    ``home_jersey`` pins cluster 0 to those RGB samples (one colour, or both
    stripes of a split kit). Home's team id stays that cluster for the run.
    An empty lock keeps the defensive-tail assignment.
    """

    min_separation: float = 28.0
    home_jersey: tuple[tuple[float, float, float], ...] = ()
    clusters: list[_Cluster] = field(default_factory=list)
    cluster_of: dict[int, int] = field(default_factory=dict)
    pending: dict[int, tuple[int, int]] = field(default_factory=dict)
    home_index: int | None = None
    _flip_streak: int = 0

    def __post_init__(self) -> None:
        self.home_jersey = _normalize_home_jersey(self.home_jersey)
        if self.home_jersey:
            self._ensure_home_anchor()

    def update(
        self,
        samples: list[tuple[int, str, tuple[float, float, float] | None, float | None]],
    ) -> dict[int, str]:
        """Update from ``(track_id, role, rgb, pitch_x)`` rows."""
        if self.home_jersey:
            self._ensure_home_anchor()
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

    def _ensure_home_anchor(self) -> None:
        """Cluster 0 is the locked kit. Its colour does not follow the mean."""
        if not self.home_jersey:
            return
        if not self.clusters:
            self.clusters.append(_Cluster(color=self.home_jersey[0]))
        self.home_index = 0

    def _dist_to_cluster(self, color: tuple[float, float, float], index: int) -> float:
        if index == 0 and self.home_jersey:
            return min(_rgb_dist(color, sample) for sample in self.home_jersey)
        return _rgb_dist(color, self.clusters[index].color)

    def _nearest_index(self, color: tuple[float, float, float]) -> int:
        if self.home_jersey:
            return min(
                range(len(self.clusters)),
                key=lambda index: self._dist_to_cluster(color, index),
            )
        return _nearest(color, self.clusters)

    def _observe_color(
        self,
        color: tuple[float, float, float],
        pitch_x: float | None,
    ) -> None:
        if not self.clusters:
            self.clusters.append(_Cluster(color=color, ema_x=pitch_x))
            return
        if len(self.clusters) == 1 and self._dist_to_cluster(color, 0) >= self.min_separation:
            self.clusters.append(_Cluster(color=color, ema_x=pitch_x))
            return
        index = self._nearest_index(color)
        # The locked home samples stay put. A white stripe must not drag the
        # black anchor toward grey, and the opponent mean must not absorb it.
        if self.home_jersey and index == 0:
            return
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
        nearest = self._nearest_index(color)
        sticky = self.cluster_of.get(track_id)
        if sticky is None or sticky == nearest:
            self.pending.pop(track_id, None)
            return nearest
        if sticky >= len(self.clusters):
            return nearest
        nearer = self._dist_to_cluster(color, nearest) + _SWITCH_MARGIN < self._dist_to_cluster(
            color, sticky
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
            if index is None and color is not None and self.clusters:
                index = self._nearest_index(color)
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
        if self.home_jersey:
            if self.clusters:
                self.home_index = 0
            return
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
