"""System 2 rationale is offline. The local model hook stays off."""

from __future__ import annotations

import socket
import urllib.request

import pytest

from inside_the_game.ingest.loader import load_events
from inside_the_game.labels import ACTION_LABELS
from inside_the_game.pipeline import run_mvp
from inside_the_game.system1.policy import SoftmaxActionPolicy
from inside_the_game.system2.explain import ViewerProfile, explain
from inside_the_game.system2.local_llm import load_local_llm


def test_explain_returns_rationale_for_synthetic_states() -> None:
    policy = SoftmaxActionPolicy()
    events = load_events()
    assert len(events) >= 2
    for synthetic in events:
        synthetic_text = explain(synthetic, policy.predict(synthetic))
        _assert_offline_rationale(synthetic_text.text)
        assert synthetic_text.source == "template"
        assert synthetic_text.event_id == synthetic.event_id
        assert "TODO" in synthetic_text.text
        assert synthetic_text.sidecar.xt is None
        assert synthetic.player in synthetic_text.text


def test_default_path_does_not_call_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"network call args={args!r} kwargs={kwargs!r}")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    monkeypatch.setenv("INSIDE_THE_GAME_LOCAL_LLM", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "not-used")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "not-used")

    assert load_local_llm() is None
    event = load_events()[0]
    explanation = explain(event, SoftmaxActionPolicy().predict(event))
    assert explanation.source == "template"
    assert explanation.text.strip()
    frames = run_mvp()
    assert frames
    assert all(frame.explanation.source == "template" for frame in frames)
    assert all(frame.overlay.explanation == frame.explanation.text for frame in frames)


def test_local_llm_hook_is_off_unless_the_caller_passes_one() -> None:
    assert load_local_llm() is None
    event = load_events()[0]
    distribution = SoftmaxActionPolicy().predict(event)
    calls = {"n": 0}

    class Spy:
        def rationale(self, event: object, distribution: object, profile: object) -> str:
            calls["n"] += 1
            return "Local note covering pass, shoot, dribble, and hold."

    default = explain(event, distribution)
    assert calls["n"] == 0
    assert default.source == "template"
    assert "Local note" not in default.text

    hooked = explain(event, distribution, local_llm=Spy())
    assert calls["n"] == 1
    assert hooked.source == "local_llm"
    assert hooked.text == "Local note covering pass, shoot, dribble, and hold."

    class Blank:
        def rationale(self, event: object, distribution: object, profile: object) -> str:
            return "  "

    fallback = explain(event, distribution, local_llm=Blank())
    assert fallback.source == "template"
    assert fallback.text.strip()

    fan = explain(event, distribution, ViewerProfile("fan"))
    assert fan.text.startswith("For a match viewer: ")
    assert fan.profile_role == "fan"


def _assert_offline_rationale(text: str) -> None:
    assert text.strip()
    lowered = text.lower()
    for label in ACTION_LABELS:
        assert label in lowered
    assert "optimal" not in lowered
    assert "best" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered
