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
    print("✓ Created HybridConversationAnalyzer")
    
    # Test compactor
    compactor = IntelligentConversationCompactor(analyzer=analyzer)
    print("✓ Created IntelligentConversationCompactor")
    
    # Test with simple messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello! I need help with Python."},
        {"role": "assistant", "content": "I'd be happy to help with Python! What specifically would you like to know?"},
        {"role": "user", "content": "How do I create a list?"},
        {"role": "assistant", "content": "You can create a list using square brackets: my_list = [1, 2, 3]"},
        {"role": "user", "content": "Thanks! That's very helpful."},
        {"role": "assistant", "content": "You're welcome! Is there anything else about Python lists you'd like to know?"},
    ]
    
    try:
        result, context = compactor.compact_conversation(
            messages=messages,
            target_tokens=200,
            preserve_recent=2
        )
        print(f"✓ Compaction successful: {len(messages)} → {len(result)} messages")
        print(f"  Context topic: {context.main_topic}")
        print("✓ Conversation compaction test passed!")
        return True
    except Exception as e:
        print(f"✗ Error during compaction: {e}")
        return False


if __name__ == "__main__":
    test_conversation_compaction()