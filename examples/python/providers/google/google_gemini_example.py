"""
Basic example of using Google Gemini with PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with Google Gemini
    praison = PraisonAI(
        model="gemini-1.5-pro",
        provider="google",
        api_key="your-google-api-key-here"  # Replace with your actual Google API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="Google Gemini Agent",
        description="A basic agent using Google Gemini model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a research task?")
    print("Agent Response:", response)
    
    # Example with research and analysis
    research_task = """
    Research and provide insights on the latest developments in 
    renewable energy technology, focusing on solar and wind power innovations.
    """
    
    response = agent.run(research_task)
    print("\nResearch Task Response:")
    print(response)
    
    # Example with multimodal capabilities (text-based for now)
    multimodal_task = """
    Describe how you would analyze an image of a city skyline 
    and provide insights about urban development patterns.
    """
    
    response = agent.run(multimodal_task)
    print("\nMultimodal Analysis Response:")
    print(response)

if __name__ == "__main__":
    main() 