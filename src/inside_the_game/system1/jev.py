"""Optional TypeSafe Jev Choice hook over JSON/text state.

The MVP pipeline uses :class:`inside_the_game.system1.policy.SoftmaxActionPolicy`.
This module is the alternate System 1 backend. ``load_jev_choice`` returns
``None`` when ``typesafe-sdk`` is not installed, and nothing here calls the
network unless a caller invokes ``TypesafeJevChoice.predict``.

Choice shape follows TypeSafe system_one:
https://docs.typesafe.ai/primitives/choice
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from inside_the_game.ingest.events import MatchEvent
from inside_the_game.labels import ACTION_LABELS, validate_distribution
from inside_the_game.system1.policy import ActionDistribution


ACTION_INSTRUCTIONS = (
    "Given this on-ball soccer state, return the probability of pass, shoot, "
    "dribble, and hold. Return the full distribution."
)
ACTION_CRITERIA: dict[str, str] = {
    "pass": "Play the ball to a teammate.",
    "shoot": "Attempt a shot on goal.",
    "dribble": "Carry the ball to a new location.",
    "hold": "Keep the ball without progressing play.",
}


class JevChoiceHook(Protocol):
    """Text/JSON System 1 backend. Implementations must not read images."""

    def predict(self, event: MatchEvent) -> ActionDistribution:
        """Return P(pass | shoot | dribble | hold) for one event."""


@dataclass(frozen=True)
class JevChoiceRequest:
    """Local description of a TypeSafe Choice call. Building it sends nothing."""

    state: str
    model: str
    questions: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "model": self.model, "questions": self.questions}


class JevUnavailable(RuntimeError):
    """Raised when a caller asks for Jev and the SDK is not installed."""


def build_choice_request(event: MatchEvent, *, model: str = "jev-latest") -> JevChoiceRequest:
    """Build the Choice question for one event from its JSON state."""
    state = json.dumps(event.to_json_state(), sort_keys=True)
    return JevChoiceRequest(
        state=state,
        model=model,
        questions={
            "action": {
                "type": "choice",
                "instructions": ACTION_INSTRUCTIONS,
                "criteria": dict(ACTION_CRITERIA),
            }
        },
    )


def load_jev_choice() -> JevChoiceHook | None:
    """Return a Jev hook when ``typesafe_sdk`` imports; otherwise ``None``.

    Import is attempted only here. A missing dependency is a normal outcome.
    """
    try:
        import typesafe_sdk  # noqa: F401
    except ImportError:
        return None
    return TypesafeJevChoice()


class TypesafeJevChoice:
    """Adapter around ``TypeSafeClient.system_one``. Not used by ``run_mvp``."""

    def __init__(self, *, model: str = "jev-latest") -> None:
        try:
            import typesafe_sdk  # noqa: F401
        except ImportError as exc:
            raise JevUnavailable(
                "typesafe-sdk is optional. Install the jev extra or keep the softmax policy."
            ) from exc
        self.model = model

    def predict(self, event: MatchEvent) -> ActionDistribution:
        from typesafe_sdk import Choice, TypeSafeClient

        request = build_choice_request(event, model=self.model)
        question = request.questions["action"]
        with TypeSafeClient(model=request.model) as client:
            response = client.system_one(
                state=request.state,
                questions={
                    "action": Choice(
                        instructions=question["instructions"],
                        criteria=question["criteria"],
                    )
                },
            )
        raw = _probabilities_from_response(response)
        return ActionDistribution(validate_distribution(raw))


def _probabilities_from_response(response: Any) -> dict[str, float]:
    answers = getattr(response, "answers", None)
    if answers is None:
        answers = getattr(response, "choices", None)
    if answers is None and isinstance(response, dict):
        answers = response.get("answers", response.get("choices"))
    if not answers or "action" not in answers:
        raise ValueError("Jev response did not include an action choice")
    action = answers["action"]
    probabilities = action["probabilities"] if isinstance(action, dict) else action.probabilities
    return {label: float(probabilities[label]) for label in ACTION_LABELS}
