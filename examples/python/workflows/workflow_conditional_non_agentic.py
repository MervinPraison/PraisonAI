"""
Workflow Conditional Execution Example

Demonstrates using should_run to conditionally execute steps
based on input or previous results.
"""

from praisonaiagents import Workflow, WorkflowStep, WorkflowContext, StepResult

# Condition functions - return True to run the step, False to skip
def is_sensitive_content(ctx: WorkflowContext) -> bool:
    """Only run compliance check for sensitive topics."""
    sensitive_keywords = ["legal", "medical", "financial", "security"]
    return any(keyword in ctx.input.lower() for keyword in sensitive_keywords)

def needs_translation(ctx: WorkflowContext) -> bool:
    """Only translate if content is not in English."""
    return ctx.variables.get("language", "en") != "en"

# Handler functions
def process_content(ctx: WorkflowContext) -> StepResult:
    return StepResult(output=f"Processed: {ctx.input}")

def compliance_check(ctx: WorkflowContext) -> StepResult:
    return StepResult(output=f"✅ Compliance verified for: {ctx.previous_result}")

def translate(ctx: WorkflowContext) -> StepResult:
    lang = ctx.variables.get("language", "unknown")
    return StepResult(output=f"🌐 Translated to {lang}: {ctx.previous_result}")

def finalize(ctx: WorkflowContext) -> StepResult:
    return StepResult(output=f"📄 Final: {ctx.previous_result}")

# Create workflow with conditional steps
workflow = Workflow(
    name="Conditional Pipeline",
    steps=[
        WorkflowStep(name="process", handler=process_content),
        WorkflowStep(
            name="compliance",
            handler=compliance_check,
            should_run=is_sensitive_content  # Only runs for sensitive content
        ),
        WorkflowStep(
            name="translate",
            handler=translate,
            should_run=needs_translation  # Only runs if language != "en"
        ),
        WorkflowStep(name="finalize", handler=finalize)
    ]
)

if __name__ == "__main__":
    # Test 1: Normal content (skips compliance)
    print("=== Test 1: Normal content ===")
    result = workflow.start("Hello world", verbose=True)
    print(f"Output: {result['output']}\n")
    
    # Test 2: Sensitive content (runs compliance)
    print("=== Test 2: Legal content ===")
    result = workflow.start("Review this legal document", verbose=True)
    print(f"Output: {result['output']}\n")
    
    # Test 3: Non-English content (runs translation)
    print("=== Test 3: Non-English content ===")
    workflow.variables = {"language": "es"}
    result = workflow.start("Hola mundo", verbose=True)
    print(f"Output: {result['output']}")
