"""Azure AI Foundry narration request. This module does not send it.

v1 narration is budgeted on ``gpt-4.1-mini``. The user message is the decision
JSON (probabilities, pass targets, carry path, scores) and nothing else: no
tracking dump, no video, no free-text match report.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


FOUNDRY_PROVIDER = "azure-ai-foundry"
FOUNDRY_DEPLOYMENT = "gpt-4.1-mini"

_NARRATION_KEYS = ("probabilities", "primary_pass", "secondary_pass", "carry")


def foundry_narration_request(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Chat body for Foundry ``gpt-4.1-mini``. ``sent`` is always false here."""
    payload = {key: decision.get(key) for key in _NARRATION_KEYS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    # Round-trip so a caller cannot slip a non-JSON blob into the user turn.
    json.loads(encoded)
    return {
        "provider": FOUNDRY_PROVIDER,
        "deployment": FOUNDRY_DEPLOYMENT,
        "sent": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Narrate a four-way soccer decision aid from the JSON object only. "
                    "Mention pass, shoot, dribble, and hold with the given probabilities. "
                    "Describe the primary pass, the secondary pass, and the carry path "
                    "using only target_id, path, and score. Do not invent players, clubs, "
                    "or events that are not in the JSON."
                ),
            },
            {"role": "user", "content": encoded},
        ],
    }
