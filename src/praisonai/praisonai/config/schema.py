"""
YAML configuration schema validation using Pydantic models.

This module provides schema validation for agents/tasks/workflow YAML configurations
with fail-fast validation, aggregated errors, and cross-reference checking.
"""

from enum import Enum
from typing import Optional, Dict, List, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator
import re


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
    backstory: str = Field(..., description="Agent backstory")
    
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
            except ImportError:
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
    def normalize_config_objects(self):
        """Convert dict configs to proper model objects."""
        # Convert tasks dict to TaskConfig objects
        if isinstance(self.tasks, dict):
            normalized_tasks = {}
            for task_name, task_config in self.tasks.items():
                if isinstance(task_config, dict):
                    # Add the agent field if not present (use self.role)
                    if 'agent' not in task_config:
                        task_config['agent'] = self.role
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
            except ImportError:
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
    """Configuration for a workflow step."""
    name: str = Field(..., description="Step name")
    type: Optional[str] = Field(default="task", description="Step type (task/route/parallel/loop)")
    agent: Optional[str] = Field(default=None, description="Agent for task steps")
    task: Optional[str] = Field(default=None, description="Task description")
    steps: Optional[List['WorkflowStep']] = Field(default=None, description="Sub-steps for complex types")
    condition: Optional[str] = Field(default=None, description="Condition for step execution")
    routes: Optional[Dict[str, List['WorkflowStep']]] = Field(default=None, description="Routes for routing steps")
    count: Optional[int] = Field(default=None, ge=1, description="Loop count")
    
    @model_validator(mode='after')
    def validate_step_type(self):
        """Validate step configuration based on type."""
        allowed = {'task', 'parallel', 'loop', 'route'}
        if self.type not in allowed:
            raise ValueError(
                f"Step '{self.name}' has invalid type '{self.type}'. "
                f"Allowed values: {', '.join(sorted(allowed))}"
            )
        
        if self.type == 'task':
            if not self.agent or not self.task:
                raise ValueError(f"Task step '{self.name}' requires both 'agent' and 'task' fields")
        elif self.type in ('parallel', 'loop'):
            if not self.steps:
                raise ValueError(f"{self.type.capitalize()} step '{self.name}' requires 'steps' field")
            if self.type == 'loop' and self.count is None:
                raise ValueError(f"Loop step '{self.name}' requires 'count' field")
        elif self.type == 'route':
            if not self.routes:
                raise ValueError(f"Route step '{self.name}' requires 'routes' field")
        
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
        
        # Validate workflow step agent references
        def validate_steps(steps: List[WorkflowStep], path: str = ""):
            for i, step in enumerate(steps or []):
                step_path = f"{path}step[{i+1}]({step.name})"
                
                if step.type == 'task' and step.agent:
                    if step.agent not in agent_names:
                        errors.append(
                            f"Workflow {step_path} references undefined agent '{step.agent}'. "
                            f"Available agents: {', '.join(sorted(agent_names))}"
                        )
                
                # Recursively check sub-steps
                if step.steps:
                    validate_steps(step.steps, f"{step_path}/")
                
                # Check routes
                if step.routes:
                    for route_name, route_steps in step.routes.items():
                        validate_steps(route_steps, f"{step_path}/route[{route_name}]/")
        
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