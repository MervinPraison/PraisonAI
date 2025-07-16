"""
Basic example of using Kimi model with Groq provider in PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with Kimi model using Groq provider
    praison = PraisonAI(
        model="kimi",
        provider="groq",
        api_key="your-groq-api-key-here"  # Replace with your actual Groq API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="Kimi Groq Agent",
        description="A basic agent using Kimi model with Groq provider"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a coding task?")
    print("Agent Response:", response)
    
    # Example with more complex task
    coding_task = """
    Write a Python function that calculates the factorial of a number.
    Include error handling and documentation.
    """
    
    response = agent.run(coding_task)
    print("\nCoding Task Response:")
    print(response)

if __name__ == "__main__":
    main() 