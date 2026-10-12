#!/usr/bin/env python3
"""Live SDK smoke harness — release gate for praisonaiagents (issue #5780).

Runs the 7 core scenarios against a real LLM. Every core scenario must pass
before a release is published (see .github/workflows/live-sdk-smoke.yml).

    python scripts/live_sdk_smoke.py                 # 7 core scenarios
    python scripts/live_sdk_smoke.py --extended      # + non-blocking extended set
    python scripts/live_sdk_smoke.py --require-key   # missing key is a failure

Exit codes: 0 = all core scenarios passed (or skipped: no key, without
--require-key), 1 = at least one core scenario failed, 2 = no API key with
--require-key. A JSON summary (with the failed scenario names) is printed as the
last stdout line and written to --json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import uuid

MODEL = os.environ.get("PRAISONAI_SMOKE_MODEL", "gpt-4o-mini")
TIMEOUT = float(os.environ.get("PRAISONAI_SMOKE_TIMEOUT", "120"))


def _agent(**kwargs):
    from praisonaiagents import Agent

    kwargs.setdefault("instructions", "You are a concise assistant.")
    return Agent(llm=MODEL, **kwargs)


def _require(cond, detail):
    if not cond:
        raise AssertionError(detail)


# ── Core scenarios (blocking) ────────────────────────────────────────────────

def agent_chat_minimal():
    reply = _agent(name="Smoke").chat("Reply with the single word: pong")
    _require(isinstance(reply, str) and reply.strip(), f"empty reply: {reply!r}")


def structured_output_pydantic():
    from pydantic import BaseModel

    class City(BaseModel):
        name: str
        country: str

    result = _agent(name="Structured").chat(
        "Give the capital city of France.", output_pydantic=City
    )
    _require(isinstance(result, City), f"expected City, got {type(result).__name__}: {result!r}")


def single_tool_invocation():
    calls = []

    def get_secret_number(label: str) -> str:
        """Return the secret number registered under a label."""
        calls.append(label)
        return "4242"

    reply = _agent(name="Tooler", tools=[get_secret_number]).chat(
        "Use the get_secret_number tool with label 'alpha' and tell me the number."
    )
    _require(calls, "tool was never called")
    _require("4242" in str(reply), f"tool result missing from reply: {reply!r}")


def memory_cross_instance_user_id():
    uid = f"smoke-{uuid.uuid4().hex[:8]}"
    _agent(name="A", memory={"user_id": uid}).chat(
        "Remember this: my codename is ORANGE-PANDA. Reply ACK."
    )
    reply = _agent(name="B", memory={"user_id": uid}).chat(
        "What is my codename? Answer with the codename only."
    )
    _require("ORANGE" in str(reply).upper(), f"second agent did not recall: {reply!r}")


def memory_dict_db_path_string():
    uid = f"smoke-{uuid.uuid4().hex[:8]}"
    db_path = os.path.join(os.getcwd(), "smoke_memory.db")
    cfg = {"backend": "sqlite", "user_id": uid, "config": {"db_path": db_path}}
    _agent(name="Writer", memory=dict(cfg)).chat(
        "Remember this: my favourite fruit is DRAGONFRUIT. Reply ACK."
    )
    _require(os.path.exists(db_path), f"db not created at {db_path}")
    hits = _agent(name="Reader", memory=dict(cfg))._memory_instance.search_long_term("favourite fruit")
    _require(any("DRAGONFRUIT" in str(h) for h in hits or []), f"stored turn not readable: {hits!r}")


def agui_sse_live_agent():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from praisonaiagents.ui.agui import AGUI

    app = FastAPI()
    app.include_router(AGUI(agent=_agent(name="AGUI")).get_router())
    payload = {
        "thread_id": "smoke",
        "messages": [{"id": "m1", "role": "user", "content": "Say hello in one word."}],
    }
    with TestClient(app).stream("POST", "/agui", json=payload) as resp:
        _require(resp.status_code == 200, f"HTTP {resp.status_code}")
        body = "".join(resp.iter_text())
    for event in ("RUN_STARTED", "TEXT_MESSAGE_CONTENT", "RUN_FINISHED"):
        _require(event in body, f"{event} not in SSE stream: {body[:300]!r}")


def package_version():
    import praisonaiagents

    version = getattr(praisonaiagents, "__version__", "")
    _require(version and version[0].isdigit(), f"bad version: {version!r}")


CORE = [
    agent_chat_minimal,
    structured_output_pydantic,
    single_tool_invocation,
    memory_cross_instance_user_id,
    memory_dict_db_path_string,
    agui_sse_live_agent,
    package_version,
]


# ── Extended scenarios (non-blocking) ────────────────────────────────────────

def stream_chat():
    reply = _agent(name="Streamer").chat("Count from 1 to 3.", stream=True)
    _require(isinstance(reply, str) and reply.strip(), f"empty streamed reply: {reply!r}")


def achat_minimal():
    reply = asyncio.run(_agent(name="Async").achat("Reply with the single word: pong"))
    _require(isinstance(reply, str) and reply.strip(), f"empty async reply: {reply!r}")


def history_second_turn():
    agent = _agent(name="Historian")
    agent.chat("My lucky number is 731. Reply ACK.")
    reply = agent.chat("What is my lucky number? Answer with the number only.")
    _require("731" in str(reply), f"prior turn not used: {reply!r}")


def agent_team():
    from praisonaiagents import AgentTeam, Task

    writer = _agent(name="Writer")
    task = Task(description="Write one sentence about the sea.", expected_output="One sentence", agent=writer)
    result = AgentTeam(agents=[writer], tasks=[task]).start(return_dict=True)
    outputs = list((result or {}).get("task_results", {}).values())
    _require(outputs and all(getattr(o, "raw", None) for o in outputs), f"team task failed: {result!r}")


EXTENDED = [stream_chat, achat_minimal, history_second_turn, agent_team]

# Only LLM-bound timeouts are retried, at most once; assertion failures are not.
NO_RETRY = {"package_version"}


def _attempt(fn):
    """Run fn on its own daemon thread; a hung call is abandoned, never queued behind."""
    outcome = {}

    def target():
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - report every failure by name
            outcome["exc"] = exc

    thread = threading.Thread(target=target, name=f"smoke-{fn.__name__}", daemon=True)
    thread.start()
    thread.join(TIMEOUT)
    if thread.is_alive():
        return None
    return outcome.get("exc", False)


def _run(fn):
    attempts = 1 if fn.__name__ in NO_RETRY else 2
    for attempt in range(attempts):
        start = time.monotonic()
        exc = _attempt(fn)
        if exc is None:
            detail = f"timeout after {TIMEOUT:.0f}s (attempt {attempt + 1})"
            continue
        if exc:
            return False, f"{type(exc).__name__}: {exc}"[:500], time.monotonic() - start
        return True, "", time.monotonic() - start
    return False, detail, time.monotonic() - start


def _run_suite(name, scenarios):
    results = []
    for i, fn in enumerate(scenarios, 1):
        ok, detail, secs = _run(fn)
        label = f"[{i}/{len(scenarios)}] {fn.__name__} "
        print(f"{label:.<44} {'PASS' if ok else 'FAIL'} ({secs:.1f}s) {detail}", flush=True)
        results.append({"suite": name, "scenario": fn.__name__, "passed": ok, "seconds": round(secs, 2), "detail": detail})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extended", action="store_true", help="also run the non-blocking extended scenarios")
    parser.add_argument("--require-key", action="store_true", help="fail (exit 2) when OPENAI_API_KEY is not set")
    parser.add_argument("--json", default="live_sdk_smoke.json", help="where to write the JSON summary")
    args = parser.parse_args()
    json_path = os.path.abspath(args.json)

    summary = {"model": MODEL, "release_tag": os.environ.get("GITHUB_REF_NAME", "local")}
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set — skipping live smoke", flush=True)
        summary.update(skipped=True, reason="OPENAI_API_KEY not set")
        code = 2 if args.require_key else 0
    else:
        # Run inside a scratch dir so memory stores never touch the checkout.
        workdir = tempfile.mkdtemp(prefix="live_sdk_smoke_")
        os.chdir(workdir)
        core = _run_suite("core", CORE)
        extended = _run_suite("extended", EXTENDED) if args.extended else []
        failures = [r["scenario"] for r in core if not r["passed"]]
        summary.update(
            passed=sum(r["passed"] for r in core),
            failed=len(failures),
            total=len(core),
            failures=failures,
            extended_failures=[r["scenario"] for r in extended if not r["passed"]],
            results=core + extended,
        )
        code = 1 if failures else 0

    summary["exit_code"] = code
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"exit={code}")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}), flush=True)
    # os._exit: a timed-out scenario thread must not keep the process alive.
    os._exit(code)


if __name__ == "__main__":
    main()
