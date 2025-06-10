"""
State Management Example for PraisonAI Agents
============================================

This example demonstrates various state management features:
1. Workflow-level state management
2. Session-level state persistence
3. State sharing between agents
4. State-based decision making
"""

from praisonaiagents import Agent, Task, PraisonAIAgents, Session
from typing import Dict, Any
import json
import time

# Create a session for persistent state
session = Session(session_id="state_demo_session", user_id="demo_user")

# Tool functions that interact with state
def initialize_project_state() -> Dict[str, Any]:
    """Initialize project state with default values"""
    # Access workflow state from global workflow variable
    workflow.set_state("project_name", "AI Assistant Project")
    workflow.set_state("stage", "planning")
    workflow.set_state("features", [])
    workflow.set_state("completed_features", [])
    workflow.set_state("budget", 100000)
    workflow.set_state("spent", 0)
    
    # Also save to session for persistence
    session.set_state("last_project", "AI Assistant Project")
    session.set_state("total_projects", session.get_state("total_projects", 0) + 1)
    
    return {
        "status": "initialized",
        "project_name": workflow.get_state("project_name"),
        "budget": workflow.get_state("budget"),
        "session_projects": session.get_state("total_projects")
    }

def add_feature_to_project(feature_name: str, estimated_cost: int) -> Dict[str, Any]:
    """Add a feature to the project and update state"""
    features = workflow.get_state("features", [])
    budget = workflow.get_state("budget", 0)
    spent = workflow.get_state("spent", 0)
    
    if spent + estimated_cost > budget:
        return {
            "status": "rejected",
            "reason": "over_budget",
            "available_budget": budget - spent
        }
    
    feature = {
        "name": feature_name,
        "cost": estimated_cost,
        "status": "planned"
    }
    
    features.append(feature)
    workflow.set_state("features", features)
    workflow.set_state("spent", spent + estimated_cost)
    
    return {
        "status": "added",
        "feature": feature,
        "total_features": len(features),
        "remaining_budget": budget - (spent + estimated_cost)
    }

def implement_next_feature() -> Dict[str, Any]:
    """Implement the next planned feature"""
    features = workflow.get_state("features", [])
    completed = workflow.get_state("completed_features", [])
    
    # Find next planned feature
    next_feature = None
    for i, feature in enumerate(features):
        if feature["status"] == "planned":
            next_feature = feature
            next_feature["status"] = "completed"
            features[i] = next_feature
            break
    
    if not next_feature:
        workflow.set_state("stage", "completed")
        return {
            "status": "no_more_features",
            "completed_count": len(completed),
            "stage": "completed"
        }
    
    completed.append(next_feature["name"])
    workflow.set_state("features", features)
    workflow.set_state("completed_features", completed)
    workflow.set_state("stage", "implementing")
    
    # Update session state
    session.set_state("last_implemented_feature", next_feature["name"])
    
    return {
        "status": "implemented",
        "feature": next_feature,
        "completed_count": len(completed),
        "remaining_count": sum(1 for f in features if f["status"] == "planned")
    }

def check_project_status() -> Dict[str, Any]:
    """Check the current project status from state"""
    return {
        "project_name": workflow.get_state("project_name"),
        "stage": workflow.get_state("stage"),
        "total_features": len(workflow.get_state("features", [])),
        "completed_features": len(workflow.get_state("completed_features", [])),
        "budget": workflow.get_state("budget"),
        "spent": workflow.get_state("spent"),
        "remaining": workflow.get_state("budget", 0) - workflow.get_state("spent", 0),
        "has_more_features": workflow.has_state("features") and any(
            f["status"] == "planned" for f in workflow.get_state("features", [])
        ),
        "all_state": workflow.get_all_state()
    }

def retrieve_session_history() -> Dict[str, Any]:
    """Retrieve historical data from session state"""
    session_state = session.restore_state()
    return {
        "total_projects": session.get_state("total_projects", 0),
        "last_project": session.get_state("last_project"),
        "last_implemented_feature": session.get_state("last_implemented_feature"),
        "session_id": session.session_id,
        "full_session_state": session_state
    }

# Create agents with state-aware tools
project_manager = Agent(
    name="ProjectManager",
    role="Project planning and management",
    goal="Initialize and manage project state effectively",
    backstory="Experienced project manager who tracks all project details",
    tools=[initialize_project_state, add_feature_to_project, check_project_status],
    llm="gpt-4o-mini"
)

developer = Agent(
    name="Developer",
    role="Feature implementation",
    goal="Implement features based on project state",
    backstory="Senior developer who implements features systematically",
    tools=[implement_next_feature, check_project_status],
    llm="gpt-4o-mini"
)

analyst = Agent(
    name="Analyst",
    role="Project analysis and reporting",
    goal="Analyze project state and provide insights",
    backstory="Data analyst who provides comprehensive project reports",
    tools=[check_project_status, retrieve_session_history],
    llm="gpt-4o-mini"
)

# Create tasks that utilize state
init_task = Task(
    name="initialize_project",
    description="Initialize the project state with default values",
    expected_output="Project initialization status with budget and name",
    agent=project_manager,
    tools=[initialize_project_state]
)

plan_features_task = Task(
    name="plan_features",
    description="""Add the following features to the project:
    1. User Authentication (cost: 15000)
    2. Data Analytics Dashboard (cost: 25000)
    3. API Integration (cost: 20000)
    4. Mobile App Support (cost: 30000)
    5. Advanced Reporting (cost: 20000)
    
    Use the add_feature_to_project tool for each feature.""",
    expected_output="List of features added with budget status",
    agent=project_manager,
    tools=[add_feature_to_project],
    context=[init_task]
)

implement_features_task = Task(
    name="implement_features",
    description="""Implement all planned features one by one.
    Use implement_next_feature tool repeatedly until all features are completed.
    Check project status after each implementation.""",
    expected_output="Implementation progress and final status",
    agent=developer,
    tools=[implement_next_feature, check_project_status],
    context=[plan_features_task]
)

analyze_project_task = Task(
    name="analyze_project",
    description="""Provide a comprehensive analysis of the project including:
    1. Current project state and completion status
    2. Budget utilization
    3. Historical session data
    4. Summary of all state information""",
    expected_output="Detailed project analysis report",
    agent=analyst,
    tools=[check_project_status, retrieve_session_history],
    context=[implement_features_task]
)

# Create workflow with state management
workflow = PraisonAIAgents(
    agents=[project_manager, developer, analyst],
    tasks=[init_task, plan_features_task, implement_features_task, analyze_project_task],
    verbose=1,
    process="sequential"
)

# Demonstrate state operations before starting
print("\n=== State Management Demo ===")
print("\n1. Initial State Check:")
print(f"   Has 'project_name' state: {workflow.has_state('project_name')}")
print(f"   All state: {workflow.get_all_state()}")

# Run the workflow
print("\n2. Running Workflow...")
result = workflow.start()

# Demonstrate state after workflow
print("\n3. Final State Check:")
print(f"   Project Name: {workflow.get_state('project_name')}")
print(f"   Stage: {workflow.get_state('stage')}")
print(f"   Features: {len(workflow.get_state('features', []))}")
print(f"   Completed: {workflow.get_state('completed_features', [])}")
print(f"   Budget Spent: ${workflow.get_state('spent')}/{workflow.get_state('budget')}")

# Test state persistence
print("\n4. Session State Persistence:")
print(f"   Total Projects (this session): {session.get_state('total_projects')}")
print(f"   Last Project: {session.get_state('last_project')}")

# Save session state
session.save_state({"workflow_completed": True, "timestamp": time.time()})

# Demonstrate state update and deletion
print("\n5. State Manipulation:")
workflow.update_state({"additional_notes": "Project completed successfully"})
print(f"   After update: {workflow.get_state('additional_notes')}")

workflow.delete_state("additional_notes")
print(f"   After delete, has 'additional_notes': {workflow.has_state('additional_notes')}")

# Clear all workflow state (optional)
# workflow.clear_state()
# print(f"   After clear: {workflow.get_all_state()}")

print("\n=== State Management Demo Complete ===")