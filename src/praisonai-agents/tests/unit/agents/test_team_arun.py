"""D-10: AgentTeam and AutoAgents have arun(), like Agent and AgentFlow.

run() is the silent counterpart of start(); the async family had astart()
but no arun(). arun() is an alias of astart() (the async path never shows
start()'s verbose panels), so nothing changes for existing callers.
"""

import asyncio
import inspect

from praisonaiagents import AgentTeam


def test_team_and_autoagents_have_arun():
    from praisonaiagents import AutoAgents

    for cls in (AgentTeam, AutoAgents):
        assert inspect.iscoroutinefunction(cls.arun), cls


def test_arun_returns_what_astart_returns(monkeypatch):
    calls = []

    async def fake_astart(self, content=None, return_dict=False, **kwargs):
        calls.append((content, return_dict, kwargs))
        return "done"

    monkeypatch.setattr(AgentTeam, "astart", fake_astart)
    team = AgentTeam.__new__(AgentTeam)
    assert asyncio.run(team.arun("ctx", return_dict=True, extra=1)) == "done"
    assert calls == [("ctx", True, {"extra": 1})]
