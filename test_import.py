#!/usr/bin/env python3
"""
Test script to verify that the agent import works
"""
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

try:
    from praisonaiagents.agent.agent import Agent
    print("Import successful! Agent class loaded.")
    
    # Test creating an agent
    agent = Agent(instructions="You are a helpful AI assistant")
    print("Agent created successfully!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)