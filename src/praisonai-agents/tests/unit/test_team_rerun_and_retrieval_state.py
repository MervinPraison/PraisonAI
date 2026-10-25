"""Regression tests for #5980.

- A second AgentTeam.start()/astart() must re-execute tasks, not return stale output.
- RAG.retrieve(top_k=...) must not mutate the shared RAGConfig.
- SmartRetriever must over-fetch before post-filtering, fail closed on a bad
  path_filter regex, and not share store errors across calls via instance state.
"""

import asyncio
import threading

import pytest

from praisonaiagents import Agent, AgentTeam, Task
from praisonaiagents.knowledge.query_engine import SubQuestionEngine
from praisonaiagents.rag.models import RAGConfig
from praisonaiagents.rag.pipeline import RAG
from praisonaiagents.rag.retriever import SmartRetriever


def _team():
    calls = []
    agent = Agent(name="a", instructions="x", llm="gpt-4o-mini")

    def chat(prompt, **kw):
        calls.append(prompt)
        return f"answer#{len(calls)}"

    async def achat(prompt, **kw):
        return chat(prompt)

    agent.chat = chat
    agent.achat = achat
    task = Task(name="t1", description="Summarise the ticket", expected_output="e", agent=agent)
    return AgentTeam(agents=[agent], tasks=[task], process="sequential"), task, calls


def test_second_start_reexecutes_and_drops_previous_content():
    team, task, calls = _team()
    assert team.start("ticket A", output="silent") == "answer#1"
    assert team.start("ticket B", output="silent") == "answer#2"
    assert len(calls) == 2
    assert task.context == ["ticket B"]


def test_second_astart_reexecutes():
    team, _, calls = _team()

    async def run():
        return await team.astart(), await team.astart()

    assert asyncio.run(run()) == ("answer#1", "answer#2")
    assert len(calls) == 2


def test_restored_checkpoint_is_resumed_not_reset():
    team, task, calls = _team()
    team.start(output="silent")
    snapshot = team._serialisable_task_state()
    assert team._restore_serialised_task_state(snapshot) == 1
    team.start(output="silent")
    assert len(calls) == 1  # completed task restored -> skipped
    assert task.status == "completed"


def test_rerun_keeps_caller_defined_task_variables():
    team, task, calls = _team()
    task.description = "Summarise {{ticket}}"
    task.variables = {"ticket": "T-1"}
    team.start(output="silent")
    team.start(output="silent")
    assert task.variables == {"ticket": "T-1"}
    assert all("T-1" in str(p) and "{{ticket}}" not in str(p) for p in calls)


def test_rerun_repropagates_current_team_variables():
    team, task, calls = _team()
    task.description = "Summarise {{ticket}}"
    team.variables = {"ticket": "T-1"}
    team.start(output="silent")
    team.variables = {"ticket": "T-2"}
    team.start(output="silent")
    assert "T-2" in str(calls[1])


def test_fresh_run_after_resume_drops_earlier_content():
    team, task, calls = _team()
    team.start("ticket A", output="silent")
    team._restore_serialised_task_state(team._serialisable_task_state())
    team.start(output="silent")  # resume: completed task skipped
    team.start("ticket B", output="silent")
    assert task.context == ["ticket B"]


def test_rag_retrieve_override_does_not_mutate_config():
    # Hold the top_k=1 call inside search() until a default call has finished,
    # so the default call is guaranteed to run while the override is active.
    override_in_search = threading.Event()
    default_done = threading.Event()

    class Knowledge:
        def search(self, query, **kw):
            if query == "override":
                override_in_search.set()
                default_done.wait(2)
            return [{"text": f"d{i}", "score": 1.0, "metadata": {}} for i in range(20)]

    rag = RAG(knowledge=Knowledge(), config=RAGConfig(top_k=5))
    out = {}
    ta = threading.Thread(target=lambda: out.setdefault("a", rag.retrieve("override", top_k=1)))
    ta.start()
    assert override_in_search.wait(2)
    out["b"] = rag.retrieve("default")
    default_done.set()
    ta.join()
    assert rag.config.top_k == 5
    assert out["a"].metadata["top_k"] == 1
    assert out["b"].metadata["top_k"] == 5


class _MixedStore:
    def search(self, query, limit=5, **kw):
        docs = [{"text": f"p{i}", "metadata": {"filename": f"p{i}.pdf"}, "score": 1 - i / 100}
                for i in range(10)]
        docs += [{"text": f"m{i}", "metadata": {"filename": f"m{i}.md"}, "score": 0.5}
                 for i in range(3)]
        return docs[:limit]


def test_filters_over_fetch_before_truncation():
    result = SmartRetriever(_MixedStore()).retrieve("q", top_k=5, include_glob=["*.md"])
    assert [c["text"] for c in result.chunks] == ["m0", "m1", "m2"]


def test_invalid_path_filter_fails_closed():
    with pytest.raises(ValueError):
        SmartRetriever(_MixedStore()).retrieve("q", path_filter="([unclosed")


def test_store_error_is_not_shared_across_concurrent_calls():
    # Hold the good call inside search() until the failing call has fully
    # recorded its error, the interleaving that leaked it via instance state.
    good_in_search = threading.Event()
    bad_done = threading.Event()

    class Store:
        def search(self, query, **kw):
            if query == "bad":
                raise RuntimeError("down")
            good_in_search.set()
            bad_done.wait(2)
            return [{"text": "ok", "metadata": {}, "score": 1.0}]

    retriever = SmartRetriever(Store())
    out = {}
    tg = threading.Thread(target=lambda: out.setdefault("good", retriever.retrieve("good")))
    tg.start()
    assert good_in_search.wait(2)
    out["bad"] = retriever.retrieve("bad")
    bad_done.set()
    tg.join()
    assert out["bad"].retrieval_failed is True
    assert out["good"].retrieval_failed is False


def test_sub_question_engine_accepts_smart_retriever():
    result = SubQuestionEngine().query("what is m?", retriever=SmartRetriever(_MixedStore()))
    assert result.sources
