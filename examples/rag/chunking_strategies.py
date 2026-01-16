"""
Chunking Strategies for RAG

This example demonstrates different approaches to splitting documents into
chunks for effective retrieval.

RAG Concept: Chunking is critical for RAG quality. Too large chunks dilute
relevance; too small chunks lose context. The right strategy depends on
your content type and query patterns.
"""

from praisonaiagents import Agent

# Sample long document: Product documentation
PRODUCT_DOCUMENTATION = """
# CloudManager Pro - Complete User Guide

## Chapter 1: Getting Started

CloudManager Pro is an enterprise cloud management platform that helps organizations
monitor, optimize, and secure their multi-cloud infrastructure. This guide covers
installation, configuration, and daily operations.

### 1.1 System Requirements

Before installing CloudManager Pro, ensure your system meets these requirements:
- Operating System: Ubuntu 20.04+, RHEL 8+, or Windows Server 2019+
- Memory: Minimum 16GB RAM, recommended 32GB for production
- Storage: 100GB SSD for application, additional storage for logs
- Network: Outbound HTTPS access to cloud provider APIs

### 1.2 Installation Steps

1. Download the installer from the customer portal
2. Run the installation script with root privileges
3. Configure the database connection
4. Set up the initial admin account
5. Verify the installation with the health check command

## Chapter 2: Dashboard Overview

The main dashboard provides a unified view of your cloud resources across all
connected providers. Key metrics displayed include:

### 2.1 Resource Metrics

- Total compute instances across all clouds
- Storage utilization and growth trends
- Network bandwidth consumption
- Cost breakdown by provider and project

### 2.2 Alert Summary

The alert panel shows active incidents categorized by severity:
- Critical: Immediate action required (service outages)
- Warning: Attention needed within 24 hours
- Info: Informational notifications

## Chapter 3: Cost Optimization

CloudManager Pro includes powerful cost optimization features that can reduce
your cloud spending by 20-40%.

### 3.1 Right-sizing Recommendations

The platform analyzes resource utilization patterns and suggests optimal
instance sizes. Recommendations are based on:
- CPU utilization over 14-day periods
- Memory usage patterns
- Network I/O requirements

### 3.2 Reserved Instance Planning

Use the RI Planner to identify opportunities for reserved instance purchases.
The tool calculates potential savings based on your usage patterns and
commitment preferences (1-year vs 3-year terms).

## Chapter 4: Security Features

### 4.1 Compliance Monitoring

CloudManager Pro continuously monitors your infrastructure against common
compliance frameworks including SOC 2, HIPAA, and PCI-DSS. Non-compliant
resources are flagged with remediation guidance.

### 4.2 Access Control

Role-based access control (RBAC) allows fine-grained permissions:
- Admin: Full access to all features
- Operator: Can view and modify resources
- Viewer: Read-only access to dashboards
- Billing: Access to cost and billing features only
"""


def chunk_by_paragraphs(text: str, min_length: int = 100) -> list:
    """Split text into paragraph-based chunks."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        if len(current_chunk) + len(para) < 500:
            current_chunk += "\n\n" + para if current_chunk else para
        else:
            if len(current_chunk) >= min_length:
                chunks.append({"content": current_chunk.strip()})
            current_chunk = para
    
    if current_chunk and len(current_chunk) >= min_length:
        chunks.append({"content": current_chunk.strip()})
    
    return chunks


def chunk_by_sections(text: str) -> list:
    """Split text by markdown headers (sections)."""
    import re
    
    # Split by headers (## or ###)
    sections = re.split(r'\n(?=##+ )', text)
    chunks = []
    
    for section in sections:
        section = section.strip()
        if len(section) > 50:  # Skip very short sections
            # Extract title if present
            lines = section.split('\n')
            title = lines[0].replace('#', '').strip() if lines[0].startswith('#') else "Untitled"
            chunks.append({
                "id": title.lower().replace(' ', '_')[:30],
                "content": section
            })
    
    return chunks


def chunk_by_fixed_size(text: str, chunk_size: int = 500, overlap: int = 50) -> list:
    """Split text into fixed-size chunks with overlap."""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        
        # Try to break at sentence boundary
        if end < len(text):
            last_period = chunk_text.rfind('.')
            if last_period > chunk_size * 0.5:
                end = start + last_period + 1
                chunk_text = text[start:end]
        
        chunks.append({"content": chunk_text.strip()})
        start = end - overlap
    
    return chunks


def demonstrate_chunking_strategies():
    """Show different chunking approaches and their effects."""
    
    print("=" * 60)
    print("CHUNKING STRATEGIES COMPARISON")
    print("=" * 60)
    
    # Strategy 1: Paragraph-based chunking
    para_chunks = chunk_by_paragraphs(PRODUCT_DOCUMENTATION)
    print(f"\n📄 Paragraph Chunking: {len(para_chunks)} chunks")
    print(f"   Average chunk size: {sum(len(c['content']) for c in para_chunks) // len(para_chunks)} chars")
    print(f"   Sample chunk: {para_chunks[0]['content'][:100]}...")
    
    # Strategy 2: Section-based chunking
    section_chunks = chunk_by_sections(PRODUCT_DOCUMENTATION)
    print(f"\n📑 Section Chunking: {len(section_chunks)} chunks")
    print(f"   Average chunk size: {sum(len(c['content']) for c in section_chunks) // len(section_chunks)} chars")
    print(f"   Sections: {[c['id'] for c in section_chunks[:5]]}...")
    
    # Strategy 3: Fixed-size chunking
    fixed_chunks = chunk_by_fixed_size(PRODUCT_DOCUMENTATION, chunk_size=400, overlap=50)
    print(f"\n📏 Fixed-Size Chunking (400 chars, 50 overlap): {len(fixed_chunks)} chunks")
    print(f"   Average chunk size: {sum(len(c['content']) for c in fixed_chunks) // len(fixed_chunks)} chars")


def rag_with_section_chunks():
    """Demonstrate RAG using section-based chunks."""
    
    # Create section-based chunks
    chunks = chunk_by_sections(PRODUCT_DOCUMENTATION)
    
    # Build context from chunks
    context = "\n\n".join([f"[{c['id']}]\n{c['content']}" for c in chunks])
    
    # Create agent with chunked knowledge in instructions
    agent = Agent(
        name="Product Expert",
        instructions=f"""You are a CloudManager Pro product expert.
        Answer questions using the product documentation.
        Be specific and reference relevant sections when helpful.
        
        PRODUCT DOCUMENTATION:
        {context}""",
        output="silent"
    )
    
    queries = [
        "What are the system requirements for CloudManager Pro?",
        "How can I reduce cloud costs?",
        "What compliance frameworks are supported?"
    ]
    
    print("\n" + "=" * 60)
    print("RAG WITH SECTION-BASED CHUNKS")
    print("=" * 60)
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 Answer: {response[:250]}..." if len(str(response)) > 250 else f"💡 Answer: {response}")
        print("-" * 40)


def semantic_chunking_concept():
    """Explain semantic chunking concept (agent-driven)."""
    
    print("\n" + "=" * 60)
    print("SEMANTIC CHUNKING CONCEPT")
    print("=" * 60)
    
    print("""
    Semantic chunking goes beyond fixed rules by considering meaning:
    
    1. **Sentence Embedding Similarity**
       - Compute embeddings for each sentence
       - Group sentences with similar embeddings
       - Split when similarity drops below threshold
    
    2. **Topic-Based Chunking**
       - Identify topic shifts in the document
       - Create chunks that maintain topical coherence
    
    3. **Agent-Driven Chunking**
       - Use an LLM to identify logical boundaries
       - Preserve context and relationships
    
    PraisonAI's Knowledge system handles chunking automatically,
    but understanding these strategies helps optimize retrieval quality.
    """)


def main():
    """Run all chunking strategy examples."""
    print("\n🚀 PraisonAI Chunking Strategies Examples\n")
    
    # Example 1: Compare chunking strategies
    demonstrate_chunking_strategies()
    
    # Example 2: RAG with section chunks
    rag_with_section_chunks()
    
    # Example 3: Semantic chunking concept
    semantic_chunking_concept()
    
    print("\n✅ Chunking strategy examples completed!")


if __name__ == "__main__":
    main()
