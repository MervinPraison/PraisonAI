"""
Simple test for conversation compaction functionality.
"""

def test_conversation_compaction():
    """Test basic conversation compaction functionality."""
    print("Testing conversation compaction...")
    
    # Import the classes
    from praisonaiagents.context.conversation import (
        HybridConversationAnalyzer,
        IntelligentConversationCompactor,
    )
    from praisonaiagents.context.protocols import ConversationContext
    
    print("✓ Successfully imported conversation compaction classes")
    
    # Test analyzer
    analyzer = HybridConversationAnalyzer()
    
    messages = [
        {"role": "user", "content": "I need help building a website"},
        {"role": "assistant", "content": "I can help you build a website. What kind of site do you need?"},
        {"role": "user", "content": "I want to create an e-commerce site for selling books"},
        {"role": "assistant", "content": "Great! We'll need to implement user authentication, product catalog, and payment processing."},
        {"role": "user", "content": "Let's start with the user authentication"},
        {"role": "assistant", "content": "I'll help you implement user registration and login functionality."},
    ]
    
    # Test conversation analysis
    context = analyzer.analyze_conversation(messages)
    
    assert isinstance(context, ConversationContext), "Context should be ConversationContext instance"
    assert context.original_message_count == len(messages), f"Expected {len(messages)}, got {context.original_message_count}"
    assert context.main_topic, "Main topic should not be empty"
    
    print(f"✓ Analyzed conversation: topic='{context.main_topic}', tone='{context.conversation_tone}'")
    
    # Test key decision extraction
    decisions = analyzer.extract_key_decisions(messages)
    print(f"✓ Extracted {len(decisions)} decisions")
    
    # Test topic identification
    topic = analyzer.identify_main_topic(messages)
    print(f"✓ Identified topic: '{topic}'")
    
    # Test conversation compaction
    compactor = IntelligentConversationCompactor(analyzer)
    
    # Create longer conversation for compaction
    long_messages = []
    for i in range(10):
        long_messages.append({"role": "user", "content": f"This is a longer user message {i} with enough content to exceed token limits and trigger compaction"})
        long_messages.append({"role": "assistant", "content": f"This is a longer assistant response {i} providing detailed information and guidance"})
    
    # Test compaction
    result, _compaction_context = compactor.compact_conversation(
        messages=long_messages,
        target_tokens=200,  # Small target to force compaction
        preserve_recent=3
    )
    
    print(f"✓ Compacted {len(long_messages)} messages to {len(result)} messages")
    
    # Check for summary message
    summary_messages = [m for m in result if m.get("_metadata", {}).get("is_conversation_summary")]
    print(f"✓ Created {len(summary_messages)} summary messages")
    
    # Test summary message creation
    test_context = ConversationContext(
        main_topic="Building a website",
        current_goal="Implement user authentication", 
        key_decisions=["Use React framework"],
        original_message_count=10,
    )
    
    summary_msg = test_context.to_summary_message()
    assert summary_msg["role"] == "system"
    assert "Building a website" in summary_msg["content"]
    
    print("✓ Summary message generation works correctly")
    
    # Test optimizer integration
    from praisonaiagents.context.optimizer import ConversationOptimizer
    from praisonaiagents.context.models import OptimizerStrategy
    
    optimizer = ConversationOptimizer(preserve_recent=2)
    result, optimization_result = optimizer.optimize(long_messages, target_tokens=300)
    
    assert optimization_result.strategy_used == OptimizerStrategy.CONVERSATION
    print(f"✓ Optimizer integration works: saved {optimization_result.tokens_saved} tokens")
    
    print("\n🎉 All conversation compaction tests passed!")


def test_protocol_imports():
    """Test that protocols can be imported correctly."""
    print("Testing protocol imports...")
    
    from praisonaiagents.context.protocols import (
        ConversationContext,
        ConversationAnalyzer,
        ConversationCompactor,
    )
    
    print("✓ Successfully imported conversation protocols")
    
    # Test that we can create ConversationContext
    context = ConversationContext(
        main_topic="Test topic",
        current_goal="Test goal"
    )
    
    assert context.main_topic == "Test topic"
    print("✓ ConversationContext creation works")


if __name__ == "__main__":
    test_protocol_imports()
    test_conversation_compaction()
    print("\n✅ All tests completed successfully!")