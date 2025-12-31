"""
Debug Interactive Mode Example

This example demonstrates how to use the debug CLI commands to test
the Interactive Coding Assistant without entering TUI mode.

Features demonstrated:
- LSP symbol listing
- LSP definition lookup
- ACP action planning
- ACP action execution
- Trace capture and JSON output
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the src directory to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "praisonai"))

from praisonai.cli.features.interactive_runtime import create_runtime
from praisonai.cli.features.code_intelligence import CodeIntelligenceRouter
from praisonai.cli.features.action_orchestrator import ActionOrchestrator


async def demo_lsp_queries(workspace: str):
    """Demonstrate LSP-based code queries."""
    print("\n" + "=" * 60)
    print("LSP CODE QUERIES DEMO")
    print("=" * 60)
    
    runtime = create_runtime(
        workspace=workspace,
        lsp=True,
        acp=False,
        trace=True
    )
    
    try:
        await runtime.start()
        router = CodeIntelligenceRouter(runtime)
        
        # Query 1: List symbols
        print("\n[Query 1] List all symbols in app.py")
        result = await router.handle_query("list all functions in app.py", "app.py")
        print(f"  Success: {result.success}")
        print(f"  LSP Used: {result.lsp_used}")
        print(f"  Fallback Used: {result.fallback_used}")
        if result.data:
            print(f"  Symbols found: {len(result.data)}")
            for symbol in result.data[:5]:
                print(f"    - {symbol['name']} ({symbol['kind']}) at line {symbol['line']}")
        
        # Query 2: Find definition
        print("\n[Query 2] Find definition of Calculator")
        result = await router.handle_query("where is Calculator defined", "app.py")
        print(f"  Success: {result.success}")
        if result.citations:
            print(f"  Found at: {result.citations[0]}")
        
        # Get trace
        trace = runtime.get_trace()
        print(f"\n[Trace] {len(trace.entries)} entries captured")
        
    finally:
        await runtime.stop()


async def demo_acp_actions(workspace: str):
    """Demonstrate ACP-based code modifications."""
    print("\n" + "=" * 60)
    print("ACP CODE MODIFICATIONS DEMO")
    print("=" * 60)
    
    runtime = create_runtime(
        workspace=workspace,
        lsp=False,
        acp=True,
        approval="auto",
        trace=True
    )
    
    try:
        await runtime.start()
        print(f"\n  ACP Ready: {runtime.acp_ready}")
        print(f"  Read Only: {runtime.read_only}")
        
        orchestrator = ActionOrchestrator(runtime)
        
        # Action 1: Create a plan
        print("\n[Action 1] Create plan for new file")
        result = await orchestrator.create_plan("create a new file called demo_output.py")
        print(f"  Success: {result.success}")
        if result.plan:
            print(f"  Plan ID: {result.plan.id}")
            print(f"  Steps: {len(result.plan.steps)}")
            for step in result.plan.steps:
                print(f"    - {step.action_type.value}: {step.target}")
        
        # Action 2: Execute with auto-approve
        print("\n[Action 2] Execute file creation")
        exec_result = await orchestrator.execute(
            "create a new file called demo_output.py with a hello function",
            auto_approve=True
        )
        print(f"  Success: {exec_result.success}")
        print(f"  Applied Steps: {exec_result.applied_steps}")
        
        # Verify file was created
        output_file = Path(workspace) / "demo_output.py"
        if output_file.exists():
            print(f"  File created: {output_file}")
            print(f"  Content preview: {output_file.read_text()[:100]}...")
        
        # Get trace
        trace = runtime.get_trace()
        print(f"\n[Trace] {len(trace.entries)} entries captured")
        for entry in trace.entries:
            print(f"    [{entry.category}] {entry.action}")
        
    finally:
        await runtime.stop()


async def demo_full_interactive_turn(workspace: str):
    """Demonstrate full interactive turn simulation."""
    print("\n" + "=" * 60)
    print("FULL INTERACTIVE TURN SIMULATION")
    print("=" * 60)
    
    runtime = create_runtime(
        workspace=workspace,
        lsp=True,
        acp=True,
        approval="auto",
        trace=True
    )
    
    try:
        status = await runtime.start()
        print("\n  Runtime Status:")
        print(f"    LSP: {'ready' if status['lsp']['ready'] else 'fallback'}")
        print(f"    ACP: {'ready' if status['acp']['ready'] else 'unavailable'}")
        
        router = CodeIntelligenceRouter(runtime)
        orchestrator = ActionOrchestrator(runtime)
        
        # Simulate user prompt: code query
        prompt1 = "What functions are in app.py?"
        print(f"\n[Turn 1] User: {prompt1}")
        
        # Classify and route
        result = await router.handle_query(prompt1, "app.py")
        print(f"  Intent: {result.intent.value}")
        print(f"  Response: Found {len(result.data) if result.data else 0} symbols")
        
        # Simulate user prompt: code modification
        prompt2 = "Create a new test file"
        print(f"\n[Turn 2] User: {prompt2}")
        
        exec_result = await orchestrator.execute(
            "create a new file called test_demo.py",
            auto_approve=True
        )
        print("  Action: file_create")
        print(f"  Result: {'success' if exec_result.success else 'failed'}")
        
        # Export trace as JSON
        trace = runtime.get_trace()
        trace_json = trace.to_dict()
        print("[Trace Export]")
        print(json.dumps(trace_json, indent=2, default=str)[:500] + "...")
        
    finally:
        await runtime.stop()


def main():
    """Run the debug demo."""
    # Create a temporary workspace
    workspace = Path(__file__).parent / "_demo_workspace"
    workspace.mkdir(exist_ok=True)
    
    # Create a sample app.py
    app_file = workspace / "app.py"
    app_file.write_text('''"""Sample application."""

def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

class Calculator:
    """Simple calculator."""
    
    def __init__(self):
        self.value = 0
    
    def add(self, x):
        self.value += x
        return self.value

if __name__ == "__main__":
    print(greet("World"))
''')
    
    print("=" * 60)
    print("PRAISONAI DEBUG MODE DEMO")
    print("=" * 60)
    print(f"Workspace: {workspace}")
    
    # Run demos
    asyncio.run(demo_lsp_queries(str(workspace)))
    asyncio.run(demo_acp_actions(str(workspace)))
    asyncio.run(demo_full_interactive_turn(str(workspace)))
    
    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
