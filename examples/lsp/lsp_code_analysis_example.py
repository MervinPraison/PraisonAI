"""
LSP Code Intelligence Example

This example demonstrates how to use LSP-powered tools through an Agent
for semantic code analysis (listing symbols, finding definitions, etc.).

How to run:
    export OPENAI_API_KEY=your_key
    python examples/lsp/lsp_code_analysis_example.py

Prerequisites:
    pip install praisonai praisonaiagents
    pip install python-lsp-server  # Optional, for full LSP support
"""

import asyncio
import os
import sys

# Add paths for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/praisonai'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/praisonai-agents'))


async def main():
    print("=" * 60)
    print("LSP CODE INTELLIGENCE EXAMPLE")
    print("=" * 60)
    print()
    
    # Import after path setup
    from praisonai.cli.features import (
        create_agent_centric_tools,
        InteractiveRuntime,
        RuntimeConfig
    )
    from praisonaiagents import Agent
    
    # Use the praisonaiagents source as workspace for analysis
    workspace = os.path.join(
        os.path.dirname(__file__), 
        '../../src/praisonai-agents/praisonaiagents'
    )
    workspace = os.path.abspath(workspace)
    
    print(f"Workspace: {workspace}")
    print()
    
    # 1. Create runtime with LSP enabled
    print("1. Creating InteractiveRuntime with LSP...")
    config = RuntimeConfig(
        workspace=workspace,
        lsp_enabled=True,  # Enable LSP for code intelligence
        acp_enabled=False,  # Disable ACP for this example
        approval_mode="auto"
    )
    runtime = InteractiveRuntime(config)
    status = await runtime.start()
    
    print(f"   LSP enabled: {status['lsp']['enabled']}")
    print(f"   LSP ready: {runtime.lsp_ready}")
    print(f"   LSP status: {status['lsp']['status']}")
    if not runtime.lsp_ready:
        print("   Note: LSP not available, will use regex fallback")
    print()
    
    # 2. Create agent-centric tools
    print("2. Creating agent-centric tools...")
    tools = create_agent_centric_tools(runtime)
    
    # Filter to show only LSP tools
    lsp_tools = [t for t in tools if t.__name__.startswith('lsp_')]
    print(f"   LSP tools available:")
    for tool in lsp_tools:
        print(f"     - {tool.__name__}")
    print()
    
    # 3. Create Agent with LSP-powered tools
    print("3. Creating Agent with LSP tools...")
    agent = Agent(
        name="CodeAnalyzer",
        instructions="""You are a code analysis assistant.
        Use lsp_list_symbols to list functions and classes in files.
        Use lsp_find_definition to find where symbols are defined.
        Use lsp_find_references to find where symbols are used.
        Provide clear, organized summaries of code structure.""",
        tools=tools,
        verbose=True
    )
    print()
    
    # 4. Test 1: List symbols in a file
    print("4. TEST 1: List symbols in agent/agent.py")
    print("-" * 50)
    result1 = agent.start("List all the main classes and public methods in agent/agent.py. Give me a brief summary.")
    print("-" * 50)
    print(f"Summary: {str(result1)[:300]}...")
    print()
    
    # 5. Test 2: Find definition of a symbol
    print("5. TEST 2: Find where 'Agent' class is defined")
    print("-" * 50)
    result2 = agent.start("Where is the Agent class defined? Use lsp_find_definition to find it.")
    print("-" * 50)
    print(f"Result: {str(result2)[:300]}...")
    print()
    
    # 6. Test 3: Analyze main.py
    print("6. TEST 3: Analyze main.py structure")
    print("-" * 50)
    result3 = agent.start("List all the functions in main.py and briefly describe what the file does.")
    print("-" * 50)
    print(f"Analysis: {str(result3)[:300]}...")
    print()
    
    # Cleanup
    await runtime.stop()
    
    print("=" * 60)
    print("EXAMPLE COMPLETE")
    print("=" * 60)
    print()
    print("Key takeaways:")
    print("- LSP tools work through the Agent (agentic LSP)")
    print("- Falls back to regex if LSP server not available")
    print("- Returns structured data with citations")


if __name__ == "__main__":
    asyncio.run(main())
