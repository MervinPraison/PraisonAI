"""Retained completed events are available to both wait entry points."""
import asyncio

from praisonaiagents import AgentTeam


def test_sync_default_returns_already_completed_events():
    with AgentTeam(agents=[]) as team:
        team.announce_completion("finished-a", "task-a", "result-a")
        team.announce_completion("finished-b", "task-b", "result-b")
        events = team.wait_for_completions(timeout=0.2)
    assert [event.agent_id for event in events] == ["finished-a", "finished-b"]


def test_explicit_empty_ids_do_not_return_retained_events():
    """An explicit empty target set retains its previous empty result."""
    with AgentTeam(agents=[]) as team:
        team.announce_completion("finished-a", "task-a", "result-a")
        assert team.wait_for_completions(timeout=0.2, agent_ids=[]) == []


def test_explicit_ids_filter_retained_events():
    with AgentTeam(agents=[]) as team:
        team.announce_completion("finished-a", "task-a", "result-a")
        team.announce_completion("finished-b", "task-b", "result-b")
        events = team.wait_for_completions(timeout=0.2, agent_ids=["finished-b"])
    assert [event.agent_id for event in events] == ["finished-b"]


def test_async_default_returns_already_completed_events():
    with AgentTeam(agents=[]) as team:
        team.announce_completion("finished-a", "task-a", "result-a")
        team.announce_completion("finished-b", "task-b", "result-b")
        events = asyncio.run(team.await_for_completions(timeout=0.2))
    assert [event.agent_id for event in events] == ["finished-a", "finished-b"]
