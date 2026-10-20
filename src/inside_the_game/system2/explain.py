"""System 2 explain. Default rationale is an offline template.

``explain`` takes one match event and a System 1 distribution and returns
short football text. A Foundry-shaped chat body is built and stored; it is
not sent. Pass ``local_llm`` only to replace the template with a local model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from inside_the_game.ingest.events import MatchEvent
from inside_the_game.system1.policy import ActionDistribution
from inside_the_game.system2.local_llm import LocalRationale
from inside_the_game.system2.sidecar import XTVAEPSidecar, xt_vaep_sidecar
from inside_the_game.system2.template import template_rationale


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
    """Offline rationale plus the message body a Foundry deployment would receive.

    ``messages`` is local data. Nothing in this package posts it.
    ``source`` is ``template`` unless the caller passed ``local_llm``.
    """

    event_id: str
    text: str
    messages: tuple[dict[str, str], ...]
    sidecar: XTVAEPSidecar
    profile_role: str
    source: str


def explain(
    event: MatchEvent,
    distribution: ActionDistribution,
    profile: ViewerProfile | None = None,
    *,
    local_llm: LocalRationale | None = None,
) -> Explanation:
    """Explain the full distribution. Probabilities are left unchanged.

    The default path formats ``template_rationale`` and does not use the
    network. ``local_llm`` is optional and off when omitted.
    """
    viewer = profile or ViewerProfile()
    sidecar = xt_vaep_sidecar(event)
    messages = foundry_messages(event, distribution, sidecar, viewer)
    if local_llm is None:
        raw = template_rationale(event, distribution, sidecar)
        source = "template"
    else:
        raw = local_llm.rationale(event, distribution, viewer).strip()
        if not raw:
            raw = template_rationale(event, distribution, sidecar)
            source = "template"
        else:
            source = "local_llm"
    text = personalize(raw, viewer)
    return Explanation(
        event_id=event.event_id,
        text=text,
        messages=tuple(messages),
        sidecar=sidecar,
        profile_role=viewer.role,
        source=source,
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
