#!/usr/bin/env python3
"""
Test script based on the user's original issue #289 code.
This tests the context injection fix for domain-aware tool execution.
"""

import sys
import os

# Add the praisonai-agents source to the path  
sys.path.insert(0, "/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents")

from praisonaiagents import Agent, Task, PraisonAIAgents

def query_fofa(query: str = "example.com") -> dict:
    """Test version of FOFA query tool with default domain"""
    print(f"🔍 FOFA tool called with query: {query}")
    return {"tool": "fofa", "query": query, "results": f"Mock FOFA results for {query}"}

def query_crtsh(domain: str = "example.com") -> dict:
    """Test version of CRT.SH query tool with default domain"""
    print(f"🔍 CRT.SH tool called with domain: {domain}")
    return {"tool": "crt.sh", "domain": domain, "results": f"Mock certificate data for {domain}"}

def query_whoxy(email_or_org: str = "example.com") -> dict:
    """Test version of WHOXY tool with default domain"""
    print(f"🔍 WHOXY tool called with email_or_org: {email_or_org}")
    return {"tool": "whoxy", "target": email_or_org, "results": f"Mock WHOIS data for {email_or_org}"}

def query_api_ninjas(domain: str = "example.com") -> dict:
    """Test version of API Ninjas DNS lookup tool"""
    print(f"🔍 API Ninjas tool called with domain: {domain}")
    return {"tool": "api_ninjas", "domain": domain, "results": f"Mock DNS data for {domain}"}

def query_networkcalc(domain: str = "example.com") -> dict:
    """Test version of NetworkCalc tool"""
    print(f"🔍 NetworkCalc tool called with domain: {domain}")
    return {"tool": "networkcalc", "domain": domain, "results": f"Mock network data for {domain}"}

def query_fofa_with_context(query: str = "example.com", task_context=None) -> dict:
    """Context-aware version of FOFA tool"""
    actual_query = query
    if task_context and (task_context.domain or task_context.target):
        actual_query = task_context.domain or task_context.target
        print(f"🎯 FOFA tool using context domain: {actual_query}")
    else:
        print(f"🔍 FOFA tool using default/provided query: {query}")
    
    return {"tool": "fofa_context", "query": actual_query, "context_used": task_context is not None}

def main():
    print("Testing User Scenario - Context Injection Fix")
    print("=" * 50)
    
    # Create agents similar to user's setup
    tool_agent = Agent(
        name="Tool Agent",
        role="Run initial tool queries", 
        goal="Gather subdomains, DNS records, reverse WHOIS data, and FOFA data.",
        backstory="Tool specialist to run initial information-gathering queries using all available tools.",
        tools=[query_fofa, query_crtsh, query_whoxy, query_api_ninjas, query_networkcalc, query_fofa_with_context],
        verbose=True,
        llm="gpt-4o"  # This will fail but we can still test context extraction
    )
    
    # Test 1: Task with explicit domain (like user's issue)
    print("\n🧪 Test 1: Task with domain 'eenadu.net'")
    print("-" * 30)
    
    task_description = "Run all tools to gather initial domain data for 'eenadu.net'. IMPORTANT: Use the domain 'eenadu.net' for all tool queries, not example.com or any other domain."
    
    try:
        # This would normally trigger LLM but will fail - that's ok for testing context extraction
        result = tool_agent.chat(task_description)
        print(f"Chat result: {result}")
    except Exception as e:
        print(f"Expected error (no API key): {e}")
        
    # Check if context was extracted correctly
    if hasattr(tool_agent, '_current_task_context') and tool_agent._current_task_context:
        ctx = tool_agent._current_task_context
        print(f"✅ Context extracted successfully!")
        print(f"   Domain: {ctx.domain}")
        print(f"   Target: {ctx.target}")
        print(f"   Description: {ctx.description[:60]}...")
    else:
        print("❌ No context extracted")
        
    # Test 2: Direct tool execution with context injection
    print("\n🧪 Test 2: Direct tool execution with context")
    print("-" * 30)
    
    if hasattr(tool_agent, '_current_task_context'):
        ctx = tool_agent._current_task_context
        
        print("Testing tools with context injection:")
        
        # Test regular tool (should get domain injected)
        print("\n📍 Testing query_fofa (should inject domain):")
        result1 = tool_agent.execute_tool("query_fofa", {}, ctx)
        print(f"Result: {result1}")
        
        # Test context-aware tool
        print("\n📍 Testing query_fofa_with_context (should use task_context):")
        result2 = tool_agent.execute_tool("query_fofa_with_context", {}, ctx)
        print(f"Result: {result2}")
        
        # Test with explicit argument (should NOT be overridden)
        print("\n📍 Testing with explicit domain argument:")
        result3 = tool_agent.execute_tool("query_fofa", {"query": "explicit.com"}, ctx)
        print(f"Result: {result3}")

if __name__ == "__main__":
    main()