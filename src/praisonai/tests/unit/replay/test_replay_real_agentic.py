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
