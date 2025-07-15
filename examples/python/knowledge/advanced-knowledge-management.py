"""
Advanced Knowledge Management Example

This example demonstrates sophisticated knowledge management capabilities including
advanced chunking strategies, reranking, and intelligent knowledge retrieval.

Features demonstrated:
- Advanced document chunking strategies
- Vector store integration with ChromaDB
- Knowledge-based question answering
- Intelligent context retrieval
- Document processing and management
"""

from praisonaiagents import Agent
import tempfile
import os

# Create a sample knowledge document for demonstration
sample_document = """
# Artificial Intelligence in Healthcare

## Introduction
Artificial intelligence (AI) is revolutionizing healthcare by enabling more accurate diagnoses, 
personalized treatments, and efficient healthcare delivery. This document explores the current 
applications and future potential of AI in healthcare.

## Current Applications

### Medical Imaging
AI algorithms, particularly deep learning models, have shown remarkable success in medical imaging:
- Radiology: AI can detect cancers in mammograms with accuracy matching or exceeding radiologists
- Ophthalmology: AI systems can diagnose diabetic retinopathy from retinal photographs
- Pathology: AI assists in analyzing tissue samples for cancer detection

### Drug Discovery
AI is accelerating drug discovery processes:
- Molecular design: AI predicts molecular properties and drug-target interactions
- Clinical trials: AI optimizes patient recruitment and trial design
- Repurposing: AI identifies new uses for existing drugs

### Predictive Analytics
Healthcare providers use AI for:
- Risk stratification: Identifying patients at risk of complications
- Early warning systems: Detecting deteriorating patient conditions
- Resource planning: Optimizing staff schedules and equipment allocation

## Challenges and Considerations

### Data Privacy and Security
Healthcare AI faces significant challenges:
- Patient data protection and HIPAA compliance
- Secure data sharing between institutions
- Consent management for AI applications

### Regulatory Approval
AI medical devices require:
- FDA approval for diagnostic tools
- Clinical validation studies
- Post-market surveillance

### Ethical Considerations
Important ethical aspects include:
- Algorithmic bias and fairness
- Transparency and explainability
- Patient autonomy and informed consent

## Future Directions

### Personalized Medicine
AI will enable:
- Genomic-based treatment selection
- Individualized drug dosing
- Precision diagnostics

### Integrated Healthcare Systems
Future developments include:
- AI-powered electronic health records
- Interoperable AI systems across healthcare networks
- Real-time decision support systems

## Conclusion
AI has tremendous potential to transform healthcare, but successful implementation requires
addressing technical, regulatory, and ethical challenges while maintaining focus on patient safety
and improved outcomes.
"""

# Save the sample document to a temporary file
temp_dir = tempfile.mkdtemp()
try:
    doc_path = os.path.join(temp_dir, "ai_healthcare_guide.txt")
    with open(doc_path, "w") as f:
        f.write(sample_document)

    # Create an agent with advanced knowledge management configuration
    knowledge_agent = Agent(
        name="AdvancedKnowledgeAgent",
        role="Healthcare AI Knowledge Expert", 
        goal="Provide comprehensive answers about AI in healthcare using advanced knowledge retrieval",
        backstory="You are an expert in healthcare AI with access to comprehensive knowledge bases and advanced retrieval capabilities.",
        
        # Advanced knowledge configuration
        knowledge=[doc_path],
        knowledge_config={
            "vector_store": {
                "provider": "chroma",
                "collection_name": "healthcare_ai_knowledge"
            },
            "chunking": {
                "strategy": "semantic",  # Advanced semantic chunking
                "chunk_size": 500,       # Optimal chunk size for retrieval
                "chunk_overlap": 50,     # Overlap for context preservation
                "separators": ["\n\n", "\n", ".", "!", "?"]  # Smart separators
            },
            "retrieval": {
                "search_type": "similarity",
                "k": 5,  # Retrieve top 5 most relevant chunks
                "score_threshold": 0.7,  # Minimum relevance score
                "rerank": True  # Enable reranking for better results
            },
            "embedding": {
                "provider": "openai",
                "model": "text-embedding-3-small",  # Efficient embedding model
                "dimensions": 1536
            }
        },
        
        instructions="""You are an expert in healthcare AI. Use the knowledge base to provide 
        comprehensive, accurate answers. Always cite specific information from the documents 
        when possible. If the knowledge base doesn't contain sufficient information, clearly 
        state this and provide general guidance based on your training.""",
        
        verbose=True
    )

    # Test advanced knowledge retrieval with various question types

    # Factual question about specific applications
    print("="*70)
    print("TESTING: Specific factual question about AI applications")
    print("="*70)
    factual_result = knowledge_agent.start(
        "What are the current applications of AI in medical imaging according to the knowledge base?"
    )
    print(f"Factual query result:\n{factual_result}\n")

    # Complex analytical question requiring synthesis
    print("="*70)
    print("TESTING: Complex analytical question requiring synthesis")  
    print("="*70)
    analytical_result = knowledge_agent.start(
        "What are the main challenges facing AI implementation in healthcare and how do they relate to each other?"
    )
    print(f"Analytical query result:\n{analytical_result}\n")

    # Specific detail extraction
    print("="*70)
    print("TESTING: Specific detail extraction")
    print("="*70)
    detail_result = knowledge_agent.start(
        "What specific regulatory requirements does the document mention for AI medical devices?"
    )
    print(f"Detail extraction result:\n{detail_result}\n")

    # Future-oriented question requiring inference
    print("="*70)
    print("TESTING: Future-oriented question requiring inference")
    print("="*70)
    future_result = knowledge_agent.start(
        "Based on the knowledge base, what integration capabilities will future AI healthcare systems have?"
    )
    print(f"Future-oriented query result:\n{future_result}\n")

    # Question about relationships and connections
    print("="*70)
    print("TESTING: Relationship and connection analysis")
    print("="*70)
    relationship_result = knowledge_agent.start(
        "How do the ethical considerations mentioned relate to the regulatory approval process for AI in healthcare?"
    )
    print(f"Relationship analysis result:\n{relationship_result}\n")

finally:
    # Clean up temporary files
    import shutil
    shutil.rmtree(temp_dir)

print("="*80)
print("ADVANCED KNOWLEDGE MANAGEMENT DEMONSTRATION COMPLETED")
print("="*80)
print("This example demonstrated:")
print("- Semantic chunking for better context preservation")
print("- Advanced retrieval with reranking capabilities")
print("- Multiple query types with intelligent responses")
print("- Knowledge base integration with vector search")
print("- Configurable embedding and retrieval parameters")