import asyncio
from types import SimpleNamespace

import pytest

from praisonaiagents.context.budgeter import context_window_usage, get_model_limit, verified_context_window
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.mark.parametrize("model", ["gpt-5", "gpt-5-2025-08-07", "openai/gpt-5-mini", "gpt-5-nano"])
def test_official_full_window(model):
    assert context_window_usage(200000, model, endpoint="https://api.openai.com/v1/") == {"used": 200000, "limit": 400000, "percent": 50}


@pytest.mark.parametrize("endpoint", [None, "https://custom.example/v1", "https://api.openai.com.evil/v1", "http://api.openai.com/v1", "https://api.openai.com/v1?x=1", "https://api.openai.com:444/v1", "https://evil@api.openai.com/v1", "https://[bad"])
def test_missing_or_untrusted_endpoint_is_unavailable(endpoint):
    assert verified_context_window("gpt-5", endpoint=endpoint) is None


def test_unverified_alias_and_provider_are_unavailable():
    assert verified_context_window("other/gpt-5", endpoint="https://api.openai.com/v1") is None
    assert verified_context_window("gpt-5-custom", endpoint="https://api.openai.com/v1") is None


def test_budget_lookup_keeps_litellm_input_cap(monkeypatch):
    from praisonaiagents.context import budgeter
    monkeypatch.setattr(budgeter, "_litellm_model_info", lambda _: {"max_input_tokens": 272000})
    assert get_model_limit("gpt-5") == 272000


def test_actual_request_provenance_is_task_local_and_follows_fallback():
    async def run():
        c = OpenAIClient(api_key="test")
        class Completions:
            async def create(self, **params):
                await asyncio.sleep(0)
                return SimpleNamespace(model=params["model"])
        class Responses:
            async def create(self, **params):
                raise RuntimeError("force fallback")
        client = SimpleNamespace(base_url="https://api.openai.com/v1/", chat=SimpleNamespace(completions=Completions()), responses=Responses())
        c._async_client = client
        c._async_client_owned = False
        c._use_responses_api = lambda _: True
        c._build_responses_input = lambda *a, **k: {}
        seen = {}
        async def one(model):
            await c.acreate_completion([], model=model, _context_provenance_callback=lambda m, e: seen.update({model: (m, e)}))
        await asyncio.gather(one("gpt-5"), one("gpt-5-mini"))
        assert seen == {"gpt-5": ("gpt-5", "https://api.openai.com/v1/"), "gpt-5-mini": ("gpt-5-mini", "https://api.openai.com/v1/")}
    asyncio.run(run())


def test_status_reports_only_effective_verified_endpoint():
    import io
    from praisonaiagents.output.status import StatusOutput
    output = io.StringIO()
    status = StatusOutput(file=output, use_color=False, show_metrics=True, show_timestamps=False)
    status.llm_end(model="gpt-5", tokens_in=200000, context_model="gpt-5-2025-08-07", context_endpoint="https://api.openai.com/v1/")
    assert "context 50% (200000/400000)" in output.getvalue()
    output.seek(0); output.truncate()
    status.llm_end(model="gpt-5", tokens_in=200000, context_model="gpt-5", context_endpoint="https://custom.example/v1")
    assert "context " not in output.getvalue()
    output.seek(0); output.truncate()
    status.llm_end(model="gpt-5", tokens_in=200000)
    assert "context " not in output.getvalue()


def test_explicit_budget_override_remains_unchanged():
    from praisonaiagents.context.budgeter import ContextBudgeter
    budget = ContextBudgeter(model="gpt-5", model_limit=100000, output_reserve=10000)
    assert budget.model_limit == 100000
    assert budget.usable == 90000
    assert budget.allocate().usable == 90000


def test_native_tool_loop_delivers_request_scoped_provenance(monkeypatch):
    import praisonaiagents.main as main
    events = []
    monkeypatch.setattr(main, "execute_sync_callback", lambda kind, **kw: events.append((kind, kw)))
    async def run():
        c = OpenAIClient(api_key="test")
        c._use_responses_api = lambda _: False
        c._track_token_usage = lambda *a, **kw: None
        class Completions:
            async def create(self, **params):
                message = SimpleNamespace(content="done", tool_calls=None)
                return SimpleNamespace(model="gpt-5-2025-08-07", choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=SimpleNamespace(prompt_tokens=200000, completion_tokens=2))
        c._async_client = SimpleNamespace(base_url="https://api.openai.com/v1/", chat=SimpleNamespace(completions=Completions()))
        c._async_client_owned = False
        await c.achat_completion_with_tools([{"role": "user", "content": "hi"}], model="gpt-5", stream=False, verbose=False)
    asyncio.run(run())
    end = [kw for kind, kw in events if kind == "llm_end"][0]
    assert end["context_model"] == "gpt-5-2025-08-07"
    assert end["context_endpoint"] == "https://api.openai.com/v1"


@pytest.mark.parametrize("metadata", [None, {"max_input_tokens": 272000, "max_output_tokens": 128000}])
def test_occupancy_does_not_depend_on_litellm_input_cap(monkeypatch, metadata):
    from praisonaiagents.context import budgeter
    monkeypatch.setattr(budgeter, "_litellm_model_info", lambda _: metadata)
    assert context_window_usage(200000, "gpt-5", endpoint="https://api.openai.com/v1")["percent"] == 50


def test_normalized_official_endpoint():
    assert verified_context_window("gpt-5", endpoint="https://API.OPENAI.COM:443/v1/") == 400000
