#!/usr/bin/env python3
"""Test script to verify MCP schema fix"""

import os
import sys

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from dotenv import load_dotenv
from praisonaiagents import Agent, MCP

# Load .env before importing anything else
load_dotenv()

# Define allowed directories for filesystem access
allowed_dirs = [
    "/Users/praison/praisonai-package/src/praisonai-agents",
]

# Test with minimal example
print("Testing MCP filesystem agent...")

try:
    # Use the correct pattern from filesystem MCP documentation
    filesystem_agent = Agent(
        instructions="""You are a helpful assistant that can interact with the filesystem.
        Use the available tools when relevant to manage files and directories.""",
        llm="gpt-4o-mini",
        tools=MCP(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"] + allowed_dirs
        )
    )
    
    print("✓ Agent created successfully")
    print("✓ MCP tools loaded without schema errors")
    
    # Try to start the agent (this will validate the tool schemas)
    result = filesystem_agent.start("List files in /Users/praison/praisonai-package/src/praisonai-agents directory using MCP list_files")
    print("✓ Agent executed successfully")
    print(f"Result: {result}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTest passed! The MCP schema fix is working correctly.")