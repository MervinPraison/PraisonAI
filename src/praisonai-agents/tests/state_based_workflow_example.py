"""
State-Based Workflow Control Example
===================================

This example shows how to use state for:
1. Conditional task execution based on state
2. Loop control using state
3. Dynamic workflow modification
4. State-based error handling and recovery
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from typing import Dict, Any, List
import random
import json

# Tool functions that use state for control flow
def analyze_data_quality() -> Dict[str, Any]:
    """Analyze data and set quality state"""
    # Simulate data quality check
    quality_score = random.uniform(0.5, 1.0)
    has_errors = random.choice([True, False])
    
    # Set state based on analysis
    workflow.set_state("quality_score", quality_score)
    workflow.set_state("has_errors", has_errors)
    workflow.set_state("data_status", "analyzed")
    
    if quality_score < 0.7:
        workflow.set_state("quality_level", "poor")
    elif quality_score < 0.85:
        workflow.set_state("quality_level", "moderate")
    else:
        workflow.set_state("quality_level", "good")
    
    return {
        "quality_score": quality_score,
        "has_errors": has_errors,
        "quality_level": workflow.get_state("quality_level"),
        "recommendation": "clean_data" if has_errors or quality_score < 0.8 else "proceed"
    }

def clean_data_based_on_state() -> Dict[str, Any]:
    """Clean data based on current state"""
    quality_score = workflow.get_state("quality_score", 0)
    has_errors = workflow.get_state("has_errors", False)
    cleaning_attempts = workflow.get_state("cleaning_attempts", 0)
    
    # Increment cleaning attempts
    workflow.set_state("cleaning_attempts", cleaning_attempts + 1)
    
    # Simulate cleaning improvement
    improvement = random.uniform(0.1, 0.2)
    new_quality = min(quality_score + improvement, 0.95)
    
    workflow.set_state("quality_score", new_quality)
    workflow.set_state("has_errors", False)
    workflow.set_state("last_cleaning_improvement", improvement)
    
    # Determine if more cleaning needed
    if new_quality < 0.8 and cleaning_attempts < 3:
        status = "needs_more_cleaning"
    else:
        status = "cleaning_complete"
        workflow.set_state("data_status", "cleaned")
    
    return {
        "previous_score": quality_score,
        "new_score": new_quality,
        "improvement": improvement,
        "attempts": cleaning_attempts + 1,
        "status": status
    }

def process_batch_with_state() -> Dict[str, Any]:
    """Process data in batches using state to track progress"""
    # Initialize batch processing state
    if not workflow.has_state("batch_total"):
        batch_total = random.randint(5, 10)
        workflow.set_state("batch_total", batch_total)
        workflow.set_state("batch_current", 0)
        workflow.set_state("batch_results", [])
    
    # Get current state
    batch_total = workflow.get_state("batch_total")
    batch_current = workflow.get_state("batch_current")
    batch_results = workflow.get_state("batch_results", [])
    
    # Process current batch
    batch_current += 1
    result = {
        "batch_number": batch_current,
        "records_processed": random.randint(100, 500),
        "errors": random.randint(0, 5)
    }
    batch_results.append(result)
    
    # Update state
    workflow.set_state("batch_current", batch_current)
    workflow.set_state("batch_results", batch_results)
    
    # Determine if more batches
    if batch_current < batch_total:
        status = "more_batches"
        workflow.set_state("batch_status", "in_progress")
    else:
        status = "all_batches_complete"
        workflow.set_state("batch_status", "completed")
        workflow.set_state("total_records", sum(r["records_processed"] for r in batch_results))
        workflow.set_state("total_errors", sum(r["errors"] for r in batch_results))
    
    return {
        "batch": result,
        "progress": f"{batch_current}/{batch_total}",
        "status": status,
        "remaining": batch_total - batch_current
    }

def generate_report_from_state() -> Dict[str, Any]:
    """Generate comprehensive report from accumulated state"""
    # Gather all relevant state
    report = {
        "data_quality": {
            "initial_score": workflow.get_state("quality_score", 0),
            "quality_level": workflow.get_state("quality_level", "unknown"),
            "cleaning_attempts": workflow.get_state("cleaning_attempts", 0),
            "final_status": workflow.get_state("data_status", "unknown")
        },
        "batch_processing": {
            "total_batches": workflow.get_state("batch_total", 0),
            "completed_batches": workflow.get_state("batch_current", 0),
            "total_records": workflow.get_state("total_records", 0),
            "total_errors": workflow.get_state("total_errors", 0),
            "status": workflow.get_state("batch_status", "not_started")
        },
        "workflow_metadata": {
            "has_errors": workflow.get_state("has_errors", False),
            "state_keys": list(workflow.get_all_state().keys()),
            "state_size": len(workflow.get_all_state())
        }
    }
    
    # Calculate summary metrics
    if workflow.has_state("batch_results"):
        batch_results = workflow.get_state("batch_results")
        report["batch_processing"]["average_records_per_batch"] = (
            sum(r["records_processed"] for r in batch_results) / len(batch_results)
            if batch_results else 0
        )
    
    # Set final state
    workflow.set_state("final_report_generated", True)
    workflow.set_state("workflow_complete", True)
    
    return report

def check_state_conditions() -> str:
    """Check various state conditions for decision making"""
    quality_level = workflow.get_state("quality_level", "unknown")
    cleaning_attempts = workflow.get_state("cleaning_attempts", 0)
    has_errors = workflow.get_state("has_errors", False)
    
    if quality_level == "poor" and cleaning_attempts == 0:
        return "needs_cleaning"
    elif quality_level == "moderate" and not has_errors:
        return "can_proceed"
    elif quality_level == "good":
        return "ready_for_processing"
    elif cleaning_attempts >= 3:
        return "max_cleaning_reached"
    else:
        return "needs_analysis"

# Create agents
data_analyst = Agent(
    name="DataAnalyst",
    role="Data quality analysis",
    goal="Analyze data quality and set appropriate state",
    backstory="Expert in data quality assessment",
    tools=[analyze_data_quality, check_state_conditions],
    llm="gpt-4o-mini"
)

data_engineer = Agent(
    name="DataEngineer", 
    role="Data cleaning and processing",
    goal="Clean data based on state and process in batches",
    backstory="Specialist in data transformation and batch processing",
    tools=[clean_data_based_on_state, process_batch_with_state],
    llm="gpt-4o-mini"
)

report_generator = Agent(
    name="ReportGenerator",
    role="Report generation",
    goal="Generate comprehensive reports from workflow state",
    backstory="Expert in creating detailed analytical reports",
    tools=[generate_report_from_state],
    llm="gpt-4o-mini"
)

# Create tasks with state-based conditions
analyze_task = Task(
    name="analyze_quality",
    description="Analyze the data quality and set initial state values",
    expected_output="Data quality analysis with recommendations",
    agent=data_analyst,
    tools=[analyze_data_quality]
)

decision_task = Task(
    name="quality_decision",
    description="Check data quality state and decide next action using check_state_conditions tool",
    expected_output="Decision on whether to clean data or proceed",
    agent=data_analyst,
    tools=[check_state_conditions],
    task_type="decision",
    condition={
        "needs_cleaning": ["clean_data"],
        "can_proceed": ["process_batches"],
        "ready_for_processing": ["process_batches"],
        "max_cleaning_reached": ["process_batches"],
        "needs_analysis": ["analyze_quality"]
    },
    context=[analyze_task]
)

clean_task = Task(
    name="clean_data",
    description="Clean the data to improve quality score. Check if more cleaning is needed.",
    expected_output="Cleaning results with status",
    agent=data_engineer,
    tools=[clean_data_based_on_state],
    task_type="decision",
    condition={
        "needs_more_cleaning": ["clean_data"],
        "cleaning_complete": ["process_batches"]
    }
)

process_task = Task(
    name="process_batches",
    description="Process data in batches. Continue until all batches are complete.",
    expected_output="Batch processing results",
    agent=data_engineer,
    tools=[process_batch_with_state],
    task_type="loop",
    condition={
        "more_batches": ["process_batches"],
        "all_batches_complete": ["generate_report"]
    }
)

report_task = Task(
    name="generate_report",
    description="Generate final report from all accumulated state data",
    expected_output="Comprehensive workflow report",
    agent=report_generator,
    tools=[generate_report_from_state]
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[data_analyst, data_engineer, report_generator],
    tasks=[analyze_task, decision_task, clean_task, process_task, report_task],
    verbose=1,
    process="workflow"
)

# Demonstrate state before workflow
print("\n=== State-Based Workflow Control Demo ===")
print("\n1. Initial state (empty):", workflow.get_all_state())

# Run the workflow
print("\n2. Running workflow with state-based decisions...")
result = workflow.start()

# Show final state
print("\n3. Final workflow state:")
final_state = workflow.get_all_state()
print(f"   Total state entries: {len(final_state)}")
print(f"   Quality level: {final_state.get('quality_level')}")
print(f"   Cleaning attempts: {final_state.get('cleaning_attempts', 0)}")
print(f"   Batches processed: {final_state.get('batch_current', 0)}/{final_state.get('batch_total', 0)}")
print(f"   Total records: {final_state.get('total_records', 0)}")
print(f"   Workflow complete: {final_state.get('workflow_complete', False)}")

# Display task execution path
print("\n4. Task Execution Path:")
for task_name, task in workflow.tasks.items():
    if hasattr(task, 'status'):
        print(f"   {task_name}: {task.status}")

print("\n=== Demo Complete ===")