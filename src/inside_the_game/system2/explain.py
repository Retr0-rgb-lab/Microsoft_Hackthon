"""System 2 explain and personalize hooks. Foundry/LLM-shaped, offline."""

from __future__ import annotations

import json
from dataclasses import dataclass

from inside_the_game.ingest.events import MatchEvent
from inside_the_game.system1.policy import ActionDistribution
from inside_the_game.system2.sidecar import XTVAEPSidecar, xt_vaep_sidecar


_ROLES = ("neutral", "fan", "analyst", "player")


@dataclass(frozen=True)
class ViewerProfile:
    """Who is reading the decision aid. Does not change the distribution."""

    role: str = "neutral"

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise ValueError(f"viewer role must be one of {_ROLES}")


@dataclass(frozen=True)
class Explanation:
    """Local explanation plus the message body a Foundry deployment would receive."""

    event_id: str
    text: str
    messages: tuple[dict[str, str], ...]
    sidecar: XTVAEPSidecar
    profile_role: str


def explain(
    event: MatchEvent,
    distribution: ActionDistribution,
    profile: ViewerProfile | None = None,
) -> Explanation:
    """Explain the full distribution. Probabilities are left unchanged."""
    viewer = profile or ViewerProfile()
    sidecar = xt_vaep_sidecar(event)
    messages = foundry_messages(event, distribution, sidecar, viewer)
    text = personalize(_local_explanation(event, distribution, sidecar), viewer)
    return Explanation(
        event_id=event.event_id,
        text=text,
        messages=tuple(messages),
        sidecar=sidecar,
        profile_role=viewer.role,
    )


def foundry_messages(
    event: MatchEvent,
    distribution: ActionDistribution,
    sidecar: XTVAEPSidecar,
    profile: ViewerProfile,
) -> list[dict[str, str]]:
    """Chat body for an Azure AI Foundry deployment. This function does not send it."""
    return [
        {
            "role": "system",
            "content": (
                "Explain a four-way soccer action distribution for a decision aid. "
                "Mention pass, shoot, dribble, and hold with their probabilities. "
                "Present the full distribution. "
                "Treat xT and VAEP notes as sidecar context only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "event": event.to_json_state(),
                    "distribution": distribution.as_dict(),
                    "sidecar": sidecar.as_dict(),
                    "viewer_role": profile.role,
                },
                sort_keys=True,
            ),
        },
    ]


def personalize(text: str, profile: ViewerProfile) -> str:
    """Prefix the explanation for a viewer role. The distribution text stays intact."""
    prefixes = {
        "neutral": "",
        "fan": "For a match viewer: ",
        "analyst": "For a match analyst: ",
        "player": "For the player on the ball: ",
    }
    return prefixes[profile.role] + text


def _local_explanation(
    event: MatchEvent,
    distribution: ActionDistribution,
    sidecar: XTVAEPSidecar,
) -> str:
    shares = ", ".join(
        f"{label} {probability:.0%}" for label, probability in distribution.probabilities.items()
    )
    return (
        f"At {event.minute}:{event.second:02d}, {event.player} ({event.team}) "
        f"has the ball at ({event.ball_x:.0f}, {event.ball_y:.0f}) "
        f"with pressure {event.pressure:.2f}. "
        f"The action distribution is {shares}. "
        f"This decision aid shows the full distribution. "
        f"xT/VAEP sidecar status: {sidecar.status}. {sidecar.detail}"
    )
