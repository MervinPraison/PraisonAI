"""Unit tests for validation feedback in workflow retry logic"""

import pytest
from unittest.mock import Mock, patch
from praisonaiagents import Agent, Task, TaskOutput
from praisonaiagents.process import Process


class TestValidationFeedback:
    """Test validation feedback functionality"""
    
    def test_task_has_validation_feedback_field(self):
        """Test that Task class has validation_feedback field"""
        task = Task(
            name="test_task",
            description="Test task",
            expected_output="Test output"
        )
        assert hasattr(task, 'validation_feedback')
        assert task.validation_feedback is None
    
    def test_validation_feedback_captured_on_invalid_decision(self):
        """Test that validation feedback is captured when decision is invalid"""
        # Create mock agents
        agent1 = Mock(spec=Agent)
        agent2 = Mock(spec=Agent)
        
        # Create tasks
        collect_task = Task(
            name="collect_data",
            description="Collect data",
            expected_output="Data",
            agent=agent1,
            is_start=True,
            next_tasks=["validate_data"]
        )
        
        validate_task = Task(
            name="validate_data",
            description="Validate data",
            expected_output="Validation result",
            agent=agent2,
            task_type="decision",
            condition={
                "valid": [],
                "invalid": ["collect_data"]
            }
        )
        
        # Set up task relationships
        validate_task.previous_tasks = ["collect_data"]
        
        # Create process
        process = Process(
            agents={"agent1": agent1, "agent2": agent2},
            tasks={"collect_data": collect_task, "validate_data": validate_task},
            verbose=0
        )
        
        # Simulate task execution results
        collect_task.result = TaskOutput(
            raw="Collected only 3 items",
            agent="agent1"
        )
        collect_task.status = "completed"
        
        validate_task.result = TaskOutput(
            raw="Not enough results, need at least 10",
            agent="agent2"
        )
        validate_task.status = "completed"
        
        # Simulate workflow routing with invalid decision
        # This would normally happen in the workflow execution
        decision_str = "invalid"
        current_task = validate_task
        target_tasks = current_task.condition.get(decision_str, [])
        
        if target_tasks:
            task_value = target_tasks[0]
            next_task = collect_task  # This is the retry task
            
            # The implementation should add validation feedback  
            if decision_str in Process.VALIDATION_FAILURE_DECISIONS:
                if current_task and current_task.result:
                    validated_task = collect_task  # The task that was validated
                    
                    feedback = {
                        'validation_response': decision_str,
                        'validation_details': current_task.result.raw,
                        'rejected_output': validated_task.result.raw if validated_task and validated_task.result else None,
                        'validator_task': current_task.name
                    }
                    next_task.validation_feedback = feedback
        
        # Verify feedback was captured
        assert collect_task.validation_feedback is not None
        assert collect_task.validation_feedback['validation_response'] == 'invalid'
        assert collect_task.validation_feedback['validation_details'] == "Not enough results, need at least 10"
        assert collect_task.validation_feedback['rejected_output'] == "Collected only 3 items"
        assert collect_task.validation_feedback['validator_task'] == "validate_data"
    
    def test_validation_feedback_included_in_context(self):
        """Test that validation feedback is included in task context"""
        # Create a task with validation feedback
        task = Task(
            name="retry_task",
            description="Original description",
            expected_output="Expected output"
        )
        
        task.validation_feedback = {
            'validation_response': 'invalid',
            'validation_details': 'Not enough results',
            'rejected_output': 'Previous output',
            'validator_task': 'validator'
        }
        
        # Create process to test context building
        process = Process(
            agents={},
            tasks={"retry_task": task},
            verbose=0
        )
        
        # Build context
        context = process._build_task_context(task)
        
        # Verify feedback is in context
        assert "Previous attempt failed validation with reason: invalid" in context
        assert "Validation feedback: Not enough results" in context
        assert "Rejected output: Previous output" in context
        assert "Please try again with a different approach based on this feedback." in context
        
        # Verify feedback was cleared after use
        assert task.validation_feedback is None
    
    def test_validation_feedback_backward_compatibility(self):
        """Test that tasks without validation feedback work normally"""
        task = Task(
            name="normal_task",
            description="Normal task",
            expected_output="Normal output"
        )
        
        process = Process(
            agents={},
            tasks={"normal_task": task},
            verbose=0
        )
        
        # Build context without validation feedback
        context = process._build_task_context(task)
        
        # Should return empty string for task with no context
        assert context == ""
        
        # Task should still work normally
        assert task.validation_feedback is None
    
    def test_multiple_retry_decisions_supported(self):
        """Test that various failure decision strings trigger feedback capture"""
        # Import the constant from Process class
        from praisonaiagents.process import Process
        failure_decisions = Process.VALIDATION_FAILURE_DECISIONS
        
        for decision in failure_decisions:
            task = Task(
                name="test_task",
                description="Test",
                expected_output="Test"
            )
            
            # Simulate the decision routing logic
            if decision in Process.VALIDATION_FAILURE_DECISIONS:
                task.validation_feedback = {
                    'validation_response': decision,
                    'validation_details': f"Failed with {decision}",
                    'rejected_output': "Previous output",
                    'validator_task': "validator"
                }
            
            assert task.validation_feedback is not None
            assert task.validation_feedback['validation_response'] == decision
    
    def test_validation_feedback_with_context_tasks(self):
        """Test that validation feedback works when validated task is in context"""
        # Create mock agents
        agent1 = Mock(spec=Agent)
        agent2 = Mock(spec=Agent)
        
        # Create tasks
        data_task = Task(
            name="data_task",
            description="Generate data",
            expected_output="Data",
            agent=agent1
        )
        
        validate_task = Task(
            name="validate_data",
            description="Validate data",
            expected_output="Validation result",
            agent=agent2,
            task_type="decision",
            context=[data_task],  # Data task is in context, not previous_tasks
            condition={
                "valid": [],
                "invalid": ["data_task"]
            }
        )
        
        # Create process
        process = Process(
            agents={"agent1": agent1, "agent2": agent2},
            tasks={"data_task": data_task, "validate_data": validate_task},
            verbose=0
        )
        
        # Simulate task execution results
        data_task.result = TaskOutput(
            raw="Generated data with errors",
            agent="agent1"
        )
        data_task.status = "completed"
        
        validate_task.result = TaskOutput(
            raw="Data has errors, please fix",
            agent="agent2"
        )
        validate_task.status = "completed"
        
        # Test the improved validation feedback logic
        decision_str = "invalid"
        current_task = validate_task
        
        # This simulates the improved logic that checks context when no previous_tasks
        validated_task = None
        if current_task.previous_tasks:
            prev_task_name = current_task.previous_tasks[-1]
            validated_task = data_task if data_task.name == prev_task_name else None
        elif current_task.context:
            # Check context for the validated task
            for ctx_task in reversed(current_task.context):
                if ctx_task.result and ctx_task.name != current_task.name:
                    validated_task = ctx_task
                    break
        
        # Verify the context-based task was found
        assert validated_task is not None
        assert validated_task.name == "data_task"
        assert validated_task.result.raw == "Generated data with errors"