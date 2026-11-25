"""D-07: the README's first-agent example shows its answer when output is piped.

It called ``agent.start(...)`` without ``print``: in a terminal ``start()``
renders the answer, but piped, redirected, in CI, Docker logs or an editor's
run panel it printed 0 bytes. The block is run here exactly as written,
against a local stub, with stdout captured (not a terminal).
"""

import json
import os
import re
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
PKG_ROOT = os.path.join(REPO, "src", "praisonai-agents")

_STUB = textwrap.dedent('''
    import json, os, threading, http.server
    B = json.dumps({"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "STUB-ANSWER"}, "finish_reason": "stop"}],
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
''')


def _first_agent_block():
    with open(os.path.join(REPO, "README.md"), encoding="utf-8") as fh:
        text = fh.read()
    # The README's first-agent example sits under "## Quick start". It imports the
    # wrapper; the README says the core package takes the same code, and this test
    # runs with only the core package on the path.
    assert "## Quick start" in text, "README.md has no '## Quick start' section"
    section = text.split("## Quick start", 1)[1]
    block = re.search(r"```python\n(.*?)```", section, re.S).group(1)
    return block.replace("from praisonai import Agent", "from praisonaiagents import Agent")


def test_first_agent_example_prints_when_piped(tmp_path):
    env = dict(os.environ, PYTHONPATH=PKG_ROOT, PRAISONAI_HOME=str(tmp_path), OPENAI_API_KEY="sk-local-fake")
    env.pop("OPENAI_BASE_URL", None)
    env.pop("OPENAI_API_BASE", None)
    env.pop("OPENAI_MODEL_NAME", None)  # an inherited non-OpenAI model would bypass the stub
    proc = subprocess.run([sys.executable, "-c", _STUB + _first_agent_block()], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "STUB-ANSWER" in proc.stdout
