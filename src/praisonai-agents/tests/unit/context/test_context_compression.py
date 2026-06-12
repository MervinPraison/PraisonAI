#!/usr/bin/env python3
"""
Test script for the new context compression implementation.

This tests the ContextCompressor and LLMContextCompressorOptimizer classes
to ensure they work correctly according to issue #1806 requirements.
"""

import sys
from praisonaiagents.context.compressor import ContextCompressor, CompressResult
from praisonaiagents.context.optimizer import LLMContextCompressorOptimizer
from praisonaiagents.context.tokens import estimate_messages_tokens


def test_context_compressor():
    """Test the new ContextCompressor class."""
    # Create test messages
    messages = []
    
    # Add system message
    messages.append({
        "role": "system",
        "content": "You are a helpful assistant specialized in Python programming."
    })
    
    # Add conversation history
    for i in range(10):
        messages.append({
            "role": "user", 
            "content": f"Question {i+1}: Can you help me understand Python concept number {i+1}?"
        })
        messages.append({
            "role": "assistant",
            "content": f"Answer {i+1}: Certainly! Python concept {i+1} is important because it helps with programming efficiency and code readability. Here's a detailed explanation that goes on for quite a while to make this message longer and more realistic for testing compression scenarios."
        })
    
    print(f"Original messages: {len(messages)}")
    original_tokens = estimate_messages_tokens(messages)
    print(f"Original tokens: {original_tokens}")
    
    # Test ContextCompressor with fallback (no LLM)
    compressor = ContextCompressor(llm=None, enable_session_tracking=True)
    
    try:
        result = compressor.compress(
            messages=messages,
            summary_target_tokens=150,
            protect_last_n_tokens=500
        )
        
        print(f"Compressed messages: {len(result.messages)}")
        print(f"Final tokens: {result.final_tokens}")
        print(f"Tokens saved: {result.tokens_saved}")
        print(f"Compression ratio: {result.compression_ratio:.2f}")
        
        # Verify compression worked
        assert len(result.messages) <= len(messages)
        assert result.final_tokens <= original_tokens
        assert result.tokens_saved >= 0
        
        print("✓ ContextCompressor test passed!")
        return True
        
    except Exception as e:
        print(f"✗ Error in ContextCompressor: {e}")
        return False


def test_llm_context_compressor_optimizer():
    """Test the LLMContextCompressorOptimizer class."""
    
    # Create test messages
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hello! How can I help you today?"},
        {"role": "user", "content": "Tell me about Python"},
        {"role": "assistant", "content": "Python is a versatile programming language."},
        {"role": "user", "content": "What about lists?"},
        {"role": "assistant", "content": "Lists in Python are ordered collections."},
        {"role": "user", "content": "Thanks for the help"},
        {"role": "assistant", "content": "You're welcome! Happy to help anytime."}
    ]
    
    print(f"Original messages: {len(messages)}")
    original_tokens = estimate_messages_tokens(messages)
    print(f"Original tokens: {original_tokens}")
    
    # Test LLMContextCompressorOptimizer (without LLM, should fall back to sync compression)
    optimizer = LLMContextCompressorOptimizer(llm_client=None)
    
    try:
        result_messages, result = optimizer.optimize(messages, target_tokens=150)
        
        print(f"Optimized messages: {len(result_messages)}")
        print(f"Optimized tokens: {result.optimized_tokens}")
        print(f"Tokens saved: {result.tokens_saved}")
        print(f"Strategy used: {result.strategy_used}")
        
        # Check if compression occurred when needed
        if result.tokens_saved > 0:
            assert result.summary_added, "Expected a summary to be added when tokens are saved"
            print("✓ LLMContextCompressorOptimizer test passed!")
            return True
        else:
            print("⚠ No compression was needed (under token limit)")
            return True
            
    except Exception as e:
        print(f"✗ Error in LLMContextCompressorOptimizer: {e}")
        return False


def test_tokenization_improvements():
    """Test the improved tokenization features."""
    
    try:
        from praisonaiagents.context.tokens import get_estimator
        
        # Test different estimator configurations
        estimator_heuristic = get_estimator(use_accurate=False)
        estimator_accurate = get_estimator(use_accurate=True)
        
        test_message = {
            "role": "assistant",
            "content": "This is a test message for tokenization with various words and punctuation!"
        }
        
        tokens_heuristic = estimator_heuristic.estimate_message_tokens(test_message)
        tokens_accurate = estimator_accurate.estimate_message_tokens(test_message)
        
        # Verify both estimators return reasonable token counts
        assert isinstance(tokens_heuristic, int) and tokens_heuristic > 0
        assert isinstance(tokens_accurate, int) and tokens_accurate > 0
        
        print("✓ Tokenization improvements test passed!")
        return True
        
    except Exception as e:
        print(f"✗ Error in tokenization test: {e}")
        return False


if __name__ == "__main__":
    print("Testing PraisonAI Context Compression Implementation")
    print("============================================================")
    
    tests = [
        test_context_compressor,
        test_llm_context_compressor_optimizer,
        test_tokenization_improvements,
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed with exception: {e}")
    
    print("============================================================")
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1)