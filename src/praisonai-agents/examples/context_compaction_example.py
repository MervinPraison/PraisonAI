#!/usr/bin/env python3
"""
Context Compaction Example - Python API

Demonstrates how to configure context compaction policies in PraisonAI agents.
This provides examples for CLI/YAML parity.
"""

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.context.adapters import ContextCompactionPolicyAdapter
from praisonaiagents.context.protocols import CompactionStrategy


def example_default_behavior():
    """Example 1: Default behavior (during deprecation period)."""
    print("=== Example 1: Default Behavior ===")
    
    # Currently defaults to False with deprecation warning
    agent = Agent(
        name="default_agent",
        instructions="You are a helpful assistant."
    )
    
    print(f"Context compaction enabled: {agent.execution.context_compaction}")
    print("Note: Currently False during deprecation period, will change to True in next release\n")


def example_explicit_disable():
    """Example 2: Explicitly disable context compaction."""
    print("=== Example 2: Explicitly Disabled ===")
    
    agent = Agent(
        name="no_compaction_agent",
        instructions="You are a helpful assistant.",
        execution=ExecutionConfig(context_compaction=False)
    )
    
    print(f"Context compaction enabled: {agent.execution.context_compaction}")
    print("No automatic compaction will occur\n")


def example_default_policy():
    """Example 3: Use default compaction policy."""
    print("=== Example 3: Default Policy ===")
    
    agent = Agent(
        name="default_policy_agent", 
        instructions="You are a helpful assistant.",
        execution=ExecutionConfig(context_compaction=True)
    )
    
    print(f"Context compaction enabled: {agent.execution.context_compaction}")
    print("Will use balanced default policy (trigger at 90%, preserve 5 recent turns)\n")


def example_conservative_policy():
    """Example 4: Conservative compaction policy."""
    print("=== Example 4: Conservative Policy ===")
    
    conservative_policy = ContextCompactionPolicyAdapter(
        trigger_at=0.80,  # Trigger at 80% capacity
        strategy=CompactionStrategy.DROP_OLDEST_TOOLS,
        preserve_last_n_turns=8,  # Keep more conversation history
        target_utilization=0.60,  # Target 60% utilization after compaction
        aggressive_tool_truncation=False
    )
    
    agent = Agent(
        name="conservative_agent",
        instructions="You are a helpful assistant.",
        execution=ExecutionConfig(context_compaction=conservative_policy)
    )
    
    print(f"Policy trigger: {conservative_policy.trigger_at}")
    print(f"Strategy: {conservative_policy.strategy}")
    print(f"Preserve turns: {conservative_policy.preserve_last_n_turns}")
    print(f"Target utilization: {conservative_policy.target_utilization}\n")


def example_aggressive_policy():
    """Example 5: Aggressive compaction policy."""
    print("=== Example 5: Aggressive Policy ===")
    
    aggressive_policy = ContextCompactionPolicyAdapter(
        trigger_at=0.95,  # Wait until 95% capacity
        strategy=CompactionStrategy.SUMMARISE,  # Use LLM summarization  
        preserve_last_n_turns=3,  # Keep only recent exchanges
        target_utilization=0.75,  # Target higher utilization 
        aggressive_tool_truncation=True,  # Truncate large tool outputs
        model_overrides={
            "gpt-4": {"trigger_at": 0.92},  # Different threshold for gpt-4
            "claude-3": {"trigger_at": 0.88}
        }
    )
    
    agent = Agent(
        name="aggressive_agent",
        instructions="You are a helpful assistant.",
        execution=ExecutionConfig(context_compaction=aggressive_policy)
    )
    
    print(f"Policy trigger: {aggressive_policy.trigger_at}")
    print(f"Strategy: {aggressive_policy.strategy}")  
    print(f"Preserve turns: {aggressive_policy.preserve_last_n_turns}")
    print(f"Model overrides: {aggressive_policy.model_overrides}\n")


def example_yaml_config():
    """Example 6: YAML configuration equivalent."""
    print("=== Example 6: YAML Configuration Equivalent ===")
    print("""
# agent_config.yaml
name: "helpful_agent"
instructions: "You are a helpful assistant."
llm: "gpt-4o-mini"
execution:
  context_compaction:
    trigger_at: 0.85
    strategy: "drop_oldest_tools"
    preserve_last_n_turns: 6
    target_utilization: 0.65
    aggressive_tool_truncation: true
    model_overrides:
      "gpt-4":
        trigger_at: 0.90
        strategy: "summarise"
""")
    
    # Python equivalent:
    policy = ContextCompactionPolicyAdapter(
        trigger_at=0.85,
        strategy="drop_oldest_tools",
        preserve_last_n_turns=6,
        target_utilization=0.65,
        aggressive_tool_truncation=True,
        model_overrides={
            "gpt-4": {
                "trigger_at": 0.90,
                "strategy": "summarise"
            }
        }
    )
    
    agent = Agent(
        name="helpful_agent",
        instructions="You are a helpful assistant.",
        llm="gpt-4o-mini",
        execution=ExecutionConfig(context_compaction=policy)
    )
    
    print(f"Loaded policy trigger: {policy.trigger_at}")
    print(f"Loaded strategy: {policy.strategy}\n")


def example_cli_equivalent():
    """Example 7: CLI equivalent commands."""
    print("=== Example 7: CLI Equivalent ===")
    print("""
# Basic usage (will use default policy when enabled)
praisonai agent run --name "assistant" --instructions "Be helpful"

# Disable compaction explicitly  
praisonai agent run --name "assistant" --execution '{"context_compaction": false}'

# Use conservative policy
praisonai agent run --name "assistant" \\
    --execution '{
        "context_compaction": {
            "trigger_at": 0.80,
            "strategy": "drop_oldest_tools",
            "preserve_last_n_turns": 8
        }
    }'

# Load from YAML config file
praisonai agent run --config agent_config.yaml
""")


def example_serialization_round_trip():
    """Example 8: Serialization round-trip."""
    print("=== Example 8: Serialization Round-Trip ===")
    
    # Create agent with custom policy
    original_policy = ContextCompactionPolicyAdapter(
        trigger_at=0.88,
        strategy=CompactionStrategy.SUMMARISE
    )
    
    config = ExecutionConfig(context_compaction=original_policy)
    
    # Serialize to dict (for JSON/YAML storage)
    config_dict = config.to_dict()
    print(f"Serialized context_compaction type: {type(config_dict['context_compaction'])}")
    
    # Deserialize back to object
    restored_config = ExecutionConfig.from_dict(config_dict)
    restored_policy = restored_config.context_compaction
    
    print(f"Restored policy type: {type(restored_policy)}")
    print(f"Attributes preserved: trigger_at={restored_policy.trigger_at}, strategy={restored_policy.strategy}")
    print("✓ Round-trip serialization successful\n")


if __name__ == "__main__":
    print("Context Compaction Configuration Examples\n")
    print("=" * 50)
    
    try:
        example_default_behavior()
        example_explicit_disable()
        example_default_policy()
        example_conservative_policy()
        example_aggressive_policy()
        example_yaml_config()
        example_cli_equivalent()
        example_serialization_round_trip()
        
        print("=" * 50)
        print("✅ All examples completed successfully!")
        print("\nFor more information, see:")
        print("- Documentation: https://docs.praisonai.com/context-compaction")
        print("- Examples: examples/context_compaction_example.py")
        
    except Exception as e:
        print(f"❌ Example failed: {e}")
        import traceback
        traceback.print_exc()