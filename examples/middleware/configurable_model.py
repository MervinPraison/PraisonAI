"""
Configurable Model Example - PraisonAI Agents

Demonstrates runtime model switching without recreating the agent.
"""

from praisonaiagents import Agent

# Create agent with configurable model enabled
agent = Agent(
    name="FlexBot",
    instructions="You are a helpful assistant.",
    llm="gpt-4o-mini",
    llm_config={"configurable": True}
)

if __name__ == "__main__":
    # Default model call
    print("Using default model (gpt-4o-mini)...")
    # response = agent.chat("Say hello in 5 words")
    
    # Override model per-call
    print("\nOverriding to different model...")
    # response = agent.chat("Say hello in 5 words", config={"model": "gpt-4o"})
    
    # Override temperature
    print("\nOverriding temperature...")
    # response = agent.chat("Say hello creatively", config={"temperature": 0.9})
    
    print("\n✓ Configurable model example complete")
    print("Note: Uncomment agent.chat() calls to run with API key")
