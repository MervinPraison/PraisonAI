"""
Workflow Configuration Classes for PraisonAI Agents.

Provides dataclasses for consolidated workflow feature configuration:
- WorkflowOutputConfig: Output and verbosity settings
- WorkflowPlanningConfig: Planning mode settings
- WorkflowMemoryConfig: Memory configuration
- WorkflowHooksConfig: Workflow lifecycle callbacks
- TaskContextConfig: Step context settings
- TaskOutputConfig: Step output settings
- TaskExecutionConfig: Step execution settings
- TaskRoutingConfig: Step routing/branching settings

All configs follow the workflow-centric pattern with precedence:
Instance > Config > Dict > Array > String > Bool > Default

Uses the CANONICAL resolver from param_resolver.py for DRY resolution.

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


# WorkflowOutputConfig is now an alias to OutputConfig for DRY approach
# Workflows use the same output configuration as Agent
# Import OutputConfig and alias it for backward compatibility
from ..config.feature_configs import OutputConfig as WorkflowOutputConfig


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
# Task-Level Config Classes
# =============================================================================

@dataclass
class TaskContextConfig:
    """
    Configuration for step context handling.
    
    Consolidates: context_from, retain_full_context
    
    Usage:
        Task(
            name="step1",
            context=TaskContextConfig(from_steps=["step0"], retain_full=True)
        )
    """
    from_steps: Optional[List[str]] = None
    retain_full: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {"from_steps": self.from_steps, "retain_full": self.retain_full}


@dataclass
class TaskOutputConfig:
    """
    Configuration for step output handling.
    
    Consolidates: output_file, output_json, output_pydantic, output_variable
    
    Usage:
        Task(
            name="step1",
            output=TaskOutputConfig(file="output.txt", variable="result")
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


class TaskExecutionPreset(str, Enum):
    """Execution preset names for workflow steps."""
    FAST = "fast"
    BALANCED = "balanced"
    THOROUGH = "thorough"


@dataclass
class TaskExecutionConfig:
    """
    Configuration for step execution behavior.
    
    Consolidates: async_execution, quality_check, rerun, max_retries, on_error
    
    Usage:
        # Preset
        Task(name="step1", execution="thorough")
        
        # Config
        Task(
            name="step1",
            execution=TaskExecutionConfig(async_exec=True, max_retries=5)
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
class TaskRoutingConfig:
    """
    Configuration for step routing/branching.
    
    Consolidates: next_steps, branch_condition
    
    Usage:
        Task(
            name="decision",
            routing=TaskRoutingConfig(
                branches={"success": ["step2"], "failure": ["step3"]}
            )
        )
    """
    next_steps: Optional[List[str]] = None
    branches: Optional[Dict[str, List[str]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {"next_steps": self.next_steps, "branches": self.branches}


# =============================================================================
# Precedence Resolution Helper - Uses CANONICAL resolver
# =============================================================================

def resolve_param(
    value: Any,
    config_class: type,
    presets: Optional[Dict[str, Any]] = None,
    default: Any = None,
    instance_check: Optional[Callable[[Any], bool]] = None,
    array_mode: Optional[str] = None,
) -> Any:
    """
    Resolve a consolidated parameter following precedence rules.
    
    DEPRECATED: This is a wrapper around the canonical resolver for backward compatibility.
    New code should use `from ..config.param_resolver import resolve` directly.
    
    Precedence: Instance > Config > Dict > Array > String > Bool > Default
    """
    # Import canonical resolver
    from ..config.param_resolver import resolve as canonical_resolve, ArrayMode
    
    # Map string array_mode to ArrayMode enum
    array_mode_map = {
        "preset_override": ArrayMode.PRESET_OVERRIDE,
        "step_names": ArrayMode.STEP_NAMES,
        "passthrough": ArrayMode.PASSTHROUGH,
    }
    canonical_array_mode = array_mode_map.get(array_mode) if array_mode else None
    
    # Convert presets from config instances to dicts for canonical resolver
    presets_dict = None
    if presets:
        presets_dict = {}
        for key, val in presets.items():
            if hasattr(val, 'to_dict'):
                presets_dict[key] = val.to_dict()
            elif hasattr(val, '__dataclass_fields__'):
                from dataclasses import asdict
                presets_dict[key] = asdict(val)
            else:
                presets_dict[key] = val
    
    return canonical_resolve(
        value=value,
        param_name="workflow_param",
        config_class=config_class,
        presets=presets_dict,
        default=default,
        instance_check=instance_check,
        array_mode=canonical_array_mode,
    )


def resolve_output_config(value: Any):
    """Resolve output parameter using canonical OUTPUT_PRESETS (DRY approach).
    
    Supports: None, str preset, list [preset, overrides], OutputConfig, dict
    
    Uses the same OUTPUT_PRESETS as Agent for consistency.
    """
    from ..config.param_resolver import resolve, ArrayMode
    from ..config.presets import OUTPUT_PRESETS
    from ..config.feature_configs import OutputConfig
    
    result = resolve(
        value=value,
        param_name="output",
        config_class=OutputConfig,
        presets=OUTPUT_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
        default=OutputConfig(),  # Default is silent mode
    )
    return result if result else OutputConfig()


def resolve_planning_config(value: Any) -> Optional[WorkflowPlanningConfig]:
    """Resolve planning parameter to WorkflowPlanningConfig using canonical resolver."""
    from ..config.param_resolver import resolve, ArrayMode
    
    result = resolve(
        value=value,
        param_name="planning",
        config_class=WorkflowPlanningConfig,
        string_mode="llm_model",
        array_mode=ArrayMode.PRESET_OVERRIDE,
        default=None,
    )
    return result


def resolve_memory_config(value: Any) -> Optional[WorkflowMemoryConfig]:
    """Resolve memory parameter to WorkflowMemoryConfig using canonical resolver."""
    from ..config.param_resolver import resolve, ArrayMode
    from ..config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
    
    result = resolve(
        value=value,
        param_name="memory",
        config_class=WorkflowMemoryConfig,
        presets=MEMORY_PRESETS,
        url_schemes=MEMORY_URL_SCHEMES,
        instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
        array_mode=ArrayMode.SINGLE_OR_LIST,
        default=None,
    )
    return result


def resolve_hooks_config(value: Any) -> Optional[WorkflowHooksConfig]:
    """Resolve hooks parameter to WorkflowHooksConfig using canonical resolver."""
    from ..config.param_resolver import resolve, ArrayMode
    
    result = resolve(
        value=value,
        param_name="hooks",
        config_class=WorkflowHooksConfig,
        array_mode=ArrayMode.PASSTHROUGH,
        default=None,
    )
    return result


def resolve_step_context_config(value: Any) -> Optional[TaskContextConfig]:
    """Resolve step context parameter using canonical resolver."""
    from ..config.param_resolver import resolve, ArrayMode
    
    result = resolve(
        value=value,
        param_name="context",
        config_class=TaskContextConfig,
        array_mode=ArrayMode.STEP_NAMES,
        default=None,
    )
    return result


def resolve_step_output_config(value: Any) -> Optional[TaskOutputConfig]:
    """Resolve step output parameter using canonical resolver."""
    # Handle string -> file conversion directly (string = output file path)
    if isinstance(value, str):
        return TaskOutputConfig(file=value)
    
    # Handle config instance
    if isinstance(value, TaskOutputConfig):
        return value
    
    # Handle dict
    if isinstance(value, dict):
        return TaskOutputConfig(**value)
    
    # None or other
    return None


def resolve_step_execution_config(value: Any) -> TaskExecutionConfig:
    """Resolve step execution parameter using canonical resolver."""
    from ..config.param_resolver import resolve, ArrayMode
    from ..config.presets import WORKFLOW_STEP_EXECUTION_PRESETS
    
    result = resolve(
        value=value,
        param_name="execution",
        config_class=TaskExecutionConfig,
        presets=WORKFLOW_STEP_EXECUTION_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
        default=TaskExecutionConfig(),
    )
    return result if result else TaskExecutionConfig()


def resolve_step_routing_config(value: Any) -> Optional[TaskRoutingConfig]:
    """Resolve step routing parameter using canonical resolver."""
    from ..config.param_resolver import resolve, ArrayMode
    
    result = resolve(
        value=value,
        param_name="routing",
        config_class=TaskRoutingConfig,
        array_mode=ArrayMode.STEP_NAMES,
        default=None,
    )
    return result


# =============================================================================
# Type Aliases
# =============================================================================

WorkflowOutputParam = Union[str, bool, WorkflowOutputConfig, None]
WorkflowPlanningParam = Union[str, bool, WorkflowPlanningConfig, None]
WorkflowMemoryParam = Union[bool, WorkflowMemoryConfig, Any, None]  # Any = instance
WorkflowHooksParam = Union[WorkflowHooksConfig, Dict[str, Callable], None]

StepContextParam = Union[bool, List[str], TaskContextConfig, None]
StepOutputParam = Union[str, TaskOutputConfig, None]
StepExecutionParam = Union[str, TaskExecutionConfig, None]
StepRoutingParam = Union[List[str], TaskRoutingConfig, None]


__all__ = [
    # Enums
    "WorkflowOutputPreset",
    "TaskExecutionPreset",
    # Workflow configs
    "WorkflowOutputConfig",
    "WorkflowPlanningConfig",
    "WorkflowMemoryConfig",
    "WorkflowHooksConfig",
    # Step configs
    "TaskContextConfig",
    "TaskOutputConfig",
    "TaskExecutionConfig",
    "TaskRoutingConfig",
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
