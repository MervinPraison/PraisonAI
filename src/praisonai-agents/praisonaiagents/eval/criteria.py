"""
Criteria evaluator for PraisonAI Agents.

Evaluates agent outputs against custom criteria using LLM-as-judge.
"""

import os
import logging
from typing import Callable, Literal, Optional, Union, TYPE_CHECKING

from .base import BaseEvaluator
from .results import CriteriaResult, CriteriaScore
from .grader import parse_score_reasoning

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..agents.agents import AgentManager

logger = logging.getLogger(__name__)


class CriteriaEvaluator(BaseEvaluator):
    """
    Evaluates agent outputs against custom criteria.
    
    Uses an LLM as a judge to score outputs based on user-defined criteria.
    Supports both numeric (1-10) and binary (pass/fail) scoring.
    """
    
    def __init__(
        self,
        criteria: str,
        agent: Optional[Union["Agent", "Agents"]] = None,
        func: Optional[Callable[..., str]] = None,
        input_text: str = "",
        scoring_type: Literal["numeric", "binary"] = "numeric",
        threshold: float = 7.0,
        num_iterations: int = 1,
        model: Optional[str] = None,
        on_fail: Optional[Callable[[CriteriaScore], None]] = None,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the criteria evaluator.
        
        Args:
            criteria: The criteria to evaluate against (e.g., "Response is helpful and accurate")
            agent: Agent or Agents instance to evaluate
            func: Alternative callable that returns output string
            input_text: Input to provide to the agent/function
            scoring_type: "numeric" (1-10 scale) or "binary" (pass/fail)
            threshold: Score threshold for passing (numeric mode only)
            num_iterations: Number of evaluation iterations
            model: LLM model to use for judging (defaults to gpt-4o-mini)
            on_fail: Callback function called when evaluation fails
            name: Name for this evaluation
            save_results_path: Path to save results
            verbose: Enable verbose output
        """
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        
        self.criteria = criteria
        self.agent = agent
        self.func = func
        self.input_text = input_text
        self.scoring_type = scoring_type
        self.threshold = threshold
        self.num_iterations = num_iterations
        self.model = model or os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.on_fail = on_fail
    
    def _get_output(self) -> str:
        """Get output from agent or function."""
        if self.func:
            return str(self.func(self.input_text))
        
        if self.agent is None:
            raise ValueError("Either 'agent' or 'func' must be provided")
        
        if hasattr(self.agent, 'chat'):
            return str(self.agent.chat(self.input_text))
        elif hasattr(self.agent, 'start'):
            result = self.agent.start(self.input_text)
            if hasattr(result, 'raw'):
                return str(result.raw)
            return str(result)
        else:
            raise ValueError("Agent must have 'chat' or 'start' method")
    
    def _judge_output(self, output: str) -> CriteriaScore:
        """
        Use LLM to judge the output against criteria.
        
        Args:
            output: The output to evaluate
            
        Returns:
            CriteriaScore with score, passed status, and reasoning
        """
        try:
            import litellm
        except ImportError:
            raise ImportError("litellm package required for criteria evaluation. Install with: pip install litellm")
        
        if self.scoring_type == "binary":
            prompt = f"""You are an expert evaluator. Evaluate the following output against the given criteria.

Criteria: {self.criteria}

Output to evaluate:
{output}

Determine if the output PASSES or FAILS the criteria.

Respond in this exact format:
RESULT: [PASS or FAIL]
REASONING: [brief explanation]"""
        else:
            prompt = f"""You are an expert evaluator. Evaluate the following output against the given criteria.

Criteria: {self.criteria}

Output to evaluate:
{output}

Score the output from 1-10 based on how well it meets the criteria.
- 10: Perfectly meets all criteria
- 8-9: Meets criteria very well with minor issues
- 6-7: Meets most criteria but has some gaps
- 4-5: Partially meets criteria
- 2-3: Barely meets criteria
- 1: Does not meet criteria at all

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
        
        # DRY: Use common parsing for numeric mode, custom for binary
        if self.scoring_type == "binary":
            score = 5.0
            passed = False
            reasoning = "Unable to parse response"
            
            lines = response_text.strip().split('\n')
            for line in lines:
                if line.startswith('RESULT:'):
                    result_str = line.replace('RESULT:', '').strip().upper()
                    passed = result_str == 'PASS'
                    score = 10.0 if passed else 0.0
                elif line.startswith('REASONING:'):
                    reasoning = line.replace('REASONING:', '').strip()
        else:
            # DRY: Use common parsing function from grader module
            score, reasoning = parse_score_reasoning(response_text)
            passed = score >= self.threshold
        
        return CriteriaScore(
            score=score,
            passed=passed,
            reasoning=reasoning,
            output_text=output,
            criteria=self.criteria
        )
    
    def run(self, print_summary: bool = False) -> CriteriaResult:
        """
        Execute the criteria evaluation.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            CriteriaResult with all evaluation scores
        """
        self.before_run()
        
        result = CriteriaResult(
            criteria=self.criteria,
            scoring_type=self.scoring_type,
            threshold=self.threshold,
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
                    status = "PASS" if score.passed else "FAIL"
                    logger.info(f"  {status} (Score: {score.score}) - {score.reasoning}")
                
                if not score.passed and self.on_fail:
                    self.on_fail(score)
                    
            except Exception as e:
                logger.error(f"Error in iteration {i + 1}: {e}")
                error_score = CriteriaScore(
                    score=0.0,
                    passed=False,
                    reasoning=f"Error: {str(e)}",
                    output_text="",
                    criteria=self.criteria
                )
                result.evaluations.append(error_score)
                
                if self.on_fail:
                    self.on_fail(error_score)
        
        self.after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
    
    async def run_async(self, print_summary: bool = False) -> CriteriaResult:
        """
        Execute the criteria evaluation asynchronously.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            CriteriaResult with all evaluation scores
        """
        await self.async_before_run()
        result = self.run(print_summary=False)
        await self.async_after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
    
    def evaluate_output(self, output: str, print_summary: bool = False) -> CriteriaResult:
        """
        Evaluate a pre-generated output without running the agent.
        
        Args:
            output: The output to evaluate
            print_summary: Whether to print summary after evaluation
            
        Returns:
            CriteriaResult with evaluation score
        """
        self.before_run()
        
        result = CriteriaResult(
            criteria=self.criteria,
            scoring_type=self.scoring_type,
            threshold=self.threshold,
            eval_id=self.eval_id,
            name=self.name
        )
        
        score = self._judge_output(output)
        result.evaluations.append(score)
        
        if not score.passed and self.on_fail:
            self.on_fail(score)
        
        self.after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
