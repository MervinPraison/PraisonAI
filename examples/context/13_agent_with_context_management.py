#!/usr/bin/env python3
"""
Agent with Context Management Example

Demonstrates how to use context management features with a real Agent
making actual API calls.

Requires: OPENAI_API_KEY environment variable
"""

import os
from praisonaiagents import Agent
from praisonaiagents.context import (
    ContextBudgeter,
    ContextLedgerManager,
    get_optimizer,
    OptimizerStrategy,
    estimate_messages_tokens,
    format_percent,
)


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        return
    
    print("=" * 60)
    print("Agent with Context Management Example")
    print("=" * 60)
    
    # Initialize context management components
    budgeter = ContextBudgeter(model="gpt-4o-mini")
    ledger = ContextLedgerManager()
    optimizer = get_optimizer(OptimizerStrategy.SMART)
    
    # Get budget info
    budget = budgeter.allocate()
    print("\nModel: gpt-4o-mini")
    print(f"Context budget: {budget.usable:,} tokens")
    print(f"Output reserve: {budget.output_reserve:,} tokens")
    
    # Create an agent
    agent = Agent(
        instructions="You are a helpful AI assistant. Keep responses concise.",
        llm="gpt-4o-mini",
    )
    
    # Track the system prompt
    ledger.track_system_prompt(agent.instructions)
    print(f"\nSystem prompt tracked: {ledger.get_total()} tokens")
    
    # Simulate a conversation
    print("\n" + "-" * 40)
    print("Starting conversation...")
    print("-" * 40)
    
    conversation = []
    questions = [
        "What is Python?",
        "What are its main features?",
        "Give me a simple example.",
    ]
    
    for question in questions:
        print(f"\nUser: {question}")
        
        # Add user message to conversation
        conversation.append({"role": "user", "content": question})
        
        # Track in ledger
        ledger.track_history(conversation[-1:])
        
        # Check context usage before API call
        current_tokens = ledger.get_total()
        utilization = budgeter.get_utilization(current_tokens)
        
        print(f"[Context: {current_tokens} tokens, {format_percent(utilization)} used]")
        
        # Check if optimization needed
        if utilization > 0.8:
            print("[Warning: High context usage, optimizing...]")
            conversation, _ = optimizer.optimize(conversation, target_tokens=int(budget.usable * 0.7))
        
        # Make API call
        response = agent.chat(question)
        
        # Add assistant response to conversation
        conversation.append({"role": "assistant", "content": response})
        ledger.track_history(conversation[-1:])
        
        print(f"Assistant: {response[:200]}..." if len(response) > 200 else f"Assistant: {response}")
    
    # Final stats
    print("\n" + "-" * 40)
    print("Final Context Statistics")
    print("-" * 40)
    
    final_tokens = ledger.get_total()
    final_utilization = budgeter.get_utilization(final_tokens)
    
    print(f"Total tokens used: {final_tokens:,}")
    print(f"Context utilization: {format_percent(final_utilization)}")
    print(f"Messages in conversation: {len(conversation)}")
    print(f"Remaining capacity: {budgeter.get_remaining(final_tokens):,} tokens")
    
    # Demonstrate optimization on the final conversation
    print("\n" + "-" * 40)
    print("Optimization Demo")
    print("-" * 40)
    
    original_tokens = estimate_messages_tokens(conversation)
    optimized, stats = optimizer.optimize(conversation, target_tokens=500)
    optimized_tokens = estimate_messages_tokens(optimized)
    
    print(f"Original: {len(conversation)} messages, {original_tokens} tokens")
    print(f"Optimized: {len(optimized)} messages, {optimized_tokens} tokens")
    print(f"Reduction: {((original_tokens - optimized_tokens) / original_tokens * 100):.1f}%")
    
    print("\n" + "=" * 60)
    print("✓ Agent with context management example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
