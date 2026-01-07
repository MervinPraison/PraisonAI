"""
RAG PDF Q&A Example

This example demonstrates how to use RAG to answer questions
about PDF documents with citations.

Usage:
    python rag_pdf_qa.py

Requirements:
    pip install praisonaiagents[knowledge]
"""

from praisonaiagents import Agent, Knowledge
from praisonaiagents.rag import RAG, RAGConfig


def main():
    # Method 1: Simple Agent with Knowledge
    print("=" * 60)
    print("Method 1: Agent with Knowledge Parameter")
    print("=" * 60)
    
    agent = Agent(
        name="PDF Assistant",
        instructions="You are a helpful assistant that answers questions about documents.",
        knowledge=["sample.pdf"],  # Add your PDF files here
    )
    
    response = agent.start("What are the main topics covered in this document?")
    print(f"\nAnswer: {response}\n")
    
    # Method 2: Explicit RAG Pipeline with Citations
    print("=" * 60)
    print("Method 2: Explicit RAG Pipeline with Citations")
    print("=" * 60)
    
    # Create knowledge base
    knowledge = Knowledge()
    knowledge.add("sample.pdf")  # Add your PDF
    
    # Configure RAG
    config = RAGConfig(
        top_k=5,
        min_score=0.3,
        include_citations=True,
        max_context_tokens=4000,
    )
    
    # Create RAG pipeline
    rag = RAG(knowledge=knowledge, config=config)
    
    # Query with citations
    result = rag.query("What methodology was used in this research?")
    
    print(f"\nAnswer: {result.answer}")
    print(f"\nSources ({len(result.citations)}):")
    for citation in result.citations:
        print(f"  [{citation.id}] {citation.source} (score: {citation.score:.2f})")
        print(f"      {citation.text[:100]}...")
    
    # Method 3: Streaming Response
    print("\n" + "=" * 60)
    print("Method 3: Streaming Response")
    print("=" * 60)
    
    print("\nStreaming answer: ", end="")
    for chunk in rag.stream("Summarize the key findings"):
        print(chunk, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    main()
