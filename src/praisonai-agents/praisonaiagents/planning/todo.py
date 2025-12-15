"""
TodoList and TodoItem classes for Planning Mode.

Provides task tracking functionality similar to:
- Cursor Agent To-Dos
- Windsurf Todo Lists
- Claude Code TodoRead/TodoWrite

Features:
- Create todo lists from plans
- Track item completion
- Dependencies between items
- Markdown and JSON serialization
"""

import uuid
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .plan import Plan

logger = logging.getLogger(__name__)


@dataclass
class TodoItem:
    """
    A single todo item.
    
    Attributes:
        id: Unique identifier
        description: What needs to be done
        status: Current status (pending, in_progress, completed)
        dependencies: List of item IDs that must complete first
        agent: Name of the agent responsible
        priority: Priority level (low, medium, high)
        notes: Additional notes
    """
    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: Literal["pending", "in_progress", "completed"] = "pending"
    dependencies: List[str] = field(default_factory=list)
    agent: Optional[str] = None
    priority: Literal["low", "medium", "high"] = "medium"
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TodoItem to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "dependencies": self.dependencies,
            "agent": self.agent,
            "priority": self.priority,
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TodoItem':
        """Create TodoItem from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            dependencies=data.get("dependencies", []),
            agent=data.get("agent"),
            priority=data.get("priority", "medium"),
            notes=data.get("notes", "")
        )
    
    def complete(self) -> None:
        """Mark this item as completed."""
        self.status = "completed"
        
    def start(self) -> None:
        """Mark this item as in progress."""
        self.status = "in_progress"
        
    def reset(self) -> None:
        """Reset this item to pending."""
        self.status = "pending"
        
    def is_ready(self, completed_ids: List[str]) -> bool:
        """
        Check if this item is ready to start.
        
        Args:
            completed_ids: List of completed item IDs
            
        Returns:
            True if all dependencies are satisfied
        """
        if self.status != "pending":
            return False
        return all(dep in completed_ids for dep in self.dependencies)


@dataclass
class TodoList:
    """
    A list of todo items with tracking capabilities.
    
    Attributes:
        items: List of TodoItem objects
        auto_update: Whether to auto-update from plan changes
        name: Optional name for the todo list
    """
    items: List[TodoItem] = field(default_factory=list)
    auto_update: bool = True
    name: str = "Todo List"
    
    def add(self, item: Union[TodoItem, str]) -> TodoItem:
        """
        Add an item to the list.
        
        Args:
            item: TodoItem or description string
            
        Returns:
            The added TodoItem
        """
        if isinstance(item, str):
            item = TodoItem(description=item)
        self.items.append(item)
        return item
    
    def remove(self, item_id: str) -> bool:
        """
        Remove an item from the list.
        
        Args:
            item_id: ID of the item to remove
            
        Returns:
            True if item was removed, False if not found
        """
        for i, item in enumerate(self.items):
            if item.id == item_id:
                self.items.pop(i)
                return True
        return False
    
    def get(self, item_id: str) -> Optional[TodoItem]:
        """
        Get an item by ID.
        
        Args:
            item_id: ID of the item to find
            
        Returns:
            TodoItem if found, None otherwise
        """
        for item in self.items:
            if item.id == item_id:
                return item
        return None
    
    def complete(self, item_id: str) -> bool:
        """
        Mark an item as completed.
        
        Args:
            item_id: ID of the item to complete
            
        Returns:
            True if item was completed, False if not found
        """
        item = self.get(item_id)
        if item:
            item.complete()
            return True
        return False
    
    def start(self, item_id: str) -> bool:
        """
        Mark an item as in progress.
        
        Args:
            item_id: ID of the item to start
            
        Returns:
            True if item was started, False if not found
        """
        item = self.get(item_id)
        if item:
            item.start()
            return True
        return False
    
    @property
    def pending(self) -> List[TodoItem]:
        """Get all pending items."""
        return [item for item in self.items if item.status == "pending"]
    
    @property
    def in_progress(self) -> List[TodoItem]:
        """Get all in-progress items."""
        return [item for item in self.items if item.status == "in_progress"]
    
    @property
    def completed(self) -> List[TodoItem]:
        """Get all completed items."""
        return [item for item in self.items if item.status == "completed"]
    
    @property
    def progress(self) -> float:
        """
        Calculate completion progress.
        
        Returns:
            Float between 0.0 and 1.0
        """
        if not self.items:
            return 1.0
        return len(self.completed) / len(self.items)
    
    @property
    def is_complete(self) -> bool:
        """Check if all items are completed."""
        return all(item.status == "completed" for item in self.items)
    
    @property
    def completed_ids(self) -> List[str]:
        """Get list of completed item IDs."""
        return [item.id for item in self.completed]
    
    def get_ready_items(self) -> List[TodoItem]:
        """
        Get items that are ready to start.
        
        Returns:
            List of items with satisfied dependencies
        """
        completed = self.completed_ids
        return [item for item in self.items if item.is_ready(completed)]
    
    def to_markdown(self) -> str:
        """
        Convert TodoList to markdown format.
        
        Returns:
            Markdown string with checkbox format
        """
        lines = [f"# {self.name}", ""]
        
        for item in self.items:
            checkbox = "[x]" if item.status == "completed" else "[ ]"
            lines.append(f"- {checkbox} {item.description}")
            
            if item.agent:
                lines.append(f"  - Agent: {item.agent}")
            if item.dependencies:
                lines.append(f"  - Depends on: {', '.join(item.dependencies)}")
            if item.notes:
                lines.append(f"  - Notes: {item.notes}")
                
        return "\n".join(lines)
    
    @classmethod
    def from_markdown(cls, markdown: str) -> 'TodoList':
        """
        Create TodoList from markdown format.
        
        Args:
            markdown: Markdown string with checkbox format
            
        Returns:
            TodoList instance
        """
        import re
        
        items = []
        # Match checkbox items: - [ ] or - [x]
        pattern = r'^-\s*\[([ x])\]\s*(.+?)$'
        
        for match in re.finditer(pattern, markdown, re.MULTILINE):
            checked = match.group(1) == 'x'
            description = match.group(2).strip()
            
            item = TodoItem(
                description=description,
                status="completed" if checked else "pending"
            )
            items.append(item)
            
        return cls(items=items)
    
    def to_json(self) -> str:
        """
        Serialize TodoList to JSON.
        
        Returns:
            JSON string
        """
        data = {
            "name": self.name,
            "auto_update": self.auto_update,
            "items": [item.to_dict() for item in self.items]
        }
        return json.dumps(data, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TodoList':
        """
        Create TodoList from JSON.
        
        Args:
            json_str: JSON string
            
        Returns:
            TodoList instance
        """
        data = json.loads(json_str)
        items = [TodoItem.from_dict(item) for item in data.get("items", [])]
        
        return cls(
            items=items,
            auto_update=data.get("auto_update", True),
            name=data.get("name", "Todo List")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TodoList to dictionary."""
        return {
            "name": self.name,
            "auto_update": self.auto_update,
            "items": [item.to_dict() for item in self.items]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TodoList':
        """Create TodoList from dictionary."""
        items = [TodoItem.from_dict(item) for item in data.get("items", [])]
        return cls(
            items=items,
            auto_update=data.get("auto_update", True),
            name=data.get("name", "Todo List")
        )
    
    @classmethod
    def from_plan(cls, plan: 'Plan') -> 'TodoList':
        """
        Create TodoList from a Plan.
        
        Args:
            plan: Plan instance
            
        Returns:
            TodoList with items matching plan steps
        """
        items = []
        for step in plan.steps:
            item = TodoItem(
                id=step.id,
                description=step.description,
                status=step.status if step.status in ["pending", "in_progress", "completed"] else "pending",
                dependencies=step.dependencies,
                agent=step.agent
            )
            items.append(item)
            
        return cls(
            items=items,
            name=f"Todo: {plan.name}"
        )
    
    def sync_with_plan(self, plan: 'Plan') -> None:
        """
        Synchronize TodoList with a Plan.
        
        Updates item statuses to match plan step statuses.
        
        Args:
            plan: Plan to sync with
        """
        step_statuses = {step.id: step.status for step in plan.steps}
        
        for item in self.items:
            if item.id in step_statuses:
                status = step_statuses[item.id]
                if status in ["pending", "in_progress", "completed"]:
                    item.status = status
                    
    def update_from_plan(self, plan: 'Plan') -> None:
        """
        Update TodoList to match Plan structure.
        
        Adds new items for new steps, removes items for removed steps.
        
        Args:
            plan: Plan to update from
        """
        # Get current step IDs
        step_ids = {step.id for step in plan.steps}
        item_ids = {item.id for item in self.items}
        
        # Remove items for deleted steps
        self.items = [item for item in self.items if item.id in step_ids]
        
        # Add items for new steps
        for step in plan.steps:
            if step.id not in item_ids:
                self.add(TodoItem(
                    id=step.id,
                    description=step.description,
                    dependencies=step.dependencies,
                    agent=step.agent
                ))
                
        # Sync statuses
        self.sync_with_plan(plan)
