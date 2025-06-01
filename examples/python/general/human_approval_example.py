#!/usr/bin/env python3
"""
Human Approval Example for PraisonAI Agents

This example demonstrates the human-in-the-loop approval system for dangerous operations.
When agents attempt to execute high-risk tools (like shell commands or file operations),
the system will prompt the user for approval before proceeding.

Usage:
    python human_approval_example.py

Features:
- Automatic approval prompts for dangerous tools
- Risk level classification (critical, high, medium, low)  
- User can approve, deny, or modify tool arguments
- Console-based approval interface with rich formatting
"""

import asyncio
import logging
import os
import sys

# Add the local development path to use the current implementation
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import python_tools, file_tools, shell_tools
from praisonaiagents.main import register_approval_callback
from praisonaiagents.approval import (
    console_approval_callback, 
    ApprovalDecision,
    add_approval_requirement,
    remove_approval_requirement
)

# Configure logging
logging.basicConfig(level=logging.INFO)

def custom_approval_callback(function_name: str, arguments: dict, risk_level: str) -> ApprovalDecision:
    """
    Custom approval callback that demonstrates how to implement
    custom approval logic beyond the default console prompts.
    """
    print(f"\n🔒 CUSTOM APPROVAL REQUIRED")
    print(f"Function: {function_name}")
    print(f"Risk Level: {risk_level}")
    print(f"Arguments: {arguments}")
    
    # Example: Auto-approve low-risk operations
    if risk_level == "low":
        print("✅ Auto-approving low-risk operation")
        return ApprovalDecision(approved=True, reason="Auto-approved low risk")
    
    # Example: Always deny certain dangerous commands
    if function_name == "execute_command" and any(
        dangerous in str(arguments.get("command", "")) 
        for dangerous in ["rm -rf", "del /f", "format", "shutdown"]
    ):
        print("❌ Automatically denying dangerous command")
        return ApprovalDecision(approved=False, reason="Dangerous command blocked")
    
    # For other cases, use the default console approval
    return console_approval_callback(function_name, arguments, risk_level)

def main():
    """Demonstrate human approval system with various dangerous operations."""
    
    print("🤖 PraisonAI Human Approval System Demo")
    print("=" * 50)
    print("This demo will show approval prompts for dangerous operations.")
    print("You can approve or deny each operation as it's requested.")
    print()
    
    # Option 1: Use default console approval callback (automatic)
    # Option 2: Use custom approval callback
    # Uncomment the line below to use custom approval logic:
    # register_approval_callback(custom_approval_callback)
    
    # Create agent with dangerous tools
    agent = Agent(
        name="Security Demo Agent",
        role="System Administrator",
        goal="Demonstrate human approval for dangerous operations",
        tools=[python_tools, file_tools, shell_tools],
        verbose=True
    )
    
    # Define tasks that will trigger approval prompts
    tasks = [
        Task(
            description="Execute a simple Python print statement",
            agent=agent,
            expected_output="Python code execution result"
        ),
        Task(
            description="Create a test file with some content",
            agent=agent,
            expected_output="File creation confirmation"
        ),
        Task(
            description="List the current directory contents using shell command",
            agent=agent,
            expected_output="Directory listing"
        ),
        Task(
            description="Delete the test file that was created",
            agent=agent,
            expected_output="File deletion confirmation"
        )
    ]
    
    # Create and run process
    process = PraisonAIAgents(
        agents=[agent],
        tasks=tasks,
        verbose=True
    )
    
    print("\n🚀 Starting process with approval-required operations...")
    print("You will be prompted to approve each dangerous operation.")
    print()
    
    try:
        result = process.start()
        print(f"\n✅ Process completed successfully!")
        print(f"Final result: {result}")
    except KeyboardInterrupt:
        print("\n❌ Process cancelled by user")
    except Exception as e:
        print(f"\n❌ Process failed: {e}")

def demo_manual_approval_configuration():
    """Demonstrate how to manually configure approval requirements."""
    
    print("\n📋 Manual Approval Configuration Demo")
    print("=" * 40)
    
    # Add approval requirement for a normally safe operation
    add_approval_requirement("list_files", "medium")
    print("✅ Added approval requirement for 'list_files' (medium risk)")
    
    # Remove approval requirement for a normally dangerous operation
    remove_approval_requirement("write_file")
    print("✅ Removed approval requirement for 'write_file'")
    
    # Show current approval requirements
    from praisonaiagents.approval import APPROVAL_REQUIRED_TOOLS, TOOL_RISK_LEVELS
    print(f"\nCurrent approval-required tools: {list(APPROVAL_REQUIRED_TOOLS)}")
    print(f"Tool risk levels: {TOOL_RISK_LEVELS}")

async def async_demo():
    """Demonstrate approval system with async operations."""
    
    print("\n🔄 Async Approval Demo")
    print("=" * 25)
    
    # Create async agent
    agent = Agent(
        name="Async Demo Agent",
        role="Async Operations Specialist", 
        goal="Demonstrate async approval workflow",
        tools=[python_tools],
        verbose=True
    )
    
    # This would trigger approval in async context
    task = Task(
        description="Execute async Python code that prints 'Hello from async!'",
        agent=agent,
        expected_output="Async execution result"
    )
    
    process = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        verbose=True
    )
    
    try:
        result = await process.astart()
        print(f"✅ Async process completed: {result}")
    except Exception as e:
        print(f"❌ Async process failed: {e}")

if __name__ == "__main__":
    print(__doc__)
    
    # Run the main demo
    main()
    
    # Show manual configuration options
    demo_manual_approval_configuration()
    
    # Demonstrate async approval (optional)
    print("\n" + "=" * 50)
    print("Would you like to run the async demo as well? (y/n): ", end="")
    try:
        if input().lower().startswith('y'):
            asyncio.run(async_demo())
    except KeyboardInterrupt:
        print("\nDemo cancelled.")
    
    print("\n🎉 Human approval demo completed!")
    print("\nKey takeaways:")
    print("- Dangerous operations automatically prompt for approval")
    print("- Risk levels help prioritize approval decisions")
    print("- Custom approval callbacks allow for automated policies")
    print("- Both sync and async operations are supported")
    print("- Approval requirements can be configured at runtime")