#!/usr/bin/env python3
"""Test script to verify the refactored Gemini tools logic."""

import logging
import sys
import os

# Setup logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

try:
    from praisonaiagents.llm.llm import LLM
    from praisonaiagents.llm.openai_client import OpenAIClient
    
    print("Testing LLM tool formatting...")
    llm = LLM(model="gpt-4o-mini")
    tools = [
        {'googleSearch': {}},  # Valid Gemini tool
        {'urlContext': {}},    # Valid Gemini tool  
        {'codeExecution': {}}, # Valid Gemini tool
        {'unknown': {}}        # Invalid tool - should be skipped
    ]
    
    formatted = llm._format_tools_for_litellm(tools)
    print(f"LLM formatted tools ({len(formatted)} tools):", formatted)
    
    print("\nTesting OpenAI client tool formatting...")
    client = OpenAIClient(api_key="not-needed")
    formatted = client.format_tools(tools)
    print(f"OpenAI client formatted tools ({len(formatted)} tools):", formatted)
    
    print("\nTest completed successfully!")
    
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()