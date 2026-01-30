"""
Workflows System for PraisonAI Agents.

Provides reusable multi-step workflows similar to Windsurf's Workflows,
allowing users to define and execute complex task sequences.

Features:
- YAML/Markdown workflow definitions
- Auto-discovery from .praison/workflows/
- Step-by-step execution with context passing
- Variable substitution
- Conditional steps
- Lazy loading for performance

Storage Structure:
    .praison/workflows/
    ├── deploy.md           # Deployment workflow
    ├── test.md             # Testing workflow
    └── review.md           # Code review workflow
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field

from .workflow_configs import (
    WorkflowPlanningConfig, WorkflowMemoryConfig,
    TaskContextConfig, TaskOutputConfig, TaskExecutionConfig, TaskRoutingConfig,
)
from ..task.task import Task

logger = logging.getLogger(__name__)


def _parse_json_output(output: Any, step_name: str = "step") -> Any:
    """
    Parse JSON from LLM output if it's a string.
    
    Handles:
    - Direct JSON strings: '{"key": "value"}'
    - Markdown code blocks: ```json\n{"key": "value"}\n```
    - LLM echoing schema: {'type': 'array', 'items': [...]} -> extract items
    
    Returns:
        Parsed dict/list if successful, original output otherwise
    """
    if not isinstance(output, str) or not output:
        # Handle LLM echoing schema structure even for non-string outputs
        if isinstance(output, dict):
            return _extract_from_schema_echo(output)
        return output
    
    # Try direct JSON parse first
    try:
        parsed = json.loads(output)
        # Check if LLM echoed the schema structure
        if isinstance(parsed, dict):
            parsed = _extract_from_schema_echo(parsed)
        return parsed
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code block
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', output)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1).strip())
            if isinstance(parsed, dict):
                parsed = _extract_from_schema_echo(parsed)
            return parsed
        except json.JSONDecodeError:
            pass
    
    # Try finding JSON object/array in text
    # Look for {...} or [...]
    for pattern in [r'(\{[^}]+\})', r'(\[[^\]]+\])']:
        match = re.search(pattern, output)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    parsed = _extract_from_schema_echo(parsed)
                return parsed
            except json.JSONDecodeError:
                continue
    
    # Return original if can't parse
    logger.debug(f"Could not parse JSON from step '{step_name}' output")
    return output


def _extract_from_schema_echo(data: dict) -> Any:
    """
    Extract actual data when LLM echoes the JSON schema structure.
    
    Common patterns:
    - {'type': 'array', 'items': [...]} -> return [...]
    - {'type': 'object', 'properties': {...}, 'data': {...}} -> return data
    - {'items': [...]} -> return [...] (native structured output wrapper)
    - {'keywords': [...]} -> return as-is (normal output)
    
    Args:
        data: Dict that might contain echoed schema
        
    Returns:
        Extracted data or original dict
    """
    # Check if this looks like a schema echo with 'type' and actual data
    if 'type' in data:
        data_type = data.get('type')
        
        # Array schema echo: {'type': 'array', 'items': [...]}
        if data_type == 'array' and 'items' in data:
            items = data['items']
            # If items is a list, that's our actual data
            if isinstance(items, list):
                logger.debug("Extracted items from schema-echoed array output")
                return items
        
        # Object schema echo: {'type': 'object', 'properties': {...}, 'data': {...}}
        if data_type == 'object':
            # Check for actual data field
            if 'data' in data and isinstance(data['data'], dict):
                logger.debug("Extracted data from schema-echoed object output")
                return data['data']
    
    # Handle native structured output wrapper: {'items': [...]}
    # This is created by _build_response_format when wrapping arrays
    if 'items' in data and len(data) == 1 and isinstance(data['items'], list):
        logger.debug("Extracted items from native structured output array wrapper")
        return data['items']
    
    # Not a schema echo, return as-is
    return data


@dataclass
class WorkflowContext:
    """Context passed to step handlers. Contains all information about the current workflow state."""
    input: str = ""  # Original workflow input
    previous_result: Optional[str] = None  # Output from previous step
    current_step: str = ""  # Current step name
    variables: Dict[str, Any] = field(default_factory=dict)  # All workflow variables
    
@dataclass
class StepResult:
    """Result returned from step handlers."""
    output: str = ""  # Step output content
    stop_workflow: bool = False  # If True, stop the entire workflow early
    variables: Dict[str, Any] = field(default_factory=dict)  # Variables to add/update

# Aliases for backward compatibility
StepInput = WorkflowContext
StepOutput = StepResult


# =============================================================================
# Workflow Pattern Helpers
# =============================================================================

@dataclass
class Route:
    """
    Decision-based branching. Routes to different steps based on previous output.
    
    Usage:
        workflow = Workflow(steps=[
            decision_maker,
            route({
                "approve": [approve_step],
                "reject": [reject_step],
                "default": [fallback_step]
            })
        ])
    """
    routes: Dict[str, List] = field(default_factory=dict)
    default: Optional[List] = None
    
    def __init__(self, routes: Dict[str, List], default: Optional[List] = None):
        self.routes = routes
        self.default = default or routes.get("default", [])


@dataclass  
class Parallel:
    """
    Execute multiple steps concurrently and combine results.
    
    Usage:
        workflow = Workflow(steps=[
            parallel([agent1, agent2, agent3]),
            aggregator
        ])
    """
    steps: List = field(default_factory=list)
    
    def __init__(self, steps: List):
        self.steps = steps


@dataclass
class Loop:
    """
    Iterate over a list or CSV file, executing step(s) for each item.
    
    Usage:
        # Loop over list variable (sequential) - single step
        workflow = Workflow(
            steps=[loop(processor, over="items")],
            variables={"items": ["a", "b", "c"]}
        )
        
        # Loop over CSV file
        workflow = Workflow(steps=[
            loop(processor, from_csv="data.csv")
        ])
        
        # Parallel loop over items (concurrent execution)
        workflow = Workflow(
            steps=[loop(processor, over="items", parallel=True)],
            variables={"items": ["a", "b", "c"]}
        )
        
        # Parallel with limited workers
        workflow = Workflow(
            steps=[loop(processor, over="items", parallel=True, max_workers=4)],
            variables={"items": ["a", "b", "c"]}
        )
        
        # Multi-step loop (NEW) - execute multiple steps per iteration
        workflow = Workflow(
            steps=[loop(
                steps=[researcher, writer, publisher],  # Multiple steps
                over="topics",
                parallel=True,
                max_workers=4
            )],
            variables={"topics": [...]}
        )
    """
    step: Any = None  # Single step (backward compat)
    steps: Optional[List[Any]] = None  # Multiple steps (NEW)
    over: Optional[str] = None  # Variable name containing list
    from_csv: Optional[str] = None  # CSV file path
    from_file: Optional[str] = None  # Text file path (one item per line)
    var_name: str = "item"  # Variable name for current item
    parallel: bool = False  # Execute iterations in parallel
    max_workers: Optional[int] = None  # Max parallel workers (None = unlimited)
    output_variable: Optional[str] = None  # Store loop results in this variable name
    
    def __init__(
        self, 
        step: Any = None,
        steps: Optional[List[Any]] = None,
        over: Optional[str] = None,
        from_csv: Optional[str] = None,
        from_file: Optional[str] = None,
        var_name: str = "item",
        parallel: bool = False,
        max_workers: Optional[int] = None,
        output_variable: Optional[str] = None
    ):
        # Validation: cannot have both step and steps
        if step is not None and steps is not None:
            raise ValueError("Cannot specify both 'step' and 'steps'")
        # Validation: must have at least one
        if step is None and steps is None:
            raise ValueError("Loop requires 'step' or 'steps'")
        # Validation: steps cannot be empty
        if steps is not None and len(steps) == 0:
            raise ValueError("Loop 'steps' cannot be empty")
        
        self.step = step
        self.steps = steps
        self.over = over
        self.from_csv = from_csv
        self.from_file = from_file
        self.var_name = var_name
        self.parallel = parallel
        self.max_workers = max_workers
        self.output_variable = output_variable


@dataclass
class Repeat:
    """
    Repeat a step until a condition is met (evaluator-optimizer pattern).
    
    Usage:
        workflow = Workflow(steps=[
            repeat(
                generator,
                until=lambda ctx: "done" in ctx.previous_result.lower(),
                max_iterations=5
            )
        ])
    """
    step: Any = None
    until: Optional[Callable[[WorkflowContext], bool]] = None
    max_iterations: int = 10
    
    def __init__(
        self,
        step: Any,
        until: Optional[Callable[[WorkflowContext], bool]] = None,
        max_iterations: int = 10
    ):
        self.step = step
        self.until = until
        self.max_iterations = max_iterations


# Convenience functions for cleaner API
def route(routes: Dict[str, List], default: Optional[List] = None) -> Route:
    """Create a routing decision point."""
    return Route(routes=routes, default=default)

def parallel(steps: List) -> Parallel:
    """Execute steps in parallel."""
    return Parallel(steps=steps)

def loop(step: Any = None, steps: Optional[List[Any]] = None,
         over: Optional[str] = None, from_csv: Optional[str] = None, 
         from_file: Optional[str] = None, var_name: str = "item",
         parallel: bool = False, max_workers: Optional[int] = None,
         output_variable: Optional[str] = None) -> Loop:
    """Loop over items executing step(s) for each.
    
    Args:
        step: Single step (agent/function) to execute for each item (backward compat)
        steps: Multiple steps to execute sequentially for each item (NEW)
        over: Variable name containing the list to iterate over
        from_csv: Path to CSV file to read items from
        from_file: Path to text file with one item per line
        var_name: Variable name for current item (default: "item")
        parallel: If True, execute iterations in parallel (default: False)
        max_workers: Max parallel workers when parallel=True (default: None = unlimited)
        output_variable: Variable name to store all loop outputs (default: None = "loop_outputs")
    
    Returns:
        Loop object configured for iteration
    """
    return Loop(step=step, steps=steps, over=over, from_csv=from_csv, from_file=from_file, 
                var_name=var_name, parallel=parallel, max_workers=max_workers,
                output_variable=output_variable)


def repeat(step: Any, until: Optional[Callable[[WorkflowContext], bool]] = None,
           max_iterations: int = 10) -> Repeat:
    """Repeat step until condition is met."""
    return Repeat(step=step, until=until, max_iterations=max_iterations)


@dataclass
class Include:
    """
    Include another recipe or workflow as a workflow step.
    
    Enables modular composition - recipes can include other recipes or workflows.
    
    Usage:
        workflow = Workflow(steps=[
            content_writer,
            include("wordpress-publisher"),  # Include another recipe
            include(workflow=my_other_workflow),  # Include another workflow
        ])
        
    YAML syntax:
        steps:
          - agent: content_writer
          - include: wordpress-publisher
          
        # Or with configuration:
          - include:
              recipe: wordpress-publisher
              input: "{{previous_output}}"
    """
    recipe: Optional[str] = None  # Recipe name or path
    workflow: Optional[Any] = None  # Workflow instance for composition
    input: Optional[str] = None  # Input override (default: previous_output)
    
    def __init__(self, recipe: Optional[str] = None, workflow: Optional[Any] = None, input: Optional[str] = None):
        if recipe is None and workflow is None:
            raise ValueError("Either 'recipe' or 'workflow' must be provided")
        self.recipe = recipe
        self.workflow = workflow
        self.input = input


def include(recipe: Optional[str] = None, workflow: Optional[Any] = None, input: Optional[str] = None) -> Include:
    """Include another recipe or workflow as a workflow step.
    
    Args:
        recipe: Recipe name or path to include
        workflow: Workflow instance to include
        input: Input override (default: previous_output)
    
    Returns:
        Include object for workflow composition
    """
    return Include(recipe=recipe, workflow=workflow, input=input)


# Maximum nesting depth for patterns (prevents stack overflow)
MAX_NESTING_DEPTH = 5


@dataclass
class If:
    """
    Conditional branching pattern for workflows.
    
    Evaluates a condition and executes either then_steps or else_steps.
    
    Usage:
        workflow = Workflow(steps=[
            if_(
                condition="{{score}} > 80",
                then_steps=[approve_step],
                else_steps=[reject_step]
            )
        ])
        
    YAML syntax:
        steps:
          - if:
              condition: "{{score}} > 80"
              then:
                - agent: approver
              else:
                - agent: rejector
    
    Supported condition formats:
        - Numeric comparison: "{{var}} > 80", "{{var}} >= 50", "{{var}} < 10"
        - String equality: "{{var}} == approved", "{{var}} != rejected"
        - Contains check: "error in {{message}}", "{{status}} contains success"
        - Boolean: "{{flag}}" (truthy check)
    """
    condition: str = ""  # Condition expression with {{var}} placeholders
    then_steps: List[Any] = field(default_factory=list)  # Steps if condition is true
    else_steps: Optional[List[Any]] = None  # Steps if condition is false (optional)
    
    def __init__(
        self,
        condition: str,
        then_steps: List[Any],
        else_steps: Optional[List[Any]] = None
    ):
        self.condition = condition
        self.then_steps = then_steps
        self.else_steps = else_steps or []


def when(
    condition: str,
    then_steps: List[Any],
    else_steps: Optional[List[Any]] = None
) -> If:
    """
    Create a conditional branching step.
    
    This is the preferred function for conditional branching (cleaner name than if_).
    
    Args:
        condition: Condition expression with {{var}} placeholders
        then_steps: Steps to execute if condition is true
        else_steps: Steps to execute if condition is false (optional)
    
    Returns:
        If object for conditional execution
    
    Example:
        when(
            condition="{{score}} > 80",
            then_steps=[approve_agent],
            else_steps=[reject_agent]
        )
    """
    return If(condition=condition, then_steps=then_steps, else_steps=else_steps)


def if_(
    condition: str,
    then_steps: List[Any],
    else_steps: Optional[List[Any]] = None
) -> If:
    """
    Create a conditional branching step.
    
    Alias for :func:`when`. Both functions work identically.
    
    Args:
        condition: Condition expression with {{var}} placeholders
        then_steps: Steps to execute if condition is true
        else_steps: Steps to execute if condition is false (optional)
    
    Returns:
        If object for conditional execution
    """
    return If(condition=condition, then_steps=then_steps, else_steps=else_steps)



@dataclass
class Workflow:
    """
    A complete workflow with multiple steps.
    
    Workflow-centric API with consolidated feature parameters.
    All params follow precedence: Instance > Config > String > Bool > Default
    
    Usage:
        from praisonaiagents import Workflow, Agent
        
        # Simple workflow
        workflow = Workflow(
            steps=[Agent(instructions="Write content"), Agent(instructions="Edit content")],
            output="verbose",
        )
        result = workflow.run("Write about AI")
        
        # With consolidated configs
        from praisonaiagents.workflows import WorkflowOutputConfig, WorkflowPlanningConfig
        
        workflow = Workflow(
            steps=[...],
            output=WorkflowOutputConfig(verbose=True, stream=True),
            planning=WorkflowPlanningConfig(llm="gpt-4o", reasoning=True),
            hooks=WorkflowHooksConfig(on_step_complete=my_callback),
        )
    """
    name: str = "Workflow"
    description: str = ""
    steps: List = field(default_factory=list)  # Can be Task, Agent, or function
    variables: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    
    # Default configuration for all steps
    default_agent_config: Optional[Dict[str, Any]] = None  # Default agent for all steps
    default_llm: Optional[str] = None  # Default LLM model
    
    # Process type: "sequential" (default) or "hierarchical" (manager-based validation)
    process: str = "sequential"  # "sequential", "hierarchical"
    manager_llm: Optional[str] = None  # LLM for manager agent (hierarchical mode)
    
    # ============================================================
    # CONSOLIDATED FEATURE PARAMS (workflow-centric API)
    # Precedence: Instance > Config > Array > Dict > String > Bool > Default
    # Workflow is "Agents in an organised way" - supports same params as Agents
    # ============================================================
    output: Optional[Any] = None  # Union[str, WorkflowOutputConfig] - verbose/stream
    planning: Optional[Any] = False  # Union[bool, str, WorkflowPlanningConfig] - planning mode
    memory: Optional[Any] = None  # Union[bool, WorkflowMemoryConfig, instance] - memory
    hooks: Optional[Any] = None  # WorkflowHooksConfig - lifecycle callbacks
    context: Optional[Any] = True  # Union[bool, ManagerConfig, ContextManager] - context management (enabled by default for workflows)
    # NEW: Agent-like consolidated params for feature parity
    autonomy: Optional[Any] = None  # Union[bool, AutonomyConfig] - agent autonomy
    knowledge: Optional[Any] = None  # Union[bool, List[str], KnowledgeConfig] - RAG
    guardrails: Optional[Any] = None  # Union[bool, Callable, GuardrailConfig] - validation
    web: Optional[Any] = None  # Union[bool, WebConfig] - web search/fetch
    reflection: Optional[Any] = None  # Union[bool, ReflectionConfig] - self-reflection
    execution: Optional[Any] = None  # Union[str, ExecutionConfig] - execution control
    caching: Optional[Any] = None  # Union[bool, CachingConfig] - caching
    
    # ============================================================
    # ROBUSTNESS PARAMS (debugging & audit trail)
    # ============================================================
    history: bool = False  # Enable execution history tracking for debugging
    
    # Status tracking
    status: str = "not_started"  # not_started, running, completed, failed
    step_statuses: Dict[str, str] = field(default_factory=dict)  # {step_name: status}
    
    # Private resolved fields (set in __post_init__)
    _verbose: bool = field(default=False, repr=False)
    _stream: bool = field(default=True, repr=False)
    _output_config: Optional[Any] = field(default=None, repr=False)  # Full OutputConfig for propagation
    _planning_enabled: bool = field(default=False, repr=False)
    _planning_llm: Optional[str] = field(default=None, repr=False)
    _reasoning: bool = field(default=False, repr=False)
    _memory_config: Optional[Any] = field(default=None, repr=False)
    _hooks_config: Optional[Any] = field(default=None, repr=False)
    _context_manager: Optional[Any] = field(default=None, repr=False)
    _context_manager_initialized: bool = field(default=False, repr=False)
    _session_dedup_cache: Optional[Any] = field(default=None, repr=False)  # Shared session deduplication cache
    # NEW: Resolved configs for agent-like params (for propagation to steps/agents)
    _autonomy_config: Optional[Any] = field(default=None, repr=False)
    _knowledge_config: Optional[Any] = field(default=None, repr=False)
    _guardrails_config: Optional[Any] = field(default=None, repr=False)
    _web_config: Optional[Any] = field(default=None, repr=False)
    _reflection_config: Optional[Any] = field(default=None, repr=False)
    # Execution history for debugging (only populated when history=True)
    _execution_history: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    
    def __post_init__(self):
        """Resolve consolidated params to internal values."""
        from .workflow_configs import (
            resolve_output_config, resolve_planning_config,
            resolve_memory_config, resolve_hooks_config,
        )
        
        # Resolve output param - now uses OUTPUT_PRESETS (same as Agent)
        output_cfg = resolve_output_config(self.output)
        self._output_config = output_cfg  # Store full config for propagation
        self._verbose = getattr(output_cfg, 'verbose', False) if output_cfg else False
        self._stream = getattr(output_cfg, 'stream', True) if output_cfg else True
        
        # Enable status/trace output if configured (same as Agent)
        if output_cfg:
            status_trace = getattr(output_cfg, 'status_trace', False)
            actions_trace = getattr(output_cfg, 'actions_trace', False)
            json_output = getattr(output_cfg, 'json_output', False)
            simple_output = getattr(output_cfg, 'simple_output', False)
            metrics = getattr(output_cfg, 'metrics', False)
            
            if status_trace:
                try:
                    from ..output.trace import enable_trace_output, is_trace_output_enabled
                    if not is_trace_output_enabled():
                        enable_trace_output(use_color=True, show_timestamps=True)
                except ImportError:
                    pass
            elif actions_trace:
                try:
                    from ..output.status import enable_status_output, is_status_output_enabled
                    if not is_status_output_enabled():
                        output_format = "jsonl" if json_output else "text"
                        enable_status_output(
                            redact=True,
                            use_color=True,
                            format=output_format,
                            show_timestamps=not simple_output,
                            show_metrics=metrics
                        )
                except ImportError:
                    pass
        
        # Resolve planning param
        planning_cfg = resolve_planning_config(self.planning)
        if planning_cfg:
            self._planning_enabled = planning_cfg.enabled
            self._planning_llm = planning_cfg.llm
            self._reasoning = planning_cfg.reasoning
        else:
            self._planning_enabled = False
            self._planning_llm = None
            self._reasoning = False
        
        # Resolve memory param
        self._memory_config = resolve_memory_config(self.memory)
        
        # Resolve hooks param
        self._hooks_config = resolve_hooks_config(self.hooks)
        
        # Resolve NEW agent-like params using canonical resolver
        # These are stored for propagation to steps/agents
        from ..config.param_resolver import resolve, ArrayMode
        from ..config.presets import (
            WEB_PRESETS, REFLECTION_PRESETS, GUARDRAIL_PRESETS,
            AUTONOMY_PRESETS, KNOWLEDGE_PRESETS,
        )
        try:
            from ..config.feature_configs import (
                AutonomyConfig, KnowledgeConfig, GuardrailConfig,
                WebConfig, ReflectionConfig,
            )
        except ImportError:
            AutonomyConfig = KnowledgeConfig = GuardrailConfig = None
            WebConfig = ReflectionConfig = None
        
        # Resolve autonomy
        if AutonomyConfig and self.autonomy is not None:
            self._autonomy_config = resolve(
                value=self.autonomy, param_name="autonomy",
                config_class=AutonomyConfig, presets=AUTONOMY_PRESETS,
                default=None,
            )
        
        # Resolve knowledge
        if KnowledgeConfig and self.knowledge is not None:
            self._knowledge_config = resolve(
                value=self.knowledge, param_name="knowledge",
                config_class=KnowledgeConfig, presets=KNOWLEDGE_PRESETS,
                array_mode=ArrayMode.SOURCES, default=None,
            )
        
        # Resolve guardrails
        if GuardrailConfig and self.guardrails is not None:
            self._guardrails_config = resolve(
                value=self.guardrails, param_name="guardrails",
                config_class=GuardrailConfig, presets=GUARDRAIL_PRESETS,
                default=None,
            )
        
        # Resolve web
        if WebConfig and self.web is not None:
            self._web_config = resolve(
                value=self.web, param_name="web",
                config_class=WebConfig, presets=WEB_PRESETS,
                default=None,
            )
        
        # Resolve reflection
        if ReflectionConfig and self.reflection is not None:
            self._reflection_config = resolve(
                value=self.reflection, param_name="reflection",
                config_class=ReflectionConfig, presets=REFLECTION_PRESETS,
                default=None,
            )
        
        # Initialize session deduplication cache for cross-agent deduplication
        if self.context:
            try:
                from ..context.manager import SessionDeduplicationCache
                self._session_dedup_cache = SessionDeduplicationCache()
            except ImportError:
                pass
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Return execution trace for debugging.
        
        Returns a list of step execution records, each containing:
        - step: Step name
        - timestamp: ISO format timestamp
        - success: Whether the step succeeded
        - output: Truncated output (first 500 chars)
        - error: Error message if failed
        
        Only populated when history=True is set on the workflow.
        """
        return self._execution_history
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() if hasattr(s, 'to_dict') else str(s) for s in self.steps],
            "variables": self.variables,
            "file_path": self.file_path,
            "default_agent_config": self.default_agent_config,
            "default_llm": self.default_llm,
            "process": self.process,
            "manager_llm": self.manager_llm,
            "output": {"verbose": self._verbose, "stream": self._stream},
            "planning": {"enabled": self._planning_enabled, "llm": self._planning_llm, "reasoning": self._reasoning},
            "memory": self._memory_config.to_dict() if hasattr(self._memory_config, 'to_dict') else bool(self._memory_config),
            "hooks": self._hooks_config.to_dict() if hasattr(self._hooks_config, 'to_dict') else None,
        }
    
    # Property accessors for backward compatibility during transition
    @property
    def verbose(self) -> bool:
        """Get verbose setting from resolved output config."""
        return self._verbose
    
    @verbose.setter
    def verbose(self, value: bool):
        """Set verbose setting."""
        self._verbose = value
    
    @property
    def stream(self) -> bool:
        """Get stream setting from resolved output config."""
        return self._stream
    
    @property
    def planning_llm(self) -> Optional[str]:
        """Get planning LLM from resolved planning config."""
        return self._planning_llm
    
    @property
    def reasoning(self) -> bool:
        """Get reasoning setting from resolved planning config."""
        return self._reasoning
    
    @property
    def memory_config(self) -> Optional[Dict[str, Any]]:
        """Get memory config dict for backward compatibility."""
        if self._memory_config:
            if hasattr(self._memory_config, 'to_dict'):
                return self._memory_config.to_dict()
            elif isinstance(self._memory_config, dict):
                return self._memory_config
        return None
    
    @property
    def on_workflow_start(self) -> Optional[Callable]:
        """Get on_workflow_start callback from hooks config."""
        return self._hooks_config.on_workflow_start if self._hooks_config else None
    
    @property
    def on_workflow_complete(self) -> Optional[Callable]:
        """Get on_workflow_complete callback from hooks config."""
        return self._hooks_config.on_workflow_complete if self._hooks_config else None
    
    @property
    def on_step_start(self) -> Optional[Callable]:
        """Get on_step_start callback from hooks config."""
        return self._hooks_config.on_step_start if self._hooks_config else None
    
    @property
    def on_step_complete(self) -> Optional[Callable]:
        """Get on_step_complete callback from hooks config."""
        return self._hooks_config.on_step_complete if self._hooks_config else None
    
    @property
    def on_step_error(self) -> Optional[Callable]:
        """Get on_step_error callback from hooks config."""
        return self._hooks_config.on_step_error if self._hooks_config else None
    
    def _resolve_pydantic_class(self, class_name: str) -> Optional[Any]:
        """
        Resolve a Pydantic class from string reference (Option B for structured output).
        
        Looks for the class in:
        1. tools.py in the workflow's directory
        2. The global namespace
        
        Args:
            class_name: Name of the Pydantic class to resolve
            
        Returns:
            The Pydantic class if found, None otherwise
        """
        import sys
        
        # Try to find the class in tools.py from the workflow's directory
        if self.file_path:
            from pathlib import Path
            workflow_dir = Path(self.file_path).parent
            tools_path = workflow_dir / "tools.py"
            
            if tools_path.exists():
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("tools", tools_path)
                    if spec and spec.loader:
                        tools_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(tools_module)
                        
                        if hasattr(tools_module, class_name):
                            cls = getattr(tools_module, class_name)
                            # Verify it's a Pydantic model
                            if hasattr(cls, 'model_json_schema'):
                                return cls
                except Exception as e:
                    logger.debug(f"Failed to load Pydantic class from tools.py: {e}")
        
        # Try to find in already-imported modules
        for module_name, module in sys.modules.items():
            if module and hasattr(module, class_name):
                cls = getattr(module, class_name)
                if hasattr(cls, 'model_json_schema'):
                    return cls
        
        return None
    
    @classmethod
    def from_template(
        cls,
        uri: str,
        config: Optional[Dict[str, Any]] = None,
        offline: bool = False,
        **kwargs
    ) -> 'Workflow':
        """
        Create a Workflow from a template.
        
        Args:
            uri: Template URI (local path, package ref, or github ref)
                Examples:
                - "./my-template" (local path)
                - "transcript-generator" (default recipes repo)
                - "github:owner/repo/template@v1.0.0" (GitHub with version)
                - "package:agent_recipes/transcript-generator" (installed package)
            config: Optional configuration overrides
            offline: If True, only use cached templates (no network)
            **kwargs: Additional Workflow constructor arguments
            
        Returns:
            Configured Workflow instance
            
        Example:
            ```python
            from praisonaiagents import Workflow
            
            # From default recipes repo
            workflow = Workflow.from_template("transcript-generator")
            result = workflow.run("./audio.mp3")
            
            # With config overrides
            workflow = Workflow.from_template(
                "data-transformer",
                config={"output_format": "json"}
            )
            ```
        """
        try:
            # Lazy import to avoid circular dependencies and keep core SDK lean
            from praisonai.templates.loader import create_workflow_from_template
            return create_workflow_from_template(uri, config=config, offline=offline, **kwargs)
        except ImportError:
            raise ImportError(
                "Template support requires the 'praisonai' package. "
                "Install with: pip install praisonai"
            )
    
    def run(
        self,
        input: str = "",
        llm: Optional[str] = None,
        verbose: bool = False,
        stream: bool = None
    ) -> Dict[str, Any]:
        """
        Run the workflow with the given input.
        
        This is the simplest way to execute a workflow:
        
        ```python
        from praisonaiagents import Workflow, Agent
        
        workflow = Workflow(
            steps=[
                Agent(name="Writer", role="Write content"),
                my_validator_function,
                Agent(name="Editor", role="Edit content"),
            ]
        )
        result = workflow.run("Write about AI")
        ```
        
        Args:
            input: The input text/prompt for the workflow
            llm: LLM model to use (default: gpt-4o-mini)
            verbose: Print step outputs
            stream: Enable streaming responses (default: use workflow's stream setting)
            
        Returns:
            Dict with 'output' (final result) and 'steps' (all step results)
        """
        # Use default LLM if not specified
        model = llm or self.default_llm or "gpt-4o-mini"
        logger.debug(f"Workflow using model: {model} (llm={llm}, default_llm={self.default_llm})")
        
        # Use workflow verbose setting if not overridden
        verbose = verbose or self.verbose
        
        # Use workflow stream setting if not overridden
        if stream is None:
            stream = self.stream
        
        # Add input to variables
        all_variables = {**self.variables, "input": input}
        
        results = []
        previous_output = None
        
        # Update workflow status
        self.status = "running"
        
        # Set YAML-approved tools in approval context (for auto-approval of dangerous tools)
        _approval_token = None
        approve_tools = getattr(self, 'approve_tools', [])
        if approve_tools:
            from ..approval import set_yaml_approved_tools
            _approval_token = set_yaml_approved_tools(approve_tools)
        
        # Call on_workflow_start callback
        if self.on_workflow_start:
            try:
                self.on_workflow_start(self, input)
            except Exception as e:
                logger.error(f"on_workflow_start callback failed: {e}")
        
        # Planning mode - create execution plan before running
        if self.planning:
            plan = self._create_plan(input, model, verbose)
            if plan and verbose:
                print(f"📋 Execution Plan: {plan}")
            all_variables["execution_plan"] = plan
        
        # Hierarchical mode - use manager-based validation
        if self.process == "hierarchical":
            if verbose:
                print("🔄 Running workflow in hierarchical mode with manager validation")
            return self._run_hierarchical(
                input=input,
                model=model,
                verbose=verbose,
                stream=stream,
                all_variables=all_variables,
                _approval_token=_approval_token
            )
        
        # Process steps (may include Route, Parallel, Loop, Repeat)
        i = 0
        while i < len(self.steps):
            step = self.steps[i]
            
            # Handle special pattern types
            if isinstance(step, Route):
                # Decision-based routing
                route_result = self._execute_route(
                    step, previous_output, input, all_variables, model, verbose, stream
                )
                results.extend(route_result["steps"])
                previous_output = route_result["output"]
                all_variables.update(route_result.get("variables", {}))
                i += 1
                continue
                
            elif isinstance(step, Parallel):
                # Parallel execution
                parallel_result = self._execute_parallel(
                    step, previous_output, input, all_variables, model, verbose, stream
                )
                results.extend(parallel_result["steps"])
                previous_output = parallel_result["output"]
                all_variables.update(parallel_result.get("variables", {}))
                i += 1
                continue
                
            elif isinstance(step, Loop):
                # Loop over items
                loop_result = self._execute_loop(
                    step, previous_output, input, all_variables, model, verbose, stream
                )
                results.extend(loop_result["steps"])
                previous_output = loop_result["output"]
                all_variables.update(loop_result.get("variables", {}))
                i += 1
                continue
                
            elif isinstance(step, Repeat):
                # Repeat until condition
                repeat_result = self._execute_repeat(
                    step, previous_output, input, all_variables, model, verbose, stream
                )
                results.extend(repeat_result["steps"])
                previous_output = repeat_result["output"]
                all_variables.update(repeat_result.get("variables", {}))
                i += 1
                continue
                
            elif isinstance(step, Include):
                # Include another recipe
                include_result = self._execute_include(
                    step, previous_output, input, all_variables, model, verbose, stream
                )
                results.extend(include_result["steps"])
                previous_output = include_result["output"]
                all_variables.update(include_result.get("variables", {}))
                i += 1
                continue
            
            elif isinstance(step, If):
                # Conditional branching
                if_result = self._execute_if(
                    step, previous_output, input, all_variables, model, verbose, stream
                )
                results.extend(if_result["steps"])
                previous_output = if_result["output"]
                all_variables.update(if_result.get("variables", {}))
                i += 1
                continue
            
            # Normalize single step
            step = self._normalize_single_step(step, i)
            
            # Create context for handlers
            context = WorkflowContext(
                input=input,
                previous_result=str(previous_output) if previous_output else None,
                current_step=step.name,
                variables=all_variables.copy()
            )
            
            # Update step status
            if hasattr(step, 'status'):
                step.status = "running"
            self.step_statuses[step.name] = "running"
            
            # Call on_step_start callback
            if self.on_step_start:
                try:
                    self.on_step_start(step.name, context)
                except Exception as e:
                    logger.error(f"on_step_start callback failed: {e}")
            
            # Check should_run condition
            if step.should_run:
                try:
                    if not step.should_run(context):
                        if verbose:
                            print(f"⏭️ Skipped: {step.name}")
                        if hasattr(step, 'status'):
                            step.status = "skipped"
                        self.step_statuses[step.name] = "skipped"
                        i += 1
                        continue
                except Exception as e:
                    logger.error(f"should_run failed for {step.name}: {e}")
            
            # Execute step with retry and guardrail support
            output = None
            stop = False
            step_error = None
            max_retries = getattr(step, 'max_retries', 3)
            retry_count = 0
            validation_feedback = None
            
            while retry_count <= max_retries:
                step_error = None
                
                # Add validation feedback to context if retrying
                if validation_feedback:
                    context.variables["validation_feedback"] = validation_feedback
                
                try:
                    if step.handler:
                        # Custom handler function
                        result = step.handler(context)
                        if isinstance(result, StepResult):
                            output = result.output
                            stop = result.stop_workflow
                            if result.variables:
                                all_variables.update(result.variables)
                        else:
                            output = str(result)
                            
                    elif step.agent:
                        # Direct agent with tools
                        # Propagate context management to existing agent if workflow has it enabled
                        if self.context and hasattr(step.agent, '_context_manager_initialized'):
                            if not step.agent._context_manager_initialized:
                                step.agent._context_param = self.context
                            # Share session deduplication cache for cross-agent deduplication
                            if self._session_dedup_cache:
                                step.agent._session_dedup_cache = self._session_dedup_cache
                                # Also set on existing context manager if already initialized
                                if step.agent._context_manager and hasattr(step.agent._context_manager, '_session_cache'):
                                    step.agent._context_manager._session_cache = self._session_dedup_cache
                        
                        # Substitute variables in action
                        action = step.action or input
                        for key, value in all_variables.items():
                            action = action.replace(f"{{{{{key}}}}}", str(value))
                        if previous_output:
                            if "{{previous_output}}" in action:
                                action = action.replace("{{previous_output}}", str(previous_output))
                            else:
                                # Auto-append context if not explicitly referenced
                                action = f"{action}\n\nContext from previous step:\n{previous_output}"
                        action = action.replace("{{input}}", input)
                        
                        # Add reasoning prompt if enabled
                        if self.reasoning:
                            action = f"Think step by step and reason through this task:\n\n{action}"
                        
                        # Add validation feedback if retrying
                        if validation_feedback:
                            action = f"{action}\n\nPrevious attempt feedback: {validation_feedback}"
                        
                        # Check if this is a specialized agent (AudioAgent, VideoAgent, ImageAgent, OCRAgent)
                        agent_class_name = step.agent.__class__.__name__
                        if agent_class_name in ('AudioAgent', 'VideoAgent', 'ImageAgent', 'OCRAgent', 'DeepResearchAgent'):
                            # Use specialized agent dispatch
                            output = self._execute_specialized_agent(
                                step.agent, agent_class_name, action, step, all_variables, stream
                            )
                        else:
                            # Standard Agent with chat() method
                            # Handle images/attachments if present - check step.images first, then variables
                            step_attachments = getattr(step, 'images', None)
                            if not step_attachments:
                                # Check for image_path, image_url, or image in variables
                                image_var = all_variables.get('image_path') or all_variables.get('image_url') or all_variables.get('image')
                                if image_var:
                                    step_attachments = [image_var] if isinstance(image_var, str) else image_var
                                    logger.debug(f"Passing image attachment to agent: {image_var}")
                            # Get structured output options from step
                            step_output_json = getattr(step, '_output_json', None)
                            step_output_pydantic = getattr(step, '_output_pydantic', None)
                            
                            # Resolve Pydantic class from string reference (Option B)
                            # If output_pydantic is a string, try to resolve it from tools.py
                            if step_output_pydantic and isinstance(step_output_pydantic, str):
                                resolved_class = self._resolve_pydantic_class(step_output_pydantic)
                                if resolved_class:
                                    step_output_pydantic = resolved_class
                                else:
                                    logger.warning(f"Could not resolve Pydantic class '{step_output_pydantic}' from tools.py")
                                    step_output_pydantic = None
                            
                            # Build chat kwargs
                            chat_kwargs = {"stream": stream}
                            if step_attachments:
                                chat_kwargs["attachments"] = step_attachments
                            if step_output_json:
                                chat_kwargs["output_json"] = step_output_json
                            if step_output_pydantic:
                                chat_kwargs["output_pydantic"] = step_output_pydantic
                            
                            # Pass tool_choice from YAML if specified (auto, required, none)
                            # This forces the LLM to use tools when tool_choice='required'
                            yaml_tool_choice = getattr(step.agent, '_yaml_tool_choice', None)
                            if yaml_tool_choice:
                                chat_kwargs["tool_choice"] = yaml_tool_choice
                            
                            output = step.agent.chat(action, **chat_kwargs)
                            
                            # Parse JSON output if output_json was requested and output is a string
                            if step_output_json and output and isinstance(output, str):
                                output = _parse_json_output(output, step.name)
                            
                            # Handle output_pydantic if present
                            output_pydantic = getattr(step, 'output_pydantic', None)
                            if output_pydantic and output:
                                try:
                                    # Try to parse output as Pydantic model
                                    if hasattr(output_pydantic, 'model_validate_json'):
                                        parsed = output_pydantic.model_validate_json(output)
                                        output = parsed.model_dump_json()
                                except Exception as e:
                                    logger.debug(f"Pydantic parsing failed: {e}")
                            
                    elif step.action:
                        # Action with agent_config - create temporary agent
                        from ..agent.agent import Agent
                        config = step.agent_config or self.default_agent_config or {}
                        
                        # Get tools from step or config
                        step_tools = step.tools or config.get("tools", [])
                        
                        temp_agent = Agent(
                            name=config.get("name", step.name),
                            role=config.get("role", "Assistant"),
                            goal=config.get("goal", "Complete the task"),
                            llm=config.get("llm", model),
                            tools=step_tools if step_tools else None,
                            output=self.output,  # Propagate output config to child agents
                            reasoning=self.reasoning,
                            stream=stream,
                            context=self.context,  # Propagate context management to child agents
                        )
                        # Substitute variables in action
                        action = step.action
                        for key, value in all_variables.items():
                            action = action.replace(f"{{{{{key}}}}}", str(value))
                        if previous_output:
                            if "{{previous_output}}" in action:
                                action = action.replace("{{previous_output}}", str(previous_output))
                            else:
                                # Auto-append context if not explicitly referenced
                                action = f"{action}\n\nContext from previous step:\n{previous_output}"
                        action = action.replace("{{input}}", input)
                        
                        # Add reasoning prompt if enabled
                        if self.reasoning:
                            action = f"Think step by step and reason through this task:\n\n{action}"
                        
                        if validation_feedback:
                            action = f"{action}\n\nPrevious attempt feedback: {validation_feedback}"
                        
                        output = temp_agent.chat(action, stream=stream)
                        
                        # Parse JSON output if output_json was requested
                        step_output_json = getattr(step, '_output_json', None)
                        if step_output_json and output and isinstance(output, str):
                            output = _parse_json_output(output, step.name)
                        
                except Exception as e:
                    step_error = e
                    output = f"Error: {e}"
                    if self.on_step_error:
                        try:
                            self.on_step_error(step.name, e)
                        except Exception:
                            pass
                
                # Check guardrail if present (guardrails is canonical, guardrail is deprecated)
                guardrail = getattr(step, 'guardrails', None) or getattr(step, 'guardrail', None)
                if guardrail and output and not step_error:
                    try:
                        is_valid, feedback = guardrail(StepResult(output=output))
                        if not is_valid:
                            validation_feedback = str(feedback)
                            retry_count += 1
                            if verbose:
                                print(f"⚠️ {step.name} failed validation (attempt {retry_count}/{max_retries}): {feedback}")
                            continue  # Retry
                    except Exception as e:
                        logger.error(f"Guardrail failed for {step.name}: {e}")
                
                # Success - break out of retry loop
                break
            
            # Update step status
            if step_error:
                if hasattr(step, 'status'):
                    step.status = "failed"
                self.step_statuses[step.name] = "failed"
            else:
                if hasattr(step, 'status'):
                    step.status = "completed"
                self.step_statuses[step.name] = "completed"
            
            # Create step result for callback
            step_result = StepResult(output=output or "", stop_workflow=stop)
            
            # Call on_step_complete callback
            if self.on_step_complete:
                try:
                    self.on_step_complete(step.name, step_result)
                except Exception as e:
                    logger.error(f"on_step_complete callback failed: {e}")
            
            # Handle output_file - save output to file
            if hasattr(step, 'output_file') and step.output_file and output:
                try:
                    import os
                    output_path = step.output_file
                    # Substitute variables in path
                    for key, value in all_variables.items():
                        output_path = output_path.replace(f"{{{{{key}}}}}", str(value))
                    # Create directory if needed
                    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
                    with open(output_path, "w") as f:
                        f.write(str(output))
                    if verbose:
                        print(f"📁 Saved output to: {output_path}")
                except Exception as e:
                    logger.error(f"Failed to save output to file: {e}")
            
            # Store result
            results.append({
                "step": step.name,
                "output": output,
                "status": self.step_statuses.get(step.name, "completed"),
                "retries": retry_count
            })
            previous_output = output
            
            if verbose:
                print(f"✅ {step.name}: {str(output)}")
            
            # Handle early stop
            if stop:
                if verbose:
                    print(f"🛑 Workflow stopped at: {step.name}")
                break
            
            # Store output in variables
            var_name = step.output_variable or f"{step.name}_output"
            all_variables[var_name] = output
            
            # Validate output and warn about issues
            if output is None:
                logger.warning(f"⚠️  Step '{step.name}': Output is None. Agent may not have returned expected format.")
                if verbose:
                    print(f"⚠️  WARNING: Step '{step.name}' output is None!")
            else:
                # Check type against output_json schema if defined
                expected_schema = getattr(step, '_output_json', None)
                if expected_schema and isinstance(expected_schema, dict):
                    expected_type = expected_schema.get('type')
                    actual_type = type(output).__name__
                    if expected_type == 'object' and not isinstance(output, dict):
                        logger.warning(f"⚠️  Step '{step.name}': Expected object/dict, got {actual_type}")
                        if verbose:
                            print(f"⚠️  Step '{step.name}': Expected 'object', received '{actual_type}'")
                    elif expected_type == 'array' and not isinstance(output, list):
                        logger.warning(f"⚠️  Step '{step.name}': Expected array/list, got {actual_type}")
                        if verbose:
                            print(f"⚠️  Step '{step.name}': Expected 'array', received '{actual_type}'")
            
            i += 1
        
        # Update workflow status
        self.status = "completed"
        
        # Reset YAML-approved tools context if it was set
        if _approval_token is not None:
            from ..approval import reset_yaml_approved_tools
            reset_yaml_approved_tools(_approval_token)
        
        final_result = {
            "output": previous_output,
            "steps": results,
            "variables": all_variables,
            "status": self.status
        }
        
        # Call on_workflow_complete callback
        if self.on_workflow_complete:
            try:
                self.on_workflow_complete(self, final_result)
            except Exception as e:
                logger.error(f"on_workflow_complete callback failed: {e}")
        
        return final_result
    
    async def astart(
        self,
        input: str = "",
        llm: Optional[str] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """Async version of start() for async workflow execution.
        
        Args:
            input: The input text/prompt for the workflow
            llm: LLM model to use (default: gpt-4o-mini)
            verbose: Print step outputs
            
        Returns:
            Dict with 'output' (final result) and 'steps' (all step results)
        """
        import asyncio
        
        # Run the synchronous version in a thread pool
        # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
        from ..trace.context_events import copy_context_to_callable
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            copy_context_to_callable(lambda: self.run(input, llm, verbose))
        )
        return result
    
    async def arun(
        self,
        input: str = "",
        llm: Optional[str] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """Alias for astart() for backward compatibility."""
        return await self.astart(input, llm, verbose)
    
    def _run_hierarchical(
        self,
        input: str,
        model: str,
        verbose: bool,
        stream: bool,
        all_variables: Dict[str, Any],
        _approval_token: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Run workflow with hierarchical manager-based validation.
        
        In hierarchical mode, a manager agent validates each step's output
        before proceeding to the next step. If the manager rejects a step,
        the workflow stops with status='failed' and includes a failure_reason.
        
        This pattern is adapted from Process.hierarchical() for Workflow use.
        
        Args:
            input: The workflow input
            model: LLM model to use for steps
            verbose: Print step outputs
            stream: Enable streaming
            all_variables: Variables dict
            _approval_token: Token for YAML-approved tools
            
        Returns:
            Dict with output, steps, variables, status, and optionally failure_reason
        """
        from ..llm import LLM
        
        results = []
        previous_output = input
        failure_reason = None
        
        manager_model = self.manager_llm or model
        
        normalized_steps = self._normalize_steps()
        
        for i, step in enumerate(normalized_steps):
            step_name = getattr(step, 'name', f'step_{i}')
            
            if self.on_step_start:
                try:
                    self.on_step_start(self, step, i)
                except Exception as e:
                    logger.error(f"on_step_start callback failed: {e}")
            
            if hasattr(step, 'status'):
                step.status = "running"
            self.step_statuses[step_name] = "running"
            
            try:
                # Use _execute_single_step_internal which returns a dict
                step_result_internal = self._execute_single_step_internal(
                    step, previous_output, input, all_variables, model, verbose, i, stream
                )
                output = step_result_internal.get("output", "")
                stop = step_result_internal.get("stop", False)
                step_vars = step_result_internal.get("variables", {})
                all_variables.update(step_vars)
                
                step_result = {
                    "step": step_name,
                    "output": output,
                    "status": "completed"
                }
                results.append(step_result)
                
                if hasattr(step, 'status'):
                    step.status = "completed"
                self.step_statuses[step_name] = "completed"
                
                if self.on_step_complete:
                    try:
                        self.on_step_complete(self, step, step_result)
                    except Exception as e:
                        logger.error(f"on_step_complete callback failed: {e}")
                
                if stop:
                    if verbose:
                        print(f"🛑 Workflow stopped at: {step_name}")
                    break
                
                # Check if step has tools assigned
                step_has_tools = bool(getattr(step, 'tools', None) or (hasattr(step, 'agent') and getattr(step.agent, 'tools', None)))
                
                # Build tool evidence guidance for manager
                tool_evidence_guidance = ""
                if step_has_tools:
                    tool_evidence_guidance = """
4. TOOL USAGE EVIDENCE: If the step required tool usage (e.g., search_web), check for EVIDENCE in the output:
   - URLs or links (e.g., https://..., [Source](url))
   - Structured data with sources/citations
   - Specific facts with references
   - Multiple distinct items from external sources
   NOTE: The agent may have called tools successfully even if it doesn't say "I called the tool".
   Look for RESULTS from tools, not explicit statements about calling them."""
                
                validation_prompt = f"""You are reviewing the output of a workflow step.

Step Name: {step_name}
Step Action: {getattr(step, 'action', 'Execute task')}
Expected Output: {getattr(step, 'expected_output', 'Task completed successfully')}

Agent Output:
{output}

Did this step complete successfully? Consider:
1. Does the output address the task?
2. Is the output meaningful (not an error message)?
3. Does it meet the expected output criteria?{tool_evidence_guidance}

IMPORTANT: Approve if the output contains substantive content that addresses the task.
Only reject if the output is clearly an error, empty, or completely off-topic.

Respond with JSON: {{"approved": true/false, "reason": "Brief explanation"}}
"""
                
                try:
                    llm_instance = LLM(model=manager_model, verbose=False)
                    validation_response = llm_instance.get_response(
                        prompt=validation_prompt,
                        system_prompt="You are a workflow quality manager. Respond only with valid JSON.",
                        output_json=True
                    )
                    
                    if isinstance(validation_response, str):
                        import json
                        try:
                            decision_data = json.loads(validation_response)
                        except json.JSONDecodeError:
                            decision_data = {"approved": True, "reason": "Could not parse response, assuming success"}
                    elif isinstance(validation_response, dict):
                        decision_data = validation_response
                    else:
                        decision_data = {"approved": True, "reason": "Unknown response format, assuming success"}
                    
                    approved = decision_data.get("approved", True)
                    reason = decision_data.get("reason", "No reason provided")
                    
                    if verbose:
                        status_icon = "✅" if approved else "❌"
                        print(f"{status_icon} Manager validation for '{step_name}': {reason}")
                    
                    if not approved:
                        failure_reason = f"Manager rejected step '{step_name}': {reason}"
                        self.status = "failed"
                        if hasattr(step, 'status'):
                            step.status = "failed"
                        self.step_statuses[step_name] = "failed"
                        step_result["status"] = "failed"
                        step_result["failure_reason"] = failure_reason
                        
                        if self.on_step_error:
                            try:
                                self.on_step_error(self, step, Exception(failure_reason))
                            except Exception as e:
                                logger.error(f"on_step_error callback failed: {e}")
                        break
                        
                except Exception as e:
                    logger.warning(f"Manager validation failed for step '{step_name}': {e}. Continuing workflow.")
                
                previous_output = output
                
                # Store output in variables for next step's variable substitution
                # This is critical for {{agent_name}}_output references to work
                var_name = f"{step_name}_output"
                all_variables[var_name] = output
                
            except Exception as e:
                error_msg = str(e)
                if hasattr(step, 'status'):
                    step.status = "failed"
                self.step_statuses[step_name] = "failed"
                
                step_result = {
                    "step": step_name,
                    "output": f"Error: {error_msg}",
                    "status": "failed"
                }
                results.append(step_result)
                
                if self.on_step_error:
                    try:
                        self.on_step_error(self, step, e)
                    except Exception as callback_e:
                        logger.error(f"on_step_error callback failed: {callback_e}")
                
                failure_reason = f"Step '{step_name}' failed with error: {error_msg}"
                self.status = "failed"
                break
        
        if failure_reason is None:
            self.status = "completed"
        
        if _approval_token is not None:
            from ..approval import reset_yaml_approved_tools
            reset_yaml_approved_tools(_approval_token)
        
        final_result = {
            "output": previous_output,
            "steps": results,
            "variables": all_variables,
            "status": self.status
        }
        
        if failure_reason:
            final_result["failure_reason"] = failure_reason
        
        if self.on_workflow_complete:
            try:
                self.on_workflow_complete(self, final_result)
            except Exception as e:
                logger.error(f"on_workflow_complete callback failed: {e}")
        
        return final_result
    
    def _normalize_steps(self) -> List['Task']:
        """Convert mixed steps (Agent, function, Task) to Task list.
        
        This method uses _normalize_single_step to ensure consistent normalization
        and avoid duplicated code paths (DRY principle).
        """
        return [self._normalize_single_step(step, i) for i, step in enumerate(self.steps)]
    
    def _create_plan(self, input: str, model: str, verbose: bool) -> Optional[str]:
        """Create an execution plan for the workflow using LLM.
        
        Args:
            input: The workflow input
            model: LLM model to use
            verbose: Print verbose output
            
        Returns:
            Execution plan as string, or None if planning fails
        """
        try:
            from ..agent.agent import Agent
            
            # Describe the steps
            step_descriptions = []
            for i, step in enumerate(self.steps):
                if isinstance(step, Task):
                    step_descriptions.append(f"{i+1}. {step.name}: {step.description or step.action or 'Execute step'}")
                elif hasattr(step, 'name'):
                    role = getattr(step, 'role', 'Agent')
                    step_descriptions.append(f"{i+1}. {step.name} ({role})")
                elif callable(step):
                    step_descriptions.append(f"{i+1}. {getattr(step, '__name__', 'function')}")
                elif isinstance(step, (Route, Parallel, Loop, Repeat)):
                    step_descriptions.append(f"{i+1}. {type(step).__name__} pattern")
                else:
                    step_descriptions.append(f"{i+1}. Step {i+1}")
            
            steps_text = "\n".join(step_descriptions)
            
            planning_prompt = f"""You are a workflow planner. Given the following workflow steps and input, create a brief execution plan.

Workflow: {self.name}
Description: {self.description}

Steps:
{steps_text}

Input: {input}

Create a brief execution plan (2-3 sentences) describing how to best accomplish this task using the available steps. Focus on the key objectives and any important considerations."""

            planner = Agent(
                name="Planner",
                role="Workflow Planner",
                goal="Create efficient execution plans",
                llm=self.planning_llm or model,
                verbose=False
            )
            
            plan = planner.chat(planning_prompt)
            return plan
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return None
    
    def _execute_specialized_agent(
        self,
        agent: Any,
        agent_class_name: str,
        action: str,
        step: 'Task',
        variables: Dict[str, Any],
        stream: bool
    ) -> Any:
        """
        Execute a specialized agent (AudioAgent, VideoAgent, ImageAgent, OCRAgent).
        
        Dispatches to the appropriate method based on agent type and action.
        Falls back to chat() for standard Agent class.
        
        Args:
            agent: The agent instance
            agent_class_name: Name of the agent class
            action: The action/prompt to execute
            step: The workflow step containing additional config
            variables: Current workflow variables
            stream: Whether to stream output
            
        Returns:
            Output from the agent execution
        """
        # Get yaml_action which specifies the method to call
        yaml_action = getattr(agent, '_yaml_action', None) or action
        
        # AudioAgent - TTS (speech) or STT (transcribe)
        if agent_class_name == 'AudioAgent':
            if yaml_action == 'speech' or 'speech' in yaml_action.lower():
                # Text-to-Speech
                text = variables.get('text', action)
                output_file = variables.get('output') or variables.get('audio_output') or 'output.mp3'
                voice = variables.get('voice', 'alloy')
                result = agent.speech(text, output=output_file, voice=voice)
                # Store the output file path in variables for next step
                variables['_last_audio_file'] = output_file
                return result
            elif yaml_action == 'transcribe' or 'transcribe' in yaml_action.lower():
                # Speech-to-Text - check multiple variable names for input file
                input_file = (
                    variables.get('audio_file') or 
                    variables.get('audio') or 
                    variables.get('_last_audio_file') or  # From previous TTS step
                    variables.get('input')
                )
                # If input is empty string or template, use default
                if not input_file or input_file == '{{input}}' or 'Context from previous' in str(input_file):
                    input_file = 'output.mp3'  # Default TTS output
                language = variables.get('language', 'en')
                return agent.transcribe(input_file, language=language)
            else:
                # Default to speech if action contains text
                return agent.speech(action, output=variables.get('output', 'output.mp3'))
        
        # VideoAgent - generate
        elif agent_class_name == 'VideoAgent':
            prompt = variables.get('prompt', action)
            output_file = variables.get('output', 'output.mp4')
            return agent.generate(prompt, output=output_file)
        
        # ImageAgent - generate with output path support
        elif agent_class_name == 'ImageAgent':
            prompt = variables.get('prompt', action)
            output_path = variables.get('output') or variables.get('image_output')
            result = agent.generate(prompt)
            # Extract URL from result and store in variables for next step
            if hasattr(result, 'data') and result.data:
                image_url = result.data[0].url if hasattr(result.data[0], 'url') else None
                if image_url:
                    variables['_last_image_url'] = image_url
                    # Save to file if output path specified
                    if output_path:
                        try:
                            import urllib.request
                            urllib.request.urlretrieve(image_url, output_path)
                            variables['_last_image_file'] = output_path
                        except Exception as e:
                            logger.warning(f"Failed to save image to {output_path}: {e}")
            return result
        
        # OCRAgent - extract with retry logic for external API failures
        elif agent_class_name == 'OCRAgent':
            source = variables.get('source') or variables.get('url') or variables.get('document')
            # If no explicit source variable, try to extract URL from action text
            if not source:
                import re
                url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
                urls = re.findall(url_pattern, action)
                source = urls[0] if urls else action
            
            # Retry logic for external API failures
            max_retries = 2
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return agent.extract(source)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    # Only retry on transient errors (network, timeout, fetch failures)
                    if any(x in error_str for x in ['fetch', 'timeout', 'connection', 'network']):
                        if attempt < max_retries:
                            import time
                            time.sleep(1 * (attempt + 1))  # Exponential backoff
                            continue
                    # Non-retryable error, raise immediately
                    raise
            # All retries exhausted
            raise last_error
        
        # DeepResearchAgent - research
        elif agent_class_name == 'DeepResearchAgent':
            query = variables.get('query', action)
            return agent.research(query)
        
        # Default: standard Agent with chat() method
        else:
            return agent.chat(action, stream=stream)
    
    def _normalize_single_step(self, step: Any, index: int) -> 'Task':
        """Normalize a single step to Task.
        
        Supports:
        - Task objects (passed through)
        - Agent objects (wrapped with agent reference and tools)
        - Specialized agents (AudioAgent, VideoAgent, ImageAgent, OCRAgent)
        - Callable functions (wrapped as handler)
        - Strings (used as action)
        """
        if isinstance(step, Task):
            return step
        
        # Check for standard Agent (has chat method) or specialized agents
        agent_class_name = step.__class__.__name__
        is_specialized_agent = agent_class_name in ('AudioAgent', 'VideoAgent', 'ImageAgent', 'OCRAgent', 'DeepResearchAgent')
        
        if hasattr(step, 'chat') or is_specialized_agent:
            # It's an Agent - wrap with agent reference and preserve tools
            agent_tools = getattr(step, 'tools', None)
            # Check for _yaml_action from YAML parser (canonical: action, alias: description)
            yaml_action = getattr(step, '_yaml_action', None)
            # Check for _yaml_output_variable from YAML parser
            yaml_output_variable = getattr(step, '_yaml_output_variable', None)
            # Check for _yaml_output_json from YAML parser (structured output - Option A)
            yaml_output_json = getattr(step, '_yaml_output_json', None)
            # Check for _yaml_output_pydantic from YAML parser (structured output - Option B)
            yaml_output_pydantic = getattr(step, '_yaml_output_pydantic', None)
            # Check for _yaml_step_name from YAML parser
            yaml_step_name = getattr(step, '_yaml_step_name', None)
            # Use yaml_action if set, otherwise fall back to previous_output/input
            default_action = "{{previous_output}}" if index > 0 else "{{input}}"
            action = yaml_action if yaml_action else default_action
            # Build output config with all structured output options
            output_config = {}
            if yaml_output_variable:
                output_config["variable"] = yaml_output_variable
            if yaml_output_json:
                output_config["json_model"] = yaml_output_json
            if yaml_output_pydantic:
                output_config["pydantic_model"] = yaml_output_pydantic
            # Only pass output_config if it has values
            output_json_model = output_config.get('json_model') if output_config else None
            output_pydantic_model = output_config.get('pydantic_model') if output_config else None
            return Task(
                name=yaml_step_name or getattr(step, 'name', f'agent_{index+1}'),
                agent=step,
                tools=agent_tools,
                action=action,
                output_json=output_json_model,
                output_pydantic=output_pydantic_model
            )
        elif callable(step):
            return Task(
                name=getattr(step, '__name__', f'step_{index+1}'),
                handler=step
            )
        else:
            return Task(
                name=f'step_{index+1}',
                action=str(step)
            )
    
    def _execute_single_step_internal(
        self, 
        step: Any, 
        previous_output: Optional[str],
        input: str,
        all_variables: Dict[str, Any],
        model: str,
        verbose: bool,
        index: int = 0,
        stream: bool = True,
        depth: int = 0
    ) -> Dict[str, Any]:
        """Execute a single step and return result.
        
        Args:
            step: The step to execute (Agent, function, or pattern like Loop/Parallel/Route/If)
            previous_output: Output from previous step
            input: Original workflow input
            all_variables: Current workflow variables
            model: LLM model to use
            verbose: Whether to print verbose output
            index: Step index
            stream: Whether to stream responses
            depth: Current nesting depth (for pattern recursion safety)
        
        Returns:
            Dict with 'step', 'output', 'stop', 'variables'
        """
        # Check nesting depth limit for nested patterns
        if depth > MAX_NESTING_DEPTH:
            raise ValueError(
                f"Maximum nesting depth ({MAX_NESTING_DEPTH}) exceeded. "
                "Simplify your workflow or reduce pattern nesting."
            )
        
        # Handle nested patterns (Loop, Parallel, Route, Repeat, If)
        if isinstance(step, Loop):
            loop_result = self._execute_loop(
                step, previous_output, input, all_variables, model, verbose, stream, depth=depth+1
            )
            return {
                "step": f"loop_{index}",
                "output": loop_result.get("output", ""),
                "stop": False,
                "variables": loop_result.get("variables", all_variables)
            }
        
        if isinstance(step, Parallel):
            parallel_result = self._execute_parallel(
                step, previous_output, input, all_variables, model, verbose, stream, depth=depth+1
            )
            return {
                "step": f"parallel_{index}",
                "output": parallel_result.get("output", ""),
                "stop": False,
                "variables": parallel_result.get("variables", all_variables)
            }
        
        if isinstance(step, Route):
            route_result = self._execute_route(
                step, previous_output, input, all_variables, model, verbose, stream, depth=depth+1
            )
            return {
                "step": f"route_{index}",
                "output": route_result.get("output", ""),
                "stop": False,
                "variables": route_result.get("variables", all_variables)
            }
        
        if isinstance(step, Repeat):
            repeat_result = self._execute_repeat(
                step, previous_output, input, all_variables, model, verbose, stream, depth=depth+1
            )
            return {
                "step": f"repeat_{index}",
                "output": repeat_result.get("output", ""),
                "stop": False,
                "variables": repeat_result.get("variables", all_variables)
            }
        
        if isinstance(step, If):
            if_result = self._execute_if(
                step, previous_output, input, all_variables, model, verbose, stream, depth=depth+1
            )
            return {
                "step": f"if_{index}",
                "output": if_result.get("output", ""),
                "stop": False,
                "variables": if_result.get("variables", all_variables)
            }
        
        # Handle Include steps (for include inside loop)
        if isinstance(step, Include):
            include_result = self._execute_include(
                step, previous_output, input, all_variables, model, verbose, stream
            )
            # Return in the expected format for single step
            combined_output = include_result.get("output", "")
            return {
                "step": f"include:{step.recipe}",
                "output": combined_output,
                "stop": False,
                "variables": include_result.get("variables", all_variables)
            }
        
        normalized = self._normalize_single_step(step, index)
        
        context = WorkflowContext(
            input=input,
            previous_result=str(previous_output) if previous_output else None,
            current_step=normalized.name,
            variables=all_variables.copy()
        )
        
        output = None
        stop = False
        
        if normalized.handler:
            try:
                result = normalized.handler(context)
                if isinstance(result, StepResult):
                    output = result.output
                    stop = result.stop_workflow
                    if result.variables:
                        all_variables.update(result.variables)
                else:
                    output = str(result)
            except Exception as e:
                output = f"Error: {e}"
        elif normalized.agent:
            try:
                # Propagate context management to existing agent if workflow has it enabled
                if self.context and hasattr(normalized.agent, '_context_manager_initialized'):
                    if not normalized.agent._context_manager_initialized:
                        normalized.agent._context_param = self.context
                    # Share session deduplication cache for cross-agent deduplication
                    if self._session_dedup_cache:
                        normalized.agent._session_dedup_cache = self._session_dedup_cache
                        # Also set on existing context manager if already initialized
                        if normalized.agent._context_manager and hasattr(normalized.agent._context_manager, '_session_cache'):
                            normalized.agent._context_manager._session_cache = self._session_dedup_cache
                
                action = normalized.action or input
                # Substitute variables
                for key, value in all_variables.items():
                    action = action.replace(f"{{{{{key}}}}}", str(value))
                if previous_output:
                    if "{{previous_output}}" in action:
                        action = action.replace("{{previous_output}}", str(previous_output))
                    else:
                        # Auto-append context if not explicitly referenced
                        action = f"{action}\n\nContext from previous step:\n{previous_output}"
                action = action.replace("{{input}}", input)
                
                # Check if this is a specialized agent (AudioAgent, VideoAgent, ImageAgent, OCRAgent)
                agent_class_name = normalized.agent.__class__.__name__
                output = self._execute_specialized_agent(
                    normalized.agent, agent_class_name, action, normalized, all_variables, stream
                )
                
                # Parse JSON output if output_json was requested
                step_output_json = getattr(normalized, '_output_json', None)
                if step_output_json and output and isinstance(output, str):
                    output = _parse_json_output(output, normalized.name)
            except Exception as e:
                output = f"Error: {e}"
        elif normalized.action:
            try:
                from ..agent.agent import Agent
                config = normalized.agent_config or self.default_agent_config or {}
                temp_agent = Agent(
                    name=config.get("name", normalized.name),
                    role=config.get("role", "Assistant"),
                    goal=config.get("goal", "Complete the task"),
                    llm=config.get("llm", model),
                    stream=stream,
                    context=self.context,  # Propagate context management to child agents
                )
                action = normalized.action
                for key, value in all_variables.items():
                    action = action.replace(f"{{{{{key}}}}}", str(value))
                if previous_output:
                    if "{{previous_output}}" in action:
                        action = action.replace("{{previous_output}}", str(previous_output))
                    else:
                        # Auto-append context if not explicitly referenced
                        action = f"{action}\n\nContext from previous step:\n{previous_output}"
                
                output = temp_agent.chat(action, stream=stream)
                
                # Parse JSON output if output_json was requested
                step_output_json = getattr(normalized, '_output_json', None)
                if step_output_json and output and isinstance(output, str):
                    output = _parse_json_output(output, normalized.name)
            except Exception as e:
                output = f"Error: {e}"
        
        if verbose:
            print(f"✅ {normalized.name}: {str(output)}")
        
        return {
            "step": normalized.name,
            "output": output,
            "stop": stop,
            "variables": all_variables
        }
    
    def _execute_route(
        self,
        route_step: Route,
        previous_output: Optional[str],
        input: str,
        all_variables: Dict[str, Any],
        model: str,
        verbose: bool,
        stream: bool = True,
        depth: int = 0
    ) -> Dict[str, Any]:
        """Execute routing based on previous output."""
        results = []
        output = previous_output
        
        # Find matching route
        matched_route = None
        prev_lower = str(previous_output).lower() if previous_output else ""
        
        for key in route_step.routes:
            if key.lower() in prev_lower or key == "default":
                if key != "default":
                    matched_route = route_step.routes[key]
                    break
        
        if matched_route is None:
            matched_route = route_step.default or []
        
        if verbose:
            route_name = next((k for k in route_step.routes if route_step.routes[k] == matched_route), "default")
            print(f"🔀 Routing to: {route_name}")
        
        # Execute matched route steps
        for idx, step in enumerate(matched_route):
            step_result = self._execute_single_step_internal(
                step, output, input, all_variables, model, verbose, idx, stream=stream, depth=depth+1
            )
            results.append({"step": step_result["step"], "output": step_result["output"]})
            output = step_result["output"]
            all_variables.update(step_result.get("variables", {}))
            
            if step_result.get("stop"):
                break
        
        return {"steps": results, "output": output, "variables": all_variables}
    
    def _llm_summarize_for_parallel(
        self,
        content: str,
        num_branches: int,
        model: str,
        verbose: bool = False
    ) -> str:
        """
        Use LLM to create a concise summary of content for parallel distribution.
        
        This reduces token usage when the same context is passed to multiple parallel branches.
        """
        from ..context.tokens import estimate_tokens_heuristic
        
        # Only summarize if content is large enough
        tokens = estimate_tokens_heuristic(content)
        if tokens < 1500:
            return content
        
        # Target summary size: ~500 tokens to leave room for each branch's work
        target_tokens = min(500, tokens // num_branches)
        
        try:
            import litellm
            
            prompt = f"""Summarize the following content concisely, preserving all key information, data, and actionable items. 
Keep the summary under {target_tokens * 4} characters. Focus on facts, numbers, and specific details.

CONTENT:
{content[:8000]}

CONCISE SUMMARY:"""
            
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=target_tokens,
                temperature=0.1,
            )
            
            summary = response.choices[0].message.content.strip()
            
            if verbose:
                print(f"  🤖 LLM summarized context: {tokens:,} → {estimate_tokens_heuristic(summary):,} tokens")
            
            return summary
            
        except Exception as e:
            logger.debug(f"LLM summarization failed, using truncation: {e}")
            raise  # Let caller handle fallback
    
    def _execute_parallel(
        self,
        parallel_step: Parallel,
        previous_output: Optional[str],
        input: str,
        all_variables: Dict[str, Any],
        model: str,
        verbose: bool,
        stream: bool = True,
        depth: int = 0
    ) -> Dict[str, Any]:
        """Execute steps in parallel (simulated with sequential for now)."""
        import concurrent.futures
        
        results = []
        outputs = []
        
        if verbose:
            print(f"⚡ Running {len(parallel_step.steps)} steps in parallel...")
        
        # Optimize: Use LLM-based summarization before distributing to parallel branches
        # This prevents rate limits and reduces token waste
        optimized_previous = previous_output
        num_branches = len(parallel_step.steps)
        if previous_output and len(previous_output) > 3000:
            from ..context.tokens import estimate_tokens_heuristic
            tokens = estimate_tokens_heuristic(previous_output)
            if tokens > 1000:
                # Try LLM-based summarization first, fall back to truncation
                try:
                    optimized_previous = self._llm_summarize_for_parallel(previous_output, num_branches, model, verbose)
                except Exception:
                    # Fallback to truncation-based summarization
                    max_chars = min(2500, len(previous_output) // max(num_branches, 2))
                    if len(previous_output) > max_chars:
                        optimized_previous = previous_output[:max_chars * 2 // 3] + "\n\n[... context summarized for parallel efficiency ...]\n\n" + previous_output[-max_chars // 3:]
                
                if verbose and optimized_previous != previous_output:
                    new_tokens = estimate_tokens_heuristic(optimized_previous)
                    saved = tokens - new_tokens
                    print(f"  📦 Optimized context for {num_branches} parallel branches: {tokens:,} → {new_tokens:,} tokens (saved {saved:,} per branch)")
        
        # Use ThreadPoolExecutor for parallel execution
        # IMPORTANT: Limit max_workers to prevent rate limit issues (max 3 concurrent branches)
        from ..trace.context_events import copy_context_to_callable, get_context_emitter
        
        effective_workers = min(3, len(parallel_step.steps))  # Cap at 3 to prevent rate limits
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = []
            for idx, step in enumerate(parallel_step.steps):
                # Wrap execution to propagate context and set branch_id for parallel tracking
                def execute_with_branch(step=step, idx=idx, opt_prev=optimized_previous):
                    emitter = get_context_emitter()
                    emitter.set_branch(f"parallel_{idx}")
                    try:
                        return self._execute_single_step_internal(
                            step, opt_prev, input, all_variables.copy(), model, False, idx, stream, depth=depth+1
                        )
                    finally:
                        emitter.clear_branch()
                
                future = executor.submit(copy_context_to_callable(execute_with_branch))
                futures.append((idx, future))
            
            for idx, future in futures:
                try:
                    step_result = future.result()
                    results.append({"step": step_result["step"], "output": step_result["output"]})
                    outputs.append(step_result["output"])
                except Exception as e:
                    results.append({"step": f"parallel_{idx}", "output": f"Error: {e}"})
                    outputs.append(f"Error: {e}")
        
        # Combine outputs
        combined_output = "\n---\n".join(str(o) for o in outputs)
        all_variables["parallel_outputs"] = outputs
        
        if verbose:
            print(f"✅ Parallel complete: {len(outputs)} results")
        
        return {"steps": results, "output": combined_output, "variables": all_variables}
    
    def _execute_loop(
        self,
        loop_step: Loop,
        previous_output: Optional[str],
        input: str,
        all_variables: Dict[str, Any],
        model: str,
        verbose: bool,
        stream: bool = True,
        depth: int = 0
    ) -> Dict[str, Any]:
        """Execute step for each item in loop.
        
        When loop_step.parallel is True, executes iterations concurrently
        using ThreadPoolExecutor for faster processing.
        """
        import csv
        import concurrent.futures
        
        results = []
        outputs = []
        items = []
        
        # Get items from variable, CSV, or file
        if loop_step.over:
            items = all_variables.get(loop_step.over, [])
            if isinstance(items, str):
                # Try to parse as JSON list first (handles agent output like '["a", "b", "c"]')
                items = self._parse_list_from_string(items)
        elif loop_step.from_csv:
            try:
                with open(loop_step.from_csv, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    items = list(reader)
            except Exception as e:
                logger.error(f"Failed to read CSV {loop_step.from_csv}: {e}")
                items = []
        elif loop_step.from_file:
            try:
                with open(loop_step.from_file, 'r', encoding='utf-8') as f:
                    items = [line.strip() for line in f if line.strip()]
            except Exception as e:
                logger.error(f"Failed to read file {loop_step.from_file}: {e}")
                items = []
        
        num_items = len(items)
        
        # Determine steps to run (multi-step or single step)
        steps_to_run = loop_step.steps if loop_step.steps else [loop_step.step]
        is_multi_step = loop_step.steps is not None and len(loop_step.steps) > 1
        
        if loop_step.parallel and num_items > 1:
            # Parallel execution - cap workers to prevent rate limits
            max_workers = min(loop_step.max_workers or num_items, 3)  # Cap at 3 to prevent rate limits
            if verbose:
                step_info = f" ({len(steps_to_run)} steps each)" if is_multi_step else ""
                print(f"⚡🔁 Parallel looping over {num_items} items{step_info} (max_workers={max_workers})...")
            
            # Optimize: Aggressively summarize large previous_output before distributing to parallel branches
            # This reduces token waste and prevents rate limit issues
            optimized_previous = previous_output
            if previous_output and len(previous_output) > 3000:
                from ..context.tokens import estimate_tokens_heuristic
                tokens = estimate_tokens_heuristic(previous_output)
                # Target: max 800 tokens per branch to stay well under rate limits
                if tokens > 1000:
                    max_chars = min(2500, len(previous_output) // max(num_items, 2))
                    if len(previous_output) > max_chars:
                        # Extract key information: first part (context) + last part (recent output)
                        optimized_previous = previous_output[:max_chars * 2 // 3] + "\n\n[... context summarized for parallel efficiency ...]\n\n" + previous_output[-max_chars // 3:]
                        if verbose:
                            new_tokens = estimate_tokens_heuristic(optimized_previous)
                            saved = tokens - new_tokens
                            print(f"  📦 Optimized context for {num_items} parallel branches: {tokens:,} → {new_tokens:,} tokens (saved {saved:,} per branch)")
            
            # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
            from ..trace.context_events import copy_context_to_callable, get_context_emitter
            
            def execute_item(idx_item_tuple, opt_prev=optimized_previous):
                """Execute step(s) for a single item in thread."""
                idx, item = idx_item_tuple
                
                # Set branch context for parallel tracking
                emitter = get_context_emitter()
                emitter.set_branch(f"loop_{idx}")
                
                try:
                    # CRITICAL: Deep copy variables to ensure thread isolation (per-branch context isolation)
                    import copy
                    loop_vars = copy.deepcopy(all_variables)
                    loop_vars[loop_step.var_name] = item
                    loop_vars["loop_index"] = idx
                    
                    # Also expand nested item properties for template access (e.g., {{item.title}})
                    if isinstance(item, dict):
                        for key, value in item.items():
                            loop_vars[f"{loop_step.var_name}.{key}"] = value
                    
                    # Execute all steps sequentially within this iteration
                    iteration_output = opt_prev
                    iteration_results = []
                    for step_idx, step in enumerate(steps_to_run):
                        step_result = self._execute_single_step_internal(
                            step, iteration_output, input, loop_vars, model, False, step_idx, stream=False, depth=depth+1
                        )
                        iteration_output = step_result.get("output")
                        iteration_results.append(step_result)
                        # Update variables if step set any
                        if step_result.get("variables"):
                            loop_vars.update(step_result["variables"])
                    
                    # Return final output (last step's output)
                    final_result = {
                        "step": f"loop_{idx}",
                        "output": iteration_output,
                        "steps": iteration_results
                    }
                    return idx, final_result
                finally:
                    emitter.clear_branch()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(copy_context_to_callable(lambda pair=(idx, item): execute_item(pair)))
                    for idx, item in enumerate(items)
                ]
                
                # Collect results in order
                indexed_results = []
                for future in concurrent.futures.as_completed(futures):
                    try:
                        idx, step_result = future.result()
                        indexed_results.append((idx, step_result))
                        if verbose:
                            print(f"  ✓ Item {idx + 1}/{num_items} complete")
                    except Exception as e:
                        logger.error(f"Parallel loop iteration failed: {e}")
                        indexed_results.append((idx, {"step": f"loop_{idx}", "output": f"Error: {e}"}))
                
                # Sort by index to maintain order
                indexed_results.sort(key=lambda x: x[0])
                
                for idx, step_result in indexed_results:
                    results.append({"step": f"{step_result['step']}_{idx}", "output": step_result["output"]})
                    outputs.append(step_result["output"])
            
            if verbose:
                print(f"✅ Parallel loop complete: {len(outputs)} results")
        else:
            # Sequential execution (original behavior)
            if verbose:
                step_info = f" ({len(steps_to_run)} steps each)" if is_multi_step else ""
                print(f"🔁 Looping over {num_items} items{step_info}...")
            
            for idx, item in enumerate(items):
                # Add current item to variables
                import copy
                loop_vars = copy.deepcopy(all_variables)
                loop_vars[loop_step.var_name] = item
                loop_vars["loop_index"] = idx
                
                # Also expand nested item properties for template access (e.g., {{item.title}})
                if isinstance(item, dict):
                    for key, value in item.items():
                        loop_vars[f"{loop_step.var_name}.{key}"] = value
                
                # Execute all steps sequentially within this iteration
                iteration_output = previous_output
                for step_idx, step in enumerate(steps_to_run):
                    step_result = self._execute_single_step_internal(
                        step, iteration_output, input, loop_vars, model, verbose, step_idx, stream=stream, depth=depth+1
                    )
                    iteration_output = step_result.get("output")
                    # Update variables if step set any
                    if step_result.get("variables"):
                        loop_vars.update(step_result["variables"])
                
                results.append({"step": f"loop_{idx}", "output": iteration_output})
                outputs.append(iteration_output)
                previous_output = iteration_output
        # Store outputs in user-specified variable or default to loop_outputs
        output_var_name = loop_step.output_variable or "loop_outputs"
        all_variables[output_var_name] = outputs
        all_variables["loop_outputs"] = outputs  # Also keep for backward compatibility
        combined_output = "\n".join(str(o) for o in outputs) if outputs else ""
        
        # Validate outputs and warn about issues
        none_count = sum(1 for o in outputs if o is None)
        if none_count > 0:
            logger.warning(f"⚠️  Loop '{output_var_name}': {none_count}/{len(outputs)} outputs are None. "
                          f"Check if agent returned expected format.")
            if verbose:
                print(f"⚠️  WARNING: {none_count}/{len(outputs)} loop outputs are None!")
        
        # Check for type consistency
        if outputs and len(outputs) > 0:
            expected_type = loop_step.step._output_json if hasattr(loop_step.step, '_output_json') else None
            if expected_type:
                expected_schema_type = expected_type.get('type') if isinstance(expected_type, dict) else None
                for i, o in enumerate(outputs):
                    if o is None:
                        continue
                    actual_type = type(o).__name__
                    if expected_schema_type == 'object' and not isinstance(o, dict):
                        logger.warning(f"⚠️  Loop output[{i}]: Expected object/dict, got {actual_type}")
                        if verbose:
                            print(f"⚠️  Loop output[{i}]: Expected 'object', received '{actual_type}'")
                    elif expected_schema_type == 'array' and not isinstance(o, list):
                        logger.warning(f"⚠️  Loop output[{i}]: Expected array/list, got {actual_type}")
                        if verbose:
                            print(f"⚠️  Loop output[{i}]: Expected 'array', received '{actual_type}'")
        
        # Debug logging for output_variable
        if verbose:
            print(f"📦 Loop stored {len(outputs)} results in variable: '{output_var_name}'")
        
        return {"steps": results, "output": combined_output, "variables": all_variables}
    
    def _parse_list_from_string(self, text: str) -> List[Any]:
        """
        Parse a list from a string, handling multiple formats.
        
        Supports:
        1. Pure JSON array: '["a", "b", "c"]'
        2. JSON array embedded in text: 'Here are topics: ["a", "b", "c"]'
        3. Newline-separated items (fallback)
        
        Args:
            text: String that may contain a list
            
        Returns:
            List of items, or [text] if no list found
        """
        import json
        import re
        
        if not text or not text.strip():
            return []
        
        text = text.strip()
        
        # 1. Try direct JSON parse (pure JSON array)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        
        # 2. Try to extract JSON array from text using regex
        # Match JSON arrays like ["item1", "item2"] or ['item1', 'item2']
        json_array_pattern = r'\[(?:[^\[\]]*(?:"[^"]*"|\'[^\']*\')?[^\[\]]*)*\]'
        matches = re.findall(json_array_pattern, text)
        
        for match in matches:
            try:
                # Try parsing as JSON
                parsed = json.loads(match)
                if isinstance(parsed, list) and len(parsed) > 0:
                    return parsed
            except json.JSONDecodeError:
                # Try replacing single quotes with double quotes
                try:
                    fixed = match.replace("'", '"')
                    parsed = json.loads(fixed)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return parsed
                except json.JSONDecodeError:
                    continue
        
        # 3. Fallback: wrap as single item
        return [text]
    
    def _execute_repeat(
        self,
        repeat_step: Repeat,
        previous_output: Optional[str],
        input: str,
        all_variables: Dict[str, Any],
        model: str,
        verbose: bool,
        stream: bool = True,
        depth: int = 0
    ) -> Dict[str, Any]:
        """Repeat step until condition is met."""
        results = []
        output = previous_output
        
        if verbose:
            print(f"🔄 Repeating up to {repeat_step.max_iterations} times...")
        
        for iteration in range(repeat_step.max_iterations):
            step_result = self._execute_single_step_internal(
                repeat_step.step, output, input, all_variables, model, verbose, iteration, stream=stream, depth=depth+1
            )
            results.append({"step": f"{step_result['step']}_{iteration}", "output": step_result["output"]})
            output = step_result["output"]
            all_variables.update(step_result.get("variables", {}))
            
            # Check until condition
            if repeat_step.until:
                context = WorkflowContext(
                    input=input,
                    previous_result=str(output) if output else None,
                    current_step=f"repeat_{iteration}",
                    variables=all_variables.copy()
                )
                try:
                    if repeat_step.until(context):
                        if verbose:
                            print(f"✅ Repeat condition met at iteration {iteration + 1}")
                        break
                except Exception as e:
                    logger.error(f"Repeat until condition failed: {e}")
            
            if step_result.get("stop"):
                break
        
        all_variables["repeat_iterations"] = iteration + 1
        return {"steps": results, "output": output, "variables": all_variables}
    
    def _execute_if(
        self,
        if_step: If,
        previous_output: Optional[str],
        input: str,
        all_variables: Dict[str, Any],
        model: str,
        verbose: bool,
        stream: bool = True,
        depth: int = 0
    ) -> Dict[str, Any]:
        """Execute conditional branching based on condition evaluation.
        
        Args:
            if_step: The If step with condition and branches
            previous_output: Output from previous step
            input: Original workflow input
            all_variables: Current workflow variables
            model: LLM model to use
            verbose: Verbose output
            stream: Enable streaming
            depth: Current nesting depth
            
        Returns:
            Dict with 'steps', 'output', and 'variables'
        """
        results = []
        output = previous_output
        
        # Evaluate the condition
        condition_result = self._evaluate_condition(if_step.condition, all_variables, previous_output)
        
        if verbose:
            branch = "then" if condition_result else "else"
            print(f"🔀 Condition '{if_step.condition}' → {condition_result}, executing {branch} branch")
        
        # Select the appropriate branch
        steps_to_execute = if_step.then_steps if condition_result else if_step.else_steps
        
        # Execute the selected branch
        for idx, step in enumerate(steps_to_execute):
            step_result = self._execute_single_step_internal(
                step, output, input, all_variables, model, verbose, idx, stream=stream, depth=depth
            )
            results.append({"step": step_result["step"], "output": step_result["output"]})
            output = step_result["output"]
            all_variables.update(step_result.get("variables", {}))
            
            if step_result.get("stop"):
                break
        
        return {"steps": results, "output": output, "variables": all_variables}
    
    def _evaluate_condition(
        self,
        condition: str,
        variables: Dict[str, Any],
        previous_output: Optional[str] = None
    ) -> bool:
        """Evaluate a condition expression with variable substitution.
        
        Supported formats:
            - Numeric comparison: "{{var}} > 80", "{{var}} >= 50", "{{var}} < 10"
            - String equality: "{{var}} == approved", "{{var}} != rejected"
            - Contains check: "error in {{message}}", "{{status}} contains success"
            - Boolean: "{{flag}}" (truthy check)
            - Nested property: "{{item.score}} >= 60"
        
        Args:
            condition: Condition expression with {{var}} placeholders
            variables: Current workflow variables
            previous_output: Output from previous step
            
        Returns:
            Boolean result of condition evaluation
        """
        import re
        
        # Substitute variables in condition
        substituted = condition
        
        # Handle nested property access like {{item.score}}
        def get_nested_value(var_path: str, vars_dict: Dict[str, Any]) -> Any:
            parts = var_path.split('.')
            value = vars_dict
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return None
            return value
        
        # Find all {{var}} patterns and substitute
        pattern = r'\{\{([^}]+)\}\}'
        matches = re.findall(pattern, condition)
        
        for var_name in matches:
            if '.' in var_name:
                # Nested property access
                value = get_nested_value(var_name, variables)
            else:
                value = variables.get(var_name)
            
            if value is None:
                value = ""
            
            # Replace the placeholder with the value
            placeholder = f"{{{{{var_name}}}}}"
            if isinstance(value, (int, float)):
                substituted = substituted.replace(placeholder, str(value))
            elif isinstance(value, bool):
                substituted = substituted.replace(placeholder, str(value).lower())
            else:
                substituted = substituted.replace(placeholder, str(value))
        
        # Also substitute {{previous_output}}
        if previous_output:
            substituted = substituted.replace("{{previous_output}}", str(previous_output))
        
        # Now evaluate the substituted condition
        try:
            # Handle different condition formats
            
            # Numeric comparisons: "90 > 80", "50 >= 50", "10 < 20", etc.
            numeric_pattern = r'^(-?\d+(?:\.\d+)?)\s*(>|>=|<|<=|==|!=)\s*(-?\d+(?:\.\d+)?)$'
            numeric_match = re.match(numeric_pattern, substituted.strip())
            if numeric_match:
                left = float(numeric_match.group(1))
                op = numeric_match.group(2)
                right = float(numeric_match.group(3))
                
                if op == '>':
                    return left > right
                if op == '>=':
                    return left >= right
                if op == '<':
                    return left < right
                if op == '<=':
                    return left <= right
                if op == '==':
                    return left == right
                if op == '!=':
                    return left != right
            
            # String equality: "approved == approved", "status != rejected"
            string_eq_pattern = r'^(.+?)\s*(==|!=)\s*(.+)$'
            string_match = re.match(string_eq_pattern, substituted.strip())
            if string_match:
                left = string_match.group(1).strip()
                op = string_match.group(2)
                right = string_match.group(3).strip()
                
                if op == '==':
                    return left == right
                if op == '!=':
                    return left != right
            
            # Contains check: "error in some message", "status contains success"
            if ' in ' in substituted:
                parts = substituted.split(' in ', 1)
                if len(parts) == 2:
                    needle = parts[0].strip()
                    haystack = parts[1].strip()
                    return needle.lower() in haystack.lower()
            
            if ' contains ' in substituted:
                parts = substituted.split(' contains ', 1)
                if len(parts) == 2:
                    haystack = parts[0].strip()
                    needle = parts[1].strip()
                    return needle.lower() in haystack.lower()
            
            # Boolean check: truthy evaluation
            # Handle "true", "false", "True", "False"
            if substituted.strip().lower() == 'true':
                return True
            if substituted.strip().lower() == 'false':
                return False
            
            # Non-empty string is truthy
            return bool(substituted.strip())
            
        except Exception as e:
            logger.warning(f"Condition evaluation failed for '{condition}': {e}")
            return False
    
    def _execute_include(
        self,
        include_step: Include,
        previous_output: Optional[str],
        input: str,
        all_variables: Dict[str, Any],
        model: str,
        verbose: bool,
        stream: bool = True,
        visited_recipes: Optional[set] = None
    ) -> Dict[str, Any]:
        """Execute an included recipe as a workflow step.
        
        Args:
            include_step: The Include step with recipe name
            previous_output: Output from previous step
            input: Original workflow input
            all_variables: Current workflow variables
            model: LLM model to use
            verbose: Verbose output
            stream: Enable streaming
            visited_recipes: Set of already-visited recipe names (for cycle detection)
            
        Returns:
            Dict with 'steps', 'output', and 'variables'
        """
        recipe_name = include_step.recipe
        
        # Cycle detection
        if visited_recipes is None:
            visited_recipes = set()
        
        if recipe_name in visited_recipes:
            error_msg = f"Circular include detected: {recipe_name} was already included in this execution chain"
            logger.error(error_msg)
            return {
                "steps": [{"step": f"include:{recipe_name}", "output": f"Error: {error_msg}"}],
                "output": error_msg,
                "variables": all_variables
            }
        
        visited_recipes.add(recipe_name)
        
        if verbose:
            print(f"📦 Including recipe: {recipe_name}")
        
        try:
            # Try to resolve recipe path using agent_recipes if available
            recipe_path = None
            
            try:
                from agent_recipes import get_template_path
                recipe_path = get_template_path(recipe_name)
            except ImportError:
                # agent_recipes not installed, try local path
                from pathlib import Path
                if Path(recipe_name).exists():
                    recipe_path = Path(recipe_name)
                else:
                    # Try as relative path to current working directory
                    import os
                    cwd = Path(os.getcwd())
                    potential_path = cwd / recipe_name
                    if potential_path.exists():
                        recipe_path = potential_path
            
            if not recipe_path:
                error_msg = f"Recipe not found: {recipe_name}"
                logger.error(error_msg)
                return {
                    "steps": [{"step": f"include:{recipe_name}", "output": f"Error: {error_msg}"}],
                    "output": error_msg,
                    "variables": all_variables
                }
            
            # Find the YAML file (agents.yaml or workflow.yaml)
            recipe_yaml = None
            from pathlib import Path
            recipe_path = Path(recipe_path)
            
            for yaml_name in ["agents.yaml", "workflow.yaml", "TEMPLATE.yaml"]:
                yaml_path = recipe_path / yaml_name
                if yaml_path.exists():
                    recipe_yaml = yaml_path
                    break
            
            if not recipe_yaml:
                error_msg = f"No workflow YAML found in {recipe_path}"
                logger.error(error_msg)
                return {
                    "steps": [{"step": f"include:{recipe_name}", "output": f"Error: {error_msg}"}],
                    "output": error_msg,
                    "variables": all_variables
                }
            
            # Load tools from the recipe's tools.py if present
            tool_registry = {}
            tools_py = recipe_path / "tools.py"
            if tools_py.exists():
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("recipe_tools", tools_py)
                    recipe_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(recipe_module)
                    
                    # Extract callable tools
                    for name in dir(recipe_module):
                        if not name.startswith("_"):
                            obj = getattr(recipe_module, name)
                            if callable(obj):
                                tool_registry[name] = obj
                except Exception as e:
                    logger.warning(f"Failed to load tools from {tools_py}: {e}")
            
            # Determine input for the included recipe
            recipe_input = include_step.input or previous_output or input
            
            # Convert non-string inputs to JSON string for variable substitution
            if recipe_input and not isinstance(recipe_input, str):
                recipe_input = json.dumps(recipe_input)
            
            # Substitute variables in the input (only if it's a string)
            if recipe_input and isinstance(recipe_input, str):
                for key, value in all_variables.items():
                    recipe_input = recipe_input.replace(f"{{{{{key}}}}}", str(value))
                if previous_output:
                    prev_str = previous_output if isinstance(previous_output, str) else json.dumps(previous_output)
                    recipe_input = recipe_input.replace("{{previous_output}}", prev_str)
                recipe_input = recipe_input.replace("{{input}}", input)
            
            # Parse and execute the included workflow
            from .yaml_parser import YAMLWorkflowParser
            parser = YAMLWorkflowParser(tool_registry=tool_registry)
            included_workflow = parser.parse_file(str(recipe_yaml))
            
            # Merge parent variables into included workflow
            included_workflow.variables.update(all_variables)
            included_workflow.variables["previous_output"] = previous_output
            
            # Execute the included workflow
            result = included_workflow.run(
                input=recipe_input or "",
                llm=model,
                verbose=verbose,
                stream=stream
            )
            
            if verbose:
                print(f"✅ Included recipe {recipe_name} completed")
            
            # Return result in expected format
            return {
                "steps": result.get("steps", []),
                "output": result.get("output", ""),
                "variables": {**all_variables, **result.get("variables", {})}
            }
            
        except Exception as e:
            logger.error(f"Failed to execute included recipe {recipe_name}: {e}")
            return {
                "steps": [{"step": f"include:{recipe_name}", "output": f"Error: {e}"}],
                "output": f"Error executing {recipe_name}: {e}",
                "variables": all_variables
            }
        finally:
            # Remove from visited after execution completes (allow re-use in different branches)
            visited_recipes.discard(recipe_name)
    
    def start(self, input: str = "", **kwargs) -> Dict[str, Any]:
        """Alias for run() for consistency with Agents."""
        return self.run(input, **kwargs)


# Alias: Pipeline = Workflow (they are the same concept)
Pipeline = Workflow


class WorkflowManager:
    """
    Manages workflow discovery, loading, and execution.
    
    Workflows are defined in markdown files with YAML frontmatter
    and step definitions.
    
    Example workflow file (.praison/workflows/deploy.md):
        ```markdown
        ---
        name: Deploy to Production
        description: Deploy the application to production
        variables:
          environment: production
          branch: main
        ---
        
        ## Step 1: Run Tests
        Run all tests to ensure code quality.
        
        ```action
        Run the test suite with pytest
        ```
        
        ## Step 2: Build
        Build the application for production.
        
        ```action
        Build the application with production settings
        ```
        
        ## Step 3: Deploy
        Deploy to the production server.
        
        ```action
        Deploy to {{environment}} from {{branch}}
        ```
        ```
    
    Example usage:
        ```python
        manager = WorkflowManager(workspace_path="/path/to/project")
        
        # List available workflows
        workflows = manager.list_workflows()
        
        # Get a specific workflow
        deploy = manager.get_workflow("deploy")
        
        # Execute a workflow
        results = manager.execute(
            "deploy",
            executor=lambda prompt: agent.chat(prompt),
            variables={"branch": "release-1.0"}
        )
        ```
    """
    
    WORKFLOWS_DIR = ".praison/workflows"
    SUPPORTED_EXTENSIONS = [".md", ".yaml", ".yml"]
    
    def __init__(
        self,
        workspace_path: Optional[str] = None,
        verbose: int = 0
    ):
        """
        Initialize WorkflowManager.
        
        Args:
            workspace_path: Path to workspace/project root
            verbose: Verbosity level
        """
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        self.verbose = verbose
        
        self._workflows: Dict[str, Workflow] = {}
        self._loaded = False
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message if verbose."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _ensure_loaded(self):
        """Lazy load workflows on first access."""
        if not self._loaded:
            self._discover_workflows()
            self._loaded = True
    
    def _parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        """Parse YAML frontmatter from markdown content."""
        frontmatter = {}
        body = content
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                yaml_content = parts[1].strip()
                body = parts[2].strip()
                
                # Simple YAML parsing
                for line in yaml_content.split("\n"):
                    line = line.strip()
                    if ":" in line and not line.startswith("#"):
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Handle basic types
                        if value.lower() in ("true", "false"):
                            value = value.lower() == "true"
                        elif value.isdigit():
                            value = int(value)
                        elif value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        
                        frontmatter[key] = value
        
        return frontmatter, body
    
    def _parse_steps(self, body: str) -> List[Task]:
        """Parse workflow steps from markdown body."""
        steps = []
        
        # Split by ## headers
        step_pattern = re.compile(r'^##\s+(?:Step\s+\d+[:\s]*)?(.+)$', re.MULTILINE)
        action_pattern = re.compile(r'```action\s*\n(.*?)\n```', re.DOTALL)
        condition_pattern = re.compile(r'```condition\s*\n(.*?)\n```', re.DOTALL)
        agent_pattern = re.compile(r'```agent\s*\n(.*?)\n```', re.DOTALL)
        tools_pattern = re.compile(r'```tools\s*\n(.*?)\n```', re.DOTALL)
        context_from_pattern = re.compile(r'context_from:\s*\[([^\]]+)\]', re.IGNORECASE)
        retain_context_pattern = re.compile(r'retain_full_context:\s*(true|false)', re.IGNORECASE)
        output_var_pattern = re.compile(r'output_variable:\s*(\w+)', re.IGNORECASE)
        next_steps_pattern = re.compile(r'next_steps:\s*\[([^\]]+)\]', re.IGNORECASE)
        loop_over_pattern = re.compile(r'loop_over:\s*(\w+)', re.IGNORECASE)
        loop_var_pattern = re.compile(r'loop_var:\s*(\w+)', re.IGNORECASE)
        branch_pattern = re.compile(r'```branch\s*\n(.*?)\n```', re.DOTALL)
        
        # New patterns for route, parallel, images, output_file
        route_pattern = re.compile(r'```route\s*\n(.*?)\n```', re.DOTALL)
        parallel_pattern = re.compile(r'```parallel\s*\n(.*?)\n```', re.DOTALL)
        images_pattern = re.compile(r'```images\s*\n(.*?)\n```', re.DOTALL)
        output_file_pattern = re.compile(r'output_file:\s*(.+)', re.IGNORECASE)
        repeat_pattern = re.compile(r'```repeat\s*\n(.*?)\n```', re.DOTALL)
        
        # Find all step headers
        matches = list(step_pattern.finditer(body))
        
        for i, match in enumerate(matches):
            step_name = match.group(1).strip()
            
            # Get content until next step or end
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            step_content = body[start:end].strip()
            
            # Extract action
            action_match = action_pattern.search(step_content)
            action = action_match.group(1).strip() if action_match else ""
            
            # Extract condition
            condition_match = condition_pattern.search(step_content)
            condition = condition_match.group(1).strip() if condition_match else None
            
            # Extract agent config
            agent_config = None
            agent_match = agent_pattern.search(step_content)
            if agent_match:
                agent_config = self._parse_agent_config(agent_match.group(1).strip())
            
            # Extract tools list
            tools = None
            tools_match = tools_pattern.search(step_content)
            if tools_match:
                tools_str = tools_match.group(1).strip()
                # Parse tools as list of strings (tool names)
                tools = [t.strip().strip('"\'') for t in tools_str.split('\n') if t.strip()]
            
            # Extract context_from
            context_from = None
            context_from_match = context_from_pattern.search(step_content)
            if context_from_match:
                context_from = [s.strip().strip('"\'') for s in context_from_match.group(1).split(',')]
            
            # Extract retain_full_context
            retain_full_context = True
            retain_match = retain_context_pattern.search(step_content)
            if retain_match:
                retain_full_context = retain_match.group(1).lower() == 'true'
            
            # Extract output_variable
            output_variable = None
            output_var_match = output_var_pattern.search(step_content)
            if output_var_match:
                output_variable = output_var_match.group(1)
            
            # Extract next_steps for branching
            next_steps = None
            next_steps_match = next_steps_pattern.search(step_content)
            if next_steps_match:
                next_steps = [s.strip().strip('"\'') for s in next_steps_match.group(1).split(',')]
            
            # Extract branch_condition
            branch_condition = None
            branch_match = branch_pattern.search(step_content)
            if branch_match:
                branch_condition = self._parse_branch_condition(branch_match.group(1).strip())
            
            # Extract loop_over
            loop_over = None
            loop_over_match = loop_over_pattern.search(step_content)
            if loop_over_match:
                loop_over = loop_over_match.group(1)
            
            # Extract loop_var
            loop_var = "item"
            loop_var_match = loop_var_pattern.search(step_content)
            if loop_var_match:
                loop_var = loop_var_match.group(1)
            
            # Extract route pattern (same as branch_condition)
            route_match = route_pattern.search(step_content)
            if route_match and not branch_condition:
                branch_condition = self._parse_branch_condition(route_match.group(1).strip())
            
            # Extract parallel pattern
            parallel_steps = None
            parallel_match = parallel_pattern.search(step_content)
            if parallel_match:
                parallel_str = parallel_match.group(1).strip()
                # Parse as list of step names
                parallel_steps = [s.strip().lstrip('- ').strip('"\'') for s in parallel_str.split('\n') if s.strip()]
                # Set next_steps to parallel steps if not already set
                if not next_steps:
                    next_steps = parallel_steps
            
            # Extract images
            images = None
            images_match = images_pattern.search(step_content)
            if images_match:
                images_str = images_match.group(1).strip()
                images = [s.strip() for s in images_str.split('\n') if s.strip()]
            
            # Extract output_file
            output_file = None
            output_file_match = output_file_pattern.search(step_content)
            if output_file_match:
                output_file = output_file_match.group(1).strip()
            
            # Extract repeat config
            repeat_config = None
            repeat_match = repeat_pattern.search(step_content)
            if repeat_match:
                repeat_config = self._parse_agent_config(repeat_match.group(1).strip())
            
            # Get description (text before action block)
            description = step_content
            if action_match:
                description = step_content[:action_match.start()].strip()
            
            # Clean up description (remove code blocks and config lines)
            description = re.sub(r'```.*?```', '', description, flags=re.DOTALL)
            description = re.sub(r'context_from:.*', '', description)
            description = re.sub(r'retain_full_context:.*', '', description)
            description = re.sub(r'output_variable:.*', '', description)
            description = re.sub(r'next_steps:.*', '', description)
            description = re.sub(r'loop_over:.*', '', description)
            description = re.sub(r'loop_var:.*', '', description)
            description = re.sub(r'output_file:.*', '', description)
            description = description.strip()
            
            # Set max_retries from repeat config
            max_retries = 3
            if repeat_config and 'max_iterations' in repeat_config:
                max_retries = int(repeat_config['max_iterations'])
            
            # Build consolidated context config if needed
            context_config = None
            if context_from or not retain_full_context:
                # Only create config if context_from is set OR retain_full_context is False (non-default)
                context_config = TaskContextConfig(
                    from_steps=context_from,
                    retain_full=retain_full_context
                )
            
            # Build consolidated output config if needed
            output_config = None
            if output_variable or output_file:
                output_config = TaskOutputConfig(
                    variable=output_variable,
                    file=output_file
                )
            
            # Build consolidated execution config if needed
            execution_config = None
            if max_retries != 3:  # Only if non-default
                execution_config = TaskExecutionConfig(
                    max_retries=max_retries
                )
            
            # Build consolidated routing config if needed
            routing_config = None
            if next_steps or branch_condition:
                routing_config = TaskRoutingConfig(
                    next_steps=next_steps,
                    branches=branch_condition
                )
            
            steps.append(Task(
                name=step_name,
                description=description,
                action=action,
                condition=condition,
                agent_config=agent_config,
                tools=tools,
                context=context_config,
                output=output_config,
                execution=execution_config,
                routing=routing_config,
                loop_over=loop_over,
                loop_var=loop_var,
                images=images
            ))
        
        return steps
    
    def _parse_branch_condition(self, branch_str: str) -> Dict[str, List[str]]:
        """Parse branch condition from a code block."""
        condition = {}
        for line in branch_str.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Parse as list
                if value.startswith('[') and value.endswith(']'):
                    value = [s.strip().strip('"\'') for s in value[1:-1].split(',')]
                else:
                    value = [value.strip('"\'')]
                
                condition[key] = value
        return condition
    
    def _parse_agent_config(self, agent_str: str) -> Dict[str, Any]:
        """Parse agent configuration from a code block."""
        config = {}
        for line in agent_str.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Handle basic types
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                elif value.isdigit():
                    value = int(value)
                elif value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                config[key] = value
        return config
    
    def _load_workflow(self, file_path: Path) -> Optional[Workflow]:
        """Load a workflow from a file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            
            name = frontmatter.get("name", file_path.stem)
            description = frontmatter.get("description", "")
            variables = frontmatter.get("variables", {})
            
            # Parse variables if it's a string (simple YAML)
            if isinstance(variables, str):
                variables = {}
            
            # Parse workflow-level configuration
            default_llm = frontmatter.get("default_llm")
            planning_enabled = frontmatter.get("planning", False)
            planning_llm = frontmatter.get("planning_llm")
            memory_config = frontmatter.get("memory_config")
            default_agent_config = frontmatter.get("default_agent_config")
            
            steps = self._parse_steps(body)
            
            # Build consolidated planning config if needed
            planning_config = None
            if planning_enabled or planning_llm:
                planning_config = WorkflowPlanningConfig(
                    enabled=planning_enabled,
                    llm=planning_llm
                )
            
            # Build consolidated memory config if needed
            memory_cfg = None
            if memory_config:
                if isinstance(memory_config, dict):
                    memory_cfg = WorkflowMemoryConfig(**memory_config)
                else:
                    memory_cfg = memory_config
            
            workflow = Workflow(
                name=name,
                description=description,
                steps=steps,
                variables=variables,
                file_path=str(file_path),
                default_llm=default_llm,
                planning=planning_config,
                memory=memory_cfg,
                default_agent_config=default_agent_config
            )
            
            self._log(f"Loaded workflow '{name}' with {len(steps)} steps")
            return workflow
            
        except Exception as e:
            self._log(f"Error loading workflow {file_path}: {e}", logging.WARNING)
            return None
    
    def _discover_workflows(self):
        """Discover all workflows in the workspace."""
        self._workflows = {}
        
        workflows_dir = self.workspace_path / self.WORKFLOWS_DIR.replace("/", os.sep)
        
        if not workflows_dir.exists():
            return
        
        for ext in self.SUPPORTED_EXTENSIONS:
            for file_path in workflows_dir.glob(f"*{ext}"):
                workflow = self._load_workflow(file_path)
                if workflow:
                    self._workflows[workflow.name.lower()] = workflow
        
        self._log(f"Discovered {len(self._workflows)} workflows")
    
    def reload(self):
        """Reload all workflows from disk."""
        self._loaded = False
        self._ensure_loaded()
    
    def list_workflows(self) -> List[Workflow]:
        """List all available workflows."""
        self._ensure_loaded()
        return list(self._workflows.values())
    
    def get_workflow(self, name: str) -> Optional[Workflow]:
        """Get a workflow by name."""
        self._ensure_loaded()
        return self._workflows.get(name.lower())
    
    def _substitute_variables(
        self,
        text: str,
        variables: Dict[str, Any]
    ) -> str:
        """
        Substitute {{variable}} placeholders in text.
        
        Delegates to shared substitute_variables() utility for DRY compliance.
        
        Resolution order:
        1. Dynamic variable providers ({{now}}, {{today}}, {{uuid}}, etc.)
        2. Static variables from workflow variables dict
        3. Keep original placeholder if not found
        """
        from praisonaiagents.utils.variables import substitute_variables
        return substitute_variables(text, variables)
    
    def _build_step_context(
        self,
        step: Task,
        step_index: int,
        results: List[Dict[str, Any]],
        variables: Dict[str, Any]
    ) -> str:
        """
        Build context for a step from previous step outputs.
        
        Args:
            step: Current workflow step
            step_index: Index of current step
            results: Results from previous steps
            variables: Current variables dict
            
        Returns:
            Context string to prepend to action
        """
        if step_index == 0 or not results:
            return ""
        
        context_parts = []
        
        if step.context_from:
            # Include only specified steps
            for step_name in step.context_from:
                for prev_result in results:
                    if prev_result["step"] == step_name and prev_result.get("output"):
                        context_parts.append(f"## {step_name} Output:\n{prev_result['output']}")
        elif step.retain_full_context:
            # Include all previous outputs
            for prev_result in results:
                if prev_result.get("output") and prev_result.get("status") == "success":
                    context_parts.append(f"## {prev_result['step']} Output:\n{prev_result['output']}")
        else:
            # Include only the last step's output
            last_result = results[-1]
            if last_result.get("output") and last_result.get("status") == "success":
                context_parts.append(f"## Previous Output:\n{last_result['output']}")
        
        if context_parts:
            return "# Context from previous steps:\n\n" + "\n\n".join(context_parts) + "\n\n"
        return ""
    
    def _update_variables_with_output(
        self,
        step: Task,
        output: str,
        variables: Dict[str, Any],
        results: List[Dict[str, Any]]
    ) -> None:
        """
        Update variables dict with step output for variable substitution.
        
        Args:
            step: Current workflow step
            output: Step output
            variables: Variables dict to update
            results: Results list for previous_output
        """
        # Store output in custom variable name if specified
        if step.output_variable:
            variables[step.output_variable] = output
        
        # Store output with step name (normalized)
        step_var_name = f"{step.name.lower().replace(' ', '_')}_output"
        variables[step_var_name] = output
        
        # Update previous_output for next step
        variables["previous_output"] = output
    
    def load_yaml(
        self,
        file_path: Union[str, Path],
        tool_registry: Optional[Dict[str, Callable]] = None
    ) -> "Workflow":
        """
        Load a workflow from a YAML file.
        
        Args:
            file_path: Path to the YAML workflow file
            tool_registry: Optional dictionary mapping tool names to callable functions
            
        Returns:
            Workflow object ready for execution
            
        Example:
            ```python
            manager = WorkflowManager()
            workflow = manager.load_yaml("research_workflow.yaml")
            result = workflow.start("Research AI trends")
            ```
        """
        from .yaml_parser import YAMLWorkflowParser
        
        parser = YAMLWorkflowParser(tool_registry=tool_registry)
        workflow = parser.parse_file(file_path)
        
        # Store in manager's workflow cache
        workflow_name = workflow.name.lower().replace(' ', '_')
        self._workflows[workflow_name] = workflow
        
        return workflow
    
    def execute_yaml(
        self,
        file_path: Union[str, Path],
        input_data: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        tool_registry: Optional[Dict[str, Callable]] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Load and execute a YAML workflow file.
        
        Args:
            file_path: Path to the YAML workflow file
            input_data: Initial input for the workflow
            variables: Additional variables to merge with workflow variables
            tool_registry: Optional dictionary mapping tool names to callable functions
            verbose: Enable verbose output
            
        Returns:
            Workflow execution results
            
        Example:
            ```python
            manager = WorkflowManager()
            result = manager.execute_yaml(
                "research_workflow.yaml",
                input_data="Research AI trends",
                variables={"topic": "Machine Learning"}
            )
            print(result["output"])
            ```
        """
        workflow = self.load_yaml(file_path, tool_registry=tool_registry)
        
        # Merge additional variables
        if variables:
            workflow.variables.update(variables)
        
        # Set verbose if specified
        if verbose:
            workflow.verbose = verbose
        
        # Execute the workflow
        return workflow.start(input_data or "")
    
    async def aexecute_yaml(
        self,
        file_path: Union[str, Path],
        input_data: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        tool_registry: Optional[Dict[str, Callable]] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Async version of execute_yaml.
        
        Args:
            file_path: Path to the YAML workflow file
            input_data: Initial input for the workflow
            variables: Additional variables to merge with workflow variables
            tool_registry: Optional dictionary mapping tool names to callable functions
            verbose: Enable verbose output
            
        Returns:
            Workflow execution results
        """
        workflow = self.load_yaml(file_path, tool_registry=tool_registry)
        
        # Merge additional variables
        if variables:
            workflow.variables.update(variables)
        
        # Set verbose if specified
        if verbose:
            workflow.verbose = verbose
        
        # Execute the workflow asynchronously
        return await workflow.astart(input_data or "")
    
    def execute(
        self,
        workflow_name: str,
        executor: Optional[Callable[[str], str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        on_step: Optional[Callable[[Task, int], None]] = None,
        on_result: Optional[Callable[[Task, str], None]] = None,
        default_agent: Optional[Any] = None,
        default_llm: Optional[str] = None,
        memory: Optional[Any] = None,
        planning: bool = False,
        stream: bool = False,
        verbose: int = 0,
        checkpoint: Optional[str] = None,
        resume: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow with context passing between steps.
        
        Args:
            workflow_name: Name of the workflow to execute
            executor: Function to execute each step (e.g., agent.chat). Optional if default_agent provided.
            variables: Variables to substitute in steps
            on_step: Callback before each step (step, index)
            on_result: Callback after each step (step, result)
            default_agent: Default agent to use for steps without agent_config
            default_llm: Default LLM model for agent creation
            memory: Shared memory instance
            planning: Enable planning mode
            stream: Enable streaming output
            verbose: Verbosity level
            checkpoint: Save checkpoint after each step with this name
            resume: Resume from checkpoint with this name
            
        Returns:
            Execution results with step outputs and status
        """
        workflow = self.get_workflow(workflow_name)
        if not workflow:
            return {
                "success": False,
                "error": f"Workflow '{workflow_name}' not found",
                "results": []
            }
        
        # Merge variables
        all_variables = {**workflow.variables}
        if variables:
            all_variables.update(variables)
        
        # Use workflow-level defaults if not provided
        if default_llm is None:
            default_llm = workflow.default_llm
        if planning is False and workflow.planning:
            planning = workflow.planning
        
        results = []
        success = True
        start_step = 0
        
        # Resume from checkpoint if specified
        if resume:
            checkpoint_data = self._load_checkpoint(resume)
            if checkpoint_data:
                results = checkpoint_data.get("results", [])
                all_variables = checkpoint_data.get("variables", all_variables)
                start_step = checkpoint_data.get("completed_steps", 0)
                self._log(f"Resuming workflow from step {start_step + 1}")
        
        # Build step lookup for branching
        step_lookup = {step.name: (i, step) for i, step in enumerate(workflow.steps)}
        
        current_step_idx = start_step
        max_iterations = len(workflow.steps) * 10  # Prevent infinite loops
        iteration = 0
        
        while current_step_idx < len(workflow.steps) and iteration < max_iterations:
            iteration += 1
            step = workflow.steps[current_step_idx]
            i = current_step_idx
            
            # Check condition
            if step.condition:
                condition = self._substitute_variables(step.condition, all_variables)
                # Simple condition evaluation (could be enhanced)
                if condition.lower() in ("false", "no", "skip", "0"):
                    results.append({
                        "step": step.name,
                        "status": "skipped",
                        "output": None
                    })
                    current_step_idx += 1
                    continue
            
            # Handle loop_over - iterate over a variable
            if step.loop_over and step.loop_over in all_variables:
                loop_items = all_variables[step.loop_over]
                if isinstance(loop_items, (list, tuple)):
                    loop_results = []
                    for item_idx, item in enumerate(loop_items):
                        # Set loop variable
                        all_variables[step.loop_var] = item
                        all_variables["_loop_index"] = item_idx
                        
                        # Execute step for this item
                        step_result = self._execute_single_step(
                            step=step,
                            step_idx=i,
                            results=results,
                            all_variables=all_variables,
                            executor=executor,
                            default_agent=default_agent,
                            default_llm=default_llm,
                            memory=memory,
                            planning=planning,
                            # verbose parameter removed - Agent no longer accepts it
                            on_step=on_step,
                            on_result=on_result
                        )
                        loop_results.append(step_result)
                        
                        if not step_result["success"] and step.on_error == "stop":
                            success = False
                            break
                    
                    # Store all loop results
                    results.append({
                        "step": step.name,
                        "status": "success" if all(r["success"] for r in loop_results) else "partial",
                        "output": [r["output"] for r in loop_results],
                        "loop_results": loop_results
                    })
                    
                    # Clean up loop variables
                    all_variables.pop(step.loop_var, None)
                    all_variables.pop("_loop_index", None)
                else:
                    self._log(f"loop_over variable '{step.loop_over}' is not iterable")
                
                current_step_idx += 1
                continue
            
            # Callback before step
            if on_step:
                on_step(step, i)
            
            # Execute single step
            step_result = self._execute_single_step(
                step=step,
                step_idx=i,
                results=results,
                all_variables=all_variables,
                executor=executor,
                default_agent=default_agent,
                default_llm=default_llm,
                memory=memory,
                planning=planning,
                # verbose parameter removed - Agent no longer accepts it
                on_step=None,  # Already called above
                on_result=on_result
            )
            
            # Handle skipped steps
            if step_result.get("skipped"):
                results.append({
                    "step": step.name,
                    "status": "skipped",
                    "output": None
                })
                current_step_idx += 1
                continue
            
            results.append({
                "step": step.name,
                "status": "success" if step_result["success"] else "failed",
                "output": step_result["output"],
                "error": step_result.get("error")
            })
            
            # Handle early stop 
            if step_result.get("stop"):
                self._log(f"Workflow stopped early at step '{step.name}'")
                break
            
            # Save checkpoint after each step if enabled
            if checkpoint:
                self._save_checkpoint(
                    name=checkpoint,
                    workflow_name=workflow_name,
                    completed_steps=i + 1,
                    results=results,
                    variables=all_variables
                )
            
            # Handle failure
            if not step_result["success"]:
                if step.on_error == "stop":
                    success = False
                    break
                elif step.on_error == "continue":
                    current_step_idx += 1
                    continue
            
            # Handle branching
            next_step_idx = None
            if step.branch_condition and step_result["output"]:
                # Evaluate branch condition based on output
                output_lower = str(step_result["output"]).lower()
                for branch_key, branch_targets in step.branch_condition.items():
                    if branch_key.lower() in output_lower or output_lower.startswith(branch_key.lower()):
                        if branch_targets and branch_targets[0] in step_lookup:
                            next_step_idx, _ = step_lookup[branch_targets[0]]
                            break
            elif step.next_steps:
                # Use explicit next_steps
                if step.next_steps[0] in step_lookup:
                    next_step_idx, _ = step_lookup[step.next_steps[0]]
            
            # Move to next step
            if next_step_idx is not None:
                current_step_idx = next_step_idx
            else:
                current_step_idx += 1
        
        return {
            "success": success,
            "workflow": workflow.name,
            "results": results,
            "variables": all_variables
        }
    
    def _execute_single_step(
        self,
        step: Task,
        step_idx: int,
        results: List[Dict[str, Any]],
        all_variables: Dict[str, Any],
        executor: Optional[Callable[[str], str]] = None,
        default_agent: Optional[Any] = None,
        default_llm: Optional[str] = None,
        memory: Optional[Any] = None,
        planning: bool = False,
        verbose: int = 0,
        on_step: Optional[Callable[[Task, int], None]] = None,
        on_result: Optional[Callable[[Task, str], None]] = None,
        original_input: str = ""
    ) -> Dict[str, Any]:
        """Execute a single workflow step."""
        # Get previous step output
        previous_output = results[-1].get("output") if results else None
        
        # Create context for step handlers
        context = WorkflowContext(
            input=original_input,
            previous_result=str(previous_output) if previous_output else None,
            current_step=step.name,
            variables=all_variables.copy()
        )
        
        # Check should_run condition if provided
        if step.should_run:
            try:
                if not step.should_run(context):
                    return {
                        "success": True,
                        "output": None,
                        "skipped": True,
                        "stop": False
                    }
            except Exception as e:
                self._log(f"should_run check for step '{step.name}' failed: {e}")
        
        # If step has a custom handler function
        if step.handler:
            try:
                result = step.handler(context)
                # Handle StepResult
                if isinstance(result, StepResult):
                    # Update variables from result
                    if result.variables:
                        all_variables.update(result.variables)
                    return {
                        "success": True,
                        "output": result.output,
                        "stop": result.stop_workflow,  # Early termination flag
                        "error": None
                    }
                else:
                    return {
                        "success": True,
                        "output": str(result),
                        "stop": False,
                        "error": None
                    }
            except Exception as e:
                return {
                    "success": False,
                    "output": None,
                    "stop": False,
                    "error": str(e)
                }
        
        # Build context from previous steps
        context = self._build_step_context(step, step_idx, results, all_variables)
        
        # Substitute variables in action
        action = self._substitute_variables(step.action, all_variables)
        
        # Prepend context to action if available
        if context:
            action = f"{context}# Current Task:\n{action}"
        
        # Get or create executor for this step
        step_executor = executor
        if step_executor is None:
            # Use step's direct agent if provided
            step_agent = step.agent
            
            # Otherwise create agent from config
            if step_agent is None:
                step_agent = self._create_step_agent(
                    step=step,
                    default_agent=default_agent,
                    default_llm=default_llm,
                    memory=memory,
                    planning=planning,
                    verbose=verbose
                )
            
            if step_agent:
                if planning and hasattr(step_agent, 'start'):
                    def agent_executor(prompt, agent=step_agent):
                        return agent.start(prompt)
                    step_executor = agent_executor
                else:
                    def agent_executor(prompt, agent=step_agent):
                        return agent.chat(prompt)
                    step_executor = agent_executor
        
        if step_executor is None:
            return {
                "success": False,
                "output": None,
                "stop": False,
                "error": f"No executor available for step '{step.name}'"
            }
        
        # Execute step with retries
        retries = 0
        step_success = False
        output = None
        error = None
        
        while retries <= step.max_retries and not step_success:
            try:
                output = step_executor(action)
                step_success = True
            except Exception as e:
                error = str(e)
                retries += 1
                if retries <= step.max_retries:
                    self._log(f"Step '{step.name}' failed, retrying ({retries}/{step.max_retries})")
        
        # Update variables with step output
        if output and step_success:
            self._update_variables_with_output(step, output, all_variables, results)
        
        # Callback after step
        if on_result and output:
            on_result(step, output)
        
        return {
            "success": step_success,
            "output": output,
            "stop": False,  # Normal execution doesn't request stop
            "error": error
        }
    
    async def aexecute(
        self,
        workflow_name: str,
        executor: Optional[Callable[[str], str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        on_step: Optional[Callable[[Task, int], None]] = None,
        on_result: Optional[Callable[[Task, str], None]] = None,
        default_agent: Optional[Any] = None,
        default_llm: Optional[str] = None,
        memory: Optional[Any] = None,
        planning: bool = False,
        stream: bool = False,
        verbose: int = 0
    ) -> Dict[str, Any]:
        """
        Async version of execute() for workflow execution.
        
        Args:
            workflow_name: Name of the workflow to execute
            executor: Async function to execute each step. Optional if default_agent provided.
            variables: Variables to substitute in steps
            on_step: Callback before each step (step, index)
            on_result: Callback after each step (step, result)
            default_agent: Default agent to use for steps without agent_config
            default_llm: Default LLM model for agent creation
            memory: Shared memory instance
            planning: Enable planning mode
            stream: Enable streaming output
            verbose: Verbosity level
            
        Returns:
            Execution results with step outputs and status
        """
        import asyncio
        
        workflow = self.get_workflow(workflow_name)
        if not workflow:
            return {
                "success": False,
                "error": f"Workflow '{workflow_name}' not found",
                "results": []
            }
        
        # Merge variables
        all_variables = {**workflow.variables}
        if variables:
            all_variables.update(variables)
        
        # Use workflow-level defaults if not provided
        if default_llm is None:
            default_llm = workflow.default_llm
        if planning is False and workflow.planning:
            planning = workflow.planning
        
        results = []
        success = True
        
        for i, step in enumerate(workflow.steps):
            # Check condition
            if step.condition:
                condition = self._substitute_variables(step.condition, all_variables)
                if condition.lower() in ("false", "no", "skip", "0"):
                    results.append({
                        "step": step.name,
                        "status": "skipped",
                        "output": None
                    })
                    continue
            
            # Callback before step
            if on_step:
                on_step(step, i)
            
            # Build context from previous steps
            context = self._build_step_context(step, i, results, all_variables)
            
            # Substitute variables in action
            action = self._substitute_variables(step.action, all_variables)
            
            # Prepend context to action if available
            if context:
                action = f"{context}# Current Task:\n{action}"
            
            # Get or create executor for this step
            step_executor = executor
            if step_executor is None:
                # Create agent for this step
                step_agent = self._create_step_agent(
                    step=step,
                    default_agent=default_agent,
                    default_llm=default_llm,
                    memory=memory,
                    verbose=verbose
                )
                if step_agent:
                    # Check if agent has async chat method (and it's actually async)
                    if hasattr(step_agent, 'achat') and asyncio.iscoroutinefunction(getattr(step_agent, 'achat', None)):
                        async def async_agent_executor(prompt, agent=step_agent):
                            return await agent.achat(prompt)
                        step_executor = async_agent_executor
                    else:
                        def sync_agent_executor(prompt, agent=step_agent):
                            return agent.chat(prompt)
                        step_executor = sync_agent_executor
            
            if step_executor is None:
                return {
                    "success": False,
                    "error": f"No executor available for step '{step.name}'. Provide executor or default_agent.",
                    "results": results
                }
            
            # Execute step
            retries = 0
            step_success = False
            output = None
            error = None
            
            while retries <= step.max_retries and not step_success:
                try:
                    # Check if executor is async
                    if asyncio.iscoroutinefunction(step_executor):
                        output = await step_executor(action)
                    else:
                        output = step_executor(action)
                    step_success = True
                except Exception as e:
                    error = str(e)
                    retries += 1
                    if retries <= step.max_retries:
                        self._log(f"Step '{step.name}' failed, retrying ({retries}/{step.max_retries})")
            
            # Update variables with step output for next steps
            if output and step_success:
                self._update_variables_with_output(step, output, all_variables, results)
            
            # Callback after step
            if on_result and output:
                on_result(step, output)
            
            results.append({
                "step": step.name,
                "status": "success" if step_success else "failed",
                "output": output,
                "error": error
            })
            
            # Handle failure
            if not step_success:
                if step.on_error == "stop":
                    success = False
                    break
                elif step.on_error == "continue":
                    continue
        
        return {
            "success": success,
            "workflow": workflow.name,
            "results": results,
            "variables": all_variables
        }
    
    def _create_step_agent(
        self,
        step: Task,
        default_agent: Optional[Any] = None,
        default_llm: Optional[str] = None,
        memory: Optional[Any] = None,
        planning: bool = False,
        verbose: int = 0
    ) -> Optional[Any]:
        """
        Create an agent for a specific step.
        
        Args:
            step: Workflow step with optional agent_config
            default_agent: Default agent to use if no config
            default_llm: Default LLM model
            memory: Shared memory instance
            planning: Enable planning mode for the agent
            verbose: Verbosity level
            
        Returns:
            Agent instance or None
        """
        if step.agent_config:
            try:
                from ..agent.agent import Agent
                
                config = step.agent_config.copy()
                # Remove verbose as Agent no longer accepts it
                config.pop("verbose", None)
                config.setdefault("name", f"{step.name}Agent")
                config.setdefault("llm", default_llm)
                # config.setdefault("verbose", verbose)  # Agent no longer accepts verbose
                config.setdefault("planning", planning)
                
                if step.tools:
                    config["tools"] = step.tools
                if memory:
                    config["memory"] = memory
                
                return Agent(**config)
            except Exception as e:
                self._log(f"Failed to create agent for step '{step.name}': {e}", logging.ERROR)
                return default_agent
        
        return default_agent
    
    def create_workflow(
        self,
        name: str,
        description: str = "",
        steps: Optional[List[Dict[str, str]]] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> Workflow:
        """
        Create a new workflow file.
        
        Args:
            name: Workflow name
            description: Workflow description
            steps: List of step dicts with name, description, action
            variables: Default variables
            
        Returns:
            Created Workflow object
        """
        workflows_dir = self.workspace_path / self.WORKFLOWS_DIR.replace("/", os.sep)
        workflows_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = workflows_dir / f"{name.lower().replace(' ', '_')}.md"
        
        # Build content
        lines = ["---"]
        lines.append(f"name: {name}")
        if description:
            lines.append(f"description: {description}")
        if variables:
            lines.append("variables:")
            for k, v in variables.items():
                lines.append(f"  {k}: {v}")
        lines.append("---")
        lines.append("")
        
        # Add steps
        workflow_steps = []
        if steps:
            for i, step in enumerate(steps, 1):
                step_name = step.get("name", f"Step {i}")
                step_desc = step.get("description", "")
                step_action = step.get("action", "")
                
                lines.append(f"## Step {i}: {step_name}")
                if step_desc:
                    lines.append(step_desc)
                lines.append("")
                lines.append("```action")
                lines.append(step_action)
                lines.append("```")
                lines.append("")
                
                workflow_steps.append(Task(
                    name=step_name,
                    description=step_desc,
                    action=step_action
                ))
        
        # Write file
        file_path.write_text("\n".join(lines), encoding="utf-8")
        
        # Create and register workflow
        workflow = Workflow(
            name=name,
            description=description,
            steps=workflow_steps,
            variables=variables or {},
            file_path=str(file_path)
        )
        
        self._workflows[name.lower()] = workflow
        self._log(f"Created workflow '{name}' at {file_path}")
        
        return workflow
    
    def get_stats(self) -> Dict[str, Any]:
        """Get workflow statistics."""
        self._ensure_loaded()
        
        total_steps = sum(len(w.steps) for w in self._workflows.values())
        
        return {
            "total_workflows": len(self._workflows),
            "total_steps": total_steps,
            "workflows": [w.name for w in self._workflows.values()]
        }
    
    # -------------------------------------------------------------------------
    #                          Checkpoint Methods
    # -------------------------------------------------------------------------
    
    def _get_checkpoints_dir(self) -> Path:
        """Get the checkpoints directory path."""
        checkpoints_dir = self.workspace_path / ".praison" / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)
        return checkpoints_dir
    
    def _save_checkpoint(
        self,
        name: str,
        workflow_name: str,
        completed_steps: int,
        results: List[Dict[str, Any]],
        variables: Dict[str, Any]
    ) -> str:
        """
        Save workflow checkpoint for later resumption.
        
        Args:
            name: Checkpoint name
            workflow_name: Name of the workflow
            completed_steps: Number of completed steps
            results: Results from completed steps
            variables: Current variable state
            
        Returns:
            Path to checkpoint file
        """
        import json
        import time
        from datetime import datetime
        
        checkpoint_file = self._get_checkpoints_dir() / f"{name}.json"
        
        checkpoint_data = {
            "name": name,
            "workflow_name": workflow_name,
            "completed_steps": completed_steps,
            "results": results,
            "variables": variables,
            "saved_at": time.time(),
            "saved_at_iso": datetime.now().isoformat()
        }
        
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2, default=str)
        
        self._log(f"Saved checkpoint '{name}' at step {completed_steps}")
        return str(checkpoint_file)
    
    def _load_checkpoint(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load a workflow checkpoint.
        
        Args:
            name: Checkpoint name
            
        Returns:
            Checkpoint data or None if not found
        """
        import json
        
        checkpoint_file = self._get_checkpoints_dir() / f"{name}.json"
        
        if not checkpoint_file.exists():
            self._log(f"Checkpoint '{name}' not found")
            return None
        
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    
    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """
        List all saved checkpoints.
        
        Returns:
            List of checkpoint info dicts
        """
        import json
        
        checkpoints = []
        checkpoints_dir = self._get_checkpoints_dir()
        
        for checkpoint_file in checkpoints_dir.glob("*.json"):
            try:
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)
                checkpoints.append({
                    "name": data.get("name", checkpoint_file.stem),
                    "workflow": data.get("workflow_name", ""),
                    "completed_steps": data.get("completed_steps", 0),
                    "saved_at": data.get("saved_at_iso", "")
                })
            except Exception:
                continue
        
        checkpoints.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
        return checkpoints
    
    def delete_checkpoint(self, name: str) -> bool:
        """
        Delete a checkpoint.
        
        Args:
            name: Checkpoint name
            
        Returns:
            True if deleted successfully
        """
        checkpoint_file = self._get_checkpoints_dir() / f"{name}.json"
        
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            self._log(f"Deleted checkpoint '{name}'")
            return True
        return False


def create_workflow_manager(
    workspace_path: Optional[str] = None,
    **kwargs
) -> WorkflowManager:
    """
    Create a WorkflowManager instance.
    
    Args:
        workspace_path: Path to workspace
        **kwargs: Additional configuration
        
    Returns:
        WorkflowManager instance
    """
    return WorkflowManager(workspace_path=workspace_path, **kwargs)
