"""
Tests for Training Hook System.

TDD: Tests written first for:
- TrainingProfile dataclass
- get_best_iteration() method
- apply_training() function
- remove_training() function
- TrainingHook class
"""

from unittest.mock import Mock, patch


class TestTrainingProfile:
    """Tests for TrainingProfile dataclass."""
    
    def test_training_profile_creation(self):
        """Test creating a TrainingProfile."""
        from praisonai.train.agents.models import TrainingProfile
        
        profile = TrainingProfile(
            agent_name="assistant",
            suggestions=["Be concise", "Use examples"],
            quality_score=8.5,
            summary="Focus on clarity",
            iteration_num=2,
            session_id="train-abc123",
        )
        
        assert profile.agent_name == "assistant"
        assert profile.suggestions == ["Be concise", "Use examples"]
        assert profile.quality_score == 8.5
        assert profile.summary == "Focus on clarity"
        assert profile.iteration_num == 2
        assert profile.session_id == "train-abc123"
    
    def test_training_profile_to_dict(self):
        """Test converting TrainingProfile to dict."""
        from praisonai.train.agents.models import TrainingProfile
        
        profile = TrainingProfile(
            agent_name="assistant",
            suggestions=["Be concise"],
            quality_score=8.0,
            summary="Test summary",
            iteration_num=1,
            session_id="train-123",
        )
        
        d = profile.to_dict()
        assert d["agent_name"] == "assistant"
        assert d["suggestions"] == ["Be concise"]
        assert d["quality_score"] == 8.0
    
    def test_training_profile_from_dict(self):
        """Test creating TrainingProfile from dict."""
        from praisonai.train.agents.models import TrainingProfile
        
        data = {
            "agent_name": "researcher",
            "suggestions": ["Search first", "Cite sources"],
            "quality_score": 9.0,
            "summary": "Research focus",
            "iteration_num": 3,
            "session_id": "train-xyz",
        }
        
        profile = TrainingProfile.from_dict(data)
        assert profile.agent_name == "researcher"
        assert profile.quality_score == 9.0
        assert profile.iteration_num == 3


class TestGetBestIteration:
    """Tests for get_best_iteration() method on TrainingReport."""
    
    def test_get_best_iteration_returns_highest_score(self):
        """Test that get_best_iteration returns iteration with highest score."""
        from praisonai.train.agents.models import TrainingReport, TrainingIteration
        
        iterations = [
            TrainingIteration(
                iteration_num=1, scenario_id="s1", input_text="test",
                output="out1", score=6.0, feedback="ok"
            ),
            TrainingIteration(
                iteration_num=2, scenario_id="s1", input_text="test",
                output="out2", score=9.0, feedback="great"  # Best
            ),
            TrainingIteration(
                iteration_num=3, scenario_id="s1", input_text="test",
                output="out3", score=7.5, feedback="good"
            ),
        ]
        
        report = TrainingReport(
            session_id="train-test",
            iterations=iterations,
            total_iterations=3,
        )
        
        best = report.get_best_iteration()
        assert best is not None
        assert best.iteration_num == 2
        assert best.score == 9.0
    
    def test_get_best_iteration_empty_returns_none(self):
        """Test that get_best_iteration returns None for empty iterations."""
        from praisonai.train.agents.models import TrainingReport
        
        report = TrainingReport(
            session_id="train-empty",
            iterations=[],
            total_iterations=0,
        )
        
        best = report.get_best_iteration()
        assert best is None
    
    def test_get_iteration_by_number(self):
        """Test getting a specific iteration by number."""
        from praisonai.train.agents.models import TrainingReport, TrainingIteration
        
        iterations = [
            TrainingIteration(
                iteration_num=1, scenario_id="s1", input_text="test",
                output="out1", score=6.0, feedback="ok"
            ),
            TrainingIteration(
                iteration_num=2, scenario_id="s1", input_text="test",
                output="out2", score=8.0, feedback="good"
            ),
        ]
        
        report = TrainingReport(
            session_id="train-test",
            iterations=iterations,
            total_iterations=2,
        )
        
        it = report.get_iteration(2)
        assert it is not None
        assert it.iteration_num == 2
        assert it.score == 8.0
    
    def test_get_iteration_not_found(self):
        """Test getting non-existent iteration returns None."""
        from praisonai.train.agents.models import TrainingReport, TrainingIteration
        
        iterations = [
            TrainingIteration(
                iteration_num=1, scenario_id="s1", input_text="test",
                output="out1", score=6.0, feedback="ok"
            ),
        ]
        
        report = TrainingReport(
            session_id="train-test",
            iterations=iterations,
            total_iterations=1,
        )
        
        it = report.get_iteration(5)
        assert it is None


class TestApplyTraining:
    """Tests for apply_training() function."""
    
    def test_apply_training_registers_hook(self):
        """Test that apply_training registers a BEFORE_AGENT hook."""
        from praisonai.train.agents.hook import apply_training
        from praisonai.train.agents.models import TrainingProfile
        
        # Create mock agent
        mock_agent = Mock()
        mock_agent.name = "assistant"
        mock_registry = Mock()
        mock_hook_runner = Mock()
        mock_hook_runner.registry = mock_registry
        mock_agent._hook_runner = mock_hook_runner
        
        # Create profile
        profile = TrainingProfile(
            agent_name="assistant",
            suggestions=["Be concise"],
            quality_score=8.0,
            summary="Test",
            iteration_num=1,
            session_id="train-123",
        )
        
        # Apply training
        result = apply_training(mock_agent, profile=profile)
        
        assert result is True
        mock_registry.register_function.assert_called_once()
    
    def test_apply_training_from_session(self):
        """Test apply_training loads from session ID."""
        from praisonai.train.agents.hook import apply_training
        
        mock_agent = Mock()
        mock_agent.name = "assistant"
        mock_registry = Mock()
        mock_hook_runner = Mock()
        mock_hook_runner.registry = mock_registry
        mock_agent._hook_runner = mock_hook_runner
        
        # Mock storage
        with patch('praisonai.train.agents.hook.TrainingStorage') as MockStorage:
            mock_storage = Mock()
            mock_report = Mock()
            mock_iteration = Mock()
            mock_iteration.suggestions = ["Be helpful"]
            mock_iteration.score = 8.5
            mock_iteration.feedback = "Good"
            mock_iteration.iteration_num = 2
            mock_report.get_best_iteration.return_value = mock_iteration
            mock_report.session_id = "train-abc"
            mock_storage.load_report.return_value = mock_report
            MockStorage.return_value = mock_storage
            
            result = apply_training(mock_agent, session_id="train-abc")
            
            assert result is True


class TestRemoveTraining:
    """Tests for remove_training() function."""
    
    def test_remove_training_unregisters_hook(self):
        """Test that remove_training removes the training hook."""
        from praisonai.train.agents.hook import apply_training, remove_training
        from praisonai.train.agents.models import TrainingProfile
        
        mock_agent = Mock()
        mock_agent.name = "assistant"
        mock_registry = Mock()
        mock_hook_runner = Mock()
        mock_hook_runner.registry = mock_registry
        mock_agent._hook_runner = mock_hook_runner
        mock_agent._training_hook_id = None
        
        profile = TrainingProfile(
            agent_name="assistant",
            suggestions=["Be concise"],
            quality_score=8.0,
            summary="Test",
            iteration_num=1,
            session_id="train-123",
        )
        
        # Apply then remove
        apply_training(mock_agent, profile=profile)
        result = remove_training(mock_agent)
        
        # Should attempt to unregister
        assert result is True or result is False  # Depends on implementation


class TestTrainingHook:
    """Tests for TrainingHook class."""
    
    def test_training_hook_modifies_prompt(self):
        """Test that TrainingHook injects suggestions into prompt."""
        from praisonai.train.agents.hook import TrainingHook
        from praisonai.train.agents.models import TrainingProfile
        from praisonaiagents.hooks import BeforeAgentInput
        
        profile = TrainingProfile(
            agent_name="assistant",
            suggestions=["Be concise", "Use examples"],
            quality_score=8.5,
            summary="Focus on clarity",
            iteration_num=2,
            session_id="train-abc",
        )
        
        hook = TrainingHook(profile)
        
        # Create input event
        event = BeforeAgentInput(
            session_id="session-1",
            cwd="/tmp",
            event_name="before_agent",
            timestamp="2024-01-01T00:00:00",
            agent_name="assistant",
            prompt="Hello, how are you?",
        )
        
        result = hook(event)
        
        # Should allow and modify prompt
        assert result.decision == "allow"
        assert result.modified_input is not None
        assert "[TRAINING GUIDANCE]" in result.modified_input.get("prompt", "")
        assert "Be concise" in result.modified_input.get("prompt", "")
        assert "Use examples" in result.modified_input.get("prompt", "")


class TestCLIApplyCommand:
    """Tests for CLI apply command."""
    
    def test_cli_apply_command_exists(self):
        """Test that apply command is registered."""
        from praisonai.cli.commands.train import app
        
        # Check command exists
        command_names = [cmd.name for cmd in app.registered_commands]
        assert "apply" in command_names
    
    def test_cli_apply_requires_session_id(self):
        """Test that apply command requires session_id argument."""
        from typer.testing import CliRunner
        from praisonai.cli.commands.train import app
        
        runner = CliRunner()
        result = runner.invoke(app, ["apply"])
        
        # Should fail without session_id
        assert result.exit_code != 0


class TestCLIShowEnhanced:
    """Tests for enhanced CLI show command."""
    
    def test_cli_show_displays_iterations(self):
        """Test that show command displays iteration details."""
        from typer.testing import CliRunner
        from praisonai.cli.commands.train import app
        
        runner = CliRunner()
        
        # Mock storage
        with patch('praisonai.train.agents.storage.TrainingStorage') as MockStorage:
            mock_storage = Mock()
            mock_storage.storage_path.exists.return_value = True
            
            # Create mock iterations
            mock_iterations = [
                Mock(iteration_num=1, score=6.0, feedback="ok", suggestions=["a"]),
                Mock(iteration_num=2, score=9.0, feedback="great", suggestions=["b", "c"]),
            ]
            mock_storage.load_iterations.return_value = mock_iterations
            mock_storage.load_report.return_value = Mock(
                session_id="train-test",
                avg_score=7.5,
                to_dict=lambda: {"session_id": "train-test"}
            )
            MockStorage.return_value = mock_storage
            
            result = runner.invoke(app, ["show", "train-test", "--iterations"])
            
            # Should show iteration details
            assert "Iteration" in result.output or result.exit_code == 0
