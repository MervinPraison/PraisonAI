"""
Compaction Strategies Example

Demonstrates different context compaction strategies.
"""

from praisonaiagents import Agent
from praisonaiagents.context import ContextConfig, OptimizerStrategy

# Strategy 1: TRUNCATE - Fast, removes oldest messages
agent_truncate = Agent(
    name="TruncateAgent",
    instructions="You are a helpful assistant",
    context=ContextConfig(
        strategy=OptimizerStrategy.TRUNCATE,
        compact_threshold=0.8,
    )
)

# Strategy 2: SLIDING_WINDOW - Keeps recent N turns
agent_sliding = Agent(
    name="SlidingAgent",
    instructions="You are a helpful assistant",
    context=ContextConfig(
        strategy=OptimizerStrategy.SLIDING_WINDOW,
        keep_recent_turns=10,
    )
)

# Strategy 3: SMART - Importance-based (default)
agent_smart = Agent(
    name="SmartAgent",
    instructions="You are a helpful assistant",
    context=ContextConfig(
        strategy=OptimizerStrategy.SMART,  # Default
        compact_threshold=0.8,
    )
)

# Strategy 4: PRUNE_TOOLS - Truncate old tool outputs
agent_prune = Agent(
    name="PruneAgent",
    instructions="You are a helpful assistant with tools",
    context=ContextConfig(
        strategy=OptimizerStrategy.PRUNE_TOOLS,
        tool_output_max=5000,  # Max tokens per tool output
    )
)

# Strategy 5: NON_DESTRUCTIVE - Only prune tools, keep all history
agent_safe = Agent(
    name="SafeAgent",
    instructions="You are a helpful assistant (safety-critical)",
    context=ContextConfig(
        strategy=OptimizerStrategy.NON_DESTRUCTIVE,
    )
)

if __name__ == "__main__":
    print("=== Compaction Strategies Example ===")
    print()
    
    strategies = [
        ("TRUNCATE", OptimizerStrategy.TRUNCATE, "Remove oldest messages"),
        ("SLIDING_WINDOW", OptimizerStrategy.SLIDING_WINDOW, "Keep last N turns"),
        ("SMART", OptimizerStrategy.SMART, "Importance-based (default)"),
        ("PRUNE_TOOLS", OptimizerStrategy.PRUNE_TOOLS, "Truncate tool outputs"),
        ("NON_DESTRUCTIVE", OptimizerStrategy.NON_DESTRUCTIVE, "Only prune tools"),
    ]
    
    for name, strategy, description in strategies:
        print(f"  {name:20} - {description}")
    
    print()
    print("Usage:")
    print("  context=ContextConfig(strategy=OptimizerStrategy.SLIDING_WINDOW)")
