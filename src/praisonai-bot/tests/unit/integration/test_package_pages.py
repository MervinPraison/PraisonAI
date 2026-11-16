"""Bot Health and Workflow Runs render as aiui components, not a raw JSON block.

Both pages returned a plain dict, which the dashboard's generic viewer shows
as a ``<pre>`` JSON dump. They now return ``aiui.layout([...])`` (the
``_components`` contract the dashboard and app shell render) with status
chips, metrics, tables, and explicit empty and error states.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient

from praisonai_bot.integration.pages import bot_health, workflow_runs
from praisonai_bot.integration.pages._blocks import clip, duration

# Components the dashboard renders through innerHTML: only fixed text and
# numbers from this package may go into them.
_HTML_TYPES = {"alert", "callout", "metric", "markdown_text", "html_embed"}


def _types(layout):
    return [c["type"] for c in layout["_components"]]


def _html_text(layout):
    out = []
    for c in layout["_components"]:
        if c["type"] in _HTML_TYPES:
            out += [str(c.get(k, "")) for k in ("message", "title", "content", "value", "label")]
        if c["type"] == "stat_group":
            out += [f"{s['label']} {s['value']}" for s in c["stats"]]
    return " ".join(out)


# ── Bot Health ───────────────────────────────────────────────────────


def test_bot_health_without_gateway_is_a_warning_and_empty_state():
    layout = bot_health.build_bot_health(None)
    assert _types(layout) == ["alert", "empty"]
    assert layout["_components"][0]["variant"] == "warning"


def test_bot_health_error_state_keeps_the_error_out_of_html():
    layout = bot_health.build_bot_health(None, error="<img src=x onerror=alert(1)>")
    assert _types(layout) == ["alert", "caption"]
    assert layout["_components"][0]["variant"] == "error"
    assert "<img" not in _html_text(layout)
    assert "<img" in layout["_components"][1]["text"]  # shown as text


def test_bot_health_with_channels_has_chips_metrics_and_a_table():
    health = {
        "status": "healthy",
        "uptime": 3725,
        "agents": 2,
        "sessions": 5,
        "channels": {
            "tg": {"platform": "telegram", "running": True, "ok": True, "reason": "healthy",
                   "last_activity": 0},
            "slack": {"platform": "slack", "running": False, "status": "degraded",
                      "reason": "credential unavailable <b>x</b>"},
        },
    }
    layout = bot_health.build_bot_health(
        health, agents=[("a1", "Researcher")],
        channels_feature={"running_channels": 1, "total_channels": 3},
    )
    comps = layout["_components"]
    assert comps[0] == {"type": "badge", "text": "Gateway: Healthy", "variant": "default"}
    stats = {s["label"]: s["value"] for s in comps[1]["stats"]}
    assert stats["Uptime"] == "1h 2m"
    assert stats["Channels healthy"] == "1 / 2"
    assert stats["Channels page running"] == "1 / 3"
    tables = [c for c in comps if c["type"] == "table"]
    assert tables[0]["headers"][:3] == ["Channel", "Platform", "State"]
    assert [r[2] for r in tables[0]["rows"]] == ["Healthy", "Degraded"]
    assert tables[0]["rows"][1][3] == "credential unavailable <b>x</b>"  # a text cell
    assert tables[1]["rows"] == [["a1", "Researcher"]]
    assert "<b>" not in _html_text(layout)
    assert "_components" in layout and "gateway" not in layout  # not the old raw dict


def test_bot_health_empty_gateway_shows_empty_states():
    layout = bot_health.build_bot_health({"status": "stopped"})
    comps = layout["_components"]
    assert comps[0]["text"] == "Gateway: Stopped"
    assert [c["type"] for c in comps].count("empty") == 2


def test_bot_health_reads_the_live_gateway(monkeypatch):
    class _Agent:
        name = "Writer"

    class _Gateway:
        def health(self):
            return {"status": "healthy", "channels": {}}

        def list_agents(self):
            return ["w1"]

        def get_agent(self, aid):
            return _Agent()

    from praisonaiui.features import _gateway_ref

    monkeypatch.setattr(_gateway_ref, "get_gateway", lambda: _Gateway())
    layout = asyncio.run(bot_health.collect_bot_health())
    assert layout["_components"][0]["text"] == "Gateway: Healthy"
    assert [c for c in layout["_components"] if c["type"] == "table"][0]["rows"] == [["w1", "Writer"]]


def test_bot_health_gateway_failure_is_the_error_state(monkeypatch):
    class _Broken:
        def health(self):
            raise RuntimeError("boom")

    from praisonaiui.features import _gateway_ref

    monkeypatch.setattr(_gateway_ref, "get_gateway", lambda: _Broken())
    layout = asyncio.run(bot_health.collect_bot_health())
    assert _types(layout) == ["alert", "caption"]
    assert "RuntimeError: boom" in layout["_components"][1]["text"]


# ── Workflow Runs ────────────────────────────────────────────────────


def test_workflow_runs_states():
    assert _types(workflow_runs.build_workflow_runs(None)) == ["alert", "empty"]
    assert _types(workflow_runs.build_workflow_runs([])) == ["stat_group", "empty"]
    err = workflow_runs.build_workflow_runs(None, error="KeyError: 'x'")
    assert _types(err) == ["alert", "caption"]


def test_workflow_runs_table_is_newest_first_with_chips():
    runs = [
        {"id": "r1", "workflow_id": "wf", "status": "completed", "input": {"text": "<b>hi</b>"},
         "output": {"output": "done"}},
        {"id": "r2", "workflow_id": "wf", "status": "failed", "input": {"text": "x"},
         "error": "Workflow has no steps"},
    ]
    layout = workflow_runs.build_workflow_runs(runs)
    comps = layout["_components"]
    stats = {s["label"]: s["value"] for s in comps[0]["stats"]}
    assert stats == {"Runs": 2, "Completed": 1, "Failed": 1, "In progress": 0}
    chips = {(c["text"], c["variant"]) for c in comps if c["type"] == "badge"}
    assert chips == {("Completed: 1", "default"), ("Failed: 1", "destructive")}
    table = next(c for c in comps if c["type"] == "table")
    assert [r[0] for r in table["rows"]] == ["r2", "r1"]
    assert table["rows"][0][2:] == ["Failed", "x", "Workflow has no steps"]
    assert table["rows"][1][3:] == ["<b>hi</b>", "done"]
    assert "<b>" not in _html_text(layout)


def test_workflow_runs_caps_rows():
    runs = [{"id": f"r{i}", "workflow_id": "wf", "status": "completed"} for i in range(150)]
    comps = workflow_runs.build_workflow_runs(runs)["_components"]
    table = next(c for c in comps if c["type"] == "table")
    assert len(table["rows"]) == workflow_runs.MAX_ROWS
    assert table["rows"][0][0] == "r149"
    assert comps[-1]["type"] == "caption"


def test_helpers():
    assert clip(None) == "—"
    assert clip("a\n b") == "a b"
    assert clip("x" * 200, 10) == "x" * 9 + "…"
    assert duration(0) == "—" and duration(59) == "59s" and duration(90061) == "1d 1h"


# ── Served through aiui ──────────────────────────────────────────────


@pytest.mark.parametrize("page_id", ["bot-health", "workflow-runs"])
def test_pages_are_served_as_components(isolated_host, page_id):
    import importlib

    # reset_state() cleared aiui's page registry; re-register the pages.
    importlib.reload(bot_health)
    importlib.reload(workflow_runs)
    isolated_host.configure_host(pages=["chat"])
    client = TestClient(isolated_host.create_host_app())
    data = client.get(f"/api/pages/{page_id}/data").json()
    assert isinstance(data.get("_components"), list) and data["_components"]


def test_workflow_runs_page_lists_runs_recorded_by_aiui(isolated_host):
    import importlib

    importlib.reload(workflow_runs)
    isolated_host.configure_host(pages=["chat"])
    client = TestClient(isolated_host.create_host_app())
    from praisonaiui.features import workflows as wf_feature

    monkey = {"id": "abc", "workflow_id": "wf1", "status": "completed", "input": {"text": "q"},
              "output": {"result": "ok"}}
    wf_feature._runs["abc"] = monkey
    try:
        data = client.get("/api/pages/workflow-runs/data").json()
    finally:
        wf_feature._runs.pop("abc", None)
    table = next(c for c in data["_components"] if c["type"] == "table")
    assert table["rows"] == [["abc", "wf1", "Completed", "q", "ok"]]
