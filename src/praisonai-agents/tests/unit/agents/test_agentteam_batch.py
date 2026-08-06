import pytest


def _make_team():
    from praisonaiagents import Agent, AgentTeam, Task

    writer = Agent(name="Writer", instructions="Write")
    task = Task(
        description="Write a short bio for {{name}}",
        expected_output="A concise bio for {{name}}",
        agent=writer,
    )
    return AgentTeam(agents=[writer], tasks=[task], process="sequential")


def test_start_for_each_maps_inputs(monkeypatch):
    team = _make_team()
    seen = []

    def fake_start(**kwargs):
        # Capture the interpolated variables applied for this item
        seen.append(dict(team.variables))
        return f"bio for {team.variables.get('name')}"

    monkeypatch.setattr(team, "start", fake_start)

    result = team.start_for_each(inputs=[{"name": "Ada"}, {"name": "Bob"}])

    assert result["total"] == 2
    assert result["succeeded"] == 2
    assert result["failed"] == 0
    assert result["outputs"] == ["bio for Ada", "bio for Bob"]
    assert [item["index"] for item in result["items"]] == [0, 1]
    assert seen == [{"name": "Ada"}, {"name": "Bob"}]
    assert result["batch_id"].startswith("batch_")


def test_template_immutability(monkeypatch):
    team = _make_team()
    original = next(iter(team.tasks.values())).description
    monkeypatch.setattr(team, "start", lambda **k: "ok")

    team.start_for_each(inputs=[{"name": "Ada"}, {"name": "Bob"}])

    assert next(iter(team.tasks.values())).description == original
    assert team.variables == {}


def test_continue_on_error(monkeypatch):
    team = _make_team()

    def fake_start(**kwargs):
        if team.variables.get("name") == "Bob":
            raise RuntimeError("boom")
        return "ok"

    monkeypatch.setattr(team, "start", fake_start)

    result = team.start_for_each(
        inputs=[{"name": "Ada"}, {"name": "Bob"}, {"name": "Chip"}],
        on_error="continue",
    )

    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert result["items"][1]["success"] is False
    assert "boom" in result["items"][1]["error"]
    assert result["items"][2]["success"] is True


def test_fail_fast(monkeypatch):
    team = _make_team()

    def fake_start(**kwargs):
        if team.variables.get("name") == "Bob":
            raise RuntimeError("boom")
        return "ok"

    monkeypatch.setattr(team, "start", fake_start)

    with pytest.raises(RuntimeError):
        team.start_for_each(
            inputs=[{"name": "Ada"}, {"name": "Bob"}, {"name": "Chip"}],
            on_error="fail_fast",
        )


def test_empty_inputs(monkeypatch):
    team = _make_team()
    called = []
    monkeypatch.setattr(team, "start", lambda **k: called.append(1))

    result = team.start_for_each(inputs=[])

    assert result["total"] == 0
    assert result["succeeded"] == 0
    assert result["outputs"] == []
    assert called == []


def test_invalid_on_error():
    team = _make_team()
    with pytest.raises(ValueError):
        team.start_for_each(inputs=[{"name": "Ada"}], on_error="nope")


def test_astart_for_each_maps_inputs(monkeypatch):
    import asyncio

    team = _make_team()

    async def fake_astart(**kwargs):
        return f"bio for {team.variables.get('name')}"

    monkeypatch.setattr(team, "astart", fake_astart)

    result = asyncio.run(
        team.astart_for_each(inputs=[{"name": "Ada"}, {"name": "Bob"}])
    )

    assert result["outputs"] == ["bio for Ada", "bio for Bob"]
    assert result["succeeded"] == 2
