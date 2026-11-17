#!/usr/bin/env python3
"""Simple test for the task_name fix."""

import sys
from praisonaiagents.main import execute_sync_callback

# Test that execute_sync_callback can handle missing task_name gracefully
def test_callback(message, response, **kwargs):
    task_name = kwargs.get('task_name', 'NOT PROVIDED')
    print(f"Callback received task_name: {task_name}")
    return True

# Register the callback
from praisonaiagents.main import register_display_callback
register_display_callback('interaction', test_callback)

def main():
    print("Testing execute_sync_callback with missing task_name...")
    
    # Test the old way (without task_name) - this should work now
    try:
        execute_sync_callback(
            'interaction',
            message="test message",
            response="test response",
            markdown=True,
            generation_time=1.0
        )
        print("✅ Old-style callback works (task_name defaults to None)")
    except Exception as e:
        print(f"❌ Old-style callback failed: {e}")
        return False
    
    # Test the new way (with task_name) - this should also work
    try:
        execute_sync_callback(
            'interaction',
            message="test message",
            response="test response",
            markdown=True,
            generation_time=1.0,
            task_name="test_task",
            task_description="test description",
            task_id="test_id"
        )
        print("✅ New-style callback works (task_name provided)")
    except Exception as e:
        print(f"❌ New-style callback failed: {e}")
        return False
    
    print("✅ All tests passed! The fix is working correctly.")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)