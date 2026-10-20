"""Draw pitch-plane arrows, a probability bar, and an optional minimap."""

from __future__ import annotations

from dataclasses import dataclass, field

from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH
from inside_the_game.labels import ACTION_LABELS


@dataclass(frozen=True)
class ArrowDraw:
    kind: str
    points: tuple[tuple[float, float], ...]
    primary: bool
    label: str


@dataclass(frozen=True)
class PlayerDraw:
    track_id: int
    bbox: tuple[float, float, float, float]
    foot: tuple[float, float]
    team: str
    possessor: bool


@dataclass(frozen=True)
class MinimapPlayer:
    xy: tuple[float, float]
    team: str
    possessor: bool


@dataclass(frozen=True)
class MinimapArrow:
    kind: str
    origin: tuple[float, float]
    target: tuple[float, float]
    primary: bool


@dataclass
class OverlayState:
    players: list[PlayerDraw] = field(default_factory=list)
    ball: tuple[float, float] | None = None
    arrows: list[ArrowDraw] = field(default_factory=list)
    wireframe: list[tuple[tuple[float, float], ...]] = field(default_factory=list)
    minimap_players: list[MinimapPlayer] = field(default_factory=list)
    minimap_ball: tuple[float, float] | None = None
    minimap_arrows: list[MinimapArrow] = field(default_factory=list)
    probabilities: dict[str, float] | None = None
    recommended: str | None = None
    badges: list[str] = field(default_factory=list)
    note: str = ""
    show_minimap: bool = True


_TEAM_BGR = {
    "home": (235, 150, 40),
    "away": (50, 70, 230),
    "referee": (210, 210, 80),
    "unknown": (170, 170, 170),
}
_KIND_BGR = {
    "pass": (90, 210, 90),
    "dribble": (255, 170, 40),
    "shoot": (50, 60, 235),
    "hold": (230, 230, 230),
}
_PRIMARY_BGR = (40, 240, 255)


def draw_overlay(frame, state: OverlayState):
    """Return a BGR frame with the tactical overlay painted on."""
    import cv2

    canvas = frame.copy()
    if state.wireframe:
        _blend_polylines(canvas, state.wireframe, (210, 230, 210), 1, 0.45)
    secondary = [arrow for arrow in state.arrows if not arrow.primary and len(arrow.points) >= 2]
    primary = [arrow for arrow in state.arrows if arrow.primary and len(arrow.points) >= 2]
    if secondary:
        _blend_arrows(canvas, secondary, primary=False, alpha=0.38)
    if primary:
        _blend_arrows(canvas, primary, primary=True, alpha=0.95)
    _players_and_ball(canvas, state)
    if state.show_minimap:
        _minimap(canvas, state)
    _panel(canvas, state)
    return canvas


def _blend_polylines(canvas, polylines, color, thickness, alpha) -> None:
    import cv2
    import numpy as np

    overlay = canvas.copy()
    for points in polylines:
        chain = _chain(points)
        if chain is None:
            continue
        cv2.polylines(overlay, [chain], False, color, thickness, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, canvas, 1.0 - alpha, 0, canvas)


def _blend_arrows(canvas, arrows: list[ArrowDraw], *, primary: bool, alpha: float) -> None:
    import cv2

    overlay = canvas.copy()
    for arrow in arrows:
        color = _PRIMARY_BGR if primary else _KIND_BGR.get(arrow.kind, (255, 255, 255))
        thickness = 4 if primary else 2
        chain = _chain(arrow.points)
        if chain is None:
            continue
        cv2.polylines(overlay, [chain], False, color, thickness, cv2.LINE_AA)
        _head(overlay, arrow.points, color, 18 if primary else 12, thickness)
        if primary or arrow.kind == "shoot":
            end = arrow.points[-1]
            label_x, label_y = _label_anchor(end, overlay.shape[1], overlay.shape[0])
            cv2.putText(
                overlay,
                arrow.label,
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5 if primary else 0.4,
                color,
                1,
                cv2.LINE_AA,
            )
        if arrow.kind == "hold":
            foot = arrow.points[0]
            radius = 16 if primary else 10
            cv2.circle(overlay, (int(foot[0]), int(foot[1])), radius, color, 2, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, canvas, 1.0 - alpha, 0, canvas)


def _label_anchor(end: tuple[float, float], width: int, height: int) -> tuple[int, int]:
    """Keep the action name on the picture when the tip sits on the border."""
    x = int(end[0]) + 8
    y = int(end[1]) - 8
    if x > width - 72:
        x = int(end[0]) - 64
    if x < 8:
        x = 8
    if y < 18:
        y = int(end[1]) + 18
    if y > height - 8:
        y = height - 8
    return x, y


def _head(image, points, color, size, thickness) -> None:
    import cv2

    end = _ipoint(points[-1])
    anchor = _ipoint(points[0])
    if end is None or anchor is None:
        return
    for point in reversed(points[:-1]):
        candidate = _ipoint(point)
        if candidate is None:
            continue
        if _hypot(candidate[0] - end[0], candidate[1] - end[1]) >= size * 1.4:
            anchor = candidate
            break
    cv2.arrowedLine(image, anchor, end, color, thickness, cv2.LINE_AA, tipLength=0.45)


def _players_and_ball(canvas, state: OverlayState) -> None:
    import cv2

    for player in state.players:
        color = _TEAM_BGR.get(player.team, _TEAM_BGR["unknown"])
        box = tuple(_ipoint((player.bbox[i], player.bbox[i + 1])) for i in (0, 2))
        foot = _ipoint(player.foot)
        if box[0] is None or box[1] is None or foot is None:
            continue
        thickness = 2 if player.possessor else 1
        cv2.rectangle(canvas, box[0], box[1], color, thickness, cv2.LINE_AA)
        cv2.circle(canvas, foot, 4, color, -1, cv2.LINE_AA)
        if player.possessor:
            cv2.circle(canvas, foot, 14, _PRIMARY_BGR, 2, cv2.LINE_AA)
    if state.ball is not None:
        ball = _ipoint(state.ball)
        if ball is not None:
            # Thin ring. A filled disc on a noisy box reads as a floating bug.
            cv2.circle(canvas, ball, 8, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.circle(canvas, ball, 2, (255, 255, 255), -1, cv2.LINE_AA)


def _panel(canvas, state: OverlayState) -> None:
    import cv2

    height, width = canvas.shape[:2]
    panel_w = min(320, width - 24)
    rows = 4 if state.probabilities else 0
    panel_h = 36 + rows * 22 + 22 + 18 * max(1, len(state.badges))
    x0, y0 = 16, 16
    overlay = canvas.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), (18, 22, 28), -1)
    cv2.addWeighted(overlay, 0.72, canvas, 0.28, 0, canvas)
    cursor = y0 + 22
    cv2.putText(
        canvas,
        "on-ball options",
        (x0 + 10, cursor),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (240, 240, 240),
        1,
        cv2.LINE_AA,
    )
    cursor += 8
    if state.probabilities:
        for label in ACTION_LABELS:
            probability = state.probabilities[label]
            cursor += 22
            chosen = label == state.recommended
            color = _PRIMARY_BGR if chosen else (200, 200, 200)
            cv2.putText(
                canvas,
                f"{label:<7} {probability:0.0%}",
                (x0 + 10, cursor),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )
            bar_x = x0 + 150
            bar_w = panel_w - 166
            cv2.rectangle(canvas, (bar_x, cursor - 10), (bar_x + bar_w, cursor), (70, 70, 70), -1)
            filled = int(bar_w * max(0.0, min(1.0, probability)))
            cv2.rectangle(canvas, (bar_x, cursor - 10), (bar_x + filled, cursor), color, -1)
    for badge in state.badges:
        cursor += 18
        cv2.putText(
            canvas,
            badge,
            (x0 + 10, cursor),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (180, 220, 255),
            1,
            cv2.LINE_AA,
        )
    if state.note:
        text = state.note[:110]
        bar_y = height - 36
        shade = canvas.copy()
        cv2.rectangle(shade, (16, bar_y - 18), (min(width - 16, 16 + 8 * len(text)), height - 12), (18, 22, 28), -1)
        cv2.addWeighted(shade, 0.65, canvas, 0.35, 0, canvas)
        cv2.putText(
            canvas,
            text,
            (24, height - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (235, 235, 235),
            1,
            cv2.LINE_AA,
        )


def _minimap(canvas, state: OverlayState) -> None:
    import cv2

    height, width = canvas.shape[:2]
    map_w, map_h = 210, 136
    x0 = width - map_w - 16
    y0 = height - map_h - 48
    overlay = canvas.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + map_w, y0 + map_h), (16, 40, 24), -1)
    cv2.addWeighted(overlay, 0.78, canvas, 0.22, 0, canvas)
    cv2.rectangle(canvas, (x0, y0), (x0 + map_w, y0 + map_h), (180, 200, 180), 1, cv2.LINE_AA)

    def px(point: tuple[float, float]) -> tuple[int, int]:
        return (
            int(x0 + point[0] / PITCH_LENGTH * map_w),
            int(y0 + point[1] / PITCH_WIDTH * map_h),
        )

    halfway = px((PITCH_LENGTH / 2.0, 0.0))[0]
    cv2.line(canvas, (halfway, y0), (halfway, y0 + map_h), (160, 180, 160), 1, cv2.LINE_AA)
    for arrow in state.minimap_arrows:
        color = _PRIMARY_BGR if arrow.primary else _KIND_BGR.get(arrow.kind, (220, 220, 220))
        thickness = 2 if arrow.primary else 1
        if arrow.kind == "hold":
            cv2.circle(canvas, px(arrow.origin), 4, color, 1, cv2.LINE_AA)
            continue
        cv2.arrowedLine(canvas, px(arrow.origin), px(arrow.target), color, thickness, cv2.LINE_AA, tipLength=0.25)
    for player in state.minimap_players:
        color = _TEAM_BGR.get(player.team, _TEAM_BGR["unknown"])
        radius = 4 if player.possessor else 3
        cv2.circle(canvas, px(player.xy), radius, color, -1, cv2.LINE_AA)
    if state.minimap_ball is not None:
        cv2.circle(canvas, px(state.minimap_ball), 3, (255, 255, 255), -1, cv2.LINE_AA)


def _hypot(dx: float, dy: float) -> float:
    return (dx * dx + dy * dy) ** 0.5


def _ipoint(point) -> tuple[int, int] | None:
    """Pixel coordinate OpenCV 5 will accept. Drops NaN and runaway projections."""
    try:
        x = float(point[0])
        y = float(point[1])
    except (TypeError, ValueError, IndexError):
        return None
    if x != x or y != y or abs(x) > 20000 or abs(y) > 20000:
        return None
    return (int(round(x)), int(round(y)))


def _chain(points):
    import numpy as np

    converted = [_ipoint(point) for point in points]
    if any(point is None for point in converted) or len(converted) < 2:
        return None
    return np.array(converted, dtype=np.int32)
