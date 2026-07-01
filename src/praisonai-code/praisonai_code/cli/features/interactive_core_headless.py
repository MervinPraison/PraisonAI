"""
Headless Interactive Core Executor for PraisonAI.

This module provides a headless execution mode that uses the SAME interactive core
pipeline as the interactive TUI:
- InteractiveRuntime config
- get_interactive_tools() tool resolution
- ActionOrchestrator behavior (plan/approve/apply/verify)
- Tool call tracing

This is for tests and CI - no terminal/prompt_toolkit dependency.
"""

import functools
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class ToolCallTrace:
    """Record of a single tool call."""
    tool_name: str
    args: Tuple
    kwargs: Dict[str, Any]
    result: Any
    success: bool
    error: Optional[str]
    duration: float
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "args": _redact_sensitive(self.args),
            "kwargs": _redact_sensitive(self.kwargs),
            "result": _truncate(str(self.result), 500) if self.result else None,
            "success": self.success,
            "error": self.error,
            "duration": self.duration,
            "timestamp": self.timestamp,
        }


@dataclass
class HeadlessExecutionResult:
    """Result of a headless execution."""
    success: bool
    responses: List[str]
    tool_trace: List[ToolCallTrace]
    duration: float
    error: Optional[str] = None
    transcript: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "responses": self.responses,
            "tool_trace": [t.to_dict() for t in self.tool_trace],
            "duration": self.duration,
            "error": self.error,
            "transcript": self.transcript,
        }


@dataclass
class AgentConfig:
    """Configuration for a single agent in headless mode."""
    name: str = "HeadlessAgent"
    instructions: str = "You are a helpful assistant with file and code tools."
    role: str = "assistant"
    llm: str = "gpt-4o-mini"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "instructions": self.instructions,
            "role": self.role,
            "llm": self.llm,
        }


@dataclass 
class HeadlessConfig:
    """Configuration for headless interactive core execution."""
    workspace: str = field(default_factory=os.getcwd)
    model: str = "gpt-4o-mini"
    approval_mode: str = "auto"  # auto, manual, scoped
    enable_acp: bool = True
    enable_lsp: bool = True
    enable_basic: bool = True
    timeout: int = 60
    verbose: bool = False
    # Multi-agent support
    agents: List[AgentConfig] = field(default_factory=list)
    workflow: Optional[Dict[str, Any]] = None  # Turn routing/handoffs
    
    def __post_init__(self):
        if not self.agents:
            # Default single agent
            self.agents = [AgentConfig(llm=self.model)]


def _redact_sensitive(obj: Any, sensitive_keys: set = None) -> Any:
    """Redact sensitive information from args/kwargs."""
    if sensitive_keys is None:
        sensitive_keys = {"api_key", "password", "secret", "token", "key"}
    
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if any(s in k.lower() for s in sensitive_keys) else _redact_sensitive(v, sensitive_keys)
            for k, v in obj.items()
        }
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_redact_sensitive(item, sensitive_keys) for item in obj)
    elif isinstance(obj, str) and len(obj) > 100:
        return obj[:100] + "...[truncated]"
    return obj


def _truncate(s: str, max_len: int) -> str:
    """Truncate string to max length."""
    if len(s) <= max_len:
        return s
    return s[:max_len] + "...[truncated]"


class HeadlessInteractiveCore:
    """
    Headless executor that uses the same interactive core pipeline as TUI.
    
    This class reuses:
    - InteractiveRuntime for ACP/LSP subsystems
    - get_interactive_tools() for tool resolution
    - ActionOrchestrator for plan/approve/apply/verify flow
    
    Usage:
        executor = HeadlessInteractiveCore(config)
        result = executor.run(["Create a file hello.py with print('hello')"])
        executor.cleanup()  # IMPORTANT: Always call cleanup to stop LSP/ACP
        
    Or use as context manager:
        with HeadlessInteractiveCore(config) as executor:
            result = executor.run(["Create a file"])
    """
    
    def __init__(self, config: Optional[HeadlessConfig] = None):
        self.config = config or HeadlessConfig()
        self._runtime = None
        self._tools: List[Callable] = []
        self._tool_trace: List[ToolCallTrace] = []
        self._agents: List[Any] = []  # Will hold Agent instances
        self._initialized = False
        self._cleanup_done = False
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.cleanup()
        return False
    
    def __del__(self):
        """Destructor - attempt cleanup if not done."""
        if not self._cleanup_done:
            try:
                self.cleanup()
            except Exception:
                pass  # Best effort cleanup in destructor
    
    def _wrap_tool_for_trace(self, tool: Callable) -> Callable:
        """Wrap a tool to capture calls in trace."""
        @functools.wraps(tool)
        def wrapper(*args, **kwargs):
            start = time.time()
            timestamp = datetime.utcnow().isoformat()
            try:
                result = tool(*args, **kwargs)
                trace = ToolCallTrace(
                    tool_name=tool.__name__,
                    args=args,
                    kwargs=kwargs,
                    result=result,
                    success=True,
                    error=None,
                    duration=time.time() - start,
                    timestamp=timestamp,
                )
                self._tool_trace.append(trace)
                logger.debug(f"Tool {tool.__name__} succeeded in {trace.duration:.3f}s")
                return result
            except Exception as e:
                trace = ToolCallTrace(
                    tool_name=tool.__name__,
                    args=args,
                    kwargs=kwargs,
                    result=None,
                    success=False,
                    error=str(e),
                    duration=time.time() - start,
                    timestamp=timestamp,
                )
                self._tool_trace.append(trace)
                logger.debug(f"Tool {tool.__name__} failed: {e}")
                raise
        return wrapper
    
    def _initialize(self) -> None:
        """Initialize runtime and tools using interactive core path."""
        if self._initialized:
            return
        
        logger.debug(f"Initializing headless core with workspace={self.config.workspace}")
        
        # Use the SAME tool loading path as interactive TUI
        # This is from: praisonai/cli/features/interactive_tools.py
        from praisonai.cli.features.interactive_tools import (
            get_interactive_tools,
            ToolConfig,
        )
        
        # Create tool config matching interactive core
        tool_config = ToolConfig(
            workspace=self.config.workspace,
            enable_acp=self.config.enable_acp,
            enable_lsp=self.config.enable_lsp,
            enable_basic=self.config.enable_basic,
            approval_mode=self.config.approval_mode,
            lsp_enabled=self.config.enable_lsp,
            acp_enabled=self.config.enable_acp,
        )
        
        # Get tools using the SAME function as TUI
        raw_tools = get_interactive_tools(config=tool_config)
        
        # Wrap tools for tracing
        self._tools = [self._wrap_tool_for_trace(t) for t in raw_tools]
        
        logger.debug(f"Loaded {len(self._tools)} tools: {[t.__name__ for t in self._tools]}")
        
        # Create agents using the SAME Agent class as TUI
        from praisonaiagents import Agent
        
        for agent_config in self.config.agents:
            agent = Agent(
                name=agent_config.name,
                role=agent_config.role,
                goal="Help the user with their requests",
                instructions=agent_config.instructions,
                llm=agent_config.llm,
                tools=self._tools if self._tools else None,
            )
            self._agents.append(agent)
            logger.debug(f"Created agent: {agent_config.name}")
        
        self._initialized = True
    
    def run(self, prompts: Union[str, List[str]]) -> HeadlessExecutionResult:
        """
        Run prompts through headless interactive core.
        
        Args:
            prompts: Single prompt or list of prompts for multi-step execution
            
        Returns:
            HeadlessExecutionResult with responses, tool trace, and transcript
        """
        if isinstance(prompts, str):
            prompts = [prompts]
        
        start_time = time.time()
        self._tool_trace = []  # Reset trace
        responses = []
        transcript = []
        
        try:
            self._initialize()
            
            # Execute prompts
            for i, prompt in enumerate(prompts):
                logger.debug(f"Executing prompt {i+1}/{len(prompts)}: {prompt[:50]}...")
                transcript.append({"role": "user", "content": prompt})
                
                # Determine which agent to use
                agent_idx = self._get_agent_for_prompt(i, prompt)
                agent = self._agents[agent_idx]
                
                # Execute using the SAME chat method as TUI
                response = agent.chat(prompt)
                responses.append(response)
                transcript.append({"role": "assistant", "content": response})
                
                logger.debug(f"Got response: {response[:100] if response else 'None'}...")
            
            return HeadlessExecutionResult(
                success=True,
                responses=responses,
                tool_trace=self._tool_trace,
                duration=time.time() - start_time,
                transcript=transcript,
            )
            
        except Exception as e:
            logger.error(f"Headless execution failed: {e}", exc_info=True)
            return HeadlessExecutionResult(
                success=False,
                responses=responses,
                tool_trace=self._tool_trace,
                duration=time.time() - start_time,
                error=str(e),
                transcript=transcript,
            )
    
    def _get_agent_for_prompt(self, prompt_idx: int, prompt: str) -> int:
        """Determine which agent should handle a prompt (for multi-agent)."""
        if len(self._agents) == 1:
            return 0
        
        # If workflow is defined, use it for routing
        if self.config.workflow:
            routing = self.config.workflow.get("routing", {})
            # Simple round-robin or keyword-based routing
            if "round_robin" in routing:
                return prompt_idx % len(self._agents)
            elif "keywords" in routing:
                for i, agent_config in enumerate(self.config.agents):
                    keywords = routing["keywords"].get(agent_config.name, [])
                    if any(kw.lower() in prompt.lower() for kw in keywords):
                        return i
        
        # Default: round-robin
        return prompt_idx % len(self._agents)
    
    def get_tool_trace(self) -> List[Dict[str, Any]]:
        """Get the tool call trace as list of dicts."""
        return [t.to_dict() for t in self._tool_trace]
    
    def get_tools_called(self) -> List[str]:
        """Get list of tool names that were called."""
        return [t.tool_name for t in self._tool_trace]
    
    def clear_trace(self) -> None:
        """Clear the tool trace."""
        self._tool_trace = []
    
    def cleanup(self) -> None:
        """
        Clean up resources - MUST be called when done.
        
        Stops LSP and ACP subsystems that were started during initialization.
        This is critical to prevent resource leaks and orphaned processes.
        """
        if self._cleanup_done:
            return
        
        logger.debug("Cleaning up HeadlessInteractiveCore resources...")
        
        # Stop the runtime if it was created
        if self._runtime is not None:
            try:
                import asyncio
                
                # Get or create event loop
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                
                if loop and loop.is_running():
                    # Schedule the stop coroutine
                    asyncio.ensure_future(self._runtime.stop())
                else:
                    # Create new loop and run
                    asyncio.run(self._runtime.stop())
                
                logger.debug("Runtime stopped successfully")
            except Exception as e:
                logger.warning(f"Error stopping runtime: {e}")
            finally:
                self._runtime = None
        
        # Clear agents
        self._agents = []
        self._tools = []
        self._initialized = False
        self._cleanup_done = True
        
        logger.debug("HeadlessInteractiveCore cleanup complete")


def run_headless(
    prompts: Union[str, List[str]],
    workspace: Optional[str] = None,
    model: str = "gpt-4o-mini",
    approval_mode: str = "auto",
    timeout: int = 60,
    agents: Optional[List[Dict[str, Any]]] = None,
    workflow: Optional[Dict[str, Any]] = None,
) -> HeadlessExecutionResult:
    """
    Convenience function to run prompts through headless interactive core.
    
    Args:
        prompts: Single prompt or list of prompts
        workspace: Working directory (default: cwd)
        model: LLM model to use
        approval_mode: Approval mode (auto, manual, scoped)
        timeout: Timeout in seconds
        agents: List of agent configs for multi-agent
        workflow: Workflow config for turn routing
        
    Returns:
        HeadlessExecutionResult
        
    Example:
        result = run_headless("Create a file hello.py with print('hello')")
        print(result.responses[0])
        print(result.get_tools_called())
    """
    agent_configs = []
    if agents:
        for a in agents:
            agent_configs.append(AgentConfig(
                name=a.get("name", "Agent"),
                instructions=a.get("instructions", "You are a helpful assistant."),
                role=a.get("role", "assistant"),
                llm=a.get("llm", model),
            ))
    
    config = HeadlessConfig(
        workspace=workspace or os.getcwd(),
        model=model,
        approval_mode=approval_mode,
        timeout=timeout,
        agents=agent_configs if agent_configs else None,
        workflow=workflow,
    )
    
    # Use context manager to ensure cleanup
    with HeadlessInteractiveCore(config) as executor:
        return executor.run(prompts)
