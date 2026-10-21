"""Command line for the broadcast overlay.

``python -m demo.run --input in.mp4 --output out.mp4 --stride 2``
"""

from __future__ import annotations

import argparse
from pathlib import Path

from demo.pipeline import DemoConfig, run_clip


def main(argv: list[str] | None = None) -> int:
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
    config = DemoConfig(
        input_path=args.input,
        output_path=args.output,
        stride=args.stride,
        seconds=args.seconds,
        minute=args.minute,
        score_home=args.score_home,
        score_away=args.score_away,
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
    run_clip(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
