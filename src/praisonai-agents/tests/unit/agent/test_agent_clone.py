"""Tests for Agent.__deepcopy__ and Agent.clone_for_channel() (issue #1746).

Validates:
- copy.deepcopy(agent) works without threading.RLock errors
- clone_for_channel() returns an independent instance
- Cloned agent has its own lock objects (not shared)
- Key configuration attributes are preserved in the clone
- Multiple clones are isolated from each other
"""
import copy
import threading
import pytest


class TestAgentDeepCopy:
    """Test Agent.__deepcopy__ and clone_for_channel()."""

    def _make_agent(self, **kwargs):
        from praisonaiagents.agent.agent import Agent
        return Agent(name="TestAgent", instructions="test", **kwargs)

    def test_deepcopy_does_not_raise(self):
        """copy.deepcopy(agent) must not raise TypeError for RLock."""
        agent = self._make_agent()
        cloned = copy.deepcopy(agent)
        assert cloned is not agent

    def test_clone_for_channel_returns_new_instance(self):
        agent = self._make_agent()
        cloned = agent.clone_for_channel()
        assert cloned is not agent

    def test_clone_has_independent_cache_lock(self):
        """__cache_lock must be a new RLock, not shared with original."""
        agent = self._make_agent()
        cloned = agent.clone_for_channel()
        assert cloned._Agent__cache_lock is not agent._Agent__cache_lock
        assert isinstance(cloned._Agent__cache_lock, type(threading.RLock()))

    def test_clone_has_independent_cost_lock(self):
        """_cost_lock must be a new Lock, not shared with original."""
        agent = self._make_agent()
        cloned = agent.clone_for_channel()
        assert cloned._cost_lock is not agent._cost_lock

    def test_clone_preserves_name(self):
        agent = self._make_agent(name="MyAgent")
        assert agent.clone_for_channel().name == "MyAgent"

    def test_clone_preserves_instructions(self):
        agent = self._make_agent(instructions="Do the thing")
        assert agent.clone_for_channel().instructions == "Do the thing"

    def test_clone_preserves_role_goal_backstory(self):
        agent = self._make_agent(
            role="Analyst",
            goal="Analyse",
            backstory="Expert analyst",
        )
        cloned = agent.clone_for_channel()
        assert cloned.role == "Analyst"
        assert cloned.goal == "Analyse"
        assert cloned.backstory == "Expert analyst"

    def test_clone_preserves_llm(self):
        agent = self._make_agent(llm="gpt-4o-mini")
        assert agent.clone_for_channel().llm == "gpt-4o-mini"

    def test_multiple_clones_are_isolated(self):
        """Regression: creating two clones (simulating 2nd+ gateway channel) must work."""
        agent = self._make_agent()
        clone1 = agent.clone_for_channel()
        clone2 = agent.clone_for_channel()
        assert clone1 is not clone2
        assert clone1._Agent__cache_lock is not clone2._Agent__cache_lock

    def test_deepcopy_multiple_times(self):
        """Successive deepcopies must all succeed (no cumulative state corruption)."""
        agent = self._make_agent()
        for _ in range(3):
            cloned = copy.deepcopy(agent)
            assert cloned is not agent
