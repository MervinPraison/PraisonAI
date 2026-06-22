#!/usr/bin/env python3
"""
Message Steering Example

Demonstrates real-time message steering for agents during execution.
Shows how to send guidance messages to agents while they're running tasks.

Usage:
    # Python API
    python message_steering_example.py
    
    # CLI with steering enabled
    praisonai --message-steering "Write a detailed report about AI trends" 
    
    # YAML (add message_steering: true to agent config)
"""

import asyncio
import threading
import time
from praisonaiagents import Agent


def basic_message_steering():
    """Basic message steering example - enable steering and send guidance."""
    print("🎯 Basic Message Steering Example")
    print("=" * 50)
    
    # Create agent with message steering enabled
    agent = Agent(
        name="researcher", 
        instructions="You are a helpful research assistant",
        message_steering=True,  # Enable real-time message steering
        llm="gpt-4o-mini"
    )
    
    print("✅ Agent created with message steering enabled")
    print(f"📊 Steering status: {agent.get_steering_status()}")
    
    # Send some guidance
    msg_id_1 = agent.steer("Focus on recent developments from 2024")
    msg_id_2 = agent.steer("Keep response under 200 words", priority=10)
    
    print(f"📨 Sent steering messages: {msg_id_1}, {msg_id_2}")
    print(f"📊 Steering status: {agent.get_steering_status()}")
    
    # Execute task - steering will be automatically injected
    result = agent.start("Summarize the latest AI trends")
    
    print("\n📝 Result:")
    print(result)


def threaded_message_steering():
    """Advanced example - send steering messages while agent is running."""
    print("\n🚀 Threaded Message Steering Example")
    print("=" * 50)
    
    agent = Agent(
        name="writer",
        instructions="You are a content writer", 
        message_steering=True,
        llm="gpt-4o-mini"
    )
    
    result_holder = [None]
    
    def run_agent():
        """Run agent in background thread."""
        result = agent.start("Write a comprehensive article about quantum computing")
        result_holder[0] = result
    
    # Start agent in background
    thread = threading.Thread(target=run_agent)
    thread.start()
    
    # Send steering messages while it's running
    time.sleep(0.5)  # Let execution start
    agent.steer("Make it accessible to beginners")
    
    time.sleep(1.0) 
    agent.steer("Include practical applications", priority=15)
    
    time.sleep(1.5)
    agent.steer("Keep it under 300 words total", priority=20)
    
    # Wait for completion
    thread.join(timeout=60)
    
    if result_holder[0]:
        print("\n📝 Final Result:")
        print(result_holder[0])
    else:
        print("⚠️ Agent execution timed out")


async def async_message_steering():
    """Async example showing message steering with async execution."""
    print("\n⚡ Async Message Steering Example")
    print("=" * 50)
    
    agent = Agent(
        name="analyst",
        instructions="You are a data analyst",
        message_steering=True,
        llm="gpt-4o-mini"
    )
    
    # Start async task
    async def run_analysis():
        return await agent.astart("Analyze the impact of AI on job markets")
    
    # Create task
    task = asyncio.create_task(run_analysis())
    
    # Send steering while running
    await asyncio.sleep(0.3)
    agent.steer("Focus on positive opportunities")
    
    await asyncio.sleep(0.7)  
    agent.steer("Include specific examples", priority=12)
    
    # Wait for result
    result = await task
    
    print("\n📝 Analysis Result:")
    print(result)


def cli_yaml_examples():
    """Show CLI and YAML usage examples."""
    print("\n💻 CLI & YAML Examples")
    print("=" * 50)
    
    print("🔧 CLI Usage:")
    print("  praisonai --message-steering 'Your task here'")
    print("  # Then in another terminal:")
    print("  # agent.steer('Additional guidance')")
    
    print("\n📄 YAML Configuration:")
    yaml_example = """
# agents.yaml
framework: praisonai
roles:
  researcher:
    role: Research Assistant
    goal: Conduct thorough research
    backstory: Expert researcher with steering support
    message_steering: true    # Enable steering for this agent
    tools:
      - internet_search
      - write_file
    tasks:
      research_task:
        description: Research AI trends and write report
        expected_output: Comprehensive research report
"""
    print(yaml_example.strip())


if __name__ == "__main__":
    # Run examples
    basic_message_steering()
    threaded_message_steering() 
    
    # Run async example
    asyncio.run(async_message_steering())
    
    # Show CLI/YAML usage
    cli_yaml_examples()
    
    print("\n✨ Message steering examples completed!")
    print("📚 See docs for more advanced patterns and priority levels")