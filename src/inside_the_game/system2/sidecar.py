"""socceraction xT / VAEP explanation sidecar.

These values are context for System 2 only. System 1 does not read them.

TODO: fit ``socceraction.xthreat.ExpectedThreat`` (typically a 16 by 12 grid)
and rate ball-progressing actions with ``ExpectedThreat.rate``.
TODO: fit ``socceraction.vaep.VAEP`` and expose offensive and defensive values
(P(score) and P(concede) before and after the action). Keep the results on
this sidecar. Do not add them to the System 1 feature vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inside_the_game.ingest.events import MatchEvent


@dataclass(frozen=True)
class XTVAEPSidecar:
    """Unfitted action-value notes. ``None`` means the model is not wired."""

    status: str
    xt: float | None
    vaep_offensive: float | None
    vaep_defensive: float | None
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "xt": self.xt,
            "vaep_offensive": self.vaep_offensive,
            "vaep_defensive": self.vaep_defensive,
            "detail": self.detail,
        }


def xt_vaep_sidecar(event: MatchEvent) -> XTVAEPSidecar:
    """Return the stub sidecar for one event. No socceraction import, no network."""
    del event  # The real rater will consume SPADL rows built from this event.
    return XTVAEPSidecar(
        status="stub",
        xt=None,
        vaep_offensive=None,
        vaep_defensive=None,
        detail=(
            "TODO: socceraction.xthreat.ExpectedThreat.rate and "
            "socceraction.vaep.VAEP. Explanation sidecar only."
        ),
    )
