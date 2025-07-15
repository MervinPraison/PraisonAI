#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Sample document for chunking demonstration
SAMPLE_DOCUMENT = """Artificial Intelligence (AI) is a transformative technology that is reshaping industries worldwide. Machine learning, a subset of AI, enables computers to learn from data without explicit programming. Deep learning uses neural networks to process complex patterns in data. Natural language processing allows computers to understand and generate human language. Computer vision enables machines to interpret visual information. These technologies are being applied in healthcare, finance, transportation, and many other sectors."""

# Create agent for document chunking
chunking_agent = Agent(
    name="Document Processor",
    role="Document Chunking Specialist",
    goal="Process and chunk documents using real chunking strategies for optimal knowledge retrieval",
    backstory="You are an expert in document processing who can break down large documents into meaningful chunks for better processing and retrieval using various chunking strategies.",
    llm="gpt-4o-mini"
)

# Create task for document chunking
chunk_task = Task(
    name="chunk_document",
    description=f"""
    Process this sample document and demonstrate different chunking strategies:
    
    SAMPLE DOCUMENT:
    "{SAMPLE_DOCUMENT}"
    
    Analyze the chunking results and provide recommendations for:
    1. Token-based chunking (best for language models with token limits)
    2. Sentence-based chunking (preserves semantic meaning)
    3. Recursive chunking (balanced approach)
    4. Fixed-size chunking (predictable chunk sizes)
    """,
    expected_output="Analysis of different chunking strategies with recommendations for when to use each method",
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
    
    # Fix sentence counting logic to handle proper sentence splitting
    sentences = [s.strip() for s in SAMPLE_DOCUMENT.split('. ') if s.strip()]
    # Add the last sentence if it doesn't end with '. '
    if not SAMPLE_DOCUMENT.endswith('. '):
        last_part = SAMPLE_DOCUMENT.split('. ')[-1].strip()
        if last_part and last_part not in sentences:
            sentences.append(last_part)
    print(f"Sentence count: {len(sentences)}")
    
    # Demonstrate real chunking strategies using the Knowledge system
    print("\n🔪 Real Chunking Examples using Knowledge System:")
    
    try:
        from praisonaiagents.knowledge import Chunking
        
        # Token-based chunking
        token_chunker = Chunking(chunker_type='token', chunk_size=50, chunk_overlap=10)
        token_chunks = token_chunker.chunk(SAMPLE_DOCUMENT)
        print(f"\n1. Token-based chunks (50 tokens, 10 overlap): {len(token_chunks)} chunks")
        for i, chunk in enumerate(token_chunks[:2]):
            print(f"   Chunk {i+1}: {chunk[:80]}...")
        
        # Sentence-based chunking
        sentence_chunker = Chunking(chunker_type='sentence', chunk_size=200, chunk_overlap=20)
        sentence_chunks = sentence_chunker.chunk(SAMPLE_DOCUMENT)
        print(f"\n2. Sentence-based chunks (200 tokens, 20 overlap): {len(sentence_chunks)} chunks")
        for i, chunk in enumerate(sentence_chunks[:2]):
            print(f"   Chunk {i+1}: {chunk[:80]}...")
        
        # Recursive chunking
        recursive_chunker = Chunking(chunker_type='recursive', chunk_size=150)
        recursive_chunks = recursive_chunker.chunk(SAMPLE_DOCUMENT)
        print(f"\n3. Recursive chunks (150 tokens): {len(recursive_chunks)} chunks")
        for i, chunk in enumerate(recursive_chunks[:2]):
            print(f"   Chunk {i+1}: {chunk[:80]}...")
        
    except Exception as e:
        print(f"\n⚠️  Real chunking unavailable: {e}")
        print("Falling back to simple chunking methods...")
        
        # Simple fallback chunking
        words = SAMPLE_DOCUMENT.split()
        token_chunks = [' '.join(words[i:i+10]) for i in range(0, len(words), 10)]
        print(f"\n1. Simple token chunks (10 words each): {len(token_chunks)} chunks")
        for i, chunk in enumerate(token_chunks[:2]):
            print(f"   Chunk {i+1}: {chunk}...")
        
        # Fixed-size chunking
        chunk_size = 100
        char_chunks = [SAMPLE_DOCUMENT[i:i+chunk_size] for i in range(0, len(SAMPLE_DOCUMENT), chunk_size)]
        print(f"\n2. Fixed-size chunks ({chunk_size} chars): {len(char_chunks)} chunks")
        for i, chunk in enumerate(char_chunks[:2]):
            print(f"   Chunk {i+1}: {chunk}...")
    
    # Run the agent for advanced chunking analysis
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ Document Chunking Complete")
    print("💡 Choose chunking strategy based on your use case:")
    print("   • Token-based: Good for language models with token limits")
    print("   • Sentence-based: Preserves semantic meaning")
    print("   • Recursive: Balanced approach for general use")
    print("   • Semantic: Best for maintaining context and meaning (requires embeddings)")
    print("🔧 Install knowledge dependencies: pip install 'praisonaiagents[knowledge]'")
