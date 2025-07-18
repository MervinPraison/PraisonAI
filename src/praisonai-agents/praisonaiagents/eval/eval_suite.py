"""
Comprehensive evaluation suite for PraisonAI agents.
"""

import json
import time
import logging
import os
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from ..agent.agent import Agent
from .accuracy_eval import AccuracyEval
from .reliability_eval import ReliabilityEval
from .performance_eval import PerformanceEval

logger = logging.getLogger(__name__)

@dataclass
class TestCase:
    """A single test case for evaluation."""
    
    name: str
    input: str
    eval_type: str  # "accuracy", "reliability", "performance"
    expected_output: Optional[str] = None
    expected_tools: Optional[List[str]] = None
    max_runtime: Optional[float] = None
    max_memory: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    weight: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'input': self.input,
            'eval_type': self.eval_type,
            'expected_output': self.expected_output,
            'expected_tools': self.expected_tools,
            'max_runtime': self.max_runtime,
            'max_memory': self.max_memory,
            'tags': self.tags,
            'weight': self.weight
        }

class EvalFailure(Exception):
    """Exception raised when evaluation fails quality gates."""
    pass

@dataclass
class EvalSuiteResult:
    """Result of a complete evaluation suite run."""
    
    name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    success_rate: float
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    @property
    def passed(self) -> bool:
        """Whether the evaluation suite passed."""
        return self.failed_tests == 0
    
    @property
    def summary(self) -> str:
        """Summary string for the results."""
        return f"{self.passed_tests}/{self.total_tests} tests passed ({self.success_rate:.1f}%)"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'total_tests': self.total_tests,
            'passed_tests': self.passed_tests,
            'failed_tests': self.failed_tests,
            'success_rate': self.success_rate,
            'passed': self.passed,
            'summary': self.summary,
            'details': self.details,
            'timestamp': self.timestamp
        }

class EvalSuite:
    """Comprehensive evaluation suite for agents with automation capabilities."""
    
    def __init__(
        self,
        name: str,
        agents: List[Agent],
        test_cases: List[TestCase],
        schedule: Optional[str] = None,
        alerts: Optional[Dict[str, Any]] = None,
        export_results: Optional[str] = None
    ):
        """
        Initialize evaluation suite.
        
        Args:
            name: Name of the evaluation suite
            agents: List of agents to evaluate
            test_cases: List of test cases to run
            schedule: Cron schedule for automated runs (e.g., "0 2 * * *")
            alerts: Alert configuration (email, threshold, etc.)
            export_results: Path/URL for exporting results
        """
        self.name = name
        self.agents = agents
        self.test_cases = test_cases
        self.schedule = schedule
        self.alerts = alerts or {}
        self.export_results = export_results
    
    def _run_accuracy_test(self, agent: Agent, test_case: TestCase) -> Dict[str, Any]:
        """Run an accuracy test case."""
        try:
            evaluator = AccuracyEval(
                agent=agent,
                input=test_case.input,
                expected_output=test_case.expected_output
            )
            result = evaluator.run()
            
            return {
                'type': 'accuracy',
                'passed': result.success and result.score >= 7.0,  # Default threshold
                'score': result.score,
                'details': result.details if hasattr(result, 'details') else {},
                'error': result.error if hasattr(result, 'error') else None
            }
            
        except Exception as e:
            logger.error(f"Error running accuracy test: {e}")
            return {
                'type': 'accuracy',
                'passed': False,
                'score': 0.0,
                'error': str(e)
            }
    
    def _run_reliability_test(self, agent: Agent, test_case: TestCase) -> Dict[str, Any]:
        """Run a reliability test case."""
        try:
            test_scenarios = [{
                'name': test_case.name,
                'input': test_case.input,
                'expected_tools': test_case.expected_tools or [],
                'required_order': False,
                'allow_additional': True
            }]
            
            evaluator = ReliabilityEval(
                agent=agent,
                test_scenarios=test_scenarios
            )
            result = evaluator.run()
            
            passed = result.success and result.success_rate >= 80.0  # Default threshold
            
            return {
                'type': 'reliability',
                'passed': passed,
                'success_rate': result.success_rate,
                'details': result.to_dict(),
                'error': result.error
            }
            
        except Exception as e:
            logger.error(f"Error running reliability test: {e}")
            return {
                'type': 'reliability',
                'passed': False,
                'success_rate': 0.0,
                'error': str(e)
            }
    
    def _run_performance_test(self, agent: Agent, test_case: TestCase) -> Dict[str, Any]:
        """Run a performance test case."""
        try:
            evaluator = PerformanceEval(
                agent=agent,
                benchmark_queries=[test_case.input]
            )
            result = evaluator.run()
            
            # Check performance thresholds
            passed = True
            if test_case.max_runtime and result.runtime > test_case.max_runtime:
                passed = False
            if test_case.max_memory and result.memory_mb and result.memory_mb > test_case.max_memory:
                passed = False
            
            return {
                'type': 'performance',
                'passed': passed and result.success,
                'runtime': result.runtime,
                'memory_mb': result.memory_mb,
                'tokens': result.tokens,
                'details': result.details if hasattr(result, 'details') else {},
                'error': result.error if hasattr(result, 'error') else None
            }
            
        except Exception as e:
            logger.error(f"Error running performance test: {e}")
            return {
                'type': 'performance',
                'passed': False,
                'runtime': 0.0,
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
                    
                    if verbose:
                        status = "PASS" if test_result['passed'] else "FAIL"
                        print(f"    {status}: {test_case.name}")
                
                agent_results[agent_name] = agent_test_results
            
            # Calculate overall results
            failed_tests = total_tests - passed_tests
            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0
            
            suite_result = EvalSuiteResult(
                name=self.name,
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                success_rate=success_rate,
                details={
                    'agent_results': agent_results,
                    'test_cases': [tc.to_dict() for tc in self.test_cases]
                }
            )
            
            if verbose:
                print(f"\nSuite Results: {suite_result.summary}")
            
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
    
    def _check_alerts(self, result: EvalSuiteResult):
        """Check if alerts should be triggered."""
        try:
            threshold = self.alerts.get('threshold', 0.8)
            if result.success_rate < (threshold * 100):
                email = self.alerts.get('email')
                if email:
                    # TODO: Implement email alerting
                    logger.warning(f"Quality gate failed: {result.summary}. Email alert would be sent to {email}")
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")
    
    def _export_results(self, result: EvalSuiteResult):
        """Export results to specified location."""
        try:
            if self.export_results.startswith('s3://'):
                # TODO: Implement S3 export
                logger.info(f"S3 export not yet implemented: {self.export_results}")
            elif self.export_results.startswith('http'):
                # TODO: Implement HTTP export
                logger.info(f"HTTP export not yet implemented: {self.export_results}")
            else:
                # Local file export
                with open(self.export_results, 'w') as f:
                    json.dump(result.to_dict(), f, indent=2)
                logger.info(f"Results exported to {self.export_results}")
        except Exception as e:
            logger.error(f"Error exporting results: {e}")
    
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
        try:
            # Run the evaluation
            result = self.run()
            
            if format == "json":
                return json.dumps(result.to_dict(), indent=2)
            
            elif format == "html":
                # TODO: Generate HTML report with graphs
                html_content = f"""
                <html>
                <head><title>Evaluation Report: {self.name}</title></head>
                <body>
                <h1>Evaluation Report: {self.name}</h1>
                <p>Summary: {result.summary}</p>
                <p>Timestamp: {time.ctime(result.timestamp)}</p>
                <p>Note: HTML report generation not fully implemented</p>
                </body>
                </html>
                """
                return html_content
            
            elif format == "markdown":
                # Generate Markdown report
                md_content = f"""
# Evaluation Report: {self.name}

## Summary
- **Total Tests**: {result.total_tests}
- **Passed**: {result.passed_tests}
- **Failed**: {result.failed_tests}
- **Success Rate**: {result.success_rate:.1f}%
- **Timestamp**: {time.ctime(result.timestamp)}

## Test Results
{json.dumps(result.details, indent=2)}

## Notes
- Report generated automatically by PraisonAI Eval Framework
"""
                return md_content
            
            else:
                raise ValueError(f"Unsupported format: {format}")
                
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return f"Error generating report: {e}"