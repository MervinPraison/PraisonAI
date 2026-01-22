"""
TDD Tests for Agent Training Orchestrator.

Tests for AgentTrainer class that orchestrates the training loop.
"""

from unittest.mock import Mock, patch
import tempfile
from pathlib import Path


class TestAgentTrainer:
    """Tests for AgentTrainer class."""
    
    def test_create_trainer_with_agent(self):
        """Test creating trainer with an agent."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Agent response")
        
        trainer = AgentTrainer(agent=mock_agent)
        
        assert trainer.agent == mock_agent
        assert trainer.iterations == 3  # Default
        assert trainer.human_mode is False  # Default is LLM mode
    
    def test_create_trainer_with_custom_iterations(self):
        """Test creating trainer with custom iteration count."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        
        mock_agent = Mock()
        trainer = AgentTrainer(agent=mock_agent, iterations=5)
        
        assert trainer.iterations == 5
    
    def test_create_trainer_human_mode(self):
        """Test creating trainer in human-in-the-loop mode."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        
        mock_agent = Mock()
        trainer = AgentTrainer(agent=mock_agent, human_mode=True)
        
        assert trainer.human_mode is True
    
    def test_trainer_generates_session_id(self):
        """Test that trainer generates unique session ID."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        
        mock_agent = Mock()
        trainer1 = AgentTrainer(agent=mock_agent)
        trainer2 = AgentTrainer(agent=mock_agent)
        
        assert trainer1.session_id.startswith("train-")
        assert trainer1.session_id != trainer2.session_id
    
    def test_add_scenario(self):
        """Test adding training scenarios."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        from praisonai.train.agents.models import TrainingScenario
        
        mock_agent = Mock()
        trainer = AgentTrainer(agent=mock_agent)
        
        scenario = TrainingScenario(
            id="s1",
            input_text="What is AI?"
        )
        trainer.add_scenario(scenario)
        
        assert len(trainer.scenarios) == 1
        assert trainer.scenarios[0].id == "s1"
    
    def test_add_scenario_from_dict(self):
        """Test adding scenario from dictionary."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        
        mock_agent = Mock()
        trainer = AgentTrainer(agent=mock_agent)
        
        trainer.add_scenario({
            "id": "s2",
            "input_text": "Explain Python",
            "expected_output": "Python is a language"
        })
        
        assert len(trainer.scenarios) == 1
        assert trainer.scenarios[0].input_text == "Explain Python"
    
    @patch("praisonai.train.agents.orchestrator.TrainingGrader")
    def test_run_llm_mode_single_iteration(self, mock_grader_class):
        """Test running single iteration in LLM mode."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        from praisonai.train.agents.models import TrainingScenario
        from praisonai.train.agents.grader import GradeResult
        
        # Setup mocks
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Agent response")
        
        mock_grader = Mock()
        mock_grader.grade = Mock(return_value=GradeResult(
            score=8.0,
            reasoning="Good",
            suggestions=["Be more specific"],
            input_text="Test",
            output="Agent response"
        ))
        mock_grader_class.return_value = mock_grader
        
        # Create trainer
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = AgentTrainer(
                agent=mock_agent,
                iterations=1,
                storage_dir=Path(tmpdir)
            )
            trainer.add_scenario(TrainingScenario(id="s1", input_text="Test"))
            
            report = trainer.run()
        
        assert report is not None
        assert len(report.iterations) == 1
        assert report.iterations[0].score == 8.0
    
    @patch("praisonai.train.agents.orchestrator.TrainingGrader")
    def test_run_llm_mode_multiple_iterations(self, mock_grader_class):
        """Test running multiple iterations shows improvement."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        from praisonai.train.agents.models import TrainingScenario
        from praisonai.train.agents.grader import GradeResult
        
        mock_agent = Mock()
        call_count = [0]
        
        def agent_response(prompt):
            call_count[0] += 1
            return f"Response {call_count[0]}"
        
        mock_agent.chat = Mock(side_effect=agent_response)
        
        # Grader returns improving scores
        scores = [6.0, 7.5, 9.0]
        score_idx = [0]
        
        def grade_response(*args, **kwargs):
            score = scores[min(score_idx[0], len(scores)-1)]
            score_idx[0] += 1
            return GradeResult(
                score=score,
                reasoning=f"Score {score}",
                suggestions=["Improve"],
                input_text="Test",
                output="Output"
            )
        
        mock_grader = Mock()
        mock_grader.grade = Mock(side_effect=grade_response)
        mock_grader_class.return_value = mock_grader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = AgentTrainer(
                agent=mock_agent,
                iterations=3,
                storage_dir=Path(tmpdir)
            )
            trainer.add_scenario(TrainingScenario(id="s1", input_text="Test"))
            
            report = trainer.run()
        
        assert len(report.iterations) == 3
        assert report.improvement > 0  # Should show improvement
    
    @patch("builtins.input")
    def test_run_human_mode_prompts_for_feedback(self, mock_input):
        """Test that human mode prompts for feedback."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        from praisonai.train.agents.models import TrainingScenario
        
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Agent response")
        
        # Mock input sequence: score, feedback, suggestions
        mock_input.side_effect = ["8", "Good feedback", "suggestion1, suggestion2"]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = AgentTrainer(
                agent=mock_agent,
                iterations=1,
                human_mode=True,
                storage_dir=Path(tmpdir),
                verbose=False,  # Suppress output in tests
            )
            trainer.add_scenario(TrainingScenario(id="s1", input_text="Test"))
            
            report = trainer.run()
        
        # Should have called input() for feedback
        mock_input.assert_called()
        assert len(report.iterations) == 1
    
    def test_run_without_scenarios_raises(self):
        """Test that running without scenarios raises error."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        import pytest
        
        mock_agent = Mock()
        trainer = AgentTrainer(agent=mock_agent)
        
        with pytest.raises(ValueError, match="No scenarios"):
            trainer.run()
    
    @patch("praisonai.train.agents.orchestrator.TrainingGrader")
    def test_run_saves_to_storage(self, mock_grader_class):
        """Test that run saves iterations to storage."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        from praisonai.train.agents.models import TrainingScenario
        from praisonai.train.agents.grader import GradeResult
        import json
        
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Response")
        
        mock_grader = Mock()
        mock_grader.grade = Mock(return_value=GradeResult(
            score=7.0,
            reasoning="OK",
            suggestions=[],
            input_text="Test",
            output="Response"
        ))
        mock_grader_class.return_value = mock_grader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = AgentTrainer(
                agent=mock_agent,
                iterations=1,
                storage_dir=Path(tmpdir)
            )
            trainer.add_scenario(TrainingScenario(id="s1", input_text="Test"))
            
            trainer.run()
            
            # Check storage file exists
            storage_file = Path(tmpdir) / f"{trainer.session_id}.json"
            assert storage_file.exists()
            
            with open(storage_file) as f:
                data = json.load(f)
            
            assert "iterations" in data


class TestAgentTrainerWithAgents:
    """Tests for AgentTrainer with multi-agent (Agents class)."""
    
    @patch("praisonai.train.agents.orchestrator.TrainingGrader")
    def test_trainer_works_with_agents_class(self, mock_grader_class):
        """Test trainer works with Agents (multi-agent) class."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        from praisonai.train.agents.models import TrainingScenario
        from praisonai.train.agents.grader import GradeResult
        
        # Mock Agents class (has start() method but NOT chat())
        mock_agents = Mock(spec=['start'])  # Only has start, not chat
        mock_agents.start = Mock(return_value="Multi-agent response")
        
        mock_grader = Mock()
        mock_grader.grade = Mock(return_value=GradeResult(
            score=8.0,
            reasoning="Good",
            suggestions=[],
            input_text="Test",
            output="Response"
        ))
        mock_grader_class.return_value = mock_grader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = AgentTrainer(
                agent=mock_agents,
                iterations=1,
                storage_dir=Path(tmpdir),
                verbose=False,
            )
            trainer.add_scenario(TrainingScenario(id="s1", input_text="Test"))
            
            report = trainer.run()
        
        assert report is not None
        mock_agents.start.assert_called()


class TestAgentTrainerCallable:
    """Tests for AgentTrainer with callable functions."""
    
    @patch("praisonai.train.agents.orchestrator.TrainingGrader")
    def test_trainer_works_with_callable(self, mock_grader_class):
        """Test trainer works with a callable function."""
        from praisonai.train.agents.orchestrator import AgentTrainer
        from praisonai.train.agents.models import TrainingScenario
        from praisonai.train.agents.grader import GradeResult
        
        def my_func(prompt):
            return f"Response to: {prompt}"
        
        mock_grader = Mock()
        mock_grader.grade = Mock(return_value=GradeResult(
            score=7.5,
            reasoning="OK",
            suggestions=[],
            input_text="Test",
            output="Response"
        ))
        mock_grader_class.return_value = mock_grader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = AgentTrainer(
                agent=my_func,
                iterations=1,
                storage_dir=Path(tmpdir)
            )
            trainer.add_scenario(TrainingScenario(id="s1", input_text="Hello"))
            
            report = trainer.run()
        
        assert report is not None
