#!/usr/bin/env python3
"""
Basic test for --overwrite functionality
"""

import os
import sys
import tempfile
import yaml
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonai.auto import AutoGenerator

def test_overwrite_functionality():
    """Test that overwrite parameter works correctly"""
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, "agents.yaml")
        
        # Create existing agents.yaml
        existing_data = {
            "framework": "crewai",
            "topic": "Existing Topic",
            "roles": {
                "existing_agent": {
                    "role": "Existing Agent",
                    "goal": "Do existing work",
                    "backstory": "I existed before",
                    "tasks": {
                        "existing_task": {
                            "description": "Existing task",
                            "expected_output": "Existing output"
                        }
                    },
                    "tools": [""]
                }
            },
            "dependencies": []
        }
        
        with open(test_file, 'w') as f:
            yaml.dump(existing_data, f)
            
        print("✓ Created existing agents.yaml file")
        
        # Test with overwrite=True (default behavior - should overwrite)
        generator_overwrite = AutoGenerator(
            topic="New Topic", 
            agent_file=test_file, 
            framework="crewai",
            overwrite=True
        )
        
        # Mock the generate process by creating simple new data
        new_data = {
            "framework": "crewai",
            "topic": "New Topic",
            "roles": {
                "new_agent": {
                    "role": "New Agent",
                    "goal": "Do new work",
                    "backstory": "I am new",
                    "tasks": {
                        "new_task": {
                            "description": "New task",
                            "expected_output": "New output"
                        }
                    },
                    "tools": [""]
                }
            },
            "dependencies": []
        }
        
        generator_overwrite.convert_and_save({"roles": {"new_agent": {
            "role": "New Agent",
            "goal": "Do new work", 
            "backstory": "I am new",
            "tools": [""],
            "tasks": {"new_task": {"description": "New task", "expected_output": "New output"}}
        }}})
        
        # Read result and check it was overwritten
        with open(test_file, 'r') as f:
            result_overwrite = yaml.safe_load(f)
            
        assert "existing_agent" not in result_overwrite["roles"], "Existing agent should be overwritten"
        assert "new_agent" in result_overwrite["roles"], "New agent should be present"
        print("✓ Overwrite=True works correctly (existing content overwritten)")
        
        # Recreate existing file for merge test
        with open(test_file, 'w') as f:
            yaml.dump(existing_data, f)
            
        # Test with overwrite=False (should merge)
        generator_merge = AutoGenerator(
            topic="New Topic",
            agent_file=test_file,
            framework="crewai", 
            overwrite=False
        )
        
        generator_merge.convert_and_save({"roles": {"new_agent": {
            "role": "New Agent",
            "goal": "Do new work",
            "backstory": "I am new", 
            "tools": [""],
            "tasks": {"new_task": {"description": "New task", "expected_output": "New output"}}
        }}})
        
        # Read result and check it was merged
        with open(test_file, 'r') as f:
            result_merge = yaml.safe_load(f)
            
        assert "existing_agent" in result_merge["roles"], "Existing agent should be preserved"
        assert "new_agent" in result_merge["roles"], "New agent should be added"
        assert "Existing Topic + New Topic" in result_merge["topic"], "Topics should be combined"
        print("✓ Overwrite=False works correctly (content merged)")
        
        # Test conflict resolution
        generator_conflict = AutoGenerator(
            topic="Conflict Topic",
            agent_file=test_file,
            framework="crewai",
            overwrite=False
        )
        
        generator_conflict.convert_and_save({"roles": {"existing_agent": {
            "role": "Conflicting Agent",
            "goal": "Create conflict",
            "backstory": "I conflict",
            "tools": [""],
            "tasks": {"conflict_task": {"description": "Conflict task", "expected_output": "Conflict output"}}
        }}})
        
        # Read result and check conflict was resolved
        with open(test_file, 'r') as f:
            result_conflict = yaml.safe_load(f)
            
        assert "existing_agent" in result_conflict["roles"], "Original agent should remain"
        assert "existing_agent_auto_1" in result_conflict["roles"], "Conflicting agent should be renamed"
        print("✓ Conflict resolution works correctly")
        
        print("\n🎉 All tests passed! The --overwrite functionality is working correctly.")

if __name__ == "__main__":
    test_overwrite_functionality()