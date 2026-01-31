"""
AgentOS module for production deployment of AI agents.

This module provides the AgentOS class which implements the AgentOSProtocol
from the core SDK. It wraps agents, managers, and workflows into a unified
FastAPI-based web service.

Example:
    from praisonai import AgentOS
    from praisonaiagents import Agent
    
    assistant = Agent(name="assistant", instructions="Be helpful")
    
    app = AgentOS(
        name="My AI App",
        agents=[assistant],
    )
    app.serve(port=8000)
"""

from .app import AgentOS

__all__ = ['AgentOS']
