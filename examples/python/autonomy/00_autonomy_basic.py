"""
Basic Agent Autonomy Example.

This example demonstrates the core autonomy features with a real API call.
Run with: python 00_autonomy_basic.py

Requirements:
- OPENAI_API_KEY environment variable set
"""

from praisonaiagents import Agent

def main():
    # Create an agent with autonomy enabled
    agent = Agent(
        instructions="You are a helpful assistant. Be concise.",
        autonomy=True,
    )
    
    print("=" * 50)
    print("Agent Autonomy Basic Example")
    print("=" * 50)
    
    # Test 1: Signal detection (no API call)
    print("\n1. Signal Detection (fast, no API call):")
    prompts = [
        "What is Python?",
        "Read src/main.py and explain it",
        "Refactor the auth module and add tests",
    ]
    
    for prompt in prompts:
        stage = agent.get_recommended_stage(prompt)
        print(f"   '{prompt[:40]}...' → {stage}")
    
    # Test 2: Simple chat with autonomy (real API call)
    print("\n2. Simple Chat (real API call):")
    response = agent.chat("What is 2 + 2? Answer with just the number.")
    print(f"   Response: {response}")
    
    # Test 3: Check autonomy status
    print("\n3. Autonomy Status:")
    print(f"   Enabled: {agent.autonomy_enabled}")
    print(f"   Config: {agent.autonomy_config}")
    
    print("\n" + "=" * 50)
    print("✓ Basic autonomy example completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
