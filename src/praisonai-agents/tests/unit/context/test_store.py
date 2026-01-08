"""
Unit tests for context store module.

Tests:
- AgentBudget configuration
- ContextViewImpl read operations
- ContextMutatorImpl write operations
- ContextStoreImpl management
- Token caching
- Non-destructive truncation/condensation
"""

import pytest
from praisonaiagents.context.store import (
    AgentBudget,
    ContextViewImpl,
    ContextMutatorImpl,
    ContextStoreImpl,
    get_global_store,
    reset_global_store,
)


class TestAgentBudget:
    """Tests for AgentBudget dataclass."""
    
    def test_default_values(self):
        """Test default budget values."""
        budget = AgentBudget()
        assert budget.max_tokens == 0
        assert budget.history_ratio == 0.6
        assert budget.output_reserve == 8000
        assert budget.compact_threshold == 0.8
    
    def test_custom_values(self):
        """Test custom budget values."""
        budget = AgentBudget(
            max_tokens=128000,
            history_ratio=0.7,
            output_reserve=4000,
        )
        assert budget.max_tokens == 128000
        assert budget.history_ratio == 0.7
        assert budget.output_reserve == 4000
    
    def test_get_history_budget(self):
        """Test history budget calculation."""
        budget = AgentBudget(
            max_tokens=100000,
            history_ratio=0.6,
            output_reserve=10000,
        )
        # (100000 - 10000) * 0.6 = 54000
        assert budget.get_history_budget() == 54000
    
    def test_get_history_budget_no_limit(self):
        """Test history budget with no limit returns 0."""
        budget = AgentBudget(max_tokens=0)
        assert budget.get_history_budget() == 0


class TestContextStoreImpl:
    """Tests for ContextStoreImpl."""
    
    def setup_method(self):
        """Reset global store before each test."""
        reset_global_store()
    
    def test_create_store(self):
        """Test creating a store."""
        store = ContextStoreImpl()
        assert store is not None
    
    def test_get_view(self):
        """Test getting a view for an agent."""
        store = ContextStoreImpl()
        view = store.get_view("agent1")
        assert view is not None
        assert isinstance(view, ContextViewImpl)
    
    def test_get_mutator(self):
        """Test getting a mutator for an agent."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        assert mutator is not None
        assert isinstance(mutator, ContextMutatorImpl)
    
    def test_view_caching(self):
        """Test views are cached."""
        store = ContextStoreImpl()
        view1 = store.get_view("agent1")
        view2 = store.get_view("agent1")
        assert view1 is view2
    
    def test_set_agent_budget(self):
        """Test setting agent budget."""
        store = ContextStoreImpl()
        budget = AgentBudget(max_tokens=50000)
        store.set_agent_budget("agent1", budget)
        
        # Verify via view
        view = store.get_view("agent1")
        assert view.get_budget_remaining() >= 0
    
    def test_snapshot_restore(self):
        """Test snapshot and restore."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        mutator.append({"role": "user", "content": "Hello"})
        mutator.commit()
        
        # Snapshot
        data = store.snapshot()
        assert len(data) > 0
        
        # Create new store and restore
        store2 = ContextStoreImpl()
        store2.restore(data)
        
        view = store2.get_view("agent1")
        messages = view.get_messages()
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello"
    
    def test_get_stats(self):
        """Test getting store statistics."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        mutator.append({"role": "user", "content": "Test"})
        mutator.commit()
        
        stats = store.get_stats()
        assert stats["agent_count"] == 1
        assert stats["total_messages"] == 1


class TestContextMutatorImpl:
    """Tests for ContextMutatorImpl."""
    
    def setup_method(self):
        """Reset global store before each test."""
        reset_global_store()
    
    def test_append_and_commit(self):
        """Test appending and committing messages."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "user", "content": "Hello"})
        mutator.append({"role": "assistant", "content": "Hi"})
        mutator.commit()
        
        view = store.get_view("agent1")
        messages = view.get_messages()
        assert len(messages) == 2
    
    def test_rollback(self):
        """Test rollback discards uncommitted changes."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "user", "content": "Hello"})
        mutator.rollback()
        
        view = store.get_view("agent1")
        messages = view.get_messages()
        assert len(messages) == 0
    
    def test_tag_for_condensation(self):
        """Test tagging messages for condensation."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        # Add messages
        mutator.append({"role": "user", "content": "Msg 1"})
        mutator.append({"role": "assistant", "content": "Msg 2"})
        mutator.append({"role": "user", "content": "Msg 3"})
        mutator.commit()
        
        # Tag first two for condensation
        mutator.tag_for_condensation([0, 1], "summary-1")
        
        # Verify tags
        messages = store._get_agent_messages("agent1")
        assert messages[0]["_metadata"]["condense_parent"] == "summary-1"
        assert messages[1]["_metadata"]["condense_parent"] == "summary-1"
        assert "condense_parent" not in messages[2].get("_metadata", {})
    
    def test_tag_for_truncation(self):
        """Test tagging messages for truncation."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "user", "content": "Old"})
        mutator.commit()
        
        mutator.tag_for_truncation([0], "trunc-1")
        
        messages = store._get_agent_messages("agent1")
        assert messages[0]["_metadata"]["truncation_parent"] == "trunc-1"
    
    def test_mask_observation(self):
        """Test masking message content."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "tool", "content": "Very long output " * 100})
        mutator.commit()
        
        mutator.mask_observation(0, preview="Long output...")
        
        messages = store._get_agent_messages("agent1")
        assert messages[0]["_metadata"]["is_masked"] is True
        assert "[Output masked:" in messages[0]["content"]
    
    def test_insert_summary(self):
        """Test inserting a summary message."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "user", "content": "Msg 1"})
        mutator.append({"role": "user", "content": "Msg 2"})
        mutator.commit()
        
        mutator.insert_summary("Summary of conversation", "sum-1", 1)
        
        messages = store._get_agent_messages("agent1")
        assert len(messages) == 3
        assert messages[1]["content"] == "Summary of conversation"
        assert messages[1]["_metadata"]["is_summary"] is True


class TestContextViewImpl:
    """Tests for ContextViewImpl."""
    
    def setup_method(self):
        """Reset global store before each test."""
        reset_global_store()
    
    def test_get_messages(self):
        """Test getting all messages."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        mutator.append({"role": "user", "content": "Hello"})
        mutator.commit()
        
        view = store.get_view("agent1")
        messages = view.get_messages()
        
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello"
        # Internal metadata should be stripped
        assert "_metadata" not in messages[0]
    
    def test_get_messages_with_limit(self):
        """Test getting messages with token limit."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        # Add several messages
        for i in range(10):
            mutator.append({"role": "user", "content": f"Message {i} " * 50})
        mutator.commit()
        
        view = store.get_view("agent1")
        # Get with small token limit
        messages = view.get_messages(max_tokens=100)
        
        # Should return fewer messages due to limit
        assert len(messages) < 10
    
    def test_get_effective_messages(self):
        """Test getting effective messages (filtered)."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "user", "content": "Old"})
        mutator.append({"role": "assistant", "content": "Summary"})
        mutator.append({"role": "user", "content": "New"})
        mutator.commit()
        
        # Tag first message as condensed
        mutator.tag_for_condensation([0], "sum-1")
        # Mark second as summary
        messages = store._get_agent_messages("agent1")
        messages[1]["_metadata"]["is_summary"] = True
        messages[1]["_metadata"]["summary_id"] = "sum-1"
        
        view = store.get_view("agent1")
        effective = view.get_effective_messages()
        
        # Should exclude the condensed message
        assert len(effective) == 2
    
    def test_get_token_count(self):
        """Test getting token count."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        mutator.append({"role": "user", "content": "Hello world"})
        mutator.commit()
        
        view = store.get_view("agent1")
        tokens = view.get_token_count()
        
        assert tokens > 0
    
    def test_get_utilization(self):
        """Test getting utilization."""
        store = ContextStoreImpl()
        store.set_agent_budget("agent1", AgentBudget(max_tokens=10000))
        
        mutator = store.get_mutator("agent1")
        mutator.append({"role": "user", "content": "Hello"})
        mutator.commit()
        
        view = store.get_view("agent1")
        util = view.get_utilization()
        
        assert 0.0 <= util <= 1.0


class TestGlobalStore:
    """Tests for global store singleton."""
    
    def setup_method(self):
        """Reset global store before each test."""
        reset_global_store()
    
    def test_get_global_store(self):
        """Test getting global store."""
        store = get_global_store()
        assert store is not None
    
    def test_global_store_singleton(self):
        """Test global store is singleton."""
        store1 = get_global_store()
        store2 = get_global_store()
        assert store1 is store2
    
    def test_reset_global_store(self):
        """Test resetting global store."""
        store1 = get_global_store()
        reset_global_store()
        store2 = get_global_store()
        assert store1 is not store2
