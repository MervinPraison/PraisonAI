"""
Reliability evaluation for PraisonAI agents.
"""

import json
import time
import logging
from typing import List, Dict, Any, Optional, Union, NamedTuple
from ..agent.agent import Agent
from ..main import TaskOutput
from .eval_result import ReliabilityResult

logger = logging.getLogger(__name__)

class ReliabilityScenario(NamedTuple):
    """A reliability test scenario result."""
    name: str
    status: str
    failed_tools: List[str]
    unexpected_tools: List[str]
    details: Dict[str, Any]

class ReliabilityEvalResult:
    """Result of reliability evaluation with multiple scenarios."""
    
    def __init__(self):
        self.scenarios: List[ReliabilityScenario] = []
        self.timestamp = time.time()
        self.success = True
        self.error: Optional[str] = None
    
    @property
    def total_scenarios(self) -> int:
        """Total number of scenarios."""
        return len(self.scenarios)
    
    @property
    def passed_scenarios(self) -> int:
        """Number of passed scenarios."""
        return len([s for s in self.scenarios if s.status == "passed"])
    
    @property
    def failed_scenarios(self) -> int:
        """Number of failed scenarios."""
        return len([s for s in self.scenarios if s.status == "failed"])
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total_scenarios == 0:
            return 100.0
        return (self.passed_scenarios / self.total_scenarios) * 100.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'total_scenarios': self.total_scenarios,
            'passed_scenarios': self.passed_scenarios,
            'failed_scenarios': self.failed_scenarios,
            'success_rate': self.success_rate,
            'scenarios': [
                {
                    'name': s.name,
                    'status': s.status,
                    'failed_tools': s.failed_tools,
                    'unexpected_tools': s.unexpected_tools,
                    'details': s.details
                }
                for s in self.scenarios
            ],
            'timestamp': self.timestamp,
            'success': self.success,
            'error': self.error
        }

class ReliabilityEval:
    """Evaluate agent reliability based on tool usage and behavioral consistency."""
    
    def __init__(
        self,
        agent: Agent,
        test_scenarios: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize reliability evaluation.
        
        Args:
            agent: Agent to evaluate
            test_scenarios: List of test scenarios with input, expected_tools, etc.
        """
        self.agent = agent
        self.test_scenarios = test_scenarios or []
    
    def _extract_tool_calls(self, task_output: TaskOutput) -> List[str]:
        """
        Extract tool names from task output.
        
        Args:
            task_output: The task output to analyze
            
        Returns:
            List of tool names that were called
        """
        tool_calls = []
        
        try:
            # Check if task_output has tool_calls attribute
            if hasattr(task_output, 'tool_calls') and task_output.tool_calls:
                for tool_call in task_output.tool_calls:
                    if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'name'):
                        tool_calls.append(tool_call.function.name)
                    elif isinstance(tool_call, dict) and 'function' in tool_call:
                        tool_calls.append(tool_call['function'].get('name', ''))
            
            # Check task details for tool information
            if hasattr(task_output, 'details') and isinstance(task_output.details, dict):
                tools_used = task_output.details.get('tools_used', [])
                if isinstance(tools_used, list):
                    tool_calls.extend(tools_used)
            
            # Parse from raw output if available (fallback)
            if hasattr(task_output, 'raw') and task_output.raw:
                # Simple heuristic to detect tool usage from output text
                raw_text = task_output.raw.lower()
                common_tools = [
                    'web_search', 'duckduckgo_search', 'wikipedia_search',
                    'create_file', 'read_file', 'write_file',
                    'calculator', 'python_repl', 'shell_command',
                    'analyze_data', 'read_csv', 'summarize'
                ]
                
                for tool in common_tools:
                    if tool in raw_text or tool.replace('_', ' ') in raw_text:
                        tool_calls.append(tool)
        
        except Exception as e:
            logger.warning(f"Error extracting tool calls: {e}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_tools = []
        for tool in tool_calls:
            if tool not in seen:
                seen.add(tool)
                unique_tools.append(tool)
        
        return unique_tools
    
    def _evaluate_scenario(self, scenario: Dict[str, Any]) -> ReliabilityScenario:
        """
        Evaluate a single reliability scenario.
        
        Args:
            scenario: Test scenario configuration
            
        Returns:
            ReliabilityScenario result
        """
        scenario_name = scenario.get('name', f"Scenario {scenario.get('input', '')[:20]}")
        test_input = scenario.get('input', '')
        expected_tools = scenario.get('expected_tools', [])
        required_order = scenario.get('required_order', False)
        allow_additional = scenario.get('allow_additional', False)
        
        try:
            # Execute the task
            task_result = self.agent.execute(test_input)
            if not isinstance(task_result, TaskOutput):
                task_result = TaskOutput(raw=str(task_result))
            
            # Extract actual tool calls
            actual_tools = self._extract_tool_calls(task_result)
            
            # Evaluate tool usage
            failed_tools = []
            unexpected_tools = []
            
            # Check for missing expected tools
            if required_order:
                # Check order and presence
                expected_set = set(expected_tools)
                actual_set = set(actual_tools)
                missing_tools = expected_set - actual_set
                failed_tools.extend(list(missing_tools))
                
                # Check order for tools that are present
                common_tools = [t for t in expected_tools if t in actual_tools]
                actual_order = [t for t in actual_tools if t in common_tools]
                
                if common_tools != actual_order[:len(common_tools)]:
                    # Order mismatch
                    failed_tools.append("tool_order_mismatch")
            else:
                # Just check presence
                missing_tools = set(expected_tools) - set(actual_tools)
                failed_tools.extend(list(missing_tools))
            
            # Check for unexpected tools
            if not allow_additional:
                extra_tools = set(actual_tools) - set(expected_tools)
                unexpected_tools.extend(list(extra_tools))
            
            # Determine status
            status = "passed" if not failed_tools and not unexpected_tools else "failed"
            
            details = {
                'input': test_input,
                'expected_tools': expected_tools,
                'actual_tools': actual_tools,
                'required_order': required_order,
                'allow_additional': allow_additional,
                'task_output': task_result.raw if hasattr(task_result, 'raw') else str(task_result)
            }
            
            return ReliabilityScenario(
                name=scenario_name,
                status=status,
                failed_tools=failed_tools,
                unexpected_tools=unexpected_tools,
                details=details
            )
            
        except Exception as e:
            logger.error(f"Error evaluating scenario '{scenario_name}': {e}")
            return ReliabilityScenario(
                name=scenario_name,
                status="error",
                failed_tools=[],
                unexpected_tools=[],
                details={'error': str(e), 'input': test_input}
            )
    
    def run(self, verbose: bool = False) -> ReliabilityEvalResult:
        """
        Run the reliability evaluation.
        
        Args:
            verbose: Whether to print detailed output
            
        Returns:
            ReliabilityEvalResult with scenario results
        """
        result = ReliabilityEvalResult()
        
        try:
            if not self.test_scenarios:
                result.success = False
                result.error = "No test scenarios provided"
                return result
            
            for scenario in self.test_scenarios:
                if verbose:
                    scenario_name = scenario.get('name', f"Scenario {scenario.get('input', '')[:20]}")
                    print(f"Evaluating scenario: {scenario_name}")
                
                scenario_result = self._evaluate_scenario(scenario)
                result.scenarios.append(scenario_result)
                
                if verbose:
                    print(f"  Status: {scenario_result.status}")
                    if scenario_result.failed_tools:
                        print(f"  Failed tools: {scenario_result.failed_tools}")
                    if scenario_result.unexpected_tools:
                        print(f"  Unexpected tools: {scenario_result.unexpected_tools}")
            
            if verbose:
                print(f"\nOverall success rate: {result.success_rate:.1f}%")
            
            result.success = True
            
        except Exception as e:
            logger.error(f"Error running reliability evaluation: {e}")
            result.success = False
            result.error = str(e)
        
        return result