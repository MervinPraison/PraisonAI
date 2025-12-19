"""
Codex CLI Integration Example

Demonstrates how to use OpenAI Codex CLI as an agent tool in PraisonAI.
"""

import asyncio
from praisonai.integrations import CodexCLIIntegration

async def main():
    # Create Codex CLI integration
    codex = CodexCLIIntegration(
        workspace=".",
        full_auto=True,
        sandbox="danger-full-access",
        json_output=True
    )
    
    # Check availability
    print(f"Codex CLI available: {codex.is_available}")
    print(f"Full Auto: {codex.full_auto}")
    print(f"Sandbox: {codex.sandbox}")
    
    # Execute a coding task
    result = await codex.execute("List files in the current directory")
    print(f"Result: {result}")
    
    # Stream JSON events
    print("\nStreaming events:")
    async for event in codex.stream("Explain the project"):
        event_type = event.get("type", "")
        if event_type == "item.completed":
            print(f"  {event}")

if __name__ == "__main__":
    asyncio.run(main())
