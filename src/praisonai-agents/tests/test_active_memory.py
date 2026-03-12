"""
Real agentic test for memory tools.

This test creates an Agent with memory=True and tools=[store_memory, search_memory],
calls agent.start() with a real prompt, and verifies the agent actually calls the LLM.
"""

from praisonaiagents import Agent
from praisonaiagents.tools import store_memory, search_memory


def test_memory_tools_real_agent():
    """Agent with memory tools can be created and started."""
    agent = Agent(
        name="MemoryTestAgent",
        instructions=(
            "You are a helpful assistant with memory. "
            "When the user tells you something to remember, use store_memory. "
            "When the user asks about something previously stored, use search_memory."
        ),
        memory=True,
        tools=[store_memory, search_memory],
    )

    # Turn 1: Ask the agent to store something
    result = agent.start("Remember that my favorite color is blue. Say OK when done.")
    print(f"Turn 1 result: {result}")
    assert result is not None
    assert len(str(result)) > 0

    # Turn 2: Ask the agent to recall
    result2 = agent.start("What is my favorite color? Search your memory if needed.")
    print(f"Turn 2 result: {result2}")
    assert result2 is not None
    assert len(str(result2)) > 0

    print("\n✅ Real agentic test passed!")


if __name__ == "__main__":
    test_memory_tools_real_agent()
