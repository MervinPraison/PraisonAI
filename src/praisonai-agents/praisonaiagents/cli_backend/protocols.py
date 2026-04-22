"""CLI Backend protocols and data structures.

Protocol-driven design following AGENTS.md:
- Lightweight protocols only (no implementations)
- Dataclasses for configuration
- Async-first with proper typing
"""

from dataclasses import dataclass, field
from typing import Protocol, AsyncIterator, Optional, List, Dict, Any, runtime_checkable


@dataclass
class CliBackendConfig:
    """Declarative CLI backend configuration.
    
    Mirrors OpenClaw's CliBackendConfig for cross-ecosystem compatibility.
    """
    # Core command
    command: str  # e.g., "claude", "codex", "gemini"
    args: List[str] = field(default_factory=list)
    
    # Session management
    resume_args: Optional[List[str]] = None  # supports "{session_id}" placeholder
    session_arg: Optional[str] = None  # e.g., "--session-id"
    session_mode: str = "none"  # "always" | "existing" | "none"
    session_id_fields: List[str] = field(default_factory=list)
    
    # Input/output format
    output: str = "text"  # "text" | "json" | "jsonl"
    input: str = "arg"  # "arg" | "stdin"
    max_prompt_arg_chars: Optional[int] = None
    
    # Model configuration
    model_arg: Optional[str] = None  # e.g., "--model"
    model_aliases: Dict[str, str] = field(default_factory=dict)
    
    # System prompt handling
    system_prompt_arg: Optional[str] = None  # e.g., "--append-system-prompt"
    system_prompt_when: str = "always"  # "first" | "always" | "never"
    system_prompt_mode: str = "append"  # "append" | "replace"
    
    # Image support
    image_arg: Optional[str] = None  # e.g., "--image"
    image_mode: str = "repeat"  # "repeat" | "list"
    
    # Environment
    clear_env: List[str] = field(default_factory=list)  # Env vars to clear
    env: Dict[str, str] = field(default_factory=dict)  # Env vars to set
    
    # Advanced features
    live_session: Optional[str] = None  # e.g., "claude-stdio"
    bundle_mcp: bool = False
    bundle_mcp_mode: Optional[str] = None  # e.g., "claude-config-file"
    serialize: bool = False  # Queue operations to avoid conflicts
    
    # Timeouts
    no_output_timeout_ms: Optional[int] = None
    timeout_ms: int = 300_000


@dataclass
class CliSessionBinding:
    """Session binding for CLI backend state tracking."""
    session_id: Optional[str] = None
    auth_profile_id: Optional[str] = None
    system_prompt_hash: Optional[str] = None
    mcp_config_hash: Optional[str] = None


@dataclass
class CliBackendResult:
    """Result from CLI backend execution."""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CliBackendDelta:
    """Streaming delta from CLI backend."""
    type: str  # "text" | "tool_call" | "thinking" | "error"
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CliBackendProtocol(Protocol):
    """Protocol for CLI backend implementations.
    
    Any object implementing these methods can serve as an Agent backend.
    Follows typing.Protocol pattern from AGENTS.md.
    """
    config: CliBackendConfig
    
    async def execute(
        self, 
        prompt: str, 
        *,
        session: Optional[CliSessionBinding] = None,
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> CliBackendResult:
        """Execute a single prompt and return result.
        
        Args:
            prompt: User prompt/query
            session: Session binding for state management
            images: List of image paths for multimodal prompts
            system_prompt: System prompt override
            **kwargs: Additional backend-specific options
            
        Returns:
            CliBackendResult with response content and metadata
        """
        ...
    
    async def stream(
        self, 
        prompt: str, 
        **kwargs
    ) -> AsyncIterator[CliBackendDelta]:
        """Stream response deltas from CLI backend.
        
        Args:
            prompt: User prompt/query
            **kwargs: Additional options (session, images, etc.)
            
        Yields:
            CliBackendDelta objects with incremental response content
        """
        ...