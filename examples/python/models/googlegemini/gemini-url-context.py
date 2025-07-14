"""
Gemini URL Context Tool Example

This example demonstrates how to use Gemini's built-in URL Context functionality
through PraisonAI. The URL Context tool allows the model to fetch and analyze
content from specific URLs in real-time.

Prerequisites:
- Set GEMINI_API_KEY environment variable
- Use a Gemini model that supports internal tools (gemini-2.0-flash, etc.)

Features:
- Real-time URL content fetching
- Automatic content analysis and summarization
- Support for various web content types
- Access to URL metadata through response.model_extra
"""

import os
from praisonaiagents import Agent

# Ensure you have your Gemini API key set
# os.environ["GEMINI_API_KEY"] = "your-api-key-here"

def main():
    # Create agent with URL Context internal tool
    agent = Agent(
        instructions="""You are a content analyst that can fetch and analyze web content.
        Use the URL Context tool to access and analyze content from provided URLs.
        Provide detailed summaries, extract key information, and answer questions about the content.""",
        
        llm="gemini/gemini-2.0-flash",
        
        # Enable URL Context internal tool
        tools=[{"urlContext": {}}],
        
        verbose=True
    )
    
    # Example URLs for analysis
    url_tasks = [
        {
            "url": "https://ai.google.dev/gemini-api/docs/models",
            "task": "Summarize the key information about Gemini models and their capabilities"
        },
        {
            "url": "https://github.com/MervinPraison/PraisonAI",
            "task": "Analyze this GitHub repository and explain what PraisonAI does"
        },
        {
            "url": "https://docs.python.org/3/tutorial/introduction.html",
            "task": "Extract the main learning objectives from this Python tutorial"
        },
        {
            "url": "https://arxiv.org/abs/2301.00234",
            "task": "Provide a summary of this research paper's abstract and key contributions"
        }
    ]
    
    print("=== Gemini URL Context Tool Demo ===\n")
    
    for i, item in enumerate(url_tasks, 1):
        print(f"Analysis {i}: {item['url']}")
        print(f"Task: {item['task']}")
        print("-" * 50)
        
        # Combine URL and task in the query
        query = f"{item['task']}: {item['url']}"
        
        try:
            response = agent.start(query)
            print(f"Analysis: {response}")
            
            # Note: URL metadata access requires direct LiteLLM response
            # In PraisonAI, this would need to be accessed through the LLM response
            print(f"\nAnalyzed URL: {item['url']}")
            print("\n" + "="*80 + "\n")
            
        except Exception as e:
            print(f"Error: {e}")
            print("\n" + "="*80 + "\n")

def demonstrate_direct_usage():
    """
    Example of how the URL Context tool works at the LiteLLM level
    (for reference - this requires direct LiteLLM usage)
    """
    print("=== Direct LiteLLM URL Context Usage (Reference) ===")
    print("""
    # This is how it works at the LiteLLM level:
    
    import litellm
    import os
    
    os.environ["GEMINI_API_KEY"] = "your-api-key"
    
    response = litellm.completion(
        model="gemini/gemini-2.0-flash",
        messages=[{
            "role": "user", 
            "content": "Summarize this document: https://ai.google.dev/gemini-api/docs/models"
        }],
        tools=[{"urlContext": {}}],
    )
    
    # Access URL metadata
    if hasattr(response, 'model_extra') and 'vertex_ai_url_context_metadata' in response.model_extra:
        url_context_metadata = response.model_extra['vertex_ai_url_context_metadata']
        urlMetadata = url_context_metadata[0]['urlMetadata'][0]
        print(f"Retrieved URL: {urlMetadata['retrievedUrl']}")
        print(f"Retrieval Status: {urlMetadata['urlRetrievalStatus']}")
    """)

if __name__ == "__main__":
    main()
    demonstrate_direct_usage()