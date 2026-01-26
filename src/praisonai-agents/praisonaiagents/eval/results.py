"""
Result dataclasses for PraisonAI Agents evaluation framework.

This module provides structured result types for different evaluation methods.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
import statistics
import json


@dataclass
class EvaluationScore:
    """Individual evaluation score with reasoning."""
    score: float
    reasoning: str
    input_text: str
    output_text: str
    expected_output: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccuracyResult:
    """Result from accuracy evaluation comparing output to expected output."""
    evaluations: List[EvaluationScore] = field(default_factory=list)
    eval_id: str = ""
    name: str = ""
    
    @property
    def scores(self) -> List[float]:
        """Get list of all scores."""
        return [e.score for e in self.evaluations]
    
    @property
    def avg_score(self) -> float:
        """Calculate average score."""
        if not self.scores:
            return 0.0
        return statistics.mean(self.scores)
    
    @property
    def min_score(self) -> float:
        """Get minimum score."""
        if not self.scores:
            return 0.0
        return min(self.scores)
    
    @property
    def max_score(self) -> float:
        """Get maximum score."""
        if not self.scores:
            return 0.0
        return max(self.scores)
    
    @property
    def std_dev(self) -> float:
        """Calculate standard deviation of scores."""
        if len(self.scores) < 2:
            return 0.0
        return statistics.stdev(self.scores)
    
    @property
    def passed(self) -> bool:
        """Check if evaluation passed (avg score >= 7)."""
        return self.avg_score >= 7.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "eval_id": self.eval_id,
            "name": self.name,
            "evaluations": [asdict(e) for e in self.evaluations],
            "avg_score": self.avg_score,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "std_dev": self.std_dev,
            "passed": self.passed,
            "num_evaluations": len(self.evaluations)
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def print_summary(self) -> None:
        """Print a summary of the evaluation results."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel  # noqa: F401
            
            console = Console()
            
            table = Table(title="Accuracy Evaluation Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Evaluations", str(len(self.evaluations)))
            table.add_row("Average Score", f"{self.avg_score:.2f}")
            table.add_row("Min Score", f"{self.min_score:.2f}")
            table.add_row("Max Score", f"{self.max_score:.2f}")
            table.add_row("Std Dev", f"{self.std_dev:.2f}")
            table.add_row("Status", "✅ PASSED" if self.passed else "❌ FAILED")
            
            console.print(table)
        except ImportError:
            print("Accuracy Evaluation Summary")
            print(f"  Evaluations: {len(self.evaluations)}")
            print(f"  Average Score: {self.avg_score:.2f}")
            print(f"  Min Score: {self.min_score:.2f}")
            print(f"  Max Score: {self.max_score:.2f}")
            print(f"  Std Dev: {self.std_dev:.2f}")
            print(f"  Status: {'PASSED' if self.passed else 'FAILED'}")


@dataclass
class PerformanceMetrics:
    """Individual performance measurement."""
    run_time: float
    memory_usage: float
    iteration: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceResult:
    """Result from performance evaluation measuring runtime and memory."""
    metrics: List[PerformanceMetrics] = field(default_factory=list)
    warmup_runs: int = 0
    eval_id: str = ""
    name: str = ""
    
    @property
    def run_times(self) -> List[float]:
        """Get list of all run times."""
        return [m.run_time for m in self.metrics]
    
    @property
    def memory_usages(self) -> List[float]:
        """Get list of all memory usages."""
        return [m.memory_usage for m in self.metrics]
    
    @property
    def avg_run_time(self) -> float:
        """Calculate average run time."""
        if not self.run_times:
            return 0.0
        return statistics.mean(self.run_times)
    
    @property
    def min_run_time(self) -> float:
        """Get minimum run time."""
        if not self.run_times:
            return 0.0
        return min(self.run_times)
    
    @property
    def max_run_time(self) -> float:
        """Get maximum run time."""
        if not self.run_times:
            return 0.0
        return max(self.run_times)
    
    @property
    def std_dev_run_time(self) -> float:
        """Calculate standard deviation of run times."""
        if len(self.run_times) < 2:
            return 0.0
        return statistics.stdev(self.run_times)
    
    @property
    def median_run_time(self) -> float:
        """Calculate median run time."""
        if not self.run_times:
            return 0.0
        return statistics.median(self.run_times)
    
    @property
    def p95_run_time(self) -> float:
        """Calculate 95th percentile run time."""
        if not self.run_times:
            return 0.0
        sorted_times = sorted(self.run_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def avg_memory(self) -> float:
        """Calculate average memory usage."""
        if not self.memory_usages:
            return 0.0
        return statistics.mean(self.memory_usages)
    
    @property
    def max_memory(self) -> float:
        """Get maximum memory usage."""
        if not self.memory_usages:
            return 0.0
        return max(self.memory_usages)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "eval_id": self.eval_id,
            "name": self.name,
            "metrics": [asdict(m) for m in self.metrics],
            "warmup_runs": self.warmup_runs,
            "avg_run_time": self.avg_run_time,
            "min_run_time": self.min_run_time,
            "max_run_time": self.max_run_time,
            "std_dev_run_time": self.std_dev_run_time,
            "median_run_time": self.median_run_time,
            "p95_run_time": self.p95_run_time,
            "avg_memory": self.avg_memory,
            "max_memory": self.max_memory,
            "num_iterations": len(self.metrics)
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def print_summary(self) -> None:
        """Print a summary of the performance results."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            table = Table(title="Performance Evaluation Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Iterations", str(len(self.metrics)))
            table.add_row("Warmup Runs", str(self.warmup_runs))
            table.add_row("Avg Run Time", f"{self.avg_run_time:.4f}s")
            table.add_row("Min Run Time", f"{self.min_run_time:.4f}s")
            table.add_row("Max Run Time", f"{self.max_run_time:.4f}s")
            table.add_row("Std Dev", f"{self.std_dev_run_time:.4f}s")
            table.add_row("Median", f"{self.median_run_time:.4f}s")
            table.add_row("P95", f"{self.p95_run_time:.4f}s")
            table.add_row("Avg Memory", f"{self.avg_memory:.2f} MB")
            table.add_row("Max Memory", f"{self.max_memory:.2f} MB")
            
            console.print(table)
        except ImportError:
            print("Performance Evaluation Summary")
            print(f"  Iterations: {len(self.metrics)}")
            print(f"  Warmup Runs: {self.warmup_runs}")
            print(f"  Avg Run Time: {self.avg_run_time:.4f}s")
            print(f"  Min Run Time: {self.min_run_time:.4f}s")
            print(f"  Max Run Time: {self.max_run_time:.4f}s")
            print(f"  Std Dev: {self.std_dev_run_time:.4f}s")
            print(f"  Median: {self.median_run_time:.4f}s")
            print(f"  P95: {self.p95_run_time:.4f}s")
            print(f"  Avg Memory: {self.avg_memory:.2f} MB")
            print(f"  Max Memory: {self.max_memory:.2f} MB")


@dataclass
class ToolCallResult:
    """Result of a single tool call verification."""
    tool_name: str
    expected: bool
    actual: bool
    passed: bool
    arguments: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReliabilityResult:
    """Result from reliability evaluation checking tool calls."""
    tool_results: List[ToolCallResult] = field(default_factory=list)
    eval_id: str = ""
    name: str = ""
    
    @property
    def passed_calls(self) -> List[ToolCallResult]:
        """Get list of passed tool calls."""
        return [t for t in self.tool_results if t.passed]
    
    @property
    def failed_calls(self) -> List[ToolCallResult]:
        """Get list of failed tool calls."""
        return [t for t in self.tool_results if not t.passed]
    
    @property
    def pass_rate(self) -> float:
        """Calculate pass rate."""
        if not self.tool_results:
            return 0.0
        return len(self.passed_calls) / len(self.tool_results)
    
    @property
    def status(self) -> str:
        """Get overall status."""
        return "PASSED" if len(self.failed_calls) == 0 else "FAILED"
    
    @property
    def passed(self) -> bool:
        """Check if all tool calls passed."""
        return len(self.failed_calls) == 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "eval_id": self.eval_id,
            "name": self.name,
            "tool_results": [asdict(t) for t in self.tool_results],
            "passed_count": len(self.passed_calls),
            "failed_count": len(self.failed_calls),
            "pass_rate": self.pass_rate,
            "status": self.status
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def print_summary(self) -> None:
        """Print a summary of the reliability results."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            table = Table(title="Reliability Evaluation Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Total Tool Calls", str(len(self.tool_results)))
            table.add_row("Passed", str(len(self.passed_calls)))
            table.add_row("Failed", str(len(self.failed_calls)))
            table.add_row("Pass Rate", f"{self.pass_rate:.1%}")
            table.add_row("Status", "✅ PASSED" if self.passed else "❌ FAILED")
            
            console.print(table)
            
            if self.failed_calls:
                fail_table = Table(title="Failed Tool Calls")
                fail_table.add_column("Tool", style="red")
                fail_table.add_column("Expected", style="yellow")
                fail_table.add_column("Actual", style="yellow")
                
                for tc in self.failed_calls:
                    fail_table.add_row(tc.tool_name, str(tc.expected), str(tc.actual))
                
                console.print(fail_table)
        except ImportError:
            print("Reliability Evaluation Summary")
            print(f"  Total Tool Calls: {len(self.tool_results)}")
            print(f"  Passed: {len(self.passed_calls)}")
            print(f"  Failed: {len(self.failed_calls)}")
            print(f"  Pass Rate: {self.pass_rate:.1%}")
            print(f"  Status: {self.status}")


@dataclass
class JudgeResult:
    """
    Result from a Judge evaluation.
    
    This is the unified result type for all LLM-as-judge evaluations.
    
    Attributes:
        score: Quality score (1-10)
        passed: Whether the evaluation passed (score >= threshold)
        reasoning: Explanation for the score
        output: The output that was judged
        expected: Optional expected output
        criteria: Optional criteria used for evaluation
        suggestions: List of improvement suggestions
        timestamp: When judging occurred
        metadata: Additional metadata
    """
    score: float
    passed: bool
    reasoning: str
    output: str = ""
    expected: Optional[str] = None
    criteria: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "score": self.score,
            "passed": self.passed,
            "reasoning": self.reasoning,
            "output": self.output,
            "expected": self.expected,
            "criteria": self.criteria,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JudgeResult":
        """Create from dictionary."""
        return cls(
            score=data.get("score", 5.0),
            passed=data.get("passed", False),
            reasoning=data.get("reasoning", ""),
            output=data.get("output", ""),
            expected=data.get("expected"),
            criteria=data.get("criteria"),
            suggestions=data.get("suggestions", []),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            metadata=data.get("metadata", {}),
        )
    
    def print_summary(self) -> None:
        """Print a summary of the judge result."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            table = Table(title="Judge Result")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green" if self.passed else "red")
            
            table.add_row("Score", f"{self.score:.1f}/10")
            table.add_row("Status", "✅ PASSED" if self.passed else "❌ FAILED")
            table.add_row("Reasoning", self.reasoning[:80] + "..." if len(self.reasoning) > 80 else self.reasoning)
            
            if self.criteria:
                table.add_row("Criteria", self.criteria[:50] + "..." if len(self.criteria) > 50 else self.criteria)
            
            console.print(table)
        except ImportError:
            print(f"Judge Result: Score={self.score:.1f}/10, {'PASSED' if self.passed else 'FAILED'}")
            print(f"  Reasoning: {self.reasoning}")


@dataclass
class CriteriaScore:
    """Individual criteria evaluation score."""
    score: float
    passed: bool
    reasoning: str
    output_text: str
    criteria: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CriteriaResult:
    """Result from criteria-based evaluation (agent-as-judge)."""
    evaluations: List[CriteriaScore] = field(default_factory=list)
    criteria: str = ""
    scoring_type: str = "numeric"  # "numeric" or "binary"
    threshold: float = 7.0
    eval_id: str = ""
    name: str = ""
    
    @property
    def scores(self) -> List[float]:
        """Get list of all scores."""
        return [e.score for e in self.evaluations]
    
    @property
    def avg_score(self) -> float:
        """Calculate average score."""
        if not self.scores:
            return 0.0
        return statistics.mean(self.scores)
    
    @property
    def pass_rate(self) -> float:
        """Calculate pass rate."""
        if not self.evaluations:
            return 0.0
        passed = sum(1 for e in self.evaluations if e.passed)
        return passed / len(self.evaluations)
    
    @property
    def passed(self) -> bool:
        """Check if evaluation passed overall."""
        if self.scoring_type == "binary":
            return self.pass_rate >= 0.5
        return self.avg_score >= self.threshold
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "eval_id": self.eval_id,
            "name": self.name,
            "criteria": self.criteria,
            "scoring_type": self.scoring_type,
            "threshold": self.threshold,
            "evaluations": [asdict(e) for e in self.evaluations],
            "avg_score": self.avg_score,
            "pass_rate": self.pass_rate,
            "passed": self.passed,
            "num_evaluations": len(self.evaluations)
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def print_summary(self) -> None:
        """Print a summary of the criteria evaluation results."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            table = Table(title="Criteria Evaluation Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Criteria", self.criteria[:50] + "..." if len(self.criteria) > 50 else self.criteria)
            table.add_row("Scoring Type", self.scoring_type)
            table.add_row("Threshold", str(self.threshold))
            table.add_row("Evaluations", str(len(self.evaluations)))
            table.add_row("Average Score", f"{self.avg_score:.2f}")
            table.add_row("Pass Rate", f"{self.pass_rate:.1%}")
            table.add_row("Status", "✅ PASSED" if self.passed else "❌ FAILED")
            
            console.print(table)
        except ImportError:
            print("Criteria Evaluation Summary")
            print(f"  Criteria: {self.criteria[:50]}...")
            print(f"  Scoring Type: {self.scoring_type}")
            print(f"  Threshold: {self.threshold}")
            print(f"  Evaluations: {len(self.evaluations)}")
            print(f"  Average Score: {self.avg_score:.2f}")
            print(f"  Pass Rate: {self.pass_rate:.1%}")
            print(f"  Status: {'PASSED' if self.passed else 'FAILED'}")
