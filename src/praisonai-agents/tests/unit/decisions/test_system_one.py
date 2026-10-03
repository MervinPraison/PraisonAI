"""Unit tests for System One / Jev decision API client."""

from __future__ import annotations

import io
import json
from unittest import mock

import pytest

from praisonaiagents.decisions import (
    SystemOneResult,
    choice_question,
    is_decision_model,
    noul_question,
    resolve_system_one_base_url,
    score_question,
    system_one,
)
from praisonaiagents.local.capabilities import Cap, parse_ollama_capabilities


def test_is_decision_model():
    assert is_decision_model("nimble")
    assert is_decision_model("ollama/nimble")
    assert is_decision_model("tev1:0.8b")
    assert not is_decision_model("llama3.2")


def test_question_helpers():
    c = choice_question("Pick team", {"a": "A", "b": "B"})
    assert c["type"] == "choice"
    n = noul_question("Yes or no?")
    assert n["type"] == "noul"
    s = score_question("Rate", ["Low", "High"])
    assert s["type"] == "score" and len(s["criteria"]) == 2


def test_parse_ollama_decision_capability():
    caps = parse_ollama_capabilities({"capabilities": ["decision", "completion"]})
    assert Cap.SYSTEM_ONE in caps


def test_system_one_result_accessors():
    raw = {
        "model": "nimble",
        "answers": {
            "team": {"type": "choice", "choice": "billing", "confidence": 0.9},
            "refund": {"type": "noul", "noul": 0.99},
            "urgency": {"type": "score", "score": 0.5, "confidence": 0.1},
        },
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    r = SystemOneResult(model="nimble", answers=raw["answers"], usage=raw["usage"], raw=raw)
    assert r.choice("team") == "billing"
    assert r.noul("refund") == pytest.approx(0.99)
    assert r.score("urgency") == pytest.approx(0.5)
    assert r.confidence("team") == pytest.approx(0.9)


def test_system_one_http_mock():
    response_body = {
        "model": "nimble",
        "answers": {
            "team": {"type": "choice", "choice": "billing", "confidence": 0.92},
        },
        "usage": {"input_tokens": 10, "output_tokens": 1},
    }
    payload_holder = {}

    def fake_urlopen(req, timeout=0):
        payload_holder["url"] = req.full_url
        payload_holder["body"] = json.loads(req.data.decode())
        return io.BytesIO(json.dumps(response_body).encode())

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        result = system_one(
            state={"ticket": "refund please"},
            questions={"team": choice_question("Team?", {"billing": "pay"})},
            model="nimble",
            api_base="http://127.0.0.1:11434",
        )
    assert result.choice("team") == "billing"
    assert payload_holder["url"].endswith("/v1/systemone")
    assert payload_holder["body"]["model"] == "nimble"


def test_resolve_base_url_env(monkeypatch):
    monkeypatch.setenv("TYPESAFE_BASE_URL", "http://127.0.0.1:11434")
    assert resolve_system_one_base_url() == "http://127.0.0.1:11434"


def test_default_timeout_honours_explicit_120(monkeypatch):
    from praisonaiagents.decisions.system_one import _default_timeout

    monkeypatch.delenv("SYSTEM_ONE_TIMEOUT", raising=False)
    monkeypatch.delenv("OLLAMA_SYSTEM_ONE_TIMEOUT", raising=False)
    assert _default_timeout(120.0) == 120.0
    assert _default_timeout(5.0) == 5.0
    assert _default_timeout(None) == 120.0
    monkeypatch.setenv("SYSTEM_ONE_TIMEOUT", "30")
    assert _default_timeout(None) == 30.0
    assert _default_timeout(7.0) == 7.0


def test_validate_base_url_rejects_plain_http_remote():
    from praisonaiagents.decisions.system_one import _validate_base_url

    _validate_base_url("http://127.0.0.1:11434")
    _validate_base_url("http://localhost:11434")
    _validate_base_url("https://api.typesafe.ai")
    with pytest.raises(ValueError):
        _validate_base_url("http://evil.example.com")
    with pytest.raises(ValueError):
        _validate_base_url("ftp://127.0.0.1")


def test_typesafe_key_not_sent_to_ollama_host(monkeypatch):
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret-typesafe")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["auth"] = req.headers.get("Authorization")
        return io.BytesIO(json.dumps({"model": "nimble", "answers": {}}).encode())

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        system_one(
            state={"ticket": "x"},
            questions={"team": choice_question("Team?", {"billing": "pay"})},
            model="nimble",
        )
    assert captured["auth"] == "Bearer ollama"


def test_typesafe_key_sent_to_typesafe_base(monkeypatch):
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret-typesafe")
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["auth"] = req.headers.get("Authorization")
        return io.BytesIO(json.dumps({"model": "nimble", "answers": {}}).encode())

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        system_one(
            state={"ticket": "x"},
            questions={"team": choice_question("Team?", {"billing": "pay"})},
            model="nimble",
        )
    assert captured["auth"] == "Bearer secret-typesafe"


@pytest.mark.skipif(
    not __import__("os").environ.get("RUN_OLLAMA_DECISION_TESTS"),
    reason="Set RUN_OLLAMA_DECISION_TESTS=1 with Ollama 0.35+ and `ollama pull nimble`",
)
def test_system_one_live_ollama():
    result = system_one(
        state={"ticket": "I was charged twice. Please refund."},
        questions={
            "team": choice_question(
                "Which team?",
                {"billing": "Payments", "technical": "Bugs", "other": "Other"},
            ),
            "refund": noul_question("Does the customer ask for a refund?"),
        },
        model="nimble",
        timeout=900,
    )
    assert result.choice("team") in {"billing", "technical", "other"}
    assert result.noul("refund") is not None
