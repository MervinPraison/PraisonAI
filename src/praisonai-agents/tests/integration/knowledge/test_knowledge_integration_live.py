"""
Live integration tests for knowledge/RAG integration.

These tests require:
- PRAISONAI_LIVE_TESTS=1 environment variable
- OPENAI_API_KEY environment variable

Run with: PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/knowledge/test_knowledge_integration_live.py -v
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.fixture
def sample_knowledge_files():
    """Create sample knowledge files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample knowledge documents
        doc1 = Path(tmpdir) / "artificial_intelligence.txt"
        doc1.write_text("""
        Artificial Intelligence (AI) refers to the simulation of human intelligence in machines.
        AI systems can perform tasks that typically require human intelligence, such as learning,
        reasoning, perception, and decision-making. Modern AI includes machine learning,
        deep learning, and neural networks.
        """)
        
        doc2 = Path(tmpdir) / "machine_learning.txt"
        doc2.write_text("""
        Machine Learning is a subset of artificial intelligence that enables computers
        to learn and improve from experience without being explicitly programmed.
        Common types include supervised learning, unsupervised learning, and reinforcement learning.
        Popular algorithms include decision trees, neural networks, and support vector machines.
        """)
        
        doc3 = Path(tmpdir) / "data_science.txt"
        doc3.write_text("""
        Data Science is an interdisciplinary field that uses scientific methods, processes,
        algorithms, and systems to extract knowledge and insights from structured and unstructured data.
        It combines statistics, mathematics, programming, and domain expertise.
        Common tools include Python, R, SQL, and various visualization libraries.
        """)
        
        yield tmpdir


@pytest.mark.live
class TestKnowledgeRAGIntegrationLive:
    """Live tests for Knowledge/RAG integration with agents."""
    
    def test_agent_with_knowledge_real_rag(self, openai_api_key, sample_knowledge_files):
        """Test agent using real knowledge base for RAG."""
        from praisonaiagents import Agent
        
        # Create agent with knowledge
        agent = Agent(
            name="KnowledgeAgent",
            instructions="You are an AI assistant with access to knowledge documents. Use the provided knowledge to answer questions accurately.",
            knowledge=[str(doc) for doc in Path(sample_knowledge_files).glob("*.txt")],
            llm="gpt-4o-mini"
        )
        
        # Ask question that requires knowledge retrieval
        result = agent.start("What is artificial intelligence and how does it relate to machine learning?")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        
        result_lower = result.lower()
        # Should contain information from knowledge base
        assert "artificial intelligence" in result_lower or "ai" in result_lower
        assert "machine learning" in result_lower or "learning" in result_lower
        
        print(f"Knowledge RAG result: {result}")


@pytest.mark.live
class TestPDFKnowledgeIntegrationLive:
    """Live tests for PDF knowledge integration."""
    
    def test_agent_with_pdf_knowledge_real(self, openai_api_key):
        """Test agent processing PDF documents for knowledge."""
        from praisonaiagents import Agent
        
        # Create a simple text file to simulate PDF content (actual PDF would require additional deps)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("""
            Quantum Computing Overview
            
            Quantum computing is a type of computation that harnesses quantum mechanical phenomena
            like superposition and entanglement to process information. Unlike classical computers
            that use bits (0 or 1), quantum computers use quantum bits or qubits that can exist
            in multiple states simultaneously.
            
            Key concepts:
            - Superposition: Qubits can be in multiple states at once
            - Entanglement: Qubits can be correlated in quantum ways
            - Quantum gates: Operations that manipulate qubits
            """)
            pdf_path = f.name
        
        try:
            # Create agent with document knowledge
            agent = Agent(
                name="PDFKnowledgeAgent",
                instructions="You are an expert assistant with access to specialized documents. Answer questions based on the provided materials.",
                knowledge=[pdf_path],
                llm="gpt-4o-mini"
            )
            
            # Query the document content
            result = agent.start("Explain quantum computing and its key concepts")
            
            # Assertions
            assert result is not None
            assert len(result) > 0
            
            result_lower = result.lower()
            # Should contain information from the document
            assert "quantum" in result_lower
            assert ("superposition" in result_lower or "entanglement" in result_lower or "qubit" in result_lower)
            
            print(f"PDF knowledge result: {result}")
            
        finally:
            # Cleanup
            Path(pdf_path).unlink()


@pytest.mark.live
class TestKnowledgeSearchLive:
    """Live tests for knowledge search functionality."""
    
    def test_agent_knowledge_search_real(self, openai_api_key, sample_knowledge_files):
        """Test agent searching through knowledge base effectively."""
        from praisonaiagents import Agent, KnowledgeConfig
        
        # Agent with enhanced knowledge configuration
        agent = Agent(
            name="KnowledgeSearchAgent",
            instructions="You are a research assistant that can search through knowledge bases efficiently.",
            knowledge=[str(doc) for doc in Path(sample_knowledge_files).glob("*.txt")],
            knowledge_config=KnowledgeConfig(include_citations=True, top_k=5),
            llm="gpt-4o-mini"
        )
        
        # Test specific knowledge search
        result = agent.start("What are the common tools used in data science?")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        
        result_lower = result.lower()
        # Should find information about data science tools
        assert ("python" in result_lower or "sql" in result_lower or "data science" in result_lower)
        
        print(f"Knowledge search result: {result}")


@pytest.mark.live
class TestMultiDocumentKnowledgeLive:
    """Live tests for multi-document knowledge processing."""
    
    def test_agent_multi_document_synthesis_real(self, openai_api_key, sample_knowledge_files):
        """Test agent synthesizing information from multiple documents."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="MultiDocAgent",
            instructions="You are an expert at synthesizing information from multiple sources. Provide comprehensive answers that draw from all available knowledge.",
            knowledge=[str(doc) for doc in Path(sample_knowledge_files).glob("*.txt")],
            llm="gpt-4o-mini"
        )
        
        # Ask question requiring synthesis from multiple documents
        result = agent.start("Compare and contrast artificial intelligence, machine learning, and data science. How are they related?")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        
        result_lower = result.lower()
        # Should mention concepts from multiple documents
        topics_mentioned = sum([
            "artificial intelligence" in result_lower or "ai" in result_lower,
            "machine learning" in result_lower,
            "data science" in result_lower,
        ])
        
        # Should synthesize from at least 2 documents
        assert topics_mentioned >= 2
        
        print(f"Multi-document synthesis result: {result}")


@pytest.mark.live
class TestKnowledgeWithMemoryLive:
    """Live tests for knowledge integration with memory."""
    
    def test_agent_knowledge_plus_memory_real(self, openai_api_key, sample_knowledge_files):
        """Test agent combining knowledge base with conversational memory."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="KnowledgeMemoryAgent",
            instructions="You are an assistant with both knowledge access and conversational memory. Use both to provide comprehensive responses.",
            knowledge=[str(doc) for doc in Path(sample_knowledge_files).glob("*.txt")],
            memory=True,
            llm="gpt-4o-mini"
        )
        
        # First interaction to establish context
        result1 = agent.start("I'm interested in learning about AI. Can you explain machine learning?")
        
        assert result1 is not None
        assert len(result1) > 0
        
        # Second interaction testing memory + knowledge
        result2 = agent.start("Based on what we just discussed, what would be the next step in my AI learning journey?")
        
        assert result2 is not None
        assert len(result2) > 0
        
        # Should reference both previous conversation and knowledge
        result2_lower = result2.lower()
        assert ("learning" in result2_lower or "ai" in result2_lower or "next" in result2_lower)
        
        print(f"Knowledge + Memory result 1: {result1}")
        print(f"Knowledge + Memory result 2: {result2}")