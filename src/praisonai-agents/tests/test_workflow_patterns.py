"""
Unit tests for Workflow Patterns: route, parallel, loop, repeat

Test-Driven Development tests for all workflow pattern features.
"""

import pytest
import tempfile
import os
from praisonaiagents import Workflow, WorkflowContext, StepResult, Pipeline
from praisonaiagents.workflows import (
    route, parallel, loop, repeat,
    Route, Parallel, Loop, Repeat,
    WorkflowStep, WorkflowManager
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def simple_step():
    """A simple step that returns its input."""
    def step(ctx: WorkflowContext) -> StepResult:
        return StepResult(output=f"Processed: {ctx.input}")
    return step


@pytest.fixture
def csv_file():
    """Create a temporary CSV file for testing."""
    content = """name,email,task
Alice,alice@example.com,Write docs
Bob,bob@example.com,Review code
Charlie,charlie@example.com,Test features"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(content)
        path = f.name
    
    yield path
    
    # Cleanup
    os.unlink(path)


# =============================================================================
# Test: Basic Workflow
# =============================================================================

class TestBasicWorkflow:
    """Test basic workflow functionality."""
    
    def test_sequential_steps(self):
        """Test sequential step execution."""
        def step1(ctx): return StepResult(output="Step 1")
        def step2(ctx): return StepResult(output="Step 2")
        def step3(ctx): return StepResult(output="Step 3")
        
        workflow = Workflow(steps=[step1, step2, step3])
        result = workflow.start("test")
        
        assert result["output"] == "Step 3"
        assert len(result["steps"]) == 3
    
    def test_context_passing(self):
        """Test that context is passed between steps."""
        def step1(ctx): 
            return StepResult(output="Hello", variables={"greeting": "Hello"})
        
        def step2(ctx):
            greeting = ctx.variables.get("greeting", "")
            prev = ctx.previous_result
            return StepResult(output=f"{greeting} from step2, prev={prev}")
        
        workflow = Workflow(steps=[step1, step2])
        result = workflow.start("test")
        
        assert "Hello" in result["output"]
        assert "prev=Hello" in result["output"]
    
    def test_early_stop(self):
        """Test early workflow termination."""
        def stopper(ctx): 
            return StepResult(output="Stopped", stop_workflow=True)
        def never_runs(ctx): 
            return StepResult(output="Should not run")
        
        workflow = Workflow(steps=[stopper, never_runs])
        result = workflow.start("test")
        
        assert result["output"] == "Stopped"
        assert len(result["steps"]) == 1
    
    def test_should_run_condition(self):
        """Test conditional step execution with should_run."""
        def always(ctx): return StepResult(output="Always")
        def conditional(ctx): return StepResult(output="Conditional")
        def is_special(ctx): return "special" in ctx.input.lower()
        
        workflow = Workflow(steps=[
            WorkflowStep(name="always", handler=always),
            WorkflowStep(name="conditional", handler=conditional, should_run=is_special)
        ])
        
        # Without "special" - conditional should be skipped
        result = workflow.start("normal input")
        assert len([s for s in result["steps"] if s["output"]]) == 1
        
        # With "special" - both should run
        result = workflow.start("special input")
        assert len([s for s in result["steps"] if s["output"]]) == 2


# =============================================================================
# Test: Route Pattern
# =============================================================================

class TestRoutePattern:
    """Test decision-based routing."""
    
    def test_route_creation(self):
        """Test Route class creation."""
        r = route({"a": ["step_a"], "b": ["step_b"]})
        assert isinstance(r, Route)
        assert "a" in r.routes
        assert "b" in r.routes
    
    def test_route_with_default(self):
        """Test Route with default fallback."""
        r = route({"a": ["step_a"]}, default=["fallback"])
        assert r.default == ["fallback"]
    
    def test_route_matching(self):
        """Test route matching based on output."""
        def classifier(ctx): 
            return StepResult(output="approve this request")
        def approve(ctx): 
            return StepResult(output="Approved!")
        def reject(ctx): 
            return StepResult(output="Rejected!")
        
        workflow = Workflow(steps=[
            classifier,
            route({
                "approve": [approve],
                "reject": [reject]
            })
        ])
        
        result = workflow.start("test")
        assert "Approved" in result["output"]
    
    def test_route_default_fallback(self):
        """Test route falls back to default when no match."""
        def classifier(ctx): 
            return StepResult(output="unknown category")
        def fallback(ctx): 
            return StepResult(output="Fallback executed")
        
        workflow = Workflow(steps=[
            classifier,
            route({
                "approve": [lambda ctx: StepResult(output="Approved")],
                "default": [fallback]
            })
        ])
        
        result = workflow.start("test")
        assert "Fallback" in result["output"]
    
    def test_route_multi_step(self):
        """Test route with multiple steps in a branch."""
        def classifier(ctx): 
            return StepResult(output="process")
        def step1(ctx): 
            return StepResult(output="Step1", variables={"step1": True})
        def step2(ctx): 
            return StepResult(output="Step2")
        
        workflow = Workflow(steps=[
            classifier,
            route({"process": [step1, step2]})
        ])
        
        result = workflow.start("test")
        assert result["output"] == "Step2"
        assert result["variables"].get("step1") == True


# =============================================================================
# Test: Parallel Pattern
# =============================================================================

class TestParallelPattern:
    """Test concurrent execution."""
    
    def test_parallel_creation(self):
        """Test Parallel class creation."""
        p = parallel(["step1", "step2", "step3"])
        assert isinstance(p, Parallel)
        assert len(p.steps) == 3
    
    def test_parallel_execution(self):
        """Test parallel step execution."""
        def task_a(ctx): return StepResult(output="Result A")
        def task_b(ctx): return StepResult(output="Result B")
        def task_c(ctx): return StepResult(output="Result C")
        
        workflow = Workflow(steps=[
            parallel([task_a, task_b, task_c])
        ])
        
        result = workflow.start("test")
        
        # All outputs should be in combined result
        assert "Result A" in result["output"]
        assert "Result B" in result["output"]
        assert "Result C" in result["output"]
        
        # parallel_outputs variable should have all results
        assert len(result["variables"]["parallel_outputs"]) == 3
    
    def test_parallel_with_aggregator(self):
        """Test parallel followed by aggregator."""
        def task_a(ctx): return StepResult(output="A")
        def task_b(ctx): return StepResult(output="B")
        
        def aggregator(ctx):
            outputs = ctx.variables.get("parallel_outputs", [])
            return StepResult(output=f"Combined: {len(outputs)} results")
        
        workflow = Workflow(steps=[
            parallel([task_a, task_b]),
            aggregator
        ])
        
        result = workflow.start("test")
        assert "Combined: 2 results" in result["output"]


# =============================================================================
# Test: Loop Pattern
# =============================================================================

class TestLoopPattern:
    """Test iteration over data."""
    
    def test_loop_creation(self):
        """Test Loop class creation."""
        l = loop("step", over="items")
        assert isinstance(l, Loop)
        assert l.over == "items"
        assert l.var_name == "item"
    
    def test_loop_over_list(self):
        """Test loop over list variable."""
        def processor(ctx):
            item = ctx.variables.get("item", "unknown")
            return StepResult(output=f"Processed: {item}")
        
        workflow = Workflow(
            steps=[loop(processor, over="items")],
            variables={"items": ["apple", "banana", "cherry"]}
        )
        
        result = workflow.start("test")
        
        assert len(result["variables"]["loop_outputs"]) == 3
        assert "Processed: apple" in result["output"]
        assert "Processed: cherry" in result["output"]
    
    def test_loop_with_index(self):
        """Test loop provides index variable."""
        def processor(ctx):
            item = ctx.variables.get("item")
            index = ctx.variables.get("loop_index")
            return StepResult(output=f"[{index}] {item}")
        
        workflow = Workflow(
            steps=[loop(processor, over="items")],
            variables={"items": ["a", "b", "c"]}
        )
        
        result = workflow.start("test")
        
        assert "[0] a" in result["output"]
        assert "[1] b" in result["output"]
        assert "[2] c" in result["output"]
    
    def test_loop_custom_var_name(self):
        """Test loop with custom variable name."""
        def processor(ctx):
            fruit = ctx.variables.get("fruit", "unknown")
            return StepResult(output=f"Fruit: {fruit}")
        
        workflow = Workflow(
            steps=[loop(processor, over="fruits", var_name="fruit")],
            variables={"fruits": ["apple", "banana"]}
        )
        
        result = workflow.start("test")
        assert "Fruit: apple" in result["output"]
    
    def test_loop_from_csv(self, csv_file):
        """Test loop over CSV file."""
        def processor(ctx):
            row = ctx.variables.get("item", {})
            name = row.get("name", "unknown")
            return StepResult(output=f"Name: {name}")
        
        workflow = Workflow(steps=[
            loop(processor, from_csv=csv_file)
        ])
        
        result = workflow.start("test")
        
        assert len(result["variables"]["loop_outputs"]) == 3
        assert "Name: Alice" in result["output"]
        assert "Name: Bob" in result["output"]
        assert "Name: Charlie" in result["output"]
    
    def test_loop_empty_list(self):
        """Test loop with empty list."""
        def processor(ctx):
            return StepResult(output="Should not run")
        
        workflow = Workflow(
            steps=[loop(processor, over="items")],
            variables={"items": []}
        )
        
        result = workflow.start("test")
        assert len(result["variables"]["loop_outputs"]) == 0


# =============================================================================
# Test: Repeat Pattern
# =============================================================================

class TestRepeatPattern:
    """Test evaluator-optimizer pattern."""
    
    def test_repeat_creation(self):
        """Test Repeat class creation."""
        r = repeat("step", until=lambda ctx: True, max_iterations=5)
        assert isinstance(r, Repeat)
        assert r.max_iterations == 5
    
    def test_repeat_until_condition(self):
        """Test repeat stops when condition is met."""
        counter = [0]
        
        def generator(ctx):
            counter[0] += 1
            return StepResult(
                output=f"Count: {counter[0]}",
                variables={"count": counter[0]}
            )
        
        def is_done(ctx):
            return ctx.variables.get("count", 0) >= 3
        
        workflow = Workflow(steps=[
            repeat(generator, until=is_done, max_iterations=10)
        ])
        
        result = workflow.start("test")
        
        assert result["variables"]["repeat_iterations"] == 3
        assert counter[0] == 3
    
    def test_repeat_max_iterations(self):
        """Test repeat respects max_iterations."""
        counter = [0]
        
        def generator(ctx):
            counter[0] += 1
            return StepResult(output=f"Count: {counter[0]}")
        
        # Never-true condition
        def never_done(ctx):
            return False
        
        workflow = Workflow(steps=[
            repeat(generator, until=never_done, max_iterations=5)
        ])
        
        result = workflow.start("test")
        
        assert result["variables"]["repeat_iterations"] == 5
        assert counter[0] == 5
    
    def test_repeat_without_condition(self):
        """Test repeat without until condition runs max_iterations times."""
        counter = [0]
        
        def generator(ctx):
            counter[0] += 1
            return StepResult(output=f"Count: {counter[0]}")
        
        workflow = Workflow(steps=[
            repeat(generator, max_iterations=3)
        ])
        
        result = workflow.start("test")
        
        assert counter[0] == 3
    
    def test_repeat_with_early_stop(self):
        """Test repeat stops on stop_workflow=True."""
        counter = [0]
        
        def generator(ctx):
            counter[0] += 1
            if counter[0] >= 2:
                return StepResult(output="Stopping", stop_workflow=True)
            return StepResult(output=f"Count: {counter[0]}")
        
        workflow = Workflow(steps=[
            repeat(generator, max_iterations=10)
        ])
        
        result = workflow.start("test")
        
        assert counter[0] == 2


# =============================================================================
# Test: Pipeline Alias
# =============================================================================

class TestPipelineAlias:
    """Test Pipeline is an alias for Workflow."""
    
    def test_pipeline_is_workflow(self):
        """Test Pipeline is the same class as Workflow."""
        assert Pipeline is Workflow
    
    def test_pipeline_works(self):
        """Test Pipeline can be used like Workflow."""
        def step1(ctx): return StepResult(output="Pipeline works!")
        
        pipeline = Pipeline(steps=[step1])
        result = pipeline.start("test")
        
        assert result["output"] == "Pipeline works!"


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Test backward compatibility with old import paths."""
    
    def test_import_from_memory_workflows(self):
        """Test imports from praisonaiagents.memory.workflows still work."""
        from praisonaiagents.memory.workflows import (
            Workflow, WorkflowStep, WorkflowContext, StepResult,
            route, parallel, loop, repeat
        )
        
        assert Workflow is not None
        assert route is not None
    
    def test_import_from_memory_module(self):
        """Test imports from praisonaiagents.memory still work."""
        from praisonaiagents.memory import Workflow, Pipeline, route, parallel
        
        assert Workflow is not None
        assert Pipeline is Workflow
    
    def test_step_input_output_aliases(self):
        """Test StepInput/StepOutput backward compatibility aliases."""
        from praisonaiagents.workflows import StepInput, StepOutput
        
        # These should be aliases for WorkflowContext and StepResult
        assert StepInput is WorkflowContext
        assert StepOutput is StepResult


# =============================================================================
# Test: Combined Patterns
# =============================================================================

class TestCombinedPatterns:
    """Test combining multiple patterns."""
    
    def test_parallel_then_route(self):
        """Test parallel followed by routing."""
        def task_a(ctx): return StepResult(output="success from A")
        def task_b(ctx): return StepResult(output="success from B")
        
        def classifier(ctx):
            outputs = ctx.variables.get("parallel_outputs", [])
            if all("success" in o for o in outputs):
                return StepResult(output="all success")
            return StepResult(output="some failed")
        
        def success_handler(ctx): return StepResult(output="All tasks succeeded!")
        def failure_handler(ctx): return StepResult(output="Some tasks failed!")
        
        workflow = Workflow(steps=[
            parallel([task_a, task_b]),
            classifier,
            route({
                "success": [success_handler],
                "failed": [failure_handler]
            })
        ])
        
        result = workflow.start("test")
        assert "succeeded" in result["output"]
    
    def test_loop_with_aggregation(self):
        """Test loop followed by aggregation step."""
        def processor(ctx):
            item = ctx.variables.get("item")
            return StepResult(output=f"Processed: {item}")
        
        def aggregator(ctx):
            outputs = ctx.variables.get("loop_outputs", [])
            return StepResult(output=f"Total: {len(outputs)} items processed")
        
        workflow = Workflow(
            steps=[
                loop(processor, over="items"),
                aggregator
            ],
            variables={"items": ["a", "b", "c", "d"]}
        )
        
        result = workflow.start("test")
        assert "Total: 4 items processed" in result["output"]


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
