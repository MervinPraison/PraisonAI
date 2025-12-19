"""
Claude Code CLI Integration Example

Demonstrates how to use Claude Code CLI as an agent tool in PraisonAI.
"""

import asyncio
from praisonai.integrations import ClaudeCodeIntegration

async def main():
    # Create Claude Code integration
    claude = ClaudeCodeIntegration(
        workspace=".",
        output_format="json",
        skip_permissions=True,
        system_prompt="Be concise and follow best practices",
        allowed_tools=["Read", "Write", "Bash"]
    )
    
    # Check availability
    print(f"Claude CLI available: {claude.is_available}")
    print(f"Claude SDK available: {claude.sdk_available}")
    
    # Execute a coding task
    result = await claude.execute("List all Python files in the current directory")
    print(f"Result: {result}")
    
    # Stream output
    print("\nStreaming output:")
    async for event in claude.stream("Explain the project structure"):
        print(event)

if __name__ == "__main__":
    asyncio.run(main())
