"""Todo/planning tools for agent task management.

This module provides simple todo list functionality that agents can use
for planning and task tracking.
"""

import json
import os
import logging
from typing import Dict, List, Optional
from ..approval import require_approval

logger = logging.getLogger(__name__)


class TodoTools:
    """Tools for managing todo lists and planning."""
    
    def __init__(self, workspace=None):
        """Initialize TodoTools with optional workspace containment.
        
        Args:
            workspace: Optional Workspace instance for path containment
        """
        self._workspace = workspace
        self._todo_file = None
    
    def _get_todo_file(self) -> str:
        """Get the path to the todo file."""
        if self._todo_file:
            return self._todo_file
        
        if self._workspace:
            self._todo_file = str(self._workspace.root / "todos.json")
        else:
            self._todo_file = os.path.expanduser("~/.praisonai/todos.json")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self._todo_file), exist_ok=True)
        return self._todo_file
    
    def _load_todos(self) -> List[Dict]:
        """Load todos from file."""
        todo_file = self._get_todo_file()
        if not os.path.exists(todo_file):
            return []
        
        try:
            with open(todo_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load todos: {e}")
            return []
    
    def _save_todos(self, todos: List[Dict]) -> None:
        """Save todos to file."""
        todo_file = self._get_todo_file()
        try:
            with open(todo_file, 'w', encoding='utf-8') as f:
                json.dump(todos, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to save todos: {e}")
            raise
    
    @require_approval(risk_level="low")
    def todo_add(self, task: str, priority: str = "medium", 
                 category: str = "general") -> str:
        """Add a new todo item.
        
        Args:
            task: Task description
            priority: Priority level (low, medium, high)
            category: Task category
            
        Returns:
            JSON string with result
        """
        try:
            todos = self._load_todos()
            
            new_todo = {
                "id": len(todos) + 1,
                "task": task,
                "priority": priority,
                "category": category,
                "status": "pending",
                "created_at": self._get_timestamp()
            }
            
            todos.append(new_todo)
            self._save_todos(todos)
            
            return json.dumps({
                "success": True,
                "todo": new_todo,
                "total_todos": len(todos)
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
    
    def todo_list(self, status: str = "all", category: str = None) -> str:
        """List todo items with optional filtering.
        
        Args:
            status: Filter by status (all, pending, completed, cancelled)
            category: Filter by category
            
        Returns:
            JSON string with todo list
        """
        try:
            todos = self._load_todos()
            
            filtered_todos = todos
            if status != "all":
                filtered_todos = [t for t in filtered_todos if t.get("status") == status]
            if category:
                filtered_todos = [t for t in filtered_todos if t.get("category") == category]
            
            return json.dumps({
                "todos": filtered_todos,
                "total": len(filtered_todos),
                "filter": {"status": status, "category": category}
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @require_approval(risk_level="low")
    def todo_update(self, todo_id: int, status: str = None, 
                   task: str = None, priority: str = None) -> str:
        """Update an existing todo item.
        
        Args:
            todo_id: ID of the todo to update
            status: New status (pending, completed, cancelled)
            task: New task description
            priority: New priority level
            
        Returns:
            JSON string with result
        """
        try:
            todos = self._load_todos()
            
            todo_found = False
            for todo in todos:
                if todo.get("id") == todo_id:
                    if status:
                        todo["status"] = status
                    if task:
                        todo["task"] = task
                    if priority:
                        todo["priority"] = priority
                    todo["updated_at"] = self._get_timestamp()
                    todo_found = True
                    break
            
            if not todo_found:
                return json.dumps({"success": False, "error": f"Todo {todo_id} not found"})
            
            self._save_todos(todos)
            
            return json.dumps({
                "success": True,
                "todo_id": todo_id,
                "updated_fields": {
                    k: v for k, v in {
                        "status": status,
                        "task": task,
                        "priority": priority
                    }.items() if v is not None
                }
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


# Create default instance for direct function access
_todo_tools = TodoTools()

@require_approval(risk_level="low")
def todo_add(task: str, priority: str = "medium", category: str = "general") -> str:
    """Add a new todo item.
    
    Args:
        task: Task description
        priority: Priority level (low, medium, high)
        category: Task category
        
    Returns:
        JSON string with result
    """
    return _todo_tools.todo_add(task, priority, category)


def todo_list(status: str = "all", category: str = None) -> str:
    """List todo items with optional filtering.
    
    Args:
        status: Filter by status (all, pending, completed, cancelled)
        category: Filter by category
        
    Returns:
        JSON string with todo list
    """
    return _todo_tools.todo_list(status, category)


@require_approval(risk_level="low")
def todo_update(todo_id: int, status: str = None, 
               task: str = None, priority: str = None) -> str:
    """Update an existing todo item.
    
    Args:
        todo_id: ID of the todo to update
        status: New status (pending, completed, cancelled)
        task: New task description
        priority: New priority level
        
    Returns:
        JSON string with result
    """
    return _todo_tools.todo_update(todo_id, status, task, priority)


def create_todo_tools(workspace=None) -> TodoTools:
    """Create TodoTools instance with optional workspace containment.
    
    Args:
        workspace: Optional Workspace instance for path containment
        
    Returns:
        TodoTools instance configured with workspace
    """
    return TodoTools(workspace=workspace)