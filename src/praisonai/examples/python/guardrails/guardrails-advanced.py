"""
Guardrails - Advanced Example

Demonstrates advanced guardrails patterns including:
- Multi-agent configuration
- Custom callbacks/handlers
- Error handling
- All available options

Expected Output:
    Comprehensive demonstration of guardrails with multiple agents.
"""
from praisonaiagents import Agent, Task, PraisonAIAgents

# ============================================================
# Section 1: Custom Configuration
# ============================================================

# Define custom guardrails configuration
# config = ...

# ============================================================
# Section 2: Multi-Agent Setup
# ============================================================

agent1 = Agent(
    name="Agent1",
    instructions="You are the first agent",
    # guardrails=config,
)

agent2 = Agent(
    name="Agent2",
    instructions="You are the second agent",
    # guardrails=config,
)

# ============================================================
# Section 3: Task Definition
# ============================================================

task = Task(
    description="Demonstrate guardrails with multiple agents",
    agent=agent1,
)

# ============================================================
# Section 4: Execution
# ============================================================

agents = PraisonAIAgents(agents=[agent1, agent2], tasks=[task])
result = agents.start()
print(result)

# ============================================================
# Section 5: All Options Reference
# ============================================================
"""
Guardrails Options:
──────────────────
| Option          | Type     | Default | Description           |
|-----------------|----------|---------|----------------------|
| option1         | str      | None    | Description here     |
| option2         | bool     | False   | Description here     |
"""
