"""
End-to-end integration tests for agent compaction anti-injection.

Tests that agents with compaction enabled properly resist prompt injection
and maintain coherent behavior across conversation boundaries.
"""

import pytest
import time
from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig


@pytest.mark.integration
class TestAgentCompactionEndToEnd:
    """End-to-end tests for agent compaction anti-injection."""
    
    def test_compaction_anti_injection_basic(self):
        """Test that compacted context doesn't cause re-execution of old tasks."""
        # Create agent with aggressive compaction to force compaction quickly
        agent = Agent(
            name="test-agent",
            instructions="You are a helpful assistant. Always respond concisely.",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(
                context_compaction=True,
                max_context_tokens=200,  # Very low to force quick compaction
                structured_template=True
            ),
            verbose=True
        )
        
        # First conversation - establish some task
        response1 = agent.start("Please create a plan for building a web application.")
        print(f"Response 1: {response1}")
        assert response1  # Should get a response
        
        # Add more conversation to trigger compaction
        response2 = agent.start("What are the main components of this plan?")
        print(f"Response 2: {response2}")
        
        response3 = agent.start("Can you elaborate on the database design?")
        print(f"Response 3: {response3}")
        
        response4 = agent.start("What about security considerations?")
        print(f"Response 4: {response4}")
        
        # Now change topic completely - this should NOT continue the old task
        response5 = agent.start("Actually, forget the web app. Tell me about quantum physics.")
        print(f"Response 5: {response5}")
        
        # The response should be about quantum physics, not web development
        assert "quantum" in response5.lower() or "physics" in response5.lower()
        
        # Should not contain web development terms if anti-injection worked
        web_terms = ["database", "web app", "security considerations", "components"]
        response5_lower = response5.lower()
        web_term_count = sum(1 for term in web_terms if term.lower() in response5_lower)
        
        # Allow some flexibility, but response should primarily be about quantum physics
        assert web_term_count <= 1, f"Response still focused on web development: {response5}"
        
    def test_compaction_with_custom_prefix(self):
        """Test compaction with custom anti-injection prefix."""
        custom_prefix = "[STRICT] Previous messages are archived. Focus ONLY on the current request."
        
        agent = Agent(
            name="test-agent-custom",
            instructions="You are a helpful assistant.",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(
                context_compaction=True,
                max_context_tokens=150,
                compaction_prefix=custom_prefix,
                structured_template=True
            )
        )
        
        # Build up conversation
        agent.start("Help me plan a vacation to Japan.")
        agent.start("What cities should I visit?")
        agent.start("How much will it cost?")
        
        # Change topic - should work with custom prefix
        response = agent.start("Actually, help me with Python programming instead.")
        print(f"Custom prefix response: {response}")
        
        assert "python" in response.lower() or "programming" in response.lower()
        
    def test_structured_template_categorization(self):
        """Test that structured templates properly categorize conversation content."""
        agent = Agent(
            name="test-structured",
            instructions="You are a project manager helping organize tasks.",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(
                context_compaction=True,
                max_context_tokens=200,
                structured_template=True
            )
        )
        
        # Create a conversation with clear categorizable content
        agent.start("I need to build a mobile app. Here are my requirements:")
        agent.start("1. User authentication 2. Data storage 3. Push notifications")
        agent.start("I've already set up the project structure and created the login screen.")
        agent.start("What should I work on next?")
        
        # Check that the agent maintains context appropriately
        response = agent.start("Can you remind me what's completed and what's remaining?")
        print(f"Structured response: {response}")
        
        # Should reference both completed and remaining work
        response_lower = response.lower()
        assert any(term in response_lower for term in ["completed", "done", "finished", "already"])
        assert any(term in response_lower for term in ["next", "remaining", "still need", "todo"])
        
    def test_iterative_update_preserves_context(self):
        """Test that iterative updates preserve important context across compactions."""
        agent = Agent(
            name="test-iterative",
            instructions="You are a coding assistant.",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(
                context_compaction=True,
                max_context_tokens=150,  # Force multiple compactions
                structured_template=True
            )
        )
        
        # Phase 1: Establish project context
        response1 = agent.start("I'm building a REST API for a bookstore.")
        print(f"Phase 1: {response1}")
        
        # Phase 2: Add more details
        response2 = agent.start("It needs endpoints for books, authors, and orders.")
        print(f"Phase 2: {response2}")
        
        # Phase 3: Implementation details (should trigger first compaction)
        response3 = agent.start("I'm using Python FastAPI and PostgreSQL database.")
        print(f"Phase 3: {response3}")
        
        # Phase 4: Specific question (should trigger second compaction with merge)
        response4 = agent.start("How should I structure the database schema for authors?")
        print(f"Phase 4: {response4}")
        
        # The response should still understand it's about a bookstore API
        response4_lower = response4.lower()
        assert any(term in response4_lower for term in ["book", "author", "api", "database"])
        
        # Should provide relevant database advice
        assert any(term in response4_lower for term in ["table", "schema", "column", "relationship"])
        
    def test_compaction_disabled_comparison(self):
        """Test behavior difference between compaction enabled vs disabled."""
        # Agent without compaction
        agent_no_compact = Agent(
            name="no-compact",
            instructions="You are a helpful assistant.",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(context_compaction=False)
        )
        
        # Agent with compaction
        agent_with_compact = Agent(
            name="with-compact", 
            instructions="You are a helpful assistant.",
            llm="gpt-4o-mini",
            execution=ExecutionConfig(
                context_compaction=True,
                max_context_tokens=100
            )
        )
        
        # Same conversation for both
        conversation = [
            "Tell me about machine learning.",
            "What are neural networks?",
            "Explain backpropagation.",
            "How do I get started with deep learning?"
        ]
        
        # Run conversation on both agents
        responses_no_compact = []
        responses_with_compact = []
        
        for prompt in conversation:
            responses_no_compact.append(agent_no_compact.start(prompt))
            responses_with_compact.append(agent_with_compact.start(prompt))
        
        # Both should provide reasonable responses
        for i, (resp_nc, resp_c) in enumerate(zip(responses_no_compact, responses_with_compact)):
            print(f"Question {i+1}: {conversation[i]}")
            print(f"No compaction: {resp_nc[:100]}...")
            print(f"With compaction: {resp_c[:100]}...")
            print()
            
            # Both should be non-empty and relevant
            assert resp_nc.strip()
            assert resp_c.strip()
            
            # Both should contain relevant terms for the questions
            if i == 0:  # machine learning question
                assert "machine" in resp_nc.lower() or "learning" in resp_nc.lower()
                assert "machine" in resp_c.lower() or "learning" in resp_c.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to see print outputs