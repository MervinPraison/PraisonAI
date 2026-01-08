"""
Integration tests for multi-agent context management.

Tests:
- Sequential multi-agent sharing correctness
- Parallel multi-agent isolation (no leakage)
- Workflow context propagation
- Tool output truncation/masking
"""

import time
from concurrent.futures import ThreadPoolExecutor

from praisonaiagents.context import (
    ContextStoreImpl,
    AgentBudget,
    reset_global_store,
    get_effective_history,
)


class TestMultiAgentIsolation:
    """Test that agents have isolated context by default."""
    
    def setup_method(self):
        reset_global_store()
    
    def test_agents_have_separate_views(self):
        """Each agent should have its own isolated view."""
        store = ContextStoreImpl()
        
        # Agent 1 adds messages
        mutator1 = store.get_mutator("agent1")
        mutator1.append({"role": "user", "content": "Hello from agent1"})
        mutator1.commit()
        
        # Agent 2 adds messages
        mutator2 = store.get_mutator("agent2")
        mutator2.append({"role": "user", "content": "Hello from agent2"})
        mutator2.commit()
        
        # Views should be isolated
        view1 = store.get_view("agent1")
        view2 = store.get_view("agent2")
        
        msgs1 = view1.get_messages()
        msgs2 = view2.get_messages()
        
        assert len(msgs1) == 1
        assert len(msgs2) == 1
        assert msgs1[0]["content"] == "Hello from agent1"
        assert msgs2[0]["content"] == "Hello from agent2"
    
    def test_parallel_agents_no_leakage(self):
        """Parallel agent execution should not leak context."""
        store = ContextStoreImpl()
        results = {}
        errors = []
        
        def agent_work(agent_id: str, message_count: int):
            try:
                mutator = store.get_mutator(agent_id)
                for i in range(message_count):
                    mutator.append({"role": "user", "content": f"{agent_id} msg {i}"})
                    time.sleep(0.001)  # Simulate work
                mutator.commit()
                
                view = store.get_view(agent_id)
                results[agent_id] = len(view.get_messages())
            except Exception as e:
                errors.append(str(e))
        
        # Run 5 agents in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i in range(5):
                futures.append(executor.submit(agent_work, f"agent_{i}", 10))
            for f in futures:
                f.result()
        
        # Verify no errors
        assert len(errors) == 0, f"Errors: {errors}"
        
        # Verify each agent has exactly 10 messages
        for i in range(5):
            assert results[f"agent_{i}"] == 10, f"agent_{i} has {results[f'agent_{i}']} messages"
    
    def test_rollback_isolation(self):
        """Rollback should only affect the agent that rolled back."""
        store = ContextStoreImpl()
        
        # Agent 1 commits
        mutator1 = store.get_mutator("agent1")
        mutator1.append({"role": "user", "content": "Committed"})
        mutator1.commit()
        
        # Agent 2 appends but rolls back
        mutator2 = store.get_mutator("agent2")
        mutator2.append({"role": "user", "content": "Will be rolled back"})
        mutator2.rollback()
        
        # Agent 1 should still have its message
        view1 = store.get_view("agent1")
        assert len(view1.get_messages()) == 1
        
        # Agent 2 should have nothing
        view2 = store.get_view("agent2")
        assert len(view2.get_messages()) == 0


class TestContextSharing:
    """Test context sharing between agents."""
    
    def setup_method(self):
        reset_global_store()
    
    def test_shared_context_visible_to_all(self):
        """Shared context should be visible to all agents."""
        store = ContextStoreImpl()
        
        # Add shared context
        store.add_shared_context({"role": "system", "content": "Shared instructions"})
        
        # Both agents should see shared context
        shared1 = store.get_shared_context()
        shared2 = store.get_shared_context()
        
        assert len(shared1) == 1
        assert len(shared2) == 1
        assert shared1[0]["content"] == "Shared instructions"


class TestBudgetEnforcement:
    """Test per-agent budget enforcement."""
    
    def setup_method(self):
        reset_global_store()
    
    def test_budget_tracking(self):
        """Budget should be tracked per agent."""
        store = ContextStoreImpl()
        
        # Set budget for agent1
        store.set_agent_budget("agent1", AgentBudget(
            max_tokens=10000,
            history_ratio=0.6,
            output_reserve=2000,
        ))
        
        # Add some messages
        mutator = store.get_mutator("agent1")
        mutator.append({"role": "user", "content": "Test message " * 100})
        mutator.commit()
        
        # Check utilization
        view = store.get_view("agent1")
        util = view.get_utilization()
        
        assert util > 0, "Utilization should be positive"
        assert util < 1.0, "Utilization should be under 100%"


class TestEffectiveHistory:
    """Test effective history filtering."""
    
    def test_condensed_messages_filtered(self):
        """Messages with condense_parent should be filtered."""
        messages = [
            {"role": "user", "content": "Old 1", "_metadata": {"condense_parent": "sum-1"}},
            {"role": "user", "content": "Old 2", "_metadata": {"condense_parent": "sum-1"}},
            {"role": "assistant", "content": "Summary", "_metadata": {"is_summary": True, "summary_id": "sum-1"}},
            {"role": "user", "content": "New message"},
        ]
        
        effective = get_effective_history(messages)
        
        # Should have summary + new message only
        assert len(effective) == 2
        assert effective[0]["content"] == "Summary"
        assert effective[1]["content"] == "New message"
    
    def test_truncated_messages_filtered(self):
        """Messages with truncation_parent should be filtered."""
        messages = [
            {"role": "user", "content": "Hidden", "_metadata": {"truncation_parent": "trunc-1"}},
            {"role": "user", "content": "[Truncation marker]", "_metadata": {"is_truncation_marker": True, "truncation_id": "trunc-1"}},
            {"role": "user", "content": "Visible"},
        ]
        
        effective = get_effective_history(messages)
        
        assert len(effective) == 2
        assert effective[0]["content"] == "[Truncation marker]"
        assert effective[1]["content"] == "Visible"


class TestObservationMasking:
    """Test observation masking functionality."""
    
    def setup_method(self):
        reset_global_store()
    
    def test_mask_observation(self):
        """Masking should replace content with preview."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        # Add a tool output
        mutator.append({
            "role": "tool",
            "content": "Very long output that should be masked " * 50,
            "tool_call_id": "call_123",
        })
        mutator.commit()
        
        # Mask it
        mutator.mask_observation(0, preview="Long output...")
        
        # Verify masking
        messages = store._get_agent_messages("agent1")
        assert messages[0]["_metadata"]["is_masked"] is True
        assert "[Output masked:" in messages[0]["content"]
        assert messages[0]["_metadata"]["original_token_count"] > 0


class TestDeltaCommitRollback:
    """Test delta buffer with commit/rollback."""
    
    def setup_method(self):
        reset_global_store()
    
    def test_commit_persists_changes(self):
        """Commit should persist delta buffer."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "user", "content": "Message 1"})
        mutator.append({"role": "assistant", "content": "Response 1"})
        mutator.commit()
        
        view = store.get_view("agent1")
        assert len(view.get_messages()) == 2
    
    def test_rollback_discards_changes(self):
        """Rollback should discard delta buffer."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        # First commit
        mutator.append({"role": "user", "content": "Committed"})
        mutator.commit()
        
        # Second batch - rollback
        mutator.append({"role": "user", "content": "Will be discarded"})
        mutator.rollback()
        
        view = store.get_view("agent1")
        messages = view.get_messages()
        assert len(messages) == 1
        assert messages[0]["content"] == "Committed"
    
    def test_multiple_commits(self):
        """Multiple commits should accumulate."""
        store = ContextStoreImpl()
        mutator = store.get_mutator("agent1")
        
        mutator.append({"role": "user", "content": "Batch 1"})
        mutator.commit()
        
        mutator.append({"role": "user", "content": "Batch 2"})
        mutator.commit()
        
        view = store.get_view("agent1")
        assert len(view.get_messages()) == 2
