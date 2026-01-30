"""
Accuracy evaluator for PraisonAI Agents.

Evaluates agent output accuracy by comparing against expected output using LLM-as-judge.
"""

import os
import logging
from typing import Callable, Optional, Union, TYPE_CHECKING

from .base import BaseEvaluator
from .results import AccuracyResult, EvaluationScore
from .grader import parse_score_reasoning

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..agents.agents import AgentManager

logger = logging.getLogger(__name__)


class AccuracyEvaluator(BaseEvaluator):
    """
    Evaluates the accuracy of agent outputs against expected outputs.
    
    Uses an LLM as a judge to score outputs on a scale of 1-10.
    """
    
    def __init__(
        self,
        agent: Optional[Union["Agent", "Agents"]] = None,
        func: Optional[Callable[..., str]] = None,
        input_text: str = "",
        expected_output: str = "",
        num_iterations: int = 1,
        model: Optional[str] = None,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the accuracy evaluator.
        
        Args:
            agent: Agent or Agents instance to evaluate
            func: Alternative callable that returns output string
            input_text: Input to provide to the agent/function
            expected_output: Expected output to compare against
            num_iterations: Number of evaluation iterations
            model: LLM model to use for judging (defaults to gpt-4o-mini)
            name: Name for this evaluation
            save_results_path: Path to save results
            verbose: Enable verbose output
        """
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        
        self.agent = agent
        self.func = func
        self.input_text = input_text
        self.expected_output = expected_output
        self.num_iterations = num_iterations
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        
        if agent is None and func is None:
            raise ValueError("Either 'agent' or 'func' must be provided")
    
    def _get_output(self) -> str:
        """Get output from agent or function."""
        if self.func:
            return str(self.func(self.input_text))
        
        if hasattr(self.agent, 'chat'):
            return str(self.agent.chat(self.input_text))
        elif hasattr(self.agent, 'start'):
            result = self.agent.start(self.input_text)
            if hasattr(result, 'raw'):
                return str(result.raw)
            return str(result)
        else:
            raise ValueError("Agent must have 'chat' or 'start' method")
    
    def _judge_output(self, output: str) -> EvaluationScore:
        """
        Use LLM to judge the output against expected output.
        
        Args:
            output: The actual output to evaluate
            
        Returns:
            EvaluationScore with score and reasoning
        """
        try:
            import litellm
        except ImportError:
            raise ImportError("litellm package required for accuracy evaluation. Install with: pip install litellm")
        
        prompt = f"""You are an expert evaluator. Compare the actual output against the expected output and provide a score from 1-10.

Input: {self.input_text}

Expected Output: {self.expected_output}

Actual Output: {output}

Scoring Guidelines:
- 10: Perfect match in meaning and completeness
- 8-9: Very close, minor differences that don't affect correctness
- 6-7: Mostly correct but missing some details or has minor errors
- 4-5: Partially correct but significant issues
- 2-3: Mostly incorrect but shows some understanding
- 1: Completely wrong or irrelevant

Respond in this exact format:
SCORE: [number 1-10]
REASONING: [brief explanation]"""

        # Use litellm for unified multi-provider support
        response = litellm.completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        response_text = response.choices[0].message.content or ""
        
        # DRY: Use common parsing function from grader module
        score, reasoning = parse_score_reasoning(response_text)
        
        return EvaluationScore(
            score=score,
            reasoning=reasoning,
            input_text=self.input_text,
            output_text=output,
            expected_output=self.expected_output
        )
    
    def run(self, print_summary: bool = False) -> AccuracyResult:
        """
        Execute the accuracy evaluation.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            AccuracyResult with all evaluation scores
        """
        self.before_run()
        
        result = AccuracyResult(
            eval_id=self.eval_id,
            name=self.name
        )
        
        for i in range(self.num_iterations):
            if self.verbose:
                logger.info(f"Running iteration {i + 1}/{self.num_iterations}")
            
            try:
                output = self._get_output()
                score = self._judge_output(output)
                result.evaluations.append(score)
                
                if self.verbose:
                    logger.info(f"  Score: {score.score}/10 - {score.reasoning}")
            except Exception as e:
                logger.error(f"Error in iteration {i + 1}: {e}")
                result.evaluations.append(EvaluationScore(
                    score=0.0,
                    reasoning=f"Error: {str(e)}",
                    input_text=self.input_text,
                    output_text="",
                    expected_output=self.expected_output
                ))
        
        self.after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
    
    async def run_async(self, print_summary: bool = False) -> AccuracyResult:
        """
        Execute the accuracy evaluation asynchronously.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            AccuracyResult with all evaluation scores
        """
        await self.async_before_run()
        result = self.run(print_summary=False)
        await self.async_after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
    
    def evaluate_output(self, output: str, print_summary: bool = False) -> AccuracyResult:
        """
        Evaluate a pre-generated output without running the agent.
        
        Args:
            output: The output to evaluate
            print_summary: Whether to print summary after evaluation
            
        Returns:
            AccuracyResult with evaluation score
        """
        self.before_run()
        
        result = AccuracyResult(
            eval_id=self.eval_id,
            name=self.name
        )
        
        score = self._judge_output(output)
        result.evaluations.append(score)
        
        self.after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
