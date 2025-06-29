# Agent Handoffs

Agent handoffs allow agents to delegate tasks to other specialized agents. This is useful when you have agents with different areas of expertise that need to collaborate.

## Basic Usage

```python
from praisonaiagents import Agent, handoff

# Create specialized agents
billing_agent = Agent(name="Billing Agent", role="Billing Specialist")
refund_agent = Agent(name="Refund Agent", role="Refund Specialist")

# Create main agent with handoffs
triage_agent = Agent(
    name="Triage Agent",
    role="Customer Service",
    handoffs=[billing_agent, refund_agent]  # Can hand off to these agents
)
```

## How Handoffs Work

1. Handoffs are automatically converted to tools that the agent can use
2. The agent decides when to hand off based on the conversation context
3. When a handoff occurs, the target agent receives the conversation history
4. The target agent's response is returned to the user

## Advanced Features

### Custom Handoff Configuration

Use the `handoff()` function for more control:

```python
from praisonaiagents import Agent, handoff

agent = Agent(name="Target Agent")

custom_handoff = handoff(
    agent=agent,
    tool_name_override="escalate_to_specialist",
    tool_description_override="Escalate complex issues to a specialist",
    on_handoff=lambda ctx: print(f"Handoff from {ctx.name}"),
    input_filter=handoff_filters.remove_all_tools
)

main_agent = Agent(
    name="Main Agent",
    handoffs=[custom_handoff]
)
```

### Handoff Callbacks

Execute custom logic when a handoff occurs:

```python
# Create target agent
target_agent = Agent(name="Target Agent", role="Specialist")

def log_handoff(source_agent):
    print(f"Handoff initiated from {source_agent.name}")

handoff_with_callback = handoff(
    target_agent,
    on_handoff=log_handoff
)
```

### Structured Input

Require specific data when handing off:

```python
from pydantic import BaseModel

class EscalationData(BaseModel):
    reason: str
    priority: str

# Create escalation agent
escalation_agent = Agent(name="Escalation Agent", role="Senior Manager")

def handle_escalation(source_agent, data: EscalationData):
    print(f"Escalation: {data.reason} (Priority: {data.priority})")

escalation_handoff = handoff(
    escalation_agent,
    on_handoff=handle_escalation,
    input_type=EscalationData
)
```

### Input Filters

Control what conversation history is passed to the target agent:

```python
from praisonaiagents import handoff_filters

# Create target agent for filtering examples
agent = Agent(name="Target Agent", role="Specialist")

# Remove all tool calls from history
filtered_handoff = handoff(
    agent,
    input_filter=handoff_filters.remove_all_tools
)

# Keep only last N messages
limited_handoff = handoff(
    agent,
    input_filter=handoff_filters.keep_last_n_messages(5)
)

# Remove system messages
clean_handoff = handoff(
    agent,
    input_filter=handoff_filters.remove_system_messages
)
```

## Recommended Prompts

Include handoff instructions in your agent prompts:

```python
from praisonaiagents import RECOMMENDED_PROMPT_PREFIX, prompt_with_handoff_instructions

# Create specialized agents
billing_agent = Agent(name="Billing Agent", role="Billing Specialist")
technical_agent = Agent(name="Technical Agent", role="Technical Support")

agent = Agent(
    name="Support Agent",
    handoffs=[billing_agent, technical_agent]
)

# After creating the agent, update its instructions
agent.instructions = prompt_with_handoff_instructions(
    "Help customers and transfer to specialists when needed.",
    agent  # Pass the agent to auto-generate handoff info
)
```

## Complete Example

See the examples directory for complete working examples:
- `examples/handoff_basic.py` - Simple handoff demonstration
- `examples/handoff_advanced.py` - Advanced features with callbacks and filters
- `examples/handoff_customer_service.py` - Real-world customer service workflow

## Best Practices

1. **Clear Role Definition**: Give each agent a clear role and area of expertise
2. **Handoff Instructions**: Include when to hand off in agent instructions
3. **Context Preservation**: Use input filters carefully to maintain necessary context
4. **Logging**: Use callbacks to track handoffs for debugging and analytics
5. **Testing**: Test handoff paths to ensure smooth transitions

## Backward Compatibility

The handoff feature is fully backward compatible:
- Existing agents work without modification
- The `handoffs` parameter is optional
- All existing agent functionality is preserved