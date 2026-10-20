"""MVP path: ingest → System 1 → System 2 → present."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from inside_the_game.ingest.events import MatchEvent
from inside_the_game.ingest.loader import load_events
from inside_the_game.present.overlay import ReplayOverlay, render_overlay
from inside_the_game.system1.policy import ActionDistribution, SoftmaxActionPolicy
from inside_the_game.system2.explain import Explanation, ViewerProfile, explain


@dataclass(frozen=True)
class DecisionFrame:
    """One event after the MVP path. The distribution is the whole answer."""

    event: MatchEvent
    distribution: ActionDistribution
    explanation: Explanation
    overlay: ReplayOverlay


def run_mvp(
    events: tuple[MatchEvent, ...] | None = None,
    *,
    fixture: Path | None = None,
    profile: ViewerProfile | None = None,
) -> tuple[DecisionFrame, ...]:
    """Run steps 1 → 2 → 4 → 5. System 1 is the softmax policy.

    Computer vision is not part of this path. The optional Jev hook is not
    called here; use ``load_jev_choice`` when that backend is installed.
    """
    match_events = events if events is not None else load_events(fixture)
    policy = SoftmaxActionPolicy()
    frames: list[DecisionFrame] = []
    for event in match_events:
        distribution = policy.predict(event)
        explanation = explain(event, distribution, profile)
        overlay = render_overlay(event, distribution, explanation.text)
        frames.append(
            DecisionFrame(
                event=event,
                distribution=distribution,
                explanation=explanation,
                overlay=overlay,
            )
        )
    return tuple(frames)
