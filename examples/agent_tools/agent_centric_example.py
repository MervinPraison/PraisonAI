"""
Agent-Centric Tools Example

This example demonstrates how to use LSP/ACP-powered tools that make
the Agent the central orchestrator for file operations.

How to run:
    export OPENAI_API_KEY=your_key
    python examples/agent_tools/agent_centric_example.py

Prerequisites:
    pip install praisonai praisonaiagents
"""

import asyncio
import os
import sys
import tempfile
import shutil

# Add paths for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/praisonai'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/praisonai-agents'))


async def main():
    print("=" * 60)
    print("AGENT-CENTRIC TOOLS EXAMPLE")
    print("=" * 60)
    print()
    
    # Create temporary workspace
    workspace = tempfile.mkdtemp(prefix="praisonai_example_")
    print(f"Workspace: {workspace}")
    print()
    
    try:
        # Import after path setup
        from praisonai.cli.features import (
            create_agent_centric_tools,
            InteractiveRuntime,
            RuntimeConfig
        )
        from praisonaiagents import Agent
        
        # 1. Create runtime with ACP enabled
        print("1. Creating InteractiveRuntime with ACP...")
        config = RuntimeConfig(
            workspace=workspace,
            lsp_enabled=False,  # Skip LSP for this example
            acp_enabled=True,
            approval_mode="auto"  # Auto-approve for demo
        )
        runtime = InteractiveRuntime(config)
        status = await runtime.start()
        
        print(f"   ACP ready: {runtime.acp_ready}")
        print(f"   Read-only: {runtime.read_only}")
        print()
        
        # 2. Create agent-centric tools
        print("2. Creating agent-centric tools...")
        tools = create_agent_centric_tools(runtime)
        print(f"   Tools created: {len(tools)}")
        for tool in tools:
            print(f"     - {tool.__name__}")
        print()
        
        # 3. Create Agent with ACP-powered tools
        print("3. Creating Agent with ACP-powered tools...")
        agent = Agent(
            name="FileAgent",
            instructions="""You help create and manage files. 
            Use acp_create_file to create files.
            Use read_file to read files.
            Use list_files to list directory contents.""",
            tools=tools,
            output="verbose"  # Use new consolidated param
        )
        print()
        
        # 4. Ask agent to create a file
        print("4. Asking agent to create a Python file...")
        print("-" * 40)
        result = agent.start(
            "Create a Python file called calculator.py with add and subtract functions"
        )
        print("-" * 40)
        print(f"Agent response: {result[:200]}..." if len(str(result)) > 200 else f"Agent response: {result}")
        print()
        
        # 5. Verify file was created
        print("5. Verifying file creation...")
        calc_path = os.path.join(workspace, "calculator.py")
        if os.path.exists(calc_path):
            print(f"   ✓ File created at {calc_path}")
            with open(calc_path) as f:
                content = f.read()
                print(f"   Content preview:")
                for line in content.split('\n')[:10]:
                    print(f"     {line}")
        else:
            # Check what files exist
            files = os.listdir(workspace)
            print(f"   Files in workspace: {files}")
            for f in files:
                fp = os.path.join(workspace, f)
                if os.path.isfile(fp):
                    print(f"   ✓ Found: {f}")
        print()
        
        # 6. Ask agent to read the file
        print("6. Asking agent to read the file...")
        print("-" * 40)
        result2 = agent.start("Read the calculator.py file and tell me what functions it has")
        print("-" * 40)
        print(f"Agent response: {result2[:300]}..." if len(str(result2)) > 300 else f"Agent response: {result2}")
        print()
        
        # Cleanup
        await runtime.stop()
        
    finally:
        # Clean up workspace
        shutil.rmtree(workspace, ignore_errors=True)
        print(f"Cleaned up workspace: {workspace}")
    
    print()
    print("=" * 60)
    print("EXAMPLE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
