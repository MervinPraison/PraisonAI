#!/usr/bin/env python3
"""
Session State Persistence Example
================================

This example demonstrates how to save and restore workflow state using sessions.
This is useful for long-running workflows that may need to be paused and resumed.

Run this example:
    python 04_session_state_persistence.py
"""

from praisonaiagents import Agent, Task, PraisonAIAgents, Session
import json
import time
from datetime import datetime
from typing import Dict, Any


def process_customer_data(customer_id: str) -> Dict[str, Any]:
    """Process customer data and update state"""
    # Track which customers have been processed
    processed_customers = workflow.get_state("processed_customers", [])
    
    # Simulate data processing
    processing_result = {
        "customer_id": customer_id,
        "status": "processed",
        "timestamp": datetime.now().isoformat(),
        "records_processed": 150
    }
    
    # Update state
    processed_customers.append(customer_id)
    workflow.set_state("processed_customers", processed_customers)
    
    # Increment counters
    workflow.increment_state("total_customers_processed", 1, default=0)
    workflow.increment_state("total_records_processed", 150, default=0)
    
    # Add to processing history
    workflow.append_to_state("processing_history", processing_result, max_length=100)
    
    return processing_result


def check_processing_status() -> str:
    """Check current processing status"""
    total_customers = workflow.get_state("total_customers_processed", 0)
    total_records = workflow.get_state("total_records_processed", 0)
    processed_list = workflow.get_state("processed_customers", [])
    session_id = workflow.get_state("session_id", "unknown")
    
    status = f"""
    Processing Status (Session: {session_id})
    ========================================
    Total Customers Processed: {total_customers}
    Total Records Processed: {total_records}
    Customers: {', '.join(processed_list) if processed_list else 'None'}
    """
    
    # Check if we need to continue
    remaining_customers = workflow.get_state("remaining_customers", [])
    if remaining_customers:
        status += f"\nRemaining Customers: {', '.join(remaining_customers)}"
        
    return status


def save_checkpoint() -> str:
    """Save current state as a checkpoint"""
    session_id = workflow.get_state("session_id", "session_001")
    
    # Add checkpoint metadata
    workflow.set_state("last_checkpoint", datetime.now().isoformat())
    workflow.set_state("checkpoint_number", workflow.get_state("checkpoint_number", 0) + 1)
    
    # Save session state
    workflow.save_session_state(session_id, include_memory=True)
    
    checkpoint_num = workflow.get_state("checkpoint_number")
    return f"Checkpoint #{checkpoint_num} saved for session {session_id}"


def simulate_long_task() -> str:
    """Simulate a long-running task that updates progress"""
    task_name = "data_migration"
    
    # Initialize or get current progress
    progress = workflow.get_state(f"{task_name}_progress", 0)
    
    # Simulate work in chunks
    chunk_size = 20
    progress += chunk_size
    
    # Update state
    workflow.set_state(f"{task_name}_progress", progress)
    workflow.set_state(f"{task_name}_last_update", datetime.now().isoformat())
    
    # Check if complete
    if progress >= 100:
        workflow.set_state(f"{task_name}_status", "completed")
        return f"Task '{task_name}' completed!"
    else:
        workflow.set_state(f"{task_name}_status", "in_progress")
        return f"Task '{task_name}' progress: {progress}%"


def generate_session_report() -> str:
    """Generate a report for the current session"""
    session_id = workflow.get_state("session_id", "unknown")
    start_time = workflow.get_state("session_start_time", "unknown")
    checkpoints = workflow.get_state("checkpoint_number", 0)
    
    # Get all task statuses
    all_state = workflow.get_all_state()
    task_statuses = {}
    for key, value in all_state.items():
        if key.endswith("_status"):
            task_name = key.replace("_status", "")
            task_statuses[task_name] = value
    
    report = f"""
    Session Report
    ==============
    Session ID: {session_id}
    Start Time: {start_time}
    Checkpoints: {checkpoints}
    
    Processing Summary:
    - Customers Processed: {workflow.get_state('total_customers_processed', 0)}
    - Records Processed: {workflow.get_state('total_records_processed', 0)}
    
    Task Statuses:
    """
    
    for task, status in task_statuses.items():
        progress = workflow.get_state(f"{task}_progress", "N/A")
        report += f"    - {task}: {status} (Progress: {progress}%)\n"
    
    # Add processing history summary
    history = workflow.get_state("processing_history", [])
    if history:
        report += f"\n    Recent Processing ({len(history)} total):\n"
        for entry in history[-3:]:  # Last 3 entries
            report += f"    - {entry['customer_id']} at {entry['timestamp']}\n"
    
    return report


# Create agents
data_processor = Agent(
    name="DataProcessor",
    role="Process customer data",
    goal="Process all customer data efficiently",
    backstory="A data processing specialist",
    tools=[process_customer_data],
    llm="gpt-4o-mini",
    verbose=True
)

status_monitor = Agent(
    name="StatusMonitor",
    role="Monitor processing status",
    goal="Track and report processing progress",
    backstory="A monitoring specialist",
    tools=[check_processing_status, save_checkpoint],
    llm="gpt-4o-mini",
    verbose=True
)

task_runner = Agent(
    name="TaskRunner",
    role="Run long-running tasks",
    goal="Execute tasks that may span multiple sessions",
    backstory="A task execution specialist",
    tools=[simulate_long_task],
    llm="gpt-4o-mini",
    verbose=True
)

report_generator = Agent(
    name="ReportGenerator",
    role="Generate session reports",
    goal="Create comprehensive session reports",
    backstory="A reporting specialist",
    tools=[generate_session_report],
    llm="gpt-4o-mini",
    verbose=True
)

# Create tasks for initial session
initial_tasks = [
    Task(
        name="check_initial_status",
        description="Check the initial processing status",
        expected_output="Initial status report",
        agent=status_monitor,
        tools=[check_processing_status]
    ),
    Task(
        name="process_customer_1",
        description="Process customer data for customer 'CUST001'",
        expected_output="Processing result for CUST001",
        agent=data_processor,
        tools=[process_customer_data]
    ),
    Task(
        name="process_customer_2",
        description="Process customer data for customer 'CUST002'",
        expected_output="Processing result for CUST002",
        agent=data_processor,
        tools=[process_customer_data]
    ),
    Task(
        name="run_long_task",
        description="Run the long-running data migration task",
        expected_output="Task progress update",
        agent=task_runner,
        tools=[simulate_long_task]
    ),
    Task(
        name="save_checkpoint_1",
        description="Save a checkpoint of the current state",
        expected_output="Checkpoint confirmation",
        agent=status_monitor,
        tools=[save_checkpoint]
    ),
    Task(
        name="generate_report_1",
        description="Generate a report for the current session",
        expected_output="Session report",
        agent=report_generator,
        tools=[generate_session_report]
    )
]

# Create workflow with memory enabled
workflow = PraisonAIAgents(
    agents=[data_processor, status_monitor, task_runner, report_generator],
    tasks=initial_tasks,
    verbose=True,
    process="sequential",
    memory=True  # Enable memory for persistence
)

# Initialize session
session_id = "project_session_001"
print(f"\n=== Starting Session: {session_id} ===")

# Set initial session state
workflow.set_state("session_id", session_id)
workflow.set_state("session_start_time", datetime.now().isoformat())
workflow.set_state("remaining_customers", ["CUST003", "CUST004", "CUST005"])

# Run initial workflow
print("\n=== Running Initial Workflow ===")
result = workflow.start()

# Save session state
print("\n=== Saving Session State ===")
workflow.save_session_state(session_id)
saved_state = workflow.get_all_state()
print(f"Saved {len(saved_state)} state keys")

# Simulate session interruption
print("\n=== Simulating Session Interruption ===")
print("Clearing current state to simulate new session...")
workflow.clear_state()
print(f"State after clear: {len(workflow.get_all_state())} keys")

# Create tasks for resumed session
resumed_tasks = [
    Task(
        name="check_resumed_status",
        description="Check the status after resuming",
        expected_output="Resumed status report",
        agent=status_monitor,
        tools=[check_processing_status]
    ),
    Task(
        name="process_remaining_customers",
        description="Process remaining customers: CUST003, CUST004",
        expected_output="Processing results for remaining customers",
        agent=data_processor,
        tools=[process_customer_data]
    ),
    Task(
        name="continue_long_task",
        description="Continue the long-running data migration task",
        expected_output="Updated task progress",
        agent=task_runner,
        tools=[simulate_long_task]
    ),
    Task(
        name="save_checkpoint_2",
        description="Save another checkpoint",
        expected_output="Checkpoint confirmation",
        agent=status_monitor,
        tools=[save_checkpoint]
    ),
    Task(
        name="generate_final_report",
        description="Generate final session report",
        expected_output="Final session report",
        agent=report_generator,
        tools=[generate_session_report]
    )
]

# Create new workflow instance for resumed session
resumed_workflow = PraisonAIAgents(
    agents=[data_processor, status_monitor, task_runner, report_generator],
    tasks=resumed_tasks,
    verbose=True,
    process="sequential",
    memory=True
)

# Make resumed_workflow available globally for tools
workflow = resumed_workflow

# Restore session state
print(f"\n=== Resuming Session: {session_id} ===")
workflow.restore_session_state(session_id)
restored_state = workflow.get_all_state()
print(f"Restored {len(restored_state)} state keys")

# Show what was restored
print("\nRestored state includes:")
print(f"- Processed customers: {workflow.get_state('processed_customers', [])}")
print(f"- Total records: {workflow.get_state('total_records_processed', 0)}")
print(f"- Task progress: {workflow.get_state('data_migration_progress', 0)}%")

# Continue workflow
print("\n=== Continuing Workflow ===")
result = resumed_workflow.start()

# Final state summary
print("\n=== Final Session Summary ===")
final_state = workflow.get_all_state()
print(f"Total customers processed: {workflow.get_state('total_customers_processed', 0)}")
print(f"Total records processed: {workflow.get_state('total_records_processed', 0)}")
print(f"Checkpoints created: {workflow.get_state('checkpoint_number', 0)}")
print(f"Task status: {workflow.get_state('data_migration_status', 'unknown')}")