"""
GNAP Tool Functions for Agent Use.

Provides @tool functions that agents can call to interact with GNAP storage.
"""

import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path

# Import tool decorator from praisonaiagents (via praisonai_tools dependency)
try:
    from praisonaiagents import tool
except ImportError:
    # Fallback if praisonaiagents not available
    def tool(func):
        """Fallback tool decorator."""
        return func

from .gnap_plugin import GnapPlugin


# Global plugin instance (lazy initialized)
_gnap_plugin: Optional[GnapPlugin] = None


def _get_gnap_plugin() -> GnapPlugin:
    """Get or create the global GNAP plugin instance."""
    global _gnap_plugin
    if _gnap_plugin is None:
        repo_path = os.getenv("GNAP_REPO_PATH", ".")
        _gnap_plugin = GnapPlugin(repo_path=repo_path)
        _gnap_plugin.on_init({})
    return _gnap_plugin


@tool
def gnap_save_state(task_id: str, state: Dict[str, Any]) -> str:
    """
    Save agent task state to GNAP storage with git persistence.
    
    Args:
        task_id: Unique identifier for the task
        state: Dictionary containing task state data
        
    Returns:
        Success message with task ID
        
    Example:
        gnap_save_state("research_001", {
            "status": "completed",
            "results": ["finding1", "finding2"],
            "agent": "researcher"
        })
    """
    try:
        plugin = _get_gnap_plugin()
        plugin.save(task_id, state)
        return f"Successfully saved state for task: {task_id}"
    except Exception as e:
        return f"Error saving state for task {task_id}: {str(e)}"


@tool
def gnap_load_state(task_id: str) -> Dict[str, Any]:
    """
    Load agent task state from GNAP storage.
    
    Args:
        task_id: Unique identifier for the task
        
    Returns:
        Dictionary containing task state data, or error message
        
    Example:
        state = gnap_load_state("research_001")
        if state and "status" in state:
            print(f"Task status: {state['status']}")
    """
    try:
        plugin = _get_gnap_plugin()
        state = plugin.load(task_id)
        
        if state is None:
            return {"error": f"Task {task_id} not found"}
        
        return state
    except Exception as e:
        return {"error": f"Error loading state for task {task_id}: {str(e)}"}


@tool
def gnap_list_tasks(prefix: str = "", status_filter: str = "") -> List[Dict[str, Any]]:
    """
    List all tasks in GNAP storage with optional filtering.
    
    Args:
        prefix: Optional prefix to filter task IDs
        status_filter: Optional status to filter tasks by
        
    Returns:
        List of task summaries with metadata
        
    Example:
        # List all tasks
        all_tasks = gnap_list_tasks()
        
        # List completed tasks
        completed = gnap_list_tasks(status_filter="completed")
        
        # List research tasks
        research_tasks = gnap_list_tasks(prefix="research_")
    """
    try:
        plugin = _get_gnap_plugin()
        task_ids = plugin.list_keys(prefix=prefix)
        
        tasks = []
        for task_id in task_ids:
            try:
                state = plugin.load(task_id)
                if state is None:
                    continue
                
                # Apply status filter if specified
                if status_filter and state.get("status") != status_filter:
                    continue
                
                # Create task summary
                task_summary = {
                    "task_id": task_id,
                    "status": state.get("status", "unknown"),
                    "agent": state.get("agent", "unknown"),
                    "last_updated": state.get("last_updated", "unknown")
                }
                
                # Add any other relevant summary fields
                if "description" in state:
                    task_summary["description"] = state["description"]
                if "priority" in state:
                    task_summary["priority"] = state["priority"]
                
                tasks.append(task_summary)
                
            except Exception:
                # Skip tasks that can't be loaded
                continue
        
        return tasks
    except Exception as e:
        return [{"error": f"Error listing tasks: {str(e)}"}]


@tool
def gnap_commit(message: str) -> str:
    """
    Manually commit current GNAP state to git with a custom message.
    
    Args:
        message: Commit message describing the changes
        
    Returns:
        Success message with commit details
        
    Example:
        gnap_commit("Completed research phase for project Alpha")
    """
    try:
        plugin = _get_gnap_plugin()
        
        # Force a manual commit
        plugin._commit_changes(f"Manual commit: {message}")
        
        # Get current branch info
        branch = plugin._get_current_branch()
        
        return f"Successfully committed GNAP state to branch '{branch}' with message: {message}"
    except Exception as e:
        return f"Error committing GNAP state: {str(e)}"


@tool
def gnap_get_status() -> Dict[str, Any]:
    """
    Get a comprehensive status summary of all GNAP tasks.
    
    Returns:
        Dictionary containing task statistics and recent activity
        
    Example:
        status = gnap_get_status()
        print(f"Total tasks: {status['total_tasks']}")
        print(f"Completed: {status['by_status'].get('completed', 0)}")
    """
    try:
        plugin = _get_gnap_plugin()
        return plugin.get_status_summary()
    except Exception as e:
        return {"error": f"Error getting GNAP status: {str(e)}"}


@tool
def gnap_get_history(task_id: str) -> List[Dict[str, Any]]:
    """
    Get the git commit history for a specific task.
    
    Args:
        task_id: Unique identifier for the task
        
    Returns:
        List of commit records showing task evolution
        
    Example:
        history = gnap_get_history("research_001")
        for commit in history:
            print(f"{commit['timestamp']}: {commit['message']}")
    """
    try:
        plugin = _get_gnap_plugin()
        return plugin.get_task_history(task_id)
    except Exception as e:
        return [{"error": f"Error getting history for task {task_id}: {str(e)}"}]


@tool
def gnap_create_workflow_branch(workflow_id: str) -> str:
    """
    Create a new git branch for workflow isolation.
    
    Args:
        workflow_id: Unique identifier for the workflow
        
    Returns:
        Name of the created/switched branch
        
    Example:
        branch = gnap_create_workflow_branch("data_analysis_pipeline")
        # All subsequent GNAP operations will be on this branch
    """
    try:
        plugin = _get_gnap_plugin()
        branch_name = plugin.create_workflow_branch(workflow_id)
        return f"Created/switched to workflow branch: {branch_name}"
    except Exception as e:
        return f"Error creating workflow branch: {str(e)}"


@tool
def gnap_merge_workflow(workflow_branch: str) -> str:
    """
    Merge a completed workflow branch back to main.
    
    Args:
        workflow_branch: Name of the workflow branch to merge
        
    Returns:
        Success message or error details
        
    Example:
        result = gnap_merge_workflow("gnap-workflow-data_analysis_pipeline")
    """
    try:
        plugin = _get_gnap_plugin()
        success = plugin.merge_workflow_to_main(workflow_branch)
        
        if success:
            return f"Successfully merged workflow branch '{workflow_branch}' to main"
        else:
            return f"Failed to merge workflow branch '{workflow_branch}'"
    except Exception as e:
        return f"Error merging workflow branch: {str(e)}"