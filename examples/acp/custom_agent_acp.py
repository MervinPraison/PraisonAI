#!/usr/bin/env python3
"""
Custom Agent ACP Server Example

This example shows how to run a custom PraisonAI agent as an ACP server.

Usage:
    python custom_agent_acp.py
"""

from praisonai.acp import serve, ACPServer, ACPConfig
from praisonaiagents import Agent

# Create a custom agent
agent = Agent(
    name="CodeAssistant",
    instructions="""You are an expert coding assistant. You help users:
    - Write clean, efficient code
    - Debug issues
    - Explain complex concepts
    - Review code for best practices
    
    Always provide clear explanations with your code suggestions.""",
    model="gpt-4o-mini",
)

if __name__ == "__main__":
    # Create config
    config = ACPConfig(
        workspace=".",
        debug=True,
        allow_write=True,  # Allow file modifications
        approval_mode="manual",
    )
    
    # Create server with custom agent
    server = ACPServer(config=config, agent=agent)
    
    # Run the server
    serve(
        workspace=".",
        debug=True,
        allow_write=True,
        approval_mode="manual",
    )
