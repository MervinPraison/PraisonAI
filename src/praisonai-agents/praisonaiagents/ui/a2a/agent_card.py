"""
A2A Agent Card Generation

Generate Agent Cards from PraisonAI Agents for A2A discovery.
"""

import inspect
from typing import TYPE_CHECKING, List, Optional

from praisonaiagents.ui.a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
)

if TYPE_CHECKING:
    from praisonaiagents import Agent


def extract_skills_from_tools(tools: Optional[List]) -> List[AgentSkill]:
    """
    Extract AgentSkill objects from a list of tools.
    
    Args:
        tools: List of tool functions or objects
        
    Returns:
        List of AgentSkill objects
    """
    if not tools:
        return []
    
    skills = []
    
    for tool in tools:
        # Skip non-callable items
        if not callable(tool):
            continue
        
        # Get function name
        name = getattr(tool, '__name__', None)
        if not name:
            continue
        
        # Get description from docstring
        docstring = inspect.getdoc(tool)
        description = docstring.split('\n')[0] if docstring else f"Tool: {name}"
        
        # Create skill
        skill = AgentSkill(
            id=name,
            name=name,
            description=description,
            tags=["tool"],
        )
        skills.append(skill)
    
    return skills


def generate_agent_card(
    agent: "Agent",
    url: str,
    version: str = "1.0.0",
    streaming: bool = False,
    push_notifications: bool = False,
) -> AgentCard:
    """
    Generate an A2A Agent Card from a PraisonAI Agent.
    
    Args:
        agent: PraisonAI Agent instance
        url: URL where the A2A endpoint is hosted
        version: Version string for the agent
        streaming: Whether streaming is supported
        push_notifications: Whether push notifications are supported
        
    Returns:
        AgentCard object for A2A discovery
    """
    # Get agent name
    name = getattr(agent, 'name', None) or "PraisonAI Agent"
    
    # Build description from role, goal, or instructions
    description_parts = []
    
    role = getattr(agent, 'role', None)
    if role:
        description_parts.append(role)
    
    goal = getattr(agent, 'goal', None)
    if goal:
        description_parts.append(goal)
    
    instructions = getattr(agent, 'instructions', None)
    if instructions and not description_parts:
        # Use first line of instructions if no role/goal
        description_parts.append(instructions.split('\n')[0][:200])
    
    description = ". ".join(description_parts) if description_parts else "PraisonAI Agent"
    
    # Extract skills from tools
    tools = getattr(agent, 'tools', None)
    skills = extract_skills_from_tools(tools)
    
    # Build capabilities
    capabilities = AgentCapabilities(
        streaming=streaming,
        push_notifications=push_notifications,
    )
    
    # Create Agent Card
    card = AgentCard(
        name=name,
        url=url,
        version=version,
        description=description,
        capabilities=capabilities,
        skills=skills if skills else None,
        provider={"name": "PraisonAI"},
    )
    
    return card
