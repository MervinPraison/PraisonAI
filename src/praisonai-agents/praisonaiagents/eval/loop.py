"""
EvaluationLoop - Iterative evaluation and improvement loop for agents.

This module provides the EvaluationLoop class which implements the "Ralph Loop"
pattern: run agent → judge output → improve → repeat until threshold met.

Example:
    from praisonaiagents import Agent
    from praisonaiagents.eval import EvaluationLoop
    
    agent = Agent(name="analyzer", instructions="Analyze systems")
    loop = EvaluationLoop(agent=agent, criteria="Analysis is thorough")
    result = loop.run("Analyze the auth flow")
    
    print(result.final_score)  # 8.5
    print(result.success)      # True
"""

import time
import logging
from typing import TYPE_CHECKING, Optional, Callable, Any, List
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..agent.agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class EvaluationLoopConfig:
    """Configuration for EvaluationLoop."""
    criteria: str = ""
    threshold: float = 8.0
    max_iterations: int = 5
    mode: str = "optimize"
    model: str = "gpt-4o-mini"
    verbose: bool = False


class EvaluationLoop:
    """
    Iterative evaluation loop that runs an agent, judges output, and improves.
    
    The loop continues until either:
    - The score meets or exceeds the threshold (success)
    - Max iterations is reached (failure in optimize mode)
    - All iterations complete (review mode always runs all)
    
    Args:
        agent: The Agent instance to evaluate
        criteria: Evaluation criteria for the Judge
        threshold: Score threshold for success (default: 8.0)
        max_iterations: Maximum number of iterations (default: 5)
        mode: "optimize" (stop on success) or "review" (run all iterations)
        judge: Optional custom Judge instance
        on_iteration: Optional callback called after each iteration
        verbose: Enable verbose logging
        model: LLM model for Judge (default: gpt-4o-mini)
        
    Example:
        loop = EvaluationLoop(
            agent=my_agent,
            criteria="Response is helpful and accurate",
            threshold=8.0,
            max_iterations=5,
            on_iteration=lambda r: print(f"Score: {r.score}")
        )
        result = loop.run("Analyze the codebase")
    """
    
    def __init__(
        self,
        agent: "Agent",
        criteria: str,
        threshold: float = 8.0,
        max_iterations: int = 5,
        mode: str = "optimize",
        judge: Optional[Any] = None,
        on_iteration: Optional[Callable[[Any], None]] = None,
        verbose: bool = False,
        model: str = "gpt-4o-mini",
    ):
        self.agent = agent
        self.criteria = criteria
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.mode = mode
        self._judge = judge
        self.on_iteration = on_iteration
        self.verbose = verbose
        self.model = model
        
        if mode not in ("optimize", "review"):
            raise ValueError(f"mode must be 'optimize' or 'review', got '{mode}'")
    
    @property
    def judge(self):
        """Lazy-load Judge to avoid import-time overhead."""
        if self._judge is None:
            from .judge import Judge
            self._judge = Judge(
                criteria=self.criteria,
                model=self.model,
            )
        return self._judge
    
    def _get_agent_output(self, prompt: str, iteration: int, feedback: str = "") -> str:
        """Get output from agent, optionally including feedback from previous iteration."""
        if iteration == 1 or not feedback:
            return str(self.agent.chat(prompt))
        
        improved_prompt = f"{prompt}\n\nPrevious feedback to address:\n{feedback}"
        return str(self.agent.chat(improved_prompt))
    
    async def _get_agent_output_async(self, prompt: str, iteration: int, feedback: str = "") -> str:
        """Async version of _get_agent_output."""
        if iteration == 1 or not feedback:
            if hasattr(self.agent, 'chat_async'):
                return str(await self.agent.chat_async(prompt))
            return str(self.agent.chat(prompt))
        
        improved_prompt = f"{prompt}\n\nPrevious feedback to address:\n{feedback}"
        if hasattr(self.agent, 'chat_async'):
            return str(await self.agent.chat_async(improved_prompt))
        return str(self.agent.chat(improved_prompt))
    
    def run(self, prompt: str) -> "EvaluationLoopResult":
        """
        Run the evaluation loop synchronously.
        
        Args:
            prompt: The prompt to send to the agent
            
        Returns:
            EvaluationLoopResult with iteration results
        """
        from .results import IterationResult, EvaluationLoopResult
        
        start_time = time.time()
        iterations: List[IterationResult] = []
        feedback = ""
        
        for i in range(1, self.max_iterations + 1):
            if self.verbose:
                logger.info(f"EvaluationLoop iteration {i}/{self.max_iterations}")
            
            output = self._get_agent_output(prompt, i, feedback)
            
            judge_result = self.judge.run(
                output=output,
                criteria=self.criteria,
            )
            
            findings = getattr(judge_result, 'suggestions', []) or []
            
            iteration_result = IterationResult(
                iteration=i,
                output=output,
                score=judge_result.score,
                reasoning=judge_result.reasoning,
                findings=findings,
            )
            iterations.append(iteration_result)
            
            if self.on_iteration:
                try:
                    self.on_iteration(iteration_result)
                except Exception as e:
                    logger.warning(f"on_iteration callback error: {e}")
            
            if self.mode == "optimize" and judge_result.score >= self.threshold:
                if self.verbose:
                    logger.info(f"Threshold met at iteration {i}: {judge_result.score} >= {self.threshold}")
                break
            
            feedback = judge_result.reasoning
            if findings:
                feedback += "\nSuggestions:\n" + "\n".join(f"- {s}" for s in findings)
        
        total_duration = time.time() - start_time
        success = iterations[-1].score >= self.threshold if iterations else False
        
        result = EvaluationLoopResult(
            iterations=iterations,
            success=success,
            total_duration_seconds=total_duration,
            threshold=self.threshold,
            mode=self.mode,
        )
        
        if self.verbose:
            result.print_summary()
        
        return result
    
    async def run_async(self, prompt: str) -> "EvaluationLoopResult":
        """
        Run the evaluation loop asynchronously.
        
        Args:
            prompt: The prompt to send to the agent
            
        Returns:
            EvaluationLoopResult with iteration results
        """
        from .results import IterationResult, EvaluationLoopResult
        
        start_time = time.time()
        iterations: List[IterationResult] = []
        feedback = ""
        
        for i in range(1, self.max_iterations + 1):
            if self.verbose:
                logger.info(f"EvaluationLoop iteration {i}/{self.max_iterations}")
            
            output = await self._get_agent_output_async(prompt, i, feedback)
            
            if hasattr(self.judge, 'run_async'):
                judge_result = await self.judge.run_async(
                    output=output,
                    criteria=self.criteria,
                )
            else:
                judge_result = self.judge.run(
                    output=output,
                    criteria=self.criteria,
                )
            
            findings = getattr(judge_result, 'suggestions', []) or []
            
            iteration_result = IterationResult(
                iteration=i,
                output=output,
                score=judge_result.score,
                reasoning=judge_result.reasoning,
                findings=findings,
            )
            iterations.append(iteration_result)
            
            if self.on_iteration:
                try:
                    self.on_iteration(iteration_result)
                except Exception as e:
                    logger.warning(f"on_iteration callback error: {e}")
            
            if self.mode == "optimize" and judge_result.score >= self.threshold:
                if self.verbose:
                    logger.info(f"Threshold met at iteration {i}: {judge_result.score} >= {self.threshold}")
                break
            
            feedback = judge_result.reasoning
            if findings:
                feedback += "\nSuggestions:\n" + "\n".join(f"- {s}" for s in findings)
        
        total_duration = time.time() - start_time
        success = iterations[-1].score >= self.threshold if iterations else False
        
        result = EvaluationLoopResult(
            iterations=iterations,
            success=success,
            total_duration_seconds=total_duration,
            threshold=self.threshold,
            mode=self.mode,
        )
        
        if self.verbose:
            result.print_summary()
        
        return result


__all__ = [
    'EvaluationLoop',
    'EvaluationLoopConfig',
]
