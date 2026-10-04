"""Todo/planning tools for agent task management.

This module provides simple todo list functionality that agents can use
for planning and task tracking.
"""

import json
import os
import logging
from typing import Dict, List, Optional
from ..approval import require_approval
from ..utils.atomic_io import update_json

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
        """Load todos from file (read-only helper used by ``todo_list``)."""
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
        """Atomically persist a full todo list.

        Retained for the MCP CLI adapter
        (``praisonai_mcp.mcp_server.adapters.cli_tools``), which does its own
        read-modify-write via ``_load_todos`` + ``_save_todos`` and writes the
        owner's record shape. The write goes through ``atomic_write_json`` so a
        crash mid-write never truncates the previous good file. In-process
        mutations (``todo_add``/``todo_update``) use the locked ``_update_todos``
        below instead; this plain save keeps the cross-adapter contract intact.
        """
        from ..utils.atomic_io import atomic_write_json
        atomic_write_json(
            self._get_todo_file(), todos, indent=2, ensure_ascii=False
        )

    def _update_todos(self, mutate) -> List[Dict]:
        """Locked atomic read-modify-write over the todo file.

        Parallel tool calls and multiple agents sharing the default
        ``~/.praisonai/todos.json`` previously raced through an unlocked
        read-modify-write plus a truncating ``open(..., 'w')``, so most
        concurrent adds were lost and a torn write reset the whole plan. Routing
        every mutation through ``update_json`` serialises them and writes
        atomically; a corrupt file is moved aside instead of silently emptied.
        """
        return update_json(
            self._get_todo_file(),
            lambda todos: (mutate(todos), todos)[1],
            default=list,
            indent=2,
            ensure_ascii=False,
        )

    def _emit_update(self, todos: List[Dict]) -> None:
        """Publish the full ordered list so subscribed frontends can render live.

        Uses the streaming progress channel that the agent already activates
        around each tool call; a cheap no-op when nothing is listening.
        """
        try:
            from ..streaming.events import emit_todo_update
            emit_todo_update(todos)
        except Exception as e:  # never let rendering break a mutation
            logger.debug(f"todo update emit failed: {e}")
    
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
            new_todo: Dict = {}

            def mutate(todos: List[Dict]) -> None:
                new_todo.update({
                    # Derive the id from the current max inside the lock so
                    # concurrent adds never collide on ``len(todos) + 1``.
                    "id": max((t.get("id", 0) for t in todos), default=0) + 1,
                    "task": task,
                    "priority": priority,
                    "category": category,
                    "status": "pending",
                    "created_at": self._get_timestamp(),
                })
                todos.append(dict(new_todo))

            todos = self._update_todos(mutate)
            self._emit_update(todos)
            
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
            status: Filter by status (all, pending, in_progress, completed, cancelled)
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
            status: New status (pending, in_progress, completed, cancelled).
                Setting a todo to in_progress demotes any other in_progress
                item to pending so exactly one item is in_progress at a time.
            task: New task description
            priority: New priority level
            
        Returns:
            JSON string with result
        """
        try:
            found = {"value": False}

            def mutate(todos: List[Dict]) -> None:
                for todo in todos:
                    if todo.get("id") == todo_id:
                        if status:
                            # Convention: exactly one item is in_progress at a time.
                            if status == "in_progress":
                                for other in todos:
                                    if other is not todo and other.get("status") == "in_progress":
                                        other["status"] = "pending"
                            todo["status"] = status
                        if task:
                            todo["task"] = task
                        if priority:
                            todo["priority"] = priority
                        todo["updated_at"] = self._get_timestamp()
                        found["value"] = True
                        break

            todos = self._update_todos(mutate)

            if not found["value"]:
                return json.dumps({"success": False, "error": f"Todo {todo_id} not found"})
            
            self._emit_update(todos)
            
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
        status: Filter by status (all, pending, in_progress, completed, cancelled)
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
        status: New status (pending, in_progress, completed, cancelled)
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