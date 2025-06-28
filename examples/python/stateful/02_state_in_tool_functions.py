#!/usr/bin/env python3
"""
State in Tool Functions Example
==============================

This example shows how to use workflow state within tool functions.
Tools can read and modify state to share information between agents and tasks.

Run this example:
    python 02_state_in_tool_functions.py
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
import time
import json
from typing import Dict, Any
from datetime import datetime


def track_progress() -> Dict[str, Any]:
    """Tool that tracks task progress using workflow state"""
    # Access current progress from state
    current_stage = workflow.get_state("stage", "not_started")
    completed_tasks = workflow.get_state("completed_tasks", 0)
    total_tasks = workflow.get_state("total_tasks", 10)
    
    # Increment completed tasks counter
    workflow.increment_state("completed_tasks", 1)
    
    # Track task completion time
    workflow.append_to_state("task_history", {
        "task_id": completed_tasks + 1,
        "stage": current_stage,
        "timestamp": datetime.now().isoformat(),
        "status": "completed"
    }, max_length=10)  # Keep only last 10 entries
    
    # Calculate progress
    new_completed = completed_tasks + 1
    progress_percentage = (new_completed / total_tasks) * 100
    
    return {
        "stage": current_stage,
        "tasks_completed": new_completed,
        "total_tasks": total_tasks,
        "progress": f"{progress_percentage:.1f}%",
        "remaining": total_tasks - new_completed
    }


def log_error(error_type: str, error_message: str) -> str:
    """Tool that logs errors to state"""
    # Increment error counter
    workflow.increment_state(f"error_count_{error_type}", 1, default=0)
    
    # Append to error log with timestamp
    error_entry = {
        "type": error_type,
        "message": error_message,
        "timestamp": datetime.now().isoformat()
    }
    
    workflow.append_to_state("error_log", error_entry, max_length=50)
    
    # Update last error timestamp
    workflow.set_state("last_error_time", datetime.now().isoformat())
    
    # Get current error count
    error_count = workflow.get_state(f"error_count_{error_type}", 0)
    
    return f"Error logged: {error_type} (Total {error_type} errors: {error_count})"


def process_data_batch() -> Dict[str, Any]:
    """Tool that processes data in batches using state for coordination"""
    # Get or initialize batch processing state
    if not workflow.has_state("batch_total"):
        workflow.set_state("batch_total", 5)
        workflow.set_state("batch_current", 0)
        workflow.set_state("batch_results", [])
    
    # Get current batch info
    batch_current = workflow.get_state("batch_current")
    batch_total = workflow.get_state("batch_total")
    
    # Process next batch
    batch_current += 1
    workflow.set_state("batch_current", batch_current)
    
    # Simulate batch processing
    result = {
        "batch_id": batch_current,
        "records_processed": 100,
        "processing_time": 0.5,
        "status": "success"
    }
    
    # Store batch result
    workflow.append_to_state("batch_results", result)
    
    # Update statistics
    workflow.increment_state("total_records_processed", 100, default=0)
    
    return {
        "batch": batch_current,
        "total_batches": batch_total,
        "result": result,
        "more_batches": batch_current < batch_total
    }


def generate_report() -> str:
    """Tool that generates a report from accumulated state data"""
    # Gather all state data
    completed_tasks = workflow.get_state("completed_tasks", 0)
    total_tasks = workflow.get_state("total_tasks", 10)
    task_history = workflow.get_state("task_history", [])
    error_log = workflow.get_state("error_log", [])
    batch_results = workflow.get_state("batch_results", [])
    total_records = workflow.get_state("total_records_processed", 0)
    
    # Count errors by type
    error_types = {}
    for key in workflow.get_all_state().keys():
        if key.startswith("error_count_"):
            error_type = key.replace("error_count_", "")
            error_types[error_type] = workflow.get_state(key)
    
    report = f"""
    ===== WORKFLOW REPORT =====
    
    Task Progress:
    - Completed: {completed_tasks}/{total_tasks} ({(completed_tasks/total_tasks*100):.1f}%)
    - Recent Tasks: {len(task_history)} tracked
    
    Batch Processing:
    - Batches Processed: {len(batch_results)}
    - Total Records: {total_records}
    
    Errors:
    - Total Errors: {len(error_log)}
    - Error Types: {json.dumps(error_types, indent=2) if error_types else 'None'}
    
    Recent Activity:
    """
    
    # Add recent task history
    if task_history:
        report += "\n    Recent Tasks:\n"
        for task in task_history[-3:]:  # Last 3 tasks
            report += f"    - Task {task['task_id']} completed at {task['timestamp']}\n"
    
    # Add recent errors
    if error_log:
        report += "\n    Recent Errors:\n"
        for error in error_log[-3:]:  # Last 3 errors
            report += f"    - {error['type']}: {error['message']} at {error['timestamp']}\n"
    
    return report


def update_configuration(key: str, value: Any) -> str:
    """Tool that updates configuration stored in state"""
    # Get current config
    config = workflow.get_state("config", {})
    
    # Store old value for audit
    old_value = config.get(key, "not_set")
    
    # Update config
    config[key] = value
    workflow.set_state("config", config)
    
    # Log configuration change
    workflow.append_to_state("config_changes", {
        "key": key,
        "old_value": old_value,
        "new_value": value,
        "timestamp": datetime.now().isoformat()
    }, max_length=100)
    
    return f"Configuration updated: {key} = {value} (was: {old_value})"


# Create agents
progress_tracker = Agent(
    name="ProgressTracker",
    role="Track and report task progress",
    goal="Monitor workflow progress using state",
    backstory="A meticulous tracker who monitors every task",
    tools=[track_progress, generate_report],
    llm="gpt-4o-mini",
    verbose=True
)

data_processor = Agent(
    name="DataProcessor",
    role="Process data in batches",
    goal="Efficiently process all data batches",
    backstory="A data processing specialist",
    tools=[process_data_batch],
    llm="gpt-4o-mini",
    verbose=True
)

error_handler = Agent(
    name="ErrorHandler",
    role="Handle and log errors",
    goal="Track all errors and maintain error logs",
    backstory="An error handling expert",
    tools=[log_error],
    llm="gpt-4o-mini",
    verbose=True
)

config_manager = Agent(
    name="ConfigManager",
    role="Manage system configuration",
    goal="Update and track configuration changes",
    backstory="A configuration management specialist",
    tools=[update_configuration],
    llm="gpt-4o-mini",
    verbose=True
)

# Create tasks
task1 = Task(
    name="initialize_tracking",
    description="Initialize the workflow and track the first progress update",
    expected_output="Initial progress report",
    agent=progress_tracker,
    tools=[track_progress]
)

task2 = Task(
    name="update_config",
    description="Update configuration settings: set 'batch_size' to 100 and 'retry_limit' to 3",
    expected_output="Configuration update confirmations",
    agent=config_manager,
    tools=[update_configuration]
)

task3 = Task(
    name="process_all_batches",
    description="Process all data batches and track progress",
    expected_output="All batch processing results",
    agent=data_processor,
    tools=[process_data_batch]
)

task4 = Task(
    name="simulate_errors",
    description="Log some sample errors: 'connection' error 'Failed to connect to database' and 'validation' error 'Invalid data format'",
    expected_output="Error logging confirmations",
    agent=error_handler,
    tools=[log_error]
)

task5 = Task(
    name="track_more_progress",
    description="Track progress for 3 more tasks",
    expected_output="Progress updates",
    agent=progress_tracker,
    tools=[track_progress]
)

task6 = Task(
    name="generate_final_report",
    description="Generate a comprehensive report of all activities",
    expected_output="Final workflow report",
    agent=progress_tracker,
    tools=[generate_report]
)

# Create workflow (global variable for state access in tools)
workflow = PraisonAIAgents(
    agents=[progress_tracker, data_processor, error_handler, config_manager],
    tasks=[task1, task2, task3, task4, task5, task6],
    verbose=True,
    process="sequential"
)

# Initialize workflow state
print("\n=== Initializing Workflow State ===")
workflow.set_state("stage", "processing")
workflow.set_state("total_tasks", 10)
workflow.set_state("completed_tasks", 0)

# Run the workflow
print("\n=== Starting Workflow ===")
result = workflow.start()

# Display final state summary
print("\n=== Final State Summary ===")
final_state = workflow.get_all_state()
print(f"Total state keys: {len(final_state)}")
print(f"Completed tasks: {final_state.get('completed_tasks', 0)}")
print(f"Total errors logged: {len(final_state.get('error_log', []))}")
print(f"Batches processed: {len(final_state.get('batch_results', []))}")
print(f"Configuration changes: {len(final_state.get('config_changes', []))}")

# Show some state details
print("\n=== State Details ===")
print(f"Current configuration: {json.dumps(final_state.get('config', {}), indent=2)}")
print(f"Error counts by type: ", end="")
error_counts = {k: v for k, v in final_state.items() if k.startswith("error_count_")}
print(json.dumps(error_counts, indent=2) if error_counts else "None")