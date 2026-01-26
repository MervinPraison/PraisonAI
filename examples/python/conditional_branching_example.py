"""
Conditional Branching Example - PraisonAI Agents

This example demonstrates the `if:` pattern for conditional workflow execution:
1. Basic if/then/else branching
2. Numeric condition evaluation (>, <, >=, <=, ==, !=)
3. String condition evaluation (==, !=)
4. Contains condition (in, contains)
5. Combining if: with loop: for per-item decisions

The if: pattern enables dynamic workflow paths based on
runtime conditions and variable values.
"""

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.workflows import if_, loop


# =============================================================================
# Example 1: Basic If/Then/Else - Score-Based Routing
# =============================================================================

def basic_if_example():
    """
    Route to different handlers based on a score threshold.
    """
    print("\n" + "="*60)
    print("Example 1: Basic If/Then/Else - Score Routing")
    print("="*60)
    
    def approve(ctx: WorkflowContext) -> StepResult:
        score = ctx.variables.get("score", 0)
        print(f"  ✅ APPROVED: Score {score} meets threshold")
        return StepResult(output="Application approved")
    
    def reject(ctx: WorkflowContext) -> StepResult:
        score = ctx.variables.get("score", 0)
        print(f"  ❌ REJECTED: Score {score} below threshold")
        return StepResult(output="Application rejected")
    
    # Test with passing score
    workflow_pass = Workflow(
        steps=[
            if_(
                condition="{{score}} >= 70",
                then_steps=[approve],
                else_steps=[reject]
            )
        ],
        variables={"score": 85}
    )
    
    print("\nTest 1: Score = 85")
    workflow_pass.start("Evaluate application")
    
    # Test with failing score
    workflow_fail = Workflow(
        steps=[
            if_(
                condition="{{score}} >= 70",
                then_steps=[approve],
                else_steps=[reject]
            )
        ],
        variables={"score": 55}
    )
    
    print("\nTest 2: Score = 55")
    workflow_fail.start("Evaluate application")


# =============================================================================
# Example 2: String Condition - Status-Based Processing
# =============================================================================

def string_condition_example():
    """
    Branch based on string equality.
    """
    print("\n" + "="*60)
    print("Example 2: String Condition - Status Processing")
    print("="*60)
    
    def process_active(ctx: WorkflowContext) -> StepResult:
        print("  🟢 Processing ACTIVE user")
        return StepResult(output="Active user processed")
    
    def process_inactive(ctx: WorkflowContext) -> StepResult:
        print("  🔴 Processing INACTIVE user")
        return StepResult(output="Inactive user archived")
    
    # Test with active status
    workflow = Workflow(
        steps=[
            if_(
                condition="{{status}} == active",
                then_steps=[process_active],
                else_steps=[process_inactive]
            )
        ],
        variables={"status": "active"}
    )
    
    print("\nTest: status = 'active'")
    workflow.start("Process user")
    
    # Test with inactive status
    workflow2 = Workflow(
        steps=[
            if_(
                condition="{{status}} == active",
                then_steps=[process_active],
                else_steps=[process_inactive]
            )
        ],
        variables={"status": "inactive"}
    )
    
    print("\nTest: status = 'inactive'")
    workflow2.start("Process user")


# =============================================================================
# Example 3: Contains Condition - Content Filtering
# =============================================================================

def contains_condition_example():
    """
    Branch based on whether a string contains a substring.
    """
    print("\n" + "="*60)
    print("Example 3: Contains Condition - Content Filtering")
    print("="*60)
    
    def flag_content(ctx: WorkflowContext) -> StepResult:
        print("  🚨 FLAGGED: Message contains sensitive content")
        return StepResult(output="Content flagged for review")
    
    def approve_content(ctx: WorkflowContext) -> StepResult:
        print("  ✅ APPROVED: Message is clean")
        return StepResult(output="Content approved")
    
    # Test with flagged content
    workflow1 = Workflow(
        steps=[
            if_(
                condition="error in {{message}}",
                then_steps=[flag_content],
                else_steps=[approve_content]
            )
        ],
        variables={"message": "System error: connection failed"}
    )
    
    print("\nTest 1: Message contains 'error'")
    workflow1.start("Filter content")
    
    # Test with clean content
    workflow2 = Workflow(
        steps=[
            if_(
                condition="error in {{message}}",
                then_steps=[flag_content],
                else_steps=[approve_content]
            )
        ],
        variables={"message": "Operation completed successfully"}
    )
    
    print("\nTest 2: Message is clean")
    workflow2.start("Filter content")


# =============================================================================
# Example 4: If Inside Loop - Per-Item Decisions
# =============================================================================

def if_inside_loop_example():
    """
    Make decisions for each item in a collection.
    Combines iteration with conditional branching.
    """
    print("\n" + "="*60)
    print("Example 4: If Inside Loop - Per-Item Decisions")
    print("="*60)
    
    results = {"premium": [], "standard": []}
    
    def premium_service(ctx: WorkflowContext) -> StepResult:
        customer = ctx.variables.get("customer", {})
        name = customer.get("name", "Unknown")
        results["premium"].append(name)
        print(f"  ⭐ {name}: Premium service activated")
        return StepResult(output=f"Premium service for {name}")
    
    def standard_service(ctx: WorkflowContext) -> StepResult:
        customer = ctx.variables.get("customer", {})
        name = customer.get("name", "Unknown")
        results["standard"].append(name)
        print(f"  📦 {name}: Standard service activated")
        return StepResult(output=f"Standard service for {name}")
    
    workflow = Workflow(
        steps=[
            loop(
                steps=[
                    if_(
                        condition="{{customer.tier}} == premium",
                        then_steps=[premium_service],
                        else_steps=[standard_service]
                    )
                ],
                over="customers",
                var_name="customer"
            )
        ],
        variables={
            "customers": [
                {"name": "Alice", "tier": "premium"},
                {"name": "Bob", "tier": "standard"},
                {"name": "Charlie", "tier": "premium"},
                {"name": "Diana", "tier": "standard"}
            ]
        }
    )
    
    print("\nProcessing customers:")
    workflow.start("Assign service tiers")
    
    print(f"\nSummary:")
    print(f"  Premium customers: {results['premium']}")
    print(f"  Standard customers: {results['standard']}")


# =============================================================================
# Example 5: Nested Conditions - Multi-Level Decision Tree
# =============================================================================

def nested_conditions_example():
    """
    Demonstrate nested if conditions for complex decision trees.
    """
    print("\n" + "="*60)
    print("Example 5: Nested Conditions - Decision Tree")
    print("="*60)
    
    def vip_treatment(ctx: WorkflowContext) -> StepResult:
        print("  👑 VIP Treatment: Dedicated support + Priority queue")
        return StepResult(output="VIP treatment applied")  # noqa: ARG001
    
    def regular_premium(ctx: WorkflowContext) -> StepResult:
        print("  ⭐ Premium: Priority support")
        return StepResult(output="Premium support applied")
    
    def basic_support(ctx: WorkflowContext) -> StepResult:
        print("  📞 Basic: Standard support queue")
        return StepResult(output="Basic support applied")
    
    # Outer condition: Is premium?
    # Inner condition (if premium): Is VIP?
    workflow = Workflow(
        steps=[
            if_(
                condition="{{tier}} == premium",
                then_steps=[
                    if_(
                        condition="{{spend}} > 10000",
                        then_steps=[vip_treatment],
                        else_steps=[regular_premium]
                    )
                ],
                else_steps=[basic_support]
            )
        ],
        variables={"tier": "premium", "spend": 15000}
    )
    
    print("\nTest 1: Premium tier, high spend")
    workflow.start("Determine support level")
    
    workflow2 = Workflow(
        steps=[
            if_(
                condition="{{tier}} == premium",
                then_steps=[
                    if_(
                        condition="{{spend}} > 10000",
                        then_steps=[vip_treatment],
                        else_steps=[regular_premium]
                    )
                ],
                else_steps=[basic_support]
            )
        ],
        variables={"tier": "premium", "spend": 5000}
    )
    
    print("\nTest 2: Premium tier, low spend")
    workflow2.start("Determine support level")
    
    workflow3 = Workflow(
        steps=[
            if_(
                condition="{{tier}} == premium",
                then_steps=[
                    if_(
                        condition="{{spend}} > 10000",
                        then_steps=[vip_treatment],
                        else_steps=[regular_premium]
                    )
                ],
                else_steps=[basic_support]
            )
        ],
        variables={"tier": "basic", "spend": 20000}
    )
    
    print("\nTest 3: Basic tier (regardless of spend)")
    workflow3.start("Determine support level")


# =============================================================================
# Example 6: No Else Branch - Optional Processing
# =============================================================================

def no_else_example():
    """
    If condition without else branch - only execute if true.
    """
    print("\n" + "="*60)
    print("Example 6: No Else Branch - Optional Processing")
    print("="*60)
    
    def send_notification(ctx: WorkflowContext) -> StepResult:
        print("  📧 Notification sent!")
        return StepResult(output="Notification sent")
    
    def continue_processing(ctx: WorkflowContext) -> StepResult:
        print("  ➡️ Continuing with main workflow...")
        return StepResult(output="Continued")
    
    # Only send notification if opted in
    workflow = Workflow(
        steps=[
            if_(
                condition="{{notify}} == true",
                then_steps=[send_notification]
                # No else_steps - just skip if false
            ),
            continue_processing
        ],
        variables={"notify": "true"}
    )
    
    print("\nTest 1: notify = true")
    workflow.start("Process with notification")
    
    workflow2 = Workflow(
        steps=[
            if_(
                condition="{{notify}} == true",
                then_steps=[send_notification]
            ),
            continue_processing
        ],
        variables={"notify": "false"}
    )
    
    print("\nTest 2: notify = false")
    workflow2.start("Process without notification")


# =============================================================================
# Main - Run All Examples
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("PraisonAI Conditional Branching Examples")
    print("="*60)
    
    basic_if_example()
    string_condition_example()
    contains_condition_example()
    if_inside_loop_example()
    nested_conditions_example()
    no_else_example()
    
    print("\n" + "="*60)
    print("All conditional branching examples completed!")
    print("="*60)
