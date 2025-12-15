"""
Plan and PlanStep dataclasses for Planning Mode.

Provides structured representation of implementation plans
with support for:
- Step dependencies
- Status tracking
- Markdown serialization
- Progress calculation
"""

import uuid
import re
import yaml
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """
    A single step in an implementation plan.
    
    Attributes:
        id: Unique identifier for the step
        description: What this step does
        agent: Name of the agent to execute this step
        tools: List of tools needed for this step
        dependencies: List of step IDs that must complete first
        status: Current status (pending, in_progress, completed, skipped)
        estimated_tokens: Estimated token usage for this step
    """
    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    status: Literal["pending", "in_progress", "completed", "skipped"] = "pending"
    estimated_tokens: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert PlanStep to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "agent": self.agent,
            "tools": self.tools,
            "dependencies": self.dependencies,
            "status": self.status,
            "estimated_tokens": self.estimated_tokens
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanStep':
        """Create PlanStep from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            description=data.get("description", ""),
            agent=data.get("agent"),
            tools=data.get("tools", []),
            dependencies=data.get("dependencies", []),
            status=data.get("status", "pending"),
            estimated_tokens=data.get("estimated_tokens", 0)
        )
    
    def mark_complete(self) -> None:
        """Mark this step as completed."""
        self.status = "completed"
        
    def mark_in_progress(self) -> None:
        """Mark this step as in progress."""
        self.status = "in_progress"
        
    def mark_skipped(self) -> None:
        """Mark this step as skipped."""
        self.status = "skipped"
        
    def is_ready(self, completed_steps: List[str]) -> bool:
        """
        Check if this step is ready to execute.
        
        Args:
            completed_steps: List of completed step IDs
            
        Returns:
            True if all dependencies are satisfied
        """
        if self.status != "pending":
            return False
        return all(dep in completed_steps for dep in self.dependencies)


@dataclass
class Plan:
    """
    An implementation plan with multiple steps.
    
    Attributes:
        id: Unique identifier for the plan
        name: Human-readable name
        description: Detailed description of what the plan accomplishes
        steps: List of PlanStep objects
        status: Current status (draft, approved, executing, completed)
        created_at: When the plan was created
        approved_at: When the plan was approved (if applicable)
        file_path: Path where the plan is stored (if saved)
    """
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    status: Literal["draft", "approved", "executing", "completed", "cancelled"] = "draft"
    created_at: datetime = field(default_factory=datetime.now)
    approved_at: Optional[datetime] = None
    file_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Plan to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "file_path": self.file_path
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Plan':
        """Create Plan from dictionary."""
        steps = [
            PlanStep.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("steps", [])
        ]
        
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
            
        approved_at = data.get("approved_at")
        if isinstance(approved_at, str):
            approved_at = datetime.fromisoformat(approved_at)
            
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Untitled Plan"),
            description=data.get("description", ""),
            steps=steps,
            status=data.get("status", "draft"),
            created_at=created_at,
            approved_at=approved_at,
            file_path=data.get("file_path")
        )
    
    def to_markdown(self) -> str:
        """
        Convert Plan to markdown format.
        
        Returns:
            Markdown string representation of the plan
        """
        # YAML frontmatter
        frontmatter = {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None
        }
        
        lines = [
            "---",
            yaml.dump(frontmatter, default_flow_style=False).strip(),
            "---",
            "",
            f"# {self.name}",
            "",
        ]
        
        if self.description:
            lines.extend([self.description, ""])
            
        lines.extend(["## Steps", ""])
        
        status_icons = {
            "pending": "⬜",
            "in_progress": "🔄",
            "completed": "✅",
            "skipped": "⏭️"
        }
        
        for i, step in enumerate(self.steps, 1):
            icon = status_icons.get(step.status, "⬜")
            lines.append(f"{i}. {icon} {step.description}")
            
            if step.agent:
                lines.append(f"   - Agent: {step.agent}")
            if step.tools:
                lines.append(f"   - Tools: {', '.join(step.tools)}")
            if step.dependencies:
                lines.append(f"   - Depends on: {', '.join(step.dependencies)}")
            lines.append("")
            
        return "\n".join(lines)
    
    @classmethod
    def from_markdown(cls, markdown: str) -> 'Plan':
        """
        Create Plan from markdown format.
        
        Args:
            markdown: Markdown string with YAML frontmatter
            
        Returns:
            Plan instance
        """
        # Extract YAML frontmatter
        frontmatter_match = re.match(r'^---\n(.*?)\n---', markdown, re.DOTALL)
        
        data = {}
        if frontmatter_match:
            try:
                data = yaml.safe_load(frontmatter_match.group(1))
            except yaml.YAMLError:
                logger.warning("Failed to parse YAML frontmatter")
                
        # Extract steps from markdown
        steps = []
        # Pattern to capture status icon and description
        step_pattern = r'^\d+\.\s*([⬜🔄✅⏭️]?)\s*(.+?)$'
        
        # Map icons to status
        icon_to_status = {
            "⬜": "pending",
            "🔄": "in_progress",
            "✅": "completed",
            "⏭️": "skipped",
            "": "pending"
        }
        
        for match in re.finditer(step_pattern, markdown, re.MULTILINE):
            icon = match.group(1).strip()
            description = match.group(2).strip()
            status = icon_to_status.get(icon, "pending")
            steps.append(PlanStep(description=description, status=status))
            
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Untitled Plan"),
            description=data.get("description", ""),
            steps=steps,
            status=data.get("status", "draft")
        )
    
    def add_step(self, step: PlanStep) -> None:
        """Add a step to the plan."""
        self.steps.append(step)
        
    def remove_step(self, step_id: str) -> bool:
        """
        Remove a step from the plan.
        
        Args:
            step_id: ID of the step to remove
            
        Returns:
            True if step was removed, False if not found
        """
        for i, step in enumerate(self.steps):
            if step.id == step_id:
                self.steps.pop(i)
                return True
        return False
    
    def get_step(self, step_id: str) -> Optional[PlanStep]:
        """
        Get a step by ID.
        
        Args:
            step_id: ID of the step to find
            
        Returns:
            PlanStep if found, None otherwise
        """
        for step in self.steps:
            if step.id == step_id:
                return step
        return None
    
    def approve(self) -> None:
        """Approve the plan for execution."""
        self.status = "approved"
        self.approved_at = datetime.now()
        
    def start_execution(self) -> None:
        """Mark the plan as executing."""
        self.status = "executing"
        
    def complete(self) -> None:
        """Mark the plan as completed."""
        self.status = "completed"
        
    def cancel(self) -> None:
        """Cancel the plan."""
        self.status = "cancelled"
    
    @property
    def progress(self) -> float:
        """
        Calculate plan progress.
        
        Returns:
            Float between 0.0 and 1.0 representing completion percentage
        """
        if not self.steps:
            return 1.0
            
        completed = sum(1 for s in self.steps if s.status == "completed")
        return completed / len(self.steps)
    
    @property
    def is_complete(self) -> bool:
        """Check if all steps are completed."""
        return all(s.status == "completed" for s in self.steps)
    
    @property
    def completed_step_ids(self) -> List[str]:
        """Get list of completed step IDs."""
        return [s.id for s in self.steps if s.status == "completed"]
    
    def get_next_steps(self) -> List[PlanStep]:
        """
        Get steps that are ready to execute.
        
        Returns:
            List of steps with satisfied dependencies
        """
        completed = self.completed_step_ids
        return [s for s in self.steps if s.is_ready(completed)]
    
    def update_step_status(self, step_id: str, status: str) -> bool:
        """
        Update the status of a step.
        
        Args:
            step_id: ID of the step to update
            status: New status
            
        Returns:
            True if step was updated, False if not found
        """
        step = self.get_step(step_id)
        if step:
            step.status = status
            return True
        return False
