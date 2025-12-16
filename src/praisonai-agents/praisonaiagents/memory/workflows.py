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
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Literal
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    name: str
    description: str = ""
    action: str = ""  # The action/prompt to execute
    condition: Optional[str] = None  # Optional condition for execution (string)
    should_run: Optional[Callable[['WorkflowContext'], bool]] = None  # Function to check if step should run
    handler: Optional[Callable[['WorkflowContext'], 'StepResult']] = None  # Custom function instead of agent
    on_error: Literal["stop", "continue", "retry"] = "stop"
    max_retries: int = 1
    
    # Context passing fields
    context_from: Optional[List[str]] = None  # Which previous steps to include context from
    retain_full_context: bool = True  # Include all previous outputs vs only last
    output_variable: Optional[str] = None  # Store output in this variable name
    
    # Agent configuration fields
    agent_config: Optional[Dict[str, Any]] = None  # Per-step agent config {role, goal, backstory, llm}
    agent: Optional[Any] = None  # Direct agent instance for this step
    tools: Optional[List[Any]] = None  # Tools for this step
    
    # Branching fields
    next_steps: Optional[List[str]] = None  # Next step names for branching
    branch_condition: Optional[Dict[str, List[str]]] = None  # {"success": ["step2"], "failure": ["step3"]}
    
    # Loop fields
    loop_over: Optional[str] = None  # Variable name to iterate over (e.g., "items")
    loop_var: str = "item"  # Variable name for current item in loop
    
    # Backward compatibility aliases
    @property
    def evaluator(self):
        return self.should_run
    
    @property
    def executor(self):
        return self.handler
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "condition": self.condition,
            "should_run": self.should_run is not None,
            "handler": self.handler is not None,
            "agent": self.agent is not None,
            "on_error": self.on_error,
            "max_retries": self.max_retries,
            "context_from": self.context_from,
            "retain_full_context": self.retain_full_context,
            "output_variable": self.output_variable,
            "agent_config": self.agent_config,
            "tools": self.tools,
            "next_steps": self.next_steps,
            "branch_condition": self.branch_condition,
            "loop_over": self.loop_over,
            "loop_var": self.loop_var
        }


@dataclass
class Workflow:
    """A complete workflow with multiple steps."""
    name: str
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    
    # Default configuration for all steps
    default_agent_config: Optional[Dict[str, Any]] = None  # Default agent for all steps
    default_llm: Optional[str] = None  # Default LLM model
    memory_config: Optional[Dict[str, Any]] = None  # Memory configuration
    planning: bool = False  # Enable planning mode
    planning_llm: Optional[str] = None  # LLM for planning
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "variables": self.variables,
            "file_path": self.file_path,
            "default_agent_config": self.default_agent_config,
            "default_llm": self.default_llm,
            "memory_config": self.memory_config,
            "planning": self.planning,
            "planning_llm": self.planning_llm
        }


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
    
    def _parse_steps(self, body: str) -> List[WorkflowStep]:
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
            description = description.strip()
            
            steps.append(WorkflowStep(
                name=step_name,
                description=description,
                action=action,
                condition=condition,
                agent_config=agent_config,
                tools=tools,
                context_from=context_from,
                retain_full_context=retain_full_context,
                output_variable=output_variable,
                next_steps=next_steps,
                branch_condition=branch_condition,
                loop_over=loop_over,
                loop_var=loop_var
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
            planning = frontmatter.get("planning", False)
            planning_llm = frontmatter.get("planning_llm")
            memory_config = frontmatter.get("memory_config")
            default_agent_config = frontmatter.get("default_agent_config")
            
            steps = self._parse_steps(body)
            
            workflow = Workflow(
                name=name,
                description=description,
                steps=steps,
                variables=variables,
                file_path=str(file_path),
                default_llm=default_llm,
                planning=planning,
                planning_llm=planning_llm,
                memory_config=memory_config,
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
        """Substitute {{variable}} placeholders in text."""
        def replace(match):
            var_name = match.group(1).strip()
            return str(variables.get(var_name, match.group(0)))
        
        return re.sub(r'\{\{(\w+)\}\}', replace, text)
    
    def _build_step_context(
        self,
        step: WorkflowStep,
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
        step: WorkflowStep,
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
    
    def execute(
        self,
        workflow_name: str,
        executor: Optional[Callable[[str], str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        on_step: Optional[Callable[[WorkflowStep, int], None]] = None,
        on_result: Optional[Callable[[WorkflowStep, str], None]] = None,
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
                            verbose=verbose,
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
                verbose=verbose,
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
            
            # Handle early stop (like Agno's StepOutput.stop=True)
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
        step: WorkflowStep,
        step_idx: int,
        results: List[Dict[str, Any]],
        all_variables: Dict[str, Any],
        executor: Optional[Callable[[str], str]] = None,
        default_agent: Optional[Any] = None,
        default_llm: Optional[str] = None,
        memory: Optional[Any] = None,
        planning: bool = False,
        verbose: int = 0,
        on_step: Optional[Callable[[WorkflowStep, int], None]] = None,
        on_result: Optional[Callable[[WorkflowStep, str], None]] = None,
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
        on_step: Optional[Callable[[WorkflowStep, int], None]] = None,
        on_result: Optional[Callable[[WorkflowStep, str], None]] = None,
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
        step: WorkflowStep,
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
                config.setdefault("name", f"{step.name}Agent")
                config.setdefault("llm", default_llm)
                config.setdefault("verbose", verbose)
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
                
                workflow_steps.append(WorkflowStep(
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
