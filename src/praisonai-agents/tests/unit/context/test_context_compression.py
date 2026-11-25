"""ContextCompressor and LLMContextCompressorOptimizer without an LLM (#1806).

These were script-style checks that caught every exception and returned
True/False, so pytest passed them whatever happened; two had been failing
silently (``compress()`` is async, and the estimator method is
``estimate_messages``). They now assert.
"""

import asyncio

from praisonaiagents.context.compressor import ContextCompressor
from praisonaiagents.context.optimizer import LLMContextCompressorOptimizer
from praisonaiagents.context.tokens import estimate_messages_tokens, get_estimator


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
    
    original_tokens = estimate_messages_tokens(messages)
    
    # Test ContextCompressor with fallback (no LLM)
    compressor = ContextCompressor(llm=None, enable_session_tracking=True)
    
    result = asyncio.run(compressor.compress(
        messages=messages,
        summary_target_tokens=150,
        protect_last_n_tokens=500
    ))

    assert len(result.messages) < len(messages)
    assert result.final_tokens < original_tokens
    assert result.tokens_saved > 0


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
    
    original_tokens = estimate_messages_tokens(messages)

    # Under the target: returned untouched, no summary.
    result_messages, result = LLMContextCompressorOptimizer(llm_client=None).optimize(
        messages, target_tokens=original_tokens + 1
    )
    assert result_messages == messages
    assert result.tokens_saved == 0 and not result.summary_added

    # Over the target with a small protected tail: the middle is summarised.
    optimizer = LLMContextCompressorOptimizer(
        llm_client=None, protect_last_n_tokens=10, summary_target_tokens=50
    )
    result_messages, result = optimizer.optimize(messages, target_tokens=original_tokens // 2)

    assert len(result_messages) < len(messages)
    assert result.tokens_saved > 0
    assert result.optimized_tokens < original_tokens
    assert result.summary_added
    assert result_messages[0] == messages[0]


def test_tokenization_improvements():
    """Test the improved tokenization features."""
    
    test_message = {
        "role": "assistant",
        "content": "This is a test message for tokenization with various words and punctuation!"
    }

    for use_accurate in (False, True):
        tokens = get_estimator(use_accurate=use_accurate).estimate_messages([test_message])
        assert isinstance(tokens, int) and tokens > 0, use_accurate

