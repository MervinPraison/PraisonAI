"""
EvalSuite - Orchestrator for running multiple evaluations and aggregating results.

This module provides the EvalSuite class for coordinating multiple evaluations
and providing comprehensive evaluation reports.

Example:
    from praisonaiagents import Agent
    from praisonaiagents.eval import EvalSuite, AccuracyEval, PerformanceEval
    
    agent = Agent(name="test", instructions="Be helpful")
    
    suite = EvalSuite(
        evaluators=[
            AccuracyEval(agent=agent, input_text="Hello", expected_output="Hi there!"),
            PerformanceEval(agent=agent)
        ]
    )
    
    results = suite.run()
    print(f"Overall score: {results.overall_score}/10")
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass, field
from praisonaiagents._logging import get_logger

if TYPE_CHECKING:
    from .base import BaseEvaluator

logger = get_logger(__name__)

@dataclass
class EvalSuiteResult:
    """Result container for EvalSuite runs."""
    
    suite_name: str
    start_time: float
    end_time: float
    evaluator_results: Dict[str, Any] = field(default_factory=dict)
    overall_score: float = 0.0
    success: bool = False
    errors: List[str] = field(default_factory=list)
    
    @property
    def duration(self) -> float:
        """Total execution time in seconds."""
        return self.end_time - self.start_time
    
    @property
    def summary(self) -> Dict[str, Any]:
        """Summary of all evaluation results."""
        return {
            "suite_name": self.suite_name,
            "duration": self.duration,
            "overall_score": self.overall_score,
            "success": self.success,
            "num_evaluators": len(self.evaluator_results),
            "errors": len(self.errors)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "suite_name": self.suite_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "evaluator_results": self.evaluator_results,
            "overall_score": self.overall_score,
            "success": self.success,
            "errors": self.errors,
            "summary": self.summary
        }

class EvalSuite:
    """
    Orchestrator for running multiple evaluations and aggregating results.
    
    EvalSuite coordinates the execution of multiple evaluators and provides
    comprehensive reporting across all evaluation types.
    """
    
    def __init__(
        self,
        evaluators: List["BaseEvaluator"],
        name: Optional[str] = None,
        parallel: bool = False,
        fail_fast: bool = False,
        score_weights: Optional[Dict[str, float]] = None,
        save_results_path: Optional[str] = None
    ):
        """
        Initialize the evaluation suite.
        
        Args:
            evaluators: List of evaluator instances to run
            name: Optional name for this evaluation suite
            parallel: Whether to run evaluators in parallel (default: False)
            fail_fast: Stop on first evaluator failure (default: False)
            score_weights: Optional weights for scoring each evaluator type
            save_results_path: Optional path to save aggregated results
        """
        self.evaluators = evaluators
        self.name = name or f"eval_suite_{int(time.time())}"
        self.parallel = parallel
        self.fail_fast = fail_fast
        self.score_weights = score_weights or {}
        self.save_results_path = save_results_path
        
        # Validate evaluators
        if not evaluators:
            raise ValueError("At least one evaluator must be provided")
    
    def run(self, print_summary: bool = True) -> EvalSuiteResult:
        """
        Run all evaluators and aggregate results.
        
        Args:
            print_summary: Print summary after completion
            
        Returns:
            EvalSuiteResult with aggregated results
        """
        logger.info(f"Starting EvalSuite '{self.name}' with {len(self.evaluators)} evaluators")
        start_time = time.time()
        
        result = EvalSuiteResult(
            suite_name=self.name,
            start_time=start_time,
            end_time=0.0  # Will be set at completion
        )
        
        try:
            if self.parallel:
                self._run_parallel(result)
            else:
                self._run_sequential(result)
            
            # Calculate overall score
            result.overall_score = self._calculate_overall_score(result)
            result.success = len(result.errors) == 0
            
        except Exception as e:
            logger.error(f"EvalSuite '{self.name}' failed: {e}")
            result.errors.append(str(e))
            result.success = False
        
        result.end_time = time.time()
        
        if print_summary:
            self._print_summary(result)
        
        if self.save_results_path:
            self._save_results(result)
        
        return result
    
    def _run_sequential(self, result: EvalSuiteResult) -> None:
        """Run evaluators sequentially."""
        for i, evaluator in enumerate(self.evaluators):
            evaluator_name = f"{evaluator.__class__.__name__}_{i}"
            logger.info(f"Running evaluator: {evaluator_name}")
            
            try:
                eval_result = evaluator.run(print_summary=False)
                result.evaluator_results[evaluator_name] = eval_result
                
            except Exception as e:
                error_msg = f"{evaluator_name} failed: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                
                if self.fail_fast:
                    raise RuntimeError(f"EvalSuite stopped due to fail_fast: {error_msg}")
    
    def _run_parallel(self, result: EvalSuiteResult) -> None:
        """Run evaluators in parallel."""
        # For now, implement as sequential since we need to be careful with LLM rate limits
        # In the future, this could use asyncio for true parallelism
        logger.warning("Parallel execution not yet implemented, falling back to sequential")
        self._run_sequential(result)
    
    def _calculate_overall_score(self, result: EvalSuiteResult) -> float:
        """Calculate weighted overall score across all evaluators."""
        if not result.evaluator_results:
            return 0.0
        
        total_score = 0.0
        total_weight = 0.0
        
        for evaluator_name, eval_result in result.evaluator_results.items():
            # Extract score from different result types
            score = self._extract_score(eval_result)
            if score is not None:
                weight = self.score_weights.get(evaluator_name, 1.0)
                total_score += score * weight
                total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def _extract_score(self, eval_result: Any) -> Optional[float]:
        """Extract numeric score from evaluation result."""
        if hasattr(eval_result, 'score'):
            score = eval_result.score
            if hasattr(score, 'value'):
                return float(score.value)
            return float(score)
        
        if hasattr(eval_result, 'overall_score'):
            return float(eval_result.overall_score)
        
        # Try to extract from result dictionary
        if isinstance(eval_result, dict):
            for key in ['score', 'overall_score', 'final_score']:
                if key in eval_result:
                    return float(eval_result[key])
        
        logger.warning(f"Could not extract score from result: {type(eval_result)}")
        return None
    
    def _print_summary(self, result: EvalSuiteResult) -> None:
        """Print evaluation suite summary."""
        print(f"\n{'='*60}")
        print(f"EvalSuite Results: {result.suite_name}")
        print(f"{'='*60}")
        print(f"Duration: {result.duration:.2f}s")
        print(f"Success: {result.success}")
        print(f"Overall Score: {result.overall_score:.1f}/10")
        print(f"Evaluators Run: {len(result.evaluator_results)}")
        
        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for error in result.errors:
                print(f"  ❌ {error}")
        
        print(f"\nEvaluator Results:")
        for name, eval_result in result.evaluator_results.items():
            score = self._extract_score(eval_result)
            score_str = f"{score:.1f}" if score is not None else "N/A"
            print(f"  📊 {name}: {score_str}/10")
        
        print(f"{'='*60}\n")
    
    def _save_results(self, result: EvalSuiteResult) -> None:
        """Save results to file."""
        try:
            import json
            from pathlib import Path
            
            # Format path with result data
            formatted_path = self.save_results_path.format(
                name=result.suite_name,
                timestamp=int(result.start_time)
            )
            
            Path(formatted_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(formatted_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
            
            logger.info(f"EvalSuite results saved to: {formatted_path}")
            
        except Exception as e:
            logger.error(f"Failed to save EvalSuite results: {e}")