"""Real agentic test for PraisonAI Replay events (AGENTS.md section 9.4).

Runs a real two-agent AgentTeam and a real hand-off against gpt-4o-mini while
recording with a ContextListSink, then checks the trace a replay needs:
workflow, task, agent and LLM events (on both the OpenAI-client path and the
LiteLLM path), a real hand-off, one run id and parent links that resolve.

About five small model calls. Opt in with:

    RUN_REAL_KEY_TESTS=1 PRAISONAI_ALLOW_NETWORK=1 OPENAI_API_KEY=... \
        pytest tests/integration/test_replay_events_real.py -s
"""

import os

import pytest

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("RUN_REAL_KEY_TESTS") != "1"
        or not os.getenv("OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY") == "test-key",
        reason="Real model calls: set RUN_REAL_KEY_TESTS=1, PRAISONAI_ALLOW_NETWORK=1 and a real OPENAI_API_KEY",
    ),
]


def _types(events):
    return [e.event_type.value for e in events]


def test_team_and_handoff_record_a_replayable_trace():
    from praisonaiagents import Agent, Task
    from praisonaiagents.agents.agents import AgentTeam
    from praisonaiagents.trace.context_events import (
        ContextListSink, ContextTraceEmitter, trace_context,
    )

    sink = ContextListSink()
    emitter = ContextTraceEmitter(sink=sink, session_id="replay-real", enabled=True)

    # Researcher uses the OpenAI-client path, Writer the LiteLLM path.
    researcher = Agent(name="Researcher", instructions="Answer in one short sentence.",
                       llm="gpt-4o-mini")
    writer = Agent(name="Writer", instructions="Rewrite the given text as a headline of at most eight words.",
                   llm="openai/gpt-4o-mini")
    team = AgentTeam(
        agents=[researcher, writer],
        tasks=[
            Task(name="research", description="State one fact about the Moon.",
                 expected_output="One sentence", agent=researcher),
            Task(name="headline", description="Turn the fact into a headline.",
                 expected_output="A headline", agent=writer),
        ],
        output="silent",
    )

    billing = Agent(name="Billing", instructions="Reply exactly: Refund logged.", llm="gpt-4o-mini")
    triage = Agent(
        name="Triage",
        instructions=("You never answer yourself. For any request, immediately call the "
                      "transfer_to_billing tool, then repeat its answer."),
        llm="gpt-4o-mini",
        handoffs=[billing],
    )

    with trace_context(emitter):
        team_output = team.start()
        handoff_output = triage.start("Please refund order 7.")

    events = sink.get_events()
    print("\n--- team output ---\n", team_output)
    print("--- hand-off output ---\n", handoff_output)
    print("--- trace ---")
    for e in events:
        print(f"{e.sequence_num:>3} parent={e.parent_seq!s:>4} {e.event_type.value:<18} "
              f"{(e.agent_name or ''):<11} {e.node_id or ''}")

    assert team_output and handoff_output
    types = _types(events)
    for needed in ("workflow_start", "workflow_end", "task_start", "task_end",
                   "agent_start", "agent_end", "llm_request", "llm_response", "agent_handoff"):
        assert needed in types, needed

    start = next(e for e in events if e.event_type.value == "workflow_start")
    assert start.data["kind"] == "team" and start.data["graph"]["schema"] == "praisonai.graph/1"
    graph_ids = {n["id"] for n in start.data["graph"]["nodes"]}
    task_ends = [e for e in events if e.event_type.value == "task_end"]
    assert [e.data["status"] for e in task_ends] == ["completed", "completed"]
    assert {e.node_id for e in task_ends} == {"task:research", "task:headline"} <= graph_ids

    team_events = [e for e in events if e.run_id == team.run_id]
    assert team_events and team_events[0] is start

    # LLM activity on both paths, attributed to the right agent.
    responses = [e for e in events if e.event_type.value == "llm_response"]
    by_agent = {e.agent_name for e in responses}
    assert {"Researcher", "Writer", "Triage", "Billing"} <= by_agent
    writer_calls = [e for e in responses if e.agent_name == "Writer"]
    assert "gpt-4o-mini" in writer_calls[0].data.get("model")  # recorded by the LLM class
    assert writer_calls[0].prompt_tokens > 0 and writer_calls[0].completion_tokens > 0
    assert len([e for e in events if e.event_type.value == "llm_request" and e.agent_name == "Writer"]) == len(writer_calls)

    handoffs = [e for e in events if e.event_type.value == "agent_handoff"]
    assert any(h.data["from_agent"] == "Triage" and h.data["to_agent"] == "Billing"
               and h.data["kind"] == "handoff" for h in handoffs)

    # Every parent link resolves to an earlier event; sequence numbers are unique.
    seqs = [e.sequence_num for e in events]
    assert seqs == list(range(len(events)))
    for e in events:
        assert e.parent_seq is None or e.parent_seq < e.sequence_num
