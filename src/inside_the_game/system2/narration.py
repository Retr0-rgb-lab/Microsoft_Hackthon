"""A narrator that actually calls a Responses API endpoint.

Azure AI Foundry serves the OpenAI Responses API shape, so the same client
reaches an OpenAI deployment and an Azure AI Foundry deployment. The base URL
is the only difference:

    https://api.openai.com/v1
    https://<resource>.openai.azure.com/openai/v1

The request body is the one ``foundry_narration_request`` builds: the four
probabilities, the two pass targets and the carry path, and nothing else.

    from inside_the_game.system2.narration import responses_narrator

    narrate = responses_narrator(base_url, "gpt-4.1-mini", api_key)
    result = run_decision_workflow(match, event, narrator=narrate)
"""

import json
import urllib.error
import urllib.request
from typing import Any

from inside_the_game.system2.foundry import (
    FOUNDRY_DEPLOYMENT,
    FOUNDRY_PROVIDER,
    foundry_narration_request,
)

DEFAULT_TIMEOUT = 30


class NarrationError(RuntimeError):
    """The narration request could not be completed."""


def _extract_text(payload: dict[str, Any]) -> str:
    """Pull the assistant text out of a Responses API result."""
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in (None, "output_text"):
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    if chunks:
        return "".join(chunks)
    raise NarrationError("the response carried no output text")


def responses_narrator(
    base_url: str,
    model: str = FOUNDRY_DEPLOYMENT,
    api_key: str = "",
    timeout: int = DEFAULT_TIMEOUT,
):
    """Build a narrator that posts the decision JSON to a Responses API."""
    endpoint = base_url.rstrip("/") + "/responses"

    def narrate(decision: dict[str, Any]) -> dict[str, Any]:
        built = foundry_narration_request(decision)
        body = {
            "model": model,
            "input": built["messages"],
            "text": {"format": {"type": "json_object"}},
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            # Azure AI Foundry authenticates with the api-key header. OpenAI
            # authenticates with a bearer token. Sending both keeps one client
            # working against either deployment.
            headers["api-key"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise NarrationError(f"{endpoint} returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise NarrationError(f"{endpoint} could not be reached: {exc.reason}") from exc
        provider = FOUNDRY_PROVIDER if "azure" in base_url else "openai"
        return {
            "provider": provider,
            "deployment": model,
            "sent": True,
            "text": _extract_text(payload),
            "response_id": payload.get("id"),
            "usage": payload.get("usage"),
        }

    return narrate
