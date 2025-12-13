from praisonaiagents import Agent
import os

# Set OpenAI API key if not already set
if not os.getenv("OPENAI_API_KEY"):
    print("Please set your OpenAI API key: export OPENAI_API_KEY='your-api-key-here'")
    exit(1)

# Create the RAG agent with web search capabilities
rag_agent = Agent(
    instructions="""You are a helpful AI assistant specialized in Thai recipes and cooking.

    You have access to a PDF knowledge base about Thai recipes from: https://phi-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf
    
    You can also search the web for additional information about Thai cooking, ingredients, and techniques.
    
    When answering questions:
    1. Use your knowledge about Thai cuisine to provide helpful information
    2. If needed, search the web for additional details, current information, or clarification
    3. Provide comprehensive, helpful answers about Thai cuisine
    4. Always be informative and helpful about Thai cooking!
    
    You can use the internet_search function to search the web when needed.""",
    llm="gpt-4o",
    markdown=True,
    verbose=True
)

if __name__ == "__main__":
    print("🤖 Thai Recipe RAG Agent is ready!")
    print("Ask me anything about Thai recipes or cooking!")
    print("Type 'quit' to exit.\n")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("👋 Goodbye! Happy cooking!")
            break
        
        try:
            response = rag_agent.start(user_input)
            print(f"\n🤖 Assistant: {response}\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")