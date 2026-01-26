"""
Unit tests for Nested Workflow Patterns and Conditional Branching (if:)

TDD tests for:
1. Nested loops (loop inside loop)
2. Nested parallel (parallel inside loop)
3. Nested route (route inside loop)
4. Conditional branching (if: pattern)
5. Depth limit enforcement
"""

import pytest
from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.workflows import loop, Loop, parallel, route


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def simple_processor():
    """A simple step that processes items."""
    def processor(ctx: WorkflowContext) -> StepResult:
        item = ctx.variables.get("item", "unknown")
        return StepResult(output=f"Processed: {item}")
    return processor


@pytest.fixture
def sub_processor():
    """A processor for nested items."""
    def processor(ctx: WorkflowContext) -> StepResult:
        item = ctx.variables.get("item", "unknown")
        sub_item = ctx.variables.get("sub_item", "unknown")
        return StepResult(output=f"Processed: {item}/{sub_item}")
    return processor


# =============================================================================
# Test: Nested Loops
# =============================================================================

class TestNestedLoops:
    """Test loop inside loop execution."""
    
    def test_nested_loop_basic(self):
        """Test basic nested loop execution."""
        results = []
        
        def outer_processor(ctx: WorkflowContext) -> StepResult:
            category = ctx.variables.get("category", "unknown")
            results.append(f"outer:{category}")
            return StepResult(output=f"Category: {category}")
        
        def inner_processor(ctx: WorkflowContext) -> StepResult:
            category = ctx.variables.get("category", "unknown")
            item = ctx.variables.get("item", "unknown")
            results.append(f"inner:{category}/{item}")
            return StepResult(output=f"Item: {category}/{item}")
        
        # Nested loop: outer loops over categories, inner loops over items
        workflow = Workflow(
            steps=[
                loop(
                    steps=[
                        outer_processor,
                        loop(inner_processor, over="items", var_name="item")
                    ],
                    over="categories",
                    var_name="category"
                )
            ],
            variables={
                "categories": ["A", "B"],
                "items": ["1", "2"]
            }
        )
        
        result = workflow.start("test")
        
        # Should have processed all combinations
        assert "outer:A" in results
        assert "outer:B" in results
        assert "inner:A/1" in results
        assert "inner:A/2" in results
        assert "inner:B/1" in results
        assert "inner:B/2" in results
    
    def test_nested_loop_with_dynamic_items(self):
        """Test nested loop where inner items come from outer item."""
        results = []
        
        def inner_processor(ctx: WorkflowContext) -> StepResult:
            category = ctx.variables.get("category", {})
            item = ctx.variables.get("item", "unknown")
            cat_name = category.get("name", "unknown") if isinstance(category, dict) else str(category)
            results.append(f"{cat_name}/{item}")
            return StepResult(output=f"Processed: {cat_name}/{item}")
        
        workflow = Workflow(
            steps=[
                loop(
                    steps=[
                        loop(inner_processor, over="category.items", var_name="item")
                    ],
                    over="categories",
                    var_name="category"
                )
            ],
            variables={
                "categories": [
                    {"name": "Fruits", "items": ["apple", "banana"]},
                    {"name": "Veggies", "items": ["carrot", "potato"]}
                ]
            }
        )
        
        result = workflow.start("test")
        
        # Should process items from each category
        assert len(results) >= 4  # At least 4 items processed
    
    def test_nested_loop_depth_limit(self):
        """Test that deeply nested loops are limited."""
        def processor(ctx: WorkflowContext) -> StepResult:
            return StepResult(output="processed")
        
        # Create deeply nested loops (6 levels - should exceed limit of 5)
        inner = loop(processor, over="items")
        for _ in range(5):  # 5 more levels = 6 total
            inner = loop(steps=[inner], over="items")
        
        workflow = Workflow(
            steps=[inner],
            variables={"items": ["a"]}
        )
        
        # Should raise error or handle gracefully
        with pytest.raises((ValueError, RecursionError)):
            workflow.start("test")


# =============================================================================
# Test: Nested Parallel
# =============================================================================

class TestNestedParallel:
    """Test parallel inside loop and loop inside parallel."""
    
    def test_parallel_inside_loop(self):
        """Test parallel execution inside a loop."""
        results = []
        
        def task_a(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", "unknown")
            results.append(f"A:{item}")
            return StepResult(output=f"A processed {item}")
        
        def task_b(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", "unknown")
            results.append(f"B:{item}")
            return StepResult(output=f"B processed {item}")
        
        workflow = Workflow(
            steps=[
                loop(
                    steps=[parallel([task_a, task_b])],
                    over="items",
                    var_name="item"
                )
            ],
            variables={"items": ["X", "Y"]}
        )
        
        result = workflow.start("test")
        
        # Both tasks should run for each item
        assert "A:X" in results
        assert "B:X" in results
        assert "A:Y" in results
        assert "B:Y" in results
    
    def test_loop_inside_parallel(self):
        """Test loop execution inside parallel branches."""
        results = []
        
        def loop_processor(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", "unknown")
            results.append(f"loop:{item}")
            return StepResult(output=f"Looped: {item}")
        
        def simple_task(ctx: WorkflowContext) -> StepResult:
            results.append("simple")
            return StepResult(output="Simple done")
        
        workflow = Workflow(
            steps=[
                parallel([
                    loop(loop_processor, over="items", var_name="item"),
                    simple_task
                ])
            ],
            variables={"items": ["1", "2", "3"]}
        )
        
        result = workflow.start("test")
        
        # Loop should process all items, simple task should run once
        assert "loop:1" in results
        assert "loop:2" in results
        assert "loop:3" in results
        assert "simple" in results


# =============================================================================
# Test: Nested Route
# =============================================================================

class TestNestedRoute:
    """Test route inside loop."""
    
    def test_route_inside_loop(self):
        """Test routing decisions inside a loop."""
        results = []
        
        def classifier(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", {})
            item_type = item.get("type", "unknown") if isinstance(item, dict) else "unknown"
            return StepResult(output=item_type)
        
        def handle_a(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", {})
            results.append(f"handled_a:{item.get('name', 'unknown')}")
            return StepResult(output="A handled")
        
        def handle_b(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", {})
            results.append(f"handled_b:{item.get('name', 'unknown')}")
            return StepResult(output="B handled")
        
        workflow = Workflow(
            steps=[
                loop(
                    steps=[
                        classifier,
                        route({"a": [handle_a], "b": [handle_b]})
                    ],
                    over="items",
                    var_name="item"
                )
            ],
            variables={
                "items": [
                    {"name": "item1", "type": "a"},
                    {"name": "item2", "type": "b"},
                    {"name": "item3", "type": "a"}
                ]
            }
        )
        
        result = workflow.start("test")
        
        # Items should be routed correctly
        assert "handled_a:item1" in results
        assert "handled_b:item2" in results
        assert "handled_a:item3" in results


# =============================================================================
# Test: Conditional Branching (if:)
# =============================================================================

class TestConditionalBranching:
    """Test if: conditional pattern."""
    
    def test_if_pattern_creation(self):
        """Test If class can be created."""
        from praisonaiagents.workflows import if_, If
        
        def then_step(ctx): return StepResult(output="then")
        def else_step(ctx): return StepResult(output="else")
        
        cond = if_(
            condition="{{score}} > 80",
            then_steps=[then_step],
            else_steps=[else_step]
        )
        
        assert isinstance(cond, If)
        assert cond.condition == "{{score}} > 80"
        assert len(cond.then_steps) == 1
        assert len(cond.else_steps) == 1
    
    def test_if_true_branch(self):
        """Test if: executes then branch when condition is true."""
        from praisonaiagents.workflows import if_
        
        results = []
        
        def then_step(ctx: WorkflowContext) -> StepResult:
            results.append("then_executed")
            return StepResult(output="Then branch")
        
        def else_step(ctx: WorkflowContext) -> StepResult:
            results.append("else_executed")
            return StepResult(output="Else branch")
        
        workflow = Workflow(
            steps=[
                if_(
                    condition="{{score}} > 80",
                    then_steps=[then_step],
                    else_steps=[else_step]
                )
            ],
            variables={"score": 90}  # 90 > 80 = True
        )
        
        result = workflow.start("test")
        
        assert "then_executed" in results
        assert "else_executed" not in results
        assert "Then branch" in result["output"]
    
    def test_if_false_branch(self):
        """Test if: executes else branch when condition is false."""
        from praisonaiagents.workflows import if_
        
        results = []
        
        def then_step(ctx: WorkflowContext) -> StepResult:
            results.append("then_executed")
            return StepResult(output="Then branch")
        
        def else_step(ctx: WorkflowContext) -> StepResult:
            results.append("else_executed")
            return StepResult(output="Else branch")
        
        workflow = Workflow(
            steps=[
                if_(
                    condition="{{score}} > 80",
                    then_steps=[then_step],
                    else_steps=[else_step]
                )
            ],
            variables={"score": 50}  # 50 > 80 = False
        )
        
        result = workflow.start("test")
        
        assert "else_executed" in results
        assert "then_executed" not in results
        assert "Else branch" in result["output"]
    
    def test_if_no_else_branch(self):
        """Test if: without else branch."""
        from praisonaiagents.workflows import if_
        
        results = []
        
        def then_step(ctx: WorkflowContext) -> StepResult:
            results.append("then_executed")
            return StepResult(output="Then branch")
        
        workflow = Workflow(
            steps=[
                if_(
                    condition="{{score}} > 80",
                    then_steps=[then_step]
                    # No else_steps
                )
            ],
            variables={"score": 50}  # False, no else
        )
        
        result = workflow.start("test")
        
        # Should not execute then, and should not error
        assert "then_executed" not in results
    
    def test_if_string_condition(self):
        """Test if: with string equality condition."""
        from praisonaiagents.workflows import if_
        
        results = []
        
        def approved(ctx: WorkflowContext) -> StepResult:
            results.append("approved")
            return StepResult(output="Approved!")
        
        def rejected(ctx: WorkflowContext) -> StepResult:
            results.append("rejected")
            return StepResult(output="Rejected!")
        
        workflow = Workflow(
            steps=[
                if_(
                    condition="{{status}} == approved",
                    then_steps=[approved],
                    else_steps=[rejected]
                )
            ],
            variables={"status": "approved"}
        )
        
        result = workflow.start("test")
        
        assert "approved" in results
        assert "rejected" not in results
    
    def test_if_contains_condition(self):
        """Test if: with 'contains' condition."""
        from praisonaiagents.workflows import if_
        
        results = []
        
        def has_error(ctx: WorkflowContext) -> StepResult:
            results.append("has_error")
            return StepResult(output="Error found")
        
        def no_error(ctx: WorkflowContext) -> StepResult:
            results.append("no_error")
            return StepResult(output="No error")
        
        workflow = Workflow(
            steps=[
                if_(
                    condition="error in {{message}}",
                    then_steps=[has_error],
                    else_steps=[no_error]
                )
            ],
            variables={"message": "This has an error in it"}
        )
        
        result = workflow.start("test")
        
        assert "has_error" in results
    
    def test_if_inside_loop(self):
        """Test if: pattern inside a loop."""
        from praisonaiagents.workflows import if_
        
        results = []
        
        def pass_handler(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", {})
            results.append(f"pass:{item.get('name', 'unknown')}")
            return StepResult(output="Passed")
        
        def fail_handler(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", {})
            results.append(f"fail:{item.get('name', 'unknown')}")
            return StepResult(output="Failed")
        
        workflow = Workflow(
            steps=[
                loop(
                    steps=[
                        if_(
                            condition="{{item.score}} >= 60",
                            then_steps=[pass_handler],
                            else_steps=[fail_handler]
                        )
                    ],
                    over="students",
                    var_name="item"
                )
            ],
            variables={
                "students": [
                    {"name": "Alice", "score": 85},
                    {"name": "Bob", "score": 45},
                    {"name": "Charlie", "score": 72}
                ]
            }
        )
        
        result = workflow.start("test")
        
        assert "pass:Alice" in results
        assert "fail:Bob" in results
        assert "pass:Charlie" in results


# =============================================================================
# Test: YAML Parsing for New Patterns
# =============================================================================

class TestYAMLParsing:
    """Test YAML parsing for nested patterns and if:."""
    
    def test_parse_nested_loop_yaml(self):
        """Test parsing nested loop from YAML."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        import tempfile
        import os
        
        yaml_content = """
name: Nested Loop Test
variables:
  categories:
    - name: A
      items: [1, 2]
    - name: B
      items: [3, 4]

agents:
  processor:
    role: Processor
    goal: Process items

steps:
  - loop:
      over: categories
      var_name: category
    steps:
      - loop:
          over: category.items
          var_name: item
        agent: processor
        action: "Process {{category.name}}/{{item}}"
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            parser = YAMLWorkflowParser()
            workflow = parser.parse_file(yaml_path)
            
            # Should have parsed the nested loop structure
            assert len(workflow.steps) >= 1
            first_step = workflow.steps[0]
            assert isinstance(first_step, Loop)
        finally:
            os.unlink(yaml_path)
    
    def test_parse_if_yaml(self):
        """Test parsing if: pattern from YAML."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        from praisonaiagents.workflows import If
        import tempfile
        import os
        
        yaml_content = """
name: Conditional Test
variables:
  score: 85

agents:
  approver:
    role: Approver
    goal: Approve items
  rejector:
    role: Rejector
    goal: Reject items

steps:
  - if:
      condition: "{{score}} > 80"
      then:
        - agent: approver
          action: "Approve with score {{score}}"
      else:
        - agent: rejector
          action: "Reject with score {{score}}"
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            parser = YAMLWorkflowParser()
            workflow = parser.parse_file(yaml_path)
            
            # Should have parsed the if pattern
            assert len(workflow.steps) >= 1
            first_step = workflow.steps[0]
            assert isinstance(first_step, If)
            assert first_step.condition == "{{score}} > 80"
        finally:
            os.unlink(yaml_path)
