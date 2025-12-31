#!/usr/bin/env python3
"""
Basic ACP Server Example

This example demonstrates how to run PraisonAI as an ACP server
that can be connected to by IDEs like Zed, JetBrains, VSCode, or Toad.

Usage:
    # Run from command line
    praisonai acp
    
    # Or run this script directly
    python basic_acp_server.py
"""

from praisonai.acp import serve

if __name__ == "__main__":
    # Start ACP server with default settings
    # This will listen on stdin/stdout for JSON-RPC messages
    serve(
        workspace=".",           # Current directory as workspace
        agent="default",         # Use default agent
        debug=False,             # Set to True for debug logging to stderr
        read_only=True,          # Safe by default
        approval_mode="manual",  # Require approval for actions
    )
