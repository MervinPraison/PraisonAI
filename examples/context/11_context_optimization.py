#!/usr/bin/env python3
"""
Context Optimization Example

Demonstrates how to use various optimization strategies to reduce
context size when approaching model limits.
"""

from praisonaiagents.context import (
    get_optimizer,
    OptimizerStrategy,
    TruncateOptimizer,
    SlidingWindowOptimizer,
    PruneToolsOptimizer,
    SmartOptimizer,
    estimate_messages_tokens,
)


def main():
    print("=" * 60)
    print("Context Optimization Example")
    print("=" * 60)
    
    # Create sample conversation with tool calls
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant with access to tools."},
        {"role": "user", "content": "What's the weather in Paris?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "Weather in Paris: 15°C, partly cloudy, humidity 65%, wind 10 km/h from the west. Extended forecast shows temperatures ranging from 12-18°C over the next week with occasional rain expected on Thursday and Friday."},
        {"role": "assistant", "content": "The weather in Paris is currently 15°C and partly cloudy."},
        {"role": "user", "content": "What about London?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_2", "function": {"name": "get_weather", "arguments": '{"city": "London"}'}}]},
        {"role": "tool", "tool_call_id": "call_2", "content": "Weather in London: 12°C, overcast with light drizzle, humidity 80%, wind 15 km/h from the southwest. Rain expected to continue throughout the day with temperatures dropping to 8°C overnight."},
        {"role": "assistant", "content": "London is 12°C with light drizzle."},
    ]
    
    # Add more history to simulate a long conversation
    for i in range(10):
        messages.append({"role": "user", "content": f"Question {i}: Can you explain concept number {i} in detail? " * 20})
        messages.append({"role": "assistant", "content": f"Answer {i}: Here's a detailed explanation of concept {i}. " * 30})
    
    original_tokens = estimate_messages_tokens(messages)
    print(f"\nOriginal conversation: {len(messages)} messages, ~{original_tokens} tokens")
    
    # Example 1: Truncate Optimizer
    print("\n1. Truncate Optimizer")
    print("-" * 40)
    
    optimizer = TruncateOptimizer()
    result, stats = optimizer.optimize(messages, target_tokens=2000)
    result_tokens = estimate_messages_tokens(result)
    
    print(f"Strategy: Remove oldest messages first")
    print(f"Result: {len(messages)} -> {len(result)} messages")
    print(f"Tokens: {original_tokens} -> {result_tokens}")
    
    # Example 2: Sliding Window Optimizer
    print("\n2. Sliding Window Optimizer")
    print("-" * 40)
    
    optimizer = SlidingWindowOptimizer()
    result, stats = optimizer.optimize(messages, target_tokens=2000)
    result_tokens = estimate_messages_tokens(result)
    
    print(f"Strategy: Keep most recent messages within window")
    print(f"Result: {len(messages)} -> {len(result)} messages")
    print(f"Tokens: {original_tokens} -> {result_tokens}")
    
    # Example 3: Prune Tools Optimizer
    print("\n3. Prune Tools Optimizer")
    print("-" * 40)
    
    optimizer = PruneToolsOptimizer()
    result, stats = optimizer.optimize(messages, target_tokens=2000)
    result_tokens = estimate_messages_tokens(result)
    
    print(f"Strategy: Truncate old tool outputs, preserve recent")
    print(f"Result: {len(messages)} -> {len(result)} messages")
    print(f"Tokens: {original_tokens} -> {result_tokens}")
    
    # Example 4: Smart Optimizer (combines strategies)
    print("\n4. Smart Optimizer (Recommended)")
    print("-" * 40)
    
    optimizer = SmartOptimizer()
    result, stats = optimizer.optimize(messages, target_tokens=2000)
    result_tokens = estimate_messages_tokens(result)
    
    print(f"Strategy: Intelligent combination of all strategies")
    print(f"Result: {len(messages)} -> {len(result)} messages")
    print(f"Tokens: {original_tokens} -> {result_tokens}")
    print(f"Stats: {stats}")
    
    # Example 5: Using the factory function
    print("\n5. Optimizer Factory")
    print("-" * 40)
    
    strategies = [
        OptimizerStrategy.TRUNCATE,
        OptimizerStrategy.SLIDING_WINDOW,
        OptimizerStrategy.PRUNE_TOOLS,
        OptimizerStrategy.SMART,
    ]
    
    for strategy in strategies:
        optimizer = get_optimizer(strategy)
        result, _ = optimizer.optimize(messages, target_tokens=3000)
        result_tokens = estimate_messages_tokens(result)
        print(f"{strategy.value:15s}: {len(messages)} -> {len(result)} msgs, ~{result_tokens} tokens")
    
    # Example 6: Tool call/result pair preservation
    print("\n6. Tool Call/Result Pair Preservation")
    print("-" * 40)
    
    tool_messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Get data"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1"}]},
        {"role": "tool", "tool_call_id": "tc1", "content": "Data result"},
        {"role": "assistant", "content": "Here's the data."},
    ]
    
    optimizer = SmartOptimizer()
    result, _ = optimizer.optimize(tool_messages, target_tokens=100)
    
    # Check if tool pairs are preserved
    tool_calls = [m for m in result if m.get("tool_calls")]
    tool_results = [m for m in result if m.get("role") == "tool"]
    
    print(f"Original: {len(tool_messages)} messages")
    print(f"Optimized: {len(result)} messages")
    print(f"Tool calls preserved: {len(tool_calls)}")
    print(f"Tool results preserved: {len(tool_results)}")
    
    print("\n" + "=" * 60)
    print("✓ Context optimization examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
