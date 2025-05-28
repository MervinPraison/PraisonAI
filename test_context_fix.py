#!/usr/bin/env python3
"""
Test script for the context injection fix.
This simulates the user's issue where tools use default domains instead of task-specified domains.
"""

import sys
import os

# Add the praisonai-agents source to the path
sys.path.insert(0, "/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents")

from praisonaiagents import Agent

def test_tool_with_defaults(domain: str = "example.com") -> dict:
    """Test tool that defaults to example.com but should use task context domain"""
    return {"tested_domain": domain, "message": f"Tool executed for domain: {domain}"}

def test_tool_with_context(domain: str = "example.com", task_context=None) -> dict:
    """Test tool that can optionally accept task context"""
    actual_domain = domain
    
    if task_context and (task_context.domain or task_context.target):
        actual_domain = task_context.domain or task_context.target
        
    return {
        "tested_domain": actual_domain, 
        "context_used": task_context is not None,
        "message": f"Tool executed for domain: {actual_domain}"
    }

def main():
    print("Testing Context Injection Fix for Issue #289")
    print("=" * 50)
    
    # Create agent with tools
    agent = Agent(
        name="Test Agent",
        role="Domain Tester", 
        goal="Test domain context injection",
        tools=[test_tool_with_defaults, test_tool_with_context],
        verbose=True,
        llm="gpt-4o"
    )
    
    # Test cases
    test_cases = [
        {
            "name": "Direct domain mention",
            "prompt": "Run the test tools for the domain eenadu.net"
        },
        {
            "name": "Task with target", 
            "prompt": "Please analyze the target google.com using all available tools"
        },
        {
            "name": "No domain context",
            "prompt": "Run the test tools"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"Prompt: {test_case['prompt']}")
        print("-" * 30)
        
        try:
            # This should trigger context extraction and injection
            response = agent.chat(test_case['prompt'])
            print(f"Response: {response}")
        except Exception as e:
            print(f"Error: {e}")
            # This is expected since we don't have a real OpenAI API key
            # but the context extraction should still work
            
        # Check if context was extracted
        if hasattr(agent, '_current_task_context') and agent._current_task_context:
            ctx = agent._current_task_context
            print(f"Extracted context: domain={ctx.domain}, target={ctx.target}")
        else:
            print("No context extracted")
        
        print()

if __name__ == "__main__":
    main()