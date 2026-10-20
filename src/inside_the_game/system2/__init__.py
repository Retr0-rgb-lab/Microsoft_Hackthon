"""System 2: explain and personalize. xT/VAEP stays on the sidecar."""

from inside_the_game.system2.explain import Explanation, ViewerProfile, explain
from inside_the_game.system2.local_llm import LocalRationale, load_local_llm
from inside_the_game.system2.sidecar import XTVAEPSidecar, sidecar_narrative, xt_vaep_sidecar

__all__ = [
    "Explanation",
    "LocalRationale",
    "ViewerProfile",
    "XTVAEPSidecar",
    "explain",
    "load_local_llm",
    "sidecar_narrative",
    "xt_vaep_sidecar",
]
