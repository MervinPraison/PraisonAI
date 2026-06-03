"""
Kanban Tools for PraisonAI Agents.

Provides kanban task management tools that allow agents to create, update,
and manage kanban tasks for multi-agent coordination and workflow management.

All tools connect to the same SQLite kanban store as the PraisonAIUI dashboard.
"""

import logging
import os
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Lazy-loaded kanban store instance 
_kanban_store = None


def _get_kanban_store():
    """Lazy load kanban store."""
    global _kanban_store
    if _kanban_store is None:
        try:
            from praisonai.kanban.sqlite_store import SQLiteKanbanStore
            _kanban_store = SQLiteKanbanStore()
        except ImportError as e:
            logger.error(f"Failed to import kanban store: {e}")
            raise ImportError("Kanban functionality requires praisonai kanban module") from e
    return _kanban_store


def kanban_create(
    title: str,
    body: str = "",
    assignee: str = "",
    status: str = "todo",
    priority: int = 0,
    board: str = "default"
) -> Dict[str, Any]:
    """
    Create a kanban task for multi-agent coordination.
    
    Args:
        title: Task title (required)
        body: Task description/details
        assignee: Username or agent name to assign to
        status: Task status (todo, ready, running, blocked, done)
        priority: Task priority (higher number = higher priority)
        board: Board name to create task on
        
    Returns:
        Dict containing the created task details including task ID
    
    Example:
        >>> kanban_create("Implement user authentication", assignee="coder")
        {'id': 'task_abc123', 'title': 'Implement user authentication', ...}
    """
    try:
        store = _get_kanban_store()
        
        task_data = {
            'title': title,
            'body': body,
            'assignee': assignee,
            'status': status,
            'priority': priority,
            'board': board
        }
        
        task = store.create_task(task_data)
        return task.to_dict()
        
    except Exception as e:
        logger.error(f"Failed to create kanban task: {e}")
        return {'error': str(e)}


def kanban_list(
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    board: str = "default",
    limit: int = 50
) -> Dict[str, Any]:
    """
    List kanban tasks with optional filtering.
    
    Args:
        status: Filter by status (todo, ready, running, blocked, done)
        assignee: Filter by assignee username
        board: Board name to list from
        limit: Maximum number of tasks to return
        
    Returns:
        Dict containing list of tasks and metadata
    
    Example:
        >>> kanban_list(status="ready", assignee="coder")
        {'tasks': [...], 'count': 3, 'filters': {...}}
    """
    try:
        store = _get_kanban_store()
        
        filters = {'board': board}
        if status:
            filters['status'] = status
        if assignee:
            filters['assignee'] = assignee
        
        tasks = store.list_tasks(filters)
        
        # Limit results
        if len(tasks) > limit:
            tasks = tasks[:limit]
        
        return {
            'tasks': [task.to_dict() for task in tasks],
            'count': len(tasks),
            'filters': filters,
            'limited': len(tasks) == limit
        }
        
    except Exception as e:
        logger.error(f"Failed to list kanban tasks: {e}")
        return {'error': str(e)}


def kanban_show(task_id: str) -> Dict[str, Any]:
    """
    Show detailed information about a specific task.
    
    Args:
        task_id: The task ID to retrieve
        
    Returns:
        Dict containing task details, comments, and dependencies
    
    Example:
        >>> kanban_show("task_abc123")
        {'task': {...}, 'comments': [...], 'dependencies': [...]}
    """
    try:
        store = _get_kanban_store()
        
        task = store.get_task(task_id)
        if not task:
            return {'error': f'Task {task_id} not found'}
        
        # Get comments
        comments = store.get_comments(task_id)
        
        # Get parent/child links (simplified - would need more complex query for full DAG)
        result = {
            'task': task.to_dict(),
            'comments': [comment.to_dict() for comment in comments],
            'comment_count': len(comments)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to show kanban task {task_id}: {e}")
        return {'error': str(e)}


def kanban_complete(task_id: str, comment: str = "") -> Dict[str, Any]:
    """
    Mark a task as completed.
    
    Args:
        task_id: The task ID to complete
        comment: Optional completion comment
        
    Returns:
        Dict containing the updated task
    
    Example:
        >>> kanban_complete("task_abc123", "Authentication system working")
        {'task': {...}, 'status': 'done'}
    """
    try:
        store = _get_kanban_store()
        
        # Move to done status
        task = store.move_task(task_id, 'done')
        
        # Add completion comment if provided
        if comment:
            store.add_comment(task_id, 'agent', f"Completed: {comment}")
        
        return {
            'task': task.to_dict(),
            'status': 'done',
            'completed': True
        }
        
    except Exception as e:
        logger.error(f"Failed to complete kanban task {task_id}: {e}")
        return {'error': str(e)}


def kanban_block(task_id: str, reason: str) -> Dict[str, Any]:
    """
    Mark a task as blocked with a reason.
    
    Args:
        task_id: The task ID to block
        reason: Reason why the task is blocked
        
    Returns:
        Dict containing the updated task
    
    Example:
        >>> kanban_block("task_abc123", "Waiting for API credentials")
        {'task': {...}, 'status': 'blocked'}
    """
    try:
        store = _get_kanban_store()
        
        # Move to blocked status
        task = store.move_task(task_id, 'blocked')
        
        # Add blocking reason as comment
        store.add_comment(task_id, 'agent', f"Blocked: {reason}")
        
        return {
            'task': task.to_dict(),
            'status': 'blocked',
            'reason': reason
        }
        
    except Exception as e:
        logger.error(f"Failed to block kanban task {task_id}: {e}")
        return {'error': str(e)}


def kanban_comment(task_id: str, text: str, author: str = "agent") -> Dict[str, Any]:
    """
    Add a comment to a kanban task.
    
    Args:
        task_id: The task ID to comment on
        text: Comment text
        author: Comment author (defaults to 'agent')
        
    Returns:
        Dict containing the created comment
    
    Example:
        >>> kanban_comment("task_abc123", "Made progress on auth module")
        {'comment': {...}, 'task_id': 'task_abc123'}
    """
    try:
        store = _get_kanban_store()
        
        comment = store.add_comment(task_id, author, text)
        
        return {
            'comment': comment.to_dict(),
            'task_id': task_id
        }
        
    except Exception as e:
        logger.error(f"Failed to add comment to kanban task {task_id}: {e}")
        return {'error': str(e)}


def kanban_link(parent_id: str, child_id: str) -> Dict[str, Any]:
    """
    Create a dependency link between two tasks.
    
    Args:
        parent_id: The parent task ID (must be completed before child)
        child_id: The child task ID (depends on parent)
        
    Returns:
        Dict containing the created link
    
    Example:
        >>> kanban_link("task_design", "task_implement")
        {'link': {...}, 'parent_id': 'task_design', 'child_id': 'task_implement'}
    """
    try:
        store = _get_kanban_store()
        
        link = store.add_link(parent_id, child_id)
        
        return {
            'link': {
                'parent_id': link.parent_id,
                'child_id': link.child_id,
                'created_at': link.created_at.isoformat()
            },
            'parent_id': parent_id,
            'child_id': child_id
        }
        
    except Exception as e:
        logger.error(f"Failed to link kanban tasks {parent_id} -> {child_id}: {e}")
        return {'error': str(e)}


def kanban_heartbeat(task_id: str, status: str = "working") -> Dict[str, Any]:
    """
    Send a heartbeat signal while working on a task.
    
    Args:
        task_id: The task ID being worked on
        status: Status message (e.g., "working", "testing", "debugging")
        
    Returns:
        Dict containing heartbeat confirmation
    
    Example:
        >>> kanban_heartbeat("task_abc123", "testing authentication flow")
        {'heartbeat': True, 'task_id': 'task_abc123', 'status': 'testing...'}
    """
    try:
        store = _get_kanban_store()
        
        # Verify task exists and is claimed
        task = store.get_task(task_id)
        if not task:
            return {'error': f'Task {task_id} not found'}
        
        # Add heartbeat comment
        store.add_comment(
            task_id, 
            'agent', 
            f"Heartbeat: {status} at {task.updated_at.strftime('%H:%M:%S')}"
        )
        
        return {
            'heartbeat': True,
            'task_id': task_id,
            'status': status,
            'timestamp': task.updated_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to send heartbeat for kanban task {task_id}: {e}")
        return {'error': str(e)}


# Export all kanban tools for agent registration
KANBAN_TOOLS = [
    kanban_create,
    kanban_list,
    kanban_show,
    kanban_complete,
    kanban_block,
    kanban_comment,
    kanban_link,
    kanban_heartbeat,
]


def get_kanban_tools() -> List[callable]:
    """
    Get all kanban tools for agent registration.
    
    Returns:
        List of kanban tool functions
    
    Example:
        >>> from praisonai.tools.kanban_tools import get_kanban_tools
        >>> agent = Agent(name="coordinator", tools=get_kanban_tools())
    """
    return KANBAN_TOOLS


def create_kanban_agent_tools(board: str = "default") -> List[callable]:
    """
    Create kanban tools bound to a specific board.
    
    Args:
        board: Board name to bind tools to
        
    Returns:
        List of board-specific kanban tools
    """
    # Create board-specific versions of tools with board parameter pre-filled
    def _make_board_tool(tool_func, board_name):
        def wrapper(*args, **kwargs):
            if 'board' not in kwargs:
                kwargs['board'] = board_name
            return tool_func(*args, **kwargs)
        wrapper.__name__ = f"{tool_func.__name__}_{board_name}"
        wrapper.__doc__ = tool_func.__doc__
        return wrapper
    
    board_tools = []
    for tool in KANBAN_TOOLS:
        if 'board' in tool.__code__.co_varnames:
            board_tools.append(_make_board_tool(tool, board))
        else:
            board_tools.append(tool)
    
    return board_tools