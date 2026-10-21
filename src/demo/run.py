"""Command line for the broadcast overlay.

``python -m demo.run --input in.mp4 --output out.mp4 --stride 2``

Lock the home kit when stripe samples would otherwise swap team ids:

``python -m demo.run --input in.mp4 --output out.mp4 --home-jersey white-black``
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from demo.pipeline import DemoConfig, run_clip
from demo.teams import HOME_JERSEY_ENV, HomeJerseySpecError, parse_home_jersey_specs


def main(argv: list[str] | None = None) -> int:
    config = build_config(argv)
    run_clip(config)
    return 0


def build_config(argv: list[str] | None = None) -> DemoConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Overlay on-ball pass, carry, and shot options on a football broadcast. "
            "The detector runs every --stride frames; the frames in between are filled "
            "by constant-velocity tracking."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Source mp4.")
    parser.add_argument("--output", required=True, type=Path, help="Overlaid mp4 to write.")
    parser.add_argument(
        "--stride",
        type=int,
        default=2,
        help="Run detection every Nth frame (default 2). Intermediate frames are tracked.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Stop after this many seconds of source video. Default: the whole file.",
    )
    parser.add_argument("--minute", type=int, default=45, help="Match minute used in the softmax vector.")
    parser.add_argument("--score-home", type=int, default=0)
    parser.add_argument("--score-away", type=int, default=0)
    parser.add_argument(
        "--home-jersey",
        action="append",
        default=None,
        metavar="SPEC",
        help=(
            "Lock this kit as home for the whole run so the jersey team id does not "
            "flip. SPEC is white-black, black-white, white, black, rgb:R,G,B, or a "
            "pair joined by + (rgb:245,245,245+rgb:16,16,16). Repeat the flag to add "
            "another sample. Omit it to keep the online 2-means defensive-tail "
            f"assignment. Falls back to {HOME_JERSEY_ENV} when the flag is omitted."
        ),
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--imgsz", type=int, default=640, help="Player detector image size.")
    parser.add_argument("--ball-imgsz", type=int, default=960)
    parser.add_argument("--pitch-imgsz", type=int, default=640)
    parser.add_argument(
        "--pitch-every",
        type=int,
        default=15,
        help="Run the pitch keypoint model every N source frames.",
    )
    parser.add_argument("--hold-frames", type=int, default=18, help="Frames to keep the last possessor.")
    parser.add_argument(
        "--homography-hold",
        type=int,
        default=30,
        help="Frames to reuse the last good homography before falling back to image coordinates.",
    )
    parser.add_argument("--minimap", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--models-dir", type=Path, default=Path("data/models"))
    parser.add_argument("--screenshot-dir", type=Path, default=None)
    parser.add_argument(
        "--screenshot-times",
        default="",
        help="Comma-separated timestamps in seconds, for example 2,5,8.",
    )
    args = parser.parse_args(argv)
    if args.stride < 1:
        parser.error("--stride must be >= 1")
    if not args.input.is_file():
        parser.error(f"input not found: {args.input}")
    times = tuple(float(piece) for piece in args.screenshot_times.split(",") if piece.strip())
    home_jersey = _home_jersey_from_args(parser, args.home_jersey)
    config = DemoConfig(
        input_path=args.input,
        output_path=args.output,
        stride=args.stride,
        seconds=args.seconds,
        minute=args.minute,
        score_home=args.score_home,
        score_away=args.score_away,
        home_jersey=home_jersey,
        device=args.device,
        imgsz=args.imgsz,
        ball_imgsz=args.ball_imgsz,
        pitch_imgsz=args.pitch_imgsz,
        pitch_every=args.pitch_every,
        hold_frames=args.hold_frames,
        homography_hold=args.homography_hold,
        minimap=args.minimap,
        models_dir=args.models_dir,
        screenshot_dir=args.screenshot_dir,
        screenshot_times=times,
    )
    return config


def _home_jersey_from_args(
    parser: argparse.ArgumentParser,
    values: list[str] | None,
) -> tuple[tuple[float, float, float], ...]:
    specs = values
    if not specs:
        env = os.environ.get(HOME_JERSEY_ENV, "").strip()
        specs = [env] if env else []
    if not specs:
        return ()
    try:
        return parse_home_jersey_specs(specs)
    except HomeJerseySpecError as exc:
        parser.error(str(exc))
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
