#!/usr/bin/env python3
"""Test script to verify async task execution in sequential mode"""

import asyncio
import time
import os
from datetime import datetime

# Set up the environment
import sys
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create test agents
async_agent = Agent(
    name="AsyncAgent",
    role="Async task executor",
    goal="Execute async tasks",
    backstory="An agent that executes async tasks",
    llm="openai/gpt-3.5-turbo"  # Using a mock/test LLM
)

sync_agent = Agent(
    name="SyncAgent", 
    role="Sync task executor",
    goal="Execute sync tasks",
    backstory="An agent that executes sync tasks",
    llm="openai/gpt-3.5-turbo"
)

# Track execution times
execution_log = []

def log_execution(task_name, start_time, end_time, is_async):
    execution_log.append({
        "task": task_name,
        "start": start_time,
        "end": end_time,
        "duration": end_time - start_time,
        "type": "async" if is_async else "sync"
    })

# Create test tasks
async def async_task_function(task_name, delay):
    start_time = time.time()
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} - {task_name} started (async)")
    await asyncio.sleep(delay)
    end_time = time.time()
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} - {task_name} completed (async)")
    log_execution(task_name, start_time, end_time, True)
    return f"{task_name} result after {delay}s"

def sync_task_function(task_name, delay):
    start_time = time.time()
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} - {task_name} started (sync)")
    time.sleep(delay)
    end_time = time.time()
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} - {task_name} completed (sync)")
    log_execution(task_name, start_time, end_time, False)
    return f"{task_name} result after {delay}s"

# Test scenario: Multiple async tasks followed by sync task followed by more async tasks
tasks = []

# First batch of async tasks (should run in parallel)
task1 = Task(
    name="async_task_1",
    description="First async task - sleep 2s",
    expected_output="Task result",
    agent=async_agent,
    async_execution=True
)

task2 = Task(
    name="async_task_2", 
    description="Second async task - sleep 2s",
    expected_output="Task result",
    agent=async_agent,
    async_execution=True
)

task3 = Task(
    name="async_task_3",
    description="Third async task - sleep 2s", 
    expected_output="Task result",
    agent=async_agent,
    async_execution=True
)

# Sync task (should wait for async tasks to complete)
task4 = Task(
    name="sync_task_1",
    description="First sync task - sleep 1s",
    expected_output="Task result",
    agent=sync_agent,
    async_execution=False
)

# Second batch of async tasks (should run in parallel after sync task)
task5 = Task(
    name="async_task_4",
    description="Fourth async task - sleep 1s",
    expected_output="Task result", 
    agent=async_agent,
    async_execution=True
)

task6 = Task(
    name="async_task_5",
    description="Fifth async task - sleep 1s",
    expected_output="Task result",
    agent=async_agent,
    async_execution=True
)

tasks = [task1, task2, task3, task4, task5, task6]

async def test_sequential_async_execution():
    """Test that async tasks run in parallel in sequential mode"""
    
    print("\n=== Testing Sequential Mode with Async Tasks ===\n")
    
    # Mock the agent execute methods to use our test functions
    original_execute = Agent.execute
    original_aexecute = Agent.aexecute
    
    def mock_execute(self, task, context=None):
        if "async" in task.name:
            # This shouldn't be called for async tasks
            print(f"WARNING: Sync execute called for async task {task.name}")
        else:
            delay = int(task.description.split("sleep ")[1].split("s")[0])
            return sync_task_function(task.name, delay)
    
    async def mock_aexecute(self, task, context=None):
        if "async" in task.name:
            delay = int(task.description.split("sleep ")[1].split("s")[0])
            return await async_task_function(task.name, delay)
        else:
            # This shouldn't be called for sync tasks
            print(f"WARNING: Async execute called for sync task {task.name}")
    
    # Patch the methods
    Agent.execute = mock_execute
    Agent.aexecute = mock_aexecute
    
    try:
        # Create workflow
        workflow = PraisonAIAgents(
            agents=[async_agent, sync_agent],
            tasks=tasks,
            process="sequential",
            verbose=True
        )
        
        # Run the workflow
        start_time = time.time()
        await workflow.astart()
        end_time = time.time()
        
        print(f"\nTotal execution time: {end_time - start_time:.2f}s")
        
        # Analyze results
        print("\n=== Execution Analysis ===")
        
        # Check if first batch of async tasks ran in parallel
        async_batch1 = [log for log in execution_log if log["task"] in ["async_task_1", "async_task_2", "async_task_3"]]
        if async_batch1:
            earliest_start = min(log["start"] for log in async_batch1)
            latest_end = max(log["end"] for log in async_batch1)
            batch1_duration = latest_end - earliest_start
            print(f"\nFirst async batch (3 tasks, 2s each):")
            print(f"  - Started at: {earliest_start:.2f}")
            print(f"  - Ended at: {latest_end:.2f}")
            print(f"  - Total duration: {batch1_duration:.2f}s")
            print(f"  - Parallel execution: {'YES' if batch1_duration < 4 else 'NO'} (expected ~2s for parallel, 6s for sequential)")
        
        # Check sync task timing
        sync_logs = [log for log in execution_log if log["type"] == "sync"]
        if sync_logs:
            sync_log = sync_logs[0]
            print(f"\nSync task:")
            print(f"  - Started at: {sync_log['start']:.2f}")
            print(f"  - Ended at: {sync_log['end']:.2f}")
            print(f"  - Started after async batch: {'YES' if sync_log['start'] >= latest_end - 0.1 else 'NO'}")
        
        # Check if second batch of async tasks ran in parallel
        async_batch2 = [log for log in execution_log if log["task"] in ["async_task_4", "async_task_5"]]
        if async_batch2:
            earliest_start = min(log["start"] for log in async_batch2)
            latest_end = max(log["end"] for log in async_batch2)
            batch2_duration = latest_end - earliest_start
            print(f"\nSecond async batch (2 tasks, 1s each):")
            print(f"  - Started at: {earliest_start:.2f}")
            print(f"  - Ended at: {latest_end:.2f}")
            print(f"  - Total duration: {batch2_duration:.2f}s")
            print(f"  - Parallel execution: {'YES' if batch2_duration < 1.5 else 'NO'} (expected ~1s for parallel, 2s for sequential)")
        
        # Overall assessment
        print(f"\n=== Test Result ===")
        expected_time = 2 + 1 + 1  # First batch (2s parallel) + sync (1s) + second batch (1s parallel)
        actual_time = end_time - start_time
        print(f"Expected total time (with parallel async): ~{expected_time}s")
        print(f"Actual total time: {actual_time:.2f}s")
        
        if actual_time < expected_time + 1:  # Allow 1s margin for overhead
            print("✅ PASS: Async tasks executed in parallel!")
        else:
            print("❌ FAIL: Async tasks did not execute in parallel as expected")
            
    finally:
        # Restore original methods
        Agent.execute = original_execute
        Agent.aexecute = original_aexecute

if __name__ == "__main__":
    # Set a dummy API key to avoid errors
    os.environ["OPENAI_API_KEY"] = "test-key"
    
    # Run the test
    asyncio.run(test_sequential_async_execution())