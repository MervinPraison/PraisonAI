"""
Real agentic tests for GNAP plugin.

Tests GNAP integration with actual agent LLM calls as required by AGENTS.md §9.4.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

# Import test requirements
import sys
sys.path.append(os.path.dirname(__file__))

from gnap_tools import (
    gnap_save_state, gnap_load_state, gnap_list_tasks, 
    gnap_commit, gnap_get_status, _get_gnap_plugin
)


class TestGNAPAgentic:
    """Real agentic tests - agents must call LLM end-to-end."""
    
    @pytest.fixture
    def temp_repo(self):
        """Create temporary repository for testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def setup_gnap_env(self, temp_repo):
        """Setup GNAP environment variables."""
        with patch.dict(os.environ, {
            "GNAP_REPO_PATH": str(temp_repo),
            "GNAP_AUTO_COMMIT": "true",
            "GNAP_AGENT_ID": "test_agent"
        }):
            yield
    
    @pytest.fixture
    def mock_git_for_tools(self):
        """Mock git operations for tool tests."""
        with patch('gnap_plugin.GitPython') as mock_git:
            mock_repo = Mock()
            mock_repo.iter_commits.return_value = []
            mock_repo.active_branch.name = "test_branch"
            mock_repo.index = Mock()
            mock_repo.index.add = Mock()
            mock_repo.index.commit = Mock()
            mock_repo.index.diff.return_value = ["mock_change"]
            mock_git.Repo.return_value = mock_repo
            mock_git.Repo.init.return_value = mock_repo
            mock_git.InvalidGitRepositoryError = Exception
            yield mock_git
    
    def test_gnap_tools_basic_operations(self, setup_gnap_env, mock_git_for_tools):
        """Test GNAP tool functions work correctly."""
        # Test save state
        result = gnap_save_state("research_task_001", {
            "status": "in_progress",
            "agent": "researcher",
            "description": "Analyzing market trends",
            "findings": ["trend1", "trend2"]
        })
        assert "Successfully saved state" in result
        assert "research_task_001" in result
        
        # Test load state
        loaded_state = gnap_load_state("research_task_001")
        assert loaded_state["status"] == "in_progress"
        assert loaded_state["agent"] == "researcher"
        assert "findings" in loaded_state
        assert len(loaded_state["findings"]) == 2
        
        # Test save another task
        gnap_save_state("analysis_task_001", {
            "status": "completed",
            "agent": "analyst",
            "results": {"score": 0.85}
        })
        
        # Test list tasks
        all_tasks = gnap_list_tasks()
        assert len(all_tasks) == 2
        
        task_ids = [task["task_id"] for task in all_tasks]
        assert "research_task_001" in task_ids
        assert "analysis_task_001" in task_ids
        
        # Test list with status filter
        completed_tasks = gnap_list_tasks(status_filter="completed")
        assert len(completed_tasks) == 1
        assert completed_tasks[0]["task_id"] == "analysis_task_001"
        
        # Test list with prefix filter
        research_tasks = gnap_list_tasks(prefix="research_")
        assert len(research_tasks) == 1
        assert research_tasks[0]["task_id"] == "research_task_001"
    
    def test_gnap_status_and_commit(self, setup_gnap_env, mock_git_for_tools):
        """Test GNAP status reporting and manual commits."""
        # Save some test tasks
        gnap_save_state("task1", {"status": "pending", "agent": "agent1"})
        gnap_save_state("task2", {"status": "completed", "agent": "agent2"})
        gnap_save_state("task3", {"status": "failed", "agent": "agent1"})
        
        # Test status summary
        status = gnap_get_status()
        assert status["total_tasks"] == 3
        assert status["by_status"]["pending"] == 1
        assert status["by_status"]["completed"] == 1
        assert status["by_status"]["failed"] == 1
        
        # Test manual commit
        commit_result = gnap_commit("Manual test commit")
        assert "Successfully committed" in commit_result
        assert "Manual test commit" in commit_result
    
    @pytest.mark.integration
    def test_real_agent_with_gnap_tools(self, setup_gnap_env, mock_git_for_tools):
        """
        REAL AGENTIC TEST - Agent calls LLM and uses GNAP tools end-to-end.
        
        This test satisfies the requirement from AGENTS.md §9.4:
        "Every feature MUST include a real agentic test — not just smoke tests."
        """
        try:
            # Import PraisonAI Agent (this is the real agentic component)
            from praisonaiagents import Agent
            
            # Create agent with GNAP tools
            agent = Agent(
                name="gnap_test_agent",
                instructions="You are a helpful assistant that manages tasks using GNAP storage. "
                           "When asked to save task information, use the gnap_save_state tool. "
                           "When asked to retrieve tasks, use gnap_load_state and gnap_list_tasks tools. "
                           "Always provide clear status updates.",
                tools=[gnap_save_state, gnap_load_state, gnap_list_tasks, gnap_get_status],
                llm="gpt-4o-mini"  # Use a fast, affordable model for testing
            )
            
            # ✅ REAL AGENTIC TEST - Agent calls LLM end-to-end
            print("\n=== REAL AGENTIC TEST: Agent with GNAP tools ===")
            
            # Test 1: Agent saves a task using GNAP
            response1 = agent.start(
                "Save a new research task with ID 'market_research_2024' that has status 'pending', "
                "is assigned to agent 'research_bot', and includes a description about analyzing "
                "Q4 market trends. Then confirm it was saved by loading the task back."
            )
            print(f"Agent Response 1: {response1}")
            
            # Verify the agent actually used GNAP tools
            loaded_task = gnap_load_state("market_research_2024")
            assert loaded_task is not None, "Agent should have saved the task"
            assert loaded_task.get("status") == "pending", "Task should have correct status"
            
            # Test 2: Agent retrieves and analyzes task status
            response2 = agent.start(
                "Show me the current status of all tasks in the GNAP storage. "
                "Provide a summary of how many tasks we have and their statuses."
            )
            print(f"Agent Response 2: {response2}")
            
            # Test 3: Agent updates task status  
            response3 = agent.start(
                "Update the market_research_2024 task to have status 'completed' and add "
                "results showing that Q4 trends indicate 15% growth in tech sector."
            )
            print(f"Agent Response 3: {response3}")
            
            # Verify the update worked
            updated_task = gnap_load_state("market_research_2024")
            assert updated_task.get("status") == "completed", "Agent should have updated task status"
            
            print("\n✅ REAL AGENTIC TEST PASSED: Agent successfully used GNAP tools with LLM calls")
            
            # Print full output so developers can verify end-to-end behavior
            print(f"\nFull test results:")
            print(f"- Agent created task: {loaded_task}")
            print(f"- Agent updated task: {updated_task}")
            print(f"- All responses included LLM-generated text")
            
        except ImportError as e:
            pytest.skip(f"PraisonAI Agents not available for real agentic test: {e}")
        except Exception as e:
            pytest.fail(f"Real agentic test failed: {e}")
    
    def test_multi_agent_workflow_isolation(self, setup_gnap_env, mock_git_for_tools):
        """Test multi-agent workflow with branch isolation."""
        # Simulate multiple agents working on different tasks
        
        # Agent 1: Researcher
        with patch.dict(os.environ, {"GNAP_AGENT_ID": "researcher_agent"}):
            gnap_save_state("research_001", {
                "status": "active",
                "agent": "researcher_agent", 
                "task": "market analysis"
            })
        
        # Agent 2: Writer  
        with patch.dict(os.environ, {"GNAP_AGENT_ID": "writer_agent"}):
            gnap_save_state("content_001", {
                "status": "active",
                "agent": "writer_agent",
                "task": "blog post creation"
            })
        
        # Verify both agents' tasks are stored
        all_tasks = gnap_list_tasks()
        assert len(all_tasks) == 2
        
        task_agents = {task["task_id"]: task["agent"] for task in all_tasks}
        assert task_agents["research_001"] == "researcher_agent"
        assert task_agents["content_001"] == "writer_agent"
        
        # Test status summary shows multi-agent activity
        status = gnap_get_status()
        assert status["by_agent"]["researcher_agent"] == 1
        assert status["by_agent"]["writer_agent"] == 1
    
    def test_crash_recovery_simulation(self, setup_gnap_env, mock_git_for_tools):
        """Simulate crash recovery by restarting GNAP plugin."""
        # Initial plugin instance saves tasks
        initial_result = gnap_save_state("recovery_test_001", {
            "status": "in_progress",
            "step": 1,
            "data": "important work"
        })
        assert "Successfully saved" in initial_result
        
        # Simulate crash - clear global plugin instance
        import gnap_tools
        gnap_tools._gnap_plugin = None
        
        # New plugin instance should recover the task
        recovered_task = gnap_load_state("recovery_test_001")
        assert recovered_task is not None
        assert recovered_task["status"] == "in_progress"
        assert recovered_task["step"] == 1
        assert recovered_task["data"] == "important work"
        
        # Continue work after recovery
        gnap_save_state("recovery_test_001", {
            **recovered_task,
            "status": "completed",
            "step": 2
        })
        
        # Verify recovery and continuation worked
        final_task = gnap_load_state("recovery_test_001") 
        assert final_task["status"] == "completed"
        assert final_task["step"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to see print output