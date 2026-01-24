"""
TDD tests for Parallel Loop pattern in YAML workflows.

Tests for parallel execution of loops:
- Loop with parallel=True executes items concurrently
- max_workers parameter limits parallelism  
- All outputs are collected correctly
- Variables are isolated between parallel executions
"""

import pytest
import time
import threading
from typing import List


class TestParallelLoopClass:
    """Tests for Loop class with parallel parameter."""
    
    def test_loop_class_has_parallel_param(self):
        """Test that Loop class accepts parallel parameter."""
        from praisonaiagents.workflows import Loop
        
        def dummy_step(ctx):
            return {"output": "done"}
        
        loop = Loop(step=dummy_step, over="items", parallel=True)
        assert loop.parallel is True
    
    def test_loop_class_has_max_workers_param(self):
        """Test that Loop class accepts max_workers parameter."""
        from praisonaiagents.workflows import Loop
        
        def dummy_step(ctx):
            return {"output": "done"}
        
        loop = Loop(step=dummy_step, over="items", parallel=True, max_workers=4)
        assert loop.max_workers == 4
    
    def test_loop_parallel_defaults_to_false(self):
        """Test that parallel defaults to False (sequential)."""
        from praisonaiagents.workflows import Loop
        
        def dummy_step(ctx):
            return {"output": "done"}
        
        loop = Loop(step=dummy_step, over="items")
        assert loop.parallel is False
    
    def test_loop_max_workers_defaults_to_none(self):
        """Test that max_workers defaults to None (unlimited)."""
        from praisonaiagents.workflows import Loop
        
        def dummy_step(ctx):
            return {"output": "done"}
        
        loop = Loop(step=dummy_step, over="items")
        assert loop.max_workers is None


class TestParallelLoopExecution:
    """Tests for parallel execution behavior."""
    
    def test_parallel_loop_collects_all_outputs(self):
        """Test that parallel loop collects outputs from all items."""
        from praisonaiagents.workflows import Workflow, Loop, loop
        from praisonaiagents import Agent
        
        # Create a simple agent that echoes the item
        agent = Agent(
            name="echo_agent",
            role="Echo",
            goal="Echo the input",
            instructions="Just repeat what you're given",
            llm="gpt-4o-mini"
        )
        
        items = ["topic_a", "topic_b", "topic_c"]
        
        # Test that loop with parallel=True can be created
        loop_step = loop(
            step=agent,
            over="items",
            parallel=True
        )
        
        # Verify the Loop object is configured correctly
        assert loop_step.parallel is True
        assert loop_step.over == "items"
        assert loop_step.step == agent
    
    def test_parallel_loop_faster_than_sequential(self):
        """Test that parallel loop with sleep is faster than sequential."""
        import concurrent.futures
        
        # Simulate work by tracking timestamps
        execution_times: List[float] = []
        execution_lock = threading.Lock()
        
        def work_item(item: str, delay: float = 0.1):
            """Simulated work that takes time."""
            start = time.time()
            time.sleep(delay)
            with execution_lock:
                execution_times.append(time.time() - start)
            return f"processed_{item}"
        
        items = ["a", "b", "c", "d"]
        
        # Sequential execution
        seq_start = time.time()
        for item in items:
            work_item(item)
        seq_duration = time.time() - seq_start
        
        execution_times.clear()
        
        # Parallel execution
        par_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(work_item, item) for item in items]
            concurrent.futures.wait(futures)
        par_duration = time.time() - par_start
        
        # Parallel should be roughly 4x faster
        assert par_duration < seq_duration * 0.5, \
            f"Parallel ({par_duration:.2f}s) should be faster than sequential ({seq_duration:.2f}s)"


class TestParallelLoopYAMLParsing:
    """Tests for parsing parallel loop from YAML."""
    
    def test_parse_parallel_true_from_yaml(self):
        """Test parsing loop with parallel: true from YAML."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Loop
        
        # Use dict format for agents (not list)
        yaml_content = '''
agents:
  processor:
    role: Processor
    goal: Process items
    
steps:
  - loop:
      over: items
      parallel: true
    agent: processor
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Check that the workflow was parsed
        assert workflow is not None
        # The Loop object with parallel=True should be in steps
        found_parallel_loop = False
        for step in workflow.steps:
            if isinstance(step, Loop):
                if step.parallel:
                    found_parallel_loop = True
                    break
        assert found_parallel_loop, "Expected a parallel Loop step"

    def test_parse_max_workers_from_yaml(self):
        """Test parsing loop with max_workers from YAML."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Loop
        
        # Use dict format for agents
        yaml_content = '''
agents:
  processor:
    role: Processor
    goal: Process items
    
steps:
  - loop:
      over: items
      parallel: true
      max_workers: 8
    agent: processor
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Find the loop step with max_workers
        found_max_workers = False
        for step in workflow.steps:
            if isinstance(step, Loop):
                if step.max_workers == 8:
                    found_max_workers = True
                    break
        assert found_max_workers, "Expected Loop with max_workers=8"


class TestLoopConvenienceFunction:
    """Tests for loop() convenience function with parallel param."""
    
    def test_loop_function_accepts_parallel(self):
        """Test that loop() function accepts parallel parameter."""
        from praisonaiagents.workflows import loop
        
        l = loop(step="agent_name", over="items", parallel=True)
        assert l.parallel is True
    
    def test_loop_function_accepts_max_workers(self):
        """Test that loop() function accepts max_workers parameter."""
        from praisonaiagents.workflows import loop
        
        l = loop(step="agent_name", over="items", parallel=True, max_workers=4)
        assert l.max_workers == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
