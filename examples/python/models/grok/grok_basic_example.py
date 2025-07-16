"""
Basic example of using Grok model in PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with Grok model
    praison = PraisonAI(
        model="grok",
        api_key="your-grok-api-key-here"  # Replace with your actual Grok API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="Grok Agent",
        description="A basic agent using Grok model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you explain quantum computing in simple terms?")
    print("Agent Response:", response)
    
    # Example with mathematical reasoning
    math_task = """
    Solve this problem step by step:
    If a train travels at 60 mph for 2.5 hours, how far does it travel?
    """
    
    response = agent.run(math_task)
    print("\nMath Task Response:")
    print(response)
    
    # Example with creative writing
    creative_task = """
    Write a short story about a robot learning to paint.
    Make it engaging and about 100 words.
    """
    
    response = agent.run(creative_task)
    print("\nCreative Task Response:")
    print(response)

if __name__ == "__main__":
    main() 