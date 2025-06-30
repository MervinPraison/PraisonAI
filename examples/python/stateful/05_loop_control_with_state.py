#!/usr/bin/env python3
"""
Loop Control with State Example
==============================

This example demonstrates how to use state to control loops and iterative processes.
Tasks can loop based on state conditions until certain criteria are met.

Run this example:
    python 05_loop_control_with_state.py
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
import time
import random
from datetime import datetime
from typing import Dict, Any


def process_batch() -> str:
    """Process data in batches using state to track progress"""
    # Initialize batch state if needed
    if not workflow.has_state("batch_total"):
        workflow.set_state("batch_total", 5)
        workflow.set_state("batch_current", 0)
        workflow.set_state("batch_start_time", datetime.now().isoformat())
    
    # Get current batch info
    batch_current = workflow.get_state("batch_current")
    batch_total = workflow.get_state("batch_total")
    
    # Process next batch
    batch_current += 1
    workflow.set_state("batch_current", batch_current)
    
    # Simulate batch processing with random success/failure
    success = random.random() > 0.2  # 80% success rate
    records_processed = random.randint(80, 120) if success else 0
    
    # Create batch result
    batch_result = {
        "batch_id": batch_current,
        "records_processed": records_processed,
        "status": "success" if success else "failed",
        "timestamp": datetime.now().isoformat()
    }
    
    # Store batch result
    workflow.append_to_state("batch_results", batch_result)
    
    # Update statistics
    if success:
        workflow.increment_state("successful_batches", 1, default=0)
        workflow.increment_state("total_records_processed", records_processed, default=0)
    else:
        workflow.increment_state("failed_batches", 1, default=0)
        # Add to retry queue
        workflow.append_to_state("retry_queue", batch_current)
    
    # Determine if more batches
    if batch_current < batch_total:
        return "more_batches"
    else:
        # Check if we have retries
        retry_queue = workflow.get_state("retry_queue", [])
        if retry_queue:
            return "process_retries"
        else:
            return "all_batches_complete"


def process_retry_batch() -> str:
    """Process failed batches from retry queue"""
    retry_queue = workflow.get_state("retry_queue", [])
    
    if not retry_queue:
        return "no_retries"
    
    # Get next batch to retry
    batch_id = retry_queue.pop(0)
    workflow.set_state("retry_queue", retry_queue)
    
    # Increment retry counter
    workflow.increment_state(f"batch_{batch_id}_retry_count", 1, default=0)
    retry_count = workflow.get_state(f"batch_{batch_id}_retry_count")
    
    # Process with higher success rate on retry
    success = random.random() > 0.1  # 90% success rate on retry
    records_processed = random.randint(80, 120) if success else 0
    
    # Update batch result
    retry_result = {
        "batch_id": batch_id,
        "records_processed": records_processed,
        "status": "retry_success" if success else "retry_failed",
        "retry_attempt": retry_count,
        "timestamp": datetime.now().isoformat()
    }
    
    workflow.append_to_state("retry_results", retry_result)
    
    if success:
        workflow.increment_state("successful_retries", 1, default=0)
        workflow.increment_state("total_records_processed", records_processed, default=0)
    else:
        # Check retry limit
        if retry_count < 3:
            # Add back to retry queue
            retry_queue.append(batch_id)
            workflow.set_state("retry_queue", retry_queue)
        else:
            # Mark as permanently failed
            workflow.append_to_state("permanently_failed_batches", batch_id)
    
    # Check if more retries needed
    retry_queue = workflow.get_state("retry_queue", [])
    if retry_queue:
        return "more_retries"
    else:
        return "retries_complete"


def collect_paginated_data() -> str:
    """Collect data from paginated API using state"""
    # Initialize pagination state
    if not workflow.has_state("current_page"):
        workflow.set_state("current_page", 1)
        workflow.set_state("total_pages", 0)  # Will be set after first call
        workflow.set_state("items_collected", [])
    
    current_page = workflow.get_state("current_page")
    
    # Simulate API call
    if current_page == 1:
        # First call - determine total pages
        total_pages = 4
        workflow.set_state("total_pages", total_pages)
    
    # Simulate collecting items
    items_per_page = random.randint(8, 12)
    new_items = [f"item_{current_page}_{i}" for i in range(items_per_page)]
    
    # Add to collected items
    items = workflow.get_state("items_collected", [])
    items.extend(new_items)
    workflow.set_state("items_collected", items)
    
    # Update page counter
    workflow.increment_state("current_page", 1)
    
    # Log page processing
    workflow.append_to_state("page_log", {
        "page": current_page,
        "items_collected": items_per_page,
        "timestamp": datetime.now().isoformat()
    })
    
    # Check if more pages
    total_pages = workflow.get_state("total_pages")
    if current_page < total_pages:
        return "more_pages"
    else:
        return "pagination_complete"


def validate_collected_items() -> str:
    """Validate all collected items"""
    items = workflow.get_state("items_collected", [])
    
    # Initialize validation state
    if not workflow.has_state("validation_index"):
        workflow.set_state("validation_index", 0)
        workflow.set_state("valid_items", [])
        workflow.set_state("invalid_items", [])
    
    validation_index = workflow.get_state("validation_index")
    batch_size = 5  # Validate 5 items at a time
    
    # Get items to validate in this iteration
    end_index = min(validation_index + batch_size, len(items))
    items_to_validate = items[validation_index:end_index]
    
    # Simulate validation
    for item in items_to_validate:
        # Random validation (90% valid)
        is_valid = random.random() > 0.1
        
        if is_valid:
            workflow.append_to_state("valid_items", item)
        else:
            workflow.append_to_state("invalid_items", item)
    
    # Update validation index
    workflow.set_state("validation_index", end_index)
    
    # Check if more items to validate
    if end_index < len(items):
        return "more_validation"
    else:
        return "validation_complete"


def generate_loop_report() -> str:
    """Generate comprehensive report on all loop operations"""
    # Batch processing stats
    batch_total = workflow.get_state("batch_total", 0)
    successful_batches = workflow.get_state("successful_batches", 0)
    failed_batches = workflow.get_state("failed_batches", 0)
    successful_retries = workflow.get_state("successful_retries", 0)
    permanently_failed = len(workflow.get_state("permanently_failed_batches", []))
    total_records = workflow.get_state("total_records_processed", 0)
    
    # Pagination stats
    total_pages = workflow.get_state("total_pages", 0)
    items_collected = len(workflow.get_state("items_collected", []))
    
    # Validation stats
    valid_items = len(workflow.get_state("valid_items", []))
    invalid_items = len(workflow.get_state("invalid_items", []))
    
    # Calculate timing
    start_time = workflow.get_state("batch_start_time", "unknown")
    
    report = f"""
    Loop Operations Report
    =====================
    
    Batch Processing:
    - Total Batches: {batch_total}
    - Successful: {successful_batches}
    - Failed Initially: {failed_batches}
    - Successful Retries: {successful_retries}
    - Permanently Failed: {permanently_failed}
    - Total Records Processed: {total_records}
    - Success Rate: {((successful_batches + successful_retries) / batch_total * 100):.1f}%
    
    Pagination Collection:
    - Pages Processed: {total_pages}
    - Items Collected: {items_collected}
    - Average Items/Page: {items_collected / total_pages:.1f}
    
    Validation Results:
    - Total Items: {items_collected}
    - Valid Items: {valid_items}
    - Invalid Items: {invalid_items}
    - Validation Rate: {(valid_items / items_collected * 100):.1f}%
    
    Processing Started: {start_time}
    """
    
    # Add batch failure details
    retry_results = workflow.get_state("retry_results", [])
    if retry_results:
        report += "\n    Retry Details:\n"
        for result in retry_results[-3:]:  # Last 3 retries
            report += f"    - Batch {result['batch_id']}: {result['status']} (Attempt {result['retry_attempt']})\n"
    
    return report


# Create agents
batch_processor = Agent(
    name="BatchProcessor",
    role="Process data in batches",
    goal="Process all batches successfully with retry logic",
    backstory="A batch processing expert",
    tools=[process_batch, process_retry_batch],
    llm="gpt-4o-mini",
    verbose=True
)

data_collector = Agent(
    name="DataCollector",
    role="Collect paginated data",
    goal="Collect all data from paginated source",
    backstory="A data collection specialist",
    tools=[collect_paginated_data],
    llm="gpt-4o-mini",
    verbose=True
)

validator = Agent(
    name="Validator",
    role="Validate collected items",
    goal="Validate all collected items in batches",
    backstory="A data validation expert",
    tools=[validate_collected_items],
    llm="gpt-4o-mini",
    verbose=True
)

reporter = Agent(
    name="Reporter",
    role="Generate reports",
    goal="Create comprehensive reports on loop operations",
    backstory="A reporting specialist",
    tools=[generate_loop_report],
    llm="gpt-4o-mini",
    verbose=True
)

# Create loop tasks
batch_loop_task = Task(
    name="process_batches",
    description="Process all data batches",
    expected_output="Batch processing status",
    agent=batch_processor,
    tools=[process_batch],
    task_type="loop",
    condition={
        "more_batches": ["process_batches"],  # Loop back to itself
        "process_retries": ["retry_failed_batches"],
        "all_batches_complete": ["collect_pages"]  # Go to next task
    }
)

retry_loop_task = Task(
    name="retry_failed_batches",
    description="Retry processing for failed batches",
    expected_output="Retry processing status",
    agent=batch_processor,
    tools=[process_retry_batch],
    task_type="loop",
    condition={
        "more_retries": ["retry_failed_batches"],  # Loop back to itself
        "retries_complete": ["collect_pages"],
        "no_retries": ["collect_pages"]
    }
)

pagination_loop_task = Task(
    name="collect_pages",
    description="Collect all pages of data",
    expected_output="Page collection status",
    agent=data_collector,
    tools=[collect_paginated_data],
    task_type="loop",
    condition={
        "more_pages": ["collect_pages"],  # Loop back to itself
        "pagination_complete": ["validate_items"]
    }
)

validation_loop_task = Task(
    name="validate_items",
    description="Validate all collected items in batches",
    expected_output="Validation status",
    agent=validator,
    tools=[validate_collected_items],
    task_type="loop",
    condition={
        "more_validation": ["validate_items"],  # Loop back to itself
        "validation_complete": ["generate_report"]
    }
)

report_task = Task(
    name="generate_report",
    description="Generate final report on all loop operations",
    expected_output="Comprehensive loop operations report",
    agent=reporter,
    tools=[generate_loop_report]
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[batch_processor, data_collector, validator, reporter],
    tasks=[batch_loop_task, retry_loop_task, pagination_loop_task, validation_loop_task, report_task],
    verbose=True,
    process="sequential"
)

# Initialize workflow
print("\n=== Starting Loop Control Example ===")
print("This example will demonstrate:")
print("1. Batch processing with automatic retry on failure")
print("2. Paginated data collection")
print("3. Iterative validation of collected items")
print("4. All controlled by state-based loop conditions")

# Run workflow
result = workflow.start()

# Display loop statistics
print("\n=== Loop Statistics ===")
print(f"Total loop iterations:")
print(f"- Batch processing: {workflow.get_state('batch_current', 0)} batches")
print(f"- Retry processing: {len(workflow.get_state('retry_results', []))} retries")
print(f"- Page collection: {workflow.get_state('current_page', 1) - 1} pages")
print(f"- Item validation: {workflow.get_state('validation_index', 0)} items validated")

# Show state size
print(f"\n=== State Management ===")
print(f"Total state keys: {len(workflow.get_all_state())}")
print(f"Batch results stored: {len(workflow.get_state('batch_results', []))}")
print(f"Items collected: {len(workflow.get_state('items_collected', []))}")