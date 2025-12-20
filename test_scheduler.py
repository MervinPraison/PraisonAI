#!/usr/bin/env python3
"""
Quick test script for scheduler with agents.yaml integration.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai'))

def test_yaml_loader():
    """Test YAML loader functionality."""
    print("Testing YAML loader...")
    
    from praisonai.scheduler.yaml_loader import load_agent_yaml_with_schedule
    
    # Test with example YAML
    yaml_path = "examples/cookbooks/yaml/news_monitor_scheduled.yaml"
    
    try:
        agent_config, schedule_config = load_agent_yaml_with_schedule(yaml_path)
        
        print(f"✅ Agent config loaded: {agent_config.get('name', 'Unknown')}")
        print(f"✅ Schedule interval: {schedule_config.get('interval', 'Not set')}")
        print(f"✅ Max retries: {schedule_config.get('max_retries', 'Not set')}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_scheduler_from_yaml():
    """Test AgentScheduler.from_yaml() method."""
    print("\nTesting AgentScheduler.from_yaml()...")
    
    from praisonai.scheduler import AgentScheduler
    
    yaml_path = "examples/cookbooks/yaml/news_monitor_scheduled.yaml"
    
    try:
        scheduler = AgentScheduler.from_yaml(yaml_path)
        
        print(f"✅ Scheduler created successfully")
        print(f"✅ Agent: {getattr(scheduler.agent, 'name', 'Unknown')}")
        print(f"✅ Task: {scheduler.task[:50]}...")
        
        # Test that we can access schedule config
        if hasattr(scheduler, '_yaml_schedule_config'):
            print(f"✅ Schedule config attached")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("Scheduler Integration Tests")
    print("="*60)
    
    results = []
    
    # Test 1: YAML Loader
    results.append(("YAML Loader", test_yaml_loader()))
    
    # Test 2: Scheduler from YAML
    results.append(("Scheduler from YAML", test_scheduler_from_yaml()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary:")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
