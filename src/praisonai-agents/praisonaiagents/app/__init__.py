"""
App module for production deployment of AI agents.

This module provides the protocol and configuration for AgentApp,
a production platform for deploying agents as web services.

The protocol is defined here in the core SDK (lightweight).
The implementation lives in the praisonai wrapper (heavy deps like FastAPI).

Example:
    # Protocol is importable from core SDK
    from praisonaiagents import AgentAppProtocol, AgentAppConfig
    
    # Implementation is in wrapper
    from praisonai import AgentApp
    
    app = AgentApp(
        name="My App",
        agents=[researcher, writer],
    )
    app.serve(port=8000)
"""

from .protocols import AgentAppProtocol
from .config import AgentAppConfig

__all__ = [
    'AgentAppProtocol',
    'AgentAppConfig',
]
