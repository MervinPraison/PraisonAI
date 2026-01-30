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
    Task, WorkflowManager,
    WorkflowHooksConfig, WorkflowPlanningConfig, WorkflowOutputConfig,
    TaskExecutionConfig, TaskOutputConfig,
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
            Task(name="always", handler=always),
            Task(name="conditional", handler=conditional, should_run=is_special)
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
            Workflow, Task, WorkflowContext, StepResult,
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
# Test: Callbacks
# =============================================================================

class TestCallbacks:
    """Test workflow and step callbacks."""
    
    def test_on_workflow_start(self):
        """Test on_workflow_start callback is called."""
        called = []
        
        def on_start(workflow, input_text):
            called.append(("start", input_text))
        
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(
            steps=[step1],
            hooks=WorkflowHooksConfig(on_workflow_start=on_start)
        )
        workflow.start("test input")
        
        assert len(called) == 1
        assert called[0] == ("start", "test input")
    
    def test_on_workflow_complete(self):
        """Test on_workflow_complete callback is called."""
        called = []
        
        def on_complete(workflow, result):
            called.append(("complete", result["output"]))
        
        def step1(ctx): return StepResult(output="Final output")
        
        workflow = Workflow(
            steps=[step1],
            hooks=WorkflowHooksConfig(on_workflow_complete=on_complete)
        )
        workflow.start("test")
        
        assert len(called) == 1
        assert called[0] == ("complete", "Final output")
    
    def test_on_step_start(self):
        """Test on_step_start callback is called for each step."""
        called = []
        
        def on_step_start(step_name, context):
            called.append(("step_start", step_name))
        
        def step1(ctx): return StepResult(output="Step 1")
        def step2(ctx): return StepResult(output="Step 2")
        
        workflow = Workflow(
            steps=[step1, step2],
            hooks=WorkflowHooksConfig(on_step_start=on_step_start)
        )
        workflow.start("test")
        
        assert len(called) == 2
        assert called[0][1] == "step1"
        assert called[1][1] == "step2"
    
    def test_on_step_complete(self):
        """Test on_step_complete callback is called for each step."""
        called = []
        
        def on_step_complete(step_name, result):
            called.append(("step_complete", step_name, result.output))
        
        def step1(ctx): return StepResult(output="Output 1")
        def step2(ctx): return StepResult(output="Output 2")
        
        workflow = Workflow(
            steps=[step1, step2],
            hooks=WorkflowHooksConfig(on_step_complete=on_step_complete)
        )
        workflow.start("test")
        
        assert len(called) == 2
        assert called[0] == ("step_complete", "step1", "Output 1")
        assert called[1] == ("step_complete", "step2", "Output 2")
    
    def test_on_step_error(self):
        """Test on_step_error callback is called on error."""
        called = []
        
        def on_error(step_name, error):
            called.append(("error", step_name, str(error)))
        
        def failing_step(ctx):
            raise ValueError("Test error")
        
        workflow = Workflow(
            steps=[failing_step],
            hooks=WorkflowHooksConfig(on_step_error=on_error)
        )
        workflow.start("test")
        
        assert len(called) == 1
        assert called[0][0] == "error"
        assert "Test error" in called[0][2]


# =============================================================================
# Test: Guardrails
# =============================================================================

class TestGuardrails:
    """Test step guardrails and validation."""
    
    def test_guardrail_passes(self):
        """Test guardrail that passes."""
        def validator(result):
            return (True, None)  # Valid
        
        def step1(ctx): return StepResult(output="Valid output")
        
        workflow = Workflow(steps=[
            Task(name="step1", handler=step1, guardrails=validator)
        ])
        result = workflow.start("test")
        
        assert result["output"] == "Valid output"
        assert result["steps"][0]["retries"] == 0
    
    def test_guardrail_fails_and_retries(self):
        """Test guardrail that fails triggers retry."""
        attempt = [0]
        
        def validator(result):
            if "attempt 3" in result.output:
                return (True, None)  # Valid on 3rd attempt
            return (False, "Not valid yet")
        
        def step1(ctx):
            attempt[0] += 1
            return StepResult(output=f"Output attempt {attempt[0]}")
        
        workflow = Workflow(steps=[
            Task(name="step1", handler=step1, guardrails=validator, execution=TaskExecutionConfig(max_retries=5))
        ])
        result = workflow.start("test")
        
        assert "attempt 3" in result["output"]
        assert attempt[0] == 3
    
    def test_guardrail_max_retries_exceeded(self):
        """Test guardrail respects max_retries."""
        attempt = [0]
        
        def validator(result):
            return (False, "Always fails")  # Never valid
        
        def step1(ctx):
            attempt[0] += 1
            return StepResult(output=f"Attempt {attempt[0]}")
        
        workflow = Workflow(steps=[
            Task(name="step1", handler=step1, guardrails=validator, execution=TaskExecutionConfig(max_retries=2))
        ])
        result = workflow.start("test")
        
        # Should have tried 3 times (initial + 2 retries)
        assert attempt[0] == 3
    
    def test_validation_feedback_in_context(self):
        """Test validation feedback is passed to context on retry."""
        feedbacks = []
        
        def validator(result):
            if "fixed" in result.output:
                return (True, None)
            return (False, "Please fix the issue")
        
        def step1(ctx):
            feedback = ctx.variables.get("validation_feedback")
            if feedback:
                feedbacks.append(feedback)
                return StepResult(output="fixed")
            return StepResult(output="initial")
        
        workflow = Workflow(steps=[
            Task(name="step1", handler=step1, guardrails=validator, execution=TaskExecutionConfig(max_retries=3))
        ])
        result = workflow.start("test")
        
        assert result["output"] == "fixed"
        assert len(feedbacks) == 1
        assert "Please fix" in feedbacks[0]


# =============================================================================
# Test: Status Tracking
# =============================================================================

class TestStatusTracking:
    """Test workflow and step status tracking."""
    
    def test_workflow_status(self):
        """Test workflow status is tracked."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1])
        assert workflow.status == "not_started"
        
        workflow.start("test")
        assert workflow.status == "completed"
    
    def test_step_statuses(self):
        """Test step statuses are tracked."""
        def step1(ctx): return StepResult(output="Step 1")
        def step2(ctx): return StepResult(output="Step 2")
        
        workflow = Workflow(steps=[step1, step2])
        workflow.start("test")
        
        assert workflow.step_statuses["step1"] == "completed"
        assert workflow.step_statuses["step2"] == "completed"
    
    def test_skipped_step_status(self):
        """Test skipped step has correct status."""
        def step1(ctx): return StepResult(output="Step 1")
        def step2(ctx): return StepResult(output="Step 2")
        def never_run(ctx): return False
        
        workflow = Workflow(steps=[
            step1,
            Task(name="step2", handler=step2, should_run=never_run)
        ])
        result = workflow.start("test")
        
        assert workflow.step_statuses["step1"] == "completed"
        assert workflow.step_statuses["step2"] == "skipped"
    
    def test_result_includes_status(self):
        """Test result includes status information."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1])
        result = workflow.start("test")
        
        assert result["status"] == "completed"
        assert result["steps"][0]["status"] == "completed"


# =============================================================================
# Test: Documentation Examples (Integration Tests)
# =============================================================================

class TestDocumentationExamples:
    """Test that documentation examples work correctly."""
    
    def test_routing_doc_example(self):
        """Test the routing example from docs/features/routing.mdx"""
        # Classifier - determines which route to take
        def classify_request(ctx: WorkflowContext) -> StepResult:
            input_lower = ctx.input.lower()
            if "urgent" in input_lower:
                return StepResult(output="priority: high")
            elif "question" in input_lower:
                return StepResult(output="priority: support")
            else:
                return StepResult(output="priority: normal")

        def handle_high_priority(ctx): return StepResult(output="HIGH PRIORITY")
        def handle_support(ctx): return StepResult(output="SUPPORT")
        def handle_normal(ctx): return StepResult(output="NORMAL")

        workflow = Workflow(
            steps=[
                classify_request,
                route({
                    "high": [handle_high_priority],
                    "support": [handle_support],
                    "default": [handle_normal]
                })
            ]
        )

        # Test urgent
        result = workflow.start("This is an urgent request!")
        assert "HIGH PRIORITY" in result["output"]

        # Test question
        result = workflow.start("I have a question about billing")
        assert "SUPPORT" in result["output"]

        # Test normal
        result = workflow.start("Please process my order")
        assert "NORMAL" in result["output"]
    
    def test_parallel_doc_example(self):
        """Test the parallel example from docs/features/parallelisation.mdx"""
        def research_market(ctx): return StepResult(output="Market: Growth 15%")
        def research_competitors(ctx): return StepResult(output="Competitors: 3 found")
        def research_customers(ctx): return StepResult(output="Customers: 5 segments")

        def summarize_research(ctx: WorkflowContext) -> StepResult:
            outputs = ctx.variables.get("parallel_outputs", [])
            return StepResult(output=f"Summary: {len(outputs)} items")

        workflow = Workflow(
            steps=[
                parallel([research_market, research_competitors, research_customers]),
                summarize_research
            ]
        )

        result = workflow.start("Research the AI market")
        assert "Summary: 3 items" in result["output"]
    
    def test_repeat_doc_example(self):
        """Test the repeat example from docs/features/evaluator-optimiser.mdx"""
        class ContentGenerator:
            def __init__(self):
                self.points = []
            
            def generate(self, ctx: WorkflowContext) -> StepResult:
                self.points.append(f"Point {len(self.points) + 1}")
                self.points.append(f"Point {len(self.points) + 1}")
                return StepResult(
                    output=f"Generated {len(self.points)} points",
                    variables={"count": len(self.points)}
                )

        def is_complete(ctx: WorkflowContext) -> bool:
            return ctx.variables.get("count", 0) >= 10

        generator = ContentGenerator()

        workflow = Workflow(
            steps=[
                repeat(generator.generate, until=is_complete, max_iterations=10)
            ]
        )

        result = workflow.start("Generate 10 points")
        assert result["variables"].get("count", 0) >= 10
    
    def test_loop_doc_example(self):
        """Test the loop example from docs/features/repetitive.mdx"""
        def process_item(ctx: WorkflowContext) -> StepResult:
            item = ctx.variables.get("item", "unknown")
            index = ctx.variables.get("loop_index", 0)
            return StepResult(output=f"[{index + 1}] Processed: {item}")

        workflow = Workflow(
            steps=[loop(process_item, over="tasks")],
            variables={"tasks": ["Task A", "Task B", "Task C", "Task D"]}
        )

        result = workflow.start("Process all tasks")
        outputs = result["variables"].get("loop_outputs", [])
        assert len(outputs) == 4
        assert "[1] Processed: Task A" in outputs[0]
        assert "[4] Processed: Task D" in outputs[3]
    
    def test_promptchaining_doc_example(self):
        """Test the prompt chaining example from docs/features/promptchaining.mdx"""
        def validate_input(ctx: WorkflowContext) -> StepResult:
            if len(ctx.input) > 5:
                return StepResult(output="valid", variables={"validated": True})
            return StepResult(output="invalid", stop_workflow=True)

        def process_data(ctx: WorkflowContext) -> StepResult:
            return StepResult(output=f"Processed: {ctx.input.upper()}")

        def analyze_results(ctx: WorkflowContext) -> StepResult:
            return StepResult(output=f"Analysis: {ctx.previous_result}")

        def generate_output(ctx: WorkflowContext) -> StepResult:
            return StepResult(output=f"Final: {ctx.previous_result}")

        workflow = Workflow(
            steps=[validate_input, process_data, analyze_results, generate_output]
        )

        # Valid input
        result = workflow.start("Hello World")
        assert "Final:" in result["output"]
        assert "HELLO WORLD" in result["output"]

        # Invalid input (too short) - should stop early
        result = workflow.start("Hi")
        assert result["output"] == "invalid"
    
    def test_autonomous_workflow_doc_example(self):
        """Test the autonomous workflow example from docs/features/autonomous-workflow.mdx"""
        class EnvironmentMonitor:
            def __init__(self):
                self.iteration = 0
            
            def check_state(self, ctx: WorkflowContext) -> StepResult:
                self.iteration += 1
                states = ["normal", "critical", "optimal"]
                state = states[self.iteration % 3]
                return StepResult(
                    output=f"state: {state}",
                    variables={"state": state, "iteration": self.iteration}
                )

        def handle_normal(ctx): return StepResult(output="Maintaining")
        def handle_critical(ctx): return StepResult(output="Fixing")
        def handle_optimal(ctx): return StepResult(output="Enhancing", stop_workflow=True)

        monitor = EnvironmentMonitor()

        workflow = Workflow(
            steps=[
                repeat(
                    monitor.check_state,
                    until=lambda ctx: ctx.variables.get("state") == "optimal",
                    max_iterations=5
                ),
                route({
                    "normal": [handle_normal],
                    "critical": [handle_critical],
                    "optimal": [handle_optimal]
                })
            ]
        )

        result = workflow.start("Monitor environment")
        # Should have run until optimal state
        assert result["variables"].get("iteration", 0) >= 1
    
    def test_workflow_with_all_callbacks(self):
        """Test workflow with all callback types."""
        events = []
        
        def on_start(w, i): events.append(f"start:{i}")
        def on_complete(w, r): events.append(f"complete:{r['status']}")
        def on_step_start(n, c): events.append(f"step_start:{n}")
        def on_step_complete(n, r): events.append(f"step_complete:{n}")
        
        def step1(ctx): return StepResult(output="Step 1 done")
        def step2(ctx): return StepResult(output="Step 2 done")
        
        workflow = Workflow(
            steps=[step1, step2],
            hooks=WorkflowHooksConfig(
                on_workflow_start=on_start,
                on_workflow_complete=on_complete,
                on_step_start=on_step_start,
                on_step_complete=on_step_complete
            )
        )
        
        result = workflow.start("test input")
        
        assert "start:test input" in events
        assert "complete:completed" in events
        assert "step_start:step1" in events
        assert "step_complete:step1" in events
        assert "step_start:step2" in events
        assert "step_complete:step2" in events
    
    def test_workflow_with_guardrail_retry(self):
        """Test workflow with guardrail that triggers retry."""
        attempts = [0]
        
        def generator(ctx: WorkflowContext) -> StepResult:
            attempts[0] += 1
            feedback = ctx.variables.get("validation_feedback", "")
            if "fix" in feedback.lower():
                return StepResult(output="fixed output")
            return StepResult(output="bad output")
        
        def validator(result):
            if "fixed" in result.output:
                return (True, None)
            return (False, "Please fix the output")
        
        workflow = Workflow(steps=[
            Task(name="gen", handler=generator, guardrails=validator, execution=TaskExecutionConfig(max_retries=3))
        ])
        
        result = workflow.start("test")
        assert "fixed" in result["output"]
        assert attempts[0] == 2  # First attempt + 1 retry


# =============================================================================
# Test: Agent Integration in Workflows
# =============================================================================

class TestAgentWorkflows:
    """Test Agent objects as workflow steps."""
    
    def test_agent_normalization(self):
        """Test that Agent objects are properly normalized to Task."""
        # Create a mock agent
        class MockAgent:
            def __init__(self, name, tools=None):
                self.name = name
                self.tools = tools or []
            
            def chat(self, message, **kwargs):
                return f"Response from {self.name}: {message}"
        
        agent = MockAgent("TestAgent", tools=["tool1", "tool2"])
        
        workflow = Workflow(steps=[agent])
        
        # Normalize and check
        normalized = workflow._normalize_single_step(agent, 0)
        assert normalized.name == "TestAgent"
        assert normalized.agent == agent
        assert normalized.tools == ["tool1", "tool2"]
    
    def test_workflow_with_mock_agent(self):
        """Test workflow execution with mock agent."""
        class MockAgent:
            def __init__(self, name):
                self.name = name
                self._context_manager_initialized = True
                self._context_param = None
                self._context_manager = None
            
            def chat(self, message, **kwargs):
                return f"Processed: {message}"
        
        agent = MockAgent("Processor")
        
        workflow = Workflow(steps=[agent])
        result = workflow.start("Hello World")
        
        assert "Processed:" in result["output"]
        assert "Hello World" in result["output"]
    
    def test_sequential_mock_agents(self):
        """Test sequential execution of multiple mock agents."""
        class MockAgent:
            def __init__(self, name, prefix):
                self.name = name
                self.prefix = prefix
                self._context_manager_initialized = True
                self._context_param = None
                self._context_manager = None
            
            def chat(self, message, **kwargs):
                return f"{self.prefix}: {message}"
        
        agent1 = MockAgent("Agent1", "First")
        agent2 = MockAgent("Agent2", "Second")
        agent3 = MockAgent("Agent3", "Third")
        
        workflow = Workflow(steps=[agent1, agent2, agent3])
        result = workflow.start("Input")
        
        # Final output should be from agent3
        assert "Third:" in result["output"]
        assert len(result["steps"]) == 3
    
    def test_parallel_mock_agents(self):
        """Test parallel execution of mock agents."""
        class MockAgent:
            def __init__(self, name, output):
                self.name = name
                self.output = output
            
            def chat(self, message, **kwargs):
                return self.output
        
        agent1 = MockAgent("Agent1", "Result A")
        agent2 = MockAgent("Agent2", "Result B")
        agent3 = MockAgent("Agent3", "Result C")
        
        def aggregator(ctx: WorkflowContext) -> StepResult:
            outputs = ctx.variables.get("parallel_outputs", [])
            return StepResult(output=f"Combined: {len(outputs)} results")
        
        workflow = Workflow(steps=[
            parallel([agent1, agent2, agent3]),
            aggregator
        ])
        
        result = workflow.start("Test")
        assert "Combined: 3 results" in result["output"]
    
    def test_route_to_mock_agents(self):
        """Test routing to different mock agents."""
        class MockAgent:
            def __init__(self, name, output):
                self.name = name
                self.output = output
                self._context_manager_initialized = True
                self._context_param = None
                self._context_manager = None
            
            def chat(self, message, **kwargs):
                return self.output
        
        tech_agent = MockAgent("TechAgent", "Technical response")
        creative_agent = MockAgent("CreativeAgent", "Creative response")
        
        def classifier(ctx: WorkflowContext) -> StepResult:
            if "tech" in ctx.input.lower():
                return StepResult(output="category: technical")
            return StepResult(output="category: creative")
        
        workflow = Workflow(steps=[
            classifier,
            route({
                "technical": [tech_agent],
                "creative": [creative_agent]
            })
        ])
        
        # Test technical route
        result = workflow.start("tech question")
        assert "Technical response" in result["output"]
        
        # Test creative route
        result = workflow.start("creative request")
        assert "Creative response" in result["output"]
    
    def test_loop_with_mock_agent(self):
        """Test loop pattern with mock agent."""
        class MockAgent:
            def __init__(self, name):
                self.name = name
            
            def chat(self, message, **kwargs):
                return f"Processed: {message}"
        
        processor = MockAgent("Processor")
        
        workflow = Workflow(
            steps=[loop(processor, over="items")],
            variables={"items": ["A", "B", "C"]}
        )
        
        result = workflow.start("Process items")
        outputs = result["variables"].get("loop_outputs", [])
        assert len(outputs) == 3


# =============================================================================
# Test: Workflow Configuration
# =============================================================================

class TestWorkflowConfiguration:
    """Test workflow configuration options."""
    
    def test_workflow_verbose_setting(self):
        """Test that workflow verbose setting is used."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1], output="verbose")
        assert workflow.verbose == True
    
    def test_workflow_reasoning_setting(self):
        """Test that workflow reasoning setting is stored."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1], planning=WorkflowPlanningConfig(reasoning=True))
        assert workflow.reasoning == True
    
    def test_workflow_planning_setting(self):
        """Test that workflow planning setting is stored."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1], planning=WorkflowPlanningConfig(enabled=True, llm="gpt-4o-mini"))
        assert workflow._planning_enabled == True
        assert workflow.planning_llm == "gpt-4o-mini"
    
    def test_workflow_default_llm(self):
        """Test default LLM setting."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1], default_llm="gpt-4o-mini")
        assert workflow.default_llm == "gpt-4o-mini"
    
    def test_workflow_default_agent_config(self):
        """Test default agent config."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(
            steps=[step1],
            default_agent_config={
                "name": "DefaultAgent",
                "role": "Assistant",
                "tools": ["tool1"]
            }
        )
        assert workflow.default_agent_config["name"] == "DefaultAgent"
        assert workflow.default_agent_config["tools"] == ["tool1"]


# =============================================================================
# Test: Task with Tools
# =============================================================================

class TestTaskTools:
    """Test Task with tools configuration."""
    
    def test_step_with_tools(self):
        """Test Task with tools parameter."""
        def my_tool(): return "tool result"
        
        step = Task(
            name="step_with_tools",
            action="Do something",
            tools=[my_tool]
        )
        
        assert step.tools == [my_tool]
    
    def test_step_with_agent_config_tools(self):
        """Test Task with tools in agent_config."""
        def my_tool(): return "tool result"
        
        step = Task(
            name="step_with_config",
            action="Do something",
            agent_config={
                "name": "Agent",
                "role": "Helper",
                "tools": [my_tool]
            }
        )
        
        assert step.agent_config["tools"] == [my_tool]


# =============================================================================
# Test: Migrated Features (output_file, images, async, etc.)
# =============================================================================

class TestMigratedFeatures:
    """Test features migrated from process='workflow'."""
    
    def test_step_output_file(self):
        """Test Task with output_file parameter."""
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.txt")
            
            def generate_content(ctx: WorkflowContext) -> StepResult:
                return StepResult(output="Generated content for file")
            
            workflow = Workflow(steps=[
                Task(
                    name="generator",
                    handler=generate_content,
                    output=TaskOutputConfig(file=output_path)
                )
            ])
            
            result = workflow.start("Generate content")
            
            # Check file was created
            assert os.path.exists(output_path)
            with open(output_path) as f:
                content = f.read()
            assert "Generated content" in content
    
    def test_step_images_parameter(self):
        """Test Task with images parameter."""
        step = Task(
            name="vision_step",
            action="Analyze this image",
            images=["image1.jpg", "image2.png"]
        )
        
        assert step.images == ["image1.jpg", "image2.png"]
    
    def test_step_output_pydantic_parameter(self):
        """Test Task with output_pydantic parameter."""
        from pydantic import BaseModel
        
        class OutputModel(BaseModel):
            title: str
            content: str
        
        step = Task(
            name="structured_step",
            action="Generate structured output",
            output=TaskOutputConfig(pydantic_model=OutputModel)
        )
        
        assert step.output_pydantic == OutputModel
    
    def test_step_async_execution_parameter(self):
        """Test Task with async_execution parameter."""
        step = Task(
            name="async_step",
            action="Run async",
            execution=TaskExecutionConfig(async_exec=True)
        )
        
        assert step.async_execution == True
    
    def test_step_quality_check_parameter(self):
        """Test Task with quality_check parameter."""
        step = Task(
            name="quality_step",
            action="Check quality",
            execution=TaskExecutionConfig(quality_check=False)
        )
        
        assert step.quality_check == False
    
    def test_step_rerun_parameter(self):
        """Test Task with rerun parameter."""
        step = Task(
            name="rerun_step",
            action="Can rerun",
            execution=TaskExecutionConfig(rerun=False)
        )
        
        assert step.rerun == False
    
    def test_workflow_astart_method_exists(self):
        """Test that Workflow has astart method."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1])
        
        assert hasattr(workflow, 'astart')
        assert callable(workflow.astart)
    
    def test_workflow_arun_method_exists(self):
        """Test that Workflow has arun method."""
        def step1(ctx): return StepResult(output="Done")
        
        workflow = Workflow(steps=[step1])
        
        assert hasattr(workflow, 'arun')
        assert callable(workflow.arun)
    
    def test_step_to_dict_includes_new_fields(self):
        """Test that to_dict includes all new fields."""
        step = Task(
            name="test_step",
            action="Test action",
            output=TaskOutputConfig(file="output.txt"),
            images=["img.jpg"],
            execution=TaskExecutionConfig(async_exec=True, quality_check=False, rerun=False)
        )
        
        d = step.to_dict()
        
        assert d["output"]["file"] == "output.txt"
        assert d["images"] == ["img.jpg"]
        assert d["execution"]["async"] == True


# =============================================================================
# Test: Planning and Reasoning Modes
# =============================================================================

class TestPlanningAndReasoning:
    """Test planning and reasoning modes in workflows."""
    
    def test_workflow_planning_parameter_exists(self):
        """Test that Workflow accepts planning parameter."""
        workflow = Workflow(
            steps=[lambda ctx: StepResult(output="test")],
            planning=WorkflowPlanningConfig(enabled=True, llm="gpt-4o-mini")
        )
        assert workflow._planning_enabled == True
        assert workflow.planning_llm == "gpt-4o-mini"
    
    def test_workflow_reasoning_parameter_exists(self):
        """Test that Workflow accepts reasoning parameter."""
        workflow = Workflow(
            steps=[lambda ctx: StepResult(output="test")],
            planning=WorkflowPlanningConfig(reasoning=True)
        )
        assert workflow.reasoning == True
    
    def test_workflow_memory_config_parameter_exists(self):
        """Test that Workflow accepts memory parameter."""
        from praisonaiagents.workflows import WorkflowMemoryConfig
        workflow = Workflow(
            steps=[lambda ctx: StepResult(output="test")],
            memory=WorkflowMemoryConfig(backend="rag")
        )
        assert workflow._memory_config is not None
    
    def test_workflow_verbose_parameter_exists(self):
        """Test that Workflow accepts output parameter for verbose."""
        workflow = Workflow(
            steps=[lambda ctx: StepResult(output="test")],
            output="verbose"
        )
        assert workflow.verbose == True


class TestToolsPerStep:
    """Test tools per step functionality."""
    
    def test_step_with_tools_list(self):
        """Test Task with tools list."""
        def my_tool():
            return "tool result"
        
        step = Task(
            name="test",
            action="Do something",
            tools=[my_tool]
        )
        
        assert step.tools == [my_tool]
    
    def test_step_with_agent_config_tools(self):
        """Test Task with tools in agent_config."""
        def my_tool():
            return "tool result"
        
        step = Task(
            name="test",
            action="Do something",
            agent_config={
                "name": "TestAgent",
                "role": "Tester",
                "tools": [my_tool]
            }
        )
        
        assert step.agent_config["tools"] == [my_tool]
    
    def test_agent_with_tools_in_workflow(self):
        """Test Agent with tools is properly handled in workflow."""
        class MockAgent:
            def __init__(self, name, tools=None):
                self.name = name
                self.tools = tools or []
                self._context_manager_initialized = True
                self._context_param = None
                self._context_manager = None
            
            def chat(self, message, **kwargs):
                return f"Response with {len(self.tools)} tools"
        
        def mock_tool():
            return "tool result"
        
        agent = MockAgent("TestAgent", tools=[mock_tool])
        workflow = Workflow(steps=[agent])
        
        # Normalize and verify tools are preserved
        normalized = workflow._normalize_single_step(agent, 0)
        assert normalized.tools == [mock_tool]
        
        # Execute and verify
        result = workflow.start("test")
        assert "1 tools" in result["output"]


# =============================================================================
# Test: WorkflowManager with Patterns in MD Files
# =============================================================================

class TestWorkflowManagerPatterns:
    """Test WorkflowManager parsing of pattern syntax in markdown files."""
    
    def test_parse_route_pattern_in_md(self):
        """Test parsing route pattern from markdown."""
        import tempfile
        import os
        from praisonaiagents.workflows import WorkflowManager
        
        md_content = """---
name: Route Test
description: Test routing pattern
---

## Step 1: Classifier
Classify the input.

```action
Classify this input as technical or creative
```

```route
technical: [Tech Handler]
creative: [Creative Handler]
default: [General Handler]
```

## Step 2: Tech Handler
Handle technical requests.

```action
Process technical request
```

## Step 3: Creative Handler
Handle creative requests.

```action
Process creative request
```

## Step 4: General Handler
Handle general requests.

```action
Process general request
```
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = os.path.join(tmpdir, ".praison", "workflows")
            os.makedirs(workflows_dir)
            
            with open(os.path.join(workflows_dir, "route_test.md"), "w") as f:
                f.write(md_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            workflows = manager.list_workflows()
            
            assert len(workflows) == 1
            workflow = workflows[0]
            assert workflow.name == "Route Test"
            
            # Check that route pattern is parsed
            step1 = workflow.steps[0]
            assert step1.name == "Classifier"
            assert step1.branch_condition is not None
            assert "technical" in step1.branch_condition
    
    def test_parse_parallel_pattern_in_md(self):
        """Test parsing parallel pattern from markdown."""
        import tempfile
        import os
        from praisonaiagents.workflows import WorkflowManager
        
        md_content = """---
name: Parallel Test
description: Test parallel pattern
---

## Step 1: Research
Research in parallel.

```parallel
- Market Research
- Competitor Analysis
- Customer Survey
```

```action
Research the topic
```

## Step 2: Market Research
Research the market.

```action
Analyze market trends
```

## Step 3: Competitor Analysis
Analyze competitors.

```action
Analyze competitors
```

## Step 4: Customer Survey
Survey customers.

```action
Survey customers
```
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = os.path.join(tmpdir, ".praison", "workflows")
            os.makedirs(workflows_dir)
            
            with open(os.path.join(workflows_dir, "parallel_test.md"), "w") as f:
                f.write(md_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            workflows = manager.list_workflows()
            
            assert len(workflows) == 1
            workflow = workflows[0]
            assert workflow.name == "Parallel Test"
            
            # Check that parallel steps are parsed
            step1 = workflow.steps[0]
            assert step1.name == "Research"
            assert hasattr(step1, 'parallel_steps') or step1.next_steps is not None
    
    def test_parse_loop_pattern_in_md(self):
        """Test parsing loop pattern from markdown."""
        import tempfile
        import os
        from praisonaiagents.workflows import WorkflowManager
        
        md_content = """---
name: Loop Test
description: Test loop pattern
variables:
  items: ["item1", "item2", "item3"]
---

## Step 1: Process Items
Process each item in the list.

loop_over: items
loop_var: current_item

```action
Process {{current_item}}
```
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = os.path.join(tmpdir, ".praison", "workflows")
            os.makedirs(workflows_dir)
            
            with open(os.path.join(workflows_dir, "loop_test.md"), "w") as f:
                f.write(md_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            workflows = manager.list_workflows()
            
            assert len(workflows) == 1
            workflow = workflows[0]
            
            step1 = workflow.steps[0]
            assert step1.name == "Process Items"
            assert step1.loop_over == "items"
            assert step1.loop_var == "current_item"
    
    def test_parse_repeat_pattern_in_md(self):
        """Test parsing repeat pattern from markdown."""
        import tempfile
        import os
        from praisonaiagents.workflows import WorkflowManager
        
        md_content = """---
name: Repeat Test
description: Test repeat pattern
---

## Step 1: Generate
Generate content repeatedly.

```repeat
max_iterations: 5
until: count >= 10
```

```action
Generate more content
```
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = os.path.join(tmpdir, ".praison", "workflows")
            os.makedirs(workflows_dir)
            
            with open(os.path.join(workflows_dir, "repeat_test.md"), "w") as f:
                f.write(md_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            workflows = manager.list_workflows()
            
            assert len(workflows) == 1
            workflow = workflows[0]
            
            step1 = workflow.steps[0]
            assert step1.name == "Generate"
            # Check repeat config is parsed
            assert hasattr(step1, 'max_retries') or hasattr(step1, 'repeat_config')
    
    def test_parse_output_file_in_md(self):
        """Test parsing output_file from markdown."""
        import tempfile
        import os
        from praisonaiagents.workflows import WorkflowManager
        
        md_content = """---
name: Output Test
description: Test output file
---

## Step 1: Generate Report
Generate a report and save to file.

output_file: output/report.txt

```action
Generate the report
```
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = os.path.join(tmpdir, ".praison", "workflows")
            os.makedirs(workflows_dir)
            
            with open(os.path.join(workflows_dir, "output_test.md"), "w") as f:
                f.write(md_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            workflows = manager.list_workflows()
            
            assert len(workflows) == 1
            workflow = workflows[0]
            
            step1 = workflow.steps[0]
            assert step1.name == "Generate Report"
            assert step1.output_file == "output/report.txt"
    
    def test_parse_images_in_md(self):
        """Test parsing images from markdown."""
        import tempfile
        import os
        from praisonaiagents.workflows import WorkflowManager
        
        md_content = """---
name: Vision Test
description: Test image handling
---

## Step 1: Analyze Image
Analyze the provided image.

```images
image1.jpg
image2.png
```

```action
Analyze these images
```
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = os.path.join(tmpdir, ".praison", "workflows")
            os.makedirs(workflows_dir)
            
            with open(os.path.join(workflows_dir, "vision_test.md"), "w") as f:
                f.write(md_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            workflows = manager.list_workflows()
            
            assert len(workflows) == 1
            workflow = workflows[0]
            
            step1 = workflow.steps[0]
            assert step1.name == "Analyze Image"
            assert step1.images is not None
            assert "image1.jpg" in step1.images


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
