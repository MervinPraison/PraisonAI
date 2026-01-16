"""
Interactive Default Tools Example

This example demonstrates how PraisonAI's interactive modes (TUI and prompt)
include ACP and LSP tools by default.

Tool Groups:
- ACP: acp_create_file, acp_edit_file, acp_delete_file, acp_execute_command
- LSP: lsp_list_symbols, lsp_find_definition, lsp_find_references, lsp_get_diagnostics
- Basic: read_file, write_file, list_files, execute_command, internet_search

Usage:
    python interactive_tools_example.py
"""

import os
import sys

# Add paths for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/praisonai'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/praisonai-agents'))


def example_get_default_tools():
    """Example: Get all default interactive tools."""
    from praisonai.cli.features.interactive_tools import (
        get_interactive_tools,
        ToolConfig,
        TOOL_GROUPS,
    )
    
    print("=== Default Interactive Tools ===\n")
    
    # Show tool groups
    print("Tool Groups:")
    for group, tools in TOOL_GROUPS.items():
        if group != "interactive":
            print(f"  {group}: {tools}")
    print()
    
    # Get all tools
    config = ToolConfig(workspace=os.getcwd())
    tools = get_interactive_tools(config=config)
    
    print(f"Total tools loaded: {len(tools)}")
    print(f"Tool names: {[t.__name__ for t in tools]}")
    print()
    
    return tools


def example_disable_acp():
    """Example: Disable ACP tools."""
    from praisonai.cli.features.interactive_tools import (
        get_interactive_tools,
        ToolConfig,
    )
    
    print("=== Disable ACP Tools (--no-acp) ===\n")
    
    config = ToolConfig(workspace=os.getcwd(), enable_acp=False)
    tools = get_interactive_tools(config=config, disable=["acp"])
    
    acp_tools = [t for t in tools if t.__name__.startswith("acp_")]
    print(f"ACP tools after --no-acp: {len(acp_tools)}")
    print(f"Remaining tools: {[t.__name__ for t in tools]}")
    print()
    
    return tools


def example_disable_lsp():
    """Example: Disable LSP tools."""
    from praisonai.cli.features.interactive_tools import (
        get_interactive_tools,
        ToolConfig,
    )
    
    print("=== Disable LSP Tools (--no-lsp) ===\n")
    
    config = ToolConfig(workspace=os.getcwd(), enable_lsp=False)
    tools = get_interactive_tools(config=config, disable=["lsp"])
    
    lsp_tools = [t for t in tools if t.__name__.startswith("lsp_")]
    print(f"LSP tools after --no-lsp: {len(lsp_tools)}")
    print(f"Remaining tools: {[t.__name__ for t in tools]}")
    print()
    
    return tools


def example_agent_with_default_tools():
    """Example: Create an Agent with default interactive tools."""
    from praisonai.cli.features.interactive_tools import get_interactive_tools, ToolConfig
    from praisonaiagents import Agent
    
    print("=== Agent with Default Interactive Tools ===\n")
    
    # Get default tools
    config = ToolConfig(workspace=os.getcwd())
    tools = get_interactive_tools(config=config)
    
    # Create agent with tools
    agent = Agent(
        name="InteractiveAgent",
        instructions="You are a helpful coding assistant with file and code analysis capabilities.",
        tools=tools,
        output="silent"
    )
    
    print(f"Agent created with {len(tools)} tools")
    print(f"Tools: {[t.__name__ for t in tools]}")
    print()
    
    # Simple test - list files
    print("Testing agent with list_files tool...")
    result = agent.start("List the Python files in the current directory using list_files tool.")
    print(f"Result: {result[:200]}..." if len(str(result)) > 200 else f"Result: {result}")
    print()
    
    return agent


if __name__ == "__main__":
    print("=" * 60)
    print("PraisonAI Interactive Default Tools Example")
    print("=" * 60)
    print()
    
    # Example 1: Get default tools
    example_get_default_tools()
    
    # Example 2: Disable ACP
    example_disable_acp()
    
    # Example 3: Disable LSP
    example_disable_lsp()
    
    # Example 4: Agent with default tools (requires API key)
    if os.environ.get("OPENAI_API_KEY"):
        example_agent_with_default_tools()
    else:
        print("=== Agent Example Skipped (no OPENAI_API_KEY) ===")
    
    print("=" * 60)
    print("Examples Complete")
    print("=" * 60)
