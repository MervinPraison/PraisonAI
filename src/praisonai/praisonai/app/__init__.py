"""
AgentApp module for production deployment of AI agents.

This module provides the AgentApp class which implements the AgentAppProtocol
from the core SDK. It wraps agents, managers, and workflows into a unified
FastAPI-based web service.

Example:
    from praisonai import AgentApp
    from praisonaiagents import Agent
    
    assistant = Agent(name="assistant", instructions="Be helpful")
    
    app = AgentApp(
        name="My AI App",
        agents=[assistant],
    )
    app.serve(port=8000)
"""

from .app import AgentApp

__all__ = ['AgentApp']
