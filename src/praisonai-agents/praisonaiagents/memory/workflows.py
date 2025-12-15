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
class WorkflowStep:
    """A single step in a workflow."""
    name: str
    description: str = ""
    action: str = ""  # The action/prompt to execute
    condition: Optional[str] = None  # Optional condition for execution
    on_error: Literal["stop", "continue", "retry"] = "stop"
    max_retries: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "condition": self.condition,
            "on_error": self.on_error,
            "max_retries": self.max_retries
        }


@dataclass
class Workflow:
    """A complete workflow with multiple steps."""
    name: str
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "variables": self.variables,
            "file_path": self.file_path
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
            
            # Get description (text before action block)
            description = step_content
            if action_match:
                description = step_content[:action_match.start()].strip()
            
            # Clean up description (remove code blocks)
            description = re.sub(r'```.*?```', '', description, flags=re.DOTALL).strip()
            
            steps.append(WorkflowStep(
                name=step_name,
                description=description,
                action=action,
                condition=condition
            ))
        
        return steps
    
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
            
            steps = self._parse_steps(body)
            
            workflow = Workflow(
                name=name,
                description=description,
                steps=steps,
                variables=variables,
                file_path=str(file_path)
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
    
    def execute(
        self,
        workflow_name: str,
        executor: Callable[[str], str],
        variables: Optional[Dict[str, Any]] = None,
        on_step: Optional[Callable[[WorkflowStep, int], None]] = None,
        on_result: Optional[Callable[[WorkflowStep, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow.
        
        Args:
            workflow_name: Name of the workflow to execute
            executor: Function to execute each step (e.g., agent.chat)
            variables: Variables to substitute in steps
            on_step: Callback before each step (step, index)
            on_result: Callback after each step (step, result)
            
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
        
        results = []
        success = True
        
        for i, step in enumerate(workflow.steps):
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
                    continue
            
            # Callback before step
            if on_step:
                on_step(step, i)
            
            # Substitute variables in action
            action = self._substitute_variables(step.action, all_variables)
            
            # Execute step
            retries = 0
            step_success = False
            output = None
            error = None
            
            while retries <= step.max_retries and not step_success:
                try:
                    output = executor(action)
                    step_success = True
                except Exception as e:
                    error = str(e)
                    retries += 1
                    if retries <= step.max_retries:
                        self._log(f"Step '{step.name}' failed, retrying ({retries}/{step.max_retries})")
            
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
            "results": results
        }
    
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
