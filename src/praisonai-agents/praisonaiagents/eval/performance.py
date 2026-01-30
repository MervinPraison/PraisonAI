"""
Performance evaluator for PraisonAI Agents.

Measures runtime and memory usage of agent executions or functions.
"""

import time
import logging
from typing import Callable, Optional, TYPE_CHECKING

from .base import BaseEvaluator
from .results import PerformanceResult, PerformanceMetrics

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..agents.agents import AgentManager

logger = logging.getLogger(__name__)


class PerformanceEvaluator(BaseEvaluator):
    """
    Evaluates the performance of agent executions or functions.
    
    Measures runtime and memory usage across multiple iterations.
    """
    
    def __init__(
        self,
        func: Optional[Callable[[], None]] = None,
        agent: Optional["Agent"] = None,
        input_text: str = "",
        num_iterations: int = 10,
        warmup_runs: int = 2,
        track_memory: bool = True,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the performance evaluator.
        
        Args:
            func: Callable to benchmark (takes no arguments)
            agent: Agent to benchmark (will call chat with input_text)
            input_text: Input text for agent benchmarking
            num_iterations: Number of benchmark iterations
            warmup_runs: Number of warmup runs before measurement
            track_memory: Whether to track memory usage
            name: Name for this evaluation
            save_results_path: Path to save results
            verbose: Enable verbose output
        """
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        
        self.func = func
        self.agent = agent
        self.input_text = input_text
        self.num_iterations = num_iterations
        self.warmup_runs = warmup_runs
        self.track_memory = track_memory
        
        if func is None and agent is None:
            raise ValueError("Either 'func' or 'agent' must be provided")
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        if not self.track_memory:
            return 0.0
        
        try:
            import tracemalloc
            current, _ = tracemalloc.get_traced_memory()
            return current / (1024 * 1024)
        except Exception:
            return 0.0
    
    def _execute(self) -> None:
        """Execute the function or agent."""
        if self.func:
            self.func()
        elif self.agent:
            if hasattr(self.agent, 'chat'):
                self.agent.chat(self.input_text)
            elif hasattr(self.agent, 'start'):
                self.agent.start(self.input_text)
            else:
                raise ValueError("Agent must have 'chat' or 'start' method")
    
    def run(self, print_summary: bool = False) -> PerformanceResult:
        """
        Execute the performance evaluation.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            PerformanceResult with all performance metrics
        """
        self.before_run()
        
        result = PerformanceResult(
            warmup_runs=self.warmup_runs,
            eval_id=self.eval_id,
            name=self.name
        )
        
        if self.track_memory:
            try:
                import tracemalloc
                tracemalloc.start()
            except Exception as e:
                logger.warning(f"Could not start memory tracking: {e}")
                self.track_memory = False
        
        if self.verbose:
            logger.info(f"Running {self.warmup_runs} warmup iterations...")
        
        for i in range(self.warmup_runs):
            try:
                self._execute()
            except Exception as e:
                logger.warning(f"Warmup iteration {i + 1} failed: {e}")
        
        if self.verbose:
            logger.info(f"Running {self.num_iterations} benchmark iterations...")
        
        for i in range(self.num_iterations):
            memory_before = self._get_memory_usage()
            
            start_time = time.perf_counter()
            try:
                self._execute()
                success = True
            except Exception as e:
                logger.error(f"Iteration {i + 1} failed: {e}")
                success = False
            end_time = time.perf_counter()
            
            memory_after = self._get_memory_usage()
            
            if success:
                metrics = PerformanceMetrics(
                    run_time=end_time - start_time,
                    memory_usage=max(0, memory_after - memory_before),
                    iteration=i + 1
                )
                result.metrics.append(metrics)
                
                if self.verbose:
                    logger.info(f"  Iteration {i + 1}: {metrics.run_time:.4f}s, {metrics.memory_usage:.2f}MB")
        
        if self.track_memory:
            try:
                import tracemalloc
                tracemalloc.stop()
            except Exception:
                pass
        
        self.after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
    
    async def run_async(self, print_summary: bool = False) -> PerformanceResult:
        """
        Execute the performance evaluation asynchronously.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            PerformanceResult with all performance metrics
        """
        await self.async_before_run()
        result = self.run(print_summary=False)
        await self.async_after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
