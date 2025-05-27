#!/usr/bin/env python3
"""
Test script to verify context management functionality
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.task.task import Task
from praisonaiagents.agent.agent import Agent
from praisonaiagents.process.process import Process
from praisonaiagents.main import TaskOutput

def test_context_management():
    """Test context management with and without retain_full_context"""
    
    print("Starting context management test...")
    
    try:
        # Create a mock agent
        agent = Agent(name="Test Agent", role="Tester", goal="Test context management")
        print("✓ Created test agent")
        
        # Create tasks with results
        task1 = Task(
            name="task1",
            description="First task",
            agent=agent,
            status="completed"
        )
        task1.result = TaskOutput(
            description="First task",
            raw="Result from task 1",
            agent="Test Agent"
        )
        print("✓ Created task1")
        
        task2 = Task(
            name="task2", 
            description="Second task",
            agent=agent,
            status="completed"
        )
        task2.result = TaskOutput(
            description="Second task",
            raw="Result from task 2",
            agent="Test Agent"
        )
        # Set up the previous_tasks manually since it's not a constructor parameter
        task2.previous_tasks = ["task1"]
        print("✓ Created task2")
        
        # Test case 1: Default behavior (retain_full_context=False)
        task3_limited = Task(
            name="task3_limited",
            description="Third task with limited context",
            agent=agent,
            retain_full_context=False  # Default behavior
        )
        # Set up the previous_tasks manually
        task3_limited.previous_tasks = ["task1", "task2"]
        print("✓ Created task3_limited")
        
        # Test case 2: Full context retention (retain_full_context=True)
        task3_full = Task(
            name="task3_full",
            description="Third task with full context",
            agent=agent,
            retain_full_context=True  # Original behavior
        )
        # Set up the previous_tasks manually
        task3_full.previous_tasks = ["task1", "task2"]
        print("✓ Created task3_full")
        
        # Create process and test context building
        tasks_dict = {
            task1.id: task1,
            task2.id: task2,
            task3_limited.id: task3_limited,
            task3_full.id: task3_full
        }
        
        process = Process(tasks=tasks_dict, agents=[agent])
        print("✓ Created process")
        
        # Test limited context
        limited_context = process._build_task_context(task3_limited)
        print("Limited context (retain_full_context=False):")
        print(f"'{limited_context}'")
        print()
        
        # Test full context
        full_context = process._build_task_context(task3_full)
        print("Full context (retain_full_context=True):")
        print(f"'{full_context}'")
        print()
        
        # Verify results
        assert "task2" in limited_context, "Limited context should include most recent task"
        assert "task1" not in limited_context, "Limited context should NOT include earlier tasks"
        
        assert "task1" in full_context, "Full context should include all previous tasks"
        assert "task2" in full_context, "Full context should include all previous tasks"
        
        print("✅ All tests passed!")
        print("- Limited context only includes most recent previous task")
        print("- Full context includes all previous tasks")
        print("- Backwards compatibility maintained")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    test_context_management()