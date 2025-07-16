"""
Basic example of using Anthropic Claude with PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with Anthropic Claude
    praison = PraisonAI(
        model="claude-3-5-sonnet-20241022",
        provider="anthropic",
        api_key="your-anthropic-api-key-here"  # Replace with your actual Anthropic API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="Anthropic Claude Agent",
        description="A basic agent using Anthropic Claude model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a writing task?")
    print("Agent Response:", response)
    
    # Example with creative writing
    writing_task = """
    Write a short story about a time traveler who discovers 
    they can only travel to moments of great historical significance.
    Make it engaging and about 200 words.
    """
    
    response = agent.run(writing_task)
    print("\nCreative Writing Response:")
    print(response)
    
    # Example with reasoning
    reasoning_task = """
    Explain the concept of quantum entanglement in simple terms,
    and then discuss its potential applications in quantum computing.
    """
    
    response = agent.run(reasoning_task)
    print("\nReasoning Task Response:")
    print(response)

if __name__ == "__main__":
    main() 