"""
Nested Workflows Example - PraisonAI Agents

This example demonstrates how to use nested workflow patterns:
1. Loop inside Loop (nested iteration)
2. Parallel inside Loop (concurrent processing per item)
3. Route inside Loop (conditional routing per item)
4. Depth limit protection (prevents infinite recursion)

These patterns enable complex data processing pipelines
while maintaining clean, readable workflow definitions.
"""

from praisonaiagents import AgentFlow, WorkflowContext, StepResult
from praisonaiagents.workflows import loop, parallel, route


# =============================================================================
# Example 1: Nested Loops - Process Matrix Data
# =============================================================================

def nested_loop_example():
    """
    Process a 2D matrix using nested loops.
    Outer loop iterates rows, inner loop iterates columns.
    """
    print("\n" + "="*60)
    print("Example 1: Nested Loops - Matrix Processing")
    print("="*60)
    
    results = []
    
    def process_cell(ctx: WorkflowContext) -> StepResult:
        row = ctx.variables.get("row", {})
        col = ctx.variables.get("col", "")
        row_name = row.get("name", "?")
        results.append(f"{row_name}-{col}")
        return StepResult(output=f"Processed cell {row_name}-{col}")
    
    # Inner loop processes columns for each row
    inner_loop = loop(
        process_cell,
        over="columns",
        var_name="col"
    )
    
    # Outer loop iterates through rows
    outer_loop = loop(
        steps=[inner_loop],
        over="rows",
        var_name="row"
    )
    
    workflow = AgentFlow(
        steps=[outer_loop],
        variables={
            "rows": [
                {"name": "Row1"},
                {"name": "Row2"}
            ],
            "columns": ["A", "B", "C"]
        }
    )
    
    workflow.start("Process matrix")
    print(f"Processed cells: {results}")
    # Output: ['Row1-A', 'Row1-B', 'Row1-C', 'Row2-A', 'Row2-B', 'Row2-C']


# =============================================================================
# Example 2: Parallel Inside Loop - Concurrent Task Processing
# =============================================================================

def parallel_inside_loop_example():
    """
    For each project, run multiple analysis tasks in parallel.
    Combines iteration with concurrent execution.
    """
    print("\n" + "="*60)
    print("Example 2: Parallel Inside Loop - Concurrent Analysis")
    print("="*60)
    
    results = []
    
    def security_scan(ctx: WorkflowContext) -> StepResult:
        project = ctx.variables.get("project", "unknown")
        results.append(f"security:{project}")
        return StepResult(output=f"Security scan complete for {project}")
    
    def performance_test(ctx: WorkflowContext) -> StepResult:
        project = ctx.variables.get("project", "unknown")
        results.append(f"performance:{project}")
        return StepResult(output=f"Performance test complete for {project}")
    
    def code_review(ctx: WorkflowContext) -> StepResult:
        project = ctx.variables.get("project", "unknown")
        results.append(f"review:{project}")
        return StepResult(output=f"Code review complete for {project}")
    
    # Parallel tasks run concurrently for each project
    parallel_analysis = parallel([security_scan, performance_test, code_review])
    
    # Loop through projects, running parallel analysis for each
    workflow = AgentFlow(
        steps=[
            loop(
                steps=[parallel_analysis],
                over="projects",
                var_name="project"
            )
        ],
        variables={
            "projects": ["frontend", "backend", "api"]
        }
    )
    
    workflow.start("Analyze all projects")
    print(f"Analysis results: {sorted(results)}")


# =============================================================================
# Example 3: Route Inside Loop - Conditional Processing Per Item
# =============================================================================

def route_inside_loop_example():
    """
    Process items differently based on their type.
    Each item in the loop is routed to the appropriate handler.
    """
    print("\n" + "="*60)
    print("Example 3: Route Inside Loop - Type-Based Processing")
    print("="*60)
    
    results = []
    
    def process_image(ctx: WorkflowContext) -> StepResult:
        item = ctx.variables.get("item", {})
        results.append(f"image:{item.get('name')}")
        return StepResult(output=f"Processed image: {item.get('name')}")
    
    def process_video(ctx: WorkflowContext) -> StepResult:
        item = ctx.variables.get("item", {})
        results.append(f"video:{item.get('name')}")
        return StepResult(output=f"Processed video: {item.get('name')}")
    
    def process_document(ctx: WorkflowContext) -> StepResult:
        item = ctx.variables.get("item", {})
        results.append(f"document:{item.get('name')}")
        return StepResult(output=f"Processed document: {item.get('name')}")
    
    # Route based on item type
    type_router = route({
        "image": [process_image],
        "video": [process_video],
        "document": [process_document]
    })
    
    # First, determine the type, then route
    def get_type(ctx: WorkflowContext) -> StepResult:
        item = ctx.variables.get("item", {})
        item_type = item.get("type", "unknown")
        return StepResult(output=item_type)
    
    workflow = AgentFlow(
        steps=[
            loop(
                steps=[get_type, type_router],
                over="files",
                var_name="item"
            )
        ],
        variables={
            "files": [
                {"name": "photo.jpg", "type": "image"},
                {"name": "movie.mp4", "type": "video"},
                {"name": "report.pdf", "type": "document"},
                {"name": "logo.png", "type": "image"}
            ]
        }
    )
    
    workflow.start("Process all files")
    print(f"Processing results: {results}")


# =============================================================================
# Example 4: Three-Level Nesting - Complex Data Pipeline
# =============================================================================

def three_level_nesting_example():
    """
    Demonstrate three levels of nesting:
    Department -> Team -> Member
    """
    print("\n" + "="*60)
    print("Example 4: Three-Level Nesting - Organization Processing")
    print("="*60)
    
    results = []
    
    def process_member(ctx: WorkflowContext) -> StepResult:
        dept = ctx.variables.get("dept", {}).get("name", "?")
        team = ctx.variables.get("team", {}).get("name", "?")
        member = ctx.variables.get("member", "?")
        results.append(f"{dept}/{team}/{member}")
        return StepResult(output=f"Processed {member}")
    
    # Level 3: Process each member
    member_loop = loop(process_member, over="members", var_name="member")
    
    # Level 2: Process each team (contains member loop)
    team_loop = loop(steps=[member_loop], over="teams", var_name="team")
    
    # Level 1: Process each department (contains team loop)
    dept_loop = loop(steps=[team_loop], over="departments", var_name="dept")
    
    workflow = AgentFlow(
        steps=[dept_loop],
        variables={
            "departments": [
                {"name": "Engineering"},
                {"name": "Marketing"}
            ],
            "teams": [
                {"name": "Frontend", "members": ["Alice", "Bob"]},
                {"name": "Backend", "members": ["Charlie"]}
            ],
            "members": ["Member1", "Member2"]  # Simplified for demo
        }
    )
    
    workflow.start("Process organization")
    print(f"Processed paths: {results}")


# =============================================================================
# Main - Run All Examples
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("PraisonAI Nested Workflows Examples")
    print("="*60)
    
    nested_loop_example()
    parallel_inside_loop_example()
    route_inside_loop_example()
    three_level_nesting_example()
    
    print("\n" + "="*60)
    print("All nested workflow examples completed!")
    print("="*60)
