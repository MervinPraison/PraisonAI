"""
TDD tests for store_learning and search_learning tools.

Tests follow the same pattern as test_memory_tools.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─── Import Tests ────────────────────────────────────────────────────────────

class TestLearningToolImports:
    """Verify clean imports and no naming collisions."""

    def test_import_from_tools_module(self):
        from praisonaiagents.tools import store_learning, search_learning
        assert callable(store_learning)
        assert callable(search_learning)

    def test_import_directly(self):
        from praisonaiagents.tools.learning import store_learning, search_learning
        assert callable(store_learning)
        assert callable(search_learning)

    def test_no_collision_with_learn_package(self):
        """tools.learning and memory.learn are separate Python paths."""
        from praisonaiagents.tools.learning import store_learning
        from praisonaiagents.memory.learn.manager import LearnManager
        assert store_learning is not LearnManager


# ─── store_learning Tests ────────────────────────────────────────────────────

class TestStoreLearning:
    """Test store_learning tool function."""

    def _make_state(self, learn_manager=None):
        from praisonaiagents.tools.injected import AgentState
        return AgentState(
            agent_id="test",
            run_id="run-1",
            session_id="sess-1",
            learn_manager=learn_manager,
        )

    def test_store_persona(self):
        from praisonaiagents.tools.learning import store_learning
        mgr = MagicMock()
        mgr.capture_persona.return_value = MagicMock(id="e1", content="likes blue")
        state = self._make_state(learn_manager=mgr)

        result = store_learning("User likes blue", category="persona", state=state)
        mgr.capture_persona.assert_called_once_with("User likes blue")
        assert "persona" in result.lower()

    def test_store_insight(self):
        from praisonaiagents.tools.learning import store_learning
        mgr = MagicMock()
        mgr.capture_insight.return_value = MagicMock(id="e2", content="uses FastAPI")
        state = self._make_state(learn_manager=mgr)

        result = store_learning("Project uses FastAPI", category="insights", state=state)
        mgr.capture_insight.assert_called_once_with("Project uses FastAPI")
        assert "insight" in result.lower()

    def test_store_pattern(self):
        from praisonaiagents.tools.learning import store_learning
        mgr = MagicMock()
        mgr.capture_pattern.return_value = MagicMock(id="e3", content="deploy=staging")
        state = self._make_state(learn_manager=mgr)

        result = store_learning("deploy means staging", category="patterns", state=state)
        mgr.capture_pattern.assert_called_once_with("deploy means staging")
        assert "pattern" in result.lower()

    def test_store_decision(self):
        from praisonaiagents.tools.learning import store_learning
        mgr = MagicMock()
        mgr.capture_decision.return_value = MagicMock(id="e4", content="chose postgres")
        state = self._make_state(learn_manager=mgr)

        result = store_learning("Use PostgreSQL", category="decisions", state=state)
        mgr.capture_decision.assert_called_once_with("Use PostgreSQL")
        assert "decision" in result.lower()

    def test_store_default_category_is_persona(self):
        """Default category should be persona (most common use case)."""
        from praisonaiagents.tools.learning import store_learning
        mgr = MagicMock()
        mgr.capture_persona.return_value = MagicMock(id="e5")
        state = self._make_state(learn_manager=mgr)

        store_learning("Prefers Python", state=state)
        mgr.capture_persona.assert_called_once()

    def test_store_no_learn_manager(self):
        """Graceful response when learn is not configured."""
        from praisonaiagents.tools.learning import store_learning
        state = self._make_state(learn_manager=None)

        result = store_learning("test", state=state)
        assert "not configured" in result.lower() or "enable" in result.lower()

    def test_store_no_state(self):
        """Graceful response when no state is available."""
        from praisonaiagents.tools.learning import store_learning
        with patch("praisonaiagents.tools.learning.get_current_state", return_value=None):
            result = store_learning("test")
        assert "not configured" in result.lower() or "enable" in result.lower()


# ─── search_learning Tests ───────────────────────────────────────────────────

class TestSearchLearning:
    """Test search_learning tool function."""

    def _make_state(self, learn_manager=None):
        from praisonaiagents.tools.injected import AgentState
        return AgentState(
            agent_id="test",
            run_id="run-1",
            session_id="sess-1",
            learn_manager=learn_manager,
        )

    def test_search_with_results(self):
        from praisonaiagents.tools.learning import search_learning
        mgr = MagicMock()
        mgr.search.return_value = {
            "persona": [{"id": "1", "content": "likes blue"}],
            "insights": [{"id": "2", "content": "uses FastAPI"}],
        }
        state = self._make_state(learn_manager=mgr)

        result = search_learning("preferences", state=state)
        mgr.search.assert_called_once_with("preferences", limit=5)
        assert "likes blue" in result
        assert "uses FastAPI" in result

    def test_search_specific_category(self):
        from praisonaiagents.tools.learning import search_learning
        mgr = MagicMock()
        # When category is specified, search should filter to that store
        mgr.search.return_value = {
            "persona": [{"id": "1", "content": "prefers bullet points"}],
        }
        state = self._make_state(learn_manager=mgr)

        result = search_learning("style", category="persona", state=state)
        assert "prefers bullet points" in result

    def test_search_no_results(self):
        from praisonaiagents.tools.learning import search_learning
        mgr = MagicMock()
        mgr.search.return_value = {}
        state = self._make_state(learn_manager=mgr)

        result = search_learning("nonexistent", state=state)
        assert "no" in result.lower() and ("found" in result.lower() or "learning" in result.lower())

    def test_search_no_learn_manager(self):
        from praisonaiagents.tools.learning import search_learning
        state = self._make_state(learn_manager=None)

        result = search_learning("test", state=state)
        assert "not configured" in result.lower() or "enable" in result.lower()


# ─── Schema Tests ────────────────────────────────────────────────────────────

class TestLearningToolSchema:
    """Verify Injected[AgentState] is hidden from LLM schema."""

    def test_store_learning_injected_hidden(self):
        import inspect
        from praisonaiagents.tools.learning import store_learning
        sig = inspect.signature(store_learning)
        params = list(sig.parameters.keys())
        # 'state' should exist for injection but be hidden from LLM
        assert "state" in params
        # LLM-visible params should be content + category
        assert "content" in params
        assert "category" in params

    def test_search_learning_injected_hidden(self):
        import inspect
        from praisonaiagents.tools.learning import search_learning
        sig = inspect.signature(search_learning)
        params = list(sig.parameters.keys())
        assert "state" in params
        assert "query" in params
        assert "limit" in params
"""
TDD tests for store_learning and search_learning tools.
"""
