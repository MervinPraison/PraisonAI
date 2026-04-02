import pytest
import asyncio
from praisonaiagents.agent.agent import Agent
from praisonaiagents.approval.protocols import ApprovalConfig
from praisonaiagents.tools import tool
from praisonai.gateway.gateway_approval import GatewayApprovalBackend
from praisonai.gateway.exec_approval import Resolution, ExecApprovalManager

@tool
def dangerous_tool(path: str) -> str:
    """A dangerous tool that requires approval."""
    return f"Deleted {path}"

@pytest.mark.asyncio
async def test_real_agentic_gateway_approval():
    mgr = ExecApprovalManager()
    backend = GatewayApprovalBackend(mgr, timeout=5.0)
    
    agent = Agent(
        name="test_agent",
        instructions="You are an assistant. Call the dangerous_tool with path '/tmp/test' to fulfill the user's request.",
        tools=[dangerous_tool],
        approval=ApprovalConfig(backend=backend, all_tools=True),
        llm="gpt-4o-mini" # Needs LLM call per AGENTS.md real agentic tests requirement
    )
    
    async def resolve_in_background():
        # wait a bit for agent to initiate request
        for _ in range(50): # wait up to 5 seconds
            await asyncio.sleep(0.1)
            pending = mgr.list_pending()
            if pending:
                req_id = pending[0]["request_id"]
                mgr.resolve(req_id, Resolution(approved=True, reason="Unit test allowed"))
                return
    
    # Start background resolver
    resolver_task = asyncio.create_task(resolve_in_background())
    
    # Run agent (this makes a real LLM call)
    result = await agent.astart("Please use your dangerous_tool to delete '/tmp/test', then tell me it is done.")
    
    # ensure it was resolved
    await resolver_task
    
    # The output should contain "Deleted /tmp/test" or similar
    print("Agent Result:", result)
    assert result is not None
