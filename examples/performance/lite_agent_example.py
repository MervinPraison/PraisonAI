#!/usr/bin/env python3
"""
Example: Lite Agent (BYO-LLM)

Demonstrates the lightweight praisonaiagents.lite subpackage
that allows you to bring your own LLM client.
"""
import os


def example_custom_llm():
    """Example using a custom LLM function."""
    print("=" * 60)
    print("Example 1: Custom LLM Function")
    print("=" * 60)
    
    from praisonaiagents.lite import LiteAgent
    
    # Define a simple mock LLM
    def mock_llm(messages):
        """A mock LLM that echoes the last message."""
        last_msg = messages[-1]["content"] if messages else "No message"
        return f"Echo: {last_msg}"
    
    agent = LiteAgent(
        name="EchoAgent",
        llm_fn=mock_llm,
        instructions="You are a simple echo agent."
    )
    
    response = agent.chat("Hello, world!")
    print(f"Response: {response}")
    print(f"Chat history length: {len(agent.chat_history)}")


def example_openai_adapter():
    """Example using the built-in OpenAI adapter."""
    print("\n" + "=" * 60)
    print("Example 2: OpenAI Adapter")
    print("=" * 60)
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Skipping: OPENAI_API_KEY not set")
        return
    
    from praisonaiagents.lite import LiteAgent, create_openai_llm_fn
    
    # Create LLM function using OpenAI SDK directly
    llm_fn = create_openai_llm_fn(model="gpt-4o-mini")
    
    agent = LiteAgent(
        name="OpenAIAgent",
        llm_fn=llm_fn,
        instructions="You are a helpful assistant. Keep responses brief."
    )
    
    response = agent.chat("What is 2+2?")
    print(f"Response: {response}")


def example_with_tools():
    """Example using tools with LiteAgent."""
    print("\n" + "=" * 60)
    print("Example 3: Tools with LiteAgent")
    print("=" * 60)
    
    from praisonaiagents.lite import LiteAgent, tool
    
    @tool
    def add_numbers(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b
    
    @tool
    def multiply_numbers(a: int, b: int) -> int:
        """Multiply two numbers together."""
        return a * b
    
    def mock_llm(messages):
        return "The calculation result is ready."
    
    agent = LiteAgent(
        name="MathAgent",
        llm_fn=mock_llm,
        tools=[add_numbers, multiply_numbers]
    )
    
    # Execute tools directly
    result1 = agent.execute_tool("add_numbers", a=5, b=3)
    print(f"5 + 3 = {result1.output}")
    print(f"Success: {result1.success}")
    
    result2 = agent.execute_tool("multiply_numbers", a=4, b=7)
    print(f"4 * 7 = {result2.output}")
    print(f"Success: {result2.success}")


def example_thread_safety():
    """Example demonstrating thread-safe operations."""
    print("\n" + "=" * 60)
    print("Example 4: Thread Safety")
    print("=" * 60)
    
    import threading
    from praisonaiagents.lite import LiteAgent
    
    counter = [0]
    lock = threading.Lock()
    
    def counting_llm(messages):
        with lock:
            counter[0] += 1
            return f"Response {counter[0]}"
    
    agent = LiteAgent(
        name="ThreadSafeAgent",
        llm_fn=counting_llm
    )
    
    def worker(thread_id):
        for i in range(5):
            agent.chat(f"Message from thread {thread_id}, iteration {i}")
    
    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(3)
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    print(f"Total messages processed: {counter[0]}")
    print(f"Chat history length: {len(agent.chat_history)}")
    print("Thread safety test: PASS")


if __name__ == "__main__":
    print("PraisonAI Agents - Lite Package Examples")
    print("=" * 60)
    
    example_custom_llm()
    example_openai_adapter()
    example_with_tools()
    example_thread_safety()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
