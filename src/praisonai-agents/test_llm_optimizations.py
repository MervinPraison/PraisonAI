#!/usr/bin/env python
"""Test script to verify LLM performance optimizations."""

import time
from praisonaiagents import Agent
from praisonaiagents.llm import LLM

def test_llm_initialization():
    """Test LLM initialization time."""
    print("1. Testing LLM initialization...")
    
    # First LLM (cold start - logging configuration)
    start = time.time()
    llm1 = LLM(model="gemini/gemini-2.5-flash")
    init_time1 = time.time() - start
    print(f"   First LLM initialization: {init_time1:.3f}s")
    
    # Check if console was created
    console_created = hasattr(llm1, '_console') and llm1._console is not None
    print(f"   Console created during init: {console_created}")
    
    # Second LLM (warm start - logging already configured)
    start = time.time()
    llm2 = LLM(model="gemini/gemini-2.5-flash")
    init_time2 = time.time() - start
    print(f"   Second LLM initialization: {init_time2:.3f}s")
    print(f"   Speedup: {init_time1/init_time2:.1f}x" if init_time2 > 0 else "   Speedup: ∞")

def test_tool_formatting_cache():
    """Test tool formatting cache in LLM."""
    print("\n2. Testing LLM tool formatting cache...")
    
    def sample_tool(query: str) -> str:
        """A sample tool for testing."""
        return f"Result: {query}"
    
    llm = LLM(model="gemini/gemini-2.5-flash")
    tools = [sample_tool]
    
    # First format (cold cache)
    start = time.time()
    formatted1 = llm._format_tools_for_litellm(tools)
    time1 = time.time() - start
    
    # Second format (warm cache)
    start = time.time()
    formatted2 = llm._format_tools_for_litellm(tools)
    time2 = time.time() - start
    
    print(f"   First tool formatting: {time1:.4f}s")
    print(f"   Second tool formatting (cached): {time2:.4f}s")
    print(f"   Cache speedup: {time1/time2:.1f}x" if time2 > 0 else "   Cache speedup: ∞")

def test_console_lazy_loading():
    """Test console lazy loading in LLM."""
    print("\n3. Testing LLM console lazy loading...")
    
    # LLM without verbose (console not needed)
    llm1 = LLM(model="gemini/gemini-2.5-flash", verbose=False)
    console_created_before = hasattr(llm1, '_console') and llm1._console is not None
    print(f"   Console created before access (verbose=False): {console_created_before}")
    
    # Access console
    _ = llm1.console
    console_created_after = hasattr(llm1, '_console') and llm1._console is not None
    print(f"   Console created after access: {console_created_after}")

def test_agent_with_custom_llm():
    """Test Agent using optimized LLM."""
    print("\n4. Testing Agent with custom optimized LLM...")
    
    start = time.time()
    # Create LLM instance
    llm_instance = LLM(model="gemini/gemini-2.5-flash")
    llm_time = time.time() - start
    print(f"   LLM creation time: {llm_time:.3f}s")
    
    start = time.time()
    # Create Agent with the LLM instance
    agent = Agent(
        instructions="You are a helpful assistant",
        llm=llm_instance
    )
    agent_time = time.time() - start
    print(f"   Agent creation time with LLM: {agent_time:.3f}s")
    
    # Total time
    print(f"   Total initialization time: {(llm_time + agent_time):.3f}s")

def test_multiple_llm_instances():
    """Test multiple LLM instances to verify shared logging configuration."""
    print("\n5. Testing multiple LLM instances...")
    
    times = []
    for i in range(5):
        start = time.time()
        llm = LLM(model="gemini/gemini-2.5-flash")
        init_time = time.time() - start
        times.append(init_time)
        if i == 0:
            print(f"   LLM {i+1} initialization: {init_time:.4f}s (cold start)")
        else:
            print(f"   LLM {i+1} initialization: {init_time:.4f}s")
    
    avg_warm = sum(times[1:]) / len(times[1:])
    print(f"\n   First LLM (cold): {times[0]:.4f}s")
    print(f"   Average subsequent LLMs: {avg_warm:.4f}s")
    print(f"   Speedup after first: {times[0]/avg_warm:.1f}x" if avg_warm > 0 else "   Speedup: ∞")

if __name__ == "__main__":
    print("Testing LLM Performance Optimizations")
    print("=====================================")
    
    test_llm_initialization()
    test_tool_formatting_cache()
    test_console_lazy_loading()
    test_agent_with_custom_llm()
    test_multiple_llm_instances()
    
    print("\nAll tests completed!")