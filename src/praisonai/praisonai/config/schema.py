"""
YAML configuration schema validation using Pydantic models.

This module provides schema validation for agents/tasks/workflow YAML configurations
with fail-fast validation, aggregated errors, and cross-reference checking.
"""

from enum import Enum
from typing import Optional, Dict, List, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator
import re


#: Stable, published URL for the ``agents.yaml`` JSON Schema, mirroring the
#: hosting convention used for the CLI-config schema (``config.schema.json``).
#: Editors that speak the YAML language server use this via a leading
#: ``# yaml-language-server: $schema=<url>`` header to provide autocomplete,
#: inline validation, and hover docs while authoring the agent YAML.
AGENTS_SCHEMA_URL = (
    "https://raw.githubusercontent.com/MervinPraison/PraisonAI/main/"
    "src/praisonai/praisonai/config/agents.schema.json"
)

#: Leading YAML comment prepended to scaffolded ``agents.yaml`` files so editors
#: wire up validation out of the box. A leading comment is ignored by
#: ``yaml.safe_load``, so execution is unaffected.
AGENTS_SCHEMA_HEADER = f"# yaml-language-server: $schema={AGENTS_SCHEMA_URL}\n"


class ProcessType(str, Enum):
    """Process type for task execution."""
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"
    CONSENSUAL = "consensual"
    WORKFLOW = "workflow"


class HandoffPolicy(str, Enum):
    """Handoff policy for agent delegation."""
    ANY = "any"
    ALL = "all"
    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"


class ToolRetryPolicy(BaseModel):
    """Configuration for tool retry behavior."""
    max_attempts: int = Field(default=3, ge=1, description="Maximum retry attempts")
    delay: float = Field(default=1.0, ge=0, description="Delay between retries in seconds")
    backoff_factor: float = Field(default=2.0, ge=1, description="Exponential backoff factor")
    max_delay: float = Field(default=60.0, ge=0, description="Maximum delay between retries")


class HandoffConfig(BaseModel):
    """Configuration for agent handoff behavior."""
    to: List[str] = Field(default_factory=list, description="List of agent roles to handoff to")
    policy: Optional[HandoffPolicy] = Field(default=HandoffPolicy.ANY, description="Handoff policy")
    timeout: Optional[float] = Field(default=300.0, ge=0, description="Handoff timeout in seconds")
    max_depth: Optional[int] = Field(default=5, ge=1, description="Maximum handoff depth")
    max_concurrent: Optional[int] = Field(default=3, ge=1, description="Maximum concurrent handoffs")
    detect_cycles: Optional[bool] = Field(default=True, description="Detect handoff cycles")


class ApprovalConfig(BaseModel):
    """Configuration for agent approval requirements."""
    enabled: bool = Field(default=False, description="Enable approval mode")
    timeout: Optional[float] = Field(default=300.0, ge=0, description="Approval timeout in seconds")
    level: Optional[str] = Field(default="tool", description="Approval level (tool/step/all)")
    auto_approve: List[str] = Field(default_factory=list, description="Auto-approved tools")


class RuntimeConfig(BaseModel):
    """Configuration for agent runtime environment."""
    type: str = Field(..., description="Runtime type (docker/sandbox/local)")
    image: Optional[str] = Field(default=None, description="Runtime image")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")


class CliBackendConfig(BaseModel):
    """Configuration for CLI backend."""
    type: str = Field(..., description="CLI backend type")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Backend-specific config")


class AgentConfig(BaseModel):
    """Configuration for a single agent/role."""
    # Required fields
    role: str = Field(..., description="Agent role")
    goal: str = Field(..., description="Agent goal")
    # Optional at the schema level: the runtime treats 'instructions' as an
    # alias for 'backstory', so an agent needs only one of the two. The
    # model_validator below enforces "at least one is present".
    backstory: Optional[str] = Field(default=None, description="Agent backstory")

    # Optional fields
    instructions: Optional[str] = Field(default=None, description="Additional instructions (alias for backstory)")
    tools: Optional[List[str]] = Field(default=None, description="List of tools the agent can use")
    toolsets: Optional[List[str]] = Field(default=None, description="List of toolsets the agent can use")
    llm: Optional[Union[str, Dict[str, Any]]] = Field(default=None, description="LLM model to use (string or dict with 'model' key)")
    function_calling_llm: Optional[Union[str, Dict[str, Any]]] = Field(default=None, description="LLM for function calling (string or dict with 'model' key)")
    tasks: Optional[Dict[str, Union[Dict[str, Any], 'TaskConfig']]] = Field(default=None, description="Tasks assigned to this agent")
    
    # Behavior configuration
    allow_delegation: Optional[bool] = Field(default=True, description="Allow delegation to other agents")
    max_iter: Optional[int] = Field(default=10, ge=1, description="Maximum iterations")
    max_rpm: Optional[int] = Field(default=60, ge=1, description="Maximum requests per minute")
    max_execution_time: Optional[float] = Field(default=None, ge=0, description="Maximum execution time")
    verbose: Optional[bool] = Field(default=False, description="Verbose output")
    cache: Optional[bool] = Field(default=True, description="Enable caching")
    streaming: Optional[bool] = Field(default=False, description="Enable streaming")
    stream: Optional[bool] = Field(default=None, description="Alias for streaming")
    
    # Advanced configuration
    tool_timeout: Optional[float] = Field(default=None, ge=0, description="Tool execution timeout")
    tool_retry_policy: Optional[Union[Dict[str, Any], ToolRetryPolicy]] = Field(default=None, description="Tool retry policy")
    planning_tools: Optional[List[str]] = Field(default=None, description="Planning tools")
    planning: Optional[bool] = Field(default=False, description="Enable planning mode")
    autonomy: Optional[int] = Field(default=0, ge=0, le=10, description="Autonomy level (0-10)")
    guardrails: Optional[List[str]] = Field(default=None, description="Guardrails to apply")
    approval: Optional[Union[bool, Dict[str, Any], ApprovalConfig]] = Field(default=None, description="Approval configuration")
    skills: Optional[List[str]] = Field(default=None, description="Skills the agent has")
    reflection: Optional[bool] = Field(default=False, description="Enable reflection")
    handoff: Optional[Union[Dict[str, Any], HandoffConfig]] = Field(default=None, description="Handoff configuration")
    web: Optional[bool] = Field(default=False, description="Enable web access")
    web_fetch: Optional[bool] = Field(default=False, description="Enable web fetching")
    
    # Runtime configuration
    cli_backend: Optional[Union[str, Dict[str, Any], CliBackendConfig]] = Field(default=None, description="CLI backend config")
    runtime: Optional[Union[str, Dict[str, Any], RuntimeConfig]] = Field(default=None, description="Runtime configuration")
    
    # Templates
    system_template: Optional[str] = Field(default=None, description="System prompt template")
    prompt_template: Optional[str] = Field(default=None, description="Prompt template")
    response_template: Optional[str] = Field(default=None, description="Response template")
    
    @model_validator(mode='before')
    @classmethod
    def normalize_cli_retry_policy(cls, data):
        """Accept praisonaiagents RetryPolicy objects injected by CLI merge."""
        if isinstance(data, dict) and data.get("tool_retry_policy") is not None:
            policy = data["tool_retry_policy"]
            if isinstance(policy, dict):
                return data
            try:
                from praisonaiagents.tools.retry import RetryPolicy as AgentRetryPolicy

                if isinstance(policy, AgentRetryPolicy):
                    data = dict(data)
                    data["tool_retry_policy"] = {
                        "max_attempts": policy.max_attempts,
                        "delay": policy.initial_delay_ms / 1000.0,
                        "backoff_factor": policy.backoff_factor,
                        "max_delay": policy.max_delay_ms / 1000.0,
                    }
            except (ImportError, AttributeError, TypeError):
                pass
        return data

    @model_validator(mode='before')
    @classmethod
    def normalize_stream_alias(cls, data):
        """Map legacy 'stream' into canonical 'streaming'."""
        if isinstance(data, dict) and 'streaming' not in data and 'stream' in data:
            data['streaming'] = data['stream']
        return data

    @model_validator(mode='after')
    def require_backstory_or_instructions(self):
        """Require at least one of 'backstory'/'instructions' (they are aliases).

        The runtime accepts either field, so validation must too — otherwise
        runnable workflows using only 'instructions' fail validation.
        """
        if not self.backstory and not self.instructions:
            raise ValueError(
                f"Agent '{self.role}' requires either 'backstory' or 'instructions'."
            )
        return self
    
    @model_validator(mode='after')
    def normalize_config_objects(self):
        """Convert dict configs to proper model objects."""
        # Convert tasks dict to TaskConfig objects
        if isinstance(self.tasks, dict):
            normalized_tasks = {}
            for task_name, task_config in self.tasks.items():
                if isinstance(task_config, dict):
                    # Add the agent field if not present (validator-safe identifier)
                    if 'agent' not in task_config:
                        safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', self.role.strip()).strip('_')
                        task_config['agent'] = safe_name or 'agent'
                    normalized_tasks[task_name] = TaskConfig(**task_config)
                else:
                    normalized_tasks[task_name] = task_config
            self.tasks = normalized_tasks
        
        # Convert tool_retry_policy dict to ToolRetryPolicy
        if isinstance(self.tool_retry_policy, dict):
            self.tool_retry_policy = ToolRetryPolicy(**self.tool_retry_policy)
        elif self.tool_retry_policy is not None and not isinstance(
            self.tool_retry_policy, ToolRetryPolicy
        ):
            try:
                from praisonaiagents.tools.retry import RetryPolicy as AgentRetryPolicy

                if isinstance(self.tool_retry_policy, AgentRetryPolicy):
                    self.tool_retry_policy = ToolRetryPolicy(
                        max_attempts=self.tool_retry_policy.max_attempts,
                        delay=self.tool_retry_policy.initial_delay_ms / 1000.0,
                        backoff_factor=self.tool_retry_policy.backoff_factor,
                        max_delay=self.tool_retry_policy.max_delay_ms / 1000.0,
                    )
            except (ImportError, AttributeError, TypeError):
                pass
        
        # Convert approval dict/bool to ApprovalConfig
        if isinstance(self.approval, bool):
            self.approval = ApprovalConfig(enabled=self.approval)
        elif isinstance(self.approval, dict):
            self.approval = ApprovalConfig(**self.approval)
        
        # Convert handoff dict to HandoffConfig
        if isinstance(self.handoff, dict):
            self.handoff = HandoffConfig(**self.handoff)
        
        # Convert cli_backend to CliBackendConfig
        if isinstance(self.cli_backend, str):
            self.cli_backend = CliBackendConfig(type=self.cli_backend)
        elif isinstance(self.cli_backend, dict):
            self.cli_backend = CliBackendConfig(**self.cli_backend)
        
        # Convert runtime to RuntimeConfig
        if isinstance(self.runtime, str):
            self.runtime = RuntimeConfig(type=self.runtime)
        elif isinstance(self.runtime, dict):
            self.runtime = RuntimeConfig(**self.runtime)
        
        return self


class TaskConfig(BaseModel):
    """Configuration for a single task."""
    description: str = Field(..., description="Task description")
    agent: str = Field(..., description="Agent to execute the task")
    
    # Optional fields
    expected_output: Optional[str] = Field(default=None, description="Expected output format")
    tools: Optional[List[str]] = Field(default=None, description="Tools to use for this task")
    context: Optional[List[str]] = Field(default=None, description="Context from other tasks")
    output_file: Optional[str] = Field(default=None, description="Output file path")
    async_execution: Optional[bool] = Field(default=False, description="Execute asynchronously")
    condition: Optional[str] = Field(default=None, description="Condition for task execution")
    
    @field_validator('agent')
    @classmethod
    def validate_agent_name(cls, v):
        """Validate agent name format."""
        if not v or not v.strip():
            raise ValueError("Agent name cannot be empty")
        # Allow alphanumeric, underscore, hyphen
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(f"Invalid agent name: {v}. Use only letters, numbers, underscore, and hyphen.")
        return v


class WorkflowStep(BaseModel):
    """Configuration for a workflow step.

    Accepts both dialects the runtime understands:

    1. Explicit ``type``-based steps (``type: task|parallel|loop|route``), and
    2. The bare runtime forms the engine's ``YAMLWorkflowParser`` executes:
       ``- agent:`` / ``route:`` / ``if:`` / ``loop:`` / ``repeat:`` /
       ``parallel:`` / ``include:`` steps, where ``name``/``type`` are optional.

    A step is valid if it matches either dialect, so runnable example workflows
    no longer fail schema validation (and vice versa).
    """
    # Optional in the runtime dialect (bare agent/route/if/... steps omit them).
    name: Optional[str] = Field(default=None, description="Step name")
    type: Optional[str] = Field(default=None, description="Step type (task/route/parallel/loop)")
    agent: Optional[str] = Field(default=None, description="Agent for task/agent steps")
    task: Optional[str] = Field(default=None, description="Task description")
    action: Optional[str] = Field(default=None, description="Action prompt for agent steps")
    steps: Optional[List['WorkflowStep']] = Field(default=None, description="Sub-steps for complex types")
    condition: Optional[str] = Field(default=None, description="Condition for step execution")
    routes: Optional[Dict[str, List['WorkflowStep']]] = Field(default=None, description="Routes for routing steps")
    count: Optional[int] = Field(default=None, ge=1, description="Loop count")

    # Runtime-dialect step keys (any one of these marks the step form).
    route: Optional[Any] = Field(default=None, description="Route step: mapping of key -> [agents]")
    loop: Optional[Any] = Field(default=None, description="Loop step configuration")
    repeat: Optional[Any] = Field(default=None, description="Repeat step configuration")
    parallel: Optional[Any] = Field(default=None, description="Parallel step configuration")
    include: Optional[Any] = Field(default=None, description="Include another workflow file")

    class Config:
        # ``if:`` is a Python keyword; allow it (and any other engine keys)
        # through by name so runtime workflows validate without renaming.
        extra = "allow"

    # Keys that identify a bare runtime-dialect step (no explicit ``type``).
    _RUNTIME_STEP_KEYS = ('agent', 'route', 'loop', 'repeat', 'parallel', 'include', 'if')

    def _has_runtime_form(self) -> bool:
        for key in self._RUNTIME_STEP_KEYS:
            if getattr(self, key, None) is not None:
                return True
            # ``if`` is not a declared field; read from extras.
            if key == 'if' and (self.__pydantic_extra__ or {}).get('if') is not None:
                return True
        return False

    @model_validator(mode='after')
    def validate_step_type(self):
        """Validate step configuration for whichever dialect is used."""
        label = self.name or "<unnamed>"

        # Runtime dialect (bare agent/route/if/loop/repeat/parallel/include):
        # accept as-is; the engine's YAMLWorkflowParser owns its structure.
        if self.type is None:
            if self._has_runtime_form():
                return self
            raise ValueError(
                f"Step '{label}' must declare a 'type' or one of "
                f"{', '.join(self._RUNTIME_STEP_KEYS)}."
            )

        # Explicit type-based dialect.
        allowed = {'task', 'parallel', 'loop', 'route', 'agent'}
        if self.type not in allowed:
            raise ValueError(
                f"Step '{label}' has invalid type '{self.type}'. "
                f"Allowed values: {', '.join(sorted(allowed))}"
            )

        if self.type == 'task':
            if not self.agent or not self.task:
                raise ValueError(f"Task step '{label}' requires both 'agent' and 'task' fields")
        elif self.type in ('parallel', 'loop'):
            if not self.steps:
                raise ValueError(f"{self.type.capitalize()} step '{label}' requires 'steps' field")
            if self.type == 'loop' and self.count is None:
                raise ValueError(f"Loop step '{label}' requires 'count' field")
        elif self.type == 'route':
            if not self.routes and not self.route:
                raise ValueError(f"Route step '{label}' requires 'routes' field")

        return self


# Enable forward references for recursive models
WorkflowStep.model_rebuild()


class WorkflowConfig(BaseModel):
    """Configuration for workflow execution."""
    default_llm: Optional[str] = Field(default=None, description="Default LLM for workflow")
    timeout: Optional[float] = Field(default=None, ge=0, description="Workflow timeout")
    max_parallel: Optional[int] = Field(default=3, ge=1, description="Maximum parallel executions")
    error_handling: Optional[str] = Field(default="stop", description="Error handling strategy")


class GlobalConfig(BaseModel):
    """Global configuration settings."""
    acp: Optional[bool] = Field(default=False, description="Enable ACP mode")
    lsp: Optional[bool] = Field(default=False, description="Enable LSP mode")


class YAMLConfig(BaseModel):
    """Complete YAML configuration schema."""
    # Metadata
    name: Optional[str] = Field(default=None, description="Configuration name")
    description: Optional[str] = Field(default=None, description="Configuration description")
    framework: Optional[str] = Field(default="praisonai", description="Framework to use")
    process: Optional[ProcessType] = Field(default=ProcessType.SEQUENTIAL, description="Process type")
    type: Optional[str] = Field(default=None, description="Configuration type discriminator")
    
    # Core sections (at least one required)
    roles: Optional[Dict[str, AgentConfig]] = Field(default=None, description="Agent roles (canonical)")
    agents: Optional[Dict[str, AgentConfig]] = Field(default=None, description="Agents (backward compat)")
    tasks: Optional[List[TaskConfig]] = Field(default=None, description="Task definitions")
    workflow: Optional[WorkflowConfig] = Field(default=None, description="Workflow configuration")
    steps: Optional[List[WorkflowStep]] = Field(default=None, description="Workflow steps")
    
    # Input/topic
    input: Optional[str] = Field(default=None, description="Input/topic (canonical)")
    topic: Optional[str] = Field(default=None, description="Topic (backward compat)")
    
    # Tools
    tools: Optional[List[str]] = Field(default=None, description="Global tools")
    toolsets: Optional[List[str]] = Field(default=None, description="Global toolsets")
    
    # Global config
    config: Optional[GlobalConfig] = Field(default=None, description="Global configuration")
    
    # LLM config
    llm: Optional[str] = Field(default=None, description="Default LLM")
    models: Optional[Dict[str, Any]] = Field(default=None, description="Model configurations")
    providers: Optional[Dict[str, Any]] = Field(default=None, description="Provider configurations")

    # Deployment / dependency declarations
    deploy: Optional[Dict[str, Any]] = Field(default=None, description="Deployment configuration")
    dependencies: Optional[Any] = Field(default=None, description="Task dependency declarations")
    
    @model_validator(mode='after')
    def validate_config_structure(self):
        """Validate overall configuration structure."""
        # Ensure at least one of roles/agents is present
        if not self.roles and not self.agents:
            raise ValueError("Configuration must define either 'roles' or 'agents' section")
        
        # Normalize agents -> roles
        if self.agents and not self.roles:
            self.roles = self.agents
        
        # Validate workflow mode requirements
        if self.process == ProcessType.WORKFLOW:
            if not self.steps and not self.workflow:
                raise ValueError("Workflow process requires 'steps' or 'workflow' section")
        
        # Normalize input/topic
        if self.topic and not self.input:
            self.input = self.topic
        
        return self
    
    def validate_cross_references(self) -> List[str]:
        """Validate cross-references between agents, tasks, and tools.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Get all defined agent names
        agent_names = set()
        if self.roles:
            agent_names.update(self.roles.keys())
        if self.agents:
            agent_names.update(self.agents.keys())
        
        # Validate task agent references
        if self.tasks:
            for i, task in enumerate(self.tasks):
                if task.agent not in agent_names:
                    errors.append(
                        f"Task {i+1} references undefined agent '{task.agent}'. "
                        f"Available agents: {', '.join(sorted(agent_names))}"
                    )
        
        def check_agent(name: Any, step_path: str):
            """Flag an agent reference that isn't a defined agent."""
            if isinstance(name, str) and name and name not in agent_names:
                errors.append(
                    f"Workflow {step_path} references undefined agent '{name}'. "
                    f"Available agents: {', '.join(sorted(agent_names))}"
                )

        def validate_substep_payload(payload: Any, step_path: str):
            """Walk a nested sub-step payload and validate ``agent:`` keys.

            Used for ``parallel``/``loop``/``repeat``/``if`` bodies, whose
            agent references only ever appear as an ``agent:`` key on a
            sub-step dict. Non-agent scalars (e.g. ``loop: {over: topics}``,
            where ``topics`` is a variable) are intentionally left alone.
            """
            if isinstance(payload, dict):
                if 'agent' in payload:
                    check_agent(payload.get('agent'), step_path)
                for value in payload.values():
                    validate_substep_payload(value, step_path)
            elif isinstance(payload, list):
                for item in payload:
                    validate_substep_payload(item, step_path)

        def validate_route_payload(payload: Any, step_path: str):
            """Validate a ``route:`` mapping's agent references.

            Runtime shape is ``{route_key: [agent_name, ...]}`` (scalars in
            the value lists are agent names), so every leaf scalar is an
            agent reference to check.
            """
            if isinstance(payload, dict):
                for value in payload.values():
                    validate_route_payload(value, step_path)
            elif isinstance(payload, list):
                for item in payload:
                    validate_route_payload(item, step_path)
            else:
                check_agent(payload, step_path)

        # Validate workflow step agent references
        def validate_steps(steps: List[WorkflowStep], path: str = ""):
            for i, step in enumerate(steps or []):
                step_path = f"{path}step[{i+1}]({step.name or '<unnamed>'})"

                # Validate agent references for both dialects (type: task and
                # the bare ``agent:`` runtime form).
                check_agent(step.agent, step_path)

                # Recursively check sub-steps
                if step.steps:
                    validate_steps(step.steps, f"{step_path}/")
                
                # Check routes
                if step.routes:
                    for route_name, route_steps in step.routes.items():
                        validate_steps(route_steps, f"{step_path}/route[{route_name}]/")

                # Check bare runtime-form payloads that hold agent references
                # but aren't parsed into typed WorkflowStep objects.
                validate_route_payload(step.route, f"{step_path}/route")
                for key in ('parallel', 'loop', 'repeat'):
                    validate_substep_payload(getattr(step, key, None), f"{step_path}/{key}")
                # ``if`` is a Python keyword; it lands in pydantic extras.
                if_payload = (step.__pydantic_extra__ or {}).get('if') if step.__pydantic_extra__ else None
                validate_substep_payload(if_payload, f"{step_path}/if")

        if self.steps:
            validate_steps(self.steps)
        
        # Validate handoff references
        all_roles = set()
        all_agent_configs = []
        for agents_dict in [self.roles, self.agents]:
            if agents_dict:
                all_agent_configs.extend(agents_dict.values())
                for agent_config in agents_dict.values():
                    all_roles.add(agent_config.role)
        
        for agent_config in all_agent_configs:
            if agent_config.handoff and isinstance(agent_config.handoff, HandoffConfig):
                for target in agent_config.handoff.to:
                    if target not in all_roles:
                        errors.append(
                            f"Agent '{agent_config.role}' handoff references undefined role '{target}'. "
                            f"Available roles: {', '.join(sorted(all_roles))}"
                        )
        
        return errors


class ValidationResult(BaseModel):
    """Result of YAML validation."""
    valid: bool = Field(..., description="Whether configuration is valid")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    warnings: List[str] = Field(default_factory=list, description="List of validation warnings")
    
    def format_message(self) -> str:
        """Format validation result as a readable message."""
        if self.valid:
            msg = "✓ Configuration is valid"
            if self.warnings:
                msg += f"\n\nWarnings ({len(self.warnings)}):\n"
                for i, warning in enumerate(self.warnings, 1):
                    msg += f"  {i}. {warning}\n"
            return msg
        
        msg = f"✗ Configuration validation failed with {len(self.errors)} error(s)"
        if self.errors:
            msg += "\n\nErrors:\n"
            for i, error in enumerate(self.errors, 1):
                msg += f"  {i}. {error}\n"
        
        if self.warnings:
            msg += f"\nWarnings ({len(self.warnings)}):\n"
            for i, warning in enumerate(self.warnings, 1):
                msg += f"  {i}. {warning}\n"
        
        return msg


# Resolve forward references for TaskConfig in AgentConfig
AgentConfig.model_rebuild()


def _relax_agent_config_for_editor(defs: Dict[str, Any]) -> None:
    """Loosen ``AgentConfig`` in ``$defs`` to match the runtime contract.

    The strict :class:`AgentConfig` marks ``role``/``goal``/``backstory`` as
    required, but the runtime (``agents_generator._normalize_yaml_config`` and
    the adapter canonicalisation step) auto-fills ``role``/``goal`` from the
    agent key and maps ``instructions`` -> ``backstory``. Publishing the strict
    form would make editors flag valid, executable YAML as invalid, so the
    published (authoring) schema drops those ``required`` entries. This only
    affects the emitted artefact — the strict model used by ``ConfigValidator``
    is untouched.
    """
    agent_def = defs.get("AgentConfig")
    if isinstance(agent_def, dict):
        agent_def.pop("required", None)


def _allow_list_form_agents(schema: Dict[str, Any]) -> None:
    """Allow list-form ``roles``/``agents`` in the published schema.

    The runtime accepts both the canonical dict form and a list of named
    entries (``agents_generator._list_to_dict``). The dict form remains the
    documented default; the list form is added as an alternative so editors
    don't reject the list variant.
    """
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    list_form = {
        "type": "array",
        "items": {"$ref": "#/$defs/AgentConfig"},
    }
    for key in ("roles", "agents"):
        entry = props.get(key)
        if not isinstance(entry, dict):
            continue
        dict_form = {k: v for k, v in entry.items() if k != "description"}
        props[key] = {
            "anyOf": [dict_form, list_form],
            "description": entry.get("description", ""),
        }


def generate_agents_schema() -> Dict[str, Any]:
    """Generate the JSON Schema for the ``agents.yaml`` file.

    Derived directly from :class:`YAMLConfig` (Pydantic's ``model_json_schema``)
    and decorated with the standard ``$schema``/``$id``/``title`` metadata so the
    artefact is self-describing and mirrors the CLI-config schema convention.

    The published (authoring) schema is deliberately a touch more permissive
    than the strict validator so editors accept every YAML shape the runtime
    accepts: list-form ``roles``/``agents`` and configs that rely on runtime
    normalisation (``instructions`` -> ``backstory``, auto-filled ``role``/
    ``goal``). The strict :class:`YAMLConfig` used by ``ConfigValidator`` is
    left unchanged.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": AGENTS_SCHEMA_URL,
        **YAMLConfig.model_json_schema(),
        "title": "PraisonAI Agents Configuration",
        "description": (
            "Schema for agents.yaml consumed by the PraisonAI agent runtime "
            "(roles/agents, tasks, tools, llm, workflow)."
        ),
    }

    defs = schema.get("$defs")
    if isinstance(defs, dict):
        _relax_agent_config_for_editor(defs)
    _allow_list_form_agents(schema)

    return schema