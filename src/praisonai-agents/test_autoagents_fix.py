#!/usr/bin/env python3
"""Test script to verify the AutoAgents fix for string tasks"""

import json
from praisonaiagents.agents.autoagents import AutoAgents

# Test the _normalize_config method directly
def test_normalize_config():
    # Create a minimal AutoAgents instance just to test the method
    agents = AutoAgents(
        instructions="Test",
        max_agents=1
    )
    
    # Test case 1: Tasks as strings (the problematic case)
    config_dict = {
        "main_instruction": "Test instruction",
        "process_type": "sequential",
        "agents": [
            {
                "name": "Agent 1",
                "role": "Test role",
                "goal": "Test goal",
                "backstory": "Test backstory",
                "tools": [],
                "tasks": [
                    "Get the current stock price for Google (GOOG).",
                    "Get the current stock price for Apple (AAPL)."
                ]
            }
        ]
    }
    
    print("Original config with string tasks:")
    print(json.dumps(config_dict, indent=2))
    
    # Normalize the config
    normalized = agents._normalize_config(config_dict.copy())
    
    print("\nNormalized config:")
    print(json.dumps(normalized, indent=2))
    
    # Verify tasks are now dictionaries
    for agent in normalized['agents']:
        for task in agent['tasks']:
            assert isinstance(task, dict), f"Task should be dict, got {type(task)}"
            assert 'name' in task, "Task missing 'name' field"
            assert 'description' in task, "Task missing 'description' field"
            assert 'expected_output' in task, "Task missing 'expected_output' field"
            assert 'tools' in task, "Task missing 'tools' field"
    
    print("\n✅ Test passed: String tasks are properly normalized to TaskConfig format")
    
    # Test case 2: Tasks already as dictionaries (should work as before)
    config_dict2 = {
        "main_instruction": "Test instruction",
        "process_type": "sequential",
        "agents": [
            {
                "name": "Agent 1",
                "role": "Test role",
                "goal": "Test goal",
                "backstory": "Test backstory",
                "tools": [],
                "tasks": [
                    {
                        "name": "Get Google stock",
                        "description": "Get the current stock price for Google (GOOG).",
                        "expected_output": "Stock price of Google",
                        "tools": ["get_stock_price"]
                    }
                ]
            }
        ]
    }
    
    normalized2 = agents._normalize_config(config_dict2.copy())
    assert normalized2 == config_dict2, "Normalization should not alter valid configurations"
    print("\n✅ Test passed: Dict tasks remain properly formatted")

if __name__ == "__main__":
    test_normalize_config()