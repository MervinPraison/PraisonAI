"""
Subagent Tool for PraisonAI Agents.

Provides a tool for spawning subagents to handle specific tasks,
enabling hierarchical task delegation and multi-agent coordination.
"""

import logging
import threading
from praisonaiagents._logging import get_logger
from typing import Any, Callable, Dict, List, Optional

logger = get_logger(__name__)

def create_subagent_tool(
    agent_factory: Optional[Callable[..., Any]] = None,
    allowed_agents: Optional[List[str]] = None,
    max_depth: int = 3,
    default_llm: Optional[str] = None,
    default_permission_mode: Optional[str] = None,
    on_job_complete: Optional[Callable[[Any], None]] = None,
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
        on_job_complete: Optional callback invoked with the terminal
            ``JobInfo`` when a ``background=True`` subagent that carries a
            ``deliver`` target finishes. This is the observable completion
            signal a gateway (e.g. ``BotOS``) subscribes to in order to
            route the result back to the originating chat without an active
            turn. When ``None`` (the default) background jobs remain strictly
            pull-only via ``subagent_result`` — byte-for-byte the prior
            behaviour.
        
    Returns:
        Tool definition dictionary
    """
    
    # Depth is tracked per-thread so that concurrent background subagents do
    # not interfere with each other's depth budget. The parent depth is
    # captured at call time and passed into ``_run_subagent`` so a background
    # worker (running on a different thread) starts from the correct depth.
    _depth_state = threading.local()

    def _get_depth() -> int:
        return getattr(_depth_state, "current_depth", 0)

    def _run_subagent(
        task: str,
        agent_name: Optional[str],
        context: Optional[str],
        tools: Optional[List[str]],
        effective_llm: Optional[str],
        effective_permission_mode: Optional[str],
        parent_depth: int = 0,
    ) -> Dict[str, Any]:
        """Execute the subagent synchronously and return the result dict.

        Depth tracking is handled here so that background jobs honour the
        same ``max_depth`` scoping as synchronous calls. ``parent_depth`` is
        the depth captured by the caller; it is restored on this thread for
        the duration of the execution so nested subagents see the correct
        value even when running off the main thread.
        """
        previous_depth = _get_depth()
        try:
            _depth_state.current_depth = parent_depth + 1

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
            _depth_state.current_depth = previous_depth

    def spawn_subagent(
        task: str,
        agent_name: Optional[str] = None,
        context: Optional[str] = None,
        tools: Optional[List[str]] = None,
        llm: Optional[str] = None,
        permission_mode: Optional[str] = None,
        background: bool = False,
        deliver: str = "",
        platform: str = "",
        chat_id: str = "",
        thread_id: str = "",
        session_id: str = "",
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
            background: When True, run the subagent on the background job
                runner and return immediately with a ``job_id`` instead of
                blocking until completion. Defaults to False (synchronous).
            deliver: Optional delivery token mirroring ``schedule_add`` —
                e.g. ``"origin"``, ``"all"`` or ``"platform:chat_id[:thread_id]"``.
                Only meaningful with ``background=True``: it captures where the
                result should be routed when the job finishes, so a gateway can
                proactively deliver it back to chat with no active turn. Empty
                (the default) keeps background jobs pull-only via
                ``subagent_result`` — byte-for-byte the prior behaviour.
            platform: Origin platform (e.g. "telegram") captured for
                ``deliver="origin"``. Usually supplied by the gateway context.
            chat_id: Origin chat/channel id captured for ``deliver="origin"``.
            thread_id: Optional origin thread id.
            session_id: Optional origin session id to preserve context.
            
        Returns:
            Result from the subagent execution. When ``background=True`` a
            ``{"success": True, "job_id": ..., "status": "running"}`` handle
            is returned instead; use ``subagent_result(job_id)`` to collect.
            When ``deliver`` is set the handle also echoes ``"deliver"``.
        """
        # Check depth limit (per-thread; captured for background workers below)
        parent_depth = _get_depth()
        if parent_depth >= max_depth:
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

        # Resolve LLM (parameter > default > None)
        effective_llm = llm or default_llm
        # Resolve permission mode (parameter > default > None)
        effective_permission_mode = permission_mode or default_permission_mode

        if background:
            # Enqueue on the existing background job runner. Depth and
            # permission/tool scoping are captured in the closure below so
            # the backgrounded subagent runs under exactly the same
            # constraints as a synchronous one.
            from praisonaiagents.background.job_manager import get_job_manager

            job_manager = get_job_manager()

            def _job() -> Dict[str, Any]:
                return _run_subagent(
                    task=task,
                    agent_name=agent_name,
                    context=context,
                    tools=tools,
                    effective_llm=effective_llm,
                    effective_permission_mode=effective_permission_mode,
                    parent_depth=parent_depth,
                )

            # Capture origin/delivery context so a gateway can route the
            # result back to the originating conversation when the job
            # finishes. Only populated when a ``deliver`` target is set;
            # otherwise the job stays pull-only (unchanged behaviour).
            origin: Dict[str, Any] = {}
            job_on_complete = None
            if deliver:
                origin = {
                    "deliver": deliver,
                    "platform": platform,
                    "chat_id": chat_id,
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "task": task,
                }
                if on_job_complete is not None:
                    job_on_complete = on_job_complete

            job_id = job_manager.start_job(
                _job,
                on_complete=job_on_complete,
                origin=origin,
            )
            handle = {
                "success": True,
                "job_id": job_id,
                "status": "running",
                "agent_name": agent_name or "subagent",
                "task": task,
                "llm": effective_llm,
                "permission_mode": effective_permission_mode,
            }
            if deliver:
                handle["deliver"] = deliver
            return handle

        return _run_subagent(
            task=task,
            agent_name=agent_name,
            context=context,
            tools=tools,
            effective_llm=effective_llm,
            effective_permission_mode=effective_permission_mode,
            parent_depth=parent_depth,
        )

    def subagent_result(job_id: str, wait: bool = False) -> Dict[str, Any]:
        """
        Fetch the status/result of a backgrounded subagent.

        Args:
            job_id: The job ID returned by ``spawn_subagent(background=True)``.
            wait: When True, block until the job completes before returning.

        Returns:
            A dict describing the job. While running:
            ``{"success": True, "job_id": ..., "status": "running"}``.
            On completion the subagent's result dict is returned under
            ``"result"`` along with ``"status": "completed"``.
        """
        from praisonaiagents.background.job_manager import (
            get_job_manager,
            JobStatus,
        )

        job_manager = get_job_manager()
        try:
            if wait:
                try:
                    result = job_manager.get_result(job_id)
                except KeyError:
                    return {
                        "success": False,
                        "job_id": job_id,
                        "error": f"Job '{job_id}' not found",
                    }
                except Exception as e:
                    # The worker failed or was cancelled. Surface the same
                    # clean failure shape the non-blocking path returns
                    # instead of re-raising to the caller.
                    return {
                        "success": False,
                        "job_id": job_id,
                        "status": JobStatus.FAILED.value,
                        "error": str(e),
                    }
                return {
                    "success": True,
                    "job_id": job_id,
                    "status": JobStatus.COMPLETED.value,
                    "result": result,
                }

            info = job_manager.get_job_info(job_id)
        except KeyError:
            return {
                "success": False,
                "job_id": job_id,
                "error": f"Job '{job_id}' not found",
            }

        if info.status == JobStatus.COMPLETED:
            return {
                "success": True,
                "job_id": job_id,
                "status": info.status.value,
                "result": info.result,
            }
        if info.status == JobStatus.FAILED:
            return {
                "success": False,
                "job_id": job_id,
                "status": info.status.value,
                "error": info.error,
            }
        return {
            "success": True,
            "job_id": job_id,
            "status": info.status.value,
        }

    spawn_subagent._subagent_result = subagent_result  # type: ignore[attr-defined]

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
                "background": {
                    "type": "boolean",
                    "description": "When true, run the subagent in the background (fire-and-forget) and return a job_id immediately instead of blocking. Use subagent_result to collect the result.",
                    "default": False,
                },
                "deliver": {
                    "type": "string",
                    "description": "Optional delivery target for a background job's result when it finishes (e.g. 'origin', 'all', 'telegram:12345'). When set, the completed result is proactively delivered back to that chat with no active turn required. Empty means pull-only via subagent_result.",
                },
            },
            "required": ["task"],
        },
        "result_tool": {
            "name": "subagent_result",
            "description": (
                "Fetch the status or result of a backgrounded subagent "
                "launched via spawn_subagent(background=true). Pass the "
                "job_id returned by spawn_subagent. Set wait=true to block "
                "until the subagent completes."
            ),
            "function": subagent_result,
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job ID returned by spawn_subagent(background=true)",
                    },
                    "wait": {
                        "type": "boolean",
                        "description": "When true, block until the subagent completes before returning",
                        "default": False,
                    },
                },
                "required": ["job_id"],
            },
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
