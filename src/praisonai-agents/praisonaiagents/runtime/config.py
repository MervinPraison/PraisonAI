"""AgentRuntimeConfig dataclass for model-scoped runtime selection.

Protocol-driven design following AGENTS.md:
- Lightweight dataclass for configuration
- No heavy implementations (those live in wrapper layer)
- Support for per-model and per-provider runtime configuration
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union


@dataclass
class AgentRuntimeConfig:
    """Model-scoped runtime configuration for PraisonAI Agents.
    
    Supports the resolution order:
    per-model runtime → per-provider default → auto → built-in default
    
    This replaces agent-level cli_backend with model-scoped runtime selection.
    """
    # Runtime identifier (e.g., "claude-code", "codex-cli", "praisonai")
    runtime: Optional[str] = None
    
    # Runtime-specific configuration overrides
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    
    # Provider-level default runtime (for YAML providers.<name>.runtime_default)
    provider_default: Optional[str] = None
    
    # Enable auto-selection if no explicit runtime is specified
    enable_auto_selection: bool = True
    
    # Metadata for runtime resolution
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate runtime configuration on initialization."""
        # Ensure config_overrides is a dictionary
        if not isinstance(self.config_overrides, dict):
            raise TypeError("config_overrides must be a dictionary")
        
        # Ensure metadata is a dictionary  
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary")
    
    @classmethod
    def from_runtime_id(cls, runtime_id: str, **kwargs) -> "AgentRuntimeConfig":
        """Create AgentRuntimeConfig from a runtime ID string.
        
        Args:
            runtime_id: Runtime identifier (e.g., "claude-code")
            **kwargs: Additional configuration options
            
        Returns:
            AgentRuntimeConfig instance
        """
        return cls(runtime=runtime_id, **kwargs)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "AgentRuntimeConfig":
        """Create AgentRuntimeConfig from a dictionary.
        
        Args:
            config_dict: Configuration dictionary
            
        Returns:
            AgentRuntimeConfig instance
            
        Raises:
            TypeError: If config_dict is not a dictionary
            ValueError: If required fields are missing or invalid
        """
        if not isinstance(config_dict, dict):
            raise TypeError("config_dict must be a dictionary")
        
        # Extract known fields
        runtime = config_dict.get("runtime")
        config_overrides = config_dict.get("config_overrides", {})
        provider_default = config_dict.get("provider_default")
        enable_auto_selection = config_dict.get("enable_auto_selection", True)
        metadata = config_dict.get("metadata", {})
        
        # Validate types
        if config_overrides is not None and not isinstance(config_overrides, dict):
            raise TypeError("config_overrides must be a dictionary")
        
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")
        
        return cls(
            runtime=runtime,
            config_overrides=config_overrides,
            provider_default=provider_default,
            enable_auto_selection=enable_auto_selection,
            metadata=metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert AgentRuntimeConfig to a dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        return {
            "runtime": self.runtime,
            "config_overrides": self.config_overrides,
            "provider_default": self.provider_default,
            "enable_auto_selection": self.enable_auto_selection,
            "metadata": self.metadata
        }
    
    def merge_overrides(self, overrides: Dict[str, Any]) -> "AgentRuntimeConfig":
        """Create a new AgentRuntimeConfig with merged configuration overrides.
        
        Args:
            overrides: Configuration overrides to merge
            
        Returns:
            New AgentRuntimeConfig instance with merged overrides
        """
        if not isinstance(overrides, dict):
            raise TypeError("overrides must be a dictionary")
        
        # Create new config overrides by merging
        new_config_overrides = {**self.config_overrides, **overrides}
        
        return AgentRuntimeConfig(
            runtime=self.runtime,
            config_overrides=new_config_overrides,
            provider_default=self.provider_default,
            enable_auto_selection=self.enable_auto_selection,
            metadata=self.metadata.copy()
        )
    
    def with_runtime(self, runtime_id: str) -> "AgentRuntimeConfig":
        """Create a new AgentRuntimeConfig with a different runtime ID.
        
        Args:
            runtime_id: New runtime identifier
            
        Returns:
            New AgentRuntimeConfig instance with updated runtime
        """
        return AgentRuntimeConfig(
            runtime=runtime_id,
            config_overrides=self.config_overrides.copy(),
            provider_default=self.provider_default,
            enable_auto_selection=self.enable_auto_selection,
            metadata=self.metadata.copy()
        )
    
    def is_explicit(self) -> bool:
        """Check if this configuration specifies an explicit runtime.
        
        Returns:
            True if runtime is explicitly specified, False otherwise
        """
        return self.runtime is not None and self.runtime != ""
    
    def __repr__(self) -> str:
        """String representation of AgentRuntimeConfig."""
        return (
            f"AgentRuntimeConfig("
            f"runtime={self.runtime!r}, "
            f"config_overrides={self.config_overrides!r}, "
            f"provider_default={self.provider_default!r}, "
            f"enable_auto_selection={self.enable_auto_selection!r})"
        )