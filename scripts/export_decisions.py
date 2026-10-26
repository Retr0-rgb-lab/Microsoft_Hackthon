"""Export System 1 decisions for the checked-in SynthData clip.

Runs the decision layer over every ``decision_point`` in the sample and writes
one JSON payload the three.js pitch sample can draw directly: the four
probabilities, the primary and secondary pass, and the carry path.

Every path is in centre-spot metres, the same frame the tracking data uses, so
the renderer only has to map ``(x, y)`` to the scene and draw a polyline.

    python scripts/export_decisions.py
    python scripts/export_decisions.py --output /tmp/decisions.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from inside_the_game.features.from_tracking import (
    frame_for_decision,
    load_synth_match,
)
from inside_the_game.system1.policy import SoftmaxActionPolicy
from inside_the_game.system1.tracking import decide_from_tracking, score_paths

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = REPO_ROOT / "touchline" / "data" / "samples" / "sample_25hz_10min"
DEFAULT_OUTPUT = REPO_ROOT / "touchline" / "data" / "decisions.json"

SCHEMA_VERSION = 1


def build_payload(sample: Path) -> dict[str, Any]:
    """Run the decision layer over the sample and return the draw payload."""
    match = load_synth_match(sample)
    policy = SoftmaxActionPolicy()
    decisions: list[dict[str, Any]] = []

    points = [event for event in match.events if event.get("type") == "decision_point"]
    points.sort(key=lambda event: int(event["available_at_ms"]))

    for event in points:
        frame = frame_for_decision(match, event)
        decision = decide_from_tracking(frame, event, match.team_of, policy)
        completion = score_paths(frame, event, match.team_of, decision)
        decisions.append(
            {
                "event_id": decision["event_id"],
                "t_ms": int(event["available_at_ms"]),
                "frame_id": int(frame["frame_id"]),
                "team_id": str(event["team_id"]),
                "player_id": str(event["player_id"]),
                "probabilities": decision["probabilities"],
                "primary_pass": decision["primary_pass"],
                "secondary_pass": decision["secondary_pass"],
                "carry": decision["carry"],
                "completion": completion,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "match_id": match.match_id,
        "frame_hz": match.frame_hz,
        "origin": "centre_spot",
        "pitch_length_m": 105,
        "pitch_width_m": 68,
        "source": str(sample.relative_to(REPO_ROOT)).replace("\\", "/"),
        "decision_count": len(decisions),
        "decisions": decisions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    payload = build_payload(args.sample)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"{payload['decision_count']} decisions -> {args.output} "
        f"(match {payload['match_id']}, {payload['frame_hz']} Hz)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
