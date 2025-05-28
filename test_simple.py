#!/usr/bin/env python3
"""
Simple test for context extraction without requiring OpenAI API
"""

import sys
import os

# Add the praisonai-agents source to the path
sys.path.insert(0, "/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents")

from praisonaiagents.agent.agent import extract_task_context

def test_context_extraction():
    print("Testing Context Extraction Function")
    print("=" * 40)
    
    test_cases = [
        "Run all tools to gather initial domain data for 'eenadu.net'",
        "Analyze tool output for vulnerabilities for domain 'google.com'",
        "Please investigate the target website reddit.com",
        "Check the site stackoverflow.com for issues",
        "Query the host github.com for information",
        "Run tools with no specific domain mentioned"
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case}")
        context = extract_task_context(test_case)
        print(f"Domain: {context.domain}")
        print(f"Target: {context.target}")
        print(f"Description: {context.description[:50]}...")

if __name__ == "__main__":
    test_context_extraction()