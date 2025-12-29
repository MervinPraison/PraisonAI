"""
Database adapter protocol for PraisonAI Agents.

This module uses only stdlib (typing, dataclasses) to define the interface.
No external dependencies are imported here.

Implementations are provided by the wrapper layer (praisonai.db).

Schema Versioning:
- SCHEMA_VERSION tracks the protocol version
- Adapters should implement get_schema_version() to report their version
- Adapters should implement migrate_schema() for upgrades
- Version format: MAJOR.MINOR (e.g., "1.0", "1.1", "2.0")
- MAJOR changes are breaking, MINOR changes are backward compatible
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, Tuple
import time


# Current schema version for the DbAdapter protocol
# Increment MINOR for backward-compatible additions
# Increment MAJOR for breaking changes
SCHEMA_VERSION = "1.0"


@dataclass
class DbToolCall:
    """A tool call to be persisted."""
    tool_name: str
    args: Dict[str, Any]
    result: Any = None
    call_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class DbMessage:
    """A message to be persisted."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: Optional[str] = None
    tool_calls: Optional[List["DbToolCall"]] = None  # For assistant messages with tool calls
    run_id: Optional[str] = None  # Group messages by run


@dataclass
class DbRun:
    """A single agent run (turn) to be persisted."""
    run_id: str
    session_id: str
    agent_name: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    status: str = "running"  # running, completed, error, cancelled
    input_content: Optional[str] = None
    output_content: Optional[str] = None
    messages: List[DbMessage] = field(default_factory=list)
    tool_calls: List[DbToolCall] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)  # tokens, latency, etc.


@dataclass
class DbSpan:
    """A span for tracing/observability."""
    span_id: str
    trace_id: str
    name: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    parent_span_id: Optional[str] = None
    status: str = "running"  # running, ok, error
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DbTrace:
    """A trace for observability (groups spans)."""
    trace_id: str
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    agent_name: Optional[str] = None
    user_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    status: str = "running"  # running, ok, error
    spans: List[DbSpan] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DbAdapter(Protocol):
    """
    Protocol for database adapters that provide persistence for agents.
    
    Implementations must provide these methods. The agent will call them
    at appropriate lifecycle points if a db adapter is provided.
    
    All methods are synchronous. Async support can be added via wrapper.
    """
    
    def on_agent_start(
        self,
        agent_name: str,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DbMessage]:
        """
        Called when agent starts a session.
        
        Args:
            agent_name: Name of the agent
            session_id: Session identifier
            user_id: Optional user identifier
            metadata: Optional session metadata
            
        Returns:
            List of previous messages for this session (for resume)
        """
        ...
    
    def on_user_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when user sends a message.
        
        Args:
            session_id: Session identifier
            content: Message content
            metadata: Optional message metadata
        """
        ...
    
    def on_agent_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when agent produces a response.
        
        Args:
            session_id: Session identifier
            content: Response content
            metadata: Optional message metadata
        """
        ...
    
    def on_tool_call(
        self,
        session_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when a tool is executed.
        
        Args:
            session_id: Session identifier
            tool_name: Name of the tool
            args: Tool arguments
            result: Tool result
            metadata: Optional call metadata
        """
        ...
    
    def on_agent_end(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when agent session ends.
        
        Args:
            session_id: Session identifier
            metadata: Optional end metadata
        """
        ...
    
    def on_run_start(
        self,
        session_id: str,
        run_id: str,
        input_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when a new run (turn) starts.
        
        Args:
            session_id: Session identifier
            run_id: Run identifier
            input_content: User input for this run
            metadata: Optional run metadata
        """
        ...
    
    def on_run_end(
        self,
        session_id: str,
        run_id: str,
        output_content: Optional[str] = None,
        status: str = "completed",
        metrics: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when a run (turn) ends.
        
        Args:
            session_id: Session identifier
            run_id: Run identifier
            output_content: Agent output for this run
            status: Run status (completed, error, cancelled)
            metrics: Optional metrics (tokens, latency)
            metadata: Optional run metadata
        """
        ...
    
    def get_runs(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List["DbRun"]:
        """
        Get runs for a session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of runs to return
            
        Returns:
            List of runs for this session
        """
        ...
    
    def export_session(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Export a session as a dictionary (for JSONL export).
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with session data, messages, runs
        """
        ...
    
    def import_session(
        self,
        data: Dict[str, Any],
    ) -> str:
        """
        Import a session from a dictionary.
        
        Args:
            data: Session data dictionary
            
        Returns:
            Session ID of imported session
        """
        ...
    
    # --- Tracing/Observability ---
    
    def on_trace_start(
        self,
        trace_id: str,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when a new trace starts.
        
        Args:
            trace_id: Unique trace identifier
            session_id: Optional session identifier
            run_id: Optional run identifier
            agent_name: Optional agent name
            user_id: Optional user identifier
            metadata: Optional trace metadata
        """
        ...
    
    def on_trace_end(
        self,
        trace_id: str,
        status: str = "ok",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when a trace ends.
        
        Args:
            trace_id: Trace identifier
            status: Trace status (ok, error)
            metadata: Optional end metadata
        """
        ...
    
    def on_span_start(
        self,
        span_id: str,
        trace_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when a new span starts.
        
        Args:
            span_id: Unique span identifier
            trace_id: Parent trace identifier
            name: Span name (e.g., "llm_call", "tool_execution")
            parent_span_id: Optional parent span for nesting
            attributes: Optional span attributes
        """
        ...
    
    def on_span_end(
        self,
        span_id: str,
        status: str = "ok",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called when a span ends.
        
        Args:
            span_id: Span identifier
            status: Span status (ok, error)
            attributes: Optional end attributes
        """
        ...
    
    def get_traces(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List["DbTrace"]:
        """
        Get traces with optional filters.
        
        Args:
            session_id: Filter by session
            user_id: Filter by user
            limit: Maximum number of traces
            
        Returns:
            List of traces
        """
        ...
    
    def close(self) -> None:
        """Close the database connection."""
        ...
    
    # --- Schema Versioning (Optional) ---
    # These methods are optional for backward compatibility.
    # Adapters that don't implement them will work but won't support migrations.
    
    def get_schema_version(self) -> str:
        """
        Get the current schema version of this adapter.
        
        Returns:
            Schema version string (e.g., "1.0")
            Default implementation returns "1.0"
        """
        ...
    
    def migrate_schema(
        self,
        from_version: str,
        to_version: str,
    ) -> bool:
        """
        Migrate the schema from one version to another.
        
        Args:
            from_version: Current schema version
            to_version: Target schema version
            
        Returns:
            True if migration succeeded, False otherwise
        """
        ...
    
    def check_schema_compatibility(self) -> Tuple[bool, str]:
        """
        Check if the adapter's schema is compatible with the protocol.
        
        Returns:
            Tuple of (is_compatible, message)
            - is_compatible: True if schema is compatible
            - message: Description of compatibility status or required action
        """
        ...


@runtime_checkable
class AsyncDbAdapter(Protocol):
    """
    Async protocol for database adapters.
    
    Provides async variants of all DbAdapter methods for use with
    async/await patterns and async backends like asyncpg.
    """
    
    async def on_agent_start(
        self,
        agent_name: str,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List["DbMessage"]:
        """Async version of on_agent_start."""
        ...
    
    async def on_user_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Async version of on_user_message."""
        ...
    
    async def on_agent_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Async version of on_agent_message."""
        ...
    
    async def on_tool_call(
        self,
        session_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Async version of on_tool_call."""
        ...
    
    async def on_agent_end(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Async version of on_agent_end."""
        ...
    
    async def on_run_start(
        self,
        session_id: str,
        run_id: str,
        input_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Async version of on_run_start."""
        ...
    
    async def on_run_end(
        self,
        session_id: str,
        run_id: str,
        output_content: Optional[str] = None,
        status: str = "completed",
        metrics: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Async version of on_run_end."""
        ...
    
    async def export_session(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        """Async version of export_session."""
        ...
    
    async def import_session(
        self,
        data: Dict[str, Any],
    ) -> str:
        """Async version of import_session."""
        ...
    
    async def close(self) -> None:
        """Async close the database connection."""
        ...
