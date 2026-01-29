"""
Subagent Tool for PraisonAI Agents.

Provides a tool for spawning subagents to handle specific tasks,
enabling hierarchical task delegation and multi-agent coordination.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def create_subagent_tool(
    agent_factory: Optional[Callable[..., Any]] = None,
    allowed_agents: Optional[List[str]] = None,
    max_depth: int = 3,
    default_llm: Optional[str] = None,
    default_permission_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a subagent tool for task delegation.
    
    This tool allows an agent to spawn a subagent to handle
    a specific task, enabling hierarchical task execution.
    
    Args:
        agent_factory: Optional factory function to create agents
        allowed_agents: Optional list of allowed agent names
        max_depth: Maximum nesting depth for subagents
        default_llm: Default LLM model for subagents (Claude Code parity)
        default_permission_mode: Default permission mode for subagents (Claude Code parity)
        
    Returns:
        Tool definition dictionary
    """
    
    _current_depth = 0
    
    def spawn_subagent(
        task: str,
        agent_name: Optional[str] = None,
        context: Optional[str] = None,
        tools: Optional[List[str]] = None,
        llm: Optional[str] = None,
        permission_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Spawn a subagent to handle a specific task.
        
        Args:
            task: The task description for the subagent
            agent_name: Optional specific agent to use
            context: Optional additional context
            tools: Optional list of tools to give the subagent
            llm: Optional LLM model override (Claude Code parity)
            permission_mode: Optional permission mode (Claude Code parity)
            
        Returns:
            Result from the subagent execution
        """
        nonlocal _current_depth
        
        # Check depth limit
        if _current_depth >= max_depth:
            return {
                "success": False,
                "error": f"Maximum subagent depth ({max_depth}) exceeded",
                "output": None,
            }
        
        # Check allowed agents
        if allowed_agents and agent_name and agent_name not in allowed_agents:
            return {
                "success": False,
                "error": f"Agent '{agent_name}' not in allowed list",
                "output": None,
            }
        
        try:
            _current_depth += 1
            
            # Resolve LLM (parameter > default > None)
            effective_llm = llm or default_llm
            # Resolve permission mode (parameter > default > None)
            effective_permission_mode = permission_mode or default_permission_mode
            
            # If we have an agent factory, use it
            if agent_factory:
                subagent = agent_factory(
                    name=agent_name or "subagent",
                    tools=tools,
                    llm=effective_llm,
                )
                
                # Build prompt with context
                prompt = task
                if context:
                    prompt = f"Context: {context}\n\nTask: {task}"
                
                # Execute the subagent
                result = subagent.chat(prompt)
                
                return {
                    "success": True,
                    "output": result,
                    "agent_name": agent_name or "subagent",
                    "task": task,
                    "llm": effective_llm,
                    "permission_mode": effective_permission_mode,
                }
            else:
                # Without factory, return a placeholder
                return {
                    "success": True,
                    "output": f"[Subagent would execute: {task}]",
                    "agent_name": agent_name or "subagent",
                    "task": task,
                    "llm": effective_llm,
                    "permission_mode": effective_permission_mode,
                    "note": "No agent factory provided - simulation mode",
                }
                
        except Exception as e:
            logger.error(f"Subagent execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "output": None,
            }
        finally:
            _current_depth -= 1
    
    return {
        "name": "spawn_subagent",
        "description": (
            "Spawn a subagent to handle a specific task. Use this when a task "
            "is complex and would benefit from dedicated focus, or when you need "
            "specialized capabilities. The subagent will execute the task and "
            "return the result."
        ),
        "function": spawn_subagent,
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task description for the subagent to execute",
                },
                "agent_name": {
                    "type": "string",
                    "description": "Optional name of a specific agent type to use",
                },
                "context": {
                    "type": "string",
                    "description": "Optional additional context for the task",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tool names to give the subagent",
                },
                "llm": {
                    "type": "string",
                    "description": "Optional LLM model to use for the subagent (e.g., 'gpt-4o-mini', 'claude-3-sonnet')",
                },
                "permission_mode": {
                    "type": "string",
                    "enum": ["default", "accept_edits", "dont_ask", "bypass_permissions", "plan"],
                    "description": "Optional permission mode for the subagent (default, accept_edits, dont_ask, bypass_permissions, plan)",
                },
            },
            "required": ["task"],
        },
    }


def create_batch_tool() -> Dict[str, Any]:
    """
    Create a batch tool for executing multiple operations.
    
    This tool allows executing multiple similar operations
    in a single call, reducing overhead.
    
    Returns:
        Tool definition dictionary
    """
    
    def batch_execute(
        operations: List[Dict[str, Any]],
        parallel: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute multiple operations in batch.
        
        Args:
            operations: List of operations to execute
            parallel: Whether to execute in parallel (not implemented)
            
        Returns:
            Results from all operations
        """
        results = []
        errors = []
        
        for i, op in enumerate(operations):
            try:
                op_type = op.get("type", "unknown")
                op_args = op.get("args", {})
                
                # Placeholder for actual operation execution
                results.append({
                    "index": i,
                    "type": op_type,
                    "success": True,
                    "result": f"[Would execute {op_type} with {op_args}]",
                })
            except Exception as e:
                errors.append({
                    "index": i,
                    "error": str(e),
                })
        
        return {
            "total": len(operations),
            "successful": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }
    
    return {
        "name": "batch_execute",
        "description": (
            "Execute multiple operations in a single batch. Use this when you "
            "need to perform many similar operations to reduce overhead. "
            "Each operation should specify a type and arguments."
        ),
        "function": batch_execute,
        "parameters": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "args": {"type": "object"},
                        },
                        "required": ["type"],
                    },
                    "description": "List of operations to execute",
                },
                "parallel": {
                    "type": "boolean",
                    "description": "Whether to execute operations in parallel",
                    "default": False,
                },
            },
            "required": ["operations"],
        },
    }


def create_todo_tools() -> List[Dict[str, Any]]:
    """
    Create todo management tools.
    
    Returns:
        List of todo tool definitions
    """
    
    _todos: Dict[str, Dict[str, Any]] = {}
    _counter = 0
    
    def add_todo(
        content: str,
        priority: str = "medium",
        status: str = "pending",
    ) -> Dict[str, Any]:
        """Add a new todo item."""
        nonlocal _counter
        _counter += 1
        todo_id = f"todo_{_counter}"
        
        _todos[todo_id] = {
            "id": todo_id,
            "content": content,
            "priority": priority,
            "status": status,
        }
        
        return {"success": True, "id": todo_id, "todo": _todos[todo_id]}
    
    def update_todo(
        todo_id: str,
        content: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing todo item."""
        if todo_id not in _todos:
            return {"success": False, "error": f"Todo {todo_id} not found"}
        
        todo = _todos[todo_id]
        if content is not None:
            todo["content"] = content
        if priority is not None:
            todo["priority"] = priority
        if status is not None:
            todo["status"] = status
        
        return {"success": True, "todo": todo}
    
    def list_todos(
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List todo items with optional filtering."""
        todos = list(_todos.values())
        
        if status:
            todos = [t for t in todos if t["status"] == status]
        if priority:
            todos = [t for t in todos if t["priority"] == priority]
        
        return {"success": True, "todos": todos, "count": len(todos)}
    
    def delete_todo(todo_id: str) -> Dict[str, Any]:
        """Delete a todo item."""
        if todo_id not in _todos:
            return {"success": False, "error": f"Todo {todo_id} not found"}
        
        del _todos[todo_id]
        return {"success": True, "deleted": todo_id}
    
    return [
        {
            "name": "add_todo",
            "description": "Add a new todo item to track tasks",
            "function": add_todo,
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Todo content"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Priority level",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                        "description": "Current status",
                    },
                },
                "required": ["content"],
            },
        },
        {
            "name": "update_todo",
            "description": "Update an existing todo item",
            "function": update_todo,
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "Todo ID"},
                    "content": {"type": "string", "description": "New content"},
                    "priority": {"type": "string", "description": "New priority"},
                    "status": {"type": "string", "description": "New status"},
                },
                "required": ["todo_id"],
            },
        },
        {
            "name": "list_todos",
            "description": "List todo items with optional filtering",
            "function": list_todos,
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status"},
                    "priority": {"type": "string", "description": "Filter by priority"},
                },
            },
        },
        {
            "name": "delete_todo",
            "description": "Delete a todo item",
            "function": delete_todo,
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "Todo ID to delete"},
                },
                "required": ["todo_id"],
            },
        },
    ]
