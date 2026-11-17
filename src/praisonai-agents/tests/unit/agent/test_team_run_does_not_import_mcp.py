"""X-16: a team run, or a per-turn ``tools=``, does not import the ``mcp`` package.

Five ``isinstance(tool, MCP)`` checks imported ``praisonaiagents.mcp.mcp``
(and with it ``mcp`` and ``mcp.server.fastmcp``, about 0.4 s) only to find
that no tool was an ``MCP``. No tool can be one unless that module was
imported, so the checks now look the class up in ``sys.modules``.
"""

import json
import os
import subprocess
import sys
import textwrap

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_SCRIPT = textwrap.dedent('''
    import json, os, sys, threading, http.server, io, contextlib
    B = json.dumps({"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "done"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", 0)))
            self.send_response(200); self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(B))); self.end_headers(); self.wfile.write(B)
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["OPENAI_BASE_URL"] = os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:%d/v1" % srv.server_address[1]
    from praisonaiagents import Agent, AgentTeam, Task
    def lookup(q: str) -> str:
        """Look up."""
        return q
    agents = [Agent(name=f"a{i}", instructions="hi", model="gpt-4o-mini", output="silent") for i in range(3)]
    tasks = [Task(description=f"task {i}", expected_output="text", agent=agents[i]) for i in range(3)]
    with contextlib.redirect_stdout(io.StringIO()):
        AgentTeam(agents=agents, tasks=tasks, output="silent").start()
        team_mcp = "mcp" in sys.modules
        Agent(name="t", instructions="hi", model="gpt-4o-mini", output="silent").chat("hi", tools=[lookup])
    print(json.dumps({"team": team_mcp, "per_turn_tools": "mcp" in sys.modules,
                      "praison_mcp": "praisonaiagents.mcp.mcp" in sys.modules}))
''')


def test_team_run_and_per_turn_tools_do_not_import_mcp(tmp_path):
    env = dict(os.environ, PYTHONPATH=PKG_ROOT, PRAISONAI_HOME=str(tmp_path), OPENAI_API_KEY="sk-local-fake")
    env.pop("OPENAI_BASE_URL", None)
    env.pop("OPENAI_API_BASE", None)
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=180)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out == {"team": False, "per_turn_tools": False, "praison_mcp": False}
