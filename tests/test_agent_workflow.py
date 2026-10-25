"""The four-tool decision graph, run on the Microsoft Agent Framework."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("agent_framework", reason="pip install inside-the-game[agent]")

from inside_the_game.features.from_tracking import load_synth_match
from inside_the_game.system1.agent_workflow import (
    TOOL_NAMES,
    run_decision_workflow,
)
from inside_the_game.system1.orchestrator import run_decision_tools
from inside_the_game.system2.foundry import foundry_narration_request


@pytest.fixture(scope="module")
def match():
    return load_synth_match()


@pytest.fixture(scope="module")
def decision_event(match):
    for event in match.events:
        if event.get("type") == "decision_point":
            return event
    raise AssertionError("the sample has no decision point")


def test_tools_run_in_order(match, decision_event):
    result = run_decision_workflow(match, decision_event)
    assert [entry["tool"] for entry in result["tools"]] == list(TOOL_NAMES)


def test_the_graph_agrees_with_the_in_process_path(match, decision_event):
    workflow_result = run_decision_workflow(match, decision_event)
    in_process = run_decision_tools(match, decision_event)
    assert workflow_result["decision"] == in_process["decision"]
    assert workflow_result["completion"] == in_process["completion"]


def test_the_decision_carries_four_probabilities(match, decision_event):
    result = run_decision_workflow(match, decision_event)
    probabilities = result["decision"]["probabilities"]
    assert set(probabilities) == {"pass", "shoot", "dribble", "hold"}
    assert sum(probabilities.values()) == pytest.approx(1.0, abs=1e-6)


def test_the_offline_narration_is_built_but_not_sent(match, decision_event):
    result = run_decision_workflow(match, decision_event)
    narration = result["narration"]
    assert narration["sent"] is False
    assert narration["deployment"] == "gpt-4.1-mini"
    assert result["degraded"] == []


def test_a_narrator_is_called_and_its_payload_is_kept(match, decision_event):
    seen: list[dict] = []

    def narrator(decision):
        seen.append(decision)
        return {"provider": "test", "deployment": "test-model", "sent": True, "text": "ok"}

    result = run_decision_workflow(match, decision_event, narrator=narrator)
    assert len(seen) == 1
    # The narrator sees the whole decision. The Foundry request body is what
    # narrows it to the four narration keys.
    assert {"probabilities", "primary_pass", "secondary_pass", "carry"} <= set(seen[0])
    body = foundry_narration_request(seen[0])
    assert body["sent"] is False
    assert set(json.loads(body["messages"][1]["content"])) == {
        "probabilities",
        "primary_pass",
        "secondary_pass",
        "carry",
    }
    assert result["narration"]["sent"] is True
    assert result["narration"]["text"] == "ok"


def test_a_failing_narrator_degrades_without_losing_the_decision(match, decision_event):
    def narrator(decision):
        raise RuntimeError("no route to the endpoint")

    result = run_decision_workflow(match, decision_event, narrator=narrator)
    assert result["decision"] is not None
    assert result["completion"] is not None
    assert result["narration"]["sent"] is False
    assert any(entry.startswith("narrate:") for entry in result["degraded"])
