"""Real agentic test (AGENTS.md §9.4): record a live Agent run, export it to HTML.

Gated: RUN_REAL_KEY_TESTS=1 PRAISONAI_ALLOW_NETWORK=1 and OPENAI_API_KEY. One
cheap gpt-4o-mini call.
"""

import json
import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("RUN_REAL_KEY_TESTS") != "1" or not os.environ.get("OPENAI_API_KEY"),
        reason="Real key tests disabled. Set RUN_REAL_KEY_TESTS=1 PRAISONAI_ALLOW_NETWORK=1 and OPENAI_API_KEY.",
    ),
    pytest.mark.network,
    pytest.mark.provider_openai,
]


def test_record_live_agent_then_export_html(traces_dir, tmp_path):
    from typer.testing import CliRunner

    from praisonaiagents import Agent
    from praisonai.cli.commands.replay import app
    from praisonai.replay import load_events, record

    with record(live=True) as rec:
        agent = Agent(name="Greeter", instructions="You are concise.", llm="gpt-4o-mini")
        answer = agent.start("Say hello in one sentence")

    print("\nAgent answer:", answer)
    assert answer and isinstance(str(answer), str)

    events = load_events(rec.path)
    types = [e["event_type"] for e in events]
    print("Recorded", rec.run_id, "->", rec.path)
    print("Event types:", types)
    assert types[0] == "session_start" and types[-1] == "session_end"
    assert len(events) > 2, "the agent run itself must have emitted events"

    out = tmp_path / "replay.html"
    result = CliRunner().invoke(app, ["export", rec.run_id, "--format", "html", "-o", str(out)])
    print(result.output)
    assert result.exit_code == 0, result.output
    html = out.read_text(encoding="utf-8")
    assert "window.__REPLAY_DATA__" in html and "Greeter" in html
    print("HTML export:", out, f"{len(html):,} bytes")

    otlp = CliRunner().invoke(app, ["export", rec.run_id, "--format", "otel"])
    spans = json.loads(otlp.output)["resourceSpans"][0]["scopeSpans"][0]["spans"]
    print("OTLP spans:", [s["name"] for s in spans])
    assert any(s["name"].startswith("invoke_agent") for s in spans)


def test_run_button_runs_a_real_team_and_draws_it(traces_dir):
    """replay_app(team): one Run click runs both agents, recorded live; a second Run runs them again."""
    mod = pytest.importorskip("praisonaiui.features.replay")
    if not hasattr(mod, "create_replay_app"):
        pytest.skip("installed aiui predates create_replay_app")
    import threading

    from starlette.testclient import TestClient

    from praisonaiagents import Agent, AgentTeam, Task
    from praisonai.replay import replay_app

    researcher = Agent(name="Researcher", instructions="Give 2 short facts.", llm="gpt-4o-mini")
    writer = Agent(name="Writer", instructions="Write one sentence from the facts.", llm="gpt-4o-mini")
    team = AgentTeam(agents=[researcher, writer], tasks=[
        Task(name="research", description="2 facts about solar sails", agent=researcher, expected_output="2 facts"),
        Task(name="write", description="One sentence using the facts", agent=writer, expected_output="a sentence"),
    ])
    traces_dir.mkdir(parents=True, exist_ok=True)
    client = TestClient(replay_app(team))
    for attempt in (1, 2):
        run_id = client.post("/api/replay/run", json={"input": ""}).json()["run_id"]
        for _ in range(600):
            data = client.get(f"/api/replay/runs/{run_id}/events?wait=1").json()
            if data["run"] and data["events"] and data["events"][-1]["event_type"] == "session_end":
                break
            threading.Event().wait(0.1)  # time.sleep may be stubbed by the suite
        types = [e["event_type"] for e in data["events"]]
        print(f"\nRun {attempt} ({run_id}):", types)
        assert types.count("llm_response") >= 2, "both agents called the LLM"
        assert [e["node_id"] for e in data["events"] if e["event_type"] == "task_end"] == ["task:research", "task:write"]
