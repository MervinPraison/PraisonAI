"""
Injected State Example - PraisonAI Agents

Demonstrates injecting agent state into tools without exposing it in the schema.
"""

from praisonaiagents import Agent, tool
from praisonaiagents.tools import Injected
from praisonaiagents.tools.injected import AgentState, with_injection_context

# Tool with injected state - state param is NOT in the public schema
@tool
def show_context(query: str, state: Injected[dict]) -> str:
    """Show the current agent context."""
    session_id = state.get('session_id', 'unknown')
    agent_id = state.get('agent_id', 'unknown')
    return f"Query: {query}, Session: {session_id}, Agent: {agent_id}"

# Create agent with the tool
agent = Agent(
    name="ContextBot",
    instructions="You help show context information.",
    tools=[show_context],
    session_id="my-session-123"
)

if __name__ == "__main__":
    # Verify injected param is not in schema
    schema = show_context.get_schema()
    params = schema['function']['parameters']['properties']
    print(f"Schema params: {list(params.keys())}")
    assert 'state' not in params, "state should NOT be in schema"
    print("✓ 'state' correctly excluded from schema")
    
    # Test with manual injection context
    mock_state = AgentState(
        agent_id="test-agent",
        run_id="run-1",
        session_id="session-abc"
    )
    
    with with_injection_context(mock_state):
        result = show_context(query="hello")
        print(f"Result: {result}")
    
    # Test via agent.execute_tool
    result = agent.execute_tool("show_context", {"query": "test"})
    print(f"Agent result: {result}")
    
    print("\n✓ Injected state example complete")
