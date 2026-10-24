"""Hot paths use the shared error classifier, token estimator and atomic writer (#5838)."""

import json
import os

import pytest


class _E(Exception):
    def __init__(self, msg, status_code=None, headers=None):
        super().__init__(msg)
        self.status_code = status_code

        class _R:
            pass

        self.response = _R()
        self.response.headers = headers or {}


@pytest.fixture
def llm():
    from praisonaiagents.llm.llm import LLM

    inst = LLM.__new__(LLM)
    inst._rate_limiter = None
    inst._retry_delay = 1.0
    inst._max_retries = 3
    return inst


@pytest.mark.parametrize("error, kind", [
    (_E("max_tokens must be <= 4096, got 8500 (request req_5003abc)", 400), "format_error"),
    (_E("Error code: 401 - Incorrect credentials", 401), "auth"),
    (_E("Error code: 403 - region not supported", 403), "auth"),
    (_E("Service Error", 503), "overloaded"),
    (_E("Error code: 404 - The model `gpt-9` does not exist", 404), "model_not_found"),
    (_E("Error code: 400 - invalid image: credit card detected", 400), "format_error"),
    (_E("You exceeded your quota: insufficient quota", 429), "billing"),
    (_E("Your credit balance is too low", 400), "billing"),
    (_E("Rate limit reached for API key sk-...", 429), "rate_limit"),
    (Exception("503 service unavailable"), "overloaded"),
])
def test_status_code_drives_error_kind(llm, error, kind):
    assert llm.classify_error_kind(error) == kind


def test_retry_after_header_is_honoured(llm):
    err = _E("Error code: 429", 429, {"retry-after": "37"})
    assert llm._parse_retry_delay(err) == 37.0
    decision = llm.resolve_failover_decision(err, {"attempt": 1, "max_retries": 3})
    assert decision.action == "retry"
    assert decision.backoff_ms == 37000


def test_budget_estimators_count_cjk_densely():
    from praisonaiagents.context.tokens import estimate_tokens_heuristic
    from praisonaiagents.rag.budget import estimate_tokens

    text = "今天天气很好，我们一起去公园散步。" * 100
    assert estimate_tokens(text) == estimate_tokens_heuristic(text)
    assert estimate_tokens(text) > len(text)


def test_file_tracker_failed_save_keeps_previous_state(tmp_path):
    from praisonaiagents.knowledge.indexing import FileTracker

    state = str(tmp_path / "tracker.json")
    tracker = FileTracker(state)
    tracker._tracked = {"a.md": {"hash": "1", "mtime": 1, "memory_ids": ["m1"]}}
    tracker.save()
    tracker._tracked["b.md"] = {"hash": "2", "mtime": 2, "memory_ids": {"m3"}}
    with pytest.raises(TypeError):
        tracker.save()

    reloaded = FileTracker(state)
    reloaded.load()
    assert list(reloaded._tracked) == ["a.md"]


def test_permission_allowlist_failed_save_and_corrupt_load(tmp_path):
    from praisonaiagents.approval import PermissionAllowlist

    path = str(tmp_path / "perm.json")
    allowlist = PermissionAllowlist()
    allowlist.add_tool("shell", paths=["/tmp"])
    allowlist.save(path)
    allowlist._tools["shell"].allowed_paths = [object()]
    with pytest.raises(TypeError):
        allowlist.save(path)
    assert PermissionAllowlist.load(path).list_tools() == ["shell"]

    with open(path, "w") as f:
        f.write("{truncated")
    assert PermissionAllowlist.load(path).is_empty()
    assert not os.path.exists(path)


def test_file_index_save_is_atomic(tmp_path):
    from praisonaiagents.context.fast.index_manager import FileIndex

    index = FileIndex(workspace_path=str(tmp_path))
    assert index.save()
    with open(index.index_path) as f:
        assert json.load(f)["workspace"] == str(tmp_path)


def test_cjk_truncation_stays_within_token_budget():
    from praisonaiagents.rag.budget import DefaultBudgetEnforcer, TokenBudget, estimate_tokens
    from praisonaiagents.rag.compressor import ContextCompressor
    from praisonaiagents.rag.context import truncate_context

    cjk = "汉" * 1000
    out = truncate_context(cjk, 200)
    assert out.endswith("[Context truncated...]")
    assert estimate_tokens(out) <= 200

    budget = TokenBudget(model_max_tokens=1200, reserved_response_tokens=0)
    available = budget.dynamic_budget()
    kept = DefaultBudgetEnforcer().enforce([{"text": cjk}, {"text": cjk}], budget)
    assert sum(estimate_tokens(c["text"]) for c in kept) <= available
    assert kept[-1]["metadata"]["_truncated"]

    kept = ContextCompressor()._truncate_to_budget([{"text": cjk}], 200)
    assert estimate_tokens(kept[0]["text"]) <= 200
