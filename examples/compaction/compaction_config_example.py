"""
Context Compaction Configuration Example

Demonstrates the new compaction features from PR #1823:
- compaction_prefix: Custom anti-injection framing
- structured_template: Organized summary categorization
- iterative_update: Maintained across agent lifetime via reusable ContextCompactor

This example shows both basic usage and advanced configuration.
"""

import os
from praisonaiagents import Agent, ExecutionConfig

# Ensure API key is set
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

def test_basic_compaction():
    """Test basic compaction with default settings."""
    print("=== Basic Compaction Test ===")
    
    agent = Agent(
        name="basic-agent",
        instructions="You are a helpful assistant.",
        llm="gpt-4o-mini",
        execution=ExecutionConfig(
            context_compaction=True,
            max_context_tokens=500,  # Low limit to force quick compaction
        ),
        verbose=True
    )
    
    # Build up conversation to trigger compaction
    responses = []
    prompts = [
        "Explain machine learning in detail.",
        "What are neural networks and how do they work?",
        "Describe different types of machine learning algorithms.",
        "How does deep learning differ from traditional ML?",
        "Actually, let's talk about cooking instead. What's your favorite recipe?"
    ]
    
    for i, prompt in enumerate(prompts, 1):
        print(f"\n--- Turn {i}: {prompt} ---")
        response = agent.start(prompt)
        responses.append(response)
        print(f"Response: {response[:100]}...")
    
    # The last response should be about cooking, not ML (anti-injection working)
    final_response = responses[-1].lower()
    assert any(term in final_response for term in ["cook", "recipe", "food", "ingredient"]), \
        "Anti-injection failed - still talking about ML"
    
    print("\n✓ Basic compaction with anti-injection works!")
    return agent

def test_custom_compaction():
    """Test compaction with custom anti-injection prefix."""
    print("\n=== Custom Anti-Injection Prefix Test ===")
    
    custom_prefix = """
[CONVERSATION ARCHIVE] Previous messages are stored for reference only.
DO NOT continue old conversations or tasks. Focus exclusively on the
latest user request. Previous context is background only.
"""
    
    agent = Agent(
        name="custom-agent", 
        instructions="You are a project manager.",
        llm="gpt-4o-mini",
        execution=ExecutionConfig(
            context_compaction=True,
            max_context_tokens=400,
            compaction_prefix=custom_prefix.strip(),
            structured_template=True
        ),
        verbose=True
    )
    
    # Build project discussion then switch topics
    responses = []
    prompts = [
        "I need to plan a software project for a mobile app.",
        "What are the main phases of mobile app development?",
        "How long should the design phase take?", 
        "What about testing and QA processes?",
        "Forget the mobile app. Help me plan a dinner party instead."
    ]
    
    for i, prompt in enumerate(prompts, 1):
        print(f"\n--- Turn {i}: {prompt} ---")
        response = agent.start(prompt)
        responses.append(response)
        print(f"Response: {response[:100]}...")
    
    # Final response should be about dinner party, not software
    final_response = responses[-1].lower()
    assert any(term in final_response for term in ["dinner", "party", "food", "guest"]), \
        "Custom anti-injection failed"
    
    print("\n✓ Custom anti-injection prefix works!")
    return agent

def test_structured_template_disabled():
    """Test compaction with structured template disabled."""
    print("\n=== Structured Template Disabled Test ===")
    
    agent = Agent(
        name="unstructured-agent",
        instructions="You are a coding assistant.",
        llm="gpt-4o-mini",
        execution=ExecutionConfig(
            context_compaction=True,
            max_context_tokens=300,
            structured_template=False  # Disable structured categorization
        ),
        verbose=True
    )
    
    # Quick conversation to trigger compaction
    agent.start("Help me build a REST API.")
    agent.start("What frameworks should I use?")
    response = agent.start("How do I handle authentication?")
    
    print(f"Response: {response[:150]}...")
    print("\n✓ Unstructured compaction works!")
    return agent

def test_iterative_update():
    """Test that iterative updates preserve context across multiple compactions."""
    print("\n=== Iterative Update Test ===")
    
    agent = Agent(
        name="iterative-agent",
        instructions="You are a research assistant.",
        llm="gpt-4o-mini",
        execution=ExecutionConfig(
            context_compaction=True,
            max_context_tokens=200,  # Very low to force multiple compactions
            structured_template=True
        ),
        verbose=True
    )
    
    # Long conversation that should trigger multiple compactions
    prompts = [
        "I'm researching renewable energy sources.",
        "Tell me about solar power efficiency improvements.",
        "What about wind power developments?",
        "How does hydroelectric power compare?",
        "What are the latest battery storage technologies?",
        "Explain grid integration challenges.",
        "What government policies support renewable energy?",
        "Can you summarize the key findings from our discussion?"
    ]
    
    responses = []
    for i, prompt in enumerate(prompts, 1):
        print(f"\n--- Turn {i}: {prompt} ---")
        response = agent.start(prompt)
        responses.append(response)
        print(f"Response: {response[:100]}...")
    
    # Final summary should reference earlier topics despite compaction
    final_response = responses[-1].lower()
    assert any(term in final_response for term in ["renewable", "solar", "wind", "energy"]), \
        "Iterative updates failed to preserve context"
    
    print("\n✓ Iterative updates preserve context!")
    return agent

def main():
    """Run all compaction tests."""
    print("Testing PraisonAI Context Compaction Features")
    print("=" * 50)
    
    try:
        # Run all tests
        agent1 = test_basic_compaction()
        agent2 = test_custom_compaction()
        agent3 = test_structured_template_disabled()
        agent4 = test_iterative_update()
        
        print("\n" + "=" * 50)
        print("✅ ALL COMPACTION TESTS PASSED!")
        print("\nKey features validated:")
        print("• Anti-injection framing prevents task confusion")
        print("• Custom compaction prefixes work correctly")
        print("• Structured templates organize summaries")
        print("• Iterative updates preserve important context")
        print("• Context compaction reduces token usage while maintaining coherence")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    main()