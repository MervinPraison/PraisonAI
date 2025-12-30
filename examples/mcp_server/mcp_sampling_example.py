#!/usr/bin/env python3
"""
MCP Sampling Example

Demonstrates the Sampling API per MCP 2025-11-25 specification.
Sampling allows servers to request LLM completions from clients.

Features:
- Tool calling support with toolChoice modes
- Model preferences
- System prompts

Usage:
    python mcp_sampling_example.py
"""

import asyncio
from praisonai.mcp_server.sampling import (
    SamplingHandler,
    SamplingRequest,
    SamplingResponse,
    SamplingMessage,
    ToolChoice,
    ToolDefinition,
    ModelPreferences,
    create_sampling_request,
)


async def mock_llm_callback(request: SamplingRequest) -> SamplingResponse:
    """Mock LLM callback for demonstration."""
    # In real usage, this would call an actual LLM
    messages_text = " | ".join([f"{m.role}: {m.content}" for m in request.messages])
    
    if request.tools:
        # Simulate tool use response
        return SamplingResponse(
            role="assistant",
            content="",
            model="mock-model",
            stop_reason="toolUse",
            tool_calls=[{
                "id": "call_123",
                "name": request.tools[0].name,
                "arguments": {"query": "test"},
            }],
        )
    
    return SamplingResponse(
        role="assistant",
        content=f"Mock response to: {messages_text}",
        model="mock-model",
        stop_reason="end_turn",
    )


async def main():
    print("=" * 60)
    print("MCP Sampling Example (2025-11-25 Specification)")
    print("=" * 60)
    
    # Create handler with mock callback
    handler = SamplingHandler(default_model="gpt-4o-mini")
    handler.set_callback(mock_llm_callback)
    
    # 1. Basic sampling request
    print("\n1. Basic Sampling Request")
    print("-" * 40)
    
    basic_request = create_sampling_request(
        prompt="What is the capital of France?",
        system_prompt="You are a helpful geography assistant.",
        max_tokens=100,
    )
    
    print(f"   Messages: {[m.content for m in basic_request.messages]}")
    print(f"   System prompt: {basic_request.system_prompt}")
    print(f"   Max tokens: {basic_request.max_tokens}")
    
    response = await handler.create_message(basic_request)
    print(f"\n   Response: {response.content}")
    print(f"   Model: {response.model}")
    print(f"   Stop reason: {response.stop_reason}")
    
    # 2. Sampling with tools
    print("\n2. Sampling with Tools")
    print("-" * 40)
    
    tool_request = create_sampling_request(
        prompt="Search for the latest AI news",
        tools=[
            {
                "name": "web_search",
                "description": "Search the web for information",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                },
            }
        ],
        tool_choice="auto",
    )
    
    print(f"   Tools: {[t.name for t in tool_request.tools]}")
    print(f"   Tool choice: {tool_request.tool_choice.to_dict()}")
    
    response = await handler.create_message(tool_request)
    print(f"\n   Response stop reason: {response.stop_reason}")
    if response.tool_calls:
        print(f"   Tool calls: {response.tool_calls}")
    
    # 3. ToolChoice modes
    print("\n3. ToolChoice Modes (MCP 2025-11-25)")
    print("-" * 40)
    
    modes = [
        ("auto", ToolChoice.auto()),
        ("none", ToolChoice.none()),
        ("any", ToolChoice.any()),
        ("tool (specific)", ToolChoice.tool("web_search")),
    ]
    
    for name, tc in modes:
        print(f"   {name}: {tc.to_dict()}")
    
    # 4. Model preferences
    print("\n4. Model Preferences")
    print("-" * 40)
    
    prefs = ModelPreferences(
        hints=[{"name": "claude-3-sonnet"}, {"name": "gpt-4"}],
        cost_priority=0.3,
        speed_priority=0.5,
        intelligence_priority=0.8,
    )
    
    print(f"   Preferences: {prefs.to_dict()}")
    
    # 5. Full request with all options
    print("\n5. Full Request with All Options")
    print("-" * 40)
    
    full_request = SamplingRequest(
        messages=[
            SamplingMessage(role="user", content="Hello!"),
            SamplingMessage(role="assistant", content="Hi there!"),
            SamplingMessage(role="user", content="What can you do?"),
        ],
        system_prompt="You are a helpful assistant.",
        model_preferences=prefs,
        max_tokens=500,
        temperature=0.7,
        tools=[
            ToolDefinition(
                name="calculator",
                description="Perform calculations",
                input_schema={"type": "object", "properties": {"expression": {"type": "string"}}},
            )
        ],
        tool_choice=ToolChoice.auto(),
    )
    
    print(f"   Message count: {len(full_request.messages)}")
    print(f"   Has tools: {bool(full_request.tools)}")
    print(f"   Temperature: {full_request.temperature}")
    
    request_dict = full_request.to_dict()
    print(f"\n   MCP Request Format (keys): {list(request_dict.keys())}")
    
    print("\n" + "=" * 60)
    print("Sampling Example Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
