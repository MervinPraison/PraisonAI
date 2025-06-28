#!/usr/bin/env python3
"""
Basic State Management Example
==============================

This example demonstrates the fundamental state management capabilities in PraisonAI.
It shows how to set, get, update, and manage state values in a multi-agent workflow.

Run this example:
    python 01_basic_state_management.py
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
import json
from typing import Dict, Any


def display_project_status() -> str:
    """Tool to display current project status from workflow state"""
    # Access state from the global workflow variable
    project_name = workflow.get_state("project_name", "Unknown Project")
    budget = workflow.get_state("budget", 0)
    stage = workflow.get_state("stage", "not_started")
    team_size = workflow.get_state("team_size", 0)
    features = workflow.get_state("features", [])
    
    status = f"""
    Project Status Report
    ====================
    Project: {project_name}
    Budget: ${budget:,}
    Stage: {stage}
    Team Size: {team_size}
    Features: {', '.join(features) if features else 'None added yet'}
    """
    
    return status


def add_feature(feature_name: str) -> str:
    """Tool to add a new feature to the project"""
    features = workflow.get_state("features", [])
    features.append(feature_name)
    workflow.set_state("features", features)
    
    return f"Added feature: {feature_name}. Total features: {len(features)}"


def update_project_stage(new_stage: str) -> str:
    """Tool to update the project stage"""
    old_stage = workflow.get_state("stage", "not_started")
    workflow.set_state("stage", new_stage)
    
    # Log stage transition
    transitions = workflow.get_state("stage_transitions", [])
    transitions.append({"from": old_stage, "to": new_stage})
    workflow.set_state("stage_transitions", transitions)
    
    return f"Project stage updated from '{old_stage}' to '{new_stage}'"


def check_budget_health() -> Dict[str, Any]:
    """Tool to check budget health"""
    budget = workflow.get_state("budget", 0)
    spent = workflow.get_state("spent", 0)
    
    if budget == 0:
        health = "undefined"
        percentage = 0
    else:
        percentage = (spent / budget) * 100
        if percentage > 90:
            health = "critical"
        elif percentage > 70:
            health = "warning"
        else:
            health = "healthy"
    
    return {
        "budget": budget,
        "spent": spent,
        "remaining": budget - spent,
        "percentage_used": percentage,
        "health": health
    }


# Create agents
project_manager = Agent(
    name="ProjectManager",
    role="Manage project state and status",
    goal="Track and report project progress",
    backstory="An experienced project manager who keeps track of all project details",
    tools=[display_project_status, update_project_stage],
    llm="gpt-4o-mini",
    verbose=True
)

developer = Agent(
    name="Developer",
    role="Add features to the project",
    goal="Implement new features and track them in state",
    backstory="A skilled developer who implements features",
    tools=[add_feature, display_project_status],
    llm="gpt-4o-mini",
    verbose=True
)

finance_manager = Agent(
    name="FinanceManager",
    role="Monitor project budget",
    goal="Ensure project stays within budget",
    backstory="A careful finance manager who tracks spending",
    tools=[check_budget_health],
    llm="gpt-4o-mini",
    verbose=True
)

# Create tasks
task1 = Task(
    name="initialize_project",
    description="Initialize the project and display initial status",
    expected_output="Initial project status report",
    agent=project_manager,
    tools=[display_project_status]
)

task2 = Task(
    name="add_core_features",
    description="Add the following core features to the project: 'User Authentication', 'Dashboard', 'API Integration'",
    expected_output="Confirmation of added features",
    agent=developer,
    tools=[add_feature]
)

task3 = Task(
    name="update_to_development",
    description="Update the project stage to 'development' and show updated status",
    expected_output="Updated project status",
    agent=project_manager,
    tools=[update_project_stage, display_project_status]
)

task4 = Task(
    name="check_budget",
    description="Check the current budget health and provide a financial report",
    expected_output="Budget health report",
    agent=finance_manager,
    tools=[check_budget_health]
)

# Create workflow (global variable for state access in tools)
workflow = PraisonAIAgents(
    agents=[project_manager, developer, finance_manager],
    tasks=[task1, task2, task3, task4],
    verbose=True,
    process="sequential"
)

# Set initial state values
print("\n=== Setting Initial State ===")
workflow.set_state("project_name", "AI Assistant Platform")
workflow.set_state("budget", 100000)
workflow.set_state("spent", 25000)
workflow.set_state("features", [])

# Update multiple state values at once
workflow.update_state({
    "stage": "planning",
    "team_size": 5,
    "project_manager": "Alice",
    "tech_stack": ["Python", "React", "PostgreSQL"]
})

# Demonstrate state operations
print("\n=== State Operations Demo ===")

# Check if state exists
if workflow.has_state("budget"):
    budget = workflow.get_state("budget")
    print(f"Project budget: ${budget:,}")

# Get all state
all_state = workflow.get_all_state()
print(f"\nAll state keys: {list(all_state.keys())}")

# Get state with default
priority = workflow.get_state("priority", "medium")
print(f"Project priority: {priority}")

# Run the workflow
print("\n=== Starting Workflow ===")
result = workflow.start()

# Display final state
print("\n=== Final State ===")
final_state = workflow.get_all_state()
print(json.dumps(final_state, indent=2))

# Demonstrate state deletion
print("\n=== State Cleanup Demo ===")
workflow.delete_state("project_manager")
print(f"State after deletion: {list(workflow.get_all_state().keys())}")

# Clear all state (commented out to preserve results)
# workflow.clear_state()
# print(f"State after clear: {workflow.get_all_state()}")