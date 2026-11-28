"""A fallback turn must not change another turn's model."""
import threading
from types import SimpleNamespace

import pytest

from praisonaiagents import Agent
from praisonaiagents import llm
from praisonaiagents.llm import error_classifier
from praisonaiagents.hooks.types import HookEvent, HookResult
from praisonaiagents.config.feature_configs import ExecutionConfig


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("middleware", [False, True])
def test_fallback_does_not_change_concurrent_chat_model(monkeypatch, stream, middleware):
    started, release = threading.Event(), threading.Event()
    calls, results = [], {}

    class Dispatcher:
        def __init__(self, model):
            self.model = model

        def chat_completion(self, **kwargs):
            prompt = str([m for m in kwargs["messages"] if m.get("role") == "user"][-1]["content"])
            label = "A" if "task-a-marker" in prompt else "B"
            calls.append((label, self.model))
            if label == "A" and self.model == "gpt-primary":
                raise ConnectionError("synthetic failure")
            if label == "A" and self.model == "gpt-backup":
                started.set()
                assert release.wait(10)
            message = SimpleNamespace(content="served by " + self.model, tool_calls=None)
            response = SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                                       usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
            if label == "A" and self.model == "gpt-backup":
                kwargs["usage_callback"](response)
            return response

    monkeypatch.setattr(llm, "create_llm_dispatcher", lambda **kwargs: Dispatcher(kwargs["model"]))
    classification = SimpleNamespace(should_compress_context=False, should_rotate_credential=False,
                                     should_fallback_model=True, is_retryable=False, backoff_seconds=0,
                                     error_category="provider_down", user_message="unavailable")
    monkeypatch.setattr(error_classifier, "classify_llm_error", lambda *args, **kwargs: classification)
    agent = Agent(name="worker", instructions="work", model="gpt-primary", fallback_models=["gpt-backup"], output="silent", retry=False, rules=False, execution=ExecutionConfig(max_budget=1))
    hook_models, priced, estimates = [], [], []
    middleware_models = []
    if middleware:
        class Manager:
            def execute_model_call(self, request, call):
                middleware_models.append(request.model)
                return call(request)
        monkeypatch.setattr(agent, "_get_model_middleware_manager", lambda: Manager())
    for event in (HookEvent.BEFORE_LLM, HookEvent.AFTER_LLM):
        agent._hook_runner.registry.register_function(event, lambda data: hook_models.append((data.event_name, data.model)) or HookResult.allow())
    monkeypatch.setattr(agent, "_calculate_llm_cost", lambda *args, model=None, **kwargs: priced.append(model or agent.llm) or 0)
    monkeypatch.setattr(agent, "_estimate_min_call_cost", lambda *args, model=None: estimates.append(model or agent.llm) or 0)

    def first():
        results["A"] = agent.chat("task-a-marker", stream=stream)

    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert started.wait(10)
        results["B"] = agent.chat("task-b-marker", stream=stream)
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert results == {"A": "served by gpt-backup", "B": "served by gpt-primary"}
    assert calls[-2:] == [("A", "gpt-backup"), ("B", "gpt-primary")]
    assert agent.llm == "gpt-primary"
    assert (HookEvent.BEFORE_LLM, "gpt-backup") in hook_models
    assert (HookEvent.AFTER_LLM, "gpt-backup") in hook_models
    assert (HookEvent.AFTER_LLM, "gpt-primary") in hook_models
    assert priced.count("gpt-backup") >= 2 and "gpt-primary" in priced
    assert "gpt-backup" in estimates and "gpt-primary" in estimates
    if middleware:
        assert "gpt-backup" in middleware_models and "gpt-primary" in middleware_models


def test_multiple_sync_fallbacks_keep_original_model(monkeypatch):
    models = []

    class Dispatcher:
        def __init__(self, model):
            self.model = model

        def chat_completion(self, **kwargs):
            models.append(self.model)
            if self.model != "gpt-final":
                raise ConnectionError("synthetic failure")
            message = SimpleNamespace(content="ok", tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None)

    monkeypatch.setattr(llm, "create_llm_dispatcher", lambda **kwargs: Dispatcher(kwargs["model"]))
    classification = SimpleNamespace(should_compress_context=False, should_rotate_credential=False,
                                     should_fallback_model=True, is_retryable=False, backoff_seconds=0,
                                     error_category="provider_down", user_message="unavailable")
    monkeypatch.setattr(error_classifier, "classify_llm_error", lambda *args, **kwargs: classification)
    agent = Agent(name="worker", instructions="work", model="gpt-primary",
                  fallback_models=["gpt-backup", "gpt-final"], output="silent", retry=False, rules=False)
    assert agent.chat("go", stream=False) == "ok"
    assert models == ["gpt-primary", "gpt-backup", "gpt-final"]
    assert agent.llm == "gpt-primary"
