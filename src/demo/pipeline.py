"""Video to overlay: detect every ``stride`` frames, track the frames between."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from demo.geometry import (
    PITCH_EDGES,
    apply_homography,
    assess_homography,
    centre_circle_m,
    clip_polyline,
    invert_homography,
    is_detection_frame,
    pitch_vertices_m,
    project_segment,
    resolve_plane,
    scene_cut,
)
from demo.options import (
    OptionPlayer,
    attacking_positive_for,
    build_options,
    compose_drawn,
    eligible_receivers,
)
from demo.possessor import BallMark, BallSmoother, FootTrail, PlayerFix, PossessorTracker
from demo.render import ArrowDraw, MinimapArrow, MinimapPlayer, OverlayState, PlayerDraw
from demo.stabilize import OverlayMemory
from demo.teams import TeamBook, summarize_jersey
from demo.tracking import TrackState, predict_tracks, velocities_from_previous
from inside_the_game.features.extract import FEATURE_NAMES
from inside_the_game.features.from_cv import (
    features_from_cv,
    image_xy_to_pitch_meters,
    pressure_from_distances,
)
from inside_the_game.ingest.events import PITCH_LENGTH, PITCH_WIDTH, zone_name
from inside_the_game.system1.policy import SoftmaxActionPolicy


_ROLE = {
    "player": "player",
    "goalkeeper": "goalkeeper",
    "referee": "referee",
    "ball": "ball",
}


@dataclass
class DemoConfig:
    input_path: Path
    output_path: Path
    stride: int = 2
    seconds: float | None = None
    minute: int = 45
    score_home: int = 0
    score_away: int = 0
    # Empty keeps the online 2-means defensive tail. Samples pin cluster 0 as home.
    home_jersey: tuple[tuple[float, float, float], ...] = ()
    device: str = "cpu"
    imgsz: int = 640
    ball_imgsz: int = 960
    pitch_imgsz: int = 640
    pitch_every: int = 15
    hold_frames: int = 18
    homography_hold: int = 30
    minimap: bool = True
    models_dir: Path = Path("data/models")
    screenshot_dir: Path | None = None
    screenshot_times: tuple[float, ...] = ()
    keypoint_conf: float = 0.5
    player_conf: float = 0.25
    ball_conf: float = 0.20


@dataclass
class RunStats:
    frames: int = 0
    source_fps: float = 0.0
    seconds: float = 0.0
    wall_seconds: float = 0.0
    output_fps: float = 0.0
    detect_frames: int = 0
    player_ms: float = 0.0
    ball_ms: float = 0.0
    pitch_ms: float = 0.0
    pitch_inferences: int = 0
    ball_inferences: int = 0
    homography_current: int = 0
    homography_held: int = 0
    image_fallback: int = 0
    possessor_frames: int = 0
    possessor_held: int = 0
    scene_cuts: int = 0
    feature_names: tuple[str, ...] = FEATURE_NAMES
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        payload = dict(self.__dict__)
        payload["feature_names"] = list(self.feature_names)
        return payload


def run_clip(config: DemoConfig) -> RunStats:
    """Read ``config.input_path`` and write an overlaid mp4."""
    import cv2
    import numpy as np
    import torch
    from ultralytics import YOLO

    from demo.weights import ensure_weights

    if config.stride < 1:
        raise ValueError("stride must be >= 1")
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    cv2.setNumThreads(max(1, os.cpu_count() or 1))
    weights = ensure_weights(config.models_dir)
    player_model = YOLO(str(weights["player"]))
    ball_model = YOLO(str(weights["ball"]))
    pitch_model = YOLO(str(weights["pitch"]))
    policy = SoftmaxActionPolicy()
    vertices = pitch_vertices_m()

    capture = cv2.VideoCapture(str(config.input_path))
    if not capture.isOpened():
        raise FileNotFoundError(f"could not open video: {config.input_path}")
    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    max_frames = None if config.seconds is None else max(1, int(round(config.seconds * source_fps)))
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    if config.screenshot_dir is not None:
        config.screenshot_dir.mkdir(parents=True, exist_ok=True)

    writer = _FfmpegWriter(config.output_path, width, height, source_fps)
    stats = RunStats(source_fps=source_fps)
    ball_smoother = BallSmoother(hold_frames=config.hold_frames)
    # Possession is decided in the image, where the ball and the feet actually are.
    # A ground-plane projection of the ball centre is a poor contact point.
    possessor_tracker = _possessor_tracker(config.hold_frames, width, height)
    teams = _team_book(config)
    jersey_memory: dict[int, tuple[float, float, float]] = {}
    memory = OverlayMemory()
    foot_trail = FootTrail()
    # The drawn ball is a light mark. It is not the possession smoother: that
    # one still holds through misses and rejects a low-confidence jump.
    ball_mark = BallMark(max_jump=0.04 * width, max_foot_gap=0.08 * height)
    last_detect: list[TrackState] = []
    last_detect_idx = 0
    plane_matrix: tuple[tuple[float, float, float], ...] | None = None
    last_good_idx = -1
    previous_tiny = None
    started = time.perf_counter()
    frame_idx = 0
    try:
        while True:
            if max_frames is not None and frame_idx >= max_frames:
                break
            ok, frame = capture.read()
            if not ok:
                break
            tiny = _tiny_gray(frame)
            cut = False
            if previous_tiny is not None:
                diff = float(np.mean(np.abs(tiny - previous_tiny)))
                cut = scene_cut(diff)
                if cut:
                    stats.scene_cuts += 1
                    plane_matrix = None
                    last_good_idx = -1
                    _reset_tracker(player_model)
                    last_detect = []
                    memory.reset()
                    foot_trail.retain(set())
                    ball_mark.reset()
                    ball_smoother = BallSmoother(hold_frames=config.hold_frames)
                    possessor_tracker = _possessor_tracker(config.hold_frames, width, height)
                    teams = _team_book(config)
                    jersey_memory = {}
            previous_tiny = tiny

            detect = is_detection_frame(frame_idx, config.stride)
            raw_ball: tuple[tuple[float, float], float] | None = None
            if detect:
                t0 = time.perf_counter()
                player_result = player_model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    imgsz=config.imgsz,
                    device=config.device,
                    verbose=False,
                    conf=config.player_conf,
                )[0]
                stats.player_ms += (time.perf_counter() - t0) * 1000.0
                stats.detect_frames += 1
                people, raw_ball = _parse_people(player_result)
                people = velocities_from_previous(last_detect, people, max(1, frame_idx - last_detect_idx))
                last_detect = people
                last_detect_idx = frame_idx
                if raw_ball is None or raw_ball[1] < 0.35:
                    t1 = time.perf_counter()
                    ball_result = ball_model.predict(
                        frame,
                        imgsz=config.ball_imgsz,
                        device=config.device,
                        verbose=False,
                        conf=config.ball_conf,
                    )[0]
                    stats.ball_ms += (time.perf_counter() - t1) * 1000.0
                    stats.ball_inferences += 1
                    specialist = _best_ball(ball_result)
                    if specialist is not None and (raw_ball is None or specialist[1] > raw_ball[1]):
                        raw_ball = specialist
            display_tracks = predict_tracks(last_detect, frame_idx - last_detect_idx)

            run_pitch = frame_idx % config.pitch_every == 0
            fresh_matrix = None
            fresh_ok = False
            if run_pitch:
                t2 = time.perf_counter()
                pitch_result = pitch_model.predict(
                    frame,
                    imgsz=config.pitch_imgsz,
                    device=config.device,
                    verbose=False,
                    conf=0.25,
                )[0]
                stats.pitch_ms += (time.perf_counter() - t2) * 1000.0
                stats.pitch_inferences += 1
                pairs = _keypoint_pairs(pitch_result, config.keypoint_conf)
                fresh_ok, fresh_matrix = _fit_homography(pairs, vertices)
            if fresh_ok and fresh_matrix is not None:
                plane_matrix = fresh_matrix
                last_good_idx = frame_idx
            age = frame_idx - last_good_idx if last_good_idx >= 0 else config.homography_hold + 1
            # Frames between pitch attempts are not failures: keep the plane as current.
            current_ok = bool(fresh_ok or (not run_pitch and plane_matrix is not None))
            mode = resolve_plane(
                current_ok,
                age,
                bool(cut and not fresh_ok),
                max_hold=config.homography_hold,
            )
            active_matrix = None if mode == "image" else plane_matrix
            if mode == "current":
                stats.homography_current += 1
            elif mode == "held":
                stats.homography_held += 1
            else:
                stats.image_fallback += 1

            image_to_pitch = invert_homography(active_matrix) if active_matrix is not None else None
            colors = _jersey_colors(frame, display_tracks) if detect else {}
            samples = []
            pitch_feet: dict[int, tuple[float, float]] = {}
            smooth_feet: dict[int, tuple[float, float]] = {}
            live_ids: set[int] = set()
            for track in display_tracks:
                live_ids.add(track.track_id)
                smooth_feet[track.track_id] = foot_trail.smooth(
                    track.track_id,
                    track.foot,
                    snap_at=0.22 * height,
                )
                raw_pitch = _foot_pitch(track.foot, image_to_pitch) if image_to_pitch is not None else None
                smooth_pitch = (
                    _foot_pitch(smooth_feet[track.track_id], image_to_pitch)
                    if image_to_pitch is not None
                    else None
                )
                if smooth_pitch is not None:
                    pitch_feet[track.track_id] = smooth_pitch
                samples.append(
                    (
                        track.track_id,
                        track.role,
                        colors.get(track.track_id),
                        None if raw_pitch is None else raw_pitch[0],
                    )
                )
            foot_trail.retain(live_ids)
            if detect:
                jersey_memory.update(colors)
                for track_id in list(jersey_memory):
                    if track_id not in live_ids:
                        del jersey_memory[track_id]
                labels = teams.update(samples)
            else:
                labels = _resolve_sticky(
                    teams,
                    {
                        track.track_id: "referee" if track.role == "referee" else "unknown"
                        for track in display_tracks
                    },
                )

            space = "image" if image_to_pitch is None else "pitch"
            ball_measurement = raw_ball[0] if detect and raw_ball is not None else None
            ball_confidence = raw_ball[1] if detect and raw_ball is not None else 0.0
            ball_fix = ball_smoother.update(
                ball_measurement if detect else None,
                visible=bool(detect and ball_measurement is not None),
                confidence=ball_confidence,
                frame_gap=1,
                max_jump=0.15 * width,
            )
            players = []
            for track in display_tracks:
                team = labels.get(track.track_id, "unknown")
                if isinstance(team, int):
                    team = "unknown"
                players.append(
                    PlayerFix(
                        track_id=track.track_id,
                        xy=track.foot,
                        team=str(team),
                        role=track.role,
                        velocity=(track.vx, track.vy),
                    )
                )
            ball_speed = _dist((0.0, 0.0), ball_smoother.velocity)
            ball_for_possessor = ball_fix.visible
            # A weak box far from every foot is ignored, unless it is moving
            # like a pass. BallSmoother already rejected a low-confidence jump.
            if ball_for_possessor and ball_fix.confidence < 0.45 and ball_fix.xy is not None:
                nearest = min(
                    (
                        _dist(ball_fix.xy, player.xy)
                        for player in players
                        if player.role != "referee"
                    ),
                    default=1e9,
                )
                if nearest > possessor_tracker.max_distance and ball_speed < possessor_tracker.resolved_flight_speed():
                    ball_for_possessor = False
            possessor = possessor_tracker.update(
                players,
                ball_fix.xy,
                ball_visible=ball_for_possessor,
                frame_gap=1,
                ball_velocity=ball_smoother.velocity,
            )
            if possessor.track_id is not None:
                stats.possessor_frames += 1
            if possessor.held:
                stats.possessor_held += 1
            possessor_foot = next(
                (player.xy for player in players if player.track_id == possessor.track_id),
                None,
            )
            display_ball = ball_mark.update(
                ball_fix.xy if ball_fix.visible else None,
                visible=ball_fix.visible,
                possessor_foot=possessor_foot,
            )

            overlay = _compose(
                frame_shape=(height, width),
                tracks=display_tracks,
                labels=labels,
                players=players,
                pitch_feet=pitch_feet,
                possessor=possessor,
                display_ball=display_ball,
                smooth_feet=smooth_feet,
                memory=memory,
                space=space,
                mode=mode,
                image_to_pitch=image_to_pitch,
                pitch_to_image=active_matrix,
                policy=policy,
                minute=config.minute,
                second=min(59, int((frame_idx / source_fps) % 60)),
                score_home=config.score_home,
                score_away=config.score_away,
                show_minimap=config.minimap,
                frame_width=width,
                frame_height=height,
                jerseys=jersey_memory,
            )
            painted = _paint(frame, overlay)
            writer.write(painted)
            _maybe_screenshot(painted, config, frame_idx, source_fps)
            stats.frames += 1
            frame_idx += 1
            if stats.frames % 25 == 0:
                elapsed = time.perf_counter() - started
                print(
                    f"frame {stats.frames}  wall {elapsed:.1f}s  "
                    f"plane {mode}  possessor {possessor.state}:{possessor.source}",
                    flush=True,
                )
    finally:
        capture.release()
        writer.close()
    stats.wall_seconds = time.perf_counter() - started
    stats.seconds = stats.frames / source_fps if source_fps else 0.0
    stats.output_fps = stats.frames / stats.wall_seconds if stats.wall_seconds else 0.0
    if stats.detect_frames:
        stats.notes.append(
            f"mean player inference {stats.player_ms / stats.detect_frames:.0f} ms"
        )
    if stats.pitch_inferences:
        stats.notes.append(
            f"mean pitch inference {stats.pitch_ms / stats.pitch_inferences:.0f} ms"
        )
    if stats.ball_inferences:
        stats.notes.append(
            f"mean ball inference {stats.ball_ms / stats.ball_inferences:.0f} ms"
        )
    summary_path = config.output_path.with_suffix(".json")
    summary_path.write_text(json.dumps(stats.as_dict(), indent=2), encoding="utf-8")
    print(json.dumps(stats.as_dict(), indent=2), flush=True)
    return stats


def _compose(
    *,
    frame_shape,
    tracks,
    labels,
    players,
    pitch_feet,
    possessor,
    display_ball,
    smooth_feet,
    memory,
    space,
    mode,
    image_to_pitch,
    pitch_to_image,
    policy,
    minute,
    second,
    score_home,
    score_away,
    show_minimap,
    frame_width,
    frame_height,
    jerseys=None,
) -> OverlayState:
    state = OverlayState(show_minimap=show_minimap)
    possessor_id = possessor.track_id
    for track in tracks:
        team = labels.get(track.track_id, "unknown")
        state.players.append(
            PlayerDraw(
                track_id=track.track_id,
                bbox=track.bbox,
                foot=smooth_feet.get(track.track_id, track.foot),
                team=str(team),
                possessor=track.track_id == possessor_id,
            )
        )
    badges = []
    if mode == "current":
        badges.append("homography ok")
    elif mode == "held":
        badges.append("homography held")
    else:
        badges.append("image coordinates")
    if possessor.held:
        badges.append("ball missed — holding possessor")
    elif possessor.state == "PASS_IN_FLIGHT":
        badges.append("pass in flight")
    elif possessor.state == "CONTESTED":
        badges.append("possession contested")
    elif possessor.source == "loose" or possessor.state == "LOOSE":
        badges.append("ball loose")
    elif possessor.source == "none":
        badges.append("no possessor")
    state.badges = badges

    state.ball = display_ball
    if pitch_to_image is not None:
        state.wireframe = _wireframe(pitch_to_image, frame_shape)

    if possessor.track_id is None or possessor.xy is None:
        state.note = "No on-ball player. Distribution hidden until the ball is with someone."
        return state

    if possessor.team not in ("home", "away"):
        state.note = "Jersey colours are still splitting, so pass and shot arrows stay hidden."
        return state

    attacking_positive = attacking_positive_for(possessor.team)
    possession_team = possessor.team
    # Arrows and the possessor ring share the smoothed foot, not the ball box.
    origin = smooth_feet.get(possessor.track_id, possessor.xy)
    working = [
        PlayerFix(
            track_id=player.track_id,
            xy=smooth_feet.get(player.track_id, player.xy),
            team=player.team,
            role=player.role,
        )
        for player in players
    ]
    if space == "pitch":
        placed = []
        for player in players:
            mapped = pitch_feet.get(player.track_id)
            if mapped is None:
                continue
            placed.append(
                PlayerFix(track_id=player.track_id, xy=mapped, team=player.team, role=player.role)
            )
        mapped_origin = pitch_feet.get(possessor.track_id)
        if mapped_origin is None or not placed:
            space = "image"
        else:
            origin = mapped_origin
            working = placed
    if space == "pitch":
        ball_x, ball_y = origin
        opponents = [
            _dist(origin, player.xy)
            for player in working
            if player.team not in (possession_team, "unknown", "referee") and player.role != "referee"
        ]
        pressure = pressure_from_distances(opponents)
        bounds = (PITCH_LENGTH, PITCH_WIDTH)
    else:
        ball_x, ball_y = image_xy_to_pitch_meters(origin[0], origin[1], frame_width, frame_height)
        pixel_distances = [
            _dist(origin, player.xy) / frame_width * PITCH_LENGTH
            for player in working
            if player.team not in (possession_team, "unknown", "referee") and player.role != "referee"
        ]
        pressure = pressure_from_distances(pixel_distances)
        bounds = (float(frame_width), float(frame_height))
    features = features_from_cv(
        ball_x_m=ball_x,
        ball_y_m=ball_y,
        possession_team=possession_team,
        pressure=pressure,
        minute=minute,
        second=second,
        score_home=score_home,
        score_away=score_away,
    )
    distribution = policy.predict_features(features)
    raw_recommended = max(distribution.probabilities, key=distribution.probabilities.get)
    remembered = {} if jerseys is None else jerseys
    option_players = [
        OptionPlayer(
            track_id=player.track_id,
            xy=player.xy,
            team=player.team,
            role=player.role,
            jersey=remembered.get(player.track_id),
        )
        for player in working
    ]
    fresh = build_options(
        origin,
        option_players,
        possessor.track_id,
        possession_team,
        raw_recommended,
        bounds=bounds,
        attacking_positive=attacking_positive,
        space=space,
    )
    # The hold locks the primary only. Dim alternatives are chosen after that.
    primary_only = [item for item in fresh if item.primary]
    recommended, smoothed, held = memory.apply(
        possessor.track_id,
        distribution.probabilities,
        primary_only,
        option_players,
        origin,
        possession_team,
        bounds,
        attacking_positive,
        space,
    )
    if recommended in ("pass", "dribble") and recommended != raw_recommended:
        fresh = build_options(
            origin,
            option_players,
            possessor.track_id,
            possession_team,
            recommended,
            bounds=bounds,
            attacking_positive=attacking_positive,
            space=space,
        )
    elif recommended not in ("pass", "dribble"):
        fresh = []
    teammates = {
        track_id: player.xy
        for track_id, player in eligible_receivers(
            option_players,
            possessor.track_id,
            possession_team,
            attacking_positive,
            bounds,
        ).items()
    }
    options = compose_drawn(recommended, held, fresh, teammates)
    for option in options:
        if option.kind not in ("pass", "dribble"):
            continue
        if option.kind == "pass" and option.target_id not in teammates:
            continue
        if space == "pitch" and pitch_to_image is not None:
            projected = project_segment(pitch_to_image, option.origin, option.target)
            if projected is None:
                continue
            points = projected
        else:
            points = _image_segment(option.origin, option.target)
        if option.kind != "hold":
            clipped = clip_polyline(points, frame_width, frame_height)
            if clipped is None:
                continue
            points = clipped
        state.arrows.append(
            ArrowDraw(
                kind=option.kind,
                points=points,
                primary=option.primary,
                label=option.label,
                alpha=option.alpha,
            )
        )
        if space == "pitch":
            origin_m, target_m = option.origin, option.target
        else:
            origin_m = image_xy_to_pitch_meters(option.origin[0], option.origin[1], frame_width, frame_height)
            target_m = image_xy_to_pitch_meters(option.target[0], option.target[1], frame_width, frame_height)
        state.minimap_arrows.append(
            MinimapArrow(kind=option.kind, origin=origin_m, target=target_m, primary=option.primary)
        )
    for player in working:
        if space == "pitch":
            xy_m = player.xy
        else:
            xy_m = image_xy_to_pitch_meters(player.xy[0], player.xy[1], frame_width, frame_height)
        state.minimap_players.append(
            MinimapPlayer(xy=xy_m, team=player.team, possessor=player.track_id == possessor.track_id)
        )
    if space == "pitch":
        state.minimap_ball = origin
    else:
        state.minimap_ball = image_xy_to_pitch_meters(
            origin[0], origin[1], frame_width, frame_height
        )
    state.probabilities = smoothed
    state.recommended = recommended
    state.badges.append("attacking the right goal" if attacking_positive else "attacking the left goal")
    zone = zone_name(ball_x, ball_y, possession_team).replace("_", " ")
    share = smoothed[recommended]
    state.note = (
        f"recommended {recommended} {share:.0%}  ·  {zone}  ·  "
        f"pressure {features.pressure:.2f}  ·  full distribution in the bars"
    )
    return state


def _paint(frame, state: OverlayState):
    from demo.render import draw_overlay

    return draw_overlay(frame, state)


def _wireframe(pitch_to_image, frame_shape) -> list[tuple[tuple[float, float], ...]]:
    height, width = frame_shape
    vertices = pitch_vertices_m()
    lines: list[tuple[tuple[float, float], ...]] = []
    for start, end in PITCH_EDGES:
        segment = project_segment(
            pitch_to_image,
            vertices[start - 1],
            vertices[end - 1],
            samples=8,
            max_jump_px=max(width, height),
        )
        if segment is not None and _mostly_inside(segment, width, height):
            lines.append(segment)
    circle = centre_circle_m(samples=20)
    projected_ring: list[tuple[float, float]] = []
    for point in list(circle) + [circle[0]]:
        mapped = apply_homography(pitch_to_image, point[0], point[1])
        if mapped is None:
            projected_ring = []
            break
        projected_ring.append(mapped)
    if projected_ring and _mostly_inside(projected_ring, width, height):
        lines.append(tuple(projected_ring))
    return lines


def _mostly_inside(points, width: int, height: int) -> bool:
    margin = 0.35 * max(width, height)
    inside = 0
    for x, y in points:
        if -margin <= x <= width + margin and -margin <= y <= height + margin:
            inside += 1
    return inside >= max(2, int(0.6 * len(points)))


def _image_segment(start, end, samples: int = 12) -> tuple[tuple[float, float], ...]:
    points = []
    for index in range(samples):
        blend = index / (samples - 1)
        points.append(
            (
                start[0] + blend * (end[0] - start[0]),
                start[1] + blend * (end[1] - start[1]),
            )
        )
    return tuple(points)


def _team_book(config: DemoConfig) -> TeamBook:
    """Team book for this run, including a scene-cut reset.

    The home-jersey lock has to survive the reset, or the next shot would
    cluster the striped kit again and pass targets would pin the wrong side.
    """
    return TeamBook(home_jersey=config.home_jersey)


def _resolve_sticky(teams: TeamBook, labels: dict[int, object]) -> dict[int, str]:
    resolved: dict[int, str] = {}
    for track_id, label in labels.items():
        if label == "referee":
            resolved[track_id] = "referee"
            continue
        index = teams.cluster_of.get(track_id)
        resolved[track_id] = "unknown" if index is None else teams.label_for(index)
    return resolved


def _foot_pitch(foot, image_to_pitch):
    mapped = apply_homography(image_to_pitch, foot[0], foot[1])
    if mapped is None or not _on_pitch(mapped, margin=12.0):
        return None
    return (
        max(0.0, min(PITCH_LENGTH, mapped[0])),
        max(0.0, min(PITCH_WIDTH, mapped[1])),
    )


def _on_pitch(point, margin: float = 8.0) -> bool:
    if point is None:
        return False
    x, y = point
    return -margin <= x <= PITCH_LENGTH + margin and -margin <= y <= PITCH_WIDTH + margin


def _fit_homography(pairs, vertices):
    import cv2
    import numpy as np

    if len(pairs) < 4:
        return False, None
    image_pts = np.array([point for _index, point in pairs], dtype=np.float64)
    pitch_pts = np.array([vertices[index] for index, _point in pairs], dtype=np.float64)
    matrix, mask = cv2.findHomography(pitch_pts, image_pts, cv2.RANSAC, 16.0)
    if matrix is None or mask is None:
        return False, None
    inliers = int(mask.ravel().sum())
    projected = cv2.perspectiveTransform(pitch_pts.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    errors = np.linalg.norm(projected - image_pts, axis=1)
    chosen = mask.ravel().astype(bool)
    mean = float(errors[chosen].mean()) if chosen.any() else None
    ok, _reason = assess_homography(len(pairs), inliers, mean, max_error_px=40.0, weak_error_px=18.0)
    if not ok:
        return False, None
    cleaned = tuple(tuple(float(value) for value in row) for row in matrix)
    if invert_homography(cleaned) is None:
        return False, None
    return True, cleaned


def _keypoint_pairs(result, min_conf: float) -> list[tuple[int, tuple[float, float]]]:
    keypoints = getattr(result, "keypoints", None)
    if keypoints is None or keypoints.xy is None or len(keypoints.xy) == 0:
        return []
    xy = keypoints.xy.cpu().numpy()
    conf = None if keypoints.conf is None else keypoints.conf.cpu().numpy()
    best: list[tuple[int, tuple[float, float]]] = []
    for index in range(xy.shape[0]):
        pairs = []
        for keypoint_index in range(xy.shape[1]):
            score = 1.0 if conf is None else float(conf[index, keypoint_index])
            if score < min_conf:
                continue
            x = float(xy[index, keypoint_index, 0])
            y = float(xy[index, keypoint_index, 1])
            if x <= 1.0 and y <= 1.0:
                continue
            pairs.append((keypoint_index, (x, y)))
        if len(pairs) > len(best):
            best = pairs
    return best


def _parse_people(result) -> tuple[list[TrackState], tuple[tuple[float, float], float] | None]:
    boxes = result.boxes
    names = result.names
    if boxes is None or boxes.xyxy is None or len(boxes) == 0:
        return [], None
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    classes = boxes.cls.cpu().numpy().astype(int)
    ids = None if boxes.id is None else boxes.id.cpu().numpy().astype(int)
    people: list[TrackState] = []
    ball: tuple[tuple[float, float], float] | None = None
    for index in range(len(xyxy)):
        name = str(names[int(classes[index])]).lower()
        role = _ROLE.get(name, "player")
        if role == "ball" or name == "ball":
            center = (
                float((xyxy[index][0] + xyxy[index][2]) * 0.5),
                float((xyxy[index][1] + xyxy[index][3]) * 0.5),
            )
            confidence = float(confs[index])
            if ball is None or confidence > ball[1]:
                ball = (center, confidence)
            continue
        track_id = int(ids[index]) if ids is not None else index + 1
        x1, y1, x2, y2 = (float(value) for value in xyxy[index])
        people.append(
            TrackState(
                track_id=track_id,
                bbox=(x1, y1, x2, y2),
                role=role,
                confidence=float(confs[index]),
            )
        )
    return people, ball


def _best_ball(result) -> tuple[tuple[float, float], float] | None:
    boxes = result.boxes
    if boxes is None or boxes.xyxy is None or len(boxes) == 0:
        return None
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    index = int(confs.argmax())
    center = (
        float((xyxy[index][0] + xyxy[index][2]) * 0.5),
        float((xyxy[index][1] + xyxy[index][3]) * 0.5),
    )
    return center, float(confs[index])


def _jersey_colors(frame, tracks: list[TrackState]) -> dict[int, tuple[float, float, float]]:
    """Torso colour after the HSV chroma gate.

    Pitch green is removed. A fluorescent shirt stays, including when white
    numbers sit on it. A grass-only crop contributes no colour: there is no
    fallback onto the pitch pixels that used to poison the median.
    """
    height, width = frame.shape[:2]
    colors: dict[int, tuple[float, float, float]] = {}
    for track in tracks:
        if track.role != "player":
            continue
        x1, y1, x2, y2 = track.bbox
        box_w = x2 - x1
        box_h = y2 - y1
        left = int(max(0, x1 + 0.38 * box_w))
        right = int(min(width, x1 + 0.62 * box_w))
        top = int(max(0, y1 + 0.22 * box_h))
        bottom = int(min(height, y1 + 0.42 * box_h))
        if right - left < 2 or bottom - top < 2:
            continue
        patch = frame[top:bottom:2, left:right:2]
        if patch.size == 0:
            continue
        flat = patch.reshape(-1, 3)
        pixels = [(float(pixel[2]), float(pixel[1]), float(pixel[0])) for pixel in flat]
        summary = summarize_jersey(pixels)
        if summary is None:
            continue
        colors[track.track_id] = summary
    return colors


def _tiny_gray(frame):
    import cv2
    import numpy as np

    small = cv2.resize(frame, (48, 27), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)


def _reset_tracker(model) -> None:
    predictor = getattr(model, "predictor", None)
    if predictor is None:
        return
    trackers = getattr(predictor, "trackers", None)
    if not trackers:
        return
    for tracker in trackers:
        reset = getattr(tracker, "reset", None)
        if callable(reset):
            reset()


def _maybe_screenshot(frame, config: DemoConfig, frame_idx: int, fps: float) -> None:
    if config.screenshot_dir is None or not config.screenshot_times:
        return
    import cv2

    timestamp = frame_idx / fps
    for target in config.screenshot_times:
        if abs(timestamp - target) <= 0.5 / fps:
            path = config.screenshot_dir / f"t{target:.1f}s.png"
            cv2.imwrite(str(path), frame)


def _possessor_tracker(hold_frames: int, width: int, height: int):
    """Image-space possession. Speeds scale with the frame, not the pitch."""
    span = float(max(width, height))
    return PossessorTracker(
        hold_frames=hold_frames,
        max_distance=0.12 * height,
        switch_frames=6,
        commit_distance=0.04 * height,
        control_scale=2.4,
        flight_speed=0.008 * span,
        touch_rel_speed=0.004 * span,
        receiver_speed=0.006 * span,
    )


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


class _FfmpegWriter:
    def __init__(self, path: Path, width: int, height: int, fps: float) -> None:
        self.path = path
        self.proc = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-s",
                f"{width}x{height}",
                "-r",
                f"{fps:.4f}",
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-crf",
                "20",
                str(path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def write(self, frame) -> None:
        import numpy as np

        if self.proc.stdin is None:
            raise RuntimeError("ffmpeg stdin is closed")
        array = np.ascontiguousarray(frame)
        self.proc.stdin.write(array.tobytes())

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        stderr = b""
        if self.proc.stderr is not None:
            stderr = self.proc.stderr.read()
        code = self.proc.wait()
        if code != 0:
            tail = stderr.decode("utf-8", errors="replace")[-800:]
            raise RuntimeError(f"ffmpeg exited {code}: {tail}")
