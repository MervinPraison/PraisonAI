"""Tests for context budgeter module."""


class TestContextBudgeter:
    """Tests for ContextBudgeter class."""
    
    def test_default_initialization(self):
        """Test default budgeter initialization."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter()
        assert budgeter.model == "gpt-4o-mini"
        assert budgeter.model_limit > 0
        assert budgeter.output_reserve > 0
        assert budgeter.usable == budgeter.model_limit - budgeter.output_reserve
    
    def test_model_limit_lookup(self):
        """Test model limit lookup."""
        from praisonaiagents.context.budgeter import get_model_limit
        
        assert get_model_limit("gpt-4o") == 128000
        assert get_model_limit("gpt-4") == 8192
        assert get_model_limit("claude-3-5-sonnet") == 200000
        assert get_model_limit("gemini-1.5-pro") == 2097152
    
    def test_model_limit_partial_match(self):
        """Test partial model name matching."""
        from praisonaiagents.context.budgeter import get_model_limit
        
        # Should match gpt-4o
        assert get_model_limit("gpt-4o-2024-05-13") == 128000
    
    def test_model_limit_unknown(self):
        """Test unknown model uses default."""
        from praisonaiagents.context.budgeter import get_model_limit
        
        limit = get_model_limit("unknown-model-xyz")
        assert limit == 128000  # Default
    
    def test_output_reserve_lookup(self):
        """Test output reserve lookup."""
        from praisonaiagents.context.budgeter import get_output_reserve
        
        assert get_output_reserve("gpt-4o") == 16384
        assert get_output_reserve("claude-3-opus") == 8192
    
    def test_allocate_returns_budget(self):
        """Test allocate returns BudgetAllocation."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        from praisonaiagents.context.models import BudgetAllocation
        
        budgeter = ContextBudgeter(model="gpt-4o")
        allocation = budgeter.allocate()
        
        assert isinstance(allocation, BudgetAllocation)
        assert allocation.model_limit == budgeter.model_limit
        assert allocation.output_reserve == budgeter.output_reserve
    
    def test_allocate_segment_budgets(self):
        """Test segment budgets in allocation."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(
            system_prompt_budget=3000,
            rules_budget=1000,
        )
        allocation = budgeter.allocate()
        
        assert allocation.system_prompt == 3000
        assert allocation.rules == 1000
    
    def test_history_budget_dynamic(self):
        """Test history budget is computed dynamically."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(model="gpt-4o")
        allocation = budgeter.allocate()
        
        # History budget should be remainder after fixed segments
        assert allocation.history_budget > 0
        assert allocation.history_budget < allocation.usable
    
    def test_history_ratio_override(self):
        """Test history_ratio overrides dynamic calculation."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(
            model="gpt-4o",
            history_ratio=0.5,
        )
        allocation = budgeter.allocate()
        
        expected = int(budgeter.usable * 0.5)
        assert allocation.history == expected
    
    def test_check_overflow_under_threshold(self):
        """Test overflow check when under threshold."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(model="gpt-4o")
        
        # 50% of usable should not trigger at 80% threshold
        current = int(budgeter.usable * 0.5)
        assert not budgeter.check_overflow(current, threshold=0.8)
    
    def test_check_overflow_over_threshold(self):
        """Test overflow check when over threshold."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(model="gpt-4o")
        
        # 90% of usable should trigger at 80% threshold
        current = int(budgeter.usable * 0.9)
        assert budgeter.check_overflow(current, threshold=0.8)
    
    def test_get_remaining(self):
        """Test remaining tokens calculation."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(model="gpt-4o")
        
        current = 50000
        remaining = budgeter.get_remaining(current)
        assert remaining == budgeter.usable - current
    
    def test_get_utilization(self):
        """Test utilization calculation."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(model="gpt-4o")
        
        current = budgeter.usable // 2
        util = budgeter.get_utilization(current)
        assert 0.49 <= util <= 0.51
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        from praisonaiagents.context.budgeter import ContextBudgeter
        
        budgeter = ContextBudgeter(model="gpt-4o")
        data = budgeter.to_dict()
        
        assert "model" in data
        assert "model_limit" in data
        assert "usable" in data
        assert "allocation" in data


class TestBudgetAllocation:
    """Tests for BudgetAllocation dataclass."""
    
    def test_usable_property(self):
        """Test usable property calculation."""
        from praisonaiagents.context.models import BudgetAllocation
        
        allocation = BudgetAllocation(
            model_limit=128000,
            output_reserve=8000,
        )
        assert allocation.usable == 120000
    
    def test_fixed_total(self):
        """Test fixed total calculation."""
        from praisonaiagents.context.models import BudgetAllocation
        
        allocation = BudgetAllocation(
            system_prompt=2000,
            rules=500,
            skills=500,
            memory=1000,
            tools_schema=2000,
            tool_outputs=20000,
            buffer=1000,
        )
        
        expected = 2000 + 500 + 500 + 1000 + 2000 + 20000 + 1000
        assert allocation.fixed_total == expected
    
    def test_history_budget_computed(self):
        """Test history budget is computed from remainder."""
        from praisonaiagents.context.models import BudgetAllocation
        
        allocation = BudgetAllocation(
            model_limit=128000,
            output_reserve=8000,
            history=-1,  # Dynamic
        )
        
        expected = allocation.usable - allocation.fixed_total
        assert allocation.history_budget == expected
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        from praisonaiagents.context.models import BudgetAllocation
        
        allocation = BudgetAllocation()
        data = allocation.to_dict()
        
        assert "model_limit" in data
        assert "usable" in data
        assert "history_budget" in data
