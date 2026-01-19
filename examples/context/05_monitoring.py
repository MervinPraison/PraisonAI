"""
Context Monitoring Example

Demonstrates monitoring context usage with logging and metrics.
"""

from praisonaiagents import Agent
from praisonaiagents.context import ContextConfig, MonitorConfig, OptimizerStrategy

# Example 1: Human-readable monitoring
agent_human = Agent(
    name="MonitoredAgent",
    instructions="You are a helpful assistant",
    context=ContextConfig(
        auto_compact=True,
        monitor=MonitorConfig(
            enabled=True,
            path="./context_logs/",
            format="human",           # Human-readable format
            frequency="turn",         # Log on every turn
            redact_sensitive=True,    # Redact sensitive data
            multi_agent_files=True,   # Separate files per agent
        )
    )
)

# Example 2: JSON monitoring (for parsing)
agent_json = Agent(
    name="JSONMonitorAgent",
    instructions="You are a helpful assistant",
    context=ContextConfig(
        monitor=MonitorConfig(
            enabled=True,
            path="./context_logs/",
            format="json",            # JSON format for parsing
            frequency="tool_call",    # Log on tool calls
        )
    )
)

# Example 3: Overflow-only monitoring
agent_overflow = Agent(
    name="OverflowAgent",
    instructions="You are a helpful assistant",
    context=ContextConfig(
        monitor=MonitorConfig(
            enabled=True,
            path="./context_logs/",
            format="human",
            frequency="overflow",     # Only log on overflow
        )
    )
)

if __name__ == "__main__":
    print("=== Context Monitoring Example ===")
    print()
    
    # Show monitor configuration
    config = MonitorConfig(
        enabled=True,
        path="./context_logs/",
        format="human",
        frequency="turn",
        redact_sensitive=True,
    )
    
    print("Monitor Config:")
    print(f"  enabled: {config.enabled}")
    print(f"  path: {config.path}")
    print(f"  format: {config.format}")
    print(f"  frequency: {config.frequency}")
    print(f"  redact_sensitive: {config.redact_sensitive}")
    print()
    
    print("Frequency options:")
    print("  'turn'      - Log on every conversation turn")
    print("  'tool_call' - Log when tools are called")
    print("  'manual'    - Manual logging only")
    print("  'overflow'  - Log only when context overflows")
    print()
    
    print("Format options:")
    print("  'human' - Human-readable format")
    print("  'json'  - JSON format for parsing")
