"""
Tests for memory tools (store_memory, search_memory).

These are standard tool functions that agents use via tools=[store_memory, search_memory].
They use Injected[AgentState] to access the memory instance at runtime.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestMemoryToolImports:
    """Test that memory tools can be imported."""

    def test_import_from_tools_module(self):
        """store_memory and search_memory importable from tools package."""
        from praisonaiagents.tools import store_memory, search_memory
        assert callable(store_memory)
        assert callable(search_memory)

    def test_import_directly(self):
        """Direct import from tools.memory module."""
        from praisonaiagents.tools.memory import store_memory, search_memory
        assert callable(store_memory)
        assert callable(search_memory)

    def test_no_collision_with_memory_package(self):
        """tools.memory does not collide with memory/ package."""
        import praisonaiagents.memory as mem_pkg
        import praisonaiagents.tools.memory as tools_mem
        assert mem_pkg is not tools_mem


class TestStoreMemory:
    """Test store_memory tool function."""

    def test_store_memory_with_memory_instance(self):
        """store_memory stores content via the injected memory."""
        from praisonaiagents.tools.memory import store_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context

        mock_memory = MagicMock()
        mock_memory.store_short_term = MagicMock()
        mock_memory.store_long_term = MagicMock()

        state = AgentState(
            agent_id="test-agent",
            run_id="test-run",
            session_id="test-session",
            memory=mock_memory,
        )

        with with_injection_context(state):
            result = store_memory(content="User likes Python", memory_type="long_term")

        assert "stored" in result.lower() or "success" in result.lower() or "saved" in result.lower()

    def test_store_memory_short_term(self):
        """store_memory correctly stores to short_term."""
        from praisonaiagents.tools.memory import store_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context

        mock_memory = MagicMock()
        mock_memory.store_short_term = MagicMock()

        state = AgentState(
            agent_id="a", run_id="r", session_id="s", memory=mock_memory,
        )

        with with_injection_context(state):
            store_memory(content="temporary note", memory_type="short_term")

        mock_memory.store_short_term.assert_called_once()

    def test_store_memory_long_term(self):
        """store_memory correctly stores to long_term."""
        from praisonaiagents.tools.memory import store_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context

        mock_memory = MagicMock()
        mock_memory.store_long_term = MagicMock()

        state = AgentState(
            agent_id="a", run_id="r", session_id="s", memory=mock_memory,
        )

        with with_injection_context(state):
            store_memory(content="important fact", memory_type="long_term")

        mock_memory.store_long_term.assert_called_once()

    def test_store_memory_no_memory_configured(self):
        """store_memory returns helpful message when no memory."""
        from praisonaiagents.tools.memory import store_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context

        state = AgentState(
            agent_id="a", run_id="r", session_id="s", memory=None,
        )

        with with_injection_context(state):
            result = store_memory(content="test")

        assert "not configured" in result.lower() or "not available" in result.lower()

    def test_store_memory_no_state(self):
        """store_memory returns helpful message with no injection context."""
        from praisonaiagents.tools.memory import store_memory
        from praisonaiagents.tools.injected import set_current_state

        set_current_state(None)
        result = store_memory(content="test")
        assert "not configured" in result.lower() or "not available" in result.lower()


class TestSearchMemory:
    """Test search_memory tool function."""

    def test_search_memory_with_results(self):
        """search_memory returns formatted results."""
        from praisonaiagents.tools.memory import search_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context

        mock_memory = MagicMock()
        mock_memory.search_long_term = MagicMock(return_value=[
            {"text": "User likes Python", "score": 0.9},
            {"text": "User is a developer", "score": 0.7},
        ])

        state = AgentState(
            agent_id="a", run_id="r", session_id="s", memory=mock_memory,
        )

        with with_injection_context(state):
            result = search_memory(query="programming preferences")

        assert "Python" in result

    def test_search_memory_no_results(self):
        """search_memory returns clear message when nothing found."""
        from praisonaiagents.tools.memory import search_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context

        mock_memory = MagicMock()
        mock_memory.search_long_term = MagicMock(return_value=[])
        mock_memory.search_short_term = MagicMock(return_value=[])

        state = AgentState(
            agent_id="a", run_id="r", session_id="s", memory=mock_memory,
        )

        with with_injection_context(state):
            result = search_memory(query="nonexistent topic")

        assert "no" in result.lower() or "nothing" in result.lower() or "found" in result.lower()

    def test_search_memory_no_memory_configured(self):
        """search_memory returns helpful message when no memory."""
        from praisonaiagents.tools.memory import search_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context

        state = AgentState(
            agent_id="a", run_id="r", session_id="s", memory=None,
        )

        with with_injection_context(state):
            result = search_memory(query="test")

        assert "not configured" in result.lower() or "not available" in result.lower()


class TestMemoryToolSchema:
    """Test that Injected params are hidden from LLM schema."""

    def test_store_memory_injected_hidden(self):
        """state param should not appear in tool schema."""
        from praisonaiagents.tools.memory import store_memory
        from praisonaiagents.tools.injected import get_injected_params

        injected = get_injected_params(store_memory)
        assert "state" in injected, "state param must be Injected"

    def test_search_memory_injected_hidden(self):
        """state param should not appear in tool schema."""
        from praisonaiagents.tools.memory import search_memory
        from praisonaiagents.tools.injected import get_injected_params

        injected = get_injected_params(search_memory)
        assert "state" in injected, "state param must be Injected"


class TestMemoryToolsWithFileMemory:
    """Integration test with real FileMemory (no mocks)."""

    def test_store_and_search_roundtrip(self, tmp_path):
        """Store a memory, then search for it."""
        from praisonaiagents.tools.memory import store_memory, search_memory
        from praisonaiagents.tools.injected import AgentState, with_injection_context
        from praisonaiagents.memory.file_memory import FileMemory

        fm = FileMemory(user_id="test_mem_tools", base_path=str(tmp_path))
        state = AgentState(
            agent_id="a", run_id="r", session_id="s", memory=fm,
        )

        with with_injection_context(state):
            store_result = store_memory(content="The capital of France is Paris", memory_type="long_term")
            assert "stored" in store_result.lower() or "saved" in store_result.lower()

            search_result = search_memory(query="capital France")
            assert "Paris" in search_result
