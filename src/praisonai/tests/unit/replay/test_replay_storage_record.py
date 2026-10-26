"""PraisonAI Replay: trace location precedence and ``praisonai.replay.record()``."""

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# storage: PRAISONAI_TRACES_DIR > $PRAISON_HOME/traces > ~/.praison/traces
# ---------------------------------------------------------------------------

def test_traces_dir_env_wins_over_praison_home(tmp_path, monkeypatch):
    from praisonai.replay.storage import get_traces_dir

    monkeypatch.setenv("PRAISON_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PRAISONAI_TRACES_DIR", str(tmp_path / "explicit"))
    assert get_traces_dir() == tmp_path / "explicit"
    assert (tmp_path / "explicit").is_dir()


def test_traces_dir_uses_praison_home(tmp_path, monkeypatch):
    from praisonai.replay.storage import get_trace_path, get_traces_dir

    monkeypatch.delenv("PRAISONAI_TRACES_DIR", raising=False)
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path / "home"))
    assert get_traces_dir() == tmp_path / "home" / "traces"
    assert get_trace_path("abc") == tmp_path / "home" / "traces" / "abc.jsonl"


def test_traces_dir_default_is_home_dot_praison(tmp_path, monkeypatch):
    from praisonai.replay.storage import resolve_traces_dir

    monkeypatch.delenv("PRAISONAI_TRACES_DIR", raising=False)
    monkeypatch.delenv("PRAISON_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert resolve_traces_dir() == tmp_path / ".praison" / "traces"


def test_praison_home_matches_last_run_pointer_root(tmp_path, monkeypatch):
    """Replay traces and the last-run pointer share one state root."""
    from praisonaiagents.trace.last_run import last_run_pointer_path
    from praisonai.replay.storage import resolve_traces_dir

    monkeypatch.delenv("PRAISONAI_TRACES_DIR", raising=False)
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    assert resolve_traces_dir().parent == last_run_pointer_path().parent


def test_writer_and_list_follow_env(traces_dir):
    from praisonai.replay import ContextTraceWriter, list_traces

    w = ContextTraceWriter(session_id="envrun")
    assert w.path == traces_dir / "envrun.jsonl"
    w.close()
    w.path.write_text('{"event_type": "session_start"}\n')
    assert [t.session_id for t in list_traces()] == ["envrun"]


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------

def _lines(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def test_record_writes_session_start_and_end(traces_dir):
    from praisonaiagents.trace.context_events import get_context_emitter
    from praisonai.replay import record

    with record(meta={"yaml_path": "/x/agents.yaml"}) as rec:
        assert rec.run_id.startswith("run-")
        assert rec.path == traces_dir / f"{rec.run_id}.jsonl"
        emitter = get_context_emitter()
        assert emitter.enabled and emitter.session_id == rec.run_id
        emitter.agent_start("A")
        emitter.agent_end("A")
    assert not get_context_emitter().enabled  # reset afterwards

    events = _lines(rec.path)
    assert [e["event_type"] for e in events] == ["session_start", "agent_start", "agent_end", "session_end"]
    assert events[0]["data"] == {"yaml_path": "/x/agents.yaml", "run_id": rec.run_id}
    assert events[-1]["data"]["status"] == "completed"


def test_record_explicit_run_id(traces_dir):
    from praisonai.replay import record

    with record("my-run") as rec:
        pass
    assert rec.run_id == "my-run" and rec.path.name == "my-run.jsonl"


def test_record_live_flushes_every_event(traces_dir):
    from praisonai.replay import record

    with record(live=True) as rec:
        assert len(_lines(rec.path)) == 1  # session_start already on disk
        rec.emitter.agent_start("A")
        assert len(_lines(rec.path)) == 2


def test_record_batched_by_default(traces_dir):
    from praisonai.replay import record

    with record() as rec:
        rec.emitter.agent_start("A")
        assert not rec.path.exists() or _lines(rec.path) == []
    assert len(_lines(rec.path)) == 3


def test_record_marks_failure_and_resets_on_exception(traces_dir):
    from praisonaiagents.trace.context_events import get_context_emitter
    from praisonai.replay import record

    with pytest.raises(ValueError):
        with record() as rec:
            raise ValueError("boom")
    assert _lines(rec.path)[-1]["data"]["status"] == "failed"
    assert not get_context_emitter().enabled


def test_record_redacts_by_default(traces_dir):
    from praisonai.replay import record

    with record() as rec:
        rec.emitter.tool_call_start("A", "search", {"q": "x", "api_key": "sk-secret-value-123456"})
    text = rec.path.read_text()
    assert "sk-secret-value-123456" not in text and "[REDACTED]" in text


def test_record_forked_from_is_stamped_on_workflow_start(traces_dir):
    from praisonaiagents.trace.context_events import ContextEvent
    from praisonai.replay.recorder import record

    with record(_forked_from={"run_id": "run-a", "node_id": "task:write"}) as rec:
        ev = ContextEvent.from_dict({"event_type": "session_start", "session_id": rec.run_id})
        ev.event_type = "workflow_start"  # what a 1.1 emitter emits
        ev.data = {"kind": "team"}
        rec.emitter._emit(ev)
    events = _lines(rec.path)
    assert events[0]["data"]["forked_from"] == {"run_id": "run-a", "node_id": "task:write"}
    assert events[1]["data"] == {"kind": "team", "forked_from": {"run_id": "run-a", "node_id": "task:write"}}


# ---------------------------------------------------------------------------
# The three callers that used to duplicate the setup still record
# ---------------------------------------------------------------------------

def test_recipe_save_replay_closes_trace_on_early_failure(traces_dir, monkeypatch):
    """A recipe that is not found used to leave the trace open and the emitter set."""
    from praisonaiagents.trace.context_events import get_context_emitter
    from praisonai.recipe import core

    monkeypatch.setattr(core, "_load_recipe", lambda name, offline=False: None)
    result = core._run_impl("nope", options={"save_replay": True, "trace_name": "recipe-run"})
    assert result.error and "not found" in result.error
    assert not get_context_emitter().enabled
    events = _lines(traces_dir / "recipe-run.jsonl")
    assert events[0]["event_type"] == "session_start"
    assert events[0]["data"] == {"recipe": "nope", "run_id": "recipe-run"}
    assert events[-1]["event_type"] == "session_end"
    assert events[-1]["data"]["status"] == "failed"


def test_recipe_save_replay_success_passes_emitter(traces_dir, monkeypatch):
    from types import SimpleNamespace

    from praisonaiagents.trace.context_events import get_context_emitter
    from praisonai.recipe import core

    cfg = SimpleNamespace(name="r", version="1.0", defaults={})
    seen = {}

    def fake_execute(recipe_config, merged, session_id, options, trace_emitter=None):
        seen["emitter"] = trace_emitter
        seen["active"] = get_context_emitter()
        trace_emitter.agent_start("RecipeAgent")
        return {"ok": True}

    monkeypatch.setattr(core, "_load_recipe", lambda name, offline=False: cfg)
    monkeypatch.setattr(core, "_check_dependencies", lambda c: {"all_satisfied": True})
    monkeypatch.setattr(core, "_check_tool_policy", lambda c, o: None)
    monkeypatch.setattr(core, "_execute_recipe", fake_execute)
    result = core._run_impl("r", options={"save_replay": True, "trace_name": "recipe-ok"})
    assert result.output == {"ok": True}
    assert seen["emitter"] is seen["active"] and seen["emitter"].enabled
    events = _lines(traces_dir / "recipe-ok.jsonl")
    assert [e["event_type"] for e in events] == ["session_start", "agent_start", "session_end"]
    assert events[-1]["data"]["status"] == "completed"
    assert not get_context_emitter().enabled


class _FakeWorkflow:
    name = "wf"
    steps = []
    planning = False
    reasoning = False
    framework = "praisonai"
    default_input = "hello"
    verbose = False

    def __init__(self):
        self.variables = {}
        self.seen_emitter = None

    def start(self, _input):
        from praisonaiagents.trace.context_events import get_context_emitter

        self.seen_emitter = get_context_emitter()
        self.seen_emitter.agent_start("Step")
        return {"status": "completed", "output": "done"}


def _run_workflow_command(monkeypatch, yaml_file, action_args):
    from praisonaiagents.workflows import WorkflowManager
    from praisonai.cli.legacy import workflow_commands

    wf = _FakeWorkflow()
    monkeypatch.setattr(WorkflowManager, "load_yaml", lambda self, path, tool_registry=None: wf)
    code = workflow_commands._run_yaml_workflow(None, str(yaml_file), action_args)
    return code, wf


def test_workflow_run_save_records(traces_dir, tmp_path, monkeypatch):
    from praisonaiagents.trace.context_events import get_context_emitter

    y = tmp_path / "wf.yaml"
    y.write_text("name: wf\nsteps: []\n")
    code, wf = _run_workflow_command(monkeypatch, y, ["--save"])
    assert code == 0
    assert wf.seen_emitter.enabled
    assert not get_context_emitter().enabled
    events = _lines(traces_dir / f"{wf.seen_emitter.session_id}.jsonl")
    assert events[0]["data"]["workflow"] == str(y)
    assert events[0]["data"]["yaml_path"] == str(y.resolve())
    assert [e["event_type"] for e in events] == ["session_start", "agent_start", "session_end"]


def test_workflow_run_yaml_save_replay_key_records(traces_dir, tmp_path, monkeypatch):
    y = tmp_path / "wf.yaml"
    y.write_text("name: wf\nsave_replay: true\nsteps: []\n")
    code, wf = _run_workflow_command(monkeypatch, y, [])
    assert code == 0 and wf.seen_emitter.enabled
    assert (traces_dir / f"{wf.seen_emitter.session_id}.jsonl").exists()


def test_workflow_run_without_save_does_not_record(traces_dir, tmp_path, monkeypatch):
    y = tmp_path / "wf.yaml"
    y.write_text("name: wf\nsteps: []\n")
    code, wf = _run_workflow_command(monkeypatch, y, [])
    assert code == 0 and not wf.seen_emitter.enabled
    assert not traces_dir.exists() or not list(traces_dir.iterdir())


def _drive_legacy_main(monkeypatch, tmp_path, argv, yaml_text):
    import sys

    pa = pytest.importorskip("praisonai_code.cli.legacy.praison_ai")
    from praisonaiagents.trace.context_events import get_context_emitter

    seen = {}

    class FakeGenerator:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def generate_crew_and_kickoff(self):
            seen["emitter"] = get_context_emitter()
            return "RESULT"

    (tmp_path / "agents.yaml").write_text(yaml_text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    monkeypatch.setattr(pa, "_get_agents_generator", lambda: FakeGenerator)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    result = pa.PraisonAI(agent_file="agents.yaml").main()
    return result, seen.get("emitter")


_AGENTS_YAML = (
    "framework: praisonai\nroles:\n  a:\n    role: A\n    goal: g\n    backstory: b\n"
    "    tasks:\n      t:\n        description: d\n        expected_output: e\n"
)


def test_agents_yaml_save_flag_records(traces_dir, tmp_path, monkeypatch):
    from praisonaiagents.trace.context_events import get_context_emitter

    result, emitter = _drive_legacy_main(monkeypatch, tmp_path, ["praisonai", "agents.yaml", "--save"], _AGENTS_YAML)
    assert result == "RESULT"
    assert emitter is not None and emitter.enabled
    assert not get_context_emitter().enabled
    events = _lines(traces_dir / f"{emitter.session_id}.jsonl")
    assert events[0]["data"]["agents_file"] == "agents.yaml"
    assert events[0]["data"]["yaml_path"] == str((tmp_path / "agents.yaml").resolve())
    assert events[-1]["event_type"] == "session_end"


def test_agents_yaml_save_replay_key_records(traces_dir, tmp_path, monkeypatch):
    result, emitter = _drive_legacy_main(
        monkeypatch, tmp_path, ["praisonai", "agents.yaml"], "save_replay: true\n" + _AGENTS_YAML
    )
    assert result == "RESULT" and emitter.enabled
    assert (traces_dir / f"{emitter.session_id}.jsonl").exists()


def test_agents_yaml_without_save_is_untraced(traces_dir, tmp_path, monkeypatch):
    result, emitter = _drive_legacy_main(monkeypatch, tmp_path, ["praisonai", "agents.yaml"], _AGENTS_YAML)
    assert result == "RESULT" and not emitter.enabled


def test_save_replay_is_a_known_yaml_field():
    from praisonai.config.schema import YAMLConfig

    assert "save_replay" in YAMLConfig.model_fields
