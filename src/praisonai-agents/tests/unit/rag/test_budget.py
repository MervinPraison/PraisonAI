"""
Unit tests for Token Budget Infrastructure (Phase 1).

Tests TokenBudget dataclass, model context window detection,
and dynamic budget calculation.
"""

import pytest
from dataclasses import dataclass


class TestTokenBudget:
    """Tests for TokenBudget dataclass."""
    
    def test_import_token_budget(self):
        """TokenBudget should be importable from rag module."""
        from praisonaiagents.rag.budget import TokenBudget
        assert TokenBudget is not None
    
    def test_default_values(self):
        """TokenBudget should have sensible defaults."""
        from praisonaiagents.rag.budget import TokenBudget
        
        budget = TokenBudget()
        assert budget.model_max_tokens == 128000  # Default for GPT-4
        assert budget.reserved_response_tokens == 4096
        assert budget.reserved_system_tokens == 1000
        assert budget.reserved_history_tokens == 2000
    
    def test_max_context_tokens_calculation(self):
        """max_context_tokens should be calculated correctly."""
        from praisonaiagents.rag.budget import TokenBudget
        
        budget = TokenBudget(
            model_max_tokens=100000,
            reserved_response_tokens=4000,
            reserved_system_tokens=1000,
            reserved_history_tokens=2000,
        )
        # 100000 - 4000 - 1000 - 2000 = 93000
        assert budget.max_context_tokens == 93000
    
    def test_dynamic_budget_calculation(self):
        """dynamic_budget should calculate remaining tokens correctly."""
        from praisonaiagents.rag.budget import TokenBudget
        
        budget = TokenBudget(
            model_max_tokens=100000,
            reserved_response_tokens=4000,
        )
        
        # With 5000 prompt tokens and 3000 history tokens
        remaining = budget.dynamic_budget(prompt_tokens=5000, history_tokens=3000)
        # 100000 - 5000 - 3000 - 4000 = 88000
        assert remaining == 88000
    
    def test_dynamic_budget_never_negative(self):
        """dynamic_budget should never return negative values."""
        from praisonaiagents.rag.budget import TokenBudget
        
        budget = TokenBudget(model_max_tokens=10000)
        
        # Request more than available
        remaining = budget.dynamic_budget(prompt_tokens=50000, history_tokens=50000)
        assert remaining == 0
    
    def test_from_model_name(self):
        """TokenBudget should be creatable from model name."""
        from praisonaiagents.rag.budget import TokenBudget
        
        # GPT-4 Turbo
        budget = TokenBudget.from_model("gpt-4-turbo")
        assert budget.model_max_tokens == 128000
        
        # GPT-3.5 Turbo
        budget = TokenBudget.from_model("gpt-3.5-turbo")
        assert budget.model_max_tokens == 16385
        
        # Claude 3
        budget = TokenBudget.from_model("claude-3-opus")
        assert budget.model_max_tokens == 200000
        
        # Unknown model should use fallback
        budget = TokenBudget.from_model("unknown-model")
        assert budget.model_max_tokens == 8192  # Safe fallback
    
    def test_to_dict(self):
        """TokenBudget should be serializable to dict."""
        from praisonaiagents.rag.budget import TokenBudget
        
        budget = TokenBudget(model_max_tokens=50000)
        d = budget.to_dict()
        
        assert d["model_max_tokens"] == 50000
        assert "reserved_response_tokens" in d
        assert "max_context_tokens" in d
    
    def test_from_dict(self):
        """TokenBudget should be deserializable from dict."""
        from praisonaiagents.rag.budget import TokenBudget
        
        d = {
            "model_max_tokens": 50000,
            "reserved_response_tokens": 2000,
        }
        budget = TokenBudget.from_dict(d)
        
        assert budget.model_max_tokens == 50000
        assert budget.reserved_response_tokens == 2000


class TestModelContextWindows:
    """Tests for model context window detection."""
    
    def test_get_model_context_window(self):
        """get_model_context_window should return correct values."""
        from praisonaiagents.rag.budget import get_model_context_window
        
        assert get_model_context_window("gpt-4") == 8192
        assert get_model_context_window("gpt-4-turbo") == 128000
        assert get_model_context_window("gpt-4o") == 128000
        assert get_model_context_window("gpt-4o-mini") == 128000
        assert get_model_context_window("gpt-3.5-turbo") == 16385
        assert get_model_context_window("claude-3-opus") == 200000
        assert get_model_context_window("claude-3-sonnet") == 200000
        assert get_model_context_window("claude-3-haiku") == 200000
        assert get_model_context_window("gemini-pro") == 32768
        assert get_model_context_window("gemini-1.5-pro") == 1000000
    
    def test_unknown_model_fallback(self):
        """Unknown models should return safe fallback."""
        from praisonaiagents.rag.budget import get_model_context_window
        
        assert get_model_context_window("unknown-model-xyz") == 8192
        assert get_model_context_window("") == 8192
        assert get_model_context_window(None) == 8192


class TestBudgetEnforcement:
    """Tests for budget enforcement in context building."""
    
    def test_budget_enforcer_protocol(self):
        """BudgetEnforcerProtocol should be importable."""
        from praisonaiagents.rag.budget import BudgetEnforcerProtocol
        assert BudgetEnforcerProtocol is not None
    
    def test_default_budget_enforcer(self):
        """DefaultBudgetEnforcer should enforce token limits."""
        from praisonaiagents.rag.budget import DefaultBudgetEnforcer, TokenBudget
        
        enforcer = DefaultBudgetEnforcer()
        budget = TokenBudget(model_max_tokens=1000, reserved_response_tokens=200)
        
        # Create chunks that exceed budget
        chunks = [
            {"text": "word " * 100, "metadata": {}},  # ~100 tokens
            {"text": "word " * 100, "metadata": {}},  # ~100 tokens
            {"text": "word " * 100, "metadata": {}},  # ~100 tokens
        ]
        
        result = enforcer.enforce(chunks, budget, prompt_tokens=500, history_tokens=0)
        
        # Should have truncated to fit budget
        # Available: 1000 - 200 - 500 = 300 tokens
        # Each chunk is ~100 tokens, so should fit ~3 chunks
        assert len(result) <= 3


class TestRetrievalConfigBudgetIntegration:
    """Tests for RetrievalConfig budget integration."""
    
    def test_retrieval_config_has_budget_fields(self):
        """RetrievalConfig should have budget-related fields."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        
        config = RetrievalConfig()
        
        # Should have max_context_tokens (already exists)
        assert hasattr(config, "max_context_tokens")
        
        # Should have new budget fields
        assert hasattr(config, "model_context_window")
        assert hasattr(config, "reserved_response_tokens")
        assert hasattr(config, "dynamic_budget")
    
    def test_retrieval_config_budget_defaults(self):
        """RetrievalConfig budget fields should have sensible defaults."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        
        config = RetrievalConfig()
        
        # model_context_window should default to None (auto-detect)
        assert config.model_context_window is None
        
        # dynamic_budget should default to True
        assert config.dynamic_budget is True
    
    def test_retrieval_config_get_token_budget(self):
        """RetrievalConfig should provide TokenBudget instance."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        from praisonaiagents.rag.budget import TokenBudget
        
        config = RetrievalConfig(model_context_window=100000)
        budget = config.get_token_budget()
        
        assert isinstance(budget, TokenBudget)
        assert budget.model_max_tokens == 100000
