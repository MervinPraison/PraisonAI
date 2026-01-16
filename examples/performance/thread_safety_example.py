#!/usr/bin/env python3
"""
Example: Thread-Safe Agent State

Demonstrates thread-safe chat history and cache management
in PraisonAI Agents.
"""
import os
import threading
import time


def example_lite_agent_thread_safety():
    """Demonstrate thread safety with LiteAgent."""
    print("=" * 60)
    print("Example 1: LiteAgent Thread Safety")
    print("=" * 60)
    
    from praisonaiagents.lite import LiteAgent
    
    # Counter for tracking responses
    response_count = [0]
    count_lock = threading.Lock()
    
    def counting_llm(messages):
        with count_lock:
            response_count[0] += 1
            return f"Response #{response_count[0]}"
    
    agent = LiteAgent(
        name="ThreadSafeAgent",
        llm_fn=counting_llm
    )
    
    errors = []
    
    def worker(thread_id):
        try:
            for i in range(10):
                agent.chat(f"Thread {thread_id}, message {i}")
        except Exception as e:
            errors.append(e)
    
    # Create and start threads
    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(5)
    ]
    
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start
    
    print(f"Threads: 5")
    print(f"Messages per thread: 10")
    print(f"Total messages: {response_count[0]}")
    print(f"Chat history length: {len(agent.chat_history)}")
    print(f"Errors: {len(errors)}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Status: {'PASS' if len(errors) == 0 else 'FAIL'}")


def example_agent_locks():
    """Verify Agent class has proper locks."""
    print("\n" + "=" * 60)
    print("Example 2: Agent Lock Verification")
    print("=" * 60)
    
    from praisonaiagents import Agent
    
    agent = Agent(
        name="LockTestAgent",
        instructions="Test agent",
        output="silent"
    )
    
    # Check for locks
    has_history_lock = hasattr(agent, '_history_lock')
    has_cache_lock = hasattr(agent, '_cache_lock')
    
    print(f"Has _history_lock: {has_history_lock}")
    print(f"Has _cache_lock: {has_cache_lock}")
    
    # Verify lock types
    if has_history_lock:
        lock_type = type(agent._history_lock).__name__
        print(f"_history_lock type: {lock_type}")
    
    if has_cache_lock:
        lock_type = type(agent._cache_lock).__name__
        print(f"_cache_lock type: {lock_type}")
    
    print(f"Status: {'PASS' if has_history_lock and has_cache_lock else 'FAIL'}")


def example_concurrent_real_api():
    """Demonstrate concurrent API calls (requires API key)."""
    print("\n" + "=" * 60)
    print("Example 3: Concurrent Real API Calls")
    print("=" * 60)
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Skipping: OPENAI_API_KEY not set")
        return
    
    from praisonaiagents import Agent
    
    agent = Agent(
        name="ConcurrentAgent",
        instructions="Reply with one word only.",
        llm="gpt-4o-mini",
        output="silent"
    )
    
    results = []
    results_lock = threading.Lock()
    errors = []
    
    def worker(thread_id):
        try:
            response = agent.chat(f"Say hello {thread_id}")
            with results_lock:
                results.append((thread_id, response))
        except Exception as e:
            errors.append(e)
    
    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(3)
    ]
    
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start
    
    print(f"Concurrent requests: 3")
    print(f"Successful responses: {len(results)}")
    print(f"Errors: {len(errors)}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Status: {'PASS' if len(errors) == 0 else 'FAIL'}")


if __name__ == "__main__":
    print("PraisonAI Agents - Thread Safety Examples")
    print("=" * 60)
    
    example_lite_agent_thread_safety()
    example_agent_locks()
    example_concurrent_real_api()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
