"""
Handoff functionality for agent-to-agent delegation.

This module provides handoff capabilities that allow agents to delegate tasks
to other agents, similar to the OpenAI Agents SDK implementation.

Unified Handoff System:
- Handoff: LLM-driven (tool call) or programmatic agent-to-agent transfer
- HandoffConfig: Configuration for context policy, timeouts, concurrency, safety
- Replaces/absorbs Agent.delegate() and SubagentDelegator functionality
"""

from typing import Optional, Any, Callable, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
import inspect
import logging
import asyncio
import threading
import time

if TYPE_CHECKING:
    from .agent import Agent

logger = logging.getLogger(__name__)


class ContextPolicy(Enum):
    """Policy for context sharing during handoff."""
    FULL = "full"       # Share full conversation history
    SUMMARY = "summary" # Share summarized context (default - safe)
    NONE = "none"       # No context sharing
    LAST_N = "last_n"   # Share last N messages


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
        timeout_seconds: Timeout for handoff execution
        max_concurrent: Maximum concurrent handoffs (0 = unlimited)
        detect_cycles: Enable cycle detection to prevent infinite loops
        max_depth: Maximum handoff chain depth
        async_mode: Enable async execution
        on_handoff: Callback when handoff starts
        on_complete: Callback when handoff completes
        on_error: Callback when handoff fails
    """
    # Context control
    context_policy: ContextPolicy = ContextPolicy.SUMMARY
    max_context_tokens: int = 4000
    max_context_messages: int = 10
    preserve_system: bool = True
    
    # Execution control
    timeout_seconds: float = 300.0
    max_concurrent: int = 3
    
    # Safety
    detect_cycles: bool = True
    max_depth: int = 10
    
    # Execution mode
    async_mode: bool = False
    
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
            "timeout_seconds": self.timeout_seconds,
            "max_concurrent": self.max_concurrent,
            "detect_cycles": self.detect_cycles,
            "max_depth": self.max_depth,
            "async_mode": self.async_mode,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HandoffConfig':
        """Create config from dictionary."""
        if "context_policy" in data and isinstance(data["context_policy"], str):
            data["context_policy"] = ContextPolicy(data["context_policy"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class HandoffError(Exception):
    """Base exception for handoff errors."""
    pass


class HandoffCycleError(HandoffError):
    """Raised when a cycle is detected in handoff chain."""
    def __init__(self, chain: List[str]):
        self.chain = chain
        super().__init__(f"Handoff cycle detected: {' -> '.join(chain)}")


class HandoffDepthError(HandoffError):
    """Raised when max handoff depth is exceeded."""
    def __init__(self, depth: int, max_depth: int):
        self.depth = depth
        self.max_depth = max_depth
        super().__init__(f"Max handoff depth exceeded: {depth} > {max_depth}")


class HandoffTimeoutError(HandoffError):
    """Raised when handoff times out."""
    def __init__(self, timeout: float, agent_name: str):
        self.timeout = timeout
        self.agent_name = agent_name
        super().__init__(f"Handoff to {agent_name} timed out after {timeout}s")


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
    """Result of a handoff operation."""
    success: bool
    response: Optional[str] = None
    target_agent: Optional[str] = None
    source_agent: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    handoff_depth: int = 0
    
    
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
    
    def __init__(
        self,
        agent: 'Agent',
        tool_name_override: Optional[str] = None,
        tool_description_override: Optional[str] = None,
        on_handoff: Optional[Callable] = None,
        input_type: Optional[type] = None,
        input_filter: Optional[Callable[[HandoffInputData], HandoffInputData]] = None,
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
            input_filter: Function to filter/transform input before passing to target agent
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
                raise HandoffCycleError(chain + [target_name])
        
        # Check depth
        current_depth = _get_handoff_depth()
        if current_depth >= self.config.max_depth:
            raise HandoffDepthError(current_depth + 1, self.config.max_depth)
    
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
        
        # Apply custom input filter if provided
        if self.input_filter:
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
        # Initialize semaphore if needed
        if self.config.max_concurrent > 0 and Handoff._semaphore is None:
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
            raise HandoffTimeoutError(self.config.timeout_seconds, self.agent.name)
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
                
                # Execute the target agent
                if last_message:
                    prompt = context_info + last_message
                    logger.info(f"Handing off to {self.agent.name} with prompt: {prompt}")
                    response = self.agent.chat(prompt)
                    
                    result = HandoffResult(
                        success=True,
                        response=str(response) if response else "",
                        target_agent=self.agent.name,
                        source_agent=source_agent.name,
                        duration_seconds=time.time() - start_time,
                        handoff_depth=_get_handoff_depth(),
                    )
                    self._execute_callback(self.config.on_complete, source_agent, kwargs, result)
                    
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
) -> Handoff:
    """
    Create a handoff configuration for delegating tasks to another agent.
    
    This is a convenience function that creates a Handoff instance with the
    specified configuration. It supports both the legacy API and the new
    unified HandoffConfig.
    
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
        
    Returns:
        A configured Handoff instance
        
    Example:
        ```python
        from praisonaiagents import Agent, handoff, HandoffConfig
        
        billing_agent = Agent(name="Billing Agent")
        refund_agent = Agent(name="Refund Agent")
        
        # Simple usage
        triage_agent = Agent(
            name="Triage Agent",
            handoffs=[billing_agent, handoff(refund_agent)]
        )
        
        # With config
        triage_agent = Agent(
            name="Triage Agent",
            handoffs=[
                handoff(billing_agent, context_policy="summary", timeout_seconds=60),
                handoff(refund_agent, config=HandoffConfig(detect_cycles=True))
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


# Recommended prompt prefix for agents that use handoffs
RECOMMENDED_PROMPT_PREFIX = """You have the ability to transfer tasks to specialized agents when appropriate. 
When you determine that a task would be better handled by another agent with specific expertise, 
use the transfer tool to hand off the task. The receiving agent will have the full context of 
the conversation and will continue helping the user."""


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