"""``praisonai replay rerun``: reuse recorded outputs before NODE, run NODE onwards fresh."""

import json
import textwrap

import pytest


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace every Agent LLM call with a counted, deterministic answer."""
    from praisonaiagents import Agent

    calls = []

    def fake_chat(self, prompt, *args, **kwargs):
        calls.append((self.name, str(prompt)))
        return f"{self.name} fresh output"

    async def fake_achat(self, prompt, *args, **kwargs):
        return fake_chat(self, prompt)

    monkeypatch.setattr(Agent, "chat", fake_chat)
    monkeypatch.setattr(Agent, "achat", fake_achat)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    return calls


def _lines(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


# ---------------------------------------------------------------------------
# plan_rerun: what the recording can support
# ---------------------------------------------------------------------------

def test_plan_rejects_schema_1_0_trace(fx):
    from praisonai.replay.rerun import RerunError, plan_rerun

    with pytest.raises(RerunError, match="schema 1.0"):
        plan_rerun(fx.legacy_events(), "task:write")


def test_plan_rejects_unknown_node_and_lists_known(fx):
    from praisonai.replay.rerun import RerunError, plan_rerun

    with pytest.raises(RerunError, match="task:research, task:write"):
        plan_rerun(fx.team_events(), "task:nope")


def test_plan_reuses_only_nodes_finished_before_target(fx):
    from praisonai.replay.rerun import plan_rerun

    plan = plan_rerun(fx.flow_events(), "step:polish")
    assert plan.kind == "flow"
    assert dict(plan.outputs) == {"step:research": "research output", "step:draft": "draft output"}
    assert plan.forked_from == {"run_id": "run-flow01", "node_id": "step:polish"}
    assert dict(plan_rerun(fx.flow_events(), "step:research").outputs) == {}


def test_plan_recovers_long_output_from_llm_response(fx):
    from praisonai.replay.rerun import plan_rerun

    full = "Findings: " + "x" * 900
    evs = fx.team_events()
    evs[5]["data"]["response_content"] = full
    evs[9]["data"]["output_preview"] = full[:500]
    assert plan_rerun(evs, "task:write").outputs["task:research"] == full


def test_plan_refuses_truncated_output_it_cannot_recover(fx):
    from praisonai.replay.rerun import RerunError, plan_rerun

    evs = fx.team_events()
    evs[5]["data"]["response_content"] = "something else"
    evs[9]["data"]["output_preview"] = "y" * 500
    with pytest.raises(RerunError, match="truncated preview"):
        plan_rerun(evs, "task:write")


def test_plan_refuses_llm_response_the_emitter_shortened(fx):
    from praisonai.replay.rerun import RerunError, plan_rerun

    full = "Findings: " + "x" * 900
    evs = fx.team_events()
    evs[5]["data"]["response_content"] = full[:600] + "\n...[60,000 chars, showing first/last portions]...\n" + "tail"
    evs[9]["data"]["output_preview"] = full[:500]
    with pytest.raises(RerunError, match="truncated preview"):
        plan_rerun(evs, "task:write")


# ---------------------------------------------------------------------------
# AgentFlow: TraceStepCache
# ---------------------------------------------------------------------------

def _counting_flow():
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    calls = []

    def research(ctx):
        calls.append("research")
        return StepResult(output="research FRESH")

    def draft(ctx):
        calls.append("draft")
        return StepResult(output=f"draft of [{ctx.previous_result}]")

    def polish(ctx):
        calls.append("polish")
        return StepResult(output=f"polished [{ctx.previous_result}]")

    return AgentFlow(steps=[research, draft, polish]), calls


def test_trace_step_cache_implements_step_cache_protocol():
    from praisonaiagents.workflows.step_cache import StepCacheProtocol, resolve_step_cache
    from praisonai.replay.rerun import TraceStepCache

    cache = TraceStepCache({})
    assert isinstance(cache, StepCacheProtocol)
    assert resolve_step_cache(cache) is cache
    assert cache.get("k") is None and cache.set("k", {}) is None


def test_flow_rerun_reuses_earlier_steps_and_runs_later_ones(traces_dir, fx):
    from praisonai.replay.rerun import rerun

    src = fx.write_trace(traces_dir, "run-flow01", fx.flow_events())
    flow, calls = _counting_flow()
    rec, result = rerun(flow, str(src), "step:draft", input="topic")

    assert calls == ["draft", "polish"]  # research came from the recording
    assert result["output"] == "polished [draft of [research output]]"
    assert flow._step_cache.hits == ["research"]

    events = _lines(rec.path)
    assert rec.run_id != "run-flow01"
    assert events[0]["data"]["forked_from"] == {"run_id": "run-flow01", "node_id": "step:draft"}
    for ev in events:
        if ev["event_type"] == "workflow_start":  # schema 1.1 core
            assert ev["data"]["forked_from"] == {"run_id": "run-flow01", "node_id": "step:draft"}


def test_flow_rerun_from_last_step(traces_dir, fx):
    from praisonai.replay.rerun import rerun

    src = fx.write_trace(traces_dir, "run-flow01", fx.flow_events())
    flow, calls = _counting_flow()
    _rec, result = rerun(flow, str(src), "step:polish", input="topic")
    assert calls == ["polish"]
    assert result["output"] == "polished [draft output]"


def test_rerun_rejects_wrong_object_kind(traces_dir, fx):
    from praisonai.replay.rerun import RerunError, rerun

    src = fx.write_trace(traces_dir, "run-team01", fx.team_events())
    flow, _calls = _counting_flow()
    with pytest.raises(RerunError, match="team task"):
        rerun(flow, str(src), "task:write")


# ---------------------------------------------------------------------------
# AgentTeam: restore finished tasks, reset the rest
# ---------------------------------------------------------------------------

def _team():
    from praisonaiagents import Agent, AgentTeam, Task

    r = Agent(name="Researcher", instructions="research")
    w = Agent(name="Writer", instructions="write")
    t1 = Task(name="research", description="Research AI", expected_output="notes", agent=r)
    t2 = Task(name="write", description="Write post", expected_output="post", agent=w)
    return AgentTeam(agents=[r, w], tasks=[t1, t2])


def test_team_rerun_skips_earlier_tasks(traces_dir, fx, fake_llm):
    from praisonai.replay.rerun import rerun

    src = fx.write_trace(traces_dir, "run-team01", fx.team_events())
    team = _team()
    rec, result = rerun(team, str(src), "task:write")

    assert [name for name, _ in fake_llm] == ["Writer"]  # Researcher not re-run
    assert "Findings: AI is big" in fake_llm[0][1]  # recorded output fed forward
    assert "Writer fresh output" in str(result)
    assert team.tasks[0].status == "completed"
    assert _lines(rec.path)[0]["data"]["forked_from"] == {"run_id": "run-team01", "node_id": "task:write"}


def test_team_rerun_from_first_task_runs_everything(traces_dir, fx, fake_llm):
    from praisonai.replay.rerun import rerun

    src = fx.write_trace(traces_dir, "run-team01", fx.team_events())
    rerun(_team(), str(src), "task:research")
    assert [name for name, _ in fake_llm] == ["Researcher", "Writer"]


def test_seed_team_resets_tasks_from_node(fx):
    from praisonai.replay.rerun import plan_rerun, seed_team

    team = _team()
    for task in team.tasks.values():
        task.status = "completed"
        task.result = "stale"
    restored = seed_team(team, plan_rerun(fx.team_events(), "task:write"))
    assert restored == [0]
    assert team.tasks[0].status == "completed"
    assert getattr(team.tasks[0].result, "raw", team.tasks[0].result) == "Findings: AI is big"
    assert team.tasks[1].status == "not started" and team.tasks[1].result is None


# ---------------------------------------------------------------------------
# CLI: praisonai replay rerun (YAML definitions through the real runner)
# ---------------------------------------------------------------------------

FLOW_YAML = textwrap.dedent("""\
    name: blog-flow
    process: workflow
    workflow:
      default_llm: gpt-4o-mini
    input: AI agents
    agents:
      researcher:
        role: Researcher
        goal: Research topics
        instructions: You research.
      writer:
        role: Writer
        goal: Write posts
        instructions: You write.
    steps:
      - name: research
        agent: researcher
        action: "Research {{input}}"
      - name: draft
        agent: writer
        action: "Write about {{previous_output}}"
""")

TEAM_YAML = textwrap.dedent("""\
    framework: praisonai
    topic: AI agents
    roles:
      researcher:
        role: Researcher
        goal: Research topics
        backstory: You research.
        tasks:
          research:
            description: Research {topic}
            expected_output: notes
      writer:
        role: Writer
        goal: Write posts
        backstory: You write.
        tasks:
          write:
            description: Write a post
            expected_output: post
""")


def _invoke(*args):
    from typer.testing import CliRunner

    from praisonai.cli.commands.replay import app

    return CliRunner().invoke(app, list(args))


def test_cli_rerun_flow_yaml(traces_dir, tmp_path, fx, fake_llm):
    y = tmp_path / "flow.yaml"
    y.write_text(FLOW_YAML)
    fx.write_trace(traces_dir, "run-flow01", fx.flow_events(
        yaml_path=y, step_names=("research", "draft"),
        outputs={"research": "RECORDED NOTES", "draft": "old post"},
    ))
    result = _invoke("rerun", "run-flow01", "--from", "step:draft")
    assert result.exit_code == 0, result.output
    assert [name for name, _ in fake_llm] == ["writer"]  # only the draft step's agent ran
    assert "RECORDED NOTES" in fake_llm[0][1]
    assert "reusing: step:research" in result.output
    new_ids = [p.stem for p in traces_dir.glob("*.jsonl") if p.stem != "run-flow01"]
    assert len(new_ids) == 1
    first = _lines(traces_dir / f"{new_ids[0]}.jsonl")[0]
    assert first["data"]["forked_from"] == {"run_id": "run-flow01", "node_id": "step:draft"}
    assert first["data"]["yaml_path"] == str(y.resolve())


def test_cli_rerun_team_yaml_with_file_option(traces_dir, tmp_path, fx, fake_llm):
    y = tmp_path / "team.yaml"
    y.write_text(TEAM_YAML)
    evs = fx.team_events()  # recorded without a yaml_path -> --file is required
    for ev in evs:  # YAML team tasks have no names: node ids are positional
        if ev.get("node_id") == "task:research":
            ev["node_id"] = "task:0"
        elif ev.get("node_id") == "task:write":
            ev["node_id"] = "task:1"
    fx.write_trace(traces_dir, "run-team01", evs)

    missing = _invoke("rerun", "run-team01", "--from", "task:1")
    assert missing.exit_code == 1 and "--file" in missing.output

    result = _invoke("rerun", "run-team01", "--from", "task:1", "--file", str(y))
    assert result.exit_code == 0, result.output
    assert [name for name, _ in fake_llm] == ["Writer"]
    assert "Findings: AI is big" in fake_llm[0][1]


def test_cli_rerun_rejects_kind_mismatch(traces_dir, tmp_path, fx, fake_llm):
    y = tmp_path / "team.yaml"
    y.write_text(TEAM_YAML)
    fx.write_trace(traces_dir, "run-flow01", fx.flow_events(yaml_path=y))
    result = _invoke("rerun", "run-flow01", "--from", "step:draft")
    assert result.exit_code == 1
    assert "defines a team" in result.output
    assert fake_llm == []  # refused before spending anything


def test_cli_rerun_legacy_trace_fails_clearly(traces_dir, fx):
    fx.write_trace(traces_dir, "run-legacy1", fx.legacy_events())
    result = _invoke("rerun", "run-legacy1", "--from", "task:write")
    assert result.exit_code == 1
    assert "schema 1.0" in result.output


def test_plan_rerun_accepts_a_path_object(tmp_path):
    """record() hands back a pathlib.Path; rerun must take it as-is."""
    import json
    from pathlib import Path

    from praisonai.replay.rerun import plan_rerun

    events = [
        {"event_type": "session_start", "session_id": "s", "sequence_num": 0, "timestamp": 1.0, "data": {}, "run_id": "r"},
        {"event_type": "workflow_start", "session_id": "s", "sequence_num": 1, "timestamp": 1.1, "data": {"kind": "flow"}, "run_id": "r"},
        {"event_type": "step_start", "session_id": "s", "sequence_num": 2, "timestamp": 1.2, "data": {"name": "a"}, "node_id": "step:a", "run_id": "r"},
        {"event_type": "step_end", "session_id": "s", "sequence_num": 3, "timestamp": 1.3, "parent_seq": 2, "data": {"status": "completed", "output": "A"}, "node_id": "step:a", "run_id": "r"},
        {"event_type": "step_start", "session_id": "s", "sequence_num": 4, "timestamp": 1.4, "data": {"name": "b"}, "node_id": "step:b", "run_id": "r"},
    ]
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    assert plan_rerun(Path(path), "step:b") is not None


def test_flow_rerun_restores_recorded_step_variables(traces_dir, fx):
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    from praisonai.replay.rerun import rerun

    seen = []

    def research(ctx):
        return StepResult(output="fresh", variables={"customer_id": 0})

    def draft(ctx):
        seen.append(ctx.variables.get("customer_id"))
        return StepResult(output="draft")

    def polish(ctx):
        return StepResult(output="polish")

    evs = fx.flow_events()
    for ev in evs:
        if ev["event_type"] == "step_end" and ev.get("node_id") == "step:research":
            ev["data"]["variables"] = {"customer_id": 42}
    src = fx.write_trace(traces_dir, "run-flow01", evs)
    rerun(AgentFlow(steps=[research, draft, polish]), str(src), "step:draft", input="topic")
    assert seen == [42]


def test_flow_rerun_rejects_flow_missing_recorded_steps(traces_dir, fx):
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    from praisonai.replay.rerun import RerunError, rerun

    def other(ctx):
        return StepResult(output="x")

    src = fx.write_trace(traces_dir, "run-flow01", fx.flow_events())
    with pytest.raises(RerunError, match="does not match any step"):
        rerun(AgentFlow(steps=[other]), str(src), "step:draft", input="topic")


def test_flow_rerun_rejects_reordered_flow(traces_dir, fx):
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    from praisonai.replay.rerun import RerunError, rerun

    ran = []

    def research(ctx):
        ran.append("research")
        return StepResult(output="r")

    def draft(ctx):
        ran.append("draft")
        return StepResult(output="d")

    def polish(ctx):
        ran.append("polish")
        return StepResult(output="p")

    src = fx.write_trace(traces_dir, "run-flow01", fx.flow_events())
    with pytest.raises(RerunError, match="different order"):
        rerun(AgentFlow(steps=[draft, research, polish]), str(src), "step:draft", input="topic")
    assert ran == []


def test_flow_rerun_rejects_step_inserted_before_target(traces_dir, fx):
    """research -> extra -> draft: 'extra' never ran, so draft would get its output, not research's."""
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    from praisonai.replay.rerun import RerunError, rerun

    ran = []

    def research(ctx):
        ran.append("research")
        return StepResult(output="r")

    def extra(ctx):
        ran.append("extra")
        return StepResult(output="e")

    def draft(ctx):
        ran.append("draft")
        return StepResult(output="d")

    def polish(ctx):
        ran.append("polish")
        return StepResult(output="p")

    src = fx.write_trace(traces_dir, "run-flow01", fx.flow_events())
    with pytest.raises(RerunError, match="did not run in the recording"):
        rerun(AgentFlow(steps=[research, extra, draft, polish]), str(src), "step:draft", input="topic")
    assert ran == []


def test_flow_rerun_allows_a_recorded_skipped_step_before_target(traces_dir, fx):
    """A step that ran but was skipped is part of the recording, not an insertion."""
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    from praisonai.replay.rerun import rerun

    evs = fx.flow_events()
    for ev in evs:
        if ev["event_type"] == "step_end" and ev.get("node_id") == "step:research":
            ev["data"]["status"] = "skipped"
    src = fx.write_trace(traces_dir, "run-flow01", evs)

    def research(ctx):
        return StepResult(output="r")

    def draft(ctx):
        return StepResult(output="d")

    def polish(ctx):
        return StepResult(output="p")

    rec, _ = rerun(AgentFlow(steps=[research, draft, polish]), str(src), "step:draft", input="topic")
    assert rec.path.exists()


def test_recorded_handler_variables_survive_a_rerun(traces_dir):
    """End to end: core records StepResult.variables on step_end; rerun restores them."""
    import json

    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    from praisonai.replay import record
    from praisonai.replay.rerun import rerun

    def make(customer_id, seen, calls):
        def research(ctx):
            calls.append("research")
            return StepResult(output="notes", variables={"customer_id": customer_id})

        def draft(ctx):
            seen.append(ctx.variables.get("customer_id"))
            return StepResult(output="draft")

        return AgentFlow(steps=[research, draft])

    with record(full_content=True) as rec:
        make(42, [], []).start("topic")
    ends = [json.loads(line) for line in open(rec.path) if '"step_end"' in line]
    assert any((e["data"].get("variables") or {}).get("customer_id") == 42 for e in ends)

    seen, calls = [], []
    rerun(make(0, seen, calls), rec.path, "step:draft", input="topic")
    assert calls == []          # research reused from the recording
    assert seen == [42]         # with the variable it set, not the fresh run's 0
