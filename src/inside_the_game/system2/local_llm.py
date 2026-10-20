"""Optional local rationale model. Off unless the caller passes one in.

``explain`` uses the offline template when ``local_llm`` is omitted.
``load_local_llm`` returns ``None``, so nothing in the environment can turn
a model on. This module does not import an HTTP client and does not open a
socket. Hosted Foundry, TypeSafe, and other inference APIs are not called.

To enable a local model, pass an object with
``rationale(event, distribution, profile) -> str``::

    explain(event, distribution, local_llm=MyLocalModel())

The string should stay short, name pass, shoot, dribble, and hold, and must
not label one action as optimal. An empty return falls back to the template.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from inside_the_game.ingest.events import MatchEvent
    from inside_the_game.system1.policy import ActionDistribution
    from inside_the_game.system2.explain import ViewerProfile


class LocalRationale(Protocol):
    """Same inputs as ``explain``. Implementations must stay on this machine."""

    def rationale(
        self,
        event: MatchEvent,
        distribution: ActionDistribution,
        profile: ViewerProfile,
    ) -> str:
        """Return short rationale text for one on-ball state."""


def load_local_llm() -> LocalRationale | None:
    """No local model is configured. The default explain path does not call this."""
    return None
