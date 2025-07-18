#!/usr/bin/env python3
"""Test script to verify the agent fix works correctly."""

import os
import sys

# Remove any existing OpenAI API key to test the error handling
if 'OPENAI_API_KEY' in os.environ:
    del os.environ['OPENAI_API_KEY']

# Test the agent with no API key
from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)

print("Testing agent with no API key...")
try:
    response = agent.start("Why is the sky blue?")
    print(f"Unexpected success: {response}")
except Exception as e:
    print(f"Expected error caught: {e}")
    print("✅ Fix working correctly - error is properly displayed")

print("\nTesting agent with API key...")
# Test with a dummy API key
test_agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    api_key="test-key"
)

try:
    response = test_agent.start("Why is the sky blue?")
    print(f"Response: {response}")
except Exception as e:
    print(f"Error with API key: {e}")