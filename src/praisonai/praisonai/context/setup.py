"""
Setup utilities for Dynamic Context Discovery.

Provides convenience functions to set up dynamic context features
with minimal configuration.
"""

import uuid
from typing import List, Optional, Callable

from .config import DynamicContextConfig
from .artifact_store import FileSystemArtifactStore
from .queue import OutputQueue, create_queue_middleware, create_artifact_tools
from .history_store import HistoryStore, create_history_tools
from .terminal_logger import TerminalLogger, create_terminal_tools


class DynamicContextSetup:
    """
    Container for dynamic context components.
    
    Provides access to all dynamic context features:
    - Artifact store
    - Output queue
    - History store
    - Terminal logger
    - Agent tools
    - Middleware
    """
    
    def __init__(
        self,
        config: Optional[DynamicContextConfig] = None,
        run_id: Optional[str] = None,
    ):
        """
        Initialize dynamic context setup.
        
        Args:
            config: Configuration (uses defaults if not provided)
            run_id: Run ID (generated if not provided)
        """
        self.config = config or DynamicContextConfig()
        self.run_id = run_id or self.config.run_id or str(uuid.uuid4())[:8]
        
        # Initialize components
        self.artifact_store = FileSystemArtifactStore(
            base_dir=self.config.base_dir,
            config=self.config.to_queue_config(),
        )
        
        self.output_queue = OutputQueue(
            store=self.artifact_store,
            config=self.config.to_queue_config(),
        )
        
        self.history_store = HistoryStore(base_dir=self.config.base_dir)
        
        self.terminal_logger = TerminalLogger(base_dir=self.config.base_dir)
    
    def get_tools(self) -> List[Callable]:
        """
        Get all dynamic context tools for agents.
        
        Returns:
            List of tool functions
        """
        tools = []
        
        # Artifact tools
        tools.extend(create_artifact_tools(store=self.artifact_store))
        
        # History tools
        if self.config.history_enabled:
            tools.extend(create_history_tools(store=self.history_store))
        
        # Terminal tools
        if self.config.terminal_logging:
            tools.extend(create_terminal_tools(terminal_logger=self.terminal_logger))
        
        return tools
    
    def get_middleware(self) -> Callable:
        """
        Get queue middleware for agents.
        
        Returns:
            Middleware function for Agent(hooks=[...])
        """
        return create_queue_middleware(
            store=self.artifact_store,
            config=self.config.to_queue_config(),
            run_id=self.run_id,
        )


def setup_dynamic_context(
    base_dir: str = "~/.praison/runs",
    inline_max_kb: int = 32,
    redact_secrets: bool = True,
    history_enabled: bool = True,
    terminal_logging: bool = False,
    run_id: Optional[str] = None,
) -> DynamicContextSetup:
    """
    Set up dynamic context discovery with minimal configuration.
    
    This is the main entry point for enabling dynamic context features.
    
    Args:
        base_dir: Base directory for artifact storage
        inline_max_kb: Maximum size for inline tool outputs (KB)
        redact_secrets: Whether to redact secrets in artifacts
        history_enabled: Whether to enable history persistence
        terminal_logging: Whether to enable terminal logging
        run_id: Run ID (generated if not provided)
        
    Returns:
        DynamicContextSetup with all components initialized
        
    Example:
        from praisonai.context import setup_dynamic_context
        from praisonaiagents import Agent
        
        # Set up dynamic context
        ctx = setup_dynamic_context(inline_max_kb=16)
        
        # Create agent with dynamic context tools and middleware
        agent = Agent(
            name="MyAgent",
            tools=ctx.get_tools(),
            hooks=[ctx.get_middleware()],
        )
    """
    config = DynamicContextConfig(
        base_dir=base_dir,
        inline_max_kb=inline_max_kb,
        redact_secrets=redact_secrets,
        history_enabled=history_enabled,
        terminal_logging=terminal_logging,
        run_id=run_id,
    )
    
    return DynamicContextSetup(config=config, run_id=run_id)
