#!/usr/bin/env python3
"""
Comprehensive test to verify praisonaiagents installation and functionality
"""

import sys
import os
import traceback

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_all_imports():
    """Test that all major components can be imported"""
    print("Testing comprehensive imports...")
    try:
        from praisonaiagents import (
            Agent, Task, Tools, PraisonAIAgents, Agents, ImageAgent,
            AutoAgents, Session, Memory, Knowledge, Chunking, MCP,
            GuardrailResult, LLMGuardrail, Handoff, handoff
        )
        print("✓ All major components imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def test_agent_functionality():
    """Test basic agent functionality"""
    print("\nTesting agent functionality...")
    try:
        from praisonaiagents import Agent
        
        # Test basic agent creation
        agent = Agent(
            name="TestAgent",
            role="Test agent",
            goal="Test functionality",
            backstory="A test agent for validation",
            instructions="You are a test agent"
        )
        
        print("✓ Agent created with all parameters")
        
        # Test agent with tools
        def test_tool(input_text: str) -> str:
            """A simple test tool"""
            return f"Processed: {input_text}"
        
        agent_with_tools = Agent(
            instructions="Test agent with tools",
            tools=[test_tool]
        )
        
        print("✓ Agent with tools created successfully")
        
        return True
    except Exception as e:
        print(f"✗ Agent functionality error: {e}")
        print(traceback.format_exc())
        return False

def test_task_creation():
    """Test task creation functionality"""
    print("\nTesting task creation...")
    try:
        from praisonaiagents import Task, Agent
        
        # Create a simple agent
        agent = Agent(instructions="Test agent")
        
        # Create a task
        task = Task(
            name="test_task",
            description="Test task description",
            expected_output="Test output",
            agent=agent
        )
        
        print("✓ Task created successfully")
        
        # Test task attributes
        assert task.name == "test_task"
        assert task.description == "Test task description"
        assert task.expected_output == "Test output"
        assert task.agent == agent
        
        print("✓ Task attributes verified")
        
        return True
    except Exception as e:
        print(f"✗ Task creation error: {e}")
        print(traceback.format_exc())
        return False

def test_tools_functionality():
    """Test tools functionality"""
    print("\nTesting tools functionality...")
    try:
        from praisonaiagents import Tools
        
        # Create tools instance
        tools = Tools()
        print("✓ Tools instance created")
        
        # Test tool registration
        def sample_tool(text: str) -> str:
            return f"Tool output: {text}"
        
        # Tools can be used with agents
        from praisonaiagents import Agent
        agent = Agent(
            instructions="Test agent",
            tools=[sample_tool]
        )
        
        print("✓ Tools integration with agent successful")
        
        return True
    except Exception as e:
        print(f"✗ Tools functionality error: {e}")
        print(traceback.format_exc())
        return False

def test_multi_agent_system():
    """Test multi-agent system functionality"""
    print("\nTesting multi-agent system...")
    try:
        from praisonaiagents import Agent, Task, PraisonAIAgents
        
        # Create multiple agents
        agent1 = Agent(
            name="Agent1",
            instructions="First agent"
        )
        
        agent2 = Agent(
            name="Agent2", 
            instructions="Second agent"
        )
        
        # Create tasks
        task1 = Task(
            name="task1",
            description="First task",
            expected_output="Output 1",
            agent=agent1
        )
        
        task2 = Task(
            name="task2",
            description="Second task",
            expected_output="Output 2",
            agent=agent2
        )
        
        # Create multi-agent system
        system = PraisonAIAgents(
            agents=[agent1, agent2],
            tasks=[task1, task2],
            process="sequential"
        )
        
        print("✓ Multi-agent system created successfully")
        
        return True
    except Exception as e:
        print(f"✗ Multi-agent system error: {e}")
        print(traceback.format_exc())
        return False

def test_example_files_syntax():
    """Test syntax of key example files"""
    print("\nTesting example files syntax...")
    try:
        import py_compile
        
        # Get repository root directory
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        while not os.path.exists(os.path.join(repo_root, '.git')) and repo_root != '/':
            repo_root = os.path.dirname(repo_root)
        
        example_files = [
            os.path.join(repo_root, "src/praisonai-agents/basic-agents.py"),
            os.path.join(repo_root, "src/praisonai-agents/basic-agents-tools.py"),
            os.path.join(repo_root, "examples/python/agents/single-agent.py"),
            os.path.join(repo_root, "examples/python/agents/math-agent.py")
        ]
        
        for file_path in example_files:
            if os.path.exists(file_path):
                try:
                    py_compile.compile(file_path, doraise=True)
                    print(f"✓ {os.path.basename(file_path)} - syntax OK")
                except py_compile.PyCompileError as e:
                    print(f"✗ {os.path.basename(file_path)} - syntax error: {e}")
                    return False
            else:
                print(f"ℹ {os.path.basename(file_path)} - file not found")
        
        return True
    except Exception as e:
        print(f"✗ Example files syntax error: {e}")
        return False

def test_optional_dependencies():
    """Test optional dependencies availability"""
    print("\nTesting optional dependencies...")
    try:
        # Test telemetry
        try:
            from praisonaiagents import get_telemetry, enable_telemetry
            print("✓ Telemetry functions available")
        except ImportError:
            print("ℹ Telemetry not available (optional)")
        
        # Test memory
        try:
            from praisonaiagents import Memory
            memory = Memory()
            print("✓ Memory functionality available")
        except ImportError:
            print("ℹ Memory not available (optional dependency)")
        except Exception as e:
            print(f"ℹ Memory available but needs configuration: {e}")
        
        # Test knowledge
        try:
            from praisonaiagents import Knowledge
            print("✓ Knowledge functionality available")
        except ImportError:
            print("ℹ Knowledge not available (optional dependency)")
        
        return True
    except Exception as e:
        print(f"✗ Optional dependencies error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 70)
    print("COMPREHENSIVE PRAISONAIAGENTS INSTALLATION AND FUNCTIONALITY TEST")
    print("=" * 70)
    
    tests = [
        test_all_imports,
        test_agent_functionality,
        test_task_creation,
        test_tools_functionality,
        test_multi_agent_system,
        test_example_files_syntax,
        test_optional_dependencies
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            print(traceback.format_exc())
            failed += 1
        
        print()  # Add spacing between tests
    
    print("=" * 70)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! Installation is fully functional.")
        print("📝 Note: Some functionality may require API keys or additional configuration for actual execution.")
        print("🚀 You can now run the example files to test with actual LLM providers.")
    else:
        print("❌ Some tests failed. Please check the installation and dependencies.")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())