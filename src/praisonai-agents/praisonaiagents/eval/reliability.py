"""
Reliability evaluator for PraisonAI Agents.

Evaluates agent reliability by verifying expected tool calls are made.
"""

import logging
from typing import Dict, List, Optional, Set, Any, TYPE_CHECKING

from .base import BaseEvaluator
from .results import ReliabilityResult, ToolCallResult

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..agents.agents import AgentManager

logger = logging.getLogger(__name__)


class ReliabilityEvaluator(BaseEvaluator):
    """
    Evaluates the reliability of agent tool usage.
    
    Verifies that expected tools are called during agent execution.
    """
    
    def __init__(
        self,
        agent: Optional["Agent"] = None,
        input_text: str = "",
        expected_tools: Optional[List[str]] = None,
        forbidden_tools: Optional[List[str]] = None,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the reliability evaluator.
        
        Args:
            agent: Agent to evaluate
            input_text: Input to provide to the agent
            expected_tools: List of tool names that should be called
            forbidden_tools: List of tool names that should NOT be called
            name: Name for this evaluation
            save_results_path: Path to save results
            verbose: Enable verbose output
        """
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        
        self.agent = agent
        self.input_text = input_text
        self.expected_tools = set(expected_tools or [])
        self.forbidden_tools = set(forbidden_tools or [])
        
        if agent is None:
            raise ValueError("'agent' must be provided")
    
    def _extract_tool_calls(self, response: Any) -> Set[str]:
        """
        Extract tool names from agent response.
        
        Args:
            response: Agent response object
            
        Returns:
            Set of tool names that were called
        """
        tool_calls = set()
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tc in response.tool_calls:
                if hasattr(tc, 'name'):
                    tool_calls.add(tc.name)
                elif hasattr(tc, 'function') and hasattr(tc.function, 'name'):
                    tool_calls.add(tc.function.name)
        
        if hasattr(self.agent, 'chat_history'):
            for msg in self.agent.chat_history:
                if isinstance(msg, dict):
                    if msg.get('role') == 'assistant' and 'tool_calls' in msg:
                        for tc in msg.get('tool_calls', []):
                            if isinstance(tc, dict) and 'function' in tc:
                                tool_calls.add(tc['function'].get('name', ''))
                    elif msg.get('role') == 'tool':
                        tool_name = msg.get('name', '')
                        if tool_name:
                            tool_calls.add(tool_name)
        
        return tool_calls
    
    def run(self, print_summary: bool = False) -> ReliabilityResult:
        """
        Execute the reliability evaluation.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            ReliabilityResult with tool call verification results
        """
        self.before_run()
        
        result = ReliabilityResult(
            eval_id=self.eval_id,
            name=self.name
        )
        
        try:
            if hasattr(self.agent, 'chat'):
                response = self.agent.chat(self.input_text)
            elif hasattr(self.agent, 'start'):
                response = self.agent.start(self.input_text)
            else:
                raise ValueError("Agent must have 'chat' or 'start' method")
            
            actual_tools = self._extract_tool_calls(response)
            
            if self.verbose:
                logger.info(f"Expected tools: {self.expected_tools}")
                logger.info(f"Actual tools called: {actual_tools}")
            
            for tool in self.expected_tools:
                was_called = tool in actual_tools
                result.tool_results.append(ToolCallResult(
                    tool_name=tool,
                    expected=True,
                    actual=was_called,
                    passed=was_called
                ))
            
            for tool in self.forbidden_tools:
                was_called = tool in actual_tools
                result.tool_results.append(ToolCallResult(
                    tool_name=tool,
                    expected=False,
                    actual=was_called,
                    passed=not was_called
                ))
            
        except Exception as e:
            logger.error(f"Error during reliability evaluation: {e}")
            for tool in self.expected_tools:
                result.tool_results.append(ToolCallResult(
                    tool_name=tool,
                    expected=True,
                    actual=False,
                    passed=False,
                    metadata={"error": str(e)}
                ))
        
        self.after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
    
    async def run_async(self, print_summary: bool = False) -> ReliabilityResult:
        """
        Execute the reliability evaluation asynchronously.
        
        Args:
            print_summary: Whether to print summary after evaluation
            
        Returns:
            ReliabilityResult with tool call verification results
        """
        await self.async_before_run()
        result = self.run(print_summary=False)
        await self.async_after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
    
    def evaluate_tool_calls(
        self,
        actual_tools: List[str],
        print_summary: bool = False
    ) -> ReliabilityResult:
        """
        Evaluate a pre-recorded list of tool calls without running the agent.
        
        Args:
            actual_tools: List of tool names that were called
            print_summary: Whether to print summary after evaluation
            
        Returns:
            ReliabilityResult with tool call verification results
        """
        self.before_run()
        
        result = ReliabilityResult(
            eval_id=self.eval_id,
            name=self.name
        )
        
        actual_set = set(actual_tools)
        
        for tool in self.expected_tools:
            was_called = tool in actual_set
            result.tool_results.append(ToolCallResult(
                tool_name=tool,
                expected=True,
                actual=was_called,
                passed=was_called
            ))
        
        for tool in self.forbidden_tools:
            was_called = tool in actual_set
            result.tool_results.append(ToolCallResult(
                tool_name=tool,
                expected=False,
                actual=was_called,
                passed=not was_called
            ))
        
        self.after_run(result)
        
        if print_summary:
            result.print_summary()
        
        return result
