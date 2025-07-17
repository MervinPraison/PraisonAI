"""
Evaluation result classes for the PraisonAI evaluation framework.
"""

import json
import time
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from statistics import mean, stdev

@dataclass
class EvalResult:
    """Result of an evaluation run."""
    
    score: float
    max_score: float = 10.0
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: Optional[str] = None
    
    @property
    def normalized_score(self) -> float:
        """Get score normalized to 0-1 range."""
        return self.score / self.max_score if self.max_score > 0 else 0.0
    
    @property
    def percentage(self) -> float:
        """Get score as percentage."""
        return self.normalized_score * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'score': self.score,
            'max_score': self.max_score,
            'normalized_score': self.normalized_score,
            'percentage': self.percentage,
            'details': self.details,
            'timestamp': self.timestamp,
            'success': self.success,
            'error': self.error
        }

@dataclass
class BatchEvalResult:
    """Result of a batch evaluation with multiple iterations."""
    
    scores: List[float]
    details: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: Optional[str] = None
    max_score: float = 10.0
    
    @property
    def avg_score(self) -> float:
        """Average score across all runs."""
        return mean(self.scores) if self.scores else 0.0
    
    @property
    def std_dev(self) -> float:
        """Standard deviation of scores."""
        return stdev(self.scores) if len(self.scores) > 1 else 0.0
    
    @property
    def min_score(self) -> float:
        """Minimum score."""
        return min(self.scores) if self.scores else 0.0
    
    @property
    def max_score_value(self) -> float:
        """Maximum score achieved."""
        return max(self.scores) if self.scores else 0.0
    
    @property
    def confidence_interval(self) -> tuple:
        """95% confidence interval for the mean."""
        if len(self.scores) < 2:
            return (self.avg_score, self.avg_score)
        
        import math
        n = len(self.scores)
        mean_score = self.avg_score
        std_err = self.std_dev / math.sqrt(n)
        margin = 1.96 * std_err  # 95% confidence
        return (mean_score - margin, mean_score + margin)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'avg_score': self.avg_score,
            'std_dev': self.std_dev,
            'min_score': self.min_score,
            'max_score': self.max_score_value,
            'confidence_interval': self.confidence_interval,
            'scores': self.scores,
            'details': self.details,
            'timestamp': self.timestamp,
            'success': self.success,
            'error': self.error,
            'total_runs': len(self.scores)
        }

@dataclass
class PerformanceResult:
    """Result of performance evaluation."""
    
    runtime: float
    memory_mb: Optional[float] = None
    tokens: Optional[int] = None
    ttft: Optional[float] = None  # Time to first token
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'runtime': self.runtime,
            'memory_mb': self.memory_mb,
            'tokens': self.tokens,
            'ttft': self.ttft,
            'details': self.details,
            'timestamp': self.timestamp,
            'success': self.success,
            'error': self.error
        }

@dataclass
class PerformanceBatchResult:
    """Result of batch performance evaluation."""
    
    runtimes: List[float]
    memory_mbs: List[Optional[float]] = field(default_factory=list)
    tokens: List[Optional[int]] = field(default_factory=list)
    ttfts: List[Optional[float]] = field(default_factory=list)
    details: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: Optional[str] = None
    
    def get_stats(self, metric_name: str) -> Dict[str, float]:
        """Get statistics for a specific metric."""
        values = getattr(self, metric_name, [])
        if not values:
            return {}
        
        # Filter out None values
        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return {}
        
        return {
            'avg': mean(valid_values),
            'std': stdev(valid_values) if len(valid_values) > 1 else 0.0,
            'min': min(valid_values),
            'max': max(valid_values),
            'p50': sorted(valid_values)[len(valid_values)//2],
            'p95': sorted(valid_values)[int(len(valid_values)*0.95)],
            'p99': sorted(valid_values)[int(len(valid_values)*0.99)]
        }
    
    def print_report(self):
        """Print a formatted performance report."""
        print("\n=== Performance Evaluation Report ===")
        print(f"Total runs: {len(self.runtimes)}")
        
        metrics = [
            ('Runtime (s)', 'runtimes'),
            ('Memory (MB)', 'memory_mbs'),
            ('Tokens', 'tokens'),
            ('TTFT (s)', 'ttfts')
        ]
        
        for metric_label, metric_name in metrics:
            stats = self.get_stats(metric_name)
            if stats:
                print(f"\n{metric_label}:")
                print(f"  Avg: {stats['avg']:.3f}")
                print(f"  Min: {stats['min']:.3f}")
                print(f"  Max: {stats['max']:.3f}")
                print(f"  P50: {stats['p50']:.3f}")
                print(f"  P95: {stats['p95']:.3f}")
                print(f"  P99: {stats['p99']:.3f}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'runtime_stats': self.get_stats('runtimes'),
            'memory_stats': self.get_stats('memory_mbs'),
            'token_stats': self.get_stats('tokens'),
            'ttft_stats': self.get_stats('ttfts'),
            'raw_data': {
                'runtimes': self.runtimes,
                'memory_mbs': self.memory_mbs,
                'tokens': self.tokens,
                'ttfts': self.ttfts
            },
            'details': self.details,
            'timestamp': self.timestamp,
            'success': self.success,
            'error': self.error,
            'total_runs': len(self.runtimes)
        }

@dataclass 
class ReliabilityResult:
    """Result of reliability evaluation."""
    
    expected_tools: List[str]
    actual_tools: List[str]
    passed: bool
    failed_tools: List[str] = field(default_factory=list)
    unexpected_tools: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: Optional[str] = None
    
    @property
    def score(self) -> float:
        """Calculate reliability score based on tool usage."""
        if not self.expected_tools:
            return 10.0  # Perfect score if no tools expected
        
        correct_tools = len(set(self.expected_tools) & set(self.actual_tools))
        return (correct_tools / len(self.expected_tools)) * 10.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'score': self.score,
            'expected_tools': self.expected_tools,
            'actual_tools': self.actual_tools,
            'passed': self.passed,
            'failed_tools': self.failed_tools,
            'unexpected_tools': self.unexpected_tools,
            'details': self.details,
            'timestamp': self.timestamp,
            'success': self.success,
            'error': self.error
        }