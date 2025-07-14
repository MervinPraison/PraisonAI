#!/usr/bin/env python3
"""
Test script to verify that the manager LLM methods correctly handle Pydantic models.
This tests the fix for the LLM interface misuse bug.
"""

import os
import sys
import json
from pydantic import BaseModel

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from praisonaiagents.process.process import Process
from praisonaiagents.task.task import Task
from praisonaiagents.agent.agent import Agent

class ManagerInstructions(BaseModel):
    task_id: int
    agent_name: str
    action: str

def test_parse_manager_instructions():
    """Test the _parse_manager_instructions helper method"""
    print("Testing _parse_manager_instructions method...")
    
    # Create a dummy process instance
    tasks = {"1": Task(name="test_task", description="Test task")}
    agents = [Agent(name="TestAgent", role="Test role", goal="Test goal")]
    process = Process(tasks=tasks, agents=agents, manager_llm="test/model")
    
    # Test valid JSON response
    valid_json = '{"task_id": 1, "agent_name": "TestAgent", "action": "execute"}'
    try:
        result = process._parse_manager_instructions(valid_json, ManagerInstructions)
        assert isinstance(result, ManagerInstructions)
        assert result.task_id == 1
        assert result.agent_name == "TestAgent"
        assert result.action == "execute"
        print("✓ Valid JSON parsing works correctly")
    except Exception as e:
        print(f"✗ Failed to parse valid JSON: {e}")
        return False
    
    # Test invalid JSON
    invalid_json = "not a json string"
    try:
        result = process._parse_manager_instructions(invalid_json, ManagerInstructions)
        print("✗ Should have failed on invalid JSON")
        return False
    except Exception as e:
        print(f"✓ Correctly raised exception for invalid JSON: {type(e).__name__}")
    
    # Test JSON with missing fields
    incomplete_json = '{"task_id": 1}'
    try:
        result = process._parse_manager_instructions(incomplete_json, ManagerInstructions)
        print("✗ Should have failed on incomplete JSON")
        return False
    except Exception as e:
        print(f"✓ Correctly raised exception for incomplete JSON: {type(e).__name__}")
    
    return True

def test_create_llm_instance():
    """Test the _create_llm_instance helper method"""
    print("\nTesting _create_llm_instance method...")
    
    # Create a dummy process instance
    tasks = {"1": Task(name="test_task", description="Test task")}
    agents = [Agent(name="TestAgent", role="Test role", goal="Test goal")]
    manager_llm = "gemini/gemini-2.5-flash-lite-preview-06-17"
    process = Process(tasks=tasks, agents=agents, manager_llm=manager_llm)
    
    # Test LLM instance creation
    try:
        llm = process._create_llm_instance()
        assert llm.model == manager_llm
        assert llm.temperature == 0.7
        print("✓ LLM instance created successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to create LLM instance: {e}")
        return False

if __name__ == "__main__":
    print("=== Testing Manager LLM Fix ===\n")
    
    # Run tests
    test_results = []
    test_results.append(("_parse_manager_instructions", test_parse_manager_instructions()))
    test_results.append(("_create_llm_instance", test_create_llm_instance()))
    
    # Summary
    print("\n=== TEST SUMMARY ===")
    all_passed = True
    for test_name, passed in test_results:
        status = "PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    sys.exit(0 if all_passed else 1)