"""
Basic example of using Mistral with PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with Mistral
    praison = PraisonAI(
        model="mistral-large-latest",
        provider="mistral",
        api_key="your-mistral-api-key-here"  # Replace with your actual Mistral API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="Mistral Agent",
        description="A basic agent using Mistral model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a language translation task?")
    print("Agent Response:", response)
    
    # Example with language translation
    translation_task = """
    Translate the following text to French and explain any cultural nuances:
    "The early bird catches the worm, but the second mouse gets the cheese."
    """
    
    response = agent.run(translation_task)
    print("\nTranslation Task Response:")
    print(response)
    
    # Example with creative content generation
    creative_task = """
    Write a haiku about artificial intelligence and its impact on society.
    Then explain the symbolism in your haiku.
    """
    
    response = agent.run(creative_task)
    print("\nCreative Content Response:")
    print(response)

if __name__ == "__main__":
    main() 