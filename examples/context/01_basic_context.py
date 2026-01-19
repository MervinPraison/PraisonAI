"""
Basic Context Management Example

Demonstrates enabling context management with ContextConfig.
This manages token budgets, auto-compaction, and prevents context overflow.
"""

from praisonaiagents import Agent
from praisonaiagents.context import ContextConfig, OptimizerStrategy

# Example 1: Enable context with defaults
agent_basic = Agent(
    name="Assistant",
    instructions="You are a helpful assistant",
    context=True  # Auto-compact at 80% utilization
)

# Example 2: Custom configuration
agent_custom = Agent(
    name="CustomAgent",
    instructions="You are a helpful assistant with custom context settings",
    context=ContextConfig(
        auto_compact=True,
        compact_threshold=0.8,      # Trigger at 80% utilization
        strategy=OptimizerStrategy.SMART,
        output_reserve=8000,        # Reserve tokens for output
        keep_recent_turns=5,        # Always keep last 5 turns
        tool_output_max=10000,      # Max tokens per tool output
    )
)

# Example 3: Sliding window strategy
agent_sliding = Agent(
    name="SlidingAgent",
    instructions="You are a helpful assistant using sliding window",
    context=ContextConfig(
        strategy=OptimizerStrategy.SLIDING_WINDOW,
        keep_recent_turns=10,       # Keep last 10 turns
    )
)

if __name__ == "__main__":
    print("=== Basic Context Example ===")
    print("Context management is automatically enabled.")
    print()
    
    # Test basic agent
    result = agent_basic.chat("Hello! What is 2 + 2?")
    print(f"Response: {result}")
    print()
    
    # Show context config
    print("=== Context Configuration ===")
    config = ContextConfig(
        auto_compact=True,
        compact_threshold=0.8,
        strategy=OptimizerStrategy.SMART,
    )
    print(f"Config: {config.to_dict()}")
