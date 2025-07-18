"""
Performance evaluation for PraisonAI agents.
"""

import time
import psutil
import os
import json
import logging
from typing import List, Dict, Any, Optional, Union
from ..agent.agent import Agent
from ..main import TaskOutput
from .eval_result import PerformanceResult, PerformanceBatchResult

logger = logging.getLogger(__name__)

class PerformanceEval:
    """Evaluate agent performance metrics like runtime, memory, and token usage."""
    
    def __init__(
        self,
        agent: Agent,
        benchmark_queries: Optional[List[str]] = None,
        metrics: Optional[Dict[str, bool]] = None,
        iterations: int = 1,
        warmup: int = 0
    ):
        """
        Initialize performance evaluation.
        
        Args:
            agent: Agent to evaluate
            benchmark_queries: List of queries to benchmark
            metrics: Dict of metrics to track (runtime, memory, tokens, ttft)
            iterations: Number of iterations to run
            warmup: Number of warmup iterations (not counted in results)
        """
        self.agent = agent
        self.benchmark_queries = benchmark_queries or ["Hello, how are you?"]
        self.metrics = metrics or {
            'runtime': True,
            'memory': True,
            'tokens': True,
            'ttft': True
        }
        self.iterations = iterations
        self.warmup = warmup
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except Exception:
            return None
    
    def _extract_token_count(self, task_output: TaskOutput) -> Optional[int]:
        """Extract token count from task output."""
        try:
            # Check if task_output has usage information
            if hasattr(task_output, 'usage') and task_output.usage:
                usage = task_output.usage
                if hasattr(usage, 'total_tokens'):
                    return usage.total_tokens
                elif isinstance(usage, dict) and 'total_tokens' in usage:
                    return usage['total_tokens']
            
            # Check details for token information
            if hasattr(task_output, 'details') and isinstance(task_output.details, dict):
                tokens = task_output.details.get('tokens', task_output.details.get('token_count'))
                if tokens is not None:
                    return int(tokens)
            
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting token count: {e}")
            return None
    
    def _run_single_benchmark(self, query: str) -> PerformanceResult:
        """
        Run a single performance benchmark.
        
        Args:
            query: Query to benchmark
            
        Returns:
            PerformanceResult with metrics
        """
        # Initialize metrics
        start_time = time.time()
        start_memory = self._get_memory_usage() if self.metrics.get('memory') else None
        ttft = None
        tokens = None
        
        try:
            # Execute the task
            task_result = self.agent.execute(query)
            
            # Calculate runtime
            end_time = time.time()
            runtime = end_time - start_time
            
            # Calculate memory usage
            end_memory = self._get_memory_usage() if self.metrics.get('memory') else None
            memory_mb = None
            if start_memory is not None and end_memory is not None:
                memory_mb = end_memory - start_memory
            
            # Extract token count
            if self.metrics.get('tokens'):
                if isinstance(task_result, TaskOutput):
                    tokens = self._extract_token_count(task_result)
            
            # TODO: Implement TTFT (Time to First Token) measurement
            # This would require streaming support and measuring time to first token
            if self.metrics.get('ttft'):
                ttft = None  # Placeholder for future implementation
            
            return PerformanceResult(
                runtime=runtime,
                memory_mb=memory_mb,
                tokens=tokens,
                ttft=ttft,
                details={
                    'query': query,
                    'output_length': len(str(task_result)) if task_result else 0
                },
                success=True
            )
            
        except Exception as e:
            logger.error(f"Error running benchmark: {e}")
            return PerformanceResult(
                runtime=time.time() - start_time,
                success=False,
                error=str(e),
                details={'query': query}
            )
    
    def run(self, verbose: bool = False) -> Union[PerformanceResult, PerformanceBatchResult]:
        """
        Run the performance evaluation.
        
        Args:
            verbose: Whether to print detailed output
            
        Returns:
            PerformanceResult for single iteration, PerformanceBatchResult for multiple
        """
        try:
            # Run warmup iterations
            if self.warmup > 0 and verbose:
                print(f"Running {self.warmup} warmup iterations...")
            
            for i in range(self.warmup):
                for query in self.benchmark_queries:
                    self._run_single_benchmark(query)
                    if verbose:
                        print(f"  Warmup {i+1}/{self.warmup} completed")
            
            # Run actual benchmark iterations
            all_results = []
            
            for iteration in range(self.iterations):
                if verbose and self.iterations > 1:
                    print(f"Running iteration {iteration + 1}/{self.iterations}")
                
                iteration_results = []
                for query_idx, query in enumerate(self.benchmark_queries):
                    if verbose:
                        print(f"  Benchmarking query {query_idx + 1}: {query[:50]}...")
                    
                    result = self._run_single_benchmark(query)
                    iteration_results.append(result)
                    
                    if verbose:
                        print(f"    Runtime: {result.runtime:.3f}s")
                        if result.memory_mb is not None:
                            print(f"    Memory: {result.memory_mb:.2f}MB")
                        if result.tokens is not None:
                            print(f"    Tokens: {result.tokens}")
                
                all_results.extend(iteration_results)
            
            # Return appropriate result type
            if len(all_results) == 1:
                return all_results[0]
            else:
                return self._create_batch_result(all_results)
                
        except Exception as e:
            logger.error(f"Error running performance evaluation: {e}")
            if self.iterations == 1 and len(self.benchmark_queries) == 1:
                return PerformanceResult(runtime=0.0, success=False, error=str(e))
            else:
                return PerformanceBatchResult(runtimes=[], success=False, error=str(e))
    
    def _create_batch_result(self, results: List[PerformanceResult]) -> PerformanceBatchResult:
        """Create a batch result from individual results."""
        runtimes = [r.runtime for r in results if r.success]
        memory_mbs = [r.memory_mb for r in results if r.success and r.memory_mb is not None]
        tokens = [r.tokens for r in results if r.success and r.tokens is not None]
        ttfts = [r.ttft for r in results if r.success and r.ttft is not None]
        details = [r.details for r in results if r.success]
        
        return PerformanceBatchResult(
            runtimes=runtimes,
            memory_mbs=memory_mbs,
            tokens=tokens,
            ttfts=ttfts,
            details=details,
            success=len(runtimes) > 0
        )
    
    @staticmethod
    def compare(
        agents: List[Agent],
        benchmark_suite: str = "standard",
        export_format: str = "json"
    ) -> Dict[str, Any]:
        """
        Compare multiple agents on the same benchmark suite.
        
        Args:
            agents: List of agents to compare
            benchmark_suite: Type of benchmark suite ("standard", "complex", etc.)
            export_format: Export format ("json", "html", "csv")
            
        Returns:
            Comparison results
        """
        # Define benchmark suites
        benchmark_suites = {
            "standard": [
                "What is 2+2?",
                "Explain quantum computing in simple terms",
                "Write a short poem about AI"
            ],
            "complex": [
                "Analyze the economic impact of artificial intelligence on employment",
                "Design a solution for climate change using technology",
                "Create a business plan for a sustainable energy startup"
            ],
            "simple": [
                "Hello",
                "What is your name?",
                "Tell me a joke"
            ]
        }
        
        queries = benchmark_suites.get(benchmark_suite, benchmark_suites["standard"])
        results = {}
        
        try:
            for i, agent in enumerate(agents):
                agent_name = getattr(agent, 'name', f"Agent_{i+1}")
                print(f"Benchmarking {agent_name}...")
                
                evaluator = PerformanceEval(
                    agent=agent,
                    benchmark_queries=queries,
                    iterations=3
                )
                
                result = evaluator.run(verbose=False)
                results[agent_name] = result.to_dict() if hasattr(result, 'to_dict') else str(result)
            
            # Create comparison summary
            comparison = {
                'benchmark_suite': benchmark_suite,
                'agents_compared': len(agents),
                'queries_used': queries,
                'results': results,
                'timestamp': time.time()
            }
            
            # Export in requested format
            if export_format == "html":
                # TODO: Generate HTML report
                comparison['export_note'] = "HTML export not yet implemented"
            elif export_format == "csv":
                # TODO: Generate CSV report
                comparison['export_note'] = "CSV export not yet implemented"
            
            return comparison
            
        except Exception as e:
            logger.error(f"Error in agent comparison: {e}")
            return {
                'error': str(e),
                'benchmark_suite': benchmark_suite,
                'agents_compared': len(agents)
            }