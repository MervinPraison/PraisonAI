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


def test_output_file_and_metrics_json(mock_endpoint, tmp_path, capsys):
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
    assert failure("text", [], 0) is None
    assert failure({"task_status": {0: "failed", 1: "completed"}}, [], 0) == "1 of 2 task(s) failed"

    missing = SimpleNamespace(output_file=str(tmp_path / "missing.md"))
    assert failure("text", [missing], 0) is None  # only checked for --trust runs
    assert "missing.md" in failure("text", [missing], 0, check_files=True)

    written = tmp_path / "written.md"
    written.write_text("x")
    assert failure("text", [SimpleNamespace(output_file=str(written))], 0, check_files=True) is None
