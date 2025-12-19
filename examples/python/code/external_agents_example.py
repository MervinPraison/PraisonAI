"""
External Agents Integration Example

Demonstrates how to use all external CLI integrations as agent tools.
"""

import asyncio
from praisonai.integrations import (
    ClaudeCodeIntegration,
    GeminiCLIIntegration,
    CodexCLIIntegration,
    CursorCLIIntegration,
    get_available_integrations
)

async def main():
    # Check availability of all integrations
    print("=== External CLI Integrations ===\n")
    
    availability = get_available_integrations()
    print("Availability:")
    for name, avail in availability.items():
        status = "✅" if avail else "❌"
        print(f"  {status} {name}")
    
    # Create integrations
    print("\n--- Claude Code ---")
    claude = ClaudeCodeIntegration(workspace=".", skip_permissions=True)
    print(f"CLI: {claude.cli_command}")
    print(f"Available: {claude.is_available}")
    tool = claude.as_tool()
    print(f"Tool: {tool.__name__}")
    
    print("\n--- Gemini CLI ---")
    gemini = GeminiCLIIntegration(workspace=".", model="gemini-2.5-flash")
    print(f"CLI: {gemini.cli_command}")
    print(f"Available: {gemini.is_available}")
    tool = gemini.as_tool()
    print(f"Tool: {tool.__name__}")
    
    print("\n--- Codex CLI ---")
    codex = CodexCLIIntegration(workspace=".", full_auto=True)
    print(f"CLI: {codex.cli_command}")
    print(f"Available: {codex.is_available}")
    tool = codex.as_tool()
    print(f"Tool: {tool.__name__}")
    
    print("\n--- Cursor CLI ---")
    cursor = CursorCLIIntegration(workspace=".", force=True)
    print(f"CLI: {cursor.cli_command}")
    print(f"Available: {cursor.is_available}")
    tool = cursor.as_tool()
    print(f"Tool: {tool.__name__}")
    
    print("\n=== All integrations ready ===")

if __name__ == "__main__":
    asyncio.run(main())
