"""
Cursor CLI Integration Example

Demonstrates how to use Cursor CLI as an agent tool in PraisonAI.
"""

import asyncio
from praisonai.integrations import CursorCLIIntegration

async def main():
    # Create Cursor CLI integration
    cursor = CursorCLIIntegration(
        workspace=".",
        output_format="json",
        force=True,
        model="gpt-5",
        stream_partial=True
    )
    
    # Check availability
    print(f"Cursor CLI available: {cursor.is_available}")
    print(f"Force mode: {cursor.force}")
    print(f"Model: {cursor.model}")
    
    # Execute a coding task
    result = await cursor.execute("List files in the current directory")
    print(f"Result: {result}")
    
    # Stream output
    print("\nStreaming output:")
    async for event in cursor.stream("Explain the project"):
        content = event.get("content", "")
        if content:
            print(content, end="", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
