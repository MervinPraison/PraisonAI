"""
Chat with PDF Example

This example demonstrates how to create an agent that can read and answer questions about PDF documents.
It uses the knowledge parameter to load PDF files and provides interactive Q&A capabilities.
"""

from praisonaiagents import Agent

# Configure vector store for PDF storage
config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "pdf_chat",
            "path": ".praison_pdf_chat",
        }
    }
}

# Create a PDF chat agent
pdf_agent = Agent(
    name="PDF Assistant",
    role="PDF document expert",
    goal="Help users understand and extract information from PDF documents",
    backstory="You are an expert at reading, analyzing, and answering questions about PDF documents. You provide accurate, detailed answers based on the document content.",
    instructions="Read the provided PDF document and answer questions about its content. Be specific and cite relevant sections when possible.",
    knowledge=["document.pdf"],  # Replace with your PDF file path
    knowledge_config=config,
    self_reflect=True,
    min_reflect=1,
    max_reflect=3
)

# Example usage
if __name__ == "__main__":
    # Single question
    response = pdf_agent.start("What are the main topics covered in this document?")
    print(response)
    
    # Interactive chat
    print("\nPDF Chat Assistant Ready! Type 'quit' to exit.")
    while True:
        question = input("\nYour question: ")
        if question.lower() == 'quit':
            break
        
        response = pdf_agent.start(question)
        print(f"\nAnswer: {response}")