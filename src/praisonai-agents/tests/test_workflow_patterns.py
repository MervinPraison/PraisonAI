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
            on_workflow_start=on_start
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
            on_workflow_complete=on_complete
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
            on_step_start=on_step_start
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
            on_step_complete=on_step_complete
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
            on_step_error=on_error
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
            WorkflowStep(name="step1", handler=step1, guardrail=validator)
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
            WorkflowStep(name="step1", handler=step1, guardrail=validator, max_retries=5)
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
            WorkflowStep(name="step1", handler=step1, guardrail=validator, max_retries=2)
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
            WorkflowStep(name="step1", handler=step1, guardrail=validator, max_retries=3)
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
            WorkflowStep(name="step2", handler=step2, should_run=never_run)
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
            on_workflow_start=on_start,
            on_workflow_complete=on_complete,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete
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
            WorkflowStep(name="gen", handler=generator, guardrail=validator, max_retries=3)
        ])
        
        result = workflow.start("test")
        assert "fixed" in result["output"]
        assert attempts[0] == 2  # First attempt + 1 retry


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
