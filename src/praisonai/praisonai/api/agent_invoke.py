"""
Agent Invoke API for n8n Integration

Provides an endpoint for n8n workflows to invoke PraisonAI agents,
enabling bidirectional n8n ↔ PraisonAI integration.
"""

from typing import Any, Dict, Optional, Union
import inspect
import logging

try:
    from fastapi import APIRouter, HTTPException, Depends
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    # Fallback for environments without FastAPI
    APIRouter = None
    HTTPException = None
    BaseModel = object
    Field = lambda *args, **kwargs: None
    FASTAPI_AVAILABLE = False

logger = logging.getLogger(__name__)


# Request/Response Models
if FASTAPI_AVAILABLE:
    class AgentInvokeRequest(BaseModel):
        """Request model for agent invocation."""
        message: str = Field(..., description="Message to send to the agent")
        session_id: Optional[str] = Field(None, description="Optional session ID for conversation continuity")
        agent_config: Optional[Dict[str, Any]] = Field(None, description="Optional agent configuration overrides")

    class AgentInvokeResponse(BaseModel):
        """Response model for agent invocation."""
        result: str = Field(..., description="Agent response")
        session_id: str = Field(..., description="Session ID used for this conversation")
        status: str = Field(default="success", description="Response status")
        metadata: Optional[Dict[str, Any]] = Field(None, description="Optional response metadata")

    class ErrorResponse(BaseModel):
        """Error response model."""
        error: str = Field(..., description="Error message")
        status: str = Field(default="error", description="Error status")
        code: Optional[str] = Field(None, description="Error code")
else:
    # Simple dict-based fallbacks
    class AgentInvokeRequest:
        def __init__(self, message: str, session_id: Optional[str] = None, agent_config: Optional[Dict[str, Any]] = None):
            self.message = message
            self.session_id = session_id
            self.agent_config = agent_config
    
    class AgentInvokeResponse:
        def __init__(self, result: str, session_id: str, status: str = "success", metadata: Optional[Dict[str, Any]] = None):
            self.result = result
            self.session_id = session_id
            self.status = status
            self.metadata = metadata
            
    class ErrorResponse:
        def __init__(self, error: str, status: str = "error", code: Optional[str] = None):
            self.error = error
            self.status = status
            self.code = code


# Agent Registry
_agent_registry: Dict[str, Any] = {}


def register_agent(agent_id: str, agent: Any) -> None:
    """Register an agent for invocation via API."""
    _agent_registry[agent_id] = agent
    logger.debug(f"Registered agent: {agent_id}")


def unregister_agent(agent_id: str) -> bool:
    """Unregister an agent."""
    if agent_id in _agent_registry:
        del _agent_registry[agent_id]
        logger.debug(f"Unregistered agent: {agent_id}")
        return True
    return False


def get_agent(agent_id: str) -> Optional[Any]:
    """Get a registered agent by ID."""
    return _agent_registry.get(agent_id)


def list_registered_agents() -> list:
    """List all registered agent IDs."""
    return list(_agent_registry.keys())


def _supports_async_start(agent: Any) -> bool:
    """Return True when agent exposes a real async astart method."""
    astart = getattr(agent, "astart", None)
    return callable(astart) and inspect.iscoroutinefunction(astart)


# FastAPI Router (if FastAPI is available)
if FASTAPI_AVAILABLE and APIRouter is not None:
    router = APIRouter(prefix="/api/v1", tags=["agents"])

    @router.post("/agents/{agent_id}/invoke")
    async def invoke_agent(
        agent_id: str,
        request: AgentInvokeRequest
    ) -> Union[AgentInvokeResponse, ErrorResponse]:
        """
        Invoke a PraisonAI agent with a message.
        
        This endpoint is designed for n8n workflows to call PraisonAI agents,
        enabling bidirectional integration between n8n and PraisonAI.
        
        Args:
            agent_id: The ID of the agent to invoke
            request: The invocation request containing message and optional session_id
            
        Returns:
            Agent response with result and session information
            
        Raises:
            HTTPException: If agent not found or execution fails
            
        Example n8n HTTP Request Node configuration:
        ```json
        {
          "method": "POST",
          "url": "http://praisonai:8000/api/v1/agents/my-agent/invoke",
          "body": {
            "message": "{{ $json.user_input }}",
            "session_id": "{{ $json.session_id }}"
          }
        }
        ```
        """
        # Get agent from registry
        agent = get_agent(agent_id)
        if not agent:
            logger.error(f"Agent not found: {agent_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found. Available agents: {list_registered_agents()}"
            )
        
        try:
            # Set session ID if provided
            session_id = request.session_id or "default"
            
            # Apply agent config overrides if provided
            if request.agent_config:
                # This would depend on the specific agent implementation
                # For now, we'll just log it
                logger.debug(f"Agent config overrides provided: {request.agent_config}")
            
            # Invoke agent (handle both sync and async agents)
            if _supports_async_start(agent):
                # Async agent
                result = await agent.astart(request.message)
            elif hasattr(agent, "start") and callable(agent.start):
                # Sync agent (use start method)
                result = agent.start(request.message)
            else:
                raise AttributeError("Agent must provide start() or async astart()")
            
            logger.info(f"Agent {agent_id} invoked successfully")
            
            return AgentInvokeResponse(
                result=str(result),
                session_id=session_id,
                status="success",
                metadata={
                    "agent_id": agent_id,
                    "message_length": len(request.message),
                    "response_length": len(str(result))
                }
            )
            
        except Exception as e:
            logger.error(f"Agent {agent_id} invocation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Agent execution failed: {str(e)}"
            )

    @router.get("/agents")
    async def list_agents() -> Dict[str, Any]:
        """
        List all registered agents.
        
        Returns:
            Dictionary containing list of available agents
        """
        agents = list_registered_agents()
        return {
            "agents": agents,
            "count": len(agents),
            "status": "success"
        }

    @router.post("/agents/{agent_id}/register")
    async def register_agent_endpoint(agent_id: str) -> Dict[str, Any]:
        """
        Register an agent for API access.
        
        Note: This is a placeholder endpoint. In practice, agents would be
        registered programmatically when they are created.
        """
        # In a real implementation, this might load an agent from a configuration
        # or database. For now, return information about registration.
        return {
            "message": f"Agent registration endpoint for '{agent_id}'",
            "note": "Agents are typically registered programmatically",
            "status": "info"
        }

    @router.delete("/agents/{agent_id}")
    async def unregister_agent_endpoint(agent_id: str) -> Dict[str, Any]:
        """
        Unregister an agent from API access.
        """
        success = unregister_agent(agent_id)
        if success:
            return {
                "message": f"Agent '{agent_id}' unregistered successfully",
                "status": "success"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found"
            )

    @router.get("/agents/{agent_id}")
    async def get_agent_info(agent_id: str) -> Dict[str, Any]:
        """
        Get information about a registered agent.
        """
        agent = get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found"
            )
        
        # Extract basic agent information
        info = {
            "agent_id": agent_id,
            "status": "registered",
            "type": type(agent).__name__,
        }
        
        # Add agent-specific information if available
        if hasattr(agent, 'name'):
            info["name"] = agent.name
        if hasattr(agent, 'instructions'):
            info["instructions"] = agent.instructions[:200] + "..." if len(agent.instructions) > 200 else agent.instructions
        if hasattr(agent, 'tools') and agent.tools:
            info["tools"] = [getattr(tool, 'name', str(tool)) for tool in agent.tools[:5]]  # First 5 tools
            if len(agent.tools) > 5:
                info["tools"].append(f"... and {len(agent.tools) - 5} more")
        
        return info


# Standalone function for non-FastAPI environments
async def invoke_agent_standalone(
    agent_id: str,
    message: str,
    session_id: Optional[str] = None,
    agent_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Standalone function to invoke an agent without FastAPI.
    
    This can be used in environments where FastAPI is not available
    or when integrating with other web frameworks.
    """
    agent = get_agent(agent_id)
    if not agent:
        return {
            "error": f"Agent '{agent_id}' not found",
            "status": "error",
            "available_agents": list_registered_agents()
        }
    
    try:
        # Apply config if provided
        if agent_config:
            logger.debug(f"Agent config provided: {agent_config}")
        
        # Invoke agent
        session_id = session_id or "default"
        
        if _supports_async_start(agent):
            result = await agent.astart(message)
        elif hasattr(agent, "start") and callable(agent.start):
            result = agent.start(message)
        else:
            raise AttributeError("Agent must provide start() or async astart()")
        
        return {
            "result": str(result),
            "session_id": session_id,
            "status": "success",
            "agent_id": agent_id
        }
        
    except Exception as e:
        logger.error(f"Agent {agent_id} invocation failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "agent_id": agent_id
        }


# Example usage and helper functions
def create_example_agents():
    """Create some example agents for testing."""
    try:
        from praisonaiagents import Agent
        
        # Create a simple assistant agent
        assistant = Agent(
            name="assistant",
            instructions="You are a helpful assistant that provides concise, helpful responses."
        )
        register_agent("assistant", assistant)
        
        # Create a coding agent
        coder = Agent(
            name="coder",
            instructions="You are a coding assistant that helps with programming questions and code review."
        )
        register_agent("coder", coder)
        
        logger.info("Example agents created and registered")
        
    except ImportError:
        logger.warning("praisonaiagents not available, skipping example agents")


# Auto-registration helper
def auto_register_agents_from_config(config_file: Optional[str] = None):
    """
    Auto-register agents from a configuration file.
    
    This is a placeholder for a more complete implementation that
    could load agents from YAML, JSON, or other configuration formats.
    """
    logger.info(f"Auto-registering agents from config: {config_file or 'default'}")
    # In a real implementation, this would parse the config and create agents
    create_example_agents()


if __name__ == "__main__":
    # For testing without FastAPI
    import asyncio
    
    async def test_standalone():
        """Test the standalone functionality."""
        create_example_agents()
        
        # Test invocation
        result = await invoke_agent_standalone(
            agent_id="assistant",
            message="Hello, can you help me with n8n integration?"
        )
        print(f"Agent response: {result}")
    
    # asyncio.run(test_standalone())
    print("Agent Invoke API module loaded successfully")
