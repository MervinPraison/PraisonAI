"""Import guard: the core stays light on import and on the default path.

``from praisonaiagents import Agent`` must not load litellm, openai or
posthog, and a tool-using turn on a bare model name (the OpenAI-client route)
must still not load litellm. Checked in a fresh interpreter so other tests'
imports cannot hide a regression.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HEAVY = ("litellm", "openai", "posthog")

_STUB = textwrap.dedent('''
    import json, os, threading, http.server
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
            if req.get("tools") and not any(m.get("role") == "tool" for m in req.get("messages", [])):
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
    os.environ["OPENAI_BASE_URL"] = os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:%d/v1" % srv.server_address[1]
''')


def _run(script, tmp_path):
    env = dict(os.environ, PYTHONPATH=PKG_ROOT, PRAISONAI_HOME=str(tmp_path), OPENAI_API_KEY="sk-local-fake")
    env.pop("OPENAI_BASE_URL", None)
    env.pop("OPENAI_API_BASE", None)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_importing_agent_loads_no_heavy_dependency(tmp_path):
    loaded = _run(textwrap.dedent(f'''
        import json, sys
        from praisonaiagents import Agent
        print(json.dumps([m for m in {HEAVY!r} if m in sys.modules]))
    '''), tmp_path)
    assert loaded == []


@pytest.mark.parametrize("mode", ["chat", "achat"])
def test_tool_turn_on_bare_model_name_does_not_load_litellm(tmp_path, mode):
    turn = 'agent.chat("1+2?")' if mode == "chat" else 'asyncio.run(agent.achat("1+2?"))'
    out = _run(_STUB + textwrap.dedent(f'''
        import asyncio, sys
        from praisonaiagents import Agent
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b
        agent = Agent(name="x", instructions="Be brief", llm="gpt-4o-mini", tools=[add], output="silent")
        print(json.dumps({{"out": {turn}, "litellm": "litellm" in sys.modules}}))
    '''), tmp_path)
    assert out == {"out": "3", "litellm": False}
