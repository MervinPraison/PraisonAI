"""Show agent progress inside your own web app.

Your app starts the run and records it; the Replay view, mounted at /replay,
draws it live in an <iframe>. No dashboard, no second server.

    pip install "praisonai[ui]" fastapi uvicorn
    uvicorn embed_fastapi:app --port 8000      # open http://127.0.0.1:8000/
"""

import threading
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from praisonaiagents import AgentFlow
from praisonaiagents.workflows import StepResult
from praisonai.replay import record, replay_app


def research(ctx):
    time.sleep(1.2)
    return StepResult(output="notes")


def write(ctx):
    time.sleep(1.2)
    return StepResult(output="article")


flow = AgentFlow(name="Article", steps=[research, write])

app = FastAPI()
app.mount("/replay", replay_app())  # read-only view: /replay/?run=<id> shows one run


@app.post("/generate")
def generate():
    run_id = f"run-{uuid.uuid4().hex[:12]}"

    def job():
        with record(run_id, live=True):  # live: the view follows it as it is written
            flow.start("solar sails")

    threading.Thread(target=job, daemon=True).start()
    return {"run_id": run_id}


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><title>My app</title>
<h1>My app</h1>
<button id="go">Generate article</button>
<iframe id="progress" title="Progress" style="width:100%;height:640px;border:1px solid #ccc"></iframe>
<script>
  go.onclick = async () => {
    const { run_id } = await (await fetch('/generate', { method: 'POST' })).json();
    progress.src = '/replay/?run=' + run_id;
  };
</script>"""
