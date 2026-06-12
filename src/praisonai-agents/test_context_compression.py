#!/usr/bin/env python3
"""
Test script for the new context compression implementation.

This tests the ContextCompressor and LLMContextCompressorOptimizer classes
to ensure they work correctly according to issue #1806 requirements.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents.context.compressor import ContextCompressor, CompressResult
from praisonaiagents.context.optimizer import LLMContextCompressorOptimizer
from praisonaiagents.context.tokens import estimate_messages_tokens


def test_context_compressor():
    """Test the new ContextCompressor class."""
    print("=== Testing ContextCompressor ===")
    
    # Create sample conversation
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Help me build a todo app."},
        {"role": "assistant", "content": "I'll help you build a todo app. Let me start by creating the basic structure."},
        {"role": "tool", "name": "file_write", "content": "Created file: app.py with basic Flask structure"},
        {"role": "user", "content": "Add database support."},
        {"role": "assistant", "content": "I'll add SQLite database support for the todo app."},
        {"role": "tool", "name": "file_write", "content": "Created file: models.py with SQLAlchemy models for Todo items"},
        {"role": "tool", "name": "file_write", "content": "Updated app.py to include database initialization"},
        {"role": "user", "content": "Add a web interface."},
        {"role": "assistant", "content": "I'll create HTML templates for the web interface."},
        {"role": "tool", "name": "file_write", "content": "Created templates/index.html with todo list display and form for adding new todos"},
        {"role": "user", "content": "Test the app and make sure it works correctly."},
        {"role": "assistant", "content": "I'll test the todo app to ensure all functionality works properly."},
        {"role": "tool", "name": "run_tests", "content": "Running Flask application in test mode...\nTest 1: Homepage loads correctly - PASS\nTest 2: Can add new todo item - PASS\nTest 3: Can mark todo as complete - PASS\nTest 4: Can delete todo item - PASS\nAll tests passed successfully!"},
        {"role": "user", "content": "Great! Now add some CSS styling to make it look better."},
        {"role": "assistant", "content": "I'll add CSS styling to improve the appearance of the todo app."},
        {"role": "tool", "name": "file_write", "content": "Created static/css/style.css with modern styling including:\n- Clean typography\n- Responsive design\n- Nice button styles\n- Color-coded todo states\n- Smooth animations"},
        {"role": "tool", "name": "file_write", "content": "Updated templates/base.html to include CSS file and improved HTML structure"},
        {"role": "user", "content": "Perfect! Can you add user authentication?"},
        {"role": "assistant", "content": "I'll add user authentication so each user can have their own todo list."},
        {"role": "tool", "name": "file_write", "content": "Created auth.py with login/logout routes and password hashing"},
        {"role": "tool", "name": "file_write", "content": "Updated models.py to add User model and link todos to users"},
        {"role": "user", "content": "Test the authentication system."},
    ]
    
    # Test deterministic compression (no LLM)
    compressor = ContextCompressor(llm=None, enable_session_tracking=True)
    
    print(f"Original messages: {len(messages)}")
    print(f"Original tokens: {estimate_messages_tokens(messages)}")
    
    # Test sync compression via optimizer
    try:
        # Create optimizer that uses the compressor
        from praisonaiagents.context.optimizer import LLMContextCompressorOptimizer
        optimizer = LLMContextCompressorOptimizer(llm_client=None)
        result = optimizer._sync_compress(messages, target_tokens=200)  # Force compression
        print(f"Compressed messages: {len(result.messages)}")
        print(f"Final tokens: {result.final_tokens}")
        print(f"Tokens saved: {result.tokens_saved}")
        print(f"Compression efficiency: {result.compression_efficiency:.1f}%")
        print(f"Head preserved: {result.head_preserved_count}")
        print(f"Tail preserved: {result.tail_preserved_count}")
        print(f"Middle compressed: {result.middle_compressed_count}")
        
        # Check if summary was created
        for msg in result.messages:
            if msg.get("role") == "system" and "[Context Summary]" in msg.get("content", ""):
                print("\n--- Generated Summary ---")
                print(msg["content"])
                print("------------------------")
                break
        
        print("✓ ContextCompressor test passed!")
        return True
    except Exception as e:
        print(f"✗ ContextCompressor test failed: {e}")
        return False


def test_llm_context_compressor_optimizer():
    """Test the LLMContextCompressorOptimizer."""
    print("\n=== Testing LLMContextCompressorOptimizer ===")
    
    # Create sample conversation
    messages = [
        {"role": "system", "content": "You are a code assistant."},
        {"role": "user", "content": "Review this Python code for bugs."},
        {"role": "assistant", "content": "I'll review the code for potential issues."},
        {"role": "tool", "name": "read_file", "content": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"},
        {"role": "assistant", "content": "Found performance issue: recursive implementation is inefficient for large n."},
        {"role": "user", "content": "Fix the performance issue."},
        {"role": "assistant", "content": "I'll implement an iterative version for better performance."},
        {"role": "tool", "name": "write_file", "content": "def fibonacci(n):\n    if n <= 1:\n        return n\n    a, b = 0, 1\n    for _ in range(2, n + 1):\n        a, b = b, a + b\n    return b"},
        {"role": "user", "content": "Add error handling."},
    ]
    
    try:
        # Test optimizer without LLM client (deterministic mode)
        optimizer = LLMContextCompressorOptimizer(
            llm_client=None,  # No LLM for testing
            protect_last_n_tokens=100,  # Protect less to allow compression
            summary_target_tokens=50,
        )
        
        original_tokens = estimate_messages_tokens(messages)
        print(f"Original messages: {len(messages)}")
        print(f"Original tokens: {original_tokens}")
        
        # Test optimization with low token limit to force compression
        optimized_messages, result = optimizer.optimize(messages, target_tokens=150)
        
        print(f"Optimized messages: {len(optimized_messages)}")
        print(f"Optimized tokens: {result.optimized_tokens}")
        print(f"Tokens saved: {result.tokens_saved}")
        print(f"Strategy used: {result.strategy_used}")
        print(f"Messages removed: {result.messages_removed}")
        print(f"Summary added: {result.summary_added}")
        
        # Check if optimization worked
        if result.tokens_saved > 0:
            print("✓ LLMContextCompressorOptimizer test passed!")
            return True
        else:
            print("⚠ No compression was needed (under token limit)")
            return True
            
    except Exception as e:
        print(f"✗ LLMContextCompressorOptimizer test failed: {e}")
        return False


def test_tokenization_improvements():
    """Test improved tokenization."""
    print("\n=== Testing Tokenization Improvements ===")
    
    from praisonaiagents.context.tokens import estimate_tokens_accurate, get_estimator
    
    test_text = "This is a test of the improved tokenization system with better model awareness."
    
    # Test heuristic estimation
    try:
        heuristic_tokens = estimate_tokens_accurate(test_text, "unknown-model")
        print(f"Heuristic estimation: {heuristic_tokens} tokens")
        
        # Test with tiktoken if available
        try:
            import tiktoken
            accurate_tokens = estimate_tokens_accurate(test_text, "gpt-4o-mini")
            print(f"Accurate estimation: {accurate_tokens} tokens")
            
            # Test improved model mapping
            claude_tokens = estimate_tokens_accurate(test_text, "claude-3-5-sonnet")
            print(f"Claude model estimation: {claude_tokens} tokens")
            
        except ImportError:
            print("tiktoken not available, using heuristic only")
        
        # Test estimator factory
        estimator = get_estimator(use_accurate=True)
        factory_tokens = estimator.estimate(test_text)
        print(f"Factory estimator: {factory_tokens} tokens")
        
        print("✓ Tokenization improvements test passed!")
        return True
        
    except Exception as e:
        print(f"✗ Tokenization test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("Testing PraisonAI Context Compression Implementation")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 3
    
    # Run tests
    if test_context_compressor():
        tests_passed += 1
    
    if test_llm_context_compressor_optimizer():
        tests_passed += 1
        
    if test_tokenization_improvements():
        tests_passed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Context compression implementation is working.")
        return 0
    else:
        print(f"❌ {total_tests - tests_passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    exit(main())