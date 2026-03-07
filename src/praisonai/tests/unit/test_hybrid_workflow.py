"""
TDD Tests for Hybrid Workflow Executor (Strategy 6).

Tests the HybridWorkflowExecutor that combines job and agent workflow capabilities.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


class TestHybridWorkflowStepDetection:
    """Test step type detection in HybridWorkflowExecutor."""

    def test_detect_shell_step(self):
        """Shell step should be detected."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        executor = HybridWorkflowExecutor({"steps": []}, "test.yaml")
        step_type = executor._detect_step_type({"run": "echo hello"})
        
        assert step_type == "shell"

    def test_detect_agent_step(self):
        """Agent step should be detected."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        executor = HybridWorkflowExecutor({"steps": []}, "test.yaml")
        step_type = executor._detect_step_type({"agent": {"role": "Writer"}})
        
        assert step_type == "agent"

    def test_detect_workflow_step(self):
        """Workflow step should be detected."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        executor = HybridWorkflowExecutor({"steps": []}, "test.yaml")
        step_type = executor._detect_step_type({"workflow": {"agent": "researcher"}})
        
        assert step_type == "workflow"

    def test_detect_parallel_step(self):
        """Parallel step should be detected."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        executor = HybridWorkflowExecutor({"steps": []}, "test.yaml")
        step_type = executor._detect_step_type({"parallel": [{"run": "echo 1"}, {"run": "echo 2"}]})
        
        assert step_type == "parallel"

    def test_detect_judge_step(self):
        """Judge step should be detected."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        executor = HybridWorkflowExecutor({"steps": []}, "test.yaml")
        step_type = executor._detect_step_type({"judge": {"threshold": 8.0}})
        
        assert step_type == "judge"

    def test_detect_approve_step(self):
        """Approve step should be detected."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        executor = HybridWorkflowExecutor({"steps": []}, "test.yaml")
        step_type = executor._detect_step_type({"approve": {"risk_level": "high"}})
        
        assert step_type == "approve"


class TestHybridWorkflowDryRun:
    """Test dry-run display for hybrid workflows."""

    def test_dry_run_shell_step(self):
        """Dry run should show shell step info."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        data = {
            "type": "hybrid",
            "name": "test-hybrid",
            "steps": [{"name": "Echo", "run": "echo hello"}]
        }
        executor = HybridWorkflowExecutor(data, "test.yaml")
        
        result = executor.run(["--dry-run"])
        
        assert result["dry_run"] is True
        assert result["results"][0]["type"] == "shell"

    def test_dry_run_agent_step(self):
        """Dry run should show agent step info."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        data = {
            "type": "hybrid",
            "name": "test-hybrid",
            "steps": [{"name": "Generate", "agent": {"role": "Writer", "model": "gpt-4o"}}]
        }
        executor = HybridWorkflowExecutor(data, "test.yaml")
        
        result = executor.run(["--dry-run"])
        
        assert result["dry_run"] is True
        assert result["results"][0]["type"] == "agent"

    def test_dry_run_workflow_step(self):
        """Dry run should show workflow step info."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        data = {
            "type": "hybrid",
            "name": "test-hybrid",
            "agents": {"researcher": {"name": "Researcher", "role": "Research Analyst"}},
            "steps": [{"name": "Research", "workflow": {"agent": "researcher"}}]
        }
        executor = HybridWorkflowExecutor(data, "test.yaml")
        
        result = executor.run(["--dry-run"])
        
        assert result["dry_run"] is True
        assert result["results"][0]["type"] == "workflow"

    def test_dry_run_parallel_step(self):
        """Dry run should show parallel step info."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        data = {
            "type": "hybrid",
            "name": "test-hybrid",
            "steps": [{"name": "Parallel", "parallel": [{"run": "echo 1"}, {"run": "echo 2"}]}]
        }
        executor = HybridWorkflowExecutor(data, "test.yaml")
        
        result = executor.run(["--dry-run"])
        
        assert result["dry_run"] is True
        assert result["results"][0]["type"] == "parallel"


class TestHybridWorkflowExecution:
    """Test actual execution of hybrid workflow steps."""

    def test_execute_shell_step(self):
        """Shell step should execute correctly."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        data = {
            "type": "hybrid",
            "name": "test-hybrid",
            "steps": [{"name": "Echo", "run": "echo hello"}]
        }
        executor = HybridWorkflowExecutor(data, "test.yaml")
        
        result = executor.run([])
        
        assert result["ok"] is True
        assert result["results"][0]["status"] == "ok"

    def test_execute_parallel_shell_steps(self):
        """Parallel shell steps should execute correctly."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        data = {
            "type": "hybrid",
            "name": "test-hybrid",
            "steps": [{
                "name": "Parallel Echo",
                "parallel": [
                    {"run": "echo one"},
                    {"run": "echo two"}
                ]
            }]
        }
        executor = HybridWorkflowExecutor(data, "test.yaml")
        
        result = executor.run([])
        
        assert result["ok"] is True
        assert result["results"][0]["status"] == "ok"

    def test_execute_agent_step_with_mock(self):
        """Agent step should execute with mocked Agent."""
        from praisonai.cli.features.hybrid_workflow import HybridWorkflowExecutor
        
        data = {
            "type": "hybrid",
            "name": "test-hybrid",
            "steps": [{"name": "Generate", "agent": {"role": "Writer", "instructions": "Write"}}]
        }
        executor = HybridWorkflowExecutor(data, "test.yaml")
        
        with patch('praisonaiagents.Agent') as MockAgent:
            mock_agent = Mock()
            mock_agent.chat.return_value = "Generated content"
            MockAgent.return_value = mock_agent
            
            result = executor.run([])
            
            assert result["ok"] is True
            assert result["results"][0]["status"] == "ok"


class TestHybridWorkflowRouting:
    """Test that workflow.py correctly routes to HybridWorkflowExecutor."""

    def test_hybrid_type_detection(self):
        """type: hybrid should be detected in workflow routing."""
        from praisonai.cli.features.workflow import WorkflowHandler
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a hybrid workflow file
            workflow_file = Path(tmpdir) / "hybrid.yaml"
            workflow_file.write_text("""
type: hybrid
name: test-hybrid
steps:
  - name: Echo
    run: echo hello
""")
            
            handler = WorkflowHandler()
            
            # Dry run should work
            result = handler.action_run([str(workflow_file), "--dry-run"])
            
            assert result is not None
            assert result["dry_run"] is True


class TestJobWorkflowAutoGenerator:
    """Test JobWorkflowAutoGenerator (Strategy 4)."""

    def test_generator_initialization(self):
        """Generator should initialize correctly."""
        from praisonai.auto import JobWorkflowAutoGenerator
        
        generator = JobWorkflowAutoGenerator(
            topic="Generate changelog",
            workflow_file="test.yaml"
        )
        
        assert generator.topic == "Generate changelog"
        assert generator.workflow_file == "test.yaml"

    def test_generator_prompt_includes_agent_steps(self):
        """Generated prompt should include agent step types."""
        from praisonai.auto import JobWorkflowAutoGenerator
        
        generator = JobWorkflowAutoGenerator(topic="Test task")
        prompt = generator._get_prompt(include_judge=True, include_approve=False)
        
        assert "agent" in prompt
        assert "judge" in prompt
        assert "approve" in prompt
        assert "run" in prompt
        assert "action" in prompt

    def test_generator_prompt_with_judge_flag(self):
        """Prompt should include judge requirement when flag is set."""
        from praisonai.auto import JobWorkflowAutoGenerator
        
        generator = JobWorkflowAutoGenerator(topic="Test task")
        prompt = generator._get_prompt(include_judge=True, include_approve=False)
        
        assert "judge" in prompt.lower()

    def test_generator_prompt_with_approve_flag(self):
        """Prompt should include approve requirement when flag is set."""
        from praisonai.auto import JobWorkflowAutoGenerator
        
        generator = JobWorkflowAutoGenerator(topic="Test task")
        prompt = generator._get_prompt(include_judge=False, include_approve=True)
        
        assert "approve" in prompt.lower()


class TestWorkflowAutoCliTypeFlag:
    """Test --type flag in workflow auto CLI."""

    def test_action_auto_parses_type_flag(self):
        """action_auto should parse --type flag."""
        from praisonai.cli.features.workflow import WorkflowHandler
        
        handler = WorkflowHandler()
        
        # Test that --type job is recognized (will fail at generation but parsing works)
        with patch.object(handler, 'print_status'):
            # This will fail because no topic, but we're testing flag parsing
            result = handler.action_auto(["--type", "job"])
            assert result is None  # No topic provided

    def test_action_auto_validates_type(self):
        """action_auto should validate type values."""
        from praisonai.cli.features.workflow import WorkflowHandler
        
        handler = WorkflowHandler()
        
        with patch.object(handler, 'print_status') as mock_print:
            result = handler.action_auto(["test topic", "--type", "invalid"])
            
            # Should print error about invalid type
            assert result is None
            mock_print.assert_called()
