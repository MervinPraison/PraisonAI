"""
Memory - Advanced Example

Demonstrates advanced memory patterns including:
- Multi-agent configuration
- Custom callbacks/handlers
- Error handling
- All available options

Expected Output:
    Comprehensive demonstration of memory with multiple agents.
"""
from praisonaiagents import Agent, Task, PraisonAIAgents, Memory, ResponseError

# ============================================================
# Section 1: Custom Configuration
# ============================================================
memory_config = Memory(
    store_size=10,   # Limit the memory to the last 10 interactions
    persist=True,    # Enable persistence across sessions
)

# ============================================================
# Section 2: Multi-Agent Setup
# ============================================================
agent1 = Agent(
    name="Agent1",
    instructions="You are the first agent",
    memory=memory_config,
)

agent2 = Agent(
    name="Agent2",
    instructions="You are the second agent",
    memory=memory_config,
)

# ============================================================
# Section 3: Task Definition
# ============================================================
task = Task(
    description="Demonstrate memory with multiple agents",
    agent=agent1,
)

# ============================================================
# Section 4: Execution
# ============================================================
try:
    agents = PraisonAIAgents(agents=[agent1, agent2], tasks=[task])
    result = agents.start()
    print(result)
except ResponseError as e:
    print(f"An error occurred: {e}")

# ============================================================
# Section 5: All Options Reference
# ============================================================
"""
Memory Options:
──────────────────
| Option          | Type     | Default | Description           |
|-----------------|----------|---------|----------------------|
| store_size      | int      | 10      | Maximum interactions to store in memory. |
| persist         | bool     | False   | Determines if memory is retained across sessions. |
| clear_on_error   | bool     | True    | Whether to clear memory upon encountering an error. |
"""
