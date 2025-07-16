"""
Basic example of using OpenAI GPT-4 with PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with OpenAI GPT-4
    praison = PraisonAI(
        model="gpt-4o",
        provider="openai",
        api_key="your-openai-api-key-here"  # Replace with your actual OpenAI API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="OpenAI GPT-4 Agent",
        description="A basic agent using OpenAI GPT-4 model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a coding task?")
    print("Agent Response:", response)
    
    # Example with code generation
    coding_task = """
    Write a Python function that implements a binary search algorithm.
    Include proper documentation and error handling.
    """
    
    response = agent.run(coding_task)
    print("\nCoding Task Response:")
    print(response)
    
    # Example with analysis
    analysis_task = """
    Analyze the pros and cons of using microservices architecture 
    for a large-scale e-commerce application.
    """
    
    response = agent.run(analysis_task)
    print("\nAnalysis Task Response:")
    print(response)

if __name__ == "__main__":
    main() 