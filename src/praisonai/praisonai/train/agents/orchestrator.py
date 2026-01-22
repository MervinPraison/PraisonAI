"""
Agent Training Orchestrator.

Orchestrates the training loop for iteratively improving agent behavior.
Supports two modes:
1. LLM-as-Judge (default): Automated review and optimization
2. Human-in-the-Loop: Interactive feedback from humans

Usage:
    # LLM mode (default)
    trainer = AgentTrainer(agent=my_agent)
    trainer.add_scenario(TrainingScenario(id="s1", input_text="Hello"))
    report = trainer.run()
    
    # Human mode
    trainer = AgentTrainer(agent=my_agent, human_mode=True)
    trainer.add_scenario(TrainingScenario(id="s1", input_text="Hello"))
    report = trainer.run()
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING

from .grader import TrainingGrader, GradeResult
from .models import TrainingIteration, TrainingReport, TrainingScenario
from .storage import TrainingStorage

if TYPE_CHECKING:
    from praisonaiagents import Agent, Agents

logger = logging.getLogger(__name__)


class AgentTrainer:
    """
    Orchestrates agent training through iterative feedback loops.
    
    Two modes are supported:
    
    1. **LLM-as-Judge (default)**: The agent runs, an LLM grades the output,
       provides suggestions, and the agent re-runs with the feedback.
       This is fully automated and requires no human intervention.
    
    2. **Human-in-the-Loop**: The agent runs, a human reviews the output
       and provides feedback, then the agent re-runs with the feedback.
       This requires interactive input from the user.
    
    Example:
        from praisonai.train.agents import AgentTrainer, TrainingScenario
        from praisonaiagents import Agent
        
        agent = Agent(instructions="You are a helpful assistant")
        
        trainer = AgentTrainer(agent=agent, iterations=3)
        trainer.add_scenario(TrainingScenario(
            id="greeting",
            input_text="Hello, how are you?",
            expected_output="I'm doing well, thank you for asking!"
        ))
        
        report = trainer.run()
        report.print_summary()
    """
    
    def __init__(
        self,
        agent: Union["Agent", "Agents", Callable[[str], str]],
        iterations: int = 3,
        human_mode: bool = False,
        grader: Optional[TrainingGrader] = None,
        storage_dir: Optional[Path] = None,
        storage_backend: Optional[Any] = None,
        verbose: bool = True,
    ):
        """
        Initialize the trainer.
        
        Args:
            agent: Agent, Agents, or callable to train
            iterations: Number of training iterations (default: 3)
            human_mode: Use human feedback instead of LLM grading (default: False)
            grader: Custom grader instance (default: TrainingGrader())
            storage_dir: Directory for storing training data
            storage_backend: Storage backend (FileBackend, SQLiteBackend, RedisBackend)
            verbose: Print progress during training (default: True)
        """
        self.agent = agent
        self.iterations = iterations
        self.human_mode = human_mode
        self.grader = grader
        self.storage_dir = storage_dir
        self.storage_backend = storage_backend
        self.verbose = verbose
        
        self.session_id = f"train-{uuid.uuid4().hex[:8]}"
        self.scenarios: List[TrainingScenario] = []
        
        self._storage: Optional[TrainingStorage] = None
    
    def add_scenario(
        self,
        scenario: Union[TrainingScenario, Dict[str, Any]],
    ) -> None:
        """
        Add a training scenario.
        
        Args:
            scenario: TrainingScenario or dict with scenario data
        """
        if isinstance(scenario, dict):
            scenario = TrainingScenario.from_dict(scenario)
        self.scenarios.append(scenario)
    
    def add_scenarios(
        self,
        scenarios: List[Union[TrainingScenario, Dict[str, Any]]],
    ) -> None:
        """
        Add multiple training scenarios.
        
        Args:
            scenarios: List of TrainingScenario or dicts
        """
        for scenario in scenarios:
            self.add_scenario(scenario)
    
    def _get_agent_output(self, prompt: str) -> str:
        """
        Get output from the agent.
        
        Handles different agent types (Agent, Agents, callable).
        
        Args:
            prompt: Input prompt
            
        Returns:
            Agent's output string
        """
        # Callable function
        if callable(self.agent) and not hasattr(self.agent, 'chat') and not hasattr(self.agent, 'start'):
            return str(self.agent(prompt))
        
        # Agent with chat method
        if hasattr(self.agent, 'chat'):
            result = self.agent.chat(prompt)
            return str(result)
        
        # Agents with start method
        if hasattr(self.agent, 'start'):
            result = self.agent.start(prompt)
            if hasattr(result, 'raw'):
                return str(result.raw)
            return str(result)
        
        raise ValueError(
            "Agent must have 'chat' method, 'start' method, or be callable"
        )
    
    def _get_human_feedback(self, output: str, scenario: TrainingScenario) -> GradeResult:
        """
        Get feedback from human.
        
        Args:
            output: Agent's output to review
            scenario: The scenario being trained
            
        Returns:
            GradeResult with human feedback
        """
        print("\n" + "=" * 60)
        print("AGENT OUTPUT:")
        print("-" * 60)
        print(output)
        print("-" * 60)
        
        if scenario.expected_output:
            print("\nEXPECTED OUTPUT:")
            print(scenario.expected_output)
            print("-" * 60)
        
        # Get score
        while True:
            try:
                score_input = input("\nScore (1-10): ").strip()
                score = float(score_input)
                if 1 <= score <= 10:
                    break
                print("Please enter a number between 1 and 10")
            except ValueError:
                print("Please enter a valid number")
        
        # Get feedback
        feedback = input("Feedback (what could be improved?): ").strip()
        if not feedback:
            feedback = "No specific feedback provided"
        
        # Get suggestions
        suggestions_input = input("Suggestions (comma-separated, or press Enter to skip): ").strip()
        suggestions = []
        if suggestions_input:
            suggestions = [s.strip() for s in suggestions_input.split(",") if s.strip()]
        
        return GradeResult(
            score=score,
            reasoning=feedback,
            suggestions=suggestions,
            input_text=scenario.input_text,
            output=output,
            expected_output=scenario.expected_output,
        )
    
    def _build_improvement_prompt(
        self,
        original_prompt: str,
        previous_output: str,
        grade_result: GradeResult,
    ) -> str:
        """
        Build prompt with improvement feedback.
        
        Args:
            original_prompt: Original input
            previous_output: Previous agent output
            grade_result: Grading result with feedback
            
        Returns:
            Enhanced prompt with feedback
        """
        prompt = original_prompt
        
        if grade_result.suggestions:
            suggestions_text = "\n".join(f"- {s}" for s in grade_result.suggestions)
            prompt += "\n\n[FEEDBACK FROM PREVIOUS ATTEMPT]\n"
            prompt += f"Score: {grade_result.score}/10\n"
            prompt += f"Feedback: {grade_result.reasoning}\n"
            prompt += f"Suggestions for improvement:\n{suggestions_text}\n"
            prompt += "\nPlease provide an improved response addressing this feedback."
        
        return prompt
    
    def run(self) -> TrainingReport:
        """
        Run the training loop.
        
        Returns:
            TrainingReport with all iterations and statistics
            
        Raises:
            ValueError: If no scenarios have been added
        """
        if not self.scenarios:
            raise ValueError(
                "No scenarios added. Use add_scenario() to add training scenarios."
            )
        
        # Initialize storage
        self._storage = TrainingStorage(
            session_id=self.session_id,
            storage_dir=self.storage_dir,
            backend=self.storage_backend,
        )
        
        # Initialize grader for LLM mode
        if not self.human_mode and self.grader is None:
            self.grader = TrainingGrader()
        
        # Save scenarios
        for scenario in self.scenarios:
            self._storage.save_scenario(scenario)
        
        all_iterations: List[TrainingIteration] = []
        started_at = datetime.utcnow().isoformat()
        
        if self.verbose:
            mode = "Human-in-the-Loop" if self.human_mode else "LLM-as-Judge"
            print("\n" + "="*60)
            print("Starting Agent Training")
            print(f"Mode: {mode}")
            print(f"Scenarios: {len(self.scenarios)}")
            print(f"Iterations: {self.iterations}")
            print(f"Session: {self.session_id}")
            print("="*60 + "\n")
        
        for scenario in self.scenarios:
            if self.verbose:
                print(f"\n--- Scenario: {scenario.id} ---")
            
            current_prompt = scenario.input_text
            previous_output = None
            previous_grade = None
            
            for iteration_num in range(1, self.iterations + 1):
                if self.verbose:
                    print(f"\nIteration {iteration_num}/{self.iterations}")
                
                # Build prompt with feedback if not first iteration
                if previous_grade is not None and previous_output is not None:
                    current_prompt = self._build_improvement_prompt(
                        scenario.input_text,
                        previous_output,
                        previous_grade,
                    )
                
                # Get agent output
                try:
                    output = self._get_agent_output(current_prompt)
                except Exception as e:
                    logger.error(f"Agent error: {e}")
                    output = f"Error: {str(e)}"
                
                # Grade the output
                if self.human_mode:
                    grade_result = self._get_human_feedback(output, scenario)
                else:
                    grade_result = self.grader.grade(
                        input_text=scenario.input_text,
                        output=output,
                        expected_output=scenario.expected_output,
                    )
                
                if self.verbose:
                    print(f"  Score: {grade_result.score}/10")
                    if grade_result.suggestions:
                        print(f"  Suggestions: {', '.join(grade_result.suggestions[:2])}")
                
                # Create iteration record
                iteration = TrainingIteration(
                    iteration_num=iteration_num,
                    scenario_id=scenario.id,
                    input_text=scenario.input_text,
                    output=output,
                    score=grade_result.score,
                    feedback=grade_result.reasoning,
                    suggestions=grade_result.suggestions,
                    metadata={
                        "mode": "human" if self.human_mode else "llm",
                        "prompt_used": current_prompt,
                    }
                )
                
                all_iterations.append(iteration)
                self._storage.save_iteration(iteration)
                
                # Update for next iteration
                previous_output = output
                previous_grade = grade_result
                
                # Early stop if score is high enough
                if grade_result.score >= 9.5:
                    if self.verbose:
                        print("  ✓ Excellent score achieved, stopping early")
                    break
        
        # Create report
        report = TrainingReport(
            session_id=self.session_id,
            iterations=all_iterations,
            total_iterations=len(all_iterations),
            started_at=started_at,
            completed_at=datetime.utcnow().isoformat(),
            metadata={
                "mode": "human" if self.human_mode else "llm",
                "scenarios_count": len(self.scenarios),
                "target_iterations": self.iterations,
            }
        )
        
        self._storage.save_report(report)
        
        if self.verbose:
            print("\n" + "="*60)
            print("Training Complete!")
            report.print_summary()
        
        return report
    
    async def run_async(self) -> TrainingReport:
        """
        Run the training loop asynchronously.
        
        Note: Human mode is not supported in async.
        
        Returns:
            TrainingReport with all iterations and statistics
        """
        if self.human_mode:
            raise ValueError("Human mode is not supported in async training")
        
        # For now, delegate to sync version
        # TODO: Implement true async with acompletion
        return self.run()
