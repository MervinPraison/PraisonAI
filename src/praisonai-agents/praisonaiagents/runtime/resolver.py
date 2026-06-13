"""Runtime resolver with resolution order implementation.

Implements the resolution order:
per-model runtime → per-provider default → auto → built-in default

Protocol-driven design following AGENTS.md:
- Core resolution logic without heavy implementations
- Fail-closed behavior for unknown runtime IDs
- Integration with model resolution system
"""

from typing import Optional, Dict, Any, Union, TYPE_CHECKING
from dataclasses import dataclass
import warnings

if TYPE_CHECKING:
    from .config import AgentRuntimeConfig
    from ..cli_backend.protocols import CliBackendProtocol


@dataclass
class RuntimeResolutionContext:
    """Context for runtime resolution containing model and provider information."""
    model_name: Optional[str] = None
    provider_name: Optional[str] = None
    model_config: Optional[Dict[str, Any]] = None
    provider_config: Optional[Dict[str, Any]] = None
    agent_config: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class RuntimeResolutionResult:
    """Result of runtime resolution containing the resolved runtime and metadata."""
    runtime: Any  # CliBackendProtocol instance
    runtime_id: str
    resolution_source: str  # "model", "provider", "auto", "default", "legacy"
    config_used: Optional["AgentRuntimeConfig"] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RuntimeResolver:
    """Core runtime resolver implementing resolution order logic.
    
    This is the core resolver that implements the resolution order without
    heavy dependencies. The actual runtime instantiation is delegated to
    the registry (which lives in the wrapper layer).
    """
    
    def __init__(self, default_runtime_id: str = "praisonai"):
        """Initialize runtime resolver.
        
        Args:
            default_runtime_id: Default runtime ID if no other runtime is found
        """
        self.default_runtime_id = default_runtime_id
    
    def resolve_runtime_config(
        self,
        context: RuntimeResolutionContext,
        model_runtime_configs: Optional[Dict[str, "AgentRuntimeConfig"]] = None,
        provider_runtime_configs: Optional[Dict[str, "AgentRuntimeConfig"]] = None,
        legacy_cli_backend: Optional[Union[str, Any]] = None,
    ) -> "AgentRuntimeConfig":
        """Resolve runtime configuration based on resolution order.
        
        Resolution order:
        1. per-model runtime (model_runtime_configs[model_name])
        2. per-provider default (provider_runtime_configs[provider_name])  
        3. auto-selection (if enabled and available)
        4. built-in default (self.default_runtime_id)
        5. legacy cli_backend (with deprecation warning)
        
        Args:
            context: Runtime resolution context
            model_runtime_configs: Per-model runtime configurations
            provider_runtime_configs: Per-provider runtime configurations  
            legacy_cli_backend: Legacy agent-level cli_backend (deprecated)
            
        Returns:
            AgentRuntimeConfig for the resolved runtime
        """
        from .config import AgentRuntimeConfig
        
        # Normalize inputs
        model_runtime_configs = model_runtime_configs or {}
        provider_runtime_configs = provider_runtime_configs or {}
        
        # 1. Check per-model runtime configuration
        if context.model_name and context.model_name in model_runtime_configs:
            config = model_runtime_configs[context.model_name]
            if config.is_explicit():
                config.metadata["resolution_source"] = "model"
                return config
        
        # 2. Check per-provider runtime configuration
        if context.provider_name and context.provider_name in provider_runtime_configs:
            config = provider_runtime_configs[context.provider_name]
            if config.is_explicit():
                config.metadata["resolution_source"] = "provider"
                return config
        
        # 3. Auto-selection (placeholder for future implementation)
        # This would check if auto-selection is enabled and delegate to auto-selection logic
        auto_config = self._try_auto_selection(context)
        if auto_config is not None:
            auto_config.metadata["resolution_source"] = "auto"
            return auto_config
        
        # 4. Built-in default
        default_config = AgentRuntimeConfig.from_runtime_id(self.default_runtime_id)
        default_config.metadata["resolution_source"] = "default"
        
        # 5. Legacy cli_backend support (with deprecation warning)
        if legacy_cli_backend is not None:
            warnings.warn(
                "Agent-level 'cli_backend' parameter is deprecated. "
                "Use model-scoped runtime configuration instead. "
                "See documentation for migration guide.",
                DeprecationWarning,
                stacklevel=3
            )
            
            # Convert legacy cli_backend to runtime config
            if isinstance(legacy_cli_backend, str):
                legacy_config = AgentRuntimeConfig.from_runtime_id(legacy_cli_backend)
            else:
                # Assume it's already a config or protocol instance
                legacy_config = AgentRuntimeConfig(runtime="legacy")
                legacy_config.config_overrides["instance"] = legacy_cli_backend
            
            legacy_config.metadata["resolution_source"] = "legacy"
            return legacy_config
        
        return default_config
    
    def _try_auto_selection(
        self, 
        context: RuntimeResolutionContext
    ) -> Optional["AgentRuntimeConfig"]:
        """Try auto-selection of runtime based on context.
        
        This is a placeholder for future auto-selection logic.
        The actual implementation would analyze the model, provider,
        and context to automatically select an appropriate runtime.
        
        Args:
            context: Runtime resolution context
            
        Returns:
            AgentRuntimeConfig if auto-selection succeeds, None otherwise
        """
        # Placeholder for auto-selection logic
        # Future implementation could:
        # - Check if model supports specific runtimes
        # - Look at provider capabilities
        # - Consider context metadata
        # - Use ML-based selection
        
        return None
    
    def resolve_runtime_instance(
        self,
        context: RuntimeResolutionContext,
        model_runtime_configs: Optional[Dict[str, "AgentRuntimeConfig"]] = None,
        provider_runtime_configs: Optional[Dict[str, "AgentRuntimeConfig"]] = None,
        legacy_cli_backend: Optional[Union[str, Any]] = None,
    ) -> RuntimeResolutionResult:
        """Resolve runtime instance based on configuration and context.
        
        This method combines configuration resolution with actual runtime
        instantiation using the global registry.
        
        Args:
            context: Runtime resolution context
            model_runtime_configs: Per-model runtime configurations
            provider_runtime_configs: Per-provider runtime configurations
            legacy_cli_backend: Legacy agent-level cli_backend (deprecated)
            
        Returns:
            RuntimeResolutionResult with resolved runtime instance
            
        Raises:
            ValueError: If runtime ID is not registered (fail-closed behavior)
            RuntimeError: If global registry is not initialized
        """
        from .registry import resolve_runtime
        
        # Resolve configuration
        config = self.resolve_runtime_config(
            context=context,
            model_runtime_configs=model_runtime_configs,
            provider_runtime_configs=provider_runtime_configs,
            legacy_cli_backend=legacy_cli_backend,
        )
        
        # Handle legacy instances that are already resolved
        if (config.metadata.get("resolution_source") == "legacy" and 
            "instance" in config.config_overrides):
            instance = config.config_overrides["instance"]
            return RuntimeResolutionResult(
                runtime=instance,
                runtime_id="legacy",
                resolution_source="legacy",
                config_used=config,
                metadata={"legacy_instance": True}
            )
        
        # Resolve runtime instance using global registry
        if config.runtime is None:
            raise ValueError("No runtime ID available for resolution")
        
        try:
            runtime_instance = resolve_runtime(
                runtime_id=config.runtime,
                config_overrides=config.config_overrides
            )
            
            return RuntimeResolutionResult(
                runtime=runtime_instance,
                runtime_id=config.runtime,
                resolution_source=config.metadata.get("resolution_source", "unknown"),
                config_used=config,
                metadata=config.metadata.copy()
            )
            
        except ValueError as e:
            # Enhance error message with available runtimes
            from .registry import list_available_runtimes
            available = [entry.runtime_id for entry in list_available_runtimes()]
            raise ValueError(
                f"Unknown runtime ID: {config.runtime}. Available runtimes: {available}. "
                f"Original error: {e}"
            ) from e
    
    def validate_runtime_config(
        self, 
        config: "AgentRuntimeConfig"
    ) -> None:
        """Validate a runtime configuration.
        
        Args:
            config: Runtime configuration to validate
            
        Raises:
            ValueError: If runtime configuration is invalid
            TypeError: If runtime configuration has invalid types
        """
        if not hasattr(config, 'runtime'):
            raise TypeError("Runtime configuration must have 'runtime' attribute")
        
        if config.runtime is not None:
            if not isinstance(config.runtime, str):
                raise TypeError("Runtime ID must be a string")
            
            if not config.runtime.strip():
                raise ValueError("Runtime ID cannot be empty")
        
        if not isinstance(config.config_overrides, dict):
            raise TypeError("config_overrides must be a dictionary")
        
        if config.metadata is not None and not isinstance(config.metadata, dict):
            raise TypeError("metadata must be a dictionary")


# Default resolver instance
default_resolver = RuntimeResolver()