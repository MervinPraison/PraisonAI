"""
Gemini CLI Integration Example

Demonstrates how to use Gemini CLI as an agent tool in PraisonAI.
"""

import asyncio
from praisonai.integrations import GeminiCLIIntegration

async def main():
    # Create Gemini CLI integration
    gemini = GeminiCLIIntegration(
        workspace=".",
        model="gemini-2.5-flash",
        output_format="json",
        include_directories=["../lib", "../docs"]
    )
    
    # Check availability
    print(f"Gemini CLI available: {gemini.is_available}")
    print(f"Model: {gemini.model}")
    
    # Execute a coding task
    result = await gemini.execute("Analyze the code structure")
    print(f"Result: {result}")
    
    # Execute with stats
    result, stats = await gemini.execute_with_stats("Explain main.py")
    print(f"Result: {result}")
    print(f"Stats: {stats}")

if __name__ == "__main__":
    asyncio.run(main())
