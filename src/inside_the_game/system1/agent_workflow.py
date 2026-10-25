"""Microsoft Agent Framework run for one on-ball decision.

Four executors with distinct roles, in a fixed order, sharing one state:

| Tool | Role |
| --- | --- |
| ``read-frame`` | the tracking frame at ``available_at_ms``, and no later event |
| ``decide`` | softmax probabilities, primary and secondary pass, carry path |
| ``score-completion`` | pitch control x xT on the ends the decision chose |
| ``narrate`` | a Foundry ``gpt-4.1-mini`` request built from the decision JSON |

The graph is a chain, so the handoff order is the contract. Each executor
recovers on its own: a scoring failure still lets the narration run, and a
narration failure still returns the decision. Every degradation is recorded in
``degraded`` rather than swallowed, so a run that lost a step says so.

The artifacts travel through the framework state store, not through Python
closures, so each executor only sees what the previous one published.

Narration is injected by the caller. With no narrator the request is built but
not sent, which keeps the offline path the default and the network path
opt-in.

    from inside_the_game.system1.agent_workflow import run_decision_workflow

    result = run_decision_workflow(match, event)
    result["narration"]["sent"]  # False without a narrator
"""

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from inside_the_game.features.from_tracking import SynthMatch, frame_for_decision
from inside_the_game.system1.policy import SoftmaxActionPolicy
from inside_the_game.system1.tracking import decide_from_tracking, score_paths
from inside_the_game.system2.foundry import foundry_narration_request

TOOL_NAMES = ("read-frame", "decide", "score-completion", "narrate")

# State store keys. The request stays in the closure; these are the artifacts
# each executor publishes for the next one.
FRAME_KEY = "frame"
DECISION_KEY = "decision"
COMPLETION_KEY = "completion"
NARRATION_KEY = "narration"
TRACE_KEY = "trace"
DEGRADED_KEY = "degraded"

# A narrator turns the decision JSON into a narration payload.
Narrator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class DecisionRequest:
    """What the run needs. Passed in, not shared between executors."""

    match: SynthMatch
    event: dict[str, Any]
    policy: SoftmaxActionPolicy
    narrator: Narrator | None = None


def _payload(ctx: Any) -> dict[str, Any]:
    """Collect what the executors published into the workflow state store."""
    return {
        "frame": ctx.get_state(FRAME_KEY),
        "decision": ctx.get_state(DECISION_KEY),
        "completion": ctx.get_state(COMPLETION_KEY),
        "narration": ctx.get_state(NARRATION_KEY),
        "trace": ctx.get_state(TRACE_KEY) or [],
        "degraded": ctx.get_state(DEGRADED_KEY) or [],
    }


def _build_workflow(request: DecisionRequest):
    """Wire the four executors into a chain. Imports the framework lazily."""
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

    def record(ctx: WorkflowContext, tool: str, **detail: Any) -> None:
        trace = ctx.get_state(TRACE_KEY)
        if not isinstance(trace, list):
            trace = []
        trace.append({"tool": tool, **detail})
        ctx.set_state(TRACE_KEY, trace)

    def degrade(ctx: WorkflowContext, tool: str, reason: str) -> None:
        degraded = ctx.get_state(DEGRADED_KEY)
        if not isinstance(degraded, list):
            degraded = []
        degraded.append(f"{tool}: {reason}")
        ctx.set_state(DEGRADED_KEY, degraded)

    class ReadFrameExecutor(Executor):
        """Publishes the frame the decision was taken on."""

        def __init__(self) -> None:
            super().__init__(id="read-frame")

        @handler
        async def process(
            self,
            message: Any,
            ctx: WorkflowContext[dict[str, Any], Any],
        ) -> None:
            frame = frame_for_decision(request.match, request.event)
            if int(frame["t_ms"]) > int(request.event["available_at_ms"]):
                raise ValueError("read-frame refused a frame from after the decision")
            ctx.set_state(FRAME_KEY, frame)
            record(
                ctx,
                "read-frame",
                frame_id=int(frame["frame_id"]),
                t_ms=int(frame["t_ms"]),
                attack_dir=int(frame["attack_dir"]),
            )
            await ctx.send_message(frame)

    class DecideExecutor(Executor):
        """Publishes the softmax probabilities and the pass and carry geometry."""

        def __init__(self) -> None:
            super().__init__(id="decide")

        @handler
        async def process(
            self,
            message: Any,
            ctx: WorkflowContext[dict[str, Any], Any],
        ) -> None:
            frame = ctx.get_state(FRAME_KEY)
            if not isinstance(frame, dict):
                raise RuntimeError("decide ran without a frame")
            try:
                decision = decide_from_tracking(
                    frame, request.event, request.match.team_of, request.policy
                )
            except Exception as exc:
                # The decision is the run. Without it there is nothing to hand on.
                degrade(ctx, "decide", repr(exc))
                raise
            ctx.set_state(DECISION_KEY, decision)
            record(ctx, "decide", event_id=decision["event_id"])
            await ctx.send_message(decision)

    class ScoreCompletionExecutor(Executor):
        """Publishes pitch control x xT on the ends the decision chose."""

        def __init__(self) -> None:
            super().__init__(id="score-completion")

        @handler
        async def process(
            self,
            message: Any,
            ctx: WorkflowContext[dict[str, Any], Any],
        ) -> None:
            frame = ctx.get_state(FRAME_KEY)
            decision = ctx.get_state(DECISION_KEY)
            if not isinstance(frame, dict) or not isinstance(decision, dict):
                raise RuntimeError("score-completion ran without a decision")
            try:
                completion = score_paths(
                    frame, request.event, request.match.team_of, decision
                )
            except Exception as exc:
                # The probabilities and the geometry still stand. A missing
                # score is a degradation, not a reason to drop the run.
                degrade(ctx, "score-completion", repr(exc))
                record(ctx, "score-completion", method="unavailable", paid_api=False)
                await ctx.send_message(decision)
                return
            ctx.set_state(COMPLETION_KEY, completion)
            record(ctx, "score-completion", method=completion["method"], paid_api=False)
            await ctx.send_message(decision)

    class NarrateExecutor(Executor):
        """Publishes the narration, sent when a narrator was injected."""

        def __init__(self) -> None:
            super().__init__(id="narrate")

        @handler
        async def process(
            self,
            message: Any,
            ctx: WorkflowContext[dict[str, Any], Any],
        ) -> None:
            decision = ctx.get_state(DECISION_KEY)
            if not isinstance(decision, dict):
                raise RuntimeError("narrate ran without a decision")
            built = foundry_narration_request(decision)
            narrator = request.narrator
            if narrator is None:
                ctx.set_state(NARRATION_KEY, built)
                record(ctx, "narrate", deployment=built["deployment"], sent=built["sent"])
            else:
                try:
                    narration = await asyncio.to_thread(narrator, decision)
                except Exception as exc:
                    degrade(ctx, "narrate", repr(exc))
                    ctx.set_state(NARRATION_KEY, built)
                    record(
                        ctx, "narrate", deployment=built["deployment"], sent=built["sent"]
                    )
                else:
                    ctx.set_state(NARRATION_KEY, narration)
                    record(
                        ctx,
                        "narrate",
                        deployment=narration.get("deployment", built["deployment"]),
                        sent=bool(narration.get("sent")),
                    )
            await ctx.yield_output(_payload(ctx))

    read_frame = ReadFrameExecutor()
    decide = DecideExecutor()
    score = ScoreCompletionExecutor()
    narrate = NarrateExecutor()

    builder = WorkflowBuilder(start_executor=read_frame, name="inside-the-game-decision")
    builder.add_edge(read_frame, decide)
    builder.add_edge(decide, score)
    builder.add_edge(score, narrate)
    return builder.build()


def run_decision_workflow(
    match: SynthMatch,
    event: dict[str, Any],
    policy: SoftmaxActionPolicy | None = None,
    narrator: Narrator | None = None,
) -> dict[str, Any]:
    """Run the four tools on one decision point and return the artifacts.

    ``narrator`` is called with the decision JSON. When it is ``None`` the
    narration request is built but not sent, which is the offline default.
    """
    request = DecisionRequest(
        match=match,
        event=event,
        policy=policy or SoftmaxActionPolicy(),
        narrator=narrator,
    )
    workflow = _build_workflow(request)
    result = workflow.run(event)
    if inspect.isawaitable(result):
        result = asyncio.run(result)  # type: ignore[arg-type]
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else []
    payload = outputs[-1] if outputs else {}
    return {
        "tools": list(payload.get("trace") or []),
        "frame": payload.get("frame"),
        "decision": payload.get("decision"),
        "completion": payload.get("completion"),
        "narration": payload.get("narration"),
        "degraded": list(payload.get("degraded") or []),
    }


def _state_of(result: Any, key: str) -> Any:
    """Read one key out of the finished run's state store."""
    final = result.get_final_state() if hasattr(result, "get_final_state") else None
    if final is None:
        return None
    if isinstance(final, dict):
        return final.get(key)
    state = getattr(final, "state", None)
    if isinstance(state, dict):
        return state.get(key)
    return None


def _trace_of(result: Any) -> Any:
    final = result.get_final_state() if hasattr(result, "get_final_state") else None
    if isinstance(final, dict):
        return final.get(TRACE_KEY) or []
    state = getattr(final, "state", None)
    if isinstance(state, dict):
        return state.get(TRACE_KEY) or []
    return []
