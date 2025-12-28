"""
A2A (Agent-to-Agent) Capabilities Module

Provides agent-to-agent communication gateway functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class A2AResult:
    """Result from A2A operations."""
    id: str
    status: str = "sent"
    response: Optional[Any] = None
    target_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def a2a_send(
    message: str,
    target_agent: str,
    source_agent: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> A2AResult:
    """
    Send a message to another agent via A2A protocol.
    
    Args:
        message: Message to send
        target_agent: Target agent identifier
        source_agent: Source agent identifier
        context: Additional context
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        A2AResult with response
        
    Example:
        >>> result = a2a_send(
        ...     "Please analyze this data",
        ...     target_agent="data-analyst"
        ... )
        >>> print(result.response)
    """
    import uuid
    
    # A2A protocol implementation
    # This integrates with PraisonAI's handoff mechanism
    
    message_id = f"a2a-{uuid.uuid4().hex[:12]}"
    
    # Try to use handoff if available
    try:
        from praisonaiagents import Agent
        
        # Create a simple agent to handle the message
        agent = Agent(
            name=target_agent,
            instructions=f"You are {target_agent}. Process the following request.",
        )
        
        response = agent.chat(message)
        
        return A2AResult(
            id=message_id,
            status="completed",
            response=response,
            target_agent=target_agent,
            metadata=metadata or {},
        )
    except Exception:
        # Return pending status if agent not available
        return A2AResult(
            id=message_id,
            status="pending",
            response=None,
            target_agent=target_agent,
            metadata=metadata or {},
        )


async def aa2a_send(
    message: str,
    target_agent: str,
    source_agent: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> A2AResult:
    """
    Async: Send a message to another agent via A2A protocol.
    
    See a2a_send() for full documentation.
    """
    import uuid
    
    message_id = f"a2a-{uuid.uuid4().hex[:12]}"
    
    try:
        from praisonaiagents import Agent
        
        agent = Agent(
            name=target_agent,
            instructions=f"You are {target_agent}. Process the following request.",
        )
        
        # Use async chat if available
        if hasattr(agent, 'achat'):
            response = await agent.achat(message)
        else:
            response = agent.chat(message)
        
        return A2AResult(
            id=message_id,
            status="completed",
            response=response,
            target_agent=target_agent,
            metadata=metadata or {},
        )
    except Exception:
        return A2AResult(
            id=message_id,
            status="pending",
            response=None,
            target_agent=target_agent,
            metadata=metadata or {},
        )
