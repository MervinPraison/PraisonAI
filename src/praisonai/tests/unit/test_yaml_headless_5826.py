"""Headless YAML team runs: --metrics, task output_file, non-zero exit on failure (#5826)."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter


class _MockOpenAI(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible endpoint (chat + responses) reporting usage."""

    fail = False

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        if self.fail:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"boom"}}')
            return
        model = body.get("model", "m")
        if "responses" in self.path:
            out = {
                "id": "r1", "object": "response", "created_at": 1, "status": "completed",
                "model": model, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
                "output": [{
                    "type": "message", "id": "m1", "status": "completed", "role": "assistant",
                    "content": [{"type": "output_text", "text": "FINAL TEXT", "annotations": []}],
                }],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
        else:
            out = {
                "id": "c1", "object": "chat.completion", "created": 1, "model": model,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "FINAL TEXT"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(autouse=True)
def _project_root(tmp_path, monkeypatch):
    # Task output_file writes are contained to the project root (#5770); these
    # runs write under tmp_path, so make it the root.
    monkeypatch.setenv("PRAISONAI_PROJECT_ROOT", str(tmp_path))


@pytest.fixture
def mock_endpoint(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _MockOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setenv("PRAISONAI_TELEMETRY_DISABLED", "true")
    yield server
    server.shutdown()


def _config(tmp_path):
    def role(name, output_file=None):
        task = {"description": f"{name} task", "expected_output": "text"}
        if output_file:
            task["output_file"] = str(output_file)
        return {
            "role": name, "goal": "g", "backstory": "b", "llm": "openai/gpt-4o-mini",
            "tasks": {f"{name.lower()}_task": task},
        }

    return {
        "framework": "praisonai",
        "topic": "risk",
        "roles": {
            "analyst": role("Analyst"),
            "writer": role("Writer", tmp_path / "out" / "risk_report.md"),
            "reviewer": role("Reviewer", tmp_path / "flat.md"),
        },
    }


def _run(config, cli_config=None):
    return asyncio.run(PraisonAIAdapter().arun(
        config, [{"model": "openai/gpt-4o-mini"}], "risk", tools_dict={}, cli_config=cli_config,
    ))


def test_yaml_cli_config_forwards_metrics_flags():
    from praisonai_code.cli.legacy.praison_ai import PraisonAI

    cli = object.__new__(PraisonAI)
    cli.args = SimpleNamespace(metrics=True, metrics_json=True, tool_retry_attempts=1)
    config = cli._extract_cli_config_for_yaml()
    assert config["metrics"] is True and config["metrics_json"] is True

    cli.args = SimpleNamespace(tool_retry_attempts=1)
    config = cli._extract_cli_config_for_yaml()
    assert "metrics" not in config and "metrics_json" not in config


def test_output_file_and_metrics_json(mock_endpoint, tmp_path, capsys, monkeypatch):
    # output_file writes are contained in the project root (#5770).
    monkeypatch.setenv("PRAISONAI_PROJECT_ROOT", str(tmp_path))
    result = _run(_config(tmp_path), {"metrics_json": True, "trust": True})

    assert "FINAL TEXT" in result
    assert (tmp_path / "out" / "risk_report.md").read_text() == "FINAL TEXT"
    assert (tmp_path / "flat.md").read_text() == "FINAL TEXT"

    out = capsys.readouterr().out
    report = json.loads(out[out.index("{"):out.rindex("}") + 1])
    assert [a["name"] for a in report["agents"]] == ["Analyst", "Writer", "Reviewer"]
    for key in ("input_tokens", "output_tokens", "total_tokens", "calls"):
        assert report["total"][key] == sum(a[key] for a in report["agents"])
    assert all(a["latency_s"] > 0 and a["calls"] >= 1 for a in report["agents"])
    assert report["model"]


def test_no_metrics_output_without_flag(mock_endpoint, tmp_path, capsys):
    _run(_config(tmp_path))
    out = capsys.readouterr().out
    assert "TOTAL" not in out and "latency_s" not in out


def test_failed_run_raises(mock_endpoint, tmp_path, monkeypatch):
    monkeypatch.setattr(_MockOpenAI, "fail", True)
    config = _config(tmp_path)
    config["roles"] = {"analyst": config["roles"]["analyst"]}
    with pytest.raises(RuntimeError, match="task\\(s\\) failed"):
        _run(config)


def test_run_failure_detection(tmp_path):
    failure = PraisonAIAdapter._run_failure
    done = lambda path=None: SimpleNamespace(status="completed", output_file=path)
    assert failure("text", [done()], set()) is None
    assert failure({"task_status": {0: "failed", 1: "completed"}}, [], set()) == "1 of 2 task(s) failed"
    # Text response from the last task must not hide an earlier failed task.
    failed = SimpleNamespace(status="failed", output_file=None)
    assert failure("text", [failed, done()], set()) == "1 of 2 task(s) failed"

    path = str(tmp_path / "out.md")
    assert failure("text", [done(path)], set()) is None  # only checked for --trust runs
    assert "out.md" in failure("text", [done(path)], set(), check_files=True)
    assert failure("text", [done(path)], {path}, check_files=True) is None
    # A task that never ran (e.g. skipped workflow branch) is not a write failure.
    skipped = SimpleNamespace(status="not started", output_file=path)
    assert failure("text", [skipped], set(), check_files=True) is None


def test_stale_output_file_is_not_counted_as_written(tmp_path):
    path = tmp_path / "report.md"
    path.write_text("OLD RUN")
    task = SimpleNamespace(output_file=str(path))
    team = SimpleNamespace(save_output_to_file=lambda t, out: None)  # write silently fails
    written = PraisonAIAdapter._track_output_files(team)
    team.save_output_to_file(task, "NEW RUN")
    assert written == set()

    team = SimpleNamespace(save_output_to_file=lambda t, out: path.write_text(str(out)))
    written = PraisonAIAdapter._track_output_files(team)
    team.save_output_to_file(task, "NEW RUN")
    assert written == {str(path)}


def test_run_metrics_counts_calls_and_closes_failed_timers():
    from praisonaiagents.telemetry.token_collector import TokenMetrics, get_token_collector
    from praisonai.framework_adapters._run_metrics import RunMetrics

    agent = SimpleNamespace(name="Analyst", _approval_scope_id="id-1")
    team = SimpleNamespace(
        agents=[agent], on_task_start=None, on_task_complete=None,
        get_token_usage_summary=lambda: {"by_agent": {}},
    )
    metrics = RunMetrics(team)
    collector = get_token_collector()
    for _ in range(150):  # more than the collector's recent-history cap
        collector.track_tokens("m", "Analyst", TokenMetrics(), agent_id="id-1")
    collector.track_tokens("m", "Analyst", TokenMetrics(), agent_id="other-team")
    team.on_task_start(SimpleNamespace(agent=agent), 0)  # task fails: no complete hook
    metrics.close()
    collector.track_tokens("m", "Analyst", TokenMetrics(), agent_id="id-1")  # after run

    row = metrics.report("m")["agents"][0]
    assert row["calls"] == 150
    assert row["latency_s"] >= 0 and "Analyst" in metrics.latency
    assert "track_tokens" not in collector.__dict__ and team.on_task_start is None


def test_crlf_output_file_counts_as_written(tmp_path):
    path = tmp_path / "report.md"
    task = SimpleNamespace(output_file=str(path))

    def save(t, out):  # mirrors core: text-mode write of str(task_output)
        with open(t.output_file, "w") as f:
            f.write(str(out))

    team = SimpleNamespace(save_output_to_file=save)
    written = PraisonAIAdapter._track_output_files(team)
    team.save_output_to_file(task, "line one\r\nline two\r\n")
    assert written == {str(path)}


def test_overlapping_run_metrics_closed_out_of_order_keep_counts():
    from praisonaiagents.telemetry.token_collector import TokenMetrics, get_token_collector
    from praisonai.framework_adapters._run_metrics import RunMetrics

    def _team(name, agent_id):
        return SimpleNamespace(
            agents=[SimpleNamespace(name=name, _approval_scope_id=agent_id)],
            on_task_start=None, on_task_complete=None,
            get_token_usage_summary=lambda: {"by_agent": {}},
        )

    collector = get_token_collector()
    first, second = RunMetrics(_team("A", "id-a")), RunMetrics(_team("B", "id-b"))
    first.close()  # first run finishes before the second
    collector.track_tokens("m", "B", TokenMetrics(), agent_id="id-b")
    collector.track_tokens("m", "A", TokenMetrics(), agent_id="id-a")
    second.close()

    assert second.calls == {"B": 1}
    assert first.calls == {}
    collector.__dict__.pop("track_tokens", None)  # drop the inert pass-through
