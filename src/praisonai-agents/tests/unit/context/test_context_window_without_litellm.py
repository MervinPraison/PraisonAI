"""G-08: a tool-using agent on the OpenAI-client path must not import litellm.

``context/budgeter.py`` imported litellm only to read a model's context
window, which made the first ``start()`` of any agent with a tool cost about
3 s and load ~3,000 modules. The same data ships with litellm as a JSON file;
reading it gives the same limits without the import.
"""

import importlib.util
import json
import os
import subprocess
import sys
import textwrap

import pytest

from praisonaiagents.context import budgeter

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_SCRIPT = textwrap.dedent('''
    import json, os, sys, threading, http.server, io, contextlib
    os.environ["OPENAI_API_KEY"] = "sk-local-fake"
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
            msgs = req.get("messages", [])
            if req.get("tools") and not any(m.get("role") == "tool" for m in msgs):
                msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "c", "type": "function",
                       "function": {"name": "add", "arguments": '{"a": 1, "b": 2}'}}]}; fin = "tool_calls"
            else:
                msg = {"role": "assistant", "content": "3"}; fin = "stop"
            b = json.dumps({"id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
                            "choices": [{"index": 0, "message": msg, "finish_reason": fin}],
                            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            self.send_response(200); self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # Point both base-URL variables the SDK reads at the stub (CI sets OPENAI_API_BASE).
    os.environ["OPENAI_BASE_URL"] = os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:%d/v1" % srv.server_address[1]
    from praisonaiagents import Agent
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    with contextlib.redirect_stdout(io.StringIO()):
        out = Agent(name="x", instructions="Be brief", llm="gpt-4o-mini", tools=[add], output="silent").start("1+2?")
    print(json.dumps({"out": out, "litellm": "litellm" in sys.modules}))
''')


def test_tool_agent_turn_does_not_import_litellm(tmp_path):
    env = dict(os.environ, PYTHONPATH=PKG_ROOT, PRAISONAI_HOME=str(tmp_path))
    env.pop("OPENAI_BASE_URL", None)
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["out"] == "3"
    assert result["litellm"] is False


@pytest.mark.parametrize("model,expected", [("gpt-5", 272000), ("o1", 200000), ("gpt-4o-mini", 128000)])
def test_limits_match_litellm_data_without_importing_it(monkeypatch, model, expected):
    monkeypatch.delitem(sys.modules, "litellm", raising=False)
    if importlib.util.find_spec("litellm") is None:
        pytest.skip("litellm not installed; static table is the only source")
    # litellm is installed, so its bundled data must load; an empty dict here
    # means the file lookup broke and lookups silently fell back to the table.
    assert budgeter._bundled_model_cost(), "litellm installed but bundled model data did not load"
    assert budgeter.get_model_limit(model) == expected
    assert "litellm" not in sys.modules
