"""
PraisonAI Chat Module

This module provides the chat UI integration for PraisonAI agents.
It uses the PraisonAI Chat (based on Chainlit) for the frontend.
"""

from typing import Optional, Any

__all__ = ["start_chat_server", "ChatConfig"]


class ChatConfig:
    """Configuration for the PraisonAI Chat server."""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        debug: bool = False,
        auth_enabled: bool = False,
        session_id: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.debug = debug
        self.auth_enabled = auth_enabled
        self.session_id = session_id


def start_chat_server(
    agent: Optional[Any] = None,
    agents: Optional[list] = None,
    config: Optional[ChatConfig] = None,
    port: int = 8000,
    host: str = "0.0.0.0",
    debug: bool = False,
) -> None:
    """
    Start the PraisonAI Chat server.
    
    Args:
        agent: A single PraisonAI agent to use in the chat.
        agents: A list of PraisonAI agents for multi-agent chat.
        config: ChatConfig object with server settings.
        port: Port to run the server on (default: 8000).
        host: Host to bind to (default: 0.0.0.0).
        debug: Enable debug mode (default: False).
    
    Example:
        >>> from praisonaiagents import Agent
        >>> from praisonai.chat import start_chat_server
        >>> 
        >>> agent = Agent(name="Assistant", instructions="You are helpful.")
        >>> start_chat_server(agent=agent, port=8000)
    """
    # Lazy import to avoid loading chainlit unless needed
    try:
        from chainlit.cli import run_chainlit
    except ImportError:
        raise ImportError(
            "PraisonAI Chat requires the 'praisonai-chat' package. "
            "Install it with: pip install praisonai-chat"
        )
    
    if config is None:
        config = ChatConfig(host=host, port=port, debug=debug)
    
    # Store agents in a way accessible to the chainlit app
    import os
    os.environ["PRAISONAI_CHAT_MODE"] = "true"
    
    if agent is not None:
        # Single agent mode
        _register_agent(agent)
    elif agents is not None:
        # Multi-agent mode
        for a in agents:
            _register_agent(a)
    
    # Start the chainlit server
    from pathlib import Path
    
    # Use the built-in app file
    app_file = Path(__file__).parent / "app.py"
    
    # Set environment variables for chainlit
    os.environ["CHAINLIT_HOST"] = config.host
    os.environ["CHAINLIT_PORT"] = str(config.port)
    
    run_chainlit(str(app_file))


# Global registry for agents
_REGISTERED_AGENTS: dict = {}


def _register_agent(agent: Any) -> None:
    """Register an agent for use in the chat UI."""
    agent_name = getattr(agent, "name", None) or getattr(agent, "role", "Agent")
    _REGISTERED_AGENTS[agent_name] = agent


def get_registered_agents() -> dict:
    """Get all registered agents."""
    return _REGISTERED_AGENTS
