"""Delegation and sub-agent tools.

This module provides tools for delegating tasks to sub-agents and managing
multi-agent workflows.
"""

import json
import logging
from typing import Dict, Any, Optional
from ..approval import require_approval
from .subagent_tool import create_subagent_tool

logger = logging.getLogger(__name__)


class DelegationTools:
    """Tools for task delegation and sub-agent management."""
    
    def __init__(self, workspace=None):
        """Initialize DelegationTools.
        
        Args:
            workspace: Optional Workspace instance for path containment
        """
        self._workspace = workspace
    
    @require_approval(risk_level="medium")
    def delegate_task(self, task_description: str, agent_type: str = "general",
                     priority: str = "medium", timeout: int = 300) -> str:
        """Delegate a task to a sub-agent.

        Wires into the existing ``create_subagent_tool`` runtime: a lightweight
        sub-``Agent`` is spawned to execute ``task_description``. The agent is
        derived from ``agent_type`` (used as its role) so the model can be
        steered toward the desired specialisation without any extra config.

        Args:
            task_description: Description of the task to delegate
            agent_type: Type/role of agent to delegate to (e.g. "research")
            priority: Task priority (low, medium, high)
            timeout: Maximum execution time in seconds

        Returns:
            JSON string with delegation result
        """
        try:
            def _agent_factory(name=None, tools=None, llm=None):
                from praisonaiagents.agent.agent import Agent
                role = agent_type if agent_type and agent_type != "general" else "assistant"
                return Agent(
                    name=name or f"{agent_type}_agent",
                    role=role,
                    goal=f"Complete delegated {agent_type} tasks accurately.",
                    llm=llm,
                    verbose=False,
                )

            spawn = create_subagent_tool(agent_factory=_agent_factory)["function"]

            # The subagent runs synchronously; enforce the caller-supplied
            # ``timeout`` by executing it on a worker thread and bounding the
            # wait. On expiry we surface a structured failure instead of
            # blocking past the documented deadline. A non-positive timeout
            # means "no bound".
            if timeout and timeout > 0:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        spawn, task=task_description, agent_name=agent_type
                    )
                    try:
                        result = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        return json.dumps({
                            "success": False,
                            "task_description": task_description,
                            "agent_type": agent_type,
                            "error": f"Delegated task timed out after {timeout}s",
                        }, indent=2)
            else:
                result = spawn(task=task_description, agent_name=agent_type)

            if not result.get("success"):
                return json.dumps({
                    "success": False,
                    "task_description": task_description,
                    "agent_type": agent_type,
                    "error": result.get("error", "delegation failed"),
                }, indent=2)

            return json.dumps({
                "success": True,
                "task_description": task_description,
                "agent_type": agent_type,
                "priority": priority,
                "output": result.get("output"),
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "task_description": task_description,
                "agent_type": agent_type,
                "error": f"Error delegating task: {e!s}"
            }, indent=2)


# Create default instance for direct function access
_delegation_tools = DelegationTools()

@require_approval(risk_level="medium")
def delegate_task(task_description: str, agent_type: str = "general",
                 priority: str = "medium", timeout: int = 300) -> str:
    """Delegate a task to a sub-agent.
    
    Args:
        task_description: Description of the task to delegate
        agent_type: Type of agent to delegate to
        priority: Task priority (low, medium, high)
        timeout: Maximum execution time in seconds
        
    Returns:
        JSON string with delegation result
    """
    return _delegation_tools.delegate_task(task_description, agent_type, priority, timeout)


def create_delegation_tools(workspace=None) -> DelegationTools:
    """Create DelegationTools instance with optional workspace containment.
    
    Args:
        workspace: Optional Workspace instance for path containment
        
    Returns:
        DelegationTools instance configured with workspace
    """
    return DelegationTools(workspace=workspace)