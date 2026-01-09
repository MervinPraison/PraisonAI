"""
Workflow Configuration Classes for PraisonAI Agents.

Provides dataclasses for consolidated workflow feature configuration:
- WorkflowOutputConfig: Output and verbosity settings
- WorkflowPlanningConfig: Planning mode settings
- WorkflowMemoryConfig: Memory configuration
- WorkflowHooksConfig: Workflow lifecycle callbacks
- WorkflowStepContextConfig: Step context settings
- WorkflowStepOutputConfig: Step output settings
- WorkflowStepExecutionConfig: Step execution settings
- WorkflowStepRoutingConfig: Step routing/branching settings

All configs follow the workflow-centric pattern with precedence:
Instance > Config > String > Bool > Default

Usage:
    from praisonaiagents import Workflow, WorkflowOutputConfig
    
    # Simple enable with preset
    workflow = Workflow(steps=[...], output="verbose")
    
    # With config
    workflow = Workflow(
        steps=[...],
        output=WorkflowOutputConfig(verbose=True, stream=True),
        planning=WorkflowPlanningConfig(llm="gpt-4o", reasoning=True),
    )
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union
from enum import Enum


# =============================================================================
# Workflow-Level Config Classes
# =============================================================================

class WorkflowOutputPreset(str, Enum):
    """Output preset names for workflows."""
    SILENT = "silent"
    MINIMAL = "minimal"
    NORMAL = "normal"
    VERBOSE = "verbose"
    DEBUG = "debug"


@dataclass
class WorkflowOutputConfig:
    """
    Configuration for workflow output behavior.
    
    Consolidates: verbose, stream
    
    Usage:
        # Preset (string)
        Workflow(steps=[...], output="verbose")
        
        # Config
        Workflow(steps=[...], output=WorkflowOutputConfig(verbose=True, stream=True))
    """
    verbose: bool = False
    stream: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {"verbose": self.verbose, "stream": self.stream}


@dataclass
class WorkflowPlanningConfig:
    """
    Configuration for workflow planning mode.
    
    Consolidates: planning, planning_llm, reasoning
    
    Usage:
        # Simple enable
        Workflow(steps=[...], planning=True)
        
        # Config
        Workflow(steps=[...], planning=WorkflowPlanningConfig(llm="gpt-4o", reasoning=True))
    """
    enabled: bool = True
    llm: Optional[str] = None
    reasoning: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "llm": self.llm, "reasoning": self.reasoning}


@dataclass
class WorkflowMemoryConfig:
    """
    Configuration for workflow memory.
    
    Consolidates: memory_config
    
    Usage:
        # Simple enable
        Workflow(steps=[...], memory=True)
        
        # Config
        Workflow(steps=[...], memory=WorkflowMemoryConfig(backend="redis", user_id="user123"))
    """
    backend: str = "file"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "config": self.config,
        }


@dataclass
class WorkflowHooksConfig:
    """
    Configuration for workflow lifecycle hooks.
    
    Consolidates: on_workflow_start, on_workflow_complete, on_step_start, on_step_complete, on_step_error
    
    Usage:
        Workflow(
            steps=[...],
            hooks=WorkflowHooksConfig(
                on_workflow_start=my_start_fn,
                on_step_complete=my_step_fn,
            )
        )
    """
    on_workflow_start: Optional[Callable] = None
    on_workflow_complete: Optional[Callable] = None
    on_step_start: Optional[Callable] = None
    on_step_complete: Optional[Callable] = None
    on_step_error: Optional[Callable] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "on_workflow_start": self.on_workflow_start is not None,
            "on_workflow_complete": self.on_workflow_complete is not None,
            "on_step_start": self.on_step_start is not None,
            "on_step_complete": self.on_step_complete is not None,
            "on_step_error": self.on_step_error is not None,
        }


# =============================================================================
# WorkflowStep-Level Config Classes
# =============================================================================

@dataclass
class WorkflowStepContextConfig:
    """
    Configuration for step context handling.
    
    Consolidates: context_from, retain_full_context
    
    Usage:
        WorkflowStep(
            name="step1",
            context=WorkflowStepContextConfig(from_steps=["step0"], retain_full=True)
        )
    """
    from_steps: Optional[List[str]] = None
    retain_full: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {"from_steps": self.from_steps, "retain_full": self.retain_full}


@dataclass
class WorkflowStepOutputConfig:
    """
    Configuration for step output handling.
    
    Consolidates: output_file, output_json, output_pydantic, output_variable
    
    Usage:
        WorkflowStep(
            name="step1",
            output=WorkflowStepOutputConfig(file="output.txt", variable="result")
        )
    """
    file: Optional[str] = None
    json_model: Optional[Any] = None
    pydantic_model: Optional[Any] = None
    variable: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "json_model": self.json_model is not None,
            "pydantic_model": self.pydantic_model is not None,
            "variable": self.variable,
        }


class WorkflowStepExecutionPreset(str, Enum):
    """Execution preset names for workflow steps."""
    FAST = "fast"
    BALANCED = "balanced"
    THOROUGH = "thorough"


@dataclass
class WorkflowStepExecutionConfig:
    """
    Configuration for step execution behavior.
    
    Consolidates: async_execution, quality_check, rerun, max_retries, on_error
    
    Usage:
        # Preset
        WorkflowStep(name="step1", execution="thorough")
        
        # Config
        WorkflowStep(
            name="step1",
            execution=WorkflowStepExecutionConfig(async_exec=True, max_retries=5)
        )
    """
    async_exec: bool = False
    quality_check: bool = True
    rerun: bool = True
    max_retries: int = 3
    on_error: str = "stop"  # "stop", "continue", "retry"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "async_exec": self.async_exec,
            "quality_check": self.quality_check,
            "rerun": self.rerun,
            "max_retries": self.max_retries,
            "on_error": self.on_error,
        }


@dataclass
class WorkflowStepRoutingConfig:
    """
    Configuration for step routing/branching.
    
    Consolidates: next_steps, branch_condition
    
    Usage:
        WorkflowStep(
            name="decision",
            routing=WorkflowStepRoutingConfig(
                branches={"success": ["step2"], "failure": ["step3"]}
            )
        )
    """
    next_steps: Optional[List[str]] = None
    branches: Optional[Dict[str, List[str]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {"next_steps": self.next_steps, "branches": self.branches}


# =============================================================================
# Precedence Resolution Helper
# =============================================================================

def resolve_param(
    value: Any,
    config_class: type,
    presets: Optional[Dict[str, Any]] = None,
    default: Any = None,
    instance_check: Optional[Callable[[Any], bool]] = None,
) -> Any:
    """
    Resolve a consolidated parameter following precedence rules:
    Instance > Config > String > Bool > Default
    
    Args:
        value: The parameter value (can be Instance, Config, String, Bool, or None)
        config_class: The expected config dataclass type
        presets: Dict mapping preset strings to config instances or dicts
        default: Default value if None/unset
        instance_check: Optional function to check if value is an instance
        
    Returns:
        Resolved config object or value
        
    Example:
        # Resolve output param
        output_config = resolve_param(
            value=output,
            config_class=WorkflowOutputConfig,
            presets={
                "silent": WorkflowOutputConfig(verbose=False, stream=False),
                "verbose": WorkflowOutputConfig(verbose=True, stream=True),
            },
            default=WorkflowOutputConfig(),
        )
    """
    # None/unset -> Default
    if value is None:
        return default
    
    # Instance check (e.g., pre-built manager object)
    if instance_check and instance_check(value):
        return value
    
    # Config dataclass
    if isinstance(value, config_class):
        return value
    
    # Dict -> convert to config
    if isinstance(value, dict):
        try:
            return config_class(**value)
        except TypeError:
            return default
    
    # String -> preset lookup
    if isinstance(value, str) and presets:
        preset_value = presets.get(value)
        if preset_value is not None:
            if isinstance(preset_value, dict):
                return config_class(**preset_value)
            return preset_value
        return default
    
    # Bool -> True enables defaults, False disables
    if isinstance(value, bool):
        if value:
            return config_class() if config_class else True
        return None  # Disabled
    
    # Fallback to default
    return default


def resolve_output_config(value: Any) -> WorkflowOutputConfig:
    """Resolve output parameter to WorkflowOutputConfig."""
    presets = {
        "silent": WorkflowOutputConfig(verbose=False, stream=False),
        "minimal": WorkflowOutputConfig(verbose=False, stream=True),
        "normal": WorkflowOutputConfig(verbose=False, stream=True),
        "verbose": WorkflowOutputConfig(verbose=True, stream=True),
        "debug": WorkflowOutputConfig(verbose=True, stream=True),
    }
    result = resolve_param(value, WorkflowOutputConfig, presets, WorkflowOutputConfig())
    return result if result else WorkflowOutputConfig(verbose=False, stream=False)


def resolve_planning_config(value: Any) -> Optional[WorkflowPlanningConfig]:
    """Resolve planning parameter to WorkflowPlanningConfig or None."""
    if value is None or value is False:
        return None
    if value is True:
        return WorkflowPlanningConfig(enabled=True)
    if isinstance(value, WorkflowPlanningConfig):
        return value
    if isinstance(value, dict):
        return WorkflowPlanningConfig(**value)
    if isinstance(value, str):
        # String is treated as LLM model name
        return WorkflowPlanningConfig(enabled=True, llm=value)
    return None


def resolve_memory_config(value: Any) -> Optional[WorkflowMemoryConfig]:
    """Resolve memory parameter to WorkflowMemoryConfig or None."""
    if value is None or value is False:
        return None
    if value is True:
        return WorkflowMemoryConfig()
    if isinstance(value, WorkflowMemoryConfig):
        return value
    if isinstance(value, dict):
        return WorkflowMemoryConfig(**value)
    # Instance check - if it has search/add methods, it's a memory instance
    if hasattr(value, 'search') and hasattr(value, 'add'):
        return value  # Return instance directly
    return None


def resolve_hooks_config(value: Any) -> Optional[WorkflowHooksConfig]:
    """Resolve hooks parameter to WorkflowHooksConfig or None."""
    if value is None:
        return None
    if isinstance(value, WorkflowHooksConfig):
        return value
    if isinstance(value, dict):
        return WorkflowHooksConfig(**value)
    return None


def resolve_step_context_config(value: Any) -> Optional[WorkflowStepContextConfig]:
    """Resolve step context parameter."""
    if value is None or value is False:
        return None
    if value is True:
        return WorkflowStepContextConfig()
    if isinstance(value, WorkflowStepContextConfig):
        return value
    if isinstance(value, dict):
        return WorkflowStepContextConfig(**value)
    if isinstance(value, list):
        # List of step names
        return WorkflowStepContextConfig(from_steps=value)
    return None


def resolve_step_output_config(value: Any) -> Optional[WorkflowStepOutputConfig]:
    """Resolve step output parameter."""
    if value is None:
        return None
    if isinstance(value, WorkflowStepOutputConfig):
        return value
    if isinstance(value, dict):
        return WorkflowStepOutputConfig(**value)
    if isinstance(value, str):
        # String is treated as output file
        return WorkflowStepOutputConfig(file=value)
    return None


def resolve_step_execution_config(value: Any) -> WorkflowStepExecutionConfig:
    """Resolve step execution parameter."""
    presets = {
        "fast": WorkflowStepExecutionConfig(max_retries=1, quality_check=False),
        "balanced": WorkflowStepExecutionConfig(max_retries=3, quality_check=True),
        "thorough": WorkflowStepExecutionConfig(max_retries=5, quality_check=True),
    }
    if value is None:
        return WorkflowStepExecutionConfig()
    if isinstance(value, WorkflowStepExecutionConfig):
        return value
    if isinstance(value, dict):
        return WorkflowStepExecutionConfig(**value)
    if isinstance(value, str) and value in presets:
        return presets[value]
    return WorkflowStepExecutionConfig()


def resolve_step_routing_config(value: Any) -> Optional[WorkflowStepRoutingConfig]:
    """Resolve step routing parameter."""
    if value is None:
        return None
    if isinstance(value, WorkflowStepRoutingConfig):
        return value
    if isinstance(value, dict):
        return WorkflowStepRoutingConfig(**value)
    if isinstance(value, list):
        # List of next step names
        return WorkflowStepRoutingConfig(next_steps=value)
    return None


# =============================================================================
# Type Aliases
# =============================================================================

WorkflowOutputParam = Union[str, bool, WorkflowOutputConfig, None]
WorkflowPlanningParam = Union[str, bool, WorkflowPlanningConfig, None]
WorkflowMemoryParam = Union[bool, WorkflowMemoryConfig, Any, None]  # Any = instance
WorkflowHooksParam = Union[WorkflowHooksConfig, Dict[str, Callable], None]

StepContextParam = Union[bool, List[str], WorkflowStepContextConfig, None]
StepOutputParam = Union[str, WorkflowStepOutputConfig, None]
StepExecutionParam = Union[str, WorkflowStepExecutionConfig, None]
StepRoutingParam = Union[List[str], WorkflowStepRoutingConfig, None]


__all__ = [
    # Enums
    "WorkflowOutputPreset",
    "WorkflowStepExecutionPreset",
    # Workflow configs
    "WorkflowOutputConfig",
    "WorkflowPlanningConfig",
    "WorkflowMemoryConfig",
    "WorkflowHooksConfig",
    # Step configs
    "WorkflowStepContextConfig",
    "WorkflowStepOutputConfig",
    "WorkflowStepExecutionConfig",
    "WorkflowStepRoutingConfig",
    # Resolution helpers
    "resolve_param",
    "resolve_output_config",
    "resolve_planning_config",
    "resolve_memory_config",
    "resolve_hooks_config",
    "resolve_step_context_config",
    "resolve_step_output_config",
    "resolve_step_execution_config",
    "resolve_step_routing_config",
    # Type aliases
    "WorkflowOutputParam",
    "WorkflowPlanningParam",
    "WorkflowMemoryParam",
    "WorkflowHooksParam",
    "StepContextParam",
    "StepOutputParam",
    "StepExecutionParam",
    "StepRoutingParam",
]
