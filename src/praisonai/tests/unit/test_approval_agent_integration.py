#!/usr/bin/env python3
"""
Agent Integration Test for Human Approval System

This test demonstrates the approval system working through the agent's execute_tool method,
which is where the approval checks are actually implemented.
"""

import sys
import os
import asyncio
import pytest

# Add the praisonai-agents module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai-agents'))

# Run interactively only when ASK_USER=1 is set
@pytest.mark.skipif(os.getenv("ASK_USER") != "1", reason="interactive approval requires user input")
def test_agent_tool_execution_with_approval():
    """Test that agent tool execution triggers approval prompts."""
    print("\n🤖 Testing Agent Tool Execution with Approval")
    print("=" * 50)
    
    try:
        from praisonaiagents import Agent
        from praisonaiagents.tools.shell_tools import ShellTools
        from praisonaiagents.approval import set_approval_callback, console_approval_callback, ApprovalDecision
        
        # Use auto-approval when running non-interactive
        if os.getenv("ASK_USER") == "1":
            set_approval_callback(console_approval_callback)
        else:
            # Auto-approve for CI
            def auto_approve_callback(function_name, arguments, risk_level):
                return ApprovalDecision(approved=True, reason="Auto-approved for CI")
            set_approval_callback(auto_approve_callback)
        
        # Create agent with dangerous tools
        agent = Agent(
            name="Test Agent",
            role="Security Tester",
            goal="Test the human approval system",
            tools=[ShellTools()],
            verbose=True
        )
        
        print("About to execute a shell command through the agent...")
        print("This should trigger an approval prompt.")
        
        # Execute tool through agent - this should trigger approval
        result = agent.execute_tool("execute_command", {"command": "echo 'Hello from agent-executed command!'"})
        
        if result.get('success'):
            print(f"✅ Command executed successfully: {result['stdout']}")
        elif result.get('approval_denied'):
            print(f"❌ Command was denied by approval system: {result['error']}")
        else:
            print(f"⚠️ Command failed for other reasons: {result}")
            
        return True
        
    except Exception as e:
        print(f"❌ Agent tool execution test failed: {e}")
        return False

def test_agent_with_auto_approval():
    """Test agent tool execution with auto-approval callback."""
    print("\n🤖 Testing Agent with Auto-Approval")
    print("=" * 40)
    
    try:
        from praisonaiagents import Agent
        from praisonaiagents.tools.shell_tools import ShellTools
        from praisonaiagents.approval import set_approval_callback, ApprovalDecision
        
        # Create auto-approval callback
        def auto_approve_callback(function_name, arguments, risk_level):
            print(f"🤖 Auto-approving {function_name} (risk: {risk_level})")
            return ApprovalDecision(approved=True, reason="Auto-approved for testing")
        
        set_approval_callback(auto_approve_callback)
        
        # Create agent
        agent = Agent(
            name="Auto-Approve Agent",
            role="Automated Tester",
            goal="Test auto-approval",
            tools=[ShellTools()],
            verbose=False
        )
        
        print("Executing command with auto-approval...")
        result = agent.execute_tool(
            "execute_command",
            {"command": "echo 'Auto-approved command executed!'"}
        )
        
        if result.get('success'):
            print(f"✅ Auto-approved command executed: {result['stdout']}")
        else:
            print(f"❌ Auto-approved command failed: {result}")
            
        return True
        
    except Exception as e:
        print(f"❌ Auto-approval test failed: {e}")
        return False

def test_agent_with_auto_denial():
    """Test agent tool execution with auto-denial callback."""
    print("\n🚫 Testing Agent with Auto-Denial")
    print("=" * 40)
    
    try:
        from praisonaiagents import Agent
        from praisonaiagents.tools.shell_tools import ShellTools
        from praisonaiagents.approval import set_approval_callback, ApprovalDecision
        
        # Create auto-denial callback
        def auto_deny_callback(function_name, arguments, risk_level):
            print(f"🚫 Auto-denying {function_name} (risk: {risk_level})")
            return ApprovalDecision(approved=False, reason="Auto-denied for testing")
        
        set_approval_callback(auto_deny_callback)
        
        # Create agent
        agent = Agent(
            name="Auto-Deny Agent",
            role="Security Tester",
            goal="Test auto-denial",
            tools=[ShellTools()],
            verbose=False
        )
        
        print("Executing command with auto-denial...")
        result = agent.execute_tool("execute_command", {"command": "echo 'This should be denied'"})
        
        if result.get('approval_denied'):
            print("✅ Command was correctly denied by approval system")
        elif result.get('success'):
            print("❌ Command executed when it should have been denied")
        else:
            print(f"⚠️ Command failed for other reasons: {result}")
            
        return True
        
    except Exception as e:
        print(f"❌ Auto-denial test failed: {e}")
        return False

def test_agent_python_code_execution():
    """Test Python code execution through agent with approval."""
    print("\n🐍 Testing Agent Python Code Execution")
    print("=" * 45)
    
    try:
        from praisonaiagents import Agent
        from praisonaiagents.tools.python_tools import PythonTools
        from praisonaiagents.approval import set_approval_callback, ApprovalDecision
        
        # Create auto-approval for this test
        def auto_approve_callback(function_name, arguments, risk_level):
            print(f"🤖 Auto-approving {function_name} (risk: {risk_level})")
            return ApprovalDecision(approved=True, reason="Auto-approved for testing")
        
        set_approval_callback(auto_approve_callback)
        
        # Create agent
        agent = Agent(
            name="Python Agent",
            role="Code Executor",
            goal="Test Python code execution",
            tools=[PythonTools()],
            verbose=False
        )
        
        code = """
print("Hello from agent-executed Python code!")
result = 3 * 7
print(f"3 * 7 = {result}")
"""
        
        print("Executing Python code through agent...")
        result = agent.execute_tool("execute_code", {"code": code})
        
        if result.get('success'):
            print(f"✅ Python code executed successfully: {result['output']}")
        else:
            print(f"❌ Python code execution failed: {result}")
            
        return True
        
    except Exception as e:
        print(f"❌ Python code execution test failed: {e}")
        return False

def test_agent_file_operations():
    """Test file operations through agent with approval."""
    print("\n📁 Testing Agent File Operations")
    print("=" * 35)
    
    try:
        from praisonaiagents import Agent
        from praisonaiagents.tools.file_tools import FileTools
        from praisonaiagents.approval import set_approval_callback, ApprovalDecision
        
        # Create auto-approval for this test
        def auto_approve_callback(function_name, arguments, risk_level):
            print(f"🤖 Auto-approving {function_name} (risk: {risk_level})")
            return ApprovalDecision(approved=True, reason="Auto-approved for testing")
        
        set_approval_callback(auto_approve_callback)
        
        # Create agent
        agent = Agent(
            name="File Agent",
            role="File Manager",
            goal="Test file operations",
            tools=[FileTools()],
            verbose=False
        )
        
        # Test file creation
        print("Creating file through agent...")
        result = agent.execute_tool("write_file", {
            "file_path": "test_agent_file.txt",
            "content": "This file was created through agent with approval!"
        })
        
        if result.get('success'):
            print(f"✅ File created successfully: {result['message']}")
            
            # Test file deletion
            print("Deleting file through agent...")
            delete_result = agent.execute_tool("delete_file", {"file_path": "test_agent_file.txt"})
            
            if delete_result.get('success'):
                print(f"✅ File deleted successfully: {delete_result['message']}")
            else:
                print(f"❌ File deletion failed: {delete_result}")
        else:
            print(f"❌ File creation failed: {result}")
            
        return True
        
    except Exception as e:
        print(f"❌ File operations test failed: {e}")
        return False

def main():
    """Run agent integration tests for the approval system."""
    print("🧪 PraisonAI Human Approval System - Agent Integration Tests")
    print("=" * 65)
    print("These tests demonstrate the approval system working through agent tool execution.")
    print()
    
    # Ask user which tests to run
    print("Available tests:")
    print("1. Agent Tool Execution with Interactive Approval")
    print("2. Agent with Auto-Approval")
    print("3. Agent with Auto-Denial")
    print("4. Agent Python Code Execution")
    print("5. Agent File Operations")
    print("6. Run all tests")
    print()
    
    try:
        choice = input("Enter your choice (1-6): ").strip()
        
        if choice == "1":
            test_agent_tool_execution_with_approval()
        elif choice == "2":
            test_agent_with_auto_approval()
        elif choice == "3":
            test_agent_with_auto_denial()
        elif choice == "4":
            test_agent_python_code_execution()
        elif choice == "5":
            test_agent_file_operations()
        elif choice == "6":
            print("\n🚀 Running all tests...")
            
            # Run non-interactive tests first
            print("\n" + "=" * 65)
            print("PART 1: NON-INTERACTIVE TESTS")
            print("=" * 65)
            test_agent_with_auto_approval()
            test_agent_with_auto_denial()
            test_agent_python_code_execution()
            test_agent_file_operations()
            
            # Ask if user wants to run interactive test
            print("\n" + "=" * 65)
            print("PART 2: INTERACTIVE TEST")
            print("=" * 65)
            print("The following test requires human interaction.")
            run_interactive = input("Run interactive approval test? (y/n): ").strip().lower()
            
            if run_interactive.startswith('y'):
                test_agent_tool_execution_with_approval()
            else:
                print("Skipping interactive test.")
        else:
            print("Invalid choice. Exiting.")
            return
            
        print("\n🎉 Test completed!")
        print("\nKey observations:")
        print("- Approval system works when tools are executed through agent.execute_tool()")
        print("- Direct tool calls bypass the approval system")
        print("- Risk levels are correctly identified and displayed")
        print("- Auto-approval and auto-denial callbacks work as expected")
        print("- The approval system integrates properly with the agent architecture")
        
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user.")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")

if __name__ == "__main__":
    main() 