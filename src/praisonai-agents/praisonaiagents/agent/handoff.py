"""
Handoff functionality for agent-to-agent delegation.

This module provides handoff capabilities that allow agents to delegate tasks
to other agents, similar to the OpenAI Agents SDK implementation.

Unified Handoff System:
- Handoff: LLM-driven (tool call) or programmatic agent-to-agent transfer
- HandoffConfig: Configuration for context policy, timeouts, concurrency, safety
- Replaces/absorbs Agent.delegate() and SubagentDelegator functionality
"""

from typing import Optional, Any, Callable, Dict, List, Union, TYPE_CHECKING, Literal, TypeVar, Type, Generic
from dataclasses import dataclass, field
from enum import Enum
import inspect
import logging
from praisonaiagents._logging import get_logger
import asyncio
import threading
import time
import json

try:
    from pydantic import BaseModel, ValidationError as PydanticValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    if TYPE_CHECKING:
        from pydantic import BaseModel, ValidationError as PydanticValidationError
    else:
        # Provide a safe sentinel for runtime
        class BaseModel:  # type: ignore
            pass
        PydanticValidationError = Exception

from ..run_outcome import AgentRunOutcome, RunStatus

if TYPE_CHECKING:
    from .agent import Agent

logger = get_logger(__name__)

class ContextPolicy(Enum):
    """Policy for context sharing during handoff."""
    FULL = "full"       # Share full conversation history
    SUMMARY = "summary" # Share summarized context (default - safe)
    NONE = "none"       # No context sharing
    LAST_N = "last_n"   # Share last N messages

@dataclass
class HandoffToolPolicy:
    """
    Policy for tool boundary enforcement during handoff.
    
    Defines how tools are filtered when handing off to a target agent.
    Default mode is 'intersect' for security by default - sub-agents only
    get tools that both they and the source agent have access to.
    
    Attributes:
        mode: Tool filtering mode
            - "intersect": Target gets intersection of source and target tools (DEFAULT - secure)
            - "passthrough": Target keeps its full tool set (legacy behavior - opt-in)
        blocked_tools: List of tool names to always strip, regardless of intersection
    """
    mode: Literal["intersect", "passthrough"] = "intersect"
    blocked_tools: List[str] = field(default_factory=list)

@dataclass
class HandoffConfig:
    """
    Unified configuration for handoff behavior.
    
    This consolidates all handoff-related settings including context policy,
    timeouts, concurrency control, and safety features.
    
    Attributes:
        context_policy: How to share context during handoff (default: summary for safety)
        max_context_tokens: Maximum tokens to include in context
        max_context_messages: Maximum messages to include (for LAST_N policy)
        preserve_system: Whether to preserve system messages in context
        tool_policy: Tool boundary enforcement policy (NEW - security by default)
        timeout_seconds: Timeout for handoff execution
        max_concurrent: Maximum concurrent handoffs (0 = unlimited)
        detect_cycles: Enable cycle detection to prevent infinite loops
        max_depth: Maximum handoff chain depth
        async_mode: Enable async execution
        allow_parallel: Enable parallel execution (from Delegator)
        on_handoff: Callback when handoff starts
        on_complete: Callback when handoff completes
        on_error: Callback when handoff fails
    """
    # Context control
    context_policy: ContextPolicy = ContextPolicy.SUMMARY
    max_context_tokens: int = 4000
    max_context_messages: int = 10
    preserve_system: bool = True
    
    # Tool security boundary (NEW)
    tool_policy: HandoffToolPolicy = field(default_factory=HandoffToolPolicy)
    
    # Execution control
    timeout_seconds: float = 300.0
    max_concurrent: int = 5
    
    # Safety
    detect_cycles: bool = True
    max_depth: int = 10
    
    # Execution mode
    async_mode: bool = False
    allow_parallel: bool = False
    
    # Callbacks
    on_handoff: Optional[Callable] = None
    on_complete: Optional[Callable] = None
    on_error: Optional[Callable] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "context_policy": self.context_policy.value,
            "max_context_tokens": self.max_context_tokens,
            "max_context_messages": self.max_context_messages,
            "preserve_system": self.preserve_system,
            "tool_policy": {
                "mode": self.tool_policy.mode,
                "blocked_tools": self.tool_policy.blocked_tools.copy()
            },
            "timeout_seconds": self.timeout_seconds,
            "max_concurrent": self.max_concurrent,
            "detect_cycles": self.detect_cycles,
            "max_depth": self.max_depth,
            "async_mode": self.async_mode,
            "allow_parallel": self.allow_parallel,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HandoffConfig':
        """Create config from dictionary."""
        data_copy = data.copy()
        
        # Handle context_policy enum conversion
        if "context_policy" in data_copy and isinstance(data_copy["context_policy"], str):
            data_copy["context_policy"] = ContextPolicy(data_copy["context_policy"])
        
        # Handle tool_policy conversion
        if "tool_policy" in data_copy and isinstance(data_copy["tool_policy"], dict):
            tool_policy_data = data_copy["tool_policy"]
            data_copy["tool_policy"] = HandoffToolPolicy(
                mode=tool_policy_data.get("mode", "intersect"),
                blocked_tools=tool_policy_data.get("blocked_tools", [])
            )
        
        return cls(**{k: v for k, v in data_copy.items() if k in cls.__dataclass_fields__})

# Import structured error hierarchy from central errors module
from ..errors import (
    HandoffError, 
    HandoffCycleError, 
    HandoffDepthError, 
    HandoffTimeoutError,
    HandoffValidationError
)

# Thread-local storage for tracking handoff chains
_handoff_context = threading.local()

def _get_handoff_chain() -> List[str]:
    """Get current handoff chain from thread-local storage."""
    if not hasattr(_handoff_context, 'chain'):
        _handoff_context.chain = []
    return _handoff_context.chain

def _get_handoff_depth() -> int:
    """Get current handoff depth."""
    return len(_get_handoff_chain())

def _push_handoff(agent_name: str) -> None:
    """Push agent to handoff chain."""
    chain = _get_handoff_chain()
    chain.append(agent_name)

def _pop_handoff() -> Optional[str]:
    """Pop agent from handoff chain."""
    chain = _get_handoff_chain()
    return chain.pop() if chain else None

def _clear_handoff_chain() -> None:
    """Clear the handoff chain."""
    if hasattr(_handoff_context, 'chain'):
        _handoff_context.chain = []

@dataclass
class HandoffInputData:
    """Data passed to a handoff target agent."""
    messages: list = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    source_agent: Optional[str] = None
    handoff_depth: int = 0
    handoff_chain: List[str] = field(default_factory=list)

@dataclass 
class HandoffResult:
    """
    Result of a handoff operation.
    
    Now includes typed outcome information while maintaining backward
    compatibility with the legacy boolean success field.
    """
    success: bool
    response: Optional[str] = None
    target_agent: Optional[str] = None
    source_agent: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    handoff_depth: int = 0
    
    # New typed outcome field
    outcome: Optional[AgentRunOutcome] = None
    
    def __post_init__(self):
        """Initialize outcome field if not provided."""
        if self.outcome is None:
            # Create outcome based on legacy success field
            if self.success:
                self.outcome = AgentRunOutcome.success(
                    output=self.response or "",
                    elapsed_s=self.duration_seconds,
                    agent_name=self.target_agent,
                    context={
                        "source_agent": self.source_agent,
                        "handoff_depth": self.handoff_depth,
                    }
                )
            else:
                error_text = (self.error or "").lower()
                context = {
                    "source_agent": self.source_agent,
                    "handoff_depth": self.handoff_depth,
                }
                if any(keyword in error_text for keyword in ["timeout", "timed out"]):
                    self.outcome = AgentRunOutcome.timeout(
                        error=self.error or "Handoff failed",
                        elapsed_s=self.duration_seconds,
                        agent_name=self.target_agent,
                        context=context,
                    )
                else:
                    self.outcome = AgentRunOutcome.failure(
                        error=self.error or "Handoff failed",
                        elapsed_s=self.duration_seconds,
                        agent_name=self.target_agent,
                        context=context,
                    )
    
    @classmethod
    def from_outcome(
        cls,
        outcome: AgentRunOutcome,
        target_agent: Optional[str] = None,
        source_agent: Optional[str] = None,
        handoff_depth: int = 0,
    ) -> "HandoffResult":
        """Create HandoffResult from AgentRunOutcome."""
        return cls(
            success=outcome.is_success(),
            response=outcome.output,
            target_agent=target_agent or outcome.agent_name,
            source_agent=source_agent,
            duration_seconds=outcome.elapsed_s,
            error=outcome.error,
            handoff_depth=handoff_depth,
            outcome=outcome,
        )
    
    
class Handoff:
    """
    Represents a handoff configuration for delegating tasks to another agent.
    
    Handoffs are represented as tools to the LLM, allowing agents to transfer
    control to specialized agents for specific tasks.
    
    This is the unified mechanism for agent-to-agent task transfer, supporting:
    - LLM-driven handoffs (via tool calls)
    - Programmatic handoffs (direct Python API)
    - Async handoffs with concurrency control
    - Cycle detection and depth limiting
    - Configurable context policies
    """
    
    # Class-level semaphore for concurrency control
    _semaphore: Optional[asyncio.Semaphore] = None
    _sync_semaphore: Optional[threading.Semaphore] = None
    _semaphore_lock: threading.Lock = threading.Lock()  # Lock for semaphore initialization
    
    def __init__(
        self,
        agent: 'Agent',
        tool_name_override: Optional[str] = None,
        tool_description_override: Optional[str] = None,
        on_handoff: Optional[Callable] = None,
        input_type: Optional[type] = None,
        input_filter: Optional[Union[Callable[[HandoffInputData], HandoffInputData], List[Callable[[HandoffInputData], HandoffInputData]]]] = None,
        config: Optional[HandoffConfig] = None,
    ):
        """
        Initialize a Handoff configuration.
        
        Args:
            agent: The target agent to hand off to
            tool_name_override: Custom tool name (defaults to transfer_to_<agent_name>)
            tool_description_override: Custom tool description
            on_handoff: Callback function executed when handoff is invoked
            input_type: Type of input expected by the handoff (for structured data)
            input_filter: Function or list of functions to filter/transform input.
                When a list is provided, filters are applied in order (chaining).
            config: HandoffConfig for advanced settings (context policy, timeouts, etc.)
        """
        self.agent = agent
        self.tool_name_override = tool_name_override
        self.tool_description_override = tool_description_override
        self.on_handoff = on_handoff
        self.input_type = input_type
        self.input_filter = input_filter
        self.config = config or HandoffConfig()
        
        # Override config callback if on_handoff provided directly
        if on_handoff and not self.config.on_handoff:
            self.config.on_handoff = on_handoff
        
    @property
    def tool_name(self) -> str:
        """Get the tool name for this handoff."""
        if self.tool_name_override:
            return self.tool_name_override
        return self.default_tool_name()
        
    @property
    def tool_description(self) -> str:
        """Get the tool description for this handoff."""
        if self.tool_description_override:
            return self.tool_description_override
        return self.default_tool_description()
        
    def default_tool_name(self) -> str:
        """Generate default tool name based on agent name."""
        # Convert agent name to snake_case for tool name
        agent_name = self.agent.name.lower().replace(' ', '_')
        return f"transfer_to_{agent_name}"
        
    def default_tool_description(self) -> str:
        """Generate default tool description based on agent role and goal."""
        agent_desc = f"Transfer task to {self.agent.name}"
        if hasattr(self.agent, 'role') and self.agent.role:
            agent_desc += f" ({self.agent.role})"
        if hasattr(self.agent, 'goal') and self.agent.goal:
            agent_desc += f" - {self.agent.goal}"
        return agent_desc
        
    def _compute_effective_tools(self, source_agent: 'Agent') -> List[Any] | None:
        """
        Compute the effective tool set for the target agent based on tool policy.
        
        Args:
            source_agent: The agent initiating the handoff
            
        Returns:
            List of tools the target agent should have access to during handoff.
            Returns None to indicate unrestricted access (for passthrough mode without blocked tools).
            Returns [] to indicate no tools allowed (for intersect mode with empty intersection).
        """
        policy = self.config.tool_policy
        
        if policy.mode == "passthrough":
            # Legacy behavior - target keeps its full tool set, minus blocked tools
            if not policy.blocked_tools:
                # No restrictions - return None so chat() uses the agent's configured tools
                return None
            else:
                # Filter out blocked tools
                target_tools = getattr(self.agent, 'tools', None) or []
                effective_tools = [
                    tool for tool in target_tools
                    if getattr(tool, 'name', getattr(tool, '__name__', str(tool))) not in policy.blocked_tools
                ]
                return effective_tools
        else:  # intersect mode (default)
            # Security by default - intersection of source and target tools
            source_tools = getattr(source_agent, 'tools', None) or []
            source_tool_names = {
                getattr(tool, 'name', getattr(tool, '__name__', str(tool)))
                for tool in source_tools
            }
            
            target_tools = getattr(self.agent, 'tools', None) or []
            effective_tools = []
            for tool in target_tools:
                tool_name = getattr(tool, 'name', getattr(tool, '__name__', str(tool)))
                if (tool_name in source_tool_names and 
                    tool_name not in policy.blocked_tools):
                    effective_tools.append(tool)
            
            # In intersect mode, empty list means no tools allowed - this is the security boundary
            return effective_tools
    
    @staticmethod
    def _extract_model_ref(agent: 'Agent') -> str:
        """Extract a model reference string from an agent configuration."""
        llm = getattr(agent, 'llm', None) or getattr(agent, 'model', None)
        if isinstance(llm, str):
            return llm
        if llm is not None:
            for attr in ('model', 'model_name', 'model_ref'):
                value = getattr(llm, attr, None)
                if isinstance(value, str) and value:
                    return value
        return 'gpt-4o-mini'

    def _execute_with_runtime_resolution(
        self, 
        source_agent: 'Agent', 
        prompt: str, 
        effective_tools: Optional[List[Any]], 
        context: Dict[str, Any]
    ) -> str:
        """Execute handoff through the target agent's full chat pipeline."""
        target_model_ref = self._extract_model_ref(self.agent)
        logger.debug(
            "Handoff to %s via agent.chat (model=%s, depth=%s)",
            getattr(self.agent, 'name', 'unknown'),
            target_model_ref,
            _get_handoff_depth(),
        )
        return self.agent.chat(prompt, tools=effective_tools)
    
    async def _execute_with_runtime_resolution_async(
        self, 
        source_agent: 'Agent', 
        prompt: str, 
        effective_tools: Optional[List[Any]], 
        context: Dict[str, Any]
    ) -> str:
        """Execute handoff through the target agent's full async chat pipeline."""
        target_model_ref = self._extract_model_ref(self.agent)
        logger.debug(
            "Async handoff to %s via agent chat (model=%s, depth=%s)",
            getattr(self.agent, 'name', 'unknown'),
            target_model_ref,
            _get_handoff_depth(),
        )
        async_chat = getattr(self.agent, 'achat', None)
        if callable(async_chat) and inspect.iscoroutinefunction(async_chat):
            return await async_chat(prompt, tools=effective_tools)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.agent.chat(prompt, tools=effective_tools)
        )
    
    def _check_safety(self, source_agent: 'Agent') -> None:
        """
        Check safety constraints before handoff.
        
        Raises:
            HandoffCycleError: If cycle detected
            HandoffDepthError: If max depth exceeded
        """
        target_name = self.agent.name
        
        # Check for cycles
        if self.config.detect_cycles:
            chain = _get_handoff_chain()
            if target_name in chain:
                cycle_path = chain + [target_name]
                raise HandoffCycleError(
                    f"Handoff cycle detected: {' -> '.join(cycle_path)}",
                    source_agent=source_agent.name if hasattr(source_agent, 'name') else 'unknown',
                    target_agent=target_name,
                    agent_id=source_agent.name if hasattr(source_agent, 'name') else 'unknown',
                    cycle_path=cycle_path
                )
        
        # Check depth
        current_depth = _get_handoff_depth()
        if current_depth >= self.config.max_depth:
            raise HandoffDepthError(
                f"Max handoff depth exceeded: {current_depth + 1} > {self.config.max_depth}",
                source_agent=source_agent.name if hasattr(source_agent, 'name') else 'unknown',
                target_agent=target_name,
                agent_id=source_agent.name if hasattr(source_agent, 'name') else 'unknown',
                max_depth=self.config.max_depth,
                current_depth=current_depth + 1
            )
    
    def _prepare_context(self, source_agent: 'Agent', kwargs: Dict[str, Any]) -> HandoffInputData:
        """
        Prepare context data for handoff based on context policy.
        
        Args:
            source_agent: The source agent
            kwargs: Additional kwargs from tool call
            
        Returns:
            HandoffInputData with filtered context
        """
        messages = getattr(source_agent, 'chat_history', [])
        
        # Apply context policy
        if self.config.context_policy == ContextPolicy.NONE:
            filtered_messages = []
        elif self.config.context_policy == ContextPolicy.LAST_N:
            n = self.config.max_context_messages
            if self.config.preserve_system:
                system_msgs = [m for m in messages if isinstance(m, dict) and m.get('role') == 'system']
                other_msgs = [m for m in messages if not (isinstance(m, dict) and m.get('role') == 'system')]
                filtered_messages = system_msgs + other_msgs[-n:]
            else:
                filtered_messages = messages[-n:]
        elif self.config.context_policy == ContextPolicy.SUMMARY:
            # For summary, keep system + last few messages
            if self.config.preserve_system:
                system_msgs = [m for m in messages if isinstance(m, dict) and m.get('role') == 'system']
                other_msgs = [m for m in messages if not (isinstance(m, dict) and m.get('role') == 'system')]
                filtered_messages = system_msgs + other_msgs[-3:]  # Last 3 non-system
            else:
                filtered_messages = messages[-3:]
        else:  # FULL
            filtered_messages = messages[:]
        
        handoff_data = HandoffInputData(
            messages=filtered_messages,
            context={'source_agent': source_agent.name, **kwargs},
            source_agent=source_agent.name,
            handoff_depth=_get_handoff_depth(),
            handoff_chain=_get_handoff_chain()[:],
        )
        
        # Apply custom input filter(s) if provided
        # Supports both single filter and list of filters for chaining
        if self.input_filter:
            if isinstance(self.input_filter, list):
                for filter_fn in self.input_filter:
                    handoff_data = filter_fn(handoff_data)
            else:
                handoff_data = self.input_filter(handoff_data)
        
        return handoff_data
    
    def _execute_callback(self, callback: Optional[Callable], source_agent: 'Agent', 
                          kwargs: Dict[str, Any], result: Optional[HandoffResult] = None) -> None:
        """Execute a callback with appropriate arguments."""
        if not callback:
            return
        try:
            sig = inspect.signature(callback)
            params = list(sig.parameters.values())
            num_params = len([p for p in params if p.default == inspect.Parameter.empty 
                             and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)])
            
            if num_params == 0:
                callback()
            elif num_params == 1:
                callback(source_agent if not result else result)
            elif num_params >= 2:
                if result:
                    callback(source_agent, result)
                elif self.input_type and kwargs:
                    try:
                        input_data = self.input_type(**kwargs)
                        callback(source_agent, input_data)
                    except TypeError:
                        callback(source_agent, kwargs)
                else:
                    callback(source_agent, kwargs or {})
        except Exception as e:
            logger.error(f"Callback error: {e}")
    
    def execute_programmatic(
        self,
        source_agent: 'Agent',
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> HandoffResult:
        """
        Execute handoff programmatically (not via LLM tool call).
        
        This is the unified programmatic handoff API that replaces Agent.delegate().
        
        Args:
            source_agent: The agent initiating the handoff
            prompt: The task/prompt to pass to target agent
            context: Optional additional context
            
        Returns:
            HandoffResult with response or error
        """
        start_time = time.time()
        kwargs = context or {}
        
        try:
            # Safety checks
            self._check_safety(source_agent)
            
            # Track handoff chain
            _push_handoff(source_agent.name)
            
            # Execute on_handoff callback
            self._execute_callback(self.config.on_handoff or self.on_handoff, source_agent, kwargs)
            
            # Prepare context (for future extensibility - context data available for hooks)
            _ = self._prepare_context(source_agent, kwargs)
            
            # Build prompt with context
            context_prefix = f"[Handoff from {source_agent.name}] "
            if kwargs:
                context_prefix += f"Context: {kwargs} "
            full_prompt = context_prefix + prompt
            
            logger.info(f"Programmatic handoff to {self.agent.name}")
            
            # Compute effective tools based on tool policy
            effective_tools = self._compute_effective_tools(source_agent)
            
            # Resolve runtime at turn-time instead of using construction-time pin
            response = self._execute_with_runtime_resolution(
                source_agent, full_prompt, effective_tools, kwargs
            )
            
            result = HandoffResult(
                success=True,
                response=str(response) if response else "",
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                handoff_depth=_get_handoff_depth(),
            )
            
            # Execute on_complete callback
            self._execute_callback(self.config.on_complete, source_agent, kwargs, result)
            
            # Call on_delegation hook on source agent's memory
            if (hasattr(source_agent, '_memory_instance') and 
                source_agent._memory_instance and
                hasattr(source_agent._memory_instance, 'on_delegation')):
                try:
                    source_agent._memory_instance.on_delegation(
                        task=full_prompt,
                        result=result.response or "",
                        agent_name=self.agent.name,
                        metadata={"handoff_depth": result.handoff_depth}
                    )
                except Exception as e:
                    logger.warning(f"[{source_agent.name}] Memory on_delegation hook failed: {e}")
            
            return result
            
        except (HandoffCycleError, HandoffDepthError, HandoffTimeoutError) as e:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=str(e),
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            raise
        except Exception as e:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=str(e),
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            logger.error(f"Handoff error: {e}")
            return result
        finally:
            _pop_handoff()
    
    async def execute_async(
        self,
        source_agent: 'Agent',
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> HandoffResult:
        """
        Execute handoff asynchronously with concurrency control.
        
        Args:
            source_agent: The agent initiating the handoff
            prompt: The task/prompt to pass to target agent
            context: Optional additional context
            
        Returns:
            HandoffResult with response or error
        """
        # Initialize semaphore if needed (thread-safe)
        if self.config.max_concurrent > 0 and Handoff._semaphore is None:
            with Handoff._semaphore_lock:  # Thread-safe initialization
                if Handoff._semaphore is None:  # Double-check after acquiring lock
                    Handoff._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        start_time = time.time()
        kwargs = context or {}
        
        async def _execute():
            try:
                # Safety checks
                self._check_safety(source_agent)
                _push_handoff(source_agent.name)
                
                # Execute callback
                self._execute_callback(self.config.on_handoff or self.on_handoff, source_agent, kwargs)
                
                # Prepare context (for future extensibility)
                _ = self._prepare_context(source_agent, kwargs)
                
                # Build prompt
                context_prefix = f"[Handoff from {source_agent.name}] "
                if kwargs:
                    context_prefix += f"Context: {kwargs} "
                full_prompt = context_prefix + prompt
                
                logger.info(f"Async handoff to {self.agent.name}")
                
                # Compute effective tools based on tool policy
                effective_tools = self._compute_effective_tools(source_agent)
                
                # Resolve runtime at turn-time for async execution
                response = await self._execute_with_runtime_resolution_async(
                    source_agent, full_prompt, effective_tools, kwargs
                )
                
                result = HandoffResult(
                    success=True,
                    response=str(response) if response else "",
                    target_agent=self.agent.name,
                    source_agent=source_agent.name,
                    duration_seconds=time.time() - start_time,
                    handoff_depth=_get_handoff_depth(),
                )
                
                # Call on_delegation hook on source agent's memory
                if (hasattr(source_agent, '_memory_instance') and 
                    source_agent._memory_instance and
                    hasattr(source_agent._memory_instance, 'on_delegation')):
                    try:
                        source_agent._memory_instance.on_delegation(
                            task=full_prompt,
                            result=result.response or "",
                            agent_name=self.agent.name,
                            metadata={"handoff_depth": result.handoff_depth}
                        )
                    except Exception as e:
                        logger.warning(f"[{source_agent.name}] Memory on_delegation hook failed: {e}")
                
                return result
            finally:
                _pop_handoff()
        
        try:
            if self.config.max_concurrent > 0 and Handoff._semaphore:
                async with Handoff._semaphore:
                    if self.config.timeout_seconds > 0:
                        result = await asyncio.wait_for(
                            _execute(),
                            timeout=self.config.timeout_seconds
                        )
                    else:
                        result = await _execute()
            else:
                if self.config.timeout_seconds > 0:
                    result = await asyncio.wait_for(
                        _execute(),
                        timeout=self.config.timeout_seconds
                    )
                else:
                    result = await _execute()
            
            self._execute_callback(self.config.on_complete, source_agent, kwargs, result)
            return result
            
        except asyncio.TimeoutError:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=f"Timeout after {self.config.timeout_seconds}s",
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            raise HandoffTimeoutError(
                f"Handoff to {self.agent.name} timed out after {self.config.timeout_seconds}s",
                timeout_seconds=self.config.timeout_seconds,
                source_agent=source_agent.name if hasattr(source_agent, "name") else "unknown",
                target_agent=self.agent.name,
                agent_id=source_agent.name if hasattr(source_agent, "name") else "unknown"
            )
        except Exception as e:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=str(e),
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            if isinstance(e, (HandoffCycleError, HandoffDepthError)):
                raise
            return result
    
    def to_tool_function(self, source_agent: 'Agent') -> Callable:
        """
        Convert this handoff to a tool function that can be called by the LLM.
        
        Args:
            source_agent: The agent that will be using this handoff
            
        Returns:
            A callable function that performs the handoff
        """
        def handoff_tool(**kwargs):
            """Execute the handoff to the target agent."""
            start_time = time.time()
            
            try:
                # Safety checks
                self._check_safety(source_agent)
                
                # Track handoff chain
                _push_handoff(source_agent.name)
                
                # Execute on_handoff callback
                self._execute_callback(self.config.on_handoff or self.on_handoff, source_agent, kwargs)
                
                # Prepare handoff data with context policy
                handoff_data = self._prepare_context(source_agent, kwargs)
                
                # Get the last user message or context to pass to target agent
                last_message = None
                for msg in reversed(handoff_data.messages):
                    if isinstance(msg, dict) and msg.get('role') == 'user':
                        last_message = msg.get('content', '')
                        break
                
                if not last_message and handoff_data.messages:
                    last_msg = handoff_data.messages[-1]
                    if isinstance(last_msg, dict):
                        last_message = last_msg.get('content', '')
                    else:
                        last_message = str(last_msg)
                
                # Prepare context information
                context_info = f"[Handoff from {source_agent.name}] "
                if kwargs and self.input_type:
                    context_info += f"Context: {kwargs} "
                
                # Execute the target agent with tool boundary enforcement
                if last_message:
                    prompt = context_info + last_message
                    logger.info(f"Handing off to {self.agent.name} with prompt: {prompt}")
                    
                    # Compute effective tools based on tool policy
                    effective_tools = self._compute_effective_tools(source_agent)
                    
                    # Resolve runtime at turn-time for tool function execution
                    response = self._execute_with_runtime_resolution(
                        source_agent, prompt, effective_tools, kwargs
                    )
                    
                    result = HandoffResult(
                        success=True,
                        response=str(response) if response else "",
                        target_agent=self.agent.name,
                        source_agent=source_agent.name,
                        duration_seconds=time.time() - start_time,
                        handoff_depth=_get_handoff_depth(),
                    )
                    self._execute_callback(self.config.on_complete, source_agent, kwargs, result)
                    
                    # Call on_delegation hook on source agent's memory
                    if (hasattr(source_agent, '_memory_instance') and 
                        source_agent._memory_instance and
                        hasattr(source_agent._memory_instance, 'on_delegation')):
                        try:
                            source_agent._memory_instance.on_delegation(
                                task=prompt,
                                result=result.response or "",
                                agent_name=self.agent.name,
                                metadata={"handoff_depth": result.handoff_depth}
                            )
                        except Exception as e:
                            logger.warning(f"[{source_agent.name}] Memory on_delegation hook failed: {e}")
                    
                    return f"Handoff successful. {self.agent.name} response: {response}"
                
                return f"Handoff to {self.agent.name} completed, but no specific task was provided."
                    
            except HandoffCycleError as e:
                logger.error(f"Handoff cycle detected: {e}")
                return f"Error: Handoff cycle detected - {e}"
            except HandoffDepthError as e:
                logger.error(f"Handoff depth exceeded: {e}")
                return f"Error: Maximum handoff depth exceeded - {e}"
            except Exception as e:
                logger.error(f"Error during handoff to {self.agent.name}: {str(e)}")
                result = HandoffResult(
                    success=False,
                    target_agent=self.agent.name,
                    source_agent=source_agent.name,
                    duration_seconds=time.time() - start_time,
                    error=str(e),
                )
                self._execute_callback(self.config.on_error, source_agent, kwargs, result)
                return f"Error during handoff to {self.agent.name}: {str(e)}"
            finally:
                _pop_handoff()
        
        # Set function metadata for tool definition generation
        handoff_tool.__name__ = self.tool_name
        handoff_tool.__doc__ = self.tool_description
        
        # Add input type annotations if provided
        if self.input_type and hasattr(self.input_type, '__annotations__'):
            sig_params = []
            for field_name, field_type in self.input_type.__annotations__.items():
                sig_params.append(
                    inspect.Parameter(
                        field_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=field_type
                    )
                )
            handoff_tool.__signature__ = inspect.Signature(sig_params)
        
        return handoff_tool

def handoff(
    agent: 'Agent',
    tool_name_override: Optional[str] = None,
    tool_description_override: Optional[str] = None,
    on_handoff: Optional[Callable] = None,
    input_type: Optional[type] = None,
    input_filter: Optional[Callable[[HandoffInputData], HandoffInputData]] = None,
    config: Optional[HandoffConfig] = None,
    # Convenience kwargs that map to HandoffConfig
    context_policy: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    max_concurrent: Optional[int] = None,
    detect_cycles: Optional[bool] = None,
    max_depth: Optional[int] = None,
    # Tool security boundary kwargs (NEW)
    tool_policy_mode: Optional[Literal["intersect", "passthrough"]] = None,
    blocked_tools: Optional[List[str]] = None,
) -> Handoff:
    """
    Create a handoff configuration for delegating tasks to another agent.
    
    This is a convenience function that creates a Handoff instance with the
    specified configuration. It supports both the legacy API and the new
    unified HandoffConfig with tool security boundary enforcement.
    
    Args:
        agent: The target agent to hand off to
        tool_name_override: Custom tool name (defaults to transfer_to_<agent_name>)
        tool_description_override: Custom tool description
        on_handoff: Callback function executed when handoff is invoked
        input_type: Type of input expected by the handoff (for structured data)
        input_filter: Function to filter/transform input before passing to target agent
        config: HandoffConfig for advanced settings
        context_policy: Shorthand for config.context_policy ("full", "summary", "none", "last_n")
        timeout_seconds: Shorthand for config.timeout_seconds
        max_concurrent: Shorthand for config.max_concurrent
        detect_cycles: Shorthand for config.detect_cycles
        max_depth: Shorthand for config.max_depth
        tool_policy_mode: Tool boundary mode ("intersect" = secure by default, "passthrough" = legacy)
        blocked_tools: List of tool names to always block regardless of intersection
        
    Returns:
        A configured Handoff instance
        
    Example:
        ```python
        from praisonaiagents import Agent, handoff, HandoffConfig, HandoffToolPolicy
        
        billing_agent = Agent(name="Billing Agent")
        refund_agent = Agent(name="Refund Agent") 
        
        # Simple usage (secure by default - tools intersected)
        triage_agent = Agent(
            name="Triage Agent",
            handoffs=[billing_agent, handoff(refund_agent)]
        )
        
        # With tool security config
        triage_agent = Agent(
            name="Triage Agent", 
            handoffs=[
                handoff(billing_agent, 
                        tool_policy_mode="intersect",  # Only shared tools
                        blocked_tools=["execute_code", "shell_tools"]),
                handoff(refund_agent,
                        config=HandoffConfig(
                            tool_policy=HandoffToolPolicy(
                                mode="passthrough",  # Legacy behavior
                                blocked_tools=["dangerous_tool"]
                            )
                        ))
            ]
        )
        ```
    """
    # Build config from kwargs if not provided
    if config is None:
        config = HandoffConfig()
    
    # Apply convenience kwargs to config
    if context_policy is not None:
        config.context_policy = ContextPolicy(context_policy)
    if timeout_seconds is not None:
        config.timeout_seconds = timeout_seconds
    if max_concurrent is not None:
        config.max_concurrent = max_concurrent
    if detect_cycles is not None:
        config.detect_cycles = detect_cycles
    if max_depth is not None:
        config.max_depth = max_depth
    
    # Apply tool policy kwargs to config
    if tool_policy_mode is not None or blocked_tools is not None:
        # Create new tool policy with updated values
        config.tool_policy = HandoffToolPolicy(
            mode=tool_policy_mode if tool_policy_mode is not None else config.tool_policy.mode,
            blocked_tools=blocked_tools if blocked_tools is not None else config.tool_policy.blocked_tools
        )
    
    return Handoff(
        agent=agent,
        tool_name_override=tool_name_override,
        tool_description_override=tool_description_override,
        on_handoff=on_handoff,
        input_type=input_type,
        input_filter=input_filter,
        config=config,
    )

# Handoff filters - common patterns for filtering handoff data
class handoff_filters:
    """Common handoff input filters."""
    
    @staticmethod
    def remove_all_tools(data: HandoffInputData) -> HandoffInputData:
        """Remove all tool calls from the message history."""
        filtered_messages = []
        for msg in data.messages:
            if isinstance(msg, dict) and (msg.get('tool_calls') or msg.get('role') == 'tool'):
                # Skip messages with tool calls
                continue
            filtered_messages.append(msg)
        
        data.messages = filtered_messages
        return data
    
    @staticmethod
    def keep_last_n_messages(n: int) -> Callable[[HandoffInputData], HandoffInputData]:
        """Keep only the last n messages in the history."""
        def filter_func(data: HandoffInputData) -> HandoffInputData:
            data.messages = data.messages[-n:]
            return data
        return filter_func
    
    @staticmethod
    def remove_system_messages(data: HandoffInputData) -> HandoffInputData:
        """Remove all system messages from the history."""
        filtered_messages = []
        for msg in data.messages:
            if (isinstance(msg, dict) and msg.get('role') != 'system') or not isinstance(msg, dict):
                filtered_messages.append(msg)
        
        data.messages = filtered_messages
        return data
    
    @staticmethod
    def compress_history(data: HandoffInputData) -> HandoffInputData:
        """Compress all messages into a single summary message.
        
        This filter concatenates all message contents into one user message,
        reducing token usage while preserving context. Useful for handoffs
        where the target agent needs context but not full conversation history.
        
        Example:
            Handoff(agent=target, input_filter=handoff_filters.compress_history)
        """
        if not data.messages:
            return data
        
        summary_parts = []
        for msg in data.messages:
            if isinstance(msg, dict):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                if content:
                    summary_parts.append(f"[{role}]: {content}")
        
        if summary_parts:
            summary = "\n".join(summary_parts)
            data.messages = [{"role": "user", "content": f"Previous conversation summary:\n{summary}"}]
        else:
            data.messages = []
        
        return data

# Recommended prompt prefix for agents that use handoffs
RECOMMENDED_PROMPT_PREFIX = """You have the ability to transfer tasks to specialized agents when appropriate. 
When you determine that a task would be better handled by another agent with specific expertise, 
use the transfer tool to hand off the task. The receiving agent will have the full context of 
the conversation and will continue helping the user."""

async def parallel_handoffs(
    source: 'Agent',
    targets: List[tuple],  # [(agent, prompt), ...]
    max_concurrent: int = 5,
    config: Optional[HandoffConfig] = None,
) -> List['HandoffResult']:
    """
    Execute multiple handoffs in parallel with concurrency control.
    
    This function provides the parallel execution capabilities from SubagentDelegator
    while using the unified Handoff system.
    
    Args:
        source: Source agent performing the handoffs
        targets: List of (agent, prompt) tuples for parallel execution
        max_concurrent: Maximum concurrent handoffs (overrides config)
        config: Optional HandoffConfig for additional settings
        
    Returns:
        List of HandoffResult objects from each parallel handoff
        
    Example:
        results = await parallel_handoffs(
            source=main_agent,
            targets=[
                (research_agent, "Research topic X"),
                (analysis_agent, "Analyze data Y"),
                (summary_agent, "Summarize findings Z")
            ],
            max_concurrent=3
        )
    """
    if not hasattr(source, 'handoff_to_async'):
        raise ValueError("Source agent must support async handoffs")
    
    # Check if parallel execution is allowed by config
    if config and not config.allow_parallel:
        raise ValueError("Parallel handoffs are disabled in the provided HandoffConfig")
    
    # Use config's max_concurrent if max_concurrent wasn't explicitly set and config is provided
    if config and max_concurrent == 5:  # Check if default value
        effective_max_concurrent = config.max_concurrent
    else:
        effective_max_concurrent = max_concurrent
    
    # Create semaphore for concurrency control (0 or negative = unlimited)
    semaphore = asyncio.Semaphore(effective_max_concurrent) if effective_max_concurrent > 0 else None
    
    async def _run_one(agent, prompt):
        async def _do_handoff():
            try:
                return await source.handoff_to_async(agent, prompt, config=config)
            except Exception as e:
                logger.error(f"Parallel handoff failed to {getattr(agent, 'name', str(agent))}: {e}")
                # Return a failed HandoffResult object
                return HandoffResult(
                    success=False,
                    response="",
                    target_agent=getattr(agent, 'name', str(agent)),
                    source_agent=getattr(source, 'name', str(source)),
                    duration_seconds=0.0,
                    error=str(e),
                    handoff_depth=0
                )
        
        if semaphore:
            async with semaphore:
                return await _do_handoff()
        else:
            return await _do_handoff()
    
    # Execute all handoffs concurrently
    tasks = [_run_one(agent, prompt) for agent, prompt in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert any exceptions to failed results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, HandoffResult):
            processed_results.append(result)
        else:
            # Handle Exception, BaseException (like CancelledError), or any other unexpected result
            agent, _prompt = targets[i]  # Prefix with _ to mark intentionally unused
            processed_results.append(HandoffResult(
                success=False,
                response="",
                target_agent=getattr(agent, 'name', str(agent)),
                source_agent=getattr(source, 'name', str(source)),
                duration_seconds=0.0,
                error=str(result),
                handoff_depth=0
            ))
    
    return processed_results


# Type variable for generic typed handoff
T = TypeVar("T", bound=BaseModel)


class TypedHandoff(Handoff, Generic[T]):
    """
    Typed handoff with schema validation using Pydantic models.
    
    This class extends the base Handoff to add type safety through Pydantic schema validation.
    The sender declares an output schema, the receiver expects that schema, and the framework
    validates the payload at the boundary, raising HandoffValidationError if validation fails.
    
    The receiving agent's prompt is constructed from validated JSON rather than raw string
    concatenation, enabling proper deserialization of structured data.
    
    Example:
        ```python
        from pydantic import BaseModel
        from praisonaiagents.agent.handoff import TypedHandoff, HandoffValidationError
        
        class ResearchResult(BaseModel):
            summary: str
            citations: list[str] 
            confidence: float
            
        # Create typed handoff
        typed_handoff = TypedHandoff(
            agent=writer_agent,
            input_schema=ResearchResult
        )
        
        # Valid payload
        result = ResearchResult(
            summary="AI research findings", 
            citations=["ref1", "ref2"], 
            confidence=0.92
        )
        response = typed_handoff.execute_programmatic(source_agent, result)
        
        # Invalid payload raises HandoffValidationError
        bad_payload = {"summary": "...", "citations": "not-a-list"}
        typed_handoff.execute_programmatic(source_agent, bad_payload)  # Raises error
        ```
    """
    
    def __init__(
        self,
        agent: 'Agent',
        input_schema: Type[T],
        tool_name_override: Optional[str] = None,
        tool_description_override: Optional[str] = None,
        on_handoff: Optional[Callable] = None,
        input_filter: Optional[Union[Callable[[HandoffInputData], HandoffInputData], List[Callable[[HandoffInputData], HandoffInputData]]]] = None,
        config: Optional[HandoffConfig] = None,
    ):
        """
        Initialize a TypedHandoff with schema validation.
        
        Args:
            agent: The target agent to hand off to
            input_schema: Pydantic model class for payload validation
            tool_name_override: Custom tool name (defaults to transfer_to_<agent_name>)
            tool_description_override: Custom tool description
            on_handoff: Callback function executed when handoff is invoked
            input_filter: Function or list of functions to filter/transform input
            config: HandoffConfig for advanced settings (context policy, timeouts, etc.)
            
        Raises:
            ImportError: If Pydantic is not available
            TypeError: If input_schema is not a Pydantic model
        """
        if not PYDANTIC_AVAILABLE:
            raise ImportError(
                "Pydantic is required for TypedHandoff. Install with: pip install pydantic"
            )
            
        if not (inspect.isclass(input_schema) and issubclass(input_schema, BaseModel)):
            raise TypeError(
                f"input_schema must be a Pydantic BaseModel class, got {type(input_schema)}"
            )
        
        super().__init__(
            agent=agent,
            tool_name_override=tool_name_override,
            tool_description_override=tool_description_override,
            on_handoff=on_handoff,
            input_type=None,  # We handle typing ourselves
            input_filter=input_filter,
            config=config,
        )
        self._input_schema = input_schema
    
    def _validate_payload(self, payload: Union[T, dict, Any]) -> T:
        """
        Validate payload against the input schema.
        
        Args:
            payload: The payload to validate - can be a Pydantic model instance,
                    dict, or any object with model_dump() method
                    
        Returns:
            Validated Pydantic model instance
            
        Raises:
            HandoffValidationError: If validation fails
        """
        try:
            if isinstance(payload, self._input_schema):
                # Already the correct type, validate by re-parsing
                validated = self._input_schema.model_validate(payload.model_dump())
            elif isinstance(payload, dict):
                # Dictionary - validate directly
                validated = self._input_schema.model_validate(payload)
            elif hasattr(payload, 'model_dump'):
                # Another Pydantic model - convert via dict
                validated = self._input_schema.model_validate(payload.model_dump())
            else:
                # Try to convert to dict first
                if hasattr(payload, '__dict__'):
                    payload_dict = payload.__dict__
                else:
                    payload_dict = dict(payload) if hasattr(payload, '__iter__') else {}
                validated = self._input_schema.model_validate(payload_dict)
                
            return validated
            
        except PydanticValidationError as exc:
            validation_errors = [
                f"{err['loc']}: {err['msg']}" for err in exc.errors()
            ] if hasattr(exc, 'errors') else [str(exc)]
            
            raise HandoffValidationError(
                f"Handoff to '{self.agent.name}' received an invalid payload: {exc}",
                source_agent="unknown",
                target_agent=self.agent.name,
                agent_id="unknown",
                validation_errors=validation_errors
            ) from exc
        except Exception as exc:
            raise HandoffValidationError(
                f"Handoff to '{self.agent.name}' failed to validate payload: {exc}",
                source_agent="unknown", 
                target_agent=self.agent.name,
                agent_id="unknown"
            ) from exc
    
    def execute_programmatic(
        self,
        source_agent: 'Agent',
        payload: Union[T, dict, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> HandoffResult:
        """
        Execute typed handoff programmatically with schema validation.
        
        Args:
            source_agent: The agent initiating the handoff
            payload: The typed payload (Pydantic model instance or dict) OR
                    a string prompt (for backward compatibility)
            context: Optional additional context
            
        Returns:
            HandoffResult with response or error
            
        Raises:
            HandoffValidationError: If payload validation fails
        """
        # Handle backward compatibility: if payload is a string, treat as regular handoff
        if isinstance(payload, str):
            return super().execute_programmatic(source_agent, payload, context)
        
        start_time = time.time()
        kwargs = context or {}
        
        try:
            # Safety checks
            self._check_safety(source_agent)
            
            # Track handoff chain
            _push_handoff(source_agent.name)
            
            # Execute on_handoff callback
            self._execute_callback(self.config.on_handoff or self.on_handoff, source_agent, kwargs)
            
            # Apply input filter if provided (fixes Greptile P1 issue)
            _ = self._prepare_context(source_agent, kwargs)
            
            # Validate payload against schema
            try:
                validated_payload = self._validate_payload(payload)
            except HandoffValidationError as e:
                # Update error context with proper agent info (fixes Greptile P2 issue)
                e.source_agent = source_agent.name
                e.agent_id = source_agent.name
                e.context["source_agent"] = source_agent.name
                e.context["agent_id"] = source_agent.name
                raise
            
            # Convert validated payload to structured JSON for the prompt
            payload_json = validated_payload.model_dump_json(indent=2)
            
            # Build prompt with structured JSON instead of string concatenation
            context_prefix = f"[Handoff from {source_agent.name}] "
            if kwargs:
                context_prefix += f"Additional context: {json.dumps(kwargs, indent=2)}\n"
            
            # The key improvement: structured JSON instead of str() concatenation
            full_prompt = f"{context_prefix}Payload:\n{payload_json}"
            
            logger.info(f"Typed handoff to {self.agent.name} with validated payload")
            
            # Execute with timeout if sync
            response = self.agent.chat(full_prompt)
            
            result = HandoffResult(
                success=True,
                response=str(response) if response else "",
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                handoff_depth=_get_handoff_depth(),
            )
            
            # Execute on_complete callback
            self._execute_callback(self.config.on_complete, source_agent, kwargs, result)
            
            return result
            
        except (HandoffCycleError, HandoffDepthError, HandoffTimeoutError, HandoffValidationError) as e:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=str(e),
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            raise
        except Exception as e:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=str(e),
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            logger.error(f"Typed handoff error: {e}")
            return result
        finally:
            _pop_handoff()
    
    async def execute_async(
        self,
        source_agent: 'Agent',
        payload: Union[T, dict, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> HandoffResult:
        """
        Execute typed handoff asynchronously with schema validation.
        
        Args:
            source_agent: The agent initiating the handoff
            payload: The typed payload (Pydantic model instance or dict) OR
                    a string prompt (for backward compatibility)
            context: Optional additional context
            
        Returns:
            HandoffResult with response or error
            
        Raises:
            HandoffValidationError: If payload validation fails
        """
        # Handle backward compatibility: if payload is a string, treat as regular handoff
        if isinstance(payload, str):
            return await super().execute_async(source_agent, payload, context)
        
        # Initialize semaphore if needed (thread-safe)
        if self.config.max_concurrent > 0 and Handoff._semaphore is None:
            with Handoff._semaphore_lock:
                if Handoff._semaphore is None:
                    Handoff._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        start_time = time.time()
        kwargs = context or {}
        
        async def _execute():
            try:
                # Safety checks
                self._check_safety(source_agent)
                _push_handoff(source_agent.name)
                
                # Execute callback
                self._execute_callback(self.config.on_handoff or self.on_handoff, source_agent, kwargs)
                
                # Apply input filter if provided (fixes Greptile P1 issue)
                _ = self._prepare_context(source_agent, kwargs)
                
                # Validate payload against schema
                try:
                    validated_payload = self._validate_payload(payload)
                except HandoffValidationError as e:
                    # Update error context with proper agent info (fixes Greptile P2 issue)
                    e.source_agent = source_agent.name
                    e.agent_id = source_agent.name
                    e.context["source_agent"] = source_agent.name
                    e.context["agent_id"] = source_agent.name
                    raise
                
                # Convert to structured JSON
                payload_json = validated_payload.model_dump_json(indent=2)
                
                # Build prompt
                context_prefix = f"[Handoff from {source_agent.name}] "
                if kwargs:
                    context_prefix += f"Additional context: {json.dumps(kwargs, indent=2)}\n"
                
                full_prompt = f"{context_prefix}Payload:\n{payload_json}"
                
                logger.info(f"Async typed handoff to {self.agent.name}")
                
                # Execute - check for async chat method
                if hasattr(self.agent, 'achat'):
                    response = await self.agent.achat(full_prompt)
                else:
                    # Run sync chat in executor
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, self.agent.chat, full_prompt)
                
                return HandoffResult(
                    success=True,
                    response=str(response) if response else "",
                    target_agent=self.agent.name,
                    source_agent=source_agent.name,
                    duration_seconds=time.time() - start_time,
                    handoff_depth=_get_handoff_depth(),
                )
            finally:
                _pop_handoff()
        
        try:
            if self.config.max_concurrent > 0 and Handoff._semaphore:
                async with Handoff._semaphore:
                    if self.config.timeout_seconds > 0:
                        result = await asyncio.wait_for(
                            _execute(),
                            timeout=self.config.timeout_seconds
                        )
                    else:
                        result = await _execute()
            else:
                if self.config.timeout_seconds > 0:
                    result = await asyncio.wait_for(
                        _execute(),
                        timeout=self.config.timeout_seconds
                    )
                else:
                    result = await _execute()
            
            self._execute_callback(self.config.on_complete, source_agent, kwargs, result)
            return result
            
        except asyncio.TimeoutError as err:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=f"Timeout after {self.config.timeout_seconds}s",
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            raise HandoffTimeoutError(
                f"Typed handoff to {self.agent.name} timed out after {self.config.timeout_seconds}s",
                timeout_seconds=self.config.timeout_seconds,
                source_agent=source_agent.name,
                target_agent=self.agent.name,
                agent_id=source_agent.name
            ) from err
        except Exception as e:
            result = HandoffResult(
                success=False,
                target_agent=self.agent.name,
                source_agent=source_agent.name,
                duration_seconds=time.time() - start_time,
                error=str(e),
                handoff_depth=_get_handoff_depth(),
            )
            self._execute_callback(self.config.on_error, source_agent, kwargs, result)
            if isinstance(e, (HandoffCycleError, HandoffDepthError, HandoffValidationError)):
                raise
            return result


def prompt_with_handoff_instructions(base_prompt: str, agent: 'Agent') -> str:
    """
    Add handoff instructions to an agent's prompt.
    
    Args:
        base_prompt: The original prompt/instructions
        agent: The agent that will use handoffs
        
    Returns:
        Updated prompt with handoff instructions
    """
    if not hasattr(agent, 'handoffs') or not agent.handoffs:
        return base_prompt
    
    handoff_info = "\n\nAvailable handoff agents:\n"
    for h in agent.handoffs:
        if isinstance(h, Handoff):
            handoff_info += f"- {h.agent.name}: {h.tool_description}\n"
        else:
            # Direct agent reference - create a temporary Handoff to get the default description
            temp_handoff = Handoff(agent=h)
            handoff_info += f"- {h.name}: {temp_handoff.tool_description}\n"
    
    return RECOMMENDED_PROMPT_PREFIX + handoff_info + "\n\n" + base_prompt