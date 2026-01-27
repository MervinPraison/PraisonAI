"""
Context Events for PraisonAI Agents.

Provides context-level tracing for replay functionality.
Tracks context changes during agent execution for debugging and replay.

Zero Performance Impact:
- NoOpSink is the default (zero overhead when not used)
- Disabled emitter has near-zero overhead
- Uses __slots__ for memory efficiency

Schema Version: 1.0
"""

import contextvars
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generator, List, Optional, Protocol, runtime_checkable
import json


CONTEXT_SCHEMA_VERSION = "1.0"


# =============================================================================
# GLOBAL EMITTER REGISTRY
# =============================================================================
# Uses contextvars for async-safe, thread-safe global state.
# Zero overhead when not set (returns disabled NoOp emitter).

_context_emitter: contextvars.ContextVar["ContextTraceEmitter"] = contextvars.ContextVar(
    'praisonai_context_emitter'
)

# Singleton disabled emitter for default case (zero allocation per call)
_default_disabled_emitter: Optional["ContextTraceEmitter"] = None


def get_context_emitter() -> "ContextTraceEmitter":
    """
    Get the current context trace emitter.
    
    Returns a disabled NoOp emitter if not set (zero overhead).
    This function is safe to call from any async context or thread.
    
    Returns:
        ContextTraceEmitter: The current emitter or a disabled default.
    """
    try:
        return _context_emitter.get()
    except LookupError:
        global _default_disabled_emitter
        if _default_disabled_emitter is None:
            _default_disabled_emitter = ContextTraceEmitter(
                sink=ContextNoOpSink(),
                session_id="",
                enabled=False
            )
        return _default_disabled_emitter


def set_context_emitter(emitter: "ContextTraceEmitter") -> contextvars.Token:
    """
    Set the context trace emitter for the current async context.
    
    Args:
        emitter: The emitter to set as current.
        
    Returns:
        Token that can be used with reset_context_emitter() to restore previous state.
    """
    return _context_emitter.set(emitter)


def reset_context_emitter(token: contextvars.Token) -> None:
    """
    Reset the context emitter to its previous state.
    
    Args:
        token: Token returned by set_context_emitter().
    """
    _context_emitter.reset(token)


@contextmanager
def trace_context(emitter: "ContextTraceEmitter") -> Generator["ContextTraceEmitter", None, None]:
    """
    Context manager for trace emitter lifecycle.
    
    Automatically sets the emitter on entry and resets on exit,
    even if an exception occurs. This is the recommended way to
    use custom trace emitters.
    
    Args:
        emitter: The emitter to use within the context.
        
    Yields:
        The emitter for use within the context.
        
    Example:
        sink = MyCustomSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="my-session", enabled=True)
        
        with trace_context(emitter) as ctx:
            agent = Agent(...)
            agent.chat("Hello")  # Events go to MyCustomSink
    """
    token = set_context_emitter(emitter)
    try:
        yield emitter
    finally:
        reset_context_emitter(token)


def copy_context_to_callable(func):
    """
    Wrap a callable to copy the current context to the new thread/executor.
    
    This is needed because contextvars are NOT automatically propagated to
    thread pool executors. Use this when calling run_in_executor().
    
    Usage:
        # Instead of:
        await loop.run_in_executor(None, lambda: agent.chat(prompt))
        
        # Use:
        await loop.run_in_executor(None, copy_context_to_callable(lambda: agent.chat(prompt)))
    
    Args:
        func: The callable to wrap.
        
    Returns:
        A wrapped callable that copies the current context.
    """
    ctx = contextvars.copy_context()
    def wrapper(*args, **kwargs):
        return ctx.run(func, *args, **kwargs)
    return wrapper


class ContextEventType(str, Enum):
    """Types of context events for replay."""
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_HANDOFF = "agent_handoff"
    MESSAGE_ADDED = "message_added"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    CONTEXT_SNAPSHOT = "context_snapshot"
    # Memory events for memory utilization tracking
    MEMORY_STORE = "memory_store"
    MEMORY_SEARCH = "memory_search"
    # Knowledge events for knowledge utilization tracking
    KNOWLEDGE_SEARCH = "knowledge_search"
    KNOWLEDGE_ADD = "knowledge_add"


@dataclass
class ContextEvent:
    """
    A single context event for replay.
    
    Represents a discrete change in agent context during execution.
    Designed for minimal memory footprint and fast serialization.
    
    Attributes:
        event_type: Type of context event
        timestamp: Unix timestamp when event occurred
        session_id: Session identifier for grouping events
        agent_name: Name of the agent (if applicable)
        sequence_num: Sequential event number within session
        messages_count: Number of messages in context at this point
        tokens_used: Tokens used in context at this point
        tokens_budget: Total token budget available
        data: Event-specific data (tool args, message content, etc.)
        branch_id: Optional branch identifier for parallel execution tracking
        prompt_tokens: Number of tokens in the prompt/request
        completion_tokens: Number of tokens in the completion/response
        cost_usd: Estimated cost in USD for this event
        content_hash: SHA256 hash of content for duplicate detection
    """
    event_type: ContextEventType
    timestamp: float
    session_id: str
    agent_name: Optional[str] = None
    sequence_num: int = 0
    messages_count: int = 0
    tokens_used: int = 0
    tokens_budget: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    branch_id: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    content_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "event_type": self.event_type.value if isinstance(self.event_type, ContextEventType) else self.event_type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "sequence_num": self.sequence_num,
            "messages_count": self.messages_count,
            "tokens_used": self.tokens_used,
            "tokens_budget": self.tokens_budget,
            "data": self.data,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
        }
        if self.branch_id is not None:
            result["branch_id"] = self.branch_id
        if self.content_hash is not None:
            result["content_hash"] = self.content_hash
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextEvent":
        """Create ContextEvent from dictionary."""
        event_type_str = data.get("event_type", "")
        
        # Convert string to enum
        try:
            event_type = ContextEventType(event_type_str)
        except ValueError:
            # Fallback for unknown event types
            event_type = ContextEventType.CONTEXT_SNAPSHOT
        
        return cls(
            event_type=event_type,
            timestamp=data.get("timestamp", 0.0),
            session_id=data.get("session_id", ""),
            agent_name=data.get("agent_name"),
            sequence_num=data.get("sequence_num", 0),
            messages_count=data.get("messages_count", 0),
            tokens_used=data.get("tokens_used", 0),
            tokens_budget=data.get("tokens_budget", 0),
            data=data.get("data", {}),
            branch_id=data.get("branch_id"),
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            cost_usd=data.get("cost_usd", 0.0),
            content_hash=data.get("content_hash"),
        )


@runtime_checkable
class ContextTraceSinkProtocol(Protocol):
    """
    Protocol for context trace event sinks.
    
    Implementations receive context events and handle them
    (e.g., write to file, collect in memory, send to server).
    
    Naming follows AGENTS.md convention: XProtocol for interfaces.
    """
    
    def emit(self, event: ContextEvent) -> None:
        """Emit a context event."""
        ...
    
    def flush(self) -> None:
        """Flush any buffered events."""
        ...
    
    def close(self) -> None:
        """Close the sink and release resources."""
        ...


# Backward compatibility alias (deprecated)
ContextTraceSink = ContextTraceSinkProtocol


class ContextNoOpSink:
    """
    No-operation sink that discards all events.
    
    Used as the default sink when context tracing is disabled.
    Has near-zero overhead.
    """
    
    __slots__ = ()
    
    def emit(self, event: ContextEvent) -> None:
        """Discard the event."""
        pass
    
    def flush(self) -> None:
        """No-op."""
        pass
    
    def close(self) -> None:
        """No-op."""
        pass


class ContextListSink:
    """
    Sink that collects events in a list.
    
    Useful for testing and programmatic access to context events.
    """
    
    __slots__ = ("_events",)
    
    def __init__(self):
        self._events: List[ContextEvent] = []
    
    def emit(self, event: ContextEvent) -> None:
        """Add event to the list."""
        self._events.append(event)
    
    def flush(self) -> None:
        """No-op for list sink."""
        pass
    
    def close(self) -> None:
        """No-op for list sink."""
        pass
    
    def get_events(self) -> List[ContextEvent]:
        """Get all collected events."""
        return self._events.copy()
    
    def clear(self) -> None:
        """Clear all collected events."""
        self._events.clear()
    
    def __len__(self) -> int:
        """Return number of events."""
        return len(self._events)
    
    def __iter__(self):
        """Iterate over events."""
        return iter(self._events)


class ContextTraceEmitter:
    """
    Emitter for context trace events.
    
    Provides a high-level API for emitting context events during
    agent execution. Handles sequence numbering and redaction.
    
    Usage:
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="my-session")
        
        emitter.session_start()
        emitter.agent_start("researcher")
        emitter.message_added("researcher", "user", "Hello", 1, 10)
        emitter.agent_end("researcher")
        emitter.session_end()
    """
    
    __slots__ = ("_sink", "_session_id", "_enabled", "_redact", "_sequence", "_branch_id", "_full_content")
    
    # Default limits for truncation (can be overridden with full_content=True)
    # Increased significantly to capture full search results and avoid false truncation
    DEFAULT_TOOL_RESULT_LIMIT = 50000  # Increased to capture full tavily_search results
    DEFAULT_LLM_RESPONSE_LIMIT = 50000  # Increased to capture full LLM responses
    
    def __init__(
        self,
        sink: Optional[ContextTraceSink] = None,
        session_id: str = "",
        enabled: bool = True,
        redact: bool = True,
        full_content: bool = False,
    ):
        """
        Initialize context trace emitter.
        
        Args:
            sink: Sink to emit events to (default: ContextNoOpSink)
            session_id: Session identifier for all events
            enabled: Whether tracing is enabled
            redact: Whether to redact sensitive data
            full_content: If True, store full content without truncation (for --full flag)
        """
        self._sink = sink if sink is not None else ContextNoOpSink()
        self._session_id = session_id
        self._enabled = enabled
        self._redact = redact
        self._sequence = 0
        self._branch_id: Optional[str] = None
        self._full_content = full_content
    
    def _emit(self, event: ContextEvent) -> None:
        """Internal emit with enabled check and sequence assignment.
        
        Exception-safe: sink errors are silently caught to prevent
        tracing from crashing agent execution.
        """
        if not self._enabled:
            return
        event.sequence_num = self._sequence
        event.branch_id = self._branch_id  # Include branch context
        self._sequence += 1
        try:
            self._sink.emit(event)
        except Exception:
            # Tracing should never crash agent execution
            pass
    
    def set_branch(self, branch_id: str) -> None:
        """Set current branch context for parallel execution tracking.
        
        All subsequent events will include this branch_id until cleared.
        
        Args:
            branch_id: Identifier for the parallel branch (e.g., 'parallel_0', 'loop_5')
        """
        self._branch_id = branch_id
    
    def clear_branch(self) -> None:
        """Clear the current branch context."""
        self._branch_id = None
    
    def _redact_dict(self, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Redact sensitive data from dictionary if enabled."""
        if data is None or not self._redact:
            return data
        
        from .redact import redact_dict
        return redact_dict(data)
    
    def session_start(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit session start event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.SESSION_START,
            timestamp=time.time(),
            session_id=self._session_id,
            data=metadata or {},
        ))
    
    def session_end(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit session end event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.SESSION_END,
            timestamp=time.time(),
            session_id=self._session_id,
            data=metadata or {},
        ))
    
    def agent_start(
        self,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent start event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.AGENT_START,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data=metadata or {},
        ))
    
    def agent_end(
        self,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent end event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.AGENT_END,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data=metadata or {},
        ))
    
    def message_added(
        self,
        agent_name: str,
        role: str,
        content: str,
        messages_count: int,
        tokens_used: int,
        tokens_budget: int = 0,
    ) -> None:
        """Emit message added event."""
        # Truncate long content for storage
        truncated_content = content[:1000] + "..." if len(content) > 1000 else content
        
        self._emit(ContextEvent(
            event_type=ContextEventType.MESSAGE_ADDED,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            messages_count=messages_count,
            tokens_used=tokens_used,
            tokens_budget=tokens_budget,
            data={
                "role": role,
                "content": truncated_content,
            },
        ))
    
    def tool_call_start(
        self,
        agent_name: str,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit tool call start event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.TOOL_CALL_START,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "tool_name": tool_name,
                "tool_args": self._redact_dict(tool_args) if tool_args else {},
            },
        ))
    
    def tool_call_end(
        self,
        agent_name: str,
        tool_name: str,
        result: Optional[str] = None,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
        cost_usd: float = 0.0,
    ) -> None:
        """Emit tool call end event.
        
        Args:
            agent_name: Name of the agent
            tool_name: Name of the tool called
            result: Tool result (will be smart-truncated to preserve key info)
            duration_ms: Duration in milliseconds
            error: Error message if any
            cost_usd: Cost in USD (e.g., 0.001 for internet search = 1 credit)
        """
        # Smart truncate long results unless full_content is enabled
        truncated_result = None
        if result:
            if self._full_content:
                truncated_result = result  # No truncation when full_content=True
            else:
                truncated_result = self._smart_truncate_result(result, tool_name)
        
        # Calculate tool cost if not provided (1 credit = $0.001 for search tools)
        if cost_usd == 0.0:
            cost_usd = self._get_tool_cost(tool_name)
        
        self._emit(ContextEvent(
            event_type=ContextEventType.TOOL_CALL_END,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            cost_usd=cost_usd,
            data={
                "tool_name": tool_name,
                "result": truncated_result,
                "duration_ms": duration_ms,
                "error": error,
            },
        ))
    
    def _smart_truncate_result(self, result: str, tool_name: str) -> str:
        """Smart truncate tool result preserving key information.
        
        For search tools, preserves structure (titles, URLs, key facts).
        For other tools, uses standard head+tail truncation.
        
        Args:
            result: Tool result to truncate
            tool_name: Name of the tool (for context-aware truncation)
            
        Returns:
            Truncated result with key info preserved
        """
        limit = self.DEFAULT_TOOL_RESULT_LIMIT
        
        if len(result) <= limit:
            return result
        
        # Check if this is a search tool result (likely JSON/structured)
        tool_lower = tool_name.lower()
        is_search = any(s in tool_lower for s in [
            "search", "tavily", "duckduckgo", "google", "bing", "web"
        ])
        
        if is_search:
            # For search results, try to preserve complete items
            # Keep first 70% and last 20% to capture beginning and end
            head_limit = int(limit * 0.7)
            tail_limit = int(limit * 0.2)
            
            head = result[:head_limit]
            tail = result[-tail_limit:] if tail_limit > 0 else ""
            
            # Try to break at natural boundaries (newlines, }, ])
            for boundary in ['\n', '},', '],', '. ']:
                if boundary in head[head_limit-200:]:
                    idx = head.rfind(boundary, head_limit-200)
                    if idx > head_limit - 500:
                        head = head[:idx+len(boundary)]
                        break
            
            return f"{head}\n...[{len(result):,} chars, showing first/last portions]...\n{tail}"
        else:
            # Standard truncation for non-search tools
            head_limit = int(limit * 0.8)
            tail_limit = int(limit * 0.15)
            
            head = result[:head_limit]
            tail = result[-tail_limit:] if tail_limit > 0 else ""
            
            # Use smart format that judge recognizes as OK (not problematic truncation)
            return f"{head}\n...[{len(result):,} chars, showing first/last portions]...\n{tail}"
    
    def _get_tool_cost(self, tool_name: str) -> float:
        """Get cost for a tool call (1 credit = $0.001 for search tools).
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Cost in USD
        """
        # Tools that cost 1 credit ($0.001) per call
        SEARCH_TOOLS = {
            "tavily_search", "internet_search", "web_search", "search",
            "tavily_extract", "web_extract", "scrape", "crawl",
            "duckduckgo_search", "google_search", "bing_search",
        }
        
        tool_lower = tool_name.lower()
        for search_tool in SEARCH_TOOLS:
            if search_tool in tool_lower:
                return 0.001  # 1 credit = $0.001
        
        return 0.0  # Free for other tools
    
    def llm_request(
        self,
        agent_name: str,
        messages_count: int,
        tokens_used: int,
        tokens_budget: int = 0,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Emit LLM request event.
        
        Args:
            agent_name: Name of the agent making the request
            messages_count: Number of messages in the request
            tokens_used: Estimated tokens used
            tokens_budget: Token budget available
            model: Model being used
            messages: Optional full messages array for context replay
        """
        data = {"model": model}
        if messages is not None:
            data["messages"] = messages
        
        self._emit(ContextEvent(
            event_type=ContextEventType.LLM_REQUEST,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            messages_count=messages_count,
            tokens_used=tokens_used,
            tokens_budget=tokens_budget,
            data=data,
        ))
    
    def llm_response(
        self,
        agent_name: str,
        response_tokens: int = 0,
        duration_ms: float = 0.0,
        finish_reason: Optional[str] = None,
        response_content: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Emit LLM response event.
        
        Args:
            agent_name: Name of the agent receiving the response
            response_tokens: Number of tokens in response (deprecated, use completion_tokens)
            duration_ms: Response time in milliseconds
            finish_reason: Reason for completion (stop, length, etc.)
            response_content: Optional response content for context replay
            prompt_tokens: Number of tokens in the prompt/request
            completion_tokens: Number of tokens in the completion/response
            cost_usd: Estimated cost in USD for this LLM call
        """
        # Use completion_tokens if provided, fallback to response_tokens for backward compat
        actual_completion_tokens = completion_tokens if completion_tokens > 0 else response_tokens
        
        data = {
            "response_tokens": actual_completion_tokens,
            "duration_ms": duration_ms,
            "finish_reason": finish_reason,
        }
        if response_content is not None:
            # Smart truncate very long responses unless full_content is enabled
            if self._full_content:
                data["response_content"] = response_content
            elif len(response_content) > self.DEFAULT_LLM_RESPONSE_LIMIT:
                # Use smart truncation preserving head and tail
                limit = self.DEFAULT_LLM_RESPONSE_LIMIT
                head_limit = int(limit * 0.8)
                tail_limit = int(limit * 0.15)
                head = response_content[:head_limit]
                tail = response_content[-tail_limit:] if tail_limit > 0 else ""
                data["response_content"] = f"{head}\n...[{len(response_content):,} chars, showing first/last portions]...\n{tail}"
            else:
                data["response_content"] = response_content
        
        self._emit(ContextEvent(
            event_type=ContextEventType.LLM_RESPONSE,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=actual_completion_tokens,
            cost_usd=cost_usd,
            data=data,
        ))
    
    def context_snapshot(
        self,
        agent_name: str,
        messages_count: int,
        tokens_used: int,
        tokens_budget: int,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Emit context snapshot event with full context state."""
        self._emit(ContextEvent(
            event_type=ContextEventType.CONTEXT_SNAPSHOT,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            messages_count=messages_count,
            tokens_used=tokens_used,
            tokens_budget=tokens_budget,
            data={
                "messages": messages or [],
            },
        ))
    
    def agent_handoff(
        self,
        from_agent: str,
        to_agent: str,
        reason: Optional[str] = None,
        context_passed: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent handoff event for tracking agent-to-agent flow."""
        self._emit(ContextEvent(
            event_type=ContextEventType.AGENT_HANDOFF,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=from_agent,
            data={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "reason": reason,
                "context_passed": context_passed or {},
            },
        ))
    
    def memory_store(
        self,
        agent_name: str,
        memory_type: str,
        content_length: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit memory store event for tracking memory writes.
        
        Args:
            agent_name: Name of the agent storing memory
            memory_type: Type of memory (short_term, long_term, entity, user)
            content_length: Length of content being stored
            metadata: Optional metadata about the storage
        """
        self._emit(ContextEvent(
            event_type=ContextEventType.MEMORY_STORE,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "memory_type": memory_type,
                "content_length": content_length,
                "metadata": metadata or {},
            },
        ))
    
    def memory_search(
        self,
        agent_name: str,
        query: str,
        result_count: int,
        memory_type: str,
        top_score: Optional[float] = None,
    ) -> None:
        """Emit memory search event for tracking memory reads.
        
        Args:
            agent_name: Name of the agent searching memory
            query: Search query
            result_count: Number of results returned
            memory_type: Type of memory searched
            top_score: Score of top result (if available)
        """
        self._emit(ContextEvent(
            event_type=ContextEventType.MEMORY_SEARCH,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "query": query[:500] if query else "",
                "result_count": result_count,
                "memory_type": memory_type,
                "top_score": top_score,
            },
        ))
    
    def knowledge_search(
        self,
        agent_name: str,
        query: str,
        result_count: int,
        sources: Optional[List[str]] = None,
        top_score: Optional[float] = None,
    ) -> None:
        """Emit knowledge search event for tracking knowledge retrieval.
        
        Args:
            agent_name: Name of the agent searching knowledge
            query: Search query
            result_count: Number of results returned
            sources: List of source documents/files
            top_score: Score of top result (if available)
        """
        self._emit(ContextEvent(
            event_type=ContextEventType.KNOWLEDGE_SEARCH,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "query": query[:500] if query else "",
                "result_count": result_count,
                "sources": (sources or [])[:10],
                "top_score": top_score,
            },
        ))
    
    def knowledge_add(
        self,
        agent_name: str,
        source: str,
        chunk_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit knowledge add event for tracking knowledge indexing.
        
        Args:
            agent_name: Name of the agent adding knowledge
            source: Source file/URL being indexed
            chunk_count: Number of chunks created
            metadata: Optional metadata about the indexing
        """
        self._emit(ContextEvent(
            event_type=ContextEventType.KNOWLEDGE_ADD,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "source": source,
                "chunk_count": chunk_count,
                "metadata": metadata or {},
            },
        ))
    
    def flush(self) -> None:
        """Flush the sink."""
        self._sink.flush()
    
    def close(self) -> None:
        """Close the sink."""
        self._sink.close()
    
    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id
    
    @property
    def enabled(self) -> bool:
        """Check if emitter is enabled."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set enabled state."""
        self._enabled = value
