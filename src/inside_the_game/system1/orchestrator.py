"""Tool order for one on-ball decision.

This is the in-process shape the Microsoft Agent Framework run will call.
The tools are ``read-frame``, ``decide``, ``score-completion``, and
``narrate``. Narration builds a Foundry ``gpt-4o-mini`` request from the
decision JSON and does not send it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from inside_the_game.features.from_tracking import SynthMatch, frame_for_decision
from inside_the_game.system1.policy import SoftmaxActionPolicy
from inside_the_game.system1.tracking import decide_from_tracking, score_paths
from inside_the_game.system2.foundry import foundry_narration_request


TOOL_NAMES = ("read-frame", "decide", "score-completion", "narrate")


def run_decision_tools(
    match: SynthMatch,
    event: Mapping[str, Any],
    policy: SoftmaxActionPolicy | None = None,
) -> dict[str, Any]:
    """Run the four tools in order on one decision_point.

    ``read-frame`` returns the tracking frame at ``available_at_ms`` and no
    later event. ``decide`` is the softmax plus pass and carry geometry.
    ``score-completion`` recomputes pitch-control × xT. ``narrate`` only
    packages structured JSON.
    """
    model = policy or SoftmaxActionPolicy()
    frame = read_frame(match, event)
    decision = decide_from_tracking(frame, event, match.team_of, model)
    completion = score_paths(frame, event, match.team_of, decision)
    narration = foundry_narration_request(decision)
    trace = [
        {
            "tool": "read-frame",
            "frame_id": int(frame["frame_id"]),
            "t_ms": int(frame["t_ms"]),
            "attack_dir": int(frame["attack_dir"]),
        },
        {"tool": "decide", "event_id": decision["event_id"]},
        {"tool": "score-completion", "method": completion["method"], "paid_api": False},
        {
            "tool": "narrate",
            "deployment": narration["deployment"],
            "sent": narration["sent"],
        },
    ]
    return {
        "tools": trace,
        "decision": decision,
        "completion": completion,
        "narration": narration,
    }


def read_frame(match: SynthMatch, event: Mapping[str, Any]) -> dict[str, Any]:
    """The frame section 6 indexes. Events after this instant are not returned."""
    frame = frame_for_decision(match, event)
    if int(frame["t_ms"]) > int(event["available_at_ms"]):
        raise ValueError("read-frame refused a frame from after the decision")
    return frame
