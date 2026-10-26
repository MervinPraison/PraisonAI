"""``praisonai replay`` CLI: flow (mermaid / YAML), export, view, and 1.0 traces still readable."""

import json
import re
import textwrap

import pytest
from typer.testing import CliRunner


def _invoke(*args):
    from praisonai.cli.commands.replay import app

    return CliRunner().invoke(app, list(args))


FLOW_YAML = textwrap.dedent("""\
    name: blog-flow
    process: workflow
    input: AI
    agents:
      researcher:
        role: Researcher
        goal: Research
        instructions: You research.
      writer:
        role: Writer
        goal: Write
        instructions: You write.
    steps:
      - name: research
        agent: researcher
        action: "Research {{input}}"
      - name: draft
        agent: writer
        action: "Write about {{previous_output}}"
""")


@pytest.fixture
def flow_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    y = tmp_path / "flow.yaml"
    y.write_text(FLOW_YAML)
    return y


# ---------------------------------------------------------------------------
# flow
# ---------------------------------------------------------------------------

def test_flow_mermaid_on_yaml_is_the_static_graph(flow_yaml, monkeypatch):
    from praisonai.replay import yaml_run

    result = _invoke("flow", str(flow_yaml), "--format", "mermaid")
    assert result.exit_code == 0, result.output
    expected = yaml_run.static_mermaid(flow_yaml)
    assert result.output == expected
    assert result.output.startswith(("graph", "flowchart"))
    assert "researcher" in result.output and "writer" in result.output


def test_flow_mermaid_on_yaml_falls_back_without_core_to_graph(flow_yaml, monkeypatch):
    """Without ``to_graph`` in the SDK, the existing AgentFlow.to_mermaid() is used."""
    from praisonai.replay import yaml_run

    monkeypatch.setattr(yaml_run, "_core_diagram", lambda name: None)
    result = _invoke("flow", str(flow_yaml), "--format", "mermaid")
    assert result.exit_code == 0, result.output
    assert result.output == yaml_run.load_flow(flow_yaml).to_mermaid()


def test_flow_json_on_yaml_is_a_graph(flow_yaml):
    result = _invoke("flow", str(flow_yaml), "--format", "json")
    assert result.exit_code == 0, result.output
    graph = json.loads(result.output)
    assert graph["schema"] == "praisonai.graph/1"
    ids = [n["id"] for n in graph["nodes"]]
    assert "start:begin" in ids and "end:done" in ids


def test_flow_mermaid_on_a_run_is_a_sequence_diagram(traces_dir, fx):
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    result = _invoke("flow", "run-team01", "--format", "mermaid")
    assert result.exit_code == 0, result.output
    assert result.output.startswith("sequenceDiagram\n")
    assert "A0->>A1: handoff: draft it" in result.output


def test_flow_rejects_unknown_format(traces_dir, fx):
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    assert _invoke("flow", "run-team01", "--format", "dot").exit_code == 2


# ---------------------------------------------------------------------------
# 1.0 traces keep working with show / flow
# ---------------------------------------------------------------------------

def test_legacy_trace_show_and_flow(traces_dir, fx):
    fx.write_trace(traces_dir, "run-legacy1", fx.legacy_events())
    shown = _invoke("show", "run-legacy1", "--json")
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["total_events"] == 9

    flow = _invoke("flow", "run-legacy1")
    assert flow.exit_code == 0, flow.output
    assert "Researcher" in flow.output and "Writer" in flow.output

    flow_json = _invoke("flow", "run-legacy1", "--format", "json")
    assert json.loads(flow_json.output)["agent_order"] == ["Researcher", "Writer"]

    mermaid = _invoke("flow", "run-legacy1", "--format", "mermaid")
    assert mermaid.exit_code == 0 and "A0->>A1: handoff: next" in mermaid.output


def test_schema_1_1_trace_show_and_flow(traces_dir, fx):
    """New event types must not break the existing readers."""
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    assert _invoke("show", "run-team01").exit_code == 0
    flow = _invoke("flow", "run-team01", "--format", "json")
    assert flow.exit_code == 0
    assert set(json.loads(flow.output)["agent_order"]) == {"Researcher"}


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_html_default_file(traces_dir, fx, tmp_path, monkeypatch):
    from praisonai.replay import export

    monkeypatch.setattr(export, "aiui_renderer_files", lambda: None)
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    monkeypatch.chdir(tmp_path)
    result = _invoke("export", "run-team01")
    assert result.exit_code == 0, result.output
    html = (tmp_path / "run-team01.html").read_text()
    assert "window.__REPLAY_DATA__" in html
    assert "sk-abcdefghijklmnop1234" not in html


@pytest.mark.parametrize("fmt", ["json", "mermaid", "otel"])
def test_export_formats_to_file(traces_dir, fx, tmp_path, fmt):
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    out = tmp_path / f"out.{fmt}"
    result = _invoke("export", "run-team01", "--format", fmt, "-o", str(out))
    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert "sk-abcdefghijklmnop1234" not in text
    if fmt == "json":
        assert json.loads(text)["run_id"] == "run-team01"
    elif fmt == "otel":
        assert json.loads(text)["resourceSpans"][0]["scopeSpans"][0]["spans"]
    else:
        assert text.startswith("sequenceDiagram")


def test_export_no_redact(traces_dir, fx):
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    result = _invoke("export", "run-team01", "--format", "json", "--no-redact")
    assert result.exit_code == 0
    assert "sk-abcdefghijklmnop1234" in result.output


def test_export_missing_run(traces_dir):
    result = _invoke("export", "run-nope", "--format", "json")
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# view (aiui is never actually started here)
# ---------------------------------------------------------------------------

class _FakeProc:
    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0

    def terminate(self):
        pass


@pytest.fixture
def fake_aiui(monkeypatch):
    from praisonai.cli.commands import replay as replay_cli

    calls = {}

    def spawn(app_path, host, port, env):
        calls["spawn"] = {"app": app_path, "host": host, "port": port, "env": env}
        return _FakeProc()

    monkeypatch.setattr(replay_cli, "_aiui_installed", lambda: True)
    monkeypatch.setattr(replay_cli, "_spawn_aiui", spawn)
    monkeypatch.setattr(replay_cli, "_open_browser", lambda url, host, port: calls.setdefault("url", url))
    monkeypatch.setattr(replay_cli, "_start_yaml_run", lambda y, run_id: calls.setdefault("yaml_run", (y, run_id)))
    return calls


def test_view_help():
    result = _invoke("view", "--help")
    assert result.exit_code == 0
    # Rich forces colour on CI (GITHUB_ACTIONS), which splits flags with ANSI codes.
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    for flag in ("--live", "--port", "--host"):
        assert flag in output


def test_view_run_opens_replay_page(traces_dir, fx, fake_aiui):
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    result = _invoke("view", "run-team01")
    assert result.exit_code == 0, result.output
    assert fake_aiui["url"] == "http://127.0.0.1:8090/#/replay?run=run-team01"
    spawn = fake_aiui["spawn"]
    assert spawn["app"].name == "default_app.py" and spawn["app"].parent.name == "ui_replay"
    assert spawn["app"].exists()
    assert (spawn["host"], spawn["port"]) == ("127.0.0.1", 8090)
    assert spawn["env"]["PRAISONAI_TRACES_DIR"] == str(traces_dir)
    assert "WARNING" not in result.output


def test_view_jsonl_path_serves_its_directory(tmp_path, fx, fake_aiui, monkeypatch):
    monkeypatch.delenv("PRAISONAI_TRACES_DIR", raising=False)
    path = fx.write_trace(tmp_path / "elsewhere", "run-team01", fx.team_events())
    result = _invoke("view", str(path), "--port", "9001")
    assert result.exit_code == 0, result.output
    assert fake_aiui["spawn"]["env"]["PRAISONAI_TRACES_DIR"] == str(tmp_path / "elsewhere")
    assert fake_aiui["url"] == "http://127.0.0.1:9001/#/replay?run=run-team01"


def test_view_yaml_runs_it_recorded_live(traces_dir, flow_yaml, fake_aiui):
    result = _invoke("view", str(flow_yaml))
    assert result.exit_code == 0, result.output
    yaml_file, run_id = fake_aiui["yaml_run"]
    assert yaml_file == str(flow_yaml) and run_id.startswith("run-")
    assert fake_aiui["url"] == f"http://127.0.0.1:8090/#/replay?run={run_id}&live=1"


def test_view_non_loopback_host_warns(traces_dir, fx, fake_aiui):
    fx.write_trace(traces_dir, "run-team01", fx.team_events())
    result = _invoke("view", "run-team01", "--host", "0.0.0.0")
    assert result.exit_code == 0
    assert "WARNING" in result.output and "0.0.0.0" in result.output
    assert fake_aiui["url"].startswith("http://127.0.0.1:8090/")


def test_view_missing_run_fails(traces_dir, fake_aiui):
    result = _invoke("view", "run-nope")
    assert result.exit_code == 1
    assert "spawn" not in fake_aiui


def test_view_live_allows_a_run_that_has_not_started(traces_dir, fake_aiui):
    result = _invoke("view", "run-soon", "--live")
    assert result.exit_code == 0
    assert fake_aiui["url"].endswith("?run=run-soon&live=1")


def test_view_without_aiui_gives_install_hint(traces_dir, monkeypatch):
    from praisonai.cli.commands import replay as replay_cli

    spawned = []
    monkeypatch.setattr(replay_cli, "_aiui_installed", lambda: False)
    monkeypatch.setattr(replay_cli, "_spawn_aiui", lambda *a: spawned.append(a))
    result = _invoke("view")
    assert result.exit_code == 1
    assert 'pip install "praisonai[ui]"' in result.output
    assert spawned == []


def test_replay_preset_targets_the_replay_page():
    import ast

    from praisonai.cli.commands.replay import _replay_app_path

    tree = ast.parse(_replay_app_path().read_text())
    pages = [
        kw.value for node in ast.walk(tree) if isinstance(node, ast.Call)
        for kw in node.keywords if kw.arg == "pages"
    ]
    assert pages and ast.literal_eval(pages[0]) == ["replay"]


def test_view_stops_the_server_when_the_cli_exits():
    from praisonai.cli.commands.replay import _wait_for_server

    class Running:
        terminated = False

        def wait(self, timeout=None):
            if timeout is None:
                raise KeyboardInterrupt
            return 0

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

    proc = Running()
    assert _wait_for_server(proc) == 0
    assert proc.terminated


def test_team_yaml_static_graph_uses_the_run_ids(tmp_path):
    """A team YAML's map is built from the same AgentTeam a run builds (task:/agent: ids)."""
    import pytest

    from praisonai.replay import yaml_run

    if yaml_run._core_diagram("to_graph") is None:
        pytest.skip("SDK has no to_graph (pre schema 1.1)")
    path = tmp_path / "team.yaml"
    path.write_text(
        "framework: praisonai\n"
        "topic: t\n"
        "roles:\n"
        "  researcher:\n    role: Researcher\n    goal: g\n    backstory: b\n"
        "    tasks:\n      research:\n        description: d\n        expected_output: e\n"
        "  writer:\n    role: Writer\n    goal: g\n    backstory: b\n"
        "    tasks:\n      write:\n        description: d\n        expected_output: e\n",
        encoding="utf-8",
    )
    graph, _ = yaml_run.static_graph(path)
    ids = {n["id"] for n in graph["nodes"]}
    assert {"agent:Researcher", "agent:Writer", "task:0", "task:1"} <= ids
    assert not any(i.startswith("step:") for i in ids)
