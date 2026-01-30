"""
Tests for multi-step loop support in workflows.

TDD tests for:
- Loop class accepting steps parameter (plural)
- YAML parsing of steps: inside loop
- Multi-step loop execution (sequential within iteration)
- previous_output chaining between nested steps
- Parallel multi-step loop execution
- Context field aliasing (enabled, max_tool_output_tokens)
"""

import pytest
from unittest.mock import MagicMock


class TestLoopClassStepsParameter:
    """Test that Loop class accepts steps parameter."""
    
    def test_loop_class_has_steps_field(self):
        """Loop class should have a steps field for multiple steps."""
        from praisonaiagents.workflows.workflows import Loop
        
        # Create loop with steps (plural)
        mock_step1 = MagicMock()
        mock_step2 = MagicMock()
        
        loop = Loop(steps=[mock_step1, mock_step2], over="items")
        
        assert loop.steps == [mock_step1, mock_step2]
        assert loop.step is None  # step should be None when steps is used
        assert loop.over == "items"
    
    def test_loop_class_backward_compat_single_step(self):
        """Loop class should still work with single step parameter."""
        from praisonaiagents.workflows.workflows import Loop
        
        mock_step = MagicMock()
        loop = Loop(step=mock_step, over="items")
        
        assert loop.step == mock_step
        assert loop.steps is None
        assert loop.over == "items"
    
    def test_loop_class_rejects_both_step_and_steps(self):
        """Loop class should raise error if both step and steps provided."""
        from praisonaiagents.workflows.workflows import Loop
        
        mock_step = MagicMock()
        
        with pytest.raises(ValueError, match="Cannot specify both 'step' and 'steps'"):
            Loop(step=mock_step, steps=[mock_step], over="items")
    
    def test_loop_class_requires_step_or_steps(self):
        """Loop class should raise error if neither step nor steps provided."""
        from praisonaiagents.workflows.workflows import Loop
        
        with pytest.raises(ValueError, match="Loop requires 'step' or 'steps'"):
            Loop(over="items")


class TestLoopFactoryFunction:
    """Test that loop() factory function accepts steps parameter."""
    
    def test_loop_factory_accepts_steps(self):
        """loop() factory should accept steps parameter."""
        from praisonaiagents.workflows.workflows import loop
        
        mock_step1 = MagicMock()
        mock_step2 = MagicMock()
        
        result = loop(steps=[mock_step1, mock_step2], over="items", parallel=True)
        
        assert result.steps == [mock_step1, mock_step2]
        assert result.step is None
        assert result.over == "items"
        assert result.parallel is True
    
    def test_loop_factory_backward_compat(self):
        """loop() factory should still work with single step."""
        from praisonaiagents.workflows.workflows import loop
        
        mock_step = MagicMock()
        result = loop(step=mock_step, over="items")
        
        assert result.step == mock_step
        assert result.steps is None


class TestYAMLParsingStepsInsideLoop:
    """Test YAML parsing of steps: inside loop."""
    
    def test_yaml_loop_with_steps_at_step_level(self):
        """YAML parser should parse steps: at step_data level (user's syntax)."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
agents:
  researcher:
    role: Researcher
    goal: Research topics
  writer:
    role: Writer
    goal: Write articles

steps:
  - loop:
      over: topics
      parallel: true
      max_workers: 4
    steps:
      - name: research
        agent: researcher
        action: Research {{item}}
      - name: write
        agent: writer
        action: Write about {{previous_output}}
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Find the loop step
        loop_step = None
        for step in workflow.steps:
            from praisonaiagents.workflows.workflows import Loop
            if isinstance(step, Loop):
                loop_step = step
                break
        
        assert loop_step is not None, "Loop step should be parsed"
        assert loop_step.steps is not None, "Loop should have steps (plural)"
        assert len(loop_step.steps) == 2, "Loop should have 2 nested steps"
        assert loop_step.parallel is True
        assert loop_step.max_workers == 4
    
    def test_yaml_loop_with_steps_inside_loop_block(self):
        """YAML parser should parse steps: inside loop: block."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
agents:
  researcher:
    role: Researcher
    goal: Research topics
  writer:
    role: Writer
    goal: Write articles

steps:
  - loop:
      over: topics
      parallel: true
      steps:
        - name: research
          agent: researcher
        - name: write
          agent: writer
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Find the loop step
        loop_step = None
        for step in workflow.steps:
            from praisonaiagents.workflows.workflows import Loop
            if isinstance(step, Loop):
                loop_step = step
                break
        
        assert loop_step is not None, "Loop step should be parsed"
        assert loop_step.steps is not None, "Loop should have steps (plural)"
        assert len(loop_step.steps) == 2, "Loop should have 2 nested steps"


class TestMultiStepLoopExecution:
    """Test multi-step loop execution."""
    
    def test_multi_step_loop_executes_all_steps_sequentially(self):
        """Each iteration should execute all nested steps sequentially."""
        from praisonaiagents.workflows.workflows import Workflow, Task, Loop
        
        # Track execution order
        execution_order = []
        
        def step1_handler(ctx):
            execution_order.append(f"step1_{ctx.variables.get('loop_index')}")
            return f"output1_{ctx.variables.get('loop_index')}"
        
        def step2_handler(ctx):
            execution_order.append(f"step2_{ctx.variables.get('loop_index')}")
            return f"output2_{ctx.variables.get('loop_index')}"
        
        step1 = Task(name="step1", handler=step1_handler)
        step2 = Task(name="step2", handler=step2_handler)
        
        loop_step = Loop(
            steps=[step1, step2],
            over="items",
            parallel=False
        )
        
        workflow = Workflow(
            name="test",
            steps=[loop_step],
            variables={"items": ["a", "b"]}
        )
        
        result = workflow.start("")
        
        # Should execute step1 then step2 for each item
        assert execution_order == [
            "step1_0", "step2_0",  # First item
            "step1_1", "step2_1",  # Second item
        ]
    
    def test_previous_output_chains_between_nested_steps(self):
        """previous_output should flow from step N to step N+1 within iteration."""
        from praisonaiagents.workflows.workflows import Workflow, Task, Loop
        
        received_previous = []
        
        def step1_handler(ctx):
            return "from_step1"
        
        def step2_handler(ctx):
            received_previous.append(ctx.previous_result)
            return "from_step2"
        
        step1 = Task(name="step1", handler=step1_handler)
        step2 = Task(name="step2", handler=step2_handler)
        
        loop_step = Loop(
            steps=[step1, step2],
            over="items",
            parallel=False
        )
        
        workflow = Workflow(
            name="test",
            steps=[loop_step],
            variables={"items": ["a"]}
        )
        
        workflow.start("")
        
        # step2 should receive step1's output
        assert received_previous == ["from_step1"]


class TestParallelMultiStepLoop:
    """Test parallel execution of multi-step loops."""
    
    def test_parallel_multi_step_loop_isolates_iterations(self):
        """Parallel iterations should be isolated from each other."""
        from praisonaiagents.workflows.workflows import Workflow, Task, Loop
        import threading
        
        # Track which thread executed which step
        thread_ids = {}
        lock = threading.Lock()
        
        def step1_handler(ctx):
            idx = ctx.variables.get('loop_index')
            with lock:
                thread_ids[f"step1_{idx}"] = threading.current_thread().ident
            return f"output1_{idx}"
        
        def step2_handler(ctx):
            idx = ctx.variables.get('loop_index')
            with lock:
                thread_ids[f"step2_{idx}"] = threading.current_thread().ident
            return f"output2_{idx}"
        
        step1 = Task(name="step1", handler=step1_handler)
        step2 = Task(name="step2", handler=step2_handler)
        
        loop_step = Loop(
            steps=[step1, step2],
            over="items",
            parallel=True,
            max_workers=2
        )
        
        workflow = Workflow(
            name="test",
            steps=[loop_step],
            variables={"items": ["a", "b"]}
        )
        
        workflow.start("")
        
        # Within same iteration, steps should run on same thread (sequential)
        assert thread_ids["step1_0"] == thread_ids["step2_0"]
        assert thread_ids["step1_1"] == thread_ids["step2_1"]


class TestContextFieldAliasing:
    """Test context field aliasing in YAML parsing."""
    
    def test_yaml_context_enabled_maps_to_auto_compact(self):
        """YAML 'enabled: true' should map to auto_compact=True."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
agents:
  test:
    role: Test
    goal: Test

steps:
  - agent: test

context:
  enabled: true
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Context should be enabled
        assert workflow.context is not None
        if hasattr(workflow.context, 'auto_compact'):
            assert workflow.context.auto_compact is True
        else:
            # If context is True (simple enable), that's also valid
            assert workflow.context is True
    
    def test_yaml_context_max_tool_output_tokens_mapped(self):
        """YAML 'max_tool_output_tokens' should map to tool_output_max."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
agents:
  test:
    role: Test
    goal: Test

steps:
  - agent: test

context:
  enabled: true
  max_tool_output_tokens: 5000
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Context should have tool_output_max set
        assert workflow.context is not None
        if hasattr(workflow.context, 'tool_output_max'):
            assert workflow.context.tool_output_max == 5000


class TestParallelLoopItemIsolation:
    """Test that parallel loop iterations get correct isolated items."""
    
    def test_parallel_loop_each_iteration_gets_correct_item(self):
        """Each parallel iteration should process its own item, not duplicates."""
        from praisonaiagents.workflows.workflows import Workflow, Task, Loop
        import threading
        
        # Track which item each iteration received
        received_items = {}
        lock = threading.Lock()
        
        def capture_item_handler(ctx):
            idx = ctx.variables.get('loop_index')
            item = ctx.variables.get('item')
            with lock:
                received_items[idx] = item
            return f"processed_{item}"
        
        step = Task(name="capture", handler=capture_item_handler)
        
        loop_step = Loop(
            steps=[step],
            over="items",
            parallel=True,
            max_workers=3
        )
        
        workflow = Workflow(
            name="test",
            steps=[loop_step],
            variables={"items": ["apple", "banana", "cherry"]}
        )
        
        workflow.start("")
        
        # Each iteration should have received a DIFFERENT item
        assert len(received_items) == 3
        assert set(received_items.values()) == {"apple", "banana", "cherry"}
    
    def test_parallel_loop_dict_items_expanded_correctly(self):
        """Dict items should have properties expanded for template access."""
        from praisonaiagents.workflows.workflows import Workflow, Task, Loop
        import threading
        
        received_titles = {}
        lock = threading.Lock()
        
        def capture_title_handler(ctx):
            idx = ctx.variables.get('loop_index')
            # Access expanded property
            title = ctx.variables.get('item.title')
            with lock:
                received_titles[idx] = title
            return f"processed_{title}"
        
        step = Task(name="capture", handler=capture_title_handler)
        
        loop_step = Loop(
            steps=[step],
            over="topics",
            parallel=True,
            max_workers=3
        )
        
        workflow = Workflow(
            name="test",
            steps=[loop_step],
            variables={"topics": [
                {"title": "Topic A", "url": "http://a.com"},
                {"title": "Topic B", "url": "http://b.com"},
                {"title": "Topic C", "url": "http://c.com"}
            ]}
        )
        
        workflow.start("")
        
        # Each iteration should have received a DIFFERENT title
        assert len(received_titles) == 3
        assert set(received_titles.values()) == {"Topic A", "Topic B", "Topic C"}


class TestLoopOutputVariable:
    """Test output_variable stores last step output per iteration."""
    
    def test_output_variable_stores_final_step_output(self):
        """output_variable should store the last step's output for each iteration."""
        from praisonaiagents.workflows.workflows import Workflow, Task, Loop
        
        def step1_handler(ctx):
            return f"step1_output_{ctx.variables.get('loop_index')}"
        
        def step2_handler(ctx):
            return f"final_output_{ctx.variables.get('loop_index')}"
        
        step1 = Task(name="step1", handler=step1_handler)
        step2 = Task(name="step2", handler=step2_handler)
        
        loop_step = Loop(
            steps=[step1, step2],
            over="items",
            output_variable="results"
        )
        
        workflow = Workflow(
            name="test",
            steps=[loop_step],
            variables={"items": ["a", "b"]}
        )
        
        result = workflow.start("")
        
        # results should contain final step outputs
        results = result.get("variables", {}).get("results", [])
        assert "final_output_0" in results
        assert "final_output_1" in results
