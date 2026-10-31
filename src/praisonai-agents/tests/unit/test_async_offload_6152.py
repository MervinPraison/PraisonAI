"""Regression tests for #6152: async APIs must not block the event loop."""
import asyncio
import contextvars
import time

from praisonaiagents.escalation.pipeline import EscalationPipeline
from praisonaiagents.escalation.types import EscalationStage, StageContext
from praisonaiagents.knowledge.query_engine import SubQuestionEngine
from praisonaiagents.rag.pipeline import RAG

BLOCK = 0.3
_request_var = contextvars.ContextVar("request_var", default=None)


async def _heartbeat_ticks(coro):
    ticks = 0
    done = False

    async def beat():
        nonlocal ticks
        while not done:
            await asyncio.sleep(0.02)
            ticks += 1

    task = asyncio.create_task(beat())
    try:
        result = await coro
    finally:
        done = True
        await task
    return result, ticks


class _BlockingAgent:
    def __init__(self):
        self.tools = ["a", "b", "c"]
        self.seen_tools = []

    def chat(self, prompt, tools=None):
        self.seen_tools.append(tools)
        time.sleep(BLOCK)
        return "ok"


def test_escalation_does_not_block_loop_or_mutate_agent_tools():
    agent = _BlockingAgent()
    pipeline = EscalationPipeline(agent=agent)
    pipeline._current_context = StageContext(stage=EscalationStage.HEURISTIC, prompt="")

    async def run():
        return await _heartbeat_ticks(
            asyncio.gather(
                pipeline._execute_heuristic("hi"),
                pipeline._execute_heuristic("there"),
            )
        )

    (r1, r2), ticks = asyncio.run(run())
    assert r1["success"] and r2["success"]
    assert ticks >= 5
    assert agent.tools == ["a", "b", "c"]
    assert all(t is not None for t in agent.seen_tools)


class _BlockingRAG(RAG):
    llm = None  # shadow the lazy LLM property

    def __init__(self):  # bypass heavy init
        from praisonaiagents.rag.models import RAGConfig
        self.config = RAGConfig()
        self.seen_var = None

    def _retrieve(self, **kwargs):
        self.seen_var = _request_var.get()
        time.sleep(BLOCK)
        return []

    def _rerank(self, question, results, rerank=None):
        return results

    def _build_context(self, results):
        return "", []

    def _build_prompt(self, question, context):
        return question


def test_rag_astream_offloads_retrieval_and_keeps_contextvars():
    rag = _BlockingRAG()

    async def consume():
        _request_var.set("req-1")
        return [c async for c in rag.astream("q")]

    chunks, ticks = asyncio.run(_heartbeat_ticks(consume()))
    assert chunks == ["LLM not available."]
    assert ticks >= 5
    assert rag.seen_var == "req-1"


def test_subquestion_aquery_offloads():
    engine = SubQuestionEngine()

    def slow_query(question, context=None, **kwargs):
        time.sleep(BLOCK)
        return "done"

    engine.query = slow_query
    result, ticks = asyncio.run(_heartbeat_ticks(engine.aquery("q")))
    assert result == "done"
    assert ticks >= 5


class _SyncStreamLLM:
    """Sync-only LLM (no ``astream``) whose ``stream()`` blocks between chunks."""

    def stream(self, messages, **kwargs):
        for tok in ("a", "b", "c"):
            time.sleep(BLOCK / 3)
            yield tok


def test_rag_astream_sync_fallback_offloads_and_retrieves_once():
    rag = _BlockingRAG()
    rag.llm = _SyncStreamLLM()
    calls = []
    orig_retrieve = rag._retrieve

    def counting_retrieve(**kwargs):
        calls.append(kwargs)
        return orig_retrieve(**kwargs)

    rag._retrieve = counting_retrieve

    async def consume():
        return [c async for c in rag.astream("q")]

    chunks, ticks = asyncio.run(_heartbeat_ticks(consume()))
    assert chunks == ["a", "b", "c"]
    assert len(calls) == 1
    assert ticks >= 10
