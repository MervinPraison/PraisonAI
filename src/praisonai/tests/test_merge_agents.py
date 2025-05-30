#!/usr/bin/env python3
"""
Test for agent merge functionality (Issue #122)
Tests that existing agents.yaml files are honored when auto-generating agents.
"""

import os
import sys
import yaml
import tempfile
import shutil

def test_merge_functionality():
    """Test the merge functionality with existing agents.yaml"""
    
    print("🧪 Testing Agent Merge Functionality (Issue #122)")
    print("=" * 50)
    
    # Create a temporary directory for testing
    test_dir = tempfile.mkdtemp()
    original_dir = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        # Create a sample existing agents.yaml file
        existing_agents = {
            "framework": "praisonai",
            "topic": "existing project",
            "roles": {
                "existing_researcher": {
                    "backstory": "Experienced researcher with domain expertise",
                    "goal": "Conduct thorough research",
                    "role": "Senior Researcher",
                    "tasks": {
                        "research_task": {
                            "description": "Research existing market trends",
                            "expected_output": "Comprehensive market research report"
                        }
                    },
                    "tools": ["search_tool"]
                }
            },
            "dependencies": []
        }
        
        # Write existing agents.yaml
        with open("agents.yaml", 'w') as f:
            yaml.dump(existing_agents, f, allow_unicode=True, sort_keys=False)
        
        print("✅ Created test agents.yaml file")
        
        # Test the merge functionality by creating a simple mock
        new_agents_data = {
            "framework": "praisonai", 
            "topic": "new auto-generated topic",
            "roles": {
                "auto_researcher": {
                    "backstory": "Auto-generated researcher",
                    "goal": "Auto research goal",
                    "role": "Auto Researcher",
                    "tasks": {
                        "auto_task": {
                            "description": "Auto-generated task",
                            "expected_output": "Auto output"
                        }
                    },
                    "tools": [""]
                }
            },
            "dependencies": []
        }
        
        # Import and test the AutoGenerator merge functionality
        sys.path.insert(0, os.path.join(original_dir, 'src', 'praisonai'))
        from praisonai.auto import AutoGenerator
        
        # Create AutoGenerator instance
        generator = AutoGenerator(topic="test merge", agent_file="test_merged.yaml", framework="praisonai")
        
        # Test the merge function directly
        merged_data = generator.merge_with_existing_agents(new_agents_data, "agents.yaml")
        
        # Verify the merge worked correctly
        assert "existing_researcher" in merged_data["roles"], "Existing role should be preserved"
        assert "auto_researcher" in merged_data["roles"], "New role should be added"
        assert merged_data["topic"] == "existing project + new auto-generated topic", "Topics should be combined"
        
        print("✅ Basic merge functionality works correctly")
        print(f"✅ Merged data contains {len(merged_data['roles'])} roles:")
        for role_name in merged_data['roles']:
            print(f"   - {role_name}")
        
        # Test conflict resolution
        conflict_data = {
            "framework": "praisonai",
            "topic": "conflict test",
            "roles": {
                "existing_researcher": {  # Same name as existing role
                    "backstory": "Conflicting researcher",
                    "goal": "Conflict goal",
                    "role": "Conflict Researcher",
                    "tasks": {
                        "conflict_task": {
                            "description": "Conflict task",
                            "expected_output": "Conflict output"
                        }
                    },
                    "tools": [""]
                }
            },
            "dependencies": []
        }
        
        merged_conflict = generator.merge_with_existing_agents(conflict_data, "agents.yaml")
        assert "existing_researcher" in merged_conflict["roles"], "Original role should be preserved"
        assert "existing_researcher_auto_1" in merged_conflict["roles"], "Conflicting role should be renamed"
        
        print("✅ Conflict resolution works correctly")
        print(f"✅ Conflict resolution renamed duplicate role to: existing_researcher_auto_1")
        
        # Test empty existing file
        with open("empty_agents.yaml", 'w') as f:
            yaml.dump({}, f)
        
        merged_empty = generator.merge_with_existing_agents(new_agents_data, "empty_agents.yaml")
        assert merged_empty == new_agents_data, "Empty file should return new data unchanged"
        
        print("✅ Empty file handling works correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup
        os.chdir(original_dir)
        shutil.rmtree(test_dir)

if __name__ == "__main__":
    success = test_merge_functionality()
    if success:
        print("\n🎉 All merge functionality tests passed!")
    else:
        print("\n💥 Merge functionality tests failed!")
        sys.exit(1)