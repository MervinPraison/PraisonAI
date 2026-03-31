"""
EvalSuite - Comprehensive evaluation orchestration for PraisonAI Agents.

This module provides the EvalSuite class which orchestrates multi-agent evaluations,
generates comprehensive reports, and provides statistical analysis with confidence intervals.
"""

import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, TYPE_CHECKING
import math

from .package import EvalPackage, EvalCase, EvalReport, EvalResult
from .accuracy import AccuracyEvaluator
from .performance import PerformanceEvaluator
from .reliability import ReliabilityEvaluator
from praisonaiagents._logging import get_logger

if TYPE_CHECKING:
    from ..agent.agent import Agent

logger = get_logger(__name__)


@dataclass
class TestCase:
    """Individual test case configuration for EvalSuite."""
    name: str
    eval_type: str  # "accuracy", "performance", "reliability"
    input_text: str
    expected_output: Optional[str] = None
    expected_tools: Optional[List[str]] = None
    num_iterations: int = 1
    threshold: float = 7.0
    criteria: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "eval_type": self.eval_type,
            "input_text": self.input_text,
            "expected_output": self.expected_output,
            "expected_tools": self.expected_tools,
            "num_iterations": self.num_iterations,
            "threshold": self.threshold,
            "criteria": self.criteria,
            "metadata": self.metadata,
        }


@dataclass
class EvalSuiteResult:
    """Result from running an EvalSuite."""
    name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    success_rate: float
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    @property
    def summary(self) -> str:
        """Get a summary string of the results."""
        return f"{self.passed_tests}/{self.total_tests} tests passed ({self.success_rate:.1f}%)"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "success_rate": self.success_rate,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "details": self.details,
        }


@dataclass
class StatisticalAnalysis:
    """Statistical analysis results with confidence intervals."""
    mean: float
    std_dev: float
    min_value: float
    max_value: float
    median: float
    percentile_95: float
    percentile_99: float
    confidence_interval_95: tuple  # (lower, upper)
    sample_size: int

    @classmethod
    def from_scores(cls, scores: List[float]) -> "StatisticalAnalysis":
        """Calculate statistical analysis from a list of scores."""
        if not scores:
            return cls(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (0.0, 0.0), 0)
        
        mean = statistics.mean(scores)
        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0
        min_value = min(scores)
        max_value = max(scores)
        median = statistics.median(scores)
        
        # Calculate percentiles
        sorted_scores = sorted(scores)
        n = len(sorted_scores)
        percentile_95 = sorted_scores[int(0.95 * n)] if n > 0 else 0.0
        percentile_99 = sorted_scores[int(0.99 * n)] if n > 0 else 0.0
        
        # Calculate 95% confidence interval for the mean
        if len(scores) > 1:
            # Using t-distribution approximation
            margin_error = 1.96 * (std_dev / math.sqrt(len(scores)))
            ci_95 = (mean - margin_error, mean + margin_error)
        else:
            ci_95 = (mean, mean)
        
        return cls(
            mean=mean,
            std_dev=std_dev,
            min_value=min_value,
            max_value=max_value,
            median=median,
            percentile_95=percentile_95,
            percentile_99=percentile_99,
            confidence_interval_95=ci_95,
            sample_size=len(scores)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mean": self.mean,
            "std_dev": self.std_dev,
            "min": self.min_value,
            "max": self.max_value,
            "median": self.median,
            "percentile_95": self.percentile_95,
            "percentile_99": self.percentile_99,
            "confidence_interval_95": self.confidence_interval_95,
            "sample_size": self.sample_size,
        }


class EvalSuite:
    """
    Comprehensive evaluation suite for orchestrating multi-agent evaluations.
    
    Features:
    - Multi-agent test execution
    - Statistical analysis with confidence intervals
    - Export to multiple formats (JSON, HTML, Markdown)
    - Alert system for test failures
    - Automated CI/CD integration support
    """

    def __init__(
        self,
        name: str,
        agents: List["Agent"],
        test_cases: List[TestCase],
        export_results: Optional[str] = None,
        alert_webhook: Optional[str] = None,
        alert_threshold: float = 80.0,
        verbose: bool = False,
    ):
        """
        Initialize the EvalSuite.
        
        Args:
            name: Name for this evaluation suite
            agents: List of agents to evaluate
            test_cases: List of test cases to run
            export_results: Export format ("json", "html", "markdown") and path
            alert_webhook: Webhook URL for alerts on test failures
            alert_threshold: Success rate threshold for triggering alerts (%)
            verbose: Enable verbose output
        """
        self.name = name
        self.agents = agents
        self.test_cases = test_cases
        self.export_results = export_results
        self.alert_webhook = alert_webhook
        self.alert_threshold = alert_threshold
        self.verbose = verbose

    def _run_accuracy_test(self, agent: "Agent", test_case: TestCase) -> Dict[str, Any]:
        """Run accuracy evaluation for a test case."""
        try:
            evaluator = AccuracyEvaluator(
                agent=agent,
                input_text=test_case.input_text,
                expected_output=test_case.expected_output or "",
                num_iterations=test_case.num_iterations,
                verbose=self.verbose,
            )
            result = evaluator.run()
            
            return {
                'type': 'accuracy',
                'passed': result.passed and result.avg_score >= test_case.threshold,
                'score': result.avg_score,
                'details': {
                    'avg_score': result.avg_score,
                    'min_score': result.min_score,
                    'max_score': result.max_score,
                    'std_dev': result.std_dev,
                    'evaluations': len(result.evaluations),
                }
            }
        except Exception as e:
            logger.error(f"Accuracy test failed: {e}")
            return {
                'type': 'accuracy',
                'passed': False,
                'score': 0.0,
                'error': str(e)
            }

    def _run_reliability_test(self, agent: "Agent", test_case: TestCase) -> Dict[str, Any]:
        """Run reliability evaluation for a test case."""
        try:
            evaluator = ReliabilityEvaluator(
                agent=agent,
                input_text=test_case.input_text,
                expected_tools=test_case.expected_tools or [],
                verbose=self.verbose,
            )
            result = evaluator.run()
            
            pass_rate = result.pass_rate
            passed = pass_rate >= (test_case.threshold / 10.0)
            
            return {
                'type': 'reliability',
                'passed': passed,
                'score': pass_rate * 10,  # Convert to 0-10 scale
                'details': {
                    'pass_rate': pass_rate,
                    'passed_calls': len(result.passed_calls),
                    'failed_calls': len(result.failed_calls), 
                    'total_calls': len(result.tool_results),
                    'tool_results': [
                        {
                            'tool_name': tr.tool_name,
                            'expected': tr.expected,
                            'actual': tr.actual,
                            'passed': tr.passed
                        }
                        for tr in result.tool_results
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Reliability test failed: {e}")
            return {
                'type': 'reliability',
                'passed': False,
                'score': 0.0,
                'error': str(e)
            }

    def _run_performance_test(self, agent: "Agent", test_case: TestCase) -> Dict[str, Any]:
        """Run performance evaluation for a test case."""
        try:
            evaluator = PerformanceEvaluator(
                agent=agent,
                input_text=test_case.input_text,
                num_iterations=test_case.num_iterations,
                verbose=self.verbose,
            )
            result = evaluator.run()
            
            # Performance passes if runtime is reasonable (under threshold seconds)
            runtime_threshold = test_case.metadata.get('runtime_threshold_ms', 5000)
            avg_runtime_ms = result.avg_run_time * 1000  # Convert to ms
            passed = avg_runtime_ms <= runtime_threshold
            
            return {
                'type': 'performance',
                'passed': passed,
                'score': max(0, 10 - (avg_runtime_ms / 1000)),  # Score based on runtime
                'details': {
                    'avg_runtime_ms': avg_runtime_ms,
                    'min_runtime_ms': result.min_run_time * 1000,
                    'max_runtime_ms': result.max_run_time * 1000,
                    'avg_memory_mb': result.avg_memory,
                    'iterations': len(result.metrics),
                    'runtime_threshold_ms': runtime_threshold,
                }
            }
        except Exception as e:
            logger.error(f"Performance test failed: {e}")
            return {
                'type': 'performance',
                'passed': False,
                'score': 0.0,
                'error': str(e)
            }

    def run(self, verbose: bool = False) -> EvalSuiteResult:
        """
        Run the complete evaluation suite.
        
        Args:
            verbose: Whether to print detailed output
            
        Returns:
            EvalSuiteResult with comprehensive results
        """
        if verbose:
            print(f"Running evaluation suite: {self.name}")
            print(f"Agents: {len(self.agents)}, Test cases: {len(self.test_cases)}")
        
        total_tests = 0
        passed_tests = 0
        agent_results = {}
        all_scores = []
        
        try:
            for agent in self.agents:
                agent_name = getattr(agent, 'name', f"Agent_{id(agent)}")
                if verbose:
                    print(f"\nEvaluating agent: {agent_name}")
                
                agent_test_results = []
                
                for test_case in self.test_cases:
                    if verbose:
                        print(f"  Running test: {test_case.name}")
                    
                    total_tests += 1
                    
                    # Run appropriate test type
                    if test_case.eval_type == "accuracy":
                        test_result = self._run_accuracy_test(agent, test_case)
                    elif test_case.eval_type == "reliability":
                        test_result = self._run_reliability_test(agent, test_case)
                    elif test_case.eval_type == "performance":
                        test_result = self._run_performance_test(agent, test_case)
                    else:
                        logger.warning(f"Unknown test type: {test_case.eval_type}")
                        test_result = {
                            'type': test_case.eval_type,
                            'passed': False,
                            'error': f"Unknown test type: {test_case.eval_type}"
                        }
                    
                    test_result['test_case'] = test_case.to_dict()
                    agent_test_results.append(test_result)
                    
                    if test_result['passed']:
                        passed_tests += 1
                    
                    # Collect scores for statistical analysis
                    if 'score' in test_result:
                        all_scores.append(test_result['score'])
                    
                    if verbose:
                        status = "PASS" if test_result['passed'] else "FAIL"
                        score = test_result.get('score', 0)
                        print(f"    {status}: {test_case.name} (score: {score:.1f})")
                
                agent_results[agent_name] = agent_test_results
            
            # Calculate overall results
            failed_tests = total_tests - passed_tests
            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0
            
            # Generate statistical analysis
            stats = StatisticalAnalysis.from_scores(all_scores) if all_scores else None
            
            suite_result = EvalSuiteResult(
                name=self.name,
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                success_rate=success_rate,
                details={
                    'agent_results': agent_results,
                    'test_cases': [tc.to_dict() for tc in self.test_cases],
                    'statistical_analysis': stats.to_dict() if stats else None,
                }
            )
            
            if verbose:
                print(f"\nSuite Results: {suite_result.summary}")
                if stats:
                    print(f"Score Statistics: μ={stats.mean:.1f}, σ={stats.std_dev:.1f}")
                    print(f"95% CI: [{stats.confidence_interval_95[0]:.1f}, {stats.confidence_interval_95[1]:.1f}]")
            
            # Check alerts
            self._check_alerts(suite_result)
            
            # Export results
            if self.export_results:
                self._export_results(suite_result)
            
            return suite_result
            
        except Exception as e:
            logger.error(f"Error running evaluation suite: {e}")
            return EvalSuiteResult(
                name=self.name,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                success_rate=0.0,
                details={'error': str(e)}
            )

    def _check_alerts(self, result: EvalSuiteResult) -> None:
        """Check if alerts should be triggered based on results."""
        if result.success_rate < self.alert_threshold:
            message = f"Evaluation suite '{self.name}' failed: {result.summary}"
            logger.warning(f"Alert triggered: {message}")
            
            if self.alert_webhook:
                try:
                    self._send_webhook_alert(message, result)
                except Exception as e:
                    logger.error(f"Failed to send webhook alert: {e}")

    def _send_webhook_alert(self, message: str, result: EvalSuiteResult) -> None:
        """Send alert to webhook URL."""
        try:
            import requests
            payload = {
                "text": message,
                "suite_name": result.name,
                "success_rate": result.success_rate,
                "details": result.to_dict()
            }
            response = requests.post(self.alert_webhook, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Alert sent to webhook: {self.alert_webhook}")
        except ImportError:
            logger.warning("requests library not available for webhook alerts")
        except Exception as e:
            logger.error(f"Webhook alert failed: {e}")

    def _export_results(self, result: EvalSuiteResult) -> None:
        """Export results to specified format."""
        if not self.export_results:
            return
        
        parts = self.export_results.split(':', 1)
        format_type = parts[0]
        output_path = parts[1] if len(parts) > 1 else f"{self.name}_results"
        
        try:
            if format_type == "json":
                self._export_json(result, output_path)
            elif format_type == "html":
                self._export_html(result, output_path)
            elif format_type == "markdown":
                self._export_markdown(result, output_path)
            else:
                logger.warning(f"Unknown export format: {format_type}")
        except Exception as e:
            logger.error(f"Failed to export results: {e}")

    def _export_json(self, result: EvalSuiteResult, output_path: str) -> None:
        """Export results as JSON."""
        if not output_path.endswith('.json'):
            output_path += '.json'
        
        with open(output_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
        
        logger.info(f"Results exported to {output_path}")

    def _export_html(self, result: EvalSuiteResult, output_path: str) -> None:
        """Export results as HTML report."""
        if not output_path.endswith('.html'):
            output_path += '.html'
        
        html_content = self._generate_html_report(result)
        
        with open(output_path, 'w') as f:
            f.write(html_content)
        
        logger.info(f"HTML report exported to {output_path}")

    def _export_markdown(self, result: EvalSuiteResult, output_path: str) -> None:
        """Export results as Markdown report."""
        if not output_path.endswith('.md'):
            output_path += '.md'
        
        md_content = self._generate_markdown_report(result)
        
        with open(output_path, 'w') as f:
            f.write(md_content)
        
        logger.info(f"Markdown report exported to {output_path}")

    def _generate_html_report(self, result: EvalSuiteResult) -> str:
        """Generate HTML report."""
        stats = result.details.get('statistical_analysis')
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Evaluation Report - {result.name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ color: #333; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .success {{ color: #28a745; }}
        .failure {{ color: #dc3545; }}
        .stats {{ background: #e9ecef; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Evaluation Report: {result.name}</h1>
        <p>Generated: {result.timestamp}</p>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Success Rate:</strong> 
            <span class="{'success' if result.success_rate >= 80 else 'failure'}">
                {result.success_rate:.1f}%
            </span>
        </p>
        <p><strong>Tests:</strong> {result.passed_tests}/{result.total_tests} passed</p>
    </div>
"""
        
        if stats:
            html += f"""
    <div class="stats">
        <h3>Statistical Analysis</h3>
        <p><strong>Mean Score:</strong> {stats['mean']:.2f}</p>
        <p><strong>Standard Deviation:</strong> {stats['std_dev']:.2f}</p>
        <p><strong>95% Confidence Interval:</strong> [{stats['confidence_interval_95'][0]:.2f}, {stats['confidence_interval_95'][1]:.2f}]</p>
        <p><strong>Range:</strong> {stats['min']:.1f} - {stats['max']:.1f}</p>
        <p><strong>Median:</strong> {stats['median']:.1f}</p>
    </div>
"""
        
        # Add agent results table
        html += """
    <h3>Agent Results</h3>
    <table>
        <tr>
            <th>Agent</th>
            <th>Test Case</th>
            <th>Type</th>
            <th>Result</th>
            <th>Score</th>
        </tr>
"""
        
        for agent_name, agent_tests in result.details.get('agent_results', {}).items():
            for test in agent_tests:
                status = "PASS" if test['passed'] else "FAIL"
                score = test.get('score', 0)
                html += f"""
        <tr>
            <td>{agent_name}</td>
            <td>{test['test_case']['name']}</td>
            <td>{test['type']}</td>
            <td class="{'success' if test['passed'] else 'failure'}">{status}</td>
            <td>{score:.1f}</td>
        </tr>
"""
        
        html += """
    </table>
    
    <footer style="margin-top: 40px; color: #666; font-size: 0.9em;">
        Generated with PraisonAI Evaluation Framework
    </footer>
</body>
</html>
"""
        
        return html

    def _generate_markdown_report(self, result: EvalSuiteResult) -> str:
        """Generate Markdown report."""
        md = f"""# Evaluation Report: {result.name}

**Generated:** {result.timestamp}

## Summary

- **Success Rate:** {result.success_rate:.1f}%
- **Tests Passed:** {result.passed_tests}/{result.total_tests}

"""
        
        stats = result.details.get('statistical_analysis')
        if stats:
            md += f"""## Statistical Analysis

- **Mean Score:** {stats['mean']:.2f}
- **Standard Deviation:** {stats['std_dev']:.2f}
- **95% Confidence Interval:** [{stats['confidence_interval_95'][0]:.2f}, {stats['confidence_interval_95'][1]:.2f}]
- **Range:** {stats['min']:.1f} - {stats['max']:.1f}
- **Median:** {stats['median']:.1f}
- **Sample Size:** {stats['sample_size']}

"""
        
        md += """## Test Results

| Agent | Test Case | Type | Result | Score |
|-------|-----------|------|---------|-------|
"""
        
        for agent_name, agent_tests in result.details.get('agent_results', {}).items():
            for test in agent_tests:
                status = "✅ PASS" if test['passed'] else "❌ FAIL"
                score = test.get('score', 0)
                md += f"| {agent_name} | {test['test_case']['name']} | {test['type']} | {status} | {score:.1f} |\n"
        
        md += "\n---\n*Generated with PraisonAI Evaluation Framework*\n"
        
        return md

    def generate_report(
        self,
        format: str = "json",
        include_graphs: bool = False,
        compare_with: Optional[str] = None
    ) -> str:
        """
        Generate a comprehensive evaluation report.
        
        Args:
            format: Report format ("json", "html", "markdown")
            include_graphs: Whether to include performance graphs
            compare_with: Compare with previous results (e.g., "last_week")
            
        Returns:
            Report content or file path
        """
        # First run the evaluation to get results
        result = self.run()
        
        if format == "json":
            return json.dumps(result.to_dict(), indent=2)
        elif format == "html":
            return self._generate_html_report(result)
        elif format == "markdown":
            return self._generate_markdown_report(result)
        else:
            raise ValueError(f"Unsupported format: {format}")