"""
Configuration for InteractiveCore.

Provides unified configuration that works across all interactive modes.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Union


class ApprovalMode(Enum):
    """Approval mode for tool execution."""
    
    PROMPT = "prompt"  # Ask user for each action (default)
    AUTO = "auto"  # Auto-approve all actions
    REJECT = "reject"  # Reject all actions requiring approval


@dataclass
class InteractiveConfig:
    """Configuration for InteractiveCore.
    
    This configuration is shared across all interactive modes:
    - `praisonai run --interactive`
    - `praisonai chat`
    - `praisonai tui launch`
    """
    
    # Model configuration
    model: Optional[str] = None
    
    # Session configuration
    session_id: Optional[str] = None
    continue_session: bool = False
    
    # Workspace
    workspace: str = field(default_factory=os.getcwd)
    
    # Tool configuration
    enable_acp: bool = True
    enable_lsp: bool = True
    
    # Behavior
    verbose: bool = False
    memory: bool = False
    
    # Autonomy configuration (agent-centric)
    autonomy: bool = True  # Enable autonomy by default for complex tasks
    autonomy_config: Optional[dict] = None  # Custom autonomy config
    
    # Approval mode - default to "auto" for full privileges in interactive mode
    # Use "prompt" for safer mode that asks before each action
    approval_mode: Union[str, ApprovalMode] = "auto"
    
    # File attachments
    files: List[str] = field(default_factory=list)
    
    # Sharing
    share: bool = False
    
    # Variant (reasoning effort)
    variant: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "InteractiveConfig":
        """Create config from environment variables."""
        return cls(
            model=os.environ.get("PRAISON_MODEL"),
            workspace=os.environ.get("PRAISON_WORKSPACE", os.getcwd()),
            approval_mode=os.environ.get("PRAISON_APPROVAL_MODE", "prompt"),
            enable_acp=os.environ.get("PRAISON_DISABLE_ACP", "").lower() != "true",
            enable_lsp=os.environ.get("PRAISON_DISABLE_LSP", "").lower() != "true",
            verbose=os.environ.get("PRAISON_VERBOSE", "").lower() == "true",
            memory=os.environ.get("PRAISON_MEMORY", "").lower() == "true",
            autonomy=os.environ.get("PRAISON_AUTONOMY", "true").lower() != "false",
        )
    
    @classmethod
    def from_args(cls, args: Any) -> "InteractiveConfig":
        """Create config from CLI arguments namespace."""
        return cls(
            model=getattr(args, "model", None),
            session_id=getattr(args, "session", None),
            continue_session=getattr(args, "continue_session", False) or getattr(args, "continue_", False),
            workspace=getattr(args, "workspace", os.getcwd()),
            enable_acp=not getattr(args, "no_acp", False),
            enable_lsp=not getattr(args, "no_lsp", False),
            verbose=getattr(args, "verbose", False),
            memory=getattr(args, "memory", False),
            files=getattr(args, "file", []) or [],
            share=getattr(args, "share", False),
            variant=getattr(args, "variant", None),
            autonomy=getattr(args, "autonomy", True),
        )
    
    def merge(self, other: "InteractiveConfig") -> "InteractiveConfig":
        """Merge with another config, other takes precedence for non-None values."""
        from dataclasses import MISSING
        
        merged_data = {}
        
        for field_name, field_info in self.__dataclass_fields__.items():
            self_value = getattr(self, field_name)
            other_value = getattr(other, field_name)
            
            # Get default value
            if field_info.default is not MISSING:
                default = field_info.default
            elif field_info.default_factory is not MISSING:
                default = field_info.default_factory()
            else:
                default = None
            
            # Use other's value if it's not the default
            if other_value != default and other_value is not None:
                merged_data[field_name] = other_value
            else:
                merged_data[field_name] = self_value
        
        return InteractiveConfig(**merged_data)
    
    def to_tool_config(self) -> "ToolConfig":
        """Convert to ToolConfig for interactive_tools module."""
        from ..features.interactive_tools import ToolConfig
        
        return ToolConfig(
            workspace=self.workspace,
            enable_acp=self.enable_acp,
            enable_lsp=self.enable_lsp,
            approval_mode=self.approval_mode if isinstance(self.approval_mode, str) else self.approval_mode.value,
        )
