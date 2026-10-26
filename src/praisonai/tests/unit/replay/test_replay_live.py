"""praisonai.replay.replay_app / watch: a page with a Run button that records each run live."""

import json
import sys
import threading

import pytest


def _flow(seen=None):
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import StepResult

    def research(ctx):
        if seen is not None:
            seen.append(ctx.input)
        return StepResult(output="notes")

    def write(ctx):
        return StepResult(output="article")

    return AgentFlow(name="Article", steps=[research, write])


def _events(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_runner_records_a_flow_under_the_given_run_id(traces_dir):
    from praisonai.replay.live import _runner

    seen = []
    _runner(_flow(seen))("solar sails", "run-live00000001")
    path = traces_dir / "run-live00000001.jsonl"
    types = [e["event_type"] for e in _events(path)]
    assert seen == ["solar sails"]
    assert types[0] == "session_start" and types[-1] == "session_end"
    assert types.count("step_end") == 2


def test_runner_resets_a_team_before_each_run(traces_dir):
    from praisonai.replay.live import _runner

    calls = []

    class Team:
        def _reset_task_state_for_item(self):
            calls.append("reset")

        def start(self, text):
            calls.append(("start", text))

    run = _runner(Team())
    run("a", "run-team-a")
    run("b", "run-team-b")
    assert calls == ["reset", ("start", "a"), "reset", ("start", "b")]


def test_runner_accepts_a_plain_callable(traces_dir):
    from praisonai.replay.live import _runner

    got = []
    _runner(lambda text: got.append(text))("hi", "run-fn")
    assert got == ["hi"] and (traces_dir / "run-fn.jsonl").is_file()


def test_runner_runs_a_yaml_file_as_written(monkeypatch, tmp_path):
    from praisonai.replay import live, yaml_run

    calls = []
    monkeypatch.setattr(yaml_run, "run_yaml_recorded", lambda path, **kw: calls.append((path, kw)))
    yml = tmp_path / "agents.yaml"
    yml.write_text("roles: {}\n")
    live._runner(str(yml))("ignored", "run-yaml")
    assert calls == [(str(yml), {"run_id": "run-yaml", "live": True})]


def test_runner_rejects_bad_targets():
    from praisonai.replay.live import _runner

    assert _runner(None) is None
    with pytest.raises(ValueError, match="not a YAML file"):
        _runner("notes.txt")
    with pytest.raises(TypeError, match="Agent, AgentTeam, AgentFlow"):
        _runner(42)


def test_replay_app_explains_how_to_install_aiui(monkeypatch):
    from praisonai.replay import replay_app

    monkeypatch.setitem(sys.modules, "praisonaiui.features.replay", None)
    with pytest.raises(ImportError, match=r'pip install -U "praisonai\[ui\]"'):
        replay_app()


def _aiui_embed():
    mod = pytest.importorskip("praisonaiui.features.replay")
    if not hasattr(mod, "create_replay_app"):
        pytest.skip("installed aiui predates create_replay_app")
    return mod


def test_run_button_records_and_serves_the_run_end_to_end(traces_dir):
    """Mounted like app.mount('/replay', replay_app(flow)): Run, then read the run back."""
    _aiui_embed()
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.testclient import TestClient

    from praisonai.replay import replay_app

    traces_dir.mkdir(parents=True, exist_ok=True)
    seen = []
    client = TestClient(Starlette(routes=[Mount("/replay", app=replay_app(_flow(seen), input="solar sails"))]))
    page = client.get("/replay/").text
    assert "PraisonAI Replay: Article" in page and '"runner"' in page
    run_id = client.post("/replay/api/replay/run", json={"input": "comets"}).json()["run_id"]
    for _ in range(200):
        data = client.get(f"/replay/api/replay/runs/{run_id}/events?wait=1").json()
        if data["run"] and data["events"][-1]["event_type"] == "session_end":
            break
        threading.Event().wait(0.02)  # time.sleep may be stubbed by the suite
    assert seen == ["comets"]
    assert data["run"]["status"] == "completed"
    assert [e.get("node_id") for e in data["events"] if e["event_type"] == "step_end"] == ["step:research", "step:write"]


def test_yaml_target_has_no_input_box():
    _aiui_embed()
    from starlette.testclient import TestClient

    from praisonai.replay import replay_app

    page = TestClient(replay_app("agents.yaml")).get("/").text
    assert '"ask":false' in page and "agents.yaml" in page
