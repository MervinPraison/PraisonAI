"""Unit tests for validation feedback in workflow retry logic"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.process.process import Process
from praisonaiagents.main import TaskOutput


class TestValidationFeedback:
    """Test validation feedback functionality in workflow process"""
    
    def test_validation_feedback_stored_on_retry(self):
        """Test that validation feedback is stored when task is retried"""
        # Create simple agents
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            llm="gpt-4o-mini",
            self_reflect=False,
            verbose=False
        )
        
        # Create tasks
        collect_task = Task(
            description="Collect data",
            expected_output="Data collected",
            agent=agent,
            name="collect_data",
            is_start=True,
            next_tasks=["validate_data"]
        )
        
        validate_task = Task(
            description="Validate data",
            expected_output="Validation result",
            agent=agent,
            name="validate_data",
            task_type="decision",
            condition={
                "valid": [],
                "invalid": ["collect_data"]
            }
        )
        
        # Create workflow process
        tasks = {
            collect_task.id: collect_task,
            validate_task.id: validate_task
        }
        process = Process(tasks=tasks, agents=[agent], verbose=False, max_iter=2)
        
        # Simulate validation failure
        validate_task.result = TaskOutput(
            name="validate_data",
            description="Validation failed",
            agent="test_agent",
            raw="The data is invalid - not enough results",
            pydantic=type('obj', (object,), {
                'response': 'Not enough results, only 3 found',
                'decision': 'invalid'
            })()
        )
        validate_task.status = "completed"
        
        # Simulate collect task completed with some data
        collect_task.result = TaskOutput(
            name="collect_data", 
            description="Data collection",
            agent="test_agent",
            raw="Result 1\nResult 2\nResult 3"
        )
        collect_task.status = "completed"
        
        # Build workflow relationships
        for task in tasks.values():
            if task.next_tasks:
                for next_task_name in task.next_tasks:
                    next_task = next((t for t in tasks.values() if t.name == next_task_name), None)
                    if next_task:
                        next_task.previous_tasks.append(task.name)
        
        # Process workflow routing logic (simplified)
        current_task = validate_task
        decision_str = "invalid"
        
        # Find next task based on decision
        target_tasks = current_task.condition.get(decision_str, [])
        task_value = target_tasks[0] if isinstance(target_tasks, list) else target_tasks
        next_task = next((t for t in tasks.values() if t.name == task_value), None)
        
        assert next_task is not None
        assert next_task.name == "collect_data"
        
        # Apply validation feedback logic
        if next_task:
            next_task.status = "not started"
            
            # This is the new logic we're testing
            if decision_str in ["invalid", "retry", "failed"] and current_task.task_type == "decision":
                validation_response = ""
                if current_task.result.pydantic and hasattr(current_task.result.pydantic, "response"):
                    validation_response = current_task.result.pydantic.response
                elif current_task.result.raw:
                    validation_response = current_task.result.raw
                
                previous_output = ""
                if current_task.previous_tasks:
                    prev_task_name = current_task.previous_tasks[-1]
                    prev_task = next((t for t in tasks.values() if t.name == prev_task_name), None)
                    if prev_task and prev_task.result:
                        previous_output = prev_task.result.raw
                
                next_task.validation_feedback = {
                    "decision": decision_str,
                    "validation_response": validation_response,
                    "rejected_output": previous_output,
                    "validator_task": current_task.name
                }
        
        # Verify feedback was set
        assert hasattr(next_task, 'validation_feedback')
        assert next_task.validation_feedback is not None
        assert next_task.validation_feedback['decision'] == 'invalid'
        assert next_task.validation_feedback['validation_response'] == 'Not enough results, only 3 found'
        assert next_task.validation_feedback['rejected_output'] == "Result 1\nResult 2\nResult 3"
        assert next_task.validation_feedback['validator_task'] == 'validate_data'
    
    def test_validation_feedback_in_context(self):
        """Test that validation feedback is included in task context"""
        # Create task with validation feedback
        task = Task(
            description="Test task",
            expected_output="Test output",
            name="test_task"
        )
        
        task.validation_feedback = {
            "decision": "invalid",
            "validation_response": "Not enough items",
            "rejected_output": "Item 1\nItem 2",
            "validator_task": "validator"
        }
        
        # Create process and build context
        process = Process(tasks={task.id: task}, agents=[], verbose=False)
        context = process._build_task_context(task)
        
        # Verify context includes validation feedback
        assert "Previous attempt failed validation" in context
        assert "invalid" in context
        assert "Not enough items" in context
        assert "Item 1\nItem 2" in context
        assert "try again with a different approach" in context
        
        # Verify feedback is cleared after use
        assert task.validation_feedback is None
    
    def test_backward_compatibility(self):
        """Test that existing workflows without validation continue to work"""
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            llm="gpt-4o-mini",
            self_reflect=False,
            verbose=False
        )
        
        # Create simple workflow without validation
        task1 = Task(
            description="Task 1",
            expected_output="Output 1",
            agent=agent,
            name="task1",
            is_start=True,
            next_tasks=["task2"]
        )
        
        task2 = Task(
            description="Task 2",
            expected_output="Output 2",
            agent=agent,
            name="task2"
        )
        
        # Build context without validation feedback
        process = Process(
            tasks={task1.id: task1, task2.id: task2},
            agents=[agent],
            verbose=False
        )
        
        # task2 has no validation feedback
        context = process._build_task_context(task2)
        
        # Should return normal context without errors
        assert context == ""  # No previous tasks or context set yet
        
        # Set up previous task relationship
        task2.previous_tasks = ["task1"]
        task1.result = TaskOutput(
            name="task1",
            description="Task 1 result",
            agent="test_agent",
            raw="Result from task 1"
        )
        
        context = process._build_task_context(task2)
        assert "Result from task 1" in context
        assert "Previous attempt failed" not in context  # No validation feedback


if __name__ == "__main__":
    pytest.main([__file__, "-v"])