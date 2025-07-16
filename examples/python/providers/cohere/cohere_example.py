"""
Basic example of using Cohere with PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with Cohere
    praison = PraisonAI(
        model="command-r-plus",
        provider="cohere",
        api_key="your-cohere-api-key-here"  # Replace with your actual Cohere API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="Cohere Agent",
        description="A basic agent using Cohere model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a business analysis task?")
    print("Agent Response:", response)
    
    # Example with business analysis
    business_task = """
    Analyze the potential market opportunities for a new AI-powered 
    productivity tool targeting remote workers. Include market size, 
    competitive landscape, and go-to-market strategy recommendations.
    """
    
    response = agent.run(business_task)
    print("\nBusiness Analysis Response:")
    print(response)
    
    # Example with document summarization
    summary_task = """
    Summarize the key points from this business proposal:
    
    Our company proposes to develop an AI-powered customer service chatbot
    that can handle 80% of common customer inquiries automatically. The system
    will integrate with existing CRM platforms and provide 24/7 support.
    Expected ROI is 300% within the first year, with implementation taking
    6 months and requiring a team of 5 developers.
    """
    
    response = agent.run(summary_task)
    print("\nDocument Summarization Response:")
    print(response)

if __name__ == "__main__":
    main() 