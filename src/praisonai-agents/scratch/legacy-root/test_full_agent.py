"""Test full agent flow with new verbose UI."""
from praisonaiagents import Agent

# Create agent - use output preset for verbose mode
agent = Agent(
    name="AIAssistant",
    role="Helpful AI",
    instructions="You are a helpful assistant. Be concise and give short answers.",
    output="verbose",  # Use output preset instead of verbose kwarg
)

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TESTING FULL AGENT FLOW WITH NEW UI")
    print("=" * 60 + "\n")
    
    # Use start() which should show verbose output
    result = agent.start("What is the capital of France? One sentence only.")
    
    print("\n" + "=" * 60)
    print(f"FINAL RESULT: {result}")
    print("=" * 60)
