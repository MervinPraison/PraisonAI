"""
TDD Tests for Agent-Centric Job Workflow Steps.

Tests the new step types: agent:, judge:, approve:
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


class TestStepTypeDetection:
    """Test _detect_step_type for new agent-centric step types."""

    def test_detect_agent_step(self):
        """agent: step should be detected."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        step_type, target = executor._detect_step_type({"agent": {"role": "Writer"}})
        
        assert step_type == "agent"
        assert target == {"role": "Writer"}

    def test_detect_agent_step_string(self):
        """agent: step with string value should be detected."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        step_type, target = executor._detect_step_type({"agent": "Write a poem"})
        
        assert step_type == "agent"
        assert target == "Write a poem"

    def test_detect_judge_step(self):
        """judge: step should be detected."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        step_type, target = executor._detect_step_type({
            "judge": {"criteria": "Quality check", "threshold": 8.0}
        })
        
        assert step_type == "judge"
        assert target["criteria"] == "Quality check"
        assert target["threshold"] == 8.0

    def test_detect_approve_step(self):
        """approve: step should be detected."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        step_type, target = executor._detect_step_type({
            "approve": {"description": "Deploy to prod", "risk_level": "high"}
        })
        
        assert step_type == "approve"
        assert target["description"] == "Deploy to prod"
        assert target["risk_level"] == "high"

    def test_detect_shell_step_unchanged(self):
        """Existing shell step detection should still work."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        step_type, target = executor._detect_step_type({"run": "echo hello"})
        
        assert step_type == "shell"
        assert target == "echo hello"

    def test_detect_action_step_unchanged(self):
        """Existing action step detection should still work."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        step_type, target = executor._detect_step_type({"action": "bump-version"})
        
        assert step_type == "action"
        assert target == "bump-version"


class TestAgentStepExecution:
    """Test _exec_agent_step method."""

    @patch('praisonai.cli.features.job_workflow.JobWorkflowExecutor._resolve_agent_tools')
    def test_agent_step_with_dict_config(self, mock_resolve_tools):
        """Agent step with dict config should create and run agent."""
        mock_resolve_tools.return_value = []
        
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        # Mock the Agent class
        with patch('praisonaiagents.Agent') as MockAgent:
            mock_agent = Mock()
            mock_agent.chat.return_value = "Generated content"
            MockAgent.return_value = mock_agent
            
            result = executor._exec_agent_step(
                {"role": "Writer", "instructions": "Write something"},
                {"name": "Write step"},
                {}
            )
            
            assert result["ok"] is True
            assert result["output"] == "Generated content"
            MockAgent.assert_called_once()

    @patch('praisonai.cli.features.job_workflow.JobWorkflowExecutor._resolve_agent_tools')
    def test_agent_step_with_string_config(self, mock_resolve_tools):
        """Agent step with string config should work."""
        mock_resolve_tools.return_value = []
        
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        with patch('praisonaiagents.Agent') as MockAgent:
            mock_agent = Mock()
            mock_agent.chat.return_value = "Result"
            MockAgent.return_value = mock_agent
            
            result = executor._exec_agent_step(
                "Simple instructions",
                {"name": "Simple step"},
                {}
            )
            
            assert result["ok"] is True
            assert result["output"] == "Result"

    def test_agent_step_writes_output_file(self):
        """Agent step should write output to file if specified."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = JobWorkflowExecutor({"steps": []}, f"{tmpdir}/test.yaml")
            executor._cwd = tmpdir
            
            with patch('praisonaiagents.Agent') as MockAgent:
                mock_agent = Mock()
                mock_agent.chat.return_value = "File content"
                MockAgent.return_value = mock_agent
                
                result = executor._exec_agent_step(
                    {"instructions": "Generate"},
                    {"name": "Write step", "output_file": "output.txt"},
                    {}
                )
                
                assert result["ok"] is True
                output_path = Path(tmpdir) / "output.txt"
                assert output_path.exists()
                assert output_path.read_text() == "File content"

    def test_agent_step_import_error(self):
        """Agent step should handle missing praisonaiagents gracefully."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        with patch.dict('sys.modules', {'praisonaiagents': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module")):
                result = executor._exec_agent_step(
                    {"instructions": "Test"},
                    {"name": "Test"},
                    {}
                )
                
                assert result["ok"] is False
                assert "praisonaiagents not installed" in result["error"]


class TestJudgeStepExecution:
    """Test _exec_judge_step method."""

    def test_judge_step_with_input_file(self):
        """Judge step should read input from file."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create input file
            input_file = Path(tmpdir) / "input.txt"
            input_file.write_text("Content to judge")
            
            executor = JobWorkflowExecutor({"steps": []}, f"{tmpdir}/test.yaml")
            executor._cwd = tmpdir
            
            with patch('praisonaiagents.eval.Judge') as MockJudge:
                mock_judge = Mock()
                mock_result = Mock()
                mock_result.score = 8.5
                mock_result.feedback = "Good quality"
                mock_judge.evaluate.return_value = mock_result
                MockJudge.return_value = mock_judge
                
                result = executor._exec_judge_step(
                    {"input_file": "input.txt", "criteria": "Quality", "threshold": 7.0},
                    {"name": "Quality check"},
                    {}
                )
                
                assert result["ok"] is True
                assert result["score"] == 8.5
                assert result["passed"] is True

    def test_judge_step_fails_below_threshold(self):
        """Judge step should fail if score below threshold."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "input.txt"
            input_file.write_text("Poor content")
            
            executor = JobWorkflowExecutor({"steps": []}, f"{tmpdir}/test.yaml")
            executor._cwd = tmpdir
            
            with patch('praisonaiagents.eval.Judge') as MockJudge:
                mock_judge = Mock()
                mock_result = Mock()
                mock_result.score = 5.0
                mock_result.feedback = "Needs improvement"
                mock_judge.evaluate.return_value = mock_result
                MockJudge.return_value = mock_judge
                
                result = executor._exec_judge_step(
                    {"input_file": "input.txt", "criteria": "Quality", "threshold": 7.0},
                    {"name": "Quality check"},
                    {}
                )
                
                assert result["ok"] is False
                assert result["score"] == 5.0
                assert result["passed"] is False

    def test_judge_step_warn_mode(self):
        """Judge step with on_fail=warn should pass even if below threshold."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "input.txt"
            input_file.write_text("Content")
            
            executor = JobWorkflowExecutor({"steps": []}, f"{tmpdir}/test.yaml")
            executor._cwd = tmpdir
            
            with patch('praisonaiagents.eval.Judge') as MockJudge:
                mock_judge = Mock()
                mock_result = Mock()
                mock_result.score = 5.0
                mock_result.feedback = "Below threshold"
                mock_judge.evaluate.return_value = mock_result
                MockJudge.return_value = mock_judge
                
                result = executor._exec_judge_step(
                    {"input_file": "input.txt", "threshold": 7.0, "on_fail": "warn"},
                    {"name": "Quality check"},
                    {}
                )
                
                assert result["ok"] is True  # Passes because on_fail=warn
                assert result["passed"] is False
                assert "warning" in result

    def test_judge_step_missing_input(self):
        """Judge step should fail if no input provided."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        result = executor._exec_judge_step(
            {"criteria": "Quality"},
            {"name": "Quality check"},
            {}
        )
        
        assert result["ok"] is False
        assert "requires input_file or input" in result["error"]


class TestApproveStepExecution:
    """Test _exec_approve_step method."""

    def test_approve_step_auto_approve(self):
        """Approve step with auto_approve should pass immediately."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        with patch('praisonaiagents.approval.backends.AutoApproveBackend') as MockBackend:
            mock_backend = Mock()
            mock_decision = Mock()
            mock_decision.approved = True
            mock_decision.reason = "auto-approved"
            mock_backend.request_approval_sync.return_value = mock_decision
            MockBackend.return_value = mock_backend
            
            result = executor._exec_approve_step(
                {"description": "Deploy", "auto_approve": True},
                {"name": "Approve deploy"},
                {}
            )
            
            assert result["ok"] is True
            assert result["reason"] == "auto-approved"

    def test_approve_step_string_config(self):
        """Approve step with string config should work."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        with patch('praisonaiagents.approval.backends.AutoApproveBackend') as MockBackend:
            mock_backend = Mock()
            mock_decision = Mock()
            mock_decision.approved = True
            mock_decision.reason = "approved"
            mock_backend.request_approval_sync.return_value = mock_decision
            MockBackend.return_value = mock_backend
            
            # Use auto_approve to avoid console interaction
            with patch.object(executor, '_exec_approve_step', wraps=executor._exec_approve_step):
                result = executor._exec_approve_step(
                    {"description": "Simple approval", "auto_approve": True},
                    {"name": "Approve"},
                    {}
                )
                
                assert result["ok"] is True


class TestAgentAsAction:
    """Test agent: key in YAML-defined actions (Strategy 5)."""

    def test_yaml_action_with_agent(self):
        """YAML action with agent: key should execute agent step."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        data = {
            "steps": [],
            "actions": {
                "summarize": {
                    "agent": {"role": "Summarizer", "instructions": "Summarize text"}
                }
            }
        }
        executor = JobWorkflowExecutor(data, "test.yaml")
        
        with patch.object(executor, '_exec_agent_step') as mock_exec:
            mock_exec.return_value = {"ok": True, "output": "Summary"}
            
            result = executor._exec_yaml_action(
                "summarize",
                data["actions"]["summarize"],
                {"name": "Summarize step"},
                {}
            )
            
            assert result["ok"] is True
            mock_exec.assert_called_once()


class TestDryRunDisplay:
    """Test dry-run display for new step types."""

    def test_dry_run_agent_step(self):
        """Dry run should show agent step info without executing."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        data = {
            "name": "test-workflow",
            "steps": [
                {"name": "Generate", "agent": {"role": "Writer", "model": "gpt-4o"}}
            ]
        }
        executor = JobWorkflowExecutor(data, "test.yaml")
        
        result = executor.run(["--dry-run"])
        
        assert result["dry_run"] is True
        assert result["results"][0]["status"] == "dry-run"
        assert result["results"][0]["type"] == "agent"

    def test_dry_run_judge_step(self):
        """Dry run should show judge step info without executing."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        data = {
            "name": "test-workflow",
            "steps": [
                {"name": "Quality", "judge": {"threshold": 8.5}}
            ]
        }
        executor = JobWorkflowExecutor(data, "test.yaml")
        
        result = executor.run(["--dry-run"])
        
        assert result["dry_run"] is True
        assert result["results"][0]["type"] == "judge"

    def test_dry_run_approve_step(self):
        """Dry run should show approve step info without executing."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        data = {
            "name": "test-workflow",
            "steps": [
                {"name": "Approve", "approve": {"risk_level": "high"}}
            ]
        }
        executor = JobWorkflowExecutor(data, "test.yaml")
        
        result = executor.run(["--dry-run"])
        
        assert result["dry_run"] is True
        assert result["results"][0]["type"] == "approve"


class TestResolveAgentTools:
    """Test _resolve_agent_tools method."""

    def test_resolve_callable_tools(self):
        """Callable tools should be passed through."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        def my_tool():
            pass
        
        result = executor._resolve_agent_tools([my_tool])
        
        assert len(result) == 1
        assert result[0] is my_tool

    def test_resolve_empty_tools(self):
        """Empty tools list should return empty list."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        result = executor._resolve_agent_tools([])
        
        assert result == []

    def test_resolve_none_tools(self):
        """None tools should return empty list."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({"steps": []}, "test.yaml")
        
        result = executor._resolve_agent_tools(None)
        
        assert result == []


class TestBackwardCompatibility:
    """Test that existing step types still work."""

    def test_shell_step_still_works(self):
        """Shell step should still execute correctly."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        data = {
            "name": "test-workflow",
            "steps": [
                {"name": "Echo", "run": "echo hello"}
            ]
        }
        executor = JobWorkflowExecutor(data, "test.yaml")
        
        result = executor.run([])
        
        assert result["ok"] is True
        assert result["results"][0]["status"] == "ok"

    def test_action_step_still_works(self):
        """Action step should still execute correctly."""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a pyproject.toml for bump-version
            pyproject = Path(tmpdir) / "pyproject.toml"
            pyproject.write_text('version = "1.0.0"')
            
            data = {
                "name": "test-workflow",
                "steps": [
                    {"name": "Bump", "action": "bump-version"}
                ]
            }
            executor = JobWorkflowExecutor(data, f"{tmpdir}/test.yaml")
            executor._cwd = tmpdir
            
            result = executor.run([])
            
            assert result["ok"] is True
            assert "1.0.1" in pyproject.read_text()
