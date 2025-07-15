#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Sample document for chunking demonstration
SAMPLE_DOCUMENT = """Artificial Intelligence (AI) is a transformative technology that is reshaping industries worldwide. 
Machine learning, a subset of AI, enables computers to learn from data without explicit programming. 
Deep learning uses neural networks to process complex patterns in data. Natural language processing 
allows computers to understand and generate human language. Computer vision enables machines to 
interpret visual information. These technologies are being applied in healthcare, finance, 
transportation, and many other sectors."""

# Create agent for document chunking
chunking_agent = Agent(
    name="Document Processor",
    role="Document Chunking Specialist",
    goal="Process and chunk documents for optimal knowledge retrieval",
    backstory="You are an expert in document processing who can break down large documents into meaningful chunks for better processing and retrieval.",
    llm="gpt-4o-mini"
)

# Create task for document chunking
chunk_task = Task(
    name="chunk_document",
    description=f"""
    Process this sample document and demonstrate different chunking strategies:
    
    SAMPLE DOCUMENT:
    "{SAMPLE_DOCUMENT}"
    
    Apply these chunking strategies:
    1. Token-based chunking (split by words/tokens)
    2. Sentence-based chunking (split by sentences)
    3. Semantic chunking (split by meaning)
    4. Fixed-size chunking (split by character count)
    """,
    expected_output="Demonstration of different chunking strategies with examples and explanations of when to use each method",
    agent=chunking_agent
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[chunking_agent],
    tasks=[chunk_task],
    process="sequential",
    verbose=True
)

# Run the document chunking workflow
if __name__ == "__main__":
    print("📄 Document Chunking Example")
    print("This example shows different strategies for chunking documents for better processing")
    print("=" * 80)
    
    # Show sample document
    print("\n📝 Sample Document:")
    print(f"Length: {len(SAMPLE_DOCUMENT)} characters")
    print(f"Word count: {len(SAMPLE_DOCUMENT.split())} words")
    print(f"Sentence count: {len([s for s in SAMPLE_DOCUMENT.split('.') if s.strip()])}")
    
    # Demonstrate simple chunking strategies
    print("\n🔪 Simple Chunking Examples:")
    
    # Token-based chunking (by words)
    words = SAMPLE_DOCUMENT.split()
    token_chunks = [' '.join(words[i:i+10]) for i in range(0, len(words), 10)]
    print(f"\n1. Token-based chunks (10 words each): {len(token_chunks)} chunks")
    for i, chunk in enumerate(token_chunks[:2]):
        print(f"   Chunk {i+1}: {chunk}...")
    
    # Sentence-based chunking
    sentences = [s.strip() for s in SAMPLE_DOCUMENT.split('. ') if s.strip()]
    print(f"\n2. Sentence-based chunks: {len(sentences)} chunks")
    for i, sentence in enumerate(sentences[:2]):
        print(f"   Sentence {i+1}: {sentence}...")
    
    # Fixed-size chunking
    chunk_size = 100
    char_chunks = [SAMPLE_DOCUMENT[i:i+chunk_size] for i in range(0, len(SAMPLE_DOCUMENT), chunk_size)]
    print(f"\n3. Fixed-size chunks ({chunk_size} chars): {len(char_chunks)} chunks")
    for i, chunk in enumerate(char_chunks[:2]):
        print(f"   Chunk {i+1}: {chunk}...")
    
    # Run the agent for advanced chunking analysis
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ Document Chunking Complete")
    print("💡 Choose chunking strategy based on your use case:")
    print("   • Token-based: Good for language models with token limits")
    print("   • Sentence-based: Preserves semantic meaning")
    print("   • Fixed-size: Predictable chunk sizes")
    print("   • Semantic: Best for maintaining context and meaning")
