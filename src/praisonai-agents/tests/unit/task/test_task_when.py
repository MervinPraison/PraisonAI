"""
TDD Tests for Task.when parameter - Unified Condition Syntax.

These tests define the expected behavior for the new unified condition syntax.
Tests should FAIL initially, then PASS after implementation.

The goal is to unify condition syntax between AgentFlow and Task:
- AgentFlow: when(condition="{{score}} > 80", then_steps=[...], else_steps=[...])
- Task: when="{{score}} > 80", then_task="approve", else_task="reject"
"""


class TestTaskWhenParameter:
    """Test Task.when parameter for string-based conditions."""
    
    def test_task_accepts_when_parameter(self):
        """Task should accept a 'when' parameter as a string expression."""
        from praisonaiagents import Task
        
        task = Task(
            name="conditional_task",
            description="A task with a condition",
            when="{{score}} > 80"
        )
        
        assert hasattr(task, 'when')
        assert task.when == "{{score}} > 80"
    
    def test_task_when_with_then_task(self):
        """Task should accept 'then_task' for routing when condition is True."""
        from praisonaiagents import Task
        
        task = Task(
            name="review",
            description="Review content",
            when="{{score}} > 80",
            then_task="approve"
        )
        
        assert hasattr(task, 'then_task')
        assert task.then_task == "approve"
    
    def test_task_when_with_else_task(self):
        """Task should accept 'else_task' for routing when condition is False."""
        from praisonaiagents import Task
        
        task = Task(
            name="review",
            description="Review content",
            when="{{score}} > 80",
            then_task="approve",
            else_task="reject"
        )
        
        assert hasattr(task, 'else_task')
        assert task.else_task == "reject"
    
    def test_task_when_defaults_to_none(self):
        """Task.when should default to None when not provided."""
        from praisonaiagents import Task
        
        task = Task(
            name="simple_task",
            description="A simple task"
        )
        
        assert hasattr(task, 'when')
        assert task.when is None
    
    def test_task_then_task_defaults_to_none(self):
        """Task.then_task should default to None when not provided."""
        from praisonaiagents import Task
        
        task = Task(
            name="simple_task",
            description="A simple task"
        )
        
        assert hasattr(task, 'then_task')
        assert task.then_task is None
    
    def test_task_else_task_defaults_to_none(self):
        """Task.else_task should default to None when not provided."""
        from praisonaiagents import Task
        
        task = Task(
            name="simple_task",
            description="A simple task"
        )
        
        assert hasattr(task, 'else_task')
        assert task.else_task is None


class TestTaskConditionRenameToRouting:
    """Test that 'condition' is renamed to 'routing' with backward compatibility."""
    
    def test_task_accepts_routing_parameter(self):
        """Task should accept 'routing' parameter (new name for condition)."""
        from praisonaiagents import Task
        
        task = Task(
            name="decision_task",
            description="Make a decision",
            task_type="decision",
            routing={"approved": ["publish"], "rejected": ["revise"]}
        )
        
        # routing should be stored
        assert hasattr(task, 'routing')
        # For backward compat, condition should also work
        assert task.condition == {"approved": ["publish"], "rejected": ["revise"]}
    
    def test_task_condition_still_works_backward_compat(self):
        """Task should still accept 'condition' parameter for backward compatibility."""
        from praisonaiagents import Task
        
        task = Task(
            name="decision_task",
            description="Make a decision",
            task_type="decision",
            condition={"approved": ["publish"], "rejected": ["revise"]}
        )
        
        # condition should still work
        assert task.condition == {"approved": ["publish"], "rejected": ["revise"]}


class TestTaskWhenEvaluation:
    """Test that Task.when conditions can be evaluated."""
    
    def test_task_has_evaluate_when_method(self):
        """Task should have a method to evaluate the 'when' condition."""
        from praisonaiagents import Task
        
        task = Task(
            name="conditional_task",
            description="A task with a condition",
            when="{{score}} > 80"
        )
        
        assert hasattr(task, 'evaluate_when')
        assert callable(task.evaluate_when)
    
    def test_evaluate_when_returns_true(self):
        """evaluate_when should return True when condition is met."""
        from praisonaiagents import Task
        
        task = Task(
            name="conditional_task",
            description="A task with a condition",
            when="{{score}} > 80"
        )
        
        result = task.evaluate_when({"score": 90})
        assert result is True
    
    def test_evaluate_when_returns_false(self):
        """evaluate_when should return False when condition is not met."""
        from praisonaiagents import Task
        
        task = Task(
            name="conditional_task",
            description="A task with a condition",
            when="{{score}} > 80"
        )
        
        result = task.evaluate_when({"score": 70})
        assert result is False
    
    def test_evaluate_when_returns_true_when_no_condition(self):
        """evaluate_when should return True when no 'when' condition is set."""
        from praisonaiagents import Task
        
        task = Task(
            name="simple_task",
            description="A simple task"
        )
        
        result = task.evaluate_when({})
        assert result is True
    
    def test_evaluate_when_with_string_comparison(self):
        """evaluate_when should handle string comparisons."""
        from praisonaiagents import Task
        
        task = Task(
            name="conditional_task",
            description="A task with a condition",
            when="{{status}} == approved"
        )
        
        assert task.evaluate_when({"status": "approved"}) is True
        assert task.evaluate_when({"status": "rejected"}) is False


class TestTaskGetNextTask:
    """Test Task routing based on when condition."""
    
    def test_get_next_task_returns_then_task_when_true(self):
        """get_next_task should return then_task when condition is True."""
        from praisonaiagents import Task
        
        task = Task(
            name="review",
            description="Review content",
            when="{{score}} > 80",
            then_task="approve",
            else_task="reject"
        )
        
        assert hasattr(task, 'get_next_task')
        next_task = task.get_next_task({"score": 90})
        assert next_task == "approve"
    
    def test_get_next_task_returns_else_task_when_false(self):
        """get_next_task should return else_task when condition is False."""
        from praisonaiagents import Task
        
        task = Task(
            name="review",
            description="Review content",
            when="{{score}} > 80",
            then_task="approve",
            else_task="reject"
        )
        
        next_task = task.get_next_task({"score": 70})
        assert next_task == "reject"
    
    def test_get_next_task_returns_none_when_no_routing(self):
        """get_next_task should return None when no routing is configured."""
        from praisonaiagents import Task
        
        task = Task(
            name="simple_task",
            description="A simple task"
        )
        
        next_task = task.get_next_task({})
        assert next_task is None
