#!/usr/bin/env python3
"""
Example: Using PraisonAI Agents Lite Package

The lite package provides a minimal agent framework without heavy dependencies
like litellm. It's ideal for users who want to bring their own LLM client.

This example shows:
1. Creating a LiteAgent with a custom LLM function
2. Using the built-in OpenAI adapter
3. Thread-safe chat history management
"""
import os


def example_custom_llm():
    """Example 1: Using a custom LLM function."""
    from praisonaiagents.lite import LiteAgent
    
    # Define your own LLM function
    def my_simple_llm(messages):
        """A mock LLM that echoes back the last message."""
        last_msg = messages[-1]["content"] if messages else "No message"
        return f"Echo: {last_msg}"
    
    agent = LiteAgent(
        name="EchoAgent",
        llm_fn=my_simple_llm,
        instructions="You are a simple echo agent."
    )
    
    response = agent.chat("Hello, world!")
    print(f"Response: {response}")
    print(f"Chat history length: {len(agent.chat_history)}")


def example_openai_adapter():
    """Example 2: Using the built-in OpenAI adapter."""
    from praisonaiagents.lite import LiteAgent, create_openai_llm_fn
    
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Skipping OpenAI example - OPENAI_API_KEY not set")
        return
    
    # Create LLM function using OpenAI SDK directly (no litellm)
    llm_fn = create_openai_llm_fn(model="gpt-4o-mini")
    
    agent = LiteAgent(
        name="OpenAIAgent",
        llm_fn=llm_fn,
        instructions="You are a helpful assistant. Keep responses brief."
    )
    
    response = agent.chat("What is 2+2?")
    print(f"OpenAI Response: {response}")


def example_with_tools():
    """Example 3: Using tools with LiteAgent."""
    from praisonaiagents.lite import LiteAgent, tool
    
    @tool
    def add_numbers(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b
    
    def mock_llm(messages):
        return "The sum is 8"
    
    agent = LiteAgent(
        name="MathAgent",
        llm_fn=mock_llm,
        tools=[add_numbers]
    )
    
    # Execute tool directly
    result = agent.execute_tool("add_numbers", a=5, b=3)
    print(f"Tool result: {result.output}")
    print(f"Tool success: {result.success}")


def example_anthropic_adapter():
    """Example 4: Using the built-in Anthropic adapter."""
    from praisonaiagents.lite import LiteAgent, create_anthropic_llm_fn
    
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Skipping Anthropic example - ANTHROPIC_API_KEY not set")
        return
    
    # Create LLM function using Anthropic SDK directly
    llm_fn = create_anthropic_llm_fn(model="claude-3-5-sonnet-20241022")
    
    agent = LiteAgent(
        name="ClaudeAgent",
        llm_fn=llm_fn,
        instructions="You are a helpful assistant. Keep responses brief."
    )
    
    response = agent.chat("What is the capital of France?")
    print(f"Claude Response: {response}")


if __name__ == "__main__":
    print("=" * 60)
    print("PraisonAI Agents Lite Examples")
    print("=" * 60)
    
    print("\n[1] Custom LLM Function:")
    example_custom_llm()
    
    print("\n[2] OpenAI Adapter:")
    example_openai_adapter()
    
    print("\n[3] Tools with LiteAgent:")
    example_with_tools()
    
    print("\n[4] Anthropic Adapter:")
    example_anthropic_adapter()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
