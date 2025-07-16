"""
Basic example of using xAI Grok with PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with xAI Grok
    praison = PraisonAI(
        model="grok-beta",
        provider="xai",
        api_key="your-xai-api-key-here"  # Replace with your actual xAI API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="xAI Grok Agent",
        description="A basic agent using xAI Grok model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a complex reasoning task?")
    print("Agent Response:", response)
    
    # Example with complex reasoning
    reasoning_task = """
    Analyze this scenario step by step:
    A company has 100 employees, 60% work remotely, 30% work hybrid, and 10% work in-office.
    They want to implement a new AI tool that requires high-speed internet.
    What are the challenges and solutions for this implementation?
    """
    
    response = agent.run(reasoning_task)
    print("\nComplex Reasoning Response:")
    print(response)
    
    # Example with creative problem solving
    creative_task = """
    Design a solution for reducing food waste in urban areas using AI technology.
    Consider economic, environmental, and social factors.
    Provide a step-by-step implementation plan.
    """
    
    response = agent.run(creative_task)
    print("\nCreative Problem Solving Response:")
    print(response)
    
    # Example with humor and personality (Grok's specialty)
    humor_task = """
    Explain quantum physics using analogies that would make a 10-year-old laugh,
    while still being scientifically accurate.
    """
    
    response = agent.run(humor_task)
    print("\nHumor and Education Response:")
    print(response)

if __name__ == "__main__":
    main() 