#!/usr/bin/env python3
"""
Basic Context Compaction Example for PraisonAI Agents.

This example demonstrates how to use context compaction to:
1. Manage conversation context length
2. Use different compaction strategies
3. Track compaction results
4. Preserve important messages

Usage:
    python basic_compaction.py
"""

from praisonaiagents.compaction import (
    ContextCompactor, CompactionConfig, CompactionStrategy, CompactionResult
)


def main():
    print("=" * 60)
    print("Context Compaction Demo")
    print("=" * 60)
    
    # ==========================================================================
    # Sample Messages
    # ==========================================================================
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "Hello! Can you help me with Python?"},
        {"role": "assistant", "content": "Of course! I'd be happy to help you with Python. What would you like to know?"},
        {"role": "user", "content": "How do I read a file in Python?"},
        {"role": "assistant", "content": "To read a file in Python, you can use the built-in open() function. Here's an example:\n\nwith open('filename.txt', 'r') as f:\n    content = f.read()\n\nThis opens the file, reads its content, and automatically closes it."},
        {"role": "user", "content": "What about writing to a file?"},
        {"role": "assistant", "content": "To write to a file, use the 'w' mode:\n\nwith open('filename.txt', 'w') as f:\n    f.write('Hello, World!')\n\nUse 'a' mode to append instead of overwriting."},
        {"role": "user", "content": "Can you explain list comprehensions?"},
        {"role": "assistant", "content": "List comprehensions are a concise way to create lists. Instead of:\n\nresult = []\nfor x in range(10):\n    result.append(x * 2)\n\nYou can write:\n\nresult = [x * 2 for x in range(10)]"},
    ]
    
    print(f"\n--- Original Messages ---")
    print(f"  Message count: {len(messages)}")
    
    # ==========================================================================
    # Basic Compaction
    # ==========================================================================
    print("\n--- Basic Compaction (Truncate Strategy) ---")
    
    compactor = ContextCompactor(
        max_tokens=50,  # Low limit to trigger compaction
        strategy=CompactionStrategy.TRUNCATE,
        preserve_system=True,
        preserve_recent=2
    )
    
    # Check stats before
    stats = compactor.get_stats(messages)
    print(f"  Total tokens: {stats['total_tokens']}")
    print(f"  Max tokens: {stats['max_tokens']}")
    print(f"  Needs compaction: {stats['needs_compaction']}")
    
    # Compact
    compacted, result = compactor.compact(messages)
    
    print(f"\n  After compaction:")
    print(f"    Messages: {len(messages)} -> {len(compacted)}")
    print(f"    Tokens: {result.original_tokens} -> {result.compacted_tokens}")
    print(f"    Saved: {result.tokens_saved} tokens")
    print(f"    Compression: {result.compression_ratio:.1%}")
    
    # ==========================================================================
    # Sliding Window Strategy
    # ==========================================================================
    print("\n--- Sliding Window Strategy ---")
    
    compactor = ContextCompactor(
        max_tokens=50,
        strategy=CompactionStrategy.SLIDING,
        preserve_system=True,
        preserve_recent=3
    )
    
    compacted, result = compactor.compact(messages)
    
    print(f"  Messages kept: {result.messages_kept}")
    print(f"  Messages removed: {result.messages_removed}")
    print(f"  Strategy: {result.strategy_used.value}")
    
    # ==========================================================================
    # Summarize Strategy
    # ==========================================================================
    print("\n--- Summarize Strategy ---")
    
    compactor = ContextCompactor(
        max_tokens=50,
        strategy=CompactionStrategy.SUMMARIZE,
        preserve_system=True,
        preserve_recent=2
    )
    
    compacted, result = compactor.compact(messages)
    
    print(f"  Messages kept: {result.messages_kept}")
    print(f"  Strategy: {result.strategy_used.value}")
    
    # Show what messages remain
    print(f"\n  Remaining message roles:")
    for msg in compacted:
        role = msg.get("role", "unknown")
        content_preview = msg.get("content", "")[:50]
        print(f"    [{role}] {content_preview}...")
    
    # ==========================================================================
    # No Compaction Needed
    # ==========================================================================
    print("\n--- No Compaction Needed ---")
    
    compactor = ContextCompactor(
        max_tokens=10000,  # High limit
        strategy=CompactionStrategy.TRUNCATE
    )
    
    compacted, result = compactor.compact(messages)
    
    print(f"  Was compacted: {result.was_compacted}")
    print(f"  Messages unchanged: {len(compacted) == len(messages)}")
    
    # ==========================================================================
    # Result Serialization
    # ==========================================================================
    print("\n--- Result Serialization ---")
    
    compactor = ContextCompactor(max_tokens=50)
    _, result = compactor.compact(messages)
    
    data = result.to_dict()
    print(f"  Original tokens: {data['original_tokens']}")
    print(f"  Compacted tokens: {data['compacted_tokens']}")
    print(f"  Compression ratio: {data['compression_ratio']:.2f}")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
