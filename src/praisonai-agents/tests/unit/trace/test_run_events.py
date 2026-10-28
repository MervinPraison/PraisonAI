"""PraisonAI Replay: run-structure events on the context trace (schema 1.1).

A replay can only explain a run if the trace says which run, which task or
step, which graph node and which enclosing span every event belongs to, and if
concurrent branches cannot scramble that. These cover the event schema, the
span/branch bookkeeping, and every place the SDK now records what happened:
hand-offs, team tasks, flow steps, manager decisions, approvals and the
LiteLLM call path. No test here reaches a model.
"""

import asyncio
import time
import types

import pytest

from praisonaiagents.trace.context_events import (
    ContextEvent,
    ContextEventType,
    ContextListSink,
    ContextTraceEmitter,
    _run_scope,
    copy_context_to_callable,
    get_context_emitter,
    trace_context,
)


@pytest.fixture
def recorder():
    """A live emitter installed for the test; yields its sink."""
    sink = ContextListSink()
    emitter = ContextTraceEmitter(sink=sink, session_id="replay-test", enabled=True)
    with trace_context(emitter):
        yield sink


def _types(sink):
    return [e.event_type.value for e in sink.get_events()]


def _of(sink, event_type):
    return [e for e in sink.get_events() if e.event_type.value == event_type]


def _by_seq(sink):
    return {e.sequence_num: e for e in sink.get_events()}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_schema_version_is_1_1(self):
        from praisonaiagents.trace.context_events import CONTEXT_SCHEMA_VERSION
        assert CONTEXT_SCHEMA_VERSION == "1.1"

    def test_new_fields_round_trip(self):
        event = ContextEvent(
            event_type=ContextEventType.TASK_START,
            timestamp=1.5,
            session_id="s",
            run_id="run-1",
            parent_seq=3,
            node_id="task:research",
        )
        data = event.to_dict()
        assert data["run_id"] == "run-1"
        assert data["parent_seq"] == 3
        assert data["node_id"] == "task:research"
        back = ContextEvent.from_dict(data)
        assert (back.run_id, back.parent_seq, back.node_id) == ("run-1", 3, "task:research")
        assert back.event_type == ContextEventType.TASK_START

    def test_new_fields_are_omitted_when_none(self):
        data = ContextEvent(ContextEventType.SESSION_START, 1.0, "s").to_dict()
        for key in ("run_id", "parent_seq", "node_id", "branch_id"):
            assert key not in data

    def test_a_1_0_event_still_loads(self):
        legacy = {
            "schema_version": "1.0",
            "event_type": "agent_start",
            "timestamp": 10.0,
            "session_id": "old",
            "agent_name": "Writer",
            "sequence_num": 4,
            "messages_count": 0,
            "tokens_used": 0,
            "tokens_budget": 0,
            "data": {"role": "w"},
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        }
        event = ContextEvent.from_dict(legacy)
        assert event.event_type == ContextEventType.AGENT_START
        assert event.sequence_num == 4
        assert event.run_id is None and event.parent_seq is None and event.node_id is None

    def test_an_unknown_event_type_keeps_its_raw_value(self):
        event = ContextEvent.from_dict({"event_type": "hologram_beamed", "session_id": "s"})
        assert event.event_type == "hologram_beamed"
        assert event.event_type.value == "hologram_beamed"  # Enum-style callers still work
        assert event.to_dict()["event_type"] == "hologram_beamed"

    def test_control_a_known_event_type_is_still_the_enum(self):
        event = ContextEvent.from_dict({"event_type": "tool_call_end", "session_id": "s"})
        assert event.event_type is ContextEventType.TOOL_CALL_END

    def test_new_event_types_have_contract_values(self):
        assert {t.value for t in ContextEventType} >= {
            "workflow_start", "workflow_end", "task_start", "task_end",
            "step_start", "step_end", "approval_requested", "approval_decided",
        }


# ---------------------------------------------------------------------------
# Spans, sequence numbers, branches, run ids
# ---------------------------------------------------------------------------


class TestSpans:
    def test_parent_seq_nests_and_end_points_at_its_start(self, recorder):
        emitter = get_context_emitter()
        emitter.workflow_start("team", "t", "sequential")        # 0
        emitter.task_start("research", node_id="task:research")  # 1
        emitter.agent_start("Writer")                             # 2
        emitter.message_added("Writer", "user", "hi", 1, 1)       # 3 point
        emitter.agent_end("Writer")                               # 4
        emitter.task_end("research", "completed", node_id="task:research")  # 5
        emitter.workflow_end()                                    # 6
        e = _by_seq(recorder)
        assert e[0].parent_seq is None
        assert e[1].parent_seq == 0
        assert e[2].parent_seq == 1
        assert e[3].parent_seq == 2
        assert e[4].parent_seq == 2
        assert e[5].parent_seq == 1
        assert e[6].parent_seq == 0

    def test_a_start_left_open_is_closed_by_its_parent_end(self, recorder):
        emitter = get_context_emitter()
        emitter.workflow_start("team", "t", "sequential")
        emitter.tool_call_start("Writer", "search")  # never ended (exception path)
        emitter.workflow_end()
        emitter.message_added("x", "user", "after", 1, 1)
        assert recorder.get_events()[-1].parent_seq is None

    def test_spans_of_another_emitter_do_not_leak(self, recorder):
        other_sink = ContextListSink()
        other = ContextTraceEmitter(sink=other_sink, session_id="other")
        get_context_emitter().workflow_start("team", "t", "sequential")
        other.message_added("x", "user", "hi", 1, 1)
        assert other_sink.get_events()[0].parent_seq is None

    def test_run_scope_stamps_run_id_and_nested_scopes_inherit(self, recorder):
        emitter = get_context_emitter()
        with _run_scope("outer") as outer:
            with _run_scope("inner") as inner:
                emitter.message_added("a", "user", "x", 1, 1)
        emitter.message_added("a", "user", "y", 1, 1)
        assert outer == inner == "outer"
        first, second = recorder.get_events()
        assert first.run_id == "outer"
        assert second.run_id is None

    def test_eight_concurrent_branches_keep_their_own_branch_and_parent(self, recorder):
        import concurrent.futures

        emitter = get_context_emitter()
        emitter.step_start("parallel", pattern="parallel", node_id="step:parallel")
        fork_seq = recorder.get_events()[-1].sequence_num

        def branch(idx):
            trace = get_context_emitter()
            trace.set_branch(f"parallel_{idx}")
            try:
                for _ in range(20):
                    trace.step_start(f"b{idx}", node_id=f"step:b{idx}")
                    time.sleep(0.0005)
                    trace.step_end(f"b{idx}", "completed", node_id=f"step:b{idx}")
            finally:
                trace.clear_branch()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(copy_context_to_callable(lambda i=i: branch(i))) for i in range(8)]
            for future in futures:
                future.result()
        emitter.step_end("parallel", "completed", node_id="step:parallel")

        events = recorder.get_events()
        seqs = [e.sequence_num for e in events]
        assert seqs == sorted(seqs) == list(range(len(events)))  # unique, append order
        by_seq = {e.sequence_num: e for e in events}
        for e in events[1:-1]:
            idx = int(e.node_id.split(":b")[1])
            assert e.branch_id == f"parallel_{idx}"
            if e.event_type == ContextEventType.STEP_START:
                assert e.parent_seq == fork_seq
            else:
                start = by_seq[e.parent_seq]
                assert start.node_id == e.node_id and start.branch_id == e.branch_id
        assert events[-1].parent_seq == fork_seq
        assert events[-1].branch_id is None


# ---------------------------------------------------------------------------
# AgentFlow steps
# ---------------------------------------------------------------------------


def _handler(name, output=None):
    def run(ctx):
        return output if output is not None else name
    run.__name__ = name
    return run


class TestFlowSteps:
    def test_flow_records_workflow_and_step_events_with_graph(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow

        flow = AgentFlow(name="demo", steps=[_handler("draft"), _handler("polish")])
        flow.run("go")
        types_ = _types(recorder)
        assert types_[0] == "workflow_start" and types_[-1] == "workflow_end"
        start = recorder.get_events()[0]
        assert start.data["kind"] == "flow" and start.data["name"] == "demo"
        assert start.data["graph"]["schema"] == "praisonai.graph/1"
        steps = _of(recorder, "step_start")
        assert [s.node_id for s in steps] == ["step:draft", "step:polish"]
        assert all(s.parent_seq == start.sequence_num for s in steps)
        run_ids = {e.run_id for e in recorder.get_events()}
        assert len(run_ids) == 1 and None not in run_ids
        assert [e.data["status"] for e in _of(recorder, "step_end")] == ["completed", "completed"]
        assert recorder.get_events()[-1].data["status"] == "completed"

    def test_parallel_with_eight_branches(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow, Parallel

        def slow(name):
            def run(ctx):
                time.sleep(0.002)
                return name
            run.__name__ = name
            return run

        flow = AgentFlow(steps=[Parallel(steps=[slow(f"b{i}") for i in range(8)])])
        flow.run("go")
        events = recorder.get_events()
        seqs = [e.sequence_num for e in events]
        assert seqs == list(range(len(events)))
        parallel = [e for e in _of(recorder, "step_start") if e.data.get("pattern") == "parallel"]
        assert len(parallel) == 1 and parallel[0].node_id == "step:parallel"
        branches = [e for e in _of(recorder, "step_start") if e.node_id != "step:parallel"]
        assert sorted(e.branch_id for e in branches) == sorted(f"parallel_{i}" for i in range(8))
        assert {e.parent_seq for e in branches} == {parallel[0].sequence_num}
        by_seq = _by_seq(recorder)
        for end in _of(recorder, "step_end"):
            assert by_seq[end.parent_seq].node_id == end.node_id
        assert {e.node_id for e in branches} == {f"step:b{i}" for i in range(8)}

    def test_route_and_if_record_the_branch_taken(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow, If, Route

        flow = AgentFlow(steps=[
            _handler("classify", "this is urgent"),
            Route(routes={"urgent": [_handler("page")], "default": [_handler("queue")]}),
            If(condition="{{missing}} == yes", then_steps=[_handler("a")], else_steps=[_handler("b")]),
        ])
        flow.run("go")
        ends = {e.node_id: e for e in _of(recorder, "step_end")}
        assert ends["step:route"].data["route"] == "urgent"
        assert ends["step:if"].data["route"] == "false"
        assert "step:page" in ends and "step:queue" not in ends
        assert "step:b" in ends and "step:a" not in ends

    def test_one_step_object_at_two_positions_keeps_each_node_id(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow

        review = _handler("review")
        flow = AgentFlow(steps=[review, _handler("draft"), review])
        flow.run("go")
        expected = ["step:review", "step:draft", "step:review#2"]
        assert [e.node_id for e in _of(recorder, "step_start")] == expected
        assert [e.node_id for e in _of(recorder, "step_end")] == expected
        nodes = {n["id"] for n in recorder.get_events()[0].data["graph"]["nodes"]}
        assert set(expected) <= nodes

    def test_one_step_object_at_two_positions_inside_a_loop(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow, Loop

        review = _handler("review")
        flow = AgentFlow(steps=[Loop(steps=[review, _handler("draft"), review], over="items")],
                         variables={"items": ["a", "b"]})
        flow.run("go")
        leaf = ["step:review", "step:draft", "step:review#2"]
        for kind in ("step_start", "step_end"):
            ids = [e.node_id for e in _of(recorder, kind) if e.node_id != "step:loop"]
            assert ids == leaf * 2  # stable across iterations

    def test_one_step_object_in_both_if_branches(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow, If

        review = _handler("review")
        flow = AgentFlow(steps=[review, If(condition="{{missing}} == yes", then_steps=[review], else_steps=[review])])
        flow.run("go")
        ids = [e.node_id for e in _of(recorder, "step_end") if e.node_id != "step:if"]
        assert ids == ["step:review", "step:review#3"]

    def test_one_pattern_object_at_two_positions_keeps_each_node_id(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow, If, Loop

        branch = If(condition="{{missing}} == yes", then_steps=[_handler("skip")], else_steps=[_handler("review")])
        loop = Loop(steps=[branch, branch], over="items")
        flow = AgentFlow(steps=[branch, branch, loop], variables={"items": ["a"]})
        flow.run("go")
        ends = [e.node_id for e in _of(recorder, "step_end")]
        nodes = {n["id"] for n in recorder.get_events()[0].data["graph"]["nodes"]}
        assert set(ends) <= nodes
        assert [i for i in ends if i.startswith("step:if")] == ["step:if", "step:if#2", "step:if#3", "step:if#4"]
        assert [i for i in ends if i.startswith("step:review")] == [
            "step:review", "step:review#2", "step:review#3", "step:review#4"]

    def test_skipped_failed_and_cached_steps(self, recorder):
        from praisonaiagents.task.task import Task
        from praisonaiagents.workflows.workflows import AgentFlow

        def boom(ctx):
            raise RuntimeError("nope")

        skip = Task(name="gated", handler=_handler("gated"), should_run=lambda ctx: False)
        fail = Task(name="boom", handler=boom, max_retries=0, on_error="continue")
        flow = AgentFlow(steps=[_handler("cached_step"), skip, fail], cache=True)
        flow.run("go")
        statuses = {e.node_id: e.data["status"] for e in _of(recorder, "step_end")}
        assert statuses == {"step:cached_step": "completed", "step:gated": "skipped", "step:boom": "failed"}
        recorder.clear()
        flow.run("go")
        statuses = {e.node_id: e.data["status"] for e in _of(recorder, "step_end")}
        assert statuses["step:cached_step"] == "cached"

    def test_nested_flow_inherits_the_outer_run_id(self, recorder):
        from praisonaiagents.workflows.workflows import AgentFlow

        inner = AgentFlow(name="inner", steps=[_handler("fetch")])

        def nested(ctx):
            return inner.run("sub")["output"]

        outer = AgentFlow(name="outer", steps=[_handler("first"), nested])
        outer.run("go")
        starts = _of(recorder, "workflow_start")
        assert [s.data["name"] for s in starts] == ["outer", "inner"]
        assert len({e.run_id for e in recorder.get_events()}) == 1
        step = [e for e in _of(recorder, "step_start") if e.node_id == "step:nested"][0]
        assert starts[1].parent_seq == step.sequence_num

    def test_team_inside_a_flow_inherits_the_flow_run_id(self, recorder, monkeypatch):
        from praisonaiagents import Agent, Task
        from praisonaiagents.agents.agents import AgentTeam
        from praisonaiagents.workflows.workflows import AgentFlow

        monkeypatch.setattr(AgentTeam, "execute_task", _fake_execute({}))
        writer = Agent(name="Writer", instructions="write")
        team = _team([Task(name="draft", description="d", agent=writer)], agents=[writer])

        def run_team(ctx):
            return team.start()

        AgentFlow(name="outer", steps=[run_team]).run("go")
        run_ids = {e.run_id for e in recorder.get_events()}
        assert len(run_ids) == 1 and team.run_id not in run_ids


# ---------------------------------------------------------------------------
# AgentTeam tasks, manager decisions, human review
# ---------------------------------------------------------------------------


def _team(tasks, process="sequential", agents=None):
    from praisonaiagents import Agent
    from praisonaiagents.agents.agents import AgentTeam

    agents = agents or [Agent(name="Writer", instructions="write")]
    return AgentTeam(agents=agents, tasks=tasks, process=process, output="silent")


def _fake_execute(outputs):
    """Stand-in for AgentTeam.execute_task: no model, scripted results."""
    from praisonaiagents.main import TaskOutput

    def execute(self, task_id):
        task = self.tasks[task_id]
        raw = outputs.get(task.name, "done")
        if raw is None:
            return None
        out = TaskOutput(description=task.description, raw=raw, agent=task.agent.name)
        task.result = out
        return out
    return execute


class TestTeamTasks:
    def test_task_completed_skipped_and_failed(self, recorder, monkeypatch):
        from praisonaiagents import Agent, Task
        from praisonaiagents.agents.agents import AgentTeam

        writer = Agent(name="Writer", instructions="write")
        done = Task(name="draft", description="Draft it", agent=writer)
        skipped = Task(name="optional", description="Maybe", agent=writer, should_run=lambda ctx: False)
        failed = Task(name="flaky", description="Never finishes", agent=writer, max_retries=1, retry_delay=0)
        monkeypatch.setattr(AgentTeam, "execute_task", _fake_execute({"flaky": None}))
        team = _team([done, skipped, failed], agents=[writer])
        team.start()

        ends = {e.node_id: e for e in _of(recorder, "task_end")}
        assert ends["task:draft"].data["status"] == "completed"
        assert ends["task:draft"].data["output_preview"] == "done"
        assert ends["task:optional"].data["status"] == "skipped"
        assert ends["task:flaky"].data["status"] == "failed"
        starts = {e.node_id: e for e in _of(recorder, "task_start")}
        assert starts["task:draft"].data["description_preview"] == "Draft it"
        assert starts["task:draft"].data["agent"] == "Writer"
        for node_id, end in ends.items():
            assert end.parent_seq == starts[node_id].sequence_num
        wf_start = _of(recorder, "workflow_start")[0]
        assert wf_start.data["kind"] == "team" and wf_start.data["graph"]["kind"] == "team"
        assert {s.parent_seq for s in starts.values()} == {wf_start.sequence_num}
        assert _of(recorder, "workflow_end")[0].data["status"] == "failed"
        assert {e.run_id for e in recorder.get_events()} == {team.run_id}

    def test_async_team_records_tasks(self, recorder, monkeypatch):
        from praisonaiagents import Agent, Task
        from praisonaiagents.agents.agents import AgentTeam

        async def aexecute(self, task_id):
            return _fake_execute({})(self, task_id)

        writer = Agent(name="Writer", instructions="write")
        task = Task(name="draft", description="Draft", agent=writer, async_execution=True)
        monkeypatch.setattr(AgentTeam, "aexecute_task", aexecute)
        team = _team([task], agents=[writer])
        asyncio.run(team.astart())
        assert [e.data["status"] for e in _of(recorder, "task_end")] == ["completed"]
        assert _types(recorder)[0] == "workflow_start"
        assert _types(recorder)[-1] == "workflow_end"

    def test_manager_choice_is_a_delegate_handoff(self, recorder, monkeypatch):
        from praisonaiagents import Agent, Task
        from praisonaiagents.agents.agents import AgentTeam
        from praisonaiagents.process.manager_schema import ManagerInstructions
        from praisonaiagents.process.process import Process

        writer = Agent(name="Writer", instructions="write")
        editor = Agent(name="Editor", instructions="edit")
        t1 = Task(name="draft", description="Draft", agent=writer)
        t2 = Task(name="review", description="Review", agent=writer)
        script = iter([
            ManagerInstructions(task_id=0, agent_name="Writer", action="execute"),
            ManagerInstructions(task_id=1, agent_name="Editor", action="execute"),
        ])
        monkeypatch.setattr(
            Process, "_get_manager_instructions_with_fallback",
            lambda self, *a: next(script),
        )
        monkeypatch.setattr(AgentTeam, "execute_task", _fake_execute({}))
        team = _team([t1, t2], process="hierarchical", agents=[writer, editor])
        team.start()

        delegates = [e for e in _of(recorder, "agent_handoff") if e.data["kind"] == "delegate"]
        assert [(d.agent_name, d.data["to_agent"], d.node_id) for d in delegates] == [
            ("Manager", "Writer", "task:draft"),
            ("Manager", "Editor", "task:review"),
        ]
        summary = delegates[1].data["context_passed"]["task_status"]
        assert [(s["name"], s["status"]) for s in summary] == [("draft", "completed"), ("review", "not started")]
        manager = [e for e in _of(recorder, "task_start") if e.node_id == "manager:Manager"]
        assert len(manager) == 1

    def test_human_review_records_an_approval_pair(self, recorder):
        from praisonaiagents import Agent, Task
        from praisonaiagents.approval import ApprovalDecision, get_approval_registry
        from praisonaiagents.main import TaskOutput

        class Reviewer:
            def request_approval_sync(self, request):
                return ApprovalDecision(approved=True, reason="looks good", approver="ana")

        registry = get_approval_registry()
        previous = registry.get_backend()
        registry.set_backend(Reviewer())
        try:
            writer = Agent(name="Writer", instructions="write")
            task = Task(name="draft", description="Draft", agent=writer, human_input=True)
            team = _team([task], agents=[writer])
            out = TaskOutput(description="Draft", raw="api_key=sk-secret123456 text", agent="Writer")
            team._apply_human_review(task, 0, out)
        finally:
            registry.set_backend(previous)
        requested, decided = _of(recorder, "approval_requested"), _of(recorder, "approval_decided")
        assert len(requested) == len(decided) == 1
        assert requested[0].data["kind"] == "task_output_review"
        assert requested[0].node_id == "task:draft"
        assert "sk-secret123456" not in str(requested[0].data["args"])
        assert decided[0].parent_seq == requested[0].sequence_num
        assert decided[0].data["approved"] is True and decided[0].data["approver"] == "ana"
        assert decided[0].data["approval_id"] == requested[0].data["approval_id"]


# ---------------------------------------------------------------------------
# Tool-call approvals
# ---------------------------------------------------------------------------


class TestToolApprovals:
    def _registry(self, backend):
        from praisonaiagents.approval.registry import ApprovalRegistry

        registry = ApprovalRegistry()
        registry.set_backend(backend)
        registry.add_requirement("delete_file", risk_level="high")
        return registry

    def test_sync_approval_records_request_and_decision(self, recorder, monkeypatch):
        from praisonaiagents.approval import ApprovalDecision

        monkeypatch.delenv("PRAISONAI_AUTO_APPROVE", raising=False)

        class Deny:
            def request_approval_sync(self, request):
                return ApprovalDecision(approved=False, reason="not today", approver="ops")

        registry = self._registry(Deny())
        decision = registry.approve_sync("Writer", "delete_file", {"path": "/x", "password": "hunter2"})
        assert decision.approved is False
        requested, decided = _of(recorder, "approval_requested"), _of(recorder, "approval_decided")
        assert len(requested) == len(decided) == 1
        assert requested[0].data["tool"] == "delete_file"
        assert requested[0].data["risk"] == "high"
        assert requested[0].data["kind"] == "tool_call"
        assert requested[0].node_id == "tool:Writer/delete_file"
        assert "hunter2" not in str(requested[0].data["args"])
        assert decided[0].parent_seq == requested[0].sequence_num
        assert decided[0].data == {
            "approval_id": requested[0].data["approval_id"],
            "approved": False, "reason": "not today", "approver": "ops", "modified": False,
        }

    def test_async_approval_records_request_and_decision(self, recorder, monkeypatch):
        from praisonaiagents.approval import ApprovalDecision

        monkeypatch.delenv("PRAISONAI_AUTO_APPROVE", raising=False)

        class Allow:
            async def request_approval(self, request):
                return ApprovalDecision(approved=True, reason="ok", modified_args={"path": "/y"})

        registry = self._registry(Allow())
        asyncio.run(registry.approve_async("Writer", "delete_file", {"path": "/x"}))
        decided = _of(recorder, "approval_decided")
        assert len(decided) == 1 and decided[0].data["modified"] is True
        assert decided[0].parent_seq == _of(recorder, "approval_requested")[0].sequence_num

    def test_control_the_fast_path_records_nothing(self, recorder):
        from praisonaiagents.approval.registry import ApprovalRegistry

        ApprovalRegistry().approve_sync("Writer", "read_file", {})  # not required
        assert _of(recorder, "approval_requested") == []


# ---------------------------------------------------------------------------
# Hand-offs
# ---------------------------------------------------------------------------


class TestHandoffs:
    def _pair(self):
        from praisonaiagents import Agent

        source = Agent(name="Router", instructions="route")
        target = Agent(name="Billing", instructions="bill")
        target.chat = lambda *a, **k: "handled"

        async def achat(*a, **k):
            return "handled"
        target.achat = achat
        return source, target

    def _one_handoff(self, sink):
        handoffs = _of(sink, "agent_handoff")
        assert len(handoffs) == 1, [h.data for h in handoffs]
        h = handoffs[0]
        assert (h.agent_name, h.data["from_agent"], h.data["to_agent"]) == ("Router", "Router", "Billing")
        assert h.data["kind"] == "handoff"
        assert h.node_id == "agent:Billing"
        return h

    def test_programmatic(self, recorder):
        from praisonaiagents.agent.handoff import Handoff

        source, target = self._pair()
        Handoff(agent=target).execute_programmatic(source, "refund order 7")
        assert self._one_handoff(recorder).data["reason"] == "refund order 7"

    def test_async(self, recorder):
        from praisonaiagents.agent.handoff import Handoff

        source, target = self._pair()
        asyncio.run(Handoff(agent=target).execute_async(source, "refund order 7"))
        self._one_handoff(recorder)

    def test_tool_function(self, recorder):
        from praisonaiagents.agent.handoff import Handoff

        source, target = self._pair()
        tool = Handoff(agent=target).to_tool_function(source)
        tool(task="refund order 7")
        h = self._one_handoff(recorder)
        assert h.data["context_passed"]["args"] == {"task": "refund order 7"}

    def test_typed_programmatic_and_async(self, recorder):
        from pydantic import BaseModel
        from praisonaiagents.agent.handoff import TypedHandoff

        class Refund(BaseModel):
            order: int

        source, target = self._pair()
        TypedHandoff(agent=target, input_schema=Refund).execute_programmatic(source, Refund(order=7))
        self._one_handoff(recorder)
        recorder.clear()
        asyncio.run(TypedHandoff(agent=target, input_schema=Refund).execute_async(source, Refund(order=7)))
        self._one_handoff(recorder)

    def test_control_a_refused_handoff_records_nothing(self, recorder):
        from praisonaiagents.agent.handoff import Handoff, HandoffConfig, _clear_handoff_chain, _push_handoff

        source, target = self._pair()
        _push_handoff("Billing")  # Billing already in the chain -> cycle
        try:
            with pytest.raises(Exception):
                Handoff(agent=target, config=HandoffConfig(detect_cycles=True)).execute_programmatic(source, "x")
        finally:
            _clear_handoff_chain()
        assert _of(recorder, "agent_handoff") == []


# ---------------------------------------------------------------------------
# LiteLLM path
# ---------------------------------------------------------------------------


def _response(text="hello", prompt=11, completion=3):
    message = types.SimpleNamespace(content=text, tool_calls=None)
    choice = types.SimpleNamespace(message=message, finish_reason="stop", delta=None)
    usage = types.SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion)
    return types.SimpleNamespace(choices=[choice], usage=usage, model="gpt-4o-mini")


def _chunk(text=None, finish=None, usage=None):
    delta = types.SimpleNamespace(content=text, tool_calls=None)
    choice = types.SimpleNamespace(delta=delta, finish_reason=finish)
    return types.SimpleNamespace(choices=[choice], usage=usage)


@pytest.fixture
def fake_litellm(monkeypatch):
    import litellm
    import praisonaiagents.llm.llm as llm_module

    monkeypatch.setattr(llm_module, "check_model_request", lambda *a, **k: None)
    calls = []

    def completion(**params):
        calls.append(params)
        if params.get("stream"):
            usage = types.SimpleNamespace(prompt_tokens=5, completion_tokens=2)
            return iter([_chunk("hel"), _chunk("lo", finish="stop"), _chunk(usage=usage)])
        return _response()

    async def acompletion(**params):
        calls.append(params)
        if params.get("stream"):
            async def gen():
                for c in [_chunk("a"), _chunk("b", finish="stop")]:
                    yield c
            return gen()
        return _response("async")

    monkeypatch.setattr(litellm, "completion", completion)
    monkeypatch.setattr(litellm, "acompletion", acompletion)
    return calls


class TestLiteLLMPath:
    def _llm(self):
        from praisonaiagents.llm.llm import LLM
        return LLM(model="gpt-4o-mini")

    def test_non_streaming_call_records_request_and_response(self, recorder, fake_litellm):
        llm = self._llm()
        emitter = get_context_emitter()
        emitter.agent_start("Writer")
        llm._completion_with_retry(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
        emitter.agent_end("Writer")
        request, response = _of(recorder, "llm_request"), _of(recorder, "llm_response")
        assert len(request) == len(response) == 1
        assert request[0].agent_name == "Writer" and request[0].node_id == "agent:Writer"
        assert request[0].messages_count == 1
        r = response[0]
        assert (r.prompt_tokens, r.completion_tokens) == (11, 3)
        assert r.data["model"] == "gpt-4o-mini"
        assert r.data["response_content"] == "hello"
        assert r.data["finish_reason"] == "stop"
        assert r.data["duration_ms"] >= 0
        assert r.cost_usd > 0  # litellm knows gpt-4o-mini's price

    def test_response_records_the_serving_model_and_a_message_snapshot(self, recorder, fake_litellm, monkeypatch):
        import litellm

        served = _response()
        served.model = "gpt-4o"  # a failover profile answered
        monkeypatch.setattr(litellm, "completion", lambda **params: served)
        messages = [{"role": "user", "content": "hi"}]
        self._llm()._completion_with_retry(model="gpt-4o-mini", messages=messages)
        messages.append({"role": "assistant", "content": "later turn"})
        assert _of(recorder, "llm_response")[0].data["model"] == "gpt-4o"
        assert _of(recorder, "llm_request")[0].messages_count == 1
        assert len(_of(recorder, "llm_request")[0].data["messages"]) == 1

    def test_streaming_call_records_response_when_the_stream_ends(self, recorder, fake_litellm):
        llm = self._llm()
        stream = llm._completion_with_retry(model="gpt-4o-mini", messages=[], stream=True)
        assert _of(recorder, "llm_response") == []
        text = "".join(c.choices[0].delta.content or "" for c in stream)
        assert text == "hello"
        response = _of(recorder, "llm_response")
        assert len(response) == 1
        assert response[0].data["response_content"] == "hello"
        assert (response[0].prompt_tokens, response[0].completion_tokens) == (5, 2)

    def test_async_calls_record_events(self, recorder, fake_litellm):
        llm = self._llm()

        async def run():
            await llm._acompletion_with_retry(model="gpt-4o-mini", messages=[])
            stream = await llm._acompletion_with_retry(model="gpt-4o-mini", messages=[], stream=True)
            return "".join([c.choices[0].delta.content async for c in stream])

        assert asyncio.run(run()) == "ab"
        responses = _of(recorder, "llm_response")
        assert [r.data["response_content"] for r in responses] == ["async", "ab"]
        assert len(_of(recorder, "llm_request")) == 2

    def test_a_call_already_recorded_by_the_agent_is_not_counted_twice(self, recorder, fake_litellm):
        llm = self._llm()
        emitter = get_context_emitter()
        emitter.agent_start("Writer")
        emitter.llm_request("Writer", messages_count=1, tokens_used=0, model="gpt-4o-mini")
        llm._completion_with_retry(model="gpt-4o-mini", messages=[])
        emitter.llm_response("Writer", duration_ms=1.0)
        llm._completion_with_retry(model="gpt-4o-mini", messages=[])  # a fresh call counts
        emitter.agent_end("Writer")
        assert len(_of(recorder, "llm_request")) == 2
        assert len(_of(recorder, "llm_response")) == 2

    def test_a_failed_call_records_an_error_response(self, recorder, monkeypatch):
        import litellm
        import praisonaiagents.llm.llm as llm_module

        monkeypatch.setattr(llm_module, "check_model_request", lambda *a, **k: None)

        def explode(**params):
            raise ValueError("bad request")
        monkeypatch.setattr(litellm, "completion", explode)
        llm = self._llm()
        llm._max_retries = 0
        with pytest.raises(Exception):
            llm._completion_with_retry(model="gpt-4o-mini", messages=[])
        response = _of(recorder, "llm_response")
        assert len(response) == 1 and response[0].data["finish_reason"] == "error"

    def test_responses_api_calls_record_events(self, recorder, monkeypatch):
        """OpenAI models on the LiteLLM path go through the Responses API."""
        from praisonaiagents.llm.llm import LLM

        usage = types.SimpleNamespace(input_tokens=7, output_tokens=2)
        monkeypatch.setattr(LLM, "_call_responses_api_impl", lambda self, **p: types.SimpleNamespace(usage=usage))
        monkeypatch.setattr(LLM, "_extract_from_responses_output", lambda self, r: ("answer", None, None))
        monkeypatch.setattr(LLM, "_stream_responses_api_impl",
                            lambda self, params, *a, **k: ("streamed", None, types.SimpleNamespace(usage=usage)))

        async def acall(self, **p):
            return types.SimpleNamespace(usage=usage)
        monkeypatch.setattr(LLM, "_call_responses_api_async_impl", acall)

        llm = self._llm()
        params = {"model": "gpt-4o-mini", "input": [{"role": "user", "content": "hi"}]}
        llm._call_responses_api(**params)
        llm._stream_responses_api(dict(params), verbose=False)
        asyncio.run(llm._call_responses_api_async(**params))
        requests, responses = _of(recorder, "llm_request"), _of(recorder, "llm_response")
        assert len(requests) == len(responses) == 3
        assert requests[0].messages_count == 1
        assert [r.data["response_content"] for r in responses] == ["answer", "streamed", "answer"]
        assert all((r.prompt_tokens, r.completion_tokens) == (7, 2) for r in responses)

    def test_control_disabled_tracing_leaves_the_stream_untouched(self, fake_litellm):
        llm = self._llm()
        stream = llm._completion_with_retry(model="gpt-4o-mini", messages=[], stream=True)
        assert type(stream).__name__ == "list_iterator"


# ---------------------------------------------------------------------------
# The disabled emitter costs (almost) nothing
# ---------------------------------------------------------------------------


def test_disabled_emitter_adds_next_to_nothing():
    emitter = ContextTraceEmitter(enabled=False)
    n = 20000

    def baseline():
        pass

    t0 = time.perf_counter()
    for _ in range(n):
        baseline()
    base = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(n):
        emitter.task_start("t", "d", "a", "task:t")
        emitter.step_end("s", "completed", 1.0, "out")
        emitter.agent_handoff("a", "b", kind="delegate")
        emitter.approval_requested("id", "tool", {"x": 1})
        emitter.workflow_start("team", "t", "sequential", graph={})
    cost = time.perf_counter() - t0
    # Five disabled calls per iteration: one attribute check each.
    assert cost / (n * 5) < 2e-6, f"{cost / (n * 5) * 1e9:.0f} ns per disabled call"
    assert cost < base * 5 * 20 + 0.05


def test_disabled_tracing_never_builds_the_graph():
    from praisonaiagents.trace.context_events import _workflow_scope

    built = []
    with _workflow_scope("team", "t", "sequential", graph_fn=lambda: built.append(1)) as run:
        assert run is None
    assert built == []


class TestTeamRunLabel:
    """An unnamed team is labelled by its agents, not by whichever agent comes first."""

    def test_unnamed_team_is_labelled_by_its_agents(self):
        from praisonaiagents import Agent, AgentTeam

        team = AgentTeam(agents=[Agent(name="Researcher", output="silent"), Agent(name="Writer", output="silent")])
        assert team._replay_name() == "Researcher + Writer"

    def test_named_team_keeps_its_name(self):
        from praisonaiagents import Agent, AgentTeam

        team = AgentTeam(agents=[Agent(name="Researcher", output="silent")], name="EV brief")
        assert team._replay_name() == "EV brief"


class TestStepVariables:
    """step_end records the variables a step set, so a re-run can restore them."""

    def test_step_end_records_handler_variables_redacted(self, recorder):
        from praisonaiagents.workflows import StepResult
        from praisonaiagents.workflows.workflows import AgentFlow

        def research(ctx):
            return StepResult(output="notes", variables={"customer_id": 42, "api_key": "sk-abcdefghijklmnop1234"})

        def draft(ctx):
            return StepResult(output="draft")

        AgentFlow(name="v", steps=[research, draft]).run("go")
        ends = {e.node_id: e.data for e in _of(recorder, "step_end")}
        assert ends["step:research"]["variables"]["customer_id"] == 42
        assert "sk-abcdefghijklmnop1234" not in str(ends["step:research"]["variables"])
        assert "variables" not in ends["step:draft"]

    def test_nested_step_end_records_handler_variables(self, recorder):
        """Steps run through _execute_single_step_internal (patterns, hierarchical) record them too."""
        from praisonaiagents.workflows import StepResult
        from praisonaiagents.workflows.workflows import AgentFlow, If

        def research(ctx):
            return StepResult(output="notes", variables={"customer_id": 42})

        AgentFlow(name="v", steps=[If(condition="1 > 0", then_steps=[research])]).run("go")
        ends = {e.node_id: e.data for e in _of(recorder, "step_end")}
        variables = next(d["variables"] for n, d in ends.items() if n.endswith("research"))
        assert variables == {"customer_id": 42}

    def test_cache_hit_step_end_leaves_out_the_output_variable(self, recorder):
        """The step cache stores the output variable (the full output); a cached
        step_end must trace only what the handler set, like the cold run."""
        from praisonaiagents.workflows import StepResult
        from praisonaiagents.workflows.workflows import AgentFlow

        def research(ctx):
            return StepResult(output="the full step output " * 50, variables={"customer_id": 42})

        flow = AgentFlow(name="v", steps=[research], cache=True)
        flow.run("go")
        flow.run("go")  # cache hit
        ends = [e.data for e in _of(recorder, "step_end")]
        assert [d["status"] for d in ends] == ["completed", "cached"]
        for d in ends:
            assert d["variables"] == {"customer_id": 42}
            assert "the full step output" not in str(d["variables"])

    def test_nested_step_records_a_variable_changed_in_place(self, recorder):
        """A list the step appends to (same object) still counts as set by it."""
        from praisonaiagents.workflows import StepResult
        from praisonaiagents.workflows.workflows import AgentFlow, If

        def seed(ctx):
            return StepResult(output="s", variables={"items": ["a"]})

        def add(ctx):
            ctx.variables["items"].append("b")
            return StepResult(output="m")

        AgentFlow(name="v", steps=[seed, If(condition="1 > 0", then_steps=[add])]).run("go")
        ends = {e.node_id: e.data for e in _of(recorder, "step_end")}
        variables = next(d.get("variables") for n, d in ends.items() if n.endswith("add"))
        assert variables == {"items": ["a", "b"]}

    def test_uncopyable_variable_does_not_hide_an_in_place_change(self, recorder):
        """One variable that cannot be deep-copied must not stop the others being compared by value."""
        import threading
        from praisonaiagents.workflows import StepResult
        from praisonaiagents.workflows.workflows import AgentFlow, If

        def seed(ctx):
            return StepResult(output="s", variables={"items": ["a"]})

        def add(ctx):
            ctx.variables["items"].append("b")
            return StepResult(output="m")

        flow = AgentFlow(name="v", steps=[seed, If(condition="1 > 0", then_steps=[add])],
                         variables={"lock": threading.Lock()})
        flow.run("go")
        ends = {e.node_id: e.data for e in _of(recorder, "step_end")}
        variables = next(d.get("variables") for n, d in ends.items() if n.endswith("add"))
        assert variables == {"items": ["a", "b"]}

    def test_skipped_or_cached_nested_step_does_not_copy_the_scope(self, recorder, monkeypatch):
        """Only a nested step that really runs snapshots the variables; a cache
        hit still records what the handler set."""
        from praisonaiagents.workflows import StepResult, Task
        from praisonaiagents.workflows import workflows as wf

        copies = []
        real = wf._isolate_scope
        monkeypatch.setattr(wf, "_isolate_scope", lambda v: copies.append(1) or real(v))

        def research(ctx):
            return StepResult(output="notes", variables={"customer_id": 42})

        def never(ctx):
            return StepResult(output="x")

        steps = [wf.If(condition="1 > 0", then_steps=[
            research, Task(name="never", handler=never, should_run=lambda ctx: False),
        ])]
        flow = wf.AgentFlow(name="v", steps=steps, variables={"items": list(range(1000))}, cache=True)
        flow.run("go")
        assert len(copies) == 1  # research ran; the skipped step copied nothing
        copies.clear()
        flow.run("go")  # research is a cache hit
        assert copies == []
        cached = [e.data for e in _of(recorder, "step_end") if e.data["status"] == "cached"]
        assert [d.get("variables") for d in cached] == [{"customer_id": 42}]
