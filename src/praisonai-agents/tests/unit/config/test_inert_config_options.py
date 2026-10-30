"""Config options that were accepted but never read must either work or fail loud.

Covers GuardrailConfig.on_fail, ToolConfig.output_max_lines/output_direction and
rerank=True on the Agent's RAG pipeline (issue #6042). No network calls.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config import GuardrailConfig, ToolConfig
from praisonaiagents.config.presets import GUARDRAIL_PRESETS


def _ok(task_output):
    return True, task_output


# --- GuardrailConfig.on_fail ------------------------------------------------

@pytest.mark.parametrize("on_fail", ["skip", "raise"])
def test_unsupported_on_fail_fails_loud(on_fail):
    with pytest.raises(ValueError, match="on_fail"):
        Agent(name="g", instructions="x", llm="gpt-4o-mini",
              guardrails=GuardrailConfig(validator=_ok, on_fail=on_fail))


def test_retry_on_fail_still_accepted():
    a = Agent(name="g", instructions="x", llm="gpt-4o-mini",
              guardrails=GuardrailConfig(validator=_ok, max_retries=2, on_fail="retry"))
    assert a.max_guardrail_retries == 2


def test_presets_carry_no_unimplemented_on_fail():
    assert all("on_fail" not in p for p in GUARDRAIL_PRESETS.values())
    a = Agent(name="g", instructions="x", llm="gpt-4o-mini",
              guardrails=["strict", {"validator": _ok}])
    assert a.max_guardrail_retries == 5
    assert a.guardrail is _ok


# --- ToolConfig.output_max_lines / output_direction --------------------------

def many_lines() -> str:
    """Return 200 short lines."""
    return "\n".join(f"line {i}" for i in range(200))


def _run_tool(cfg):
    a = Agent(name="t", instructions="x", llm="gpt-4o-mini", tools=[many_lines],
              tool_config=cfg, output="silent")
    return str(a.execute_tool("many_lines", {}))


def test_default_tool_config_does_not_cap_lines():
    out = _run_tool(ToolConfig())
    assert out.splitlines()[-1] == "line 199"
    assert out.count("\n") == 199


def test_output_max_lines_head():
    lines = _run_tool(ToolConfig(output_max_lines=5, output_direction="head")).splitlines()
    assert lines[:5] == [f"line {i}" for i in range(5)]
    assert "line 5" not in lines and "line 199" not in lines
    assert "200 lines total" in lines[5]


def test_output_max_lines_tail():
    lines = _run_tool(ToolConfig(output_max_lines=5, output_direction="tail")).splitlines()
    assert lines[-5:] == [f"line {i}" for i in range(195, 200)]
    assert "line 0" not in lines


def test_output_max_lines_both():
    lines = _run_tool(ToolConfig(output_max_lines=4)).splitlines()
    assert lines[:2] == ["line 0", "line 1"]
    assert lines[-2:] == ["line 198", "line 199"]
    assert len(lines) == 5  # 4 kept lines + marker


def test_output_direction_applies_to_char_cap():
    out = _run_tool(ToolConfig(output_limit=50, output_direction="head"))
    assert out.startswith("line 0\nline 1")
    assert "line 199" not in out


def short_lines() -> str:
    """Return ten one-character lines."""
    return "\n".join("abcdefghij")


def big_dict() -> dict:
    """Return a dict with one large field."""
    return {"body": "START" + "x" * 45000 + "END"}


def test_line_cap_applies_to_short_lines():
    a = Agent(name="t", instructions="x", llm="gpt-4o-mini", tools=[short_lines],
              tool_config=ToolConfig(output_max_lines=5, output_direction="head"), output="silent")
    lines = str(a.execute_tool("short_lines", {})).splitlines()
    assert lines[:5] == list("abcde")
    assert "j" not in lines


def test_output_direction_applies_to_dict_results():
    a = Agent(name="t", instructions="x", llm="gpt-4o-mini", tools=[big_dict],
              tool_config=ToolConfig(output_limit=40000, output_direction="head"), output="silent")
    out = str(a.execute_tool("big_dict", {}))
    assert "START" in out and "END" not in out


# --- rerank=True on Agent.rag -----------------------------------------------

class StubKnowledge:
    """Minimal Knowledge stand-in: search() returns hits worst-first."""

    def add(self, *a, **k):
        pass

    def search(self, query, **kw):
        return {"results": [
            {"memory": "bananas are yellow", "score": 0.9, "metadata": {"source": "a"}},
            {"memory": "paris is the capital of france", "score": 0.8, "metadata": {"source": "b"}},
        ]}


def _rag(retrieval_config=None):
    a = Agent(name="r", instructions="x", llm="gpt-4o-mini", knowledge=StubKnowledge(),
              retrieval_config=retrieval_config)
    return a.rag


def test_rerank_true_reranks_and_reports_it():
    pack = _rag({"rerank": True}).retrieve("capital of france")
    assert pack.metadata["reranked"] is True
    assert pack.context.index("paris") < pack.context.index("bananas")


def test_rerank_false_reports_not_reranked():
    rag = _rag()
    assert rag.reranker is None
    assert rag.retrieve("capital of france").metadata["reranked"] is False


def test_rerank_override_without_reranker_reports_false():
    assert _rag().retrieve("q", rerank=True).metadata["reranked"] is False


def test_rerank_model_leaves_reranking_to_backend():
    rag = _rag({"rerank": True, "rerank_model": "cohere/rerank-v3"})
    assert rag.reranker is None


def test_rerank_model_backend_reranking_reported():
    class BackendRerankKnowledge(StubKnowledge):
        config = {"reranker": {"default_rerank": True, "provider": "cohere"}}

    a = Agent(name="r", instructions="x", llm="gpt-4o-mini", knowledge=BackendRerankKnowledge(),
              retrieval_config={"rerank": True, "rerank_model": "cohere/rerank-v3"})
    assert a.rag.reranker is None
    assert a.rag.retrieve("q").metadata["reranked"] is True
    assert a.rag.retrieve("q", rerank=False).metadata["reranked"] is False


@pytest.mark.asyncio
async def test_rerank_true_async():
    pack = await _rag({"rerank": True}).aretrieve("capital of france")
    assert pack.metadata["reranked"] is True
    assert pack.context.index("paris") < pack.context.index("bananas")


def test_simple_reranker_accepts_search_result_items():
    from praisonaiagents.knowledge.models import SearchResultItem
    from praisonaiagents.rag.retriever import SimpleReranker
    hits = [SearchResultItem(text="bananas are yellow", score=0.9),
            SearchResultItem(text="paris is the capital of france", score=0.8)]
    ranked = SimpleReranker().rerank("capital of france", hits)
    assert ranked[0]["text"].startswith("paris")
