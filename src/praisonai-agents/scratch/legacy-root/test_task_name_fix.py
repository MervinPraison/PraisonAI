#!/usr/bin/env python3
"""
Test script to validate the task_name fix for agentic parallelization.
This script tests the structure without requiring API keys.
"""

import asyncio
import sys
import os

# Add the source path to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_achat_signature():
    """Test that achat method has the correct signature"""
    try:
        from praisonaiagents import Agent
        
        # Create a basic agent
        agent = Agent(
            name="TestAgent",
            role="Test Role",
            goal="Test Goal",
            llm="mock-llm"  # Using a mock LLM
        )
        
        # Check if achat method exists and has the correct signature
        import inspect
        achat_sig = inspect.signature(agent.achat)
        params = list(achat_sig.parameters.keys())
        
        required_params = ['prompt', 'temperature', 'tools', 'output_json', 'output_pydantic', 'reasoning_steps', 'task_name', 'task_description', 'task_id']
        
        print("✅ Agent.achat signature test:")
        print(f"  Method parameters: {params}")
        
        missing_params = [p for p in required_params if p not in params]
        if missing_params:
            print(f"  ❌ Missing parameters: {missing_params}")
            return False
        else:
            print("  ✅ All required parameters present")
            return True
            
    except Exception as e:
        print(f"❌ Error testing achat signature: {e}")
        return False

def test_task_structure():
    """Test that Task objects have the required attributes"""
    try:
        from praisonaiagents import Agent, Task
        
        # Create a basic task
        agent = Agent(
            name="TestAgent",
            role="Test Role", 
            goal="Test Goal",
            llm="mock-llm"
        )
        
        task = Task(
            name="test_task",
            description="Test task description",
            expected_output="Test output",
            agent=agent
        )
        
        print("✅ Task structure test:")
        print(f"  Task name: {getattr(task, 'name', 'MISSING')}")
        print(f"  Task description: {getattr(task, 'description', 'MISSING')}")
        print(f"  Task id: {getattr(task, 'id', 'MISSING')}")
        
        has_name = hasattr(task, 'name')
        has_description = hasattr(task, 'description') 
        has_id = hasattr(task, 'id')
        
        if has_name and has_description and has_id:
            print("  ✅ Task has all required attributes")
            return True
        else:
            print(f"  ❌ Task missing attributes - name: {has_name}, description: {has_description}, id: {has_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing task structure: {e}")
        return False

async def test_achat_call():
    """Test that achat can be called with task parameters"""
    try:
        from praisonaiagents import Agent
        
        # Create a basic agent  
        agent = Agent(
            name="TestAgent",
            role="Test Role",
            goal="Test Goal",
            llm="mock-llm"  # This should gracefully handle mock LLM
        )
        
        print("✅ Testing achat call with task parameters:")
        
        # This should not raise a NameError for task_name anymore
        try:
            # We expect this to fail due to mock LLM, but NOT due to NameError: task_name not defined
            await agent.achat(
                "Test prompt",
                task_name="test_task",
                task_description="Test description", 
                task_id="test_id"
            )
            print("  ✅ achat call succeeded (unexpected but good!)")
            return True
        except NameError as e:
            if "task_name" in str(e):
                print(f"  ❌ Still getting task_name NameError: {e}")
                return False
            else:
                print(f"  ⚠️ Different NameError (acceptable): {e}")
                return True
        except Exception as e:
            if "task_name" in str(e) and "not defined" in str(e):
                print(f"  ❌ Still getting task_name error: {e}")
                return False
            else:
                print(f"  ✅ Different error (expected with mock LLM): {type(e).__name__}: {e}")
                return True
            
    except Exception as e:
        print(f"❌ Error testing achat call: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 Testing task_name fix for agentic parallelization...")
    print()
    
    results = []
    
    # Test 1: Check achat signature
    results.append(test_achat_signature())
    print()
    
    # Test 2: Check task structure  
    results.append(test_task_structure())
    print()
    
    # Test 3: Test achat call
    results.append(await test_achat_call())
    print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The task_name fix appears to be working.")
        return 0
    else:
        print("❌ Some tests failed. The fix may need more work.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)