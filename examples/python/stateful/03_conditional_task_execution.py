#!/usr/bin/env python3
"""
Conditional Task Execution with State Example
============================================

This example demonstrates how to use state to control task flow with conditional execution.
Tasks can make decisions based on state values to determine which tasks execute next.

Run this example:
    python 03_conditional_task_execution.py
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
import json
from typing import Dict, Any


def check_budget_status() -> str:
    """Check budget and return decision based on spending"""
    budget = workflow.get_state("budget", 0)
    spent = workflow.get_state("spent", 0)
    
    if budget == 0:
        return "no_budget"
    
    percentage_spent = (spent / budget) * 100
    
    # Store budget analysis in state
    workflow.set_state("budget_analysis", {
        "budget": budget,
        "spent": spent,
        "remaining": budget - spent,
        "percentage_spent": percentage_spent
    })
    
    # Return decision based on budget status
    if percentage_spent >= 90:
        workflow.set_state("budget_alert", "critical")
        return "over_budget"
    elif percentage_spent >= 70:
        workflow.set_state("budget_alert", "warning")
        return "within_budget"
    else:
        workflow.set_state("budget_alert", "healthy")
        return "under_budget"


def reduce_costs() -> str:
    """Implement cost reduction measures"""
    current_spent = workflow.get_state("spent", 0)
    
    # Simulate cost reduction
    savings = current_spent * 0.15  # 15% reduction
    new_spent = current_spent - savings
    workflow.set_state("spent", new_spent)
    workflow.set_state("cost_reduction_applied", True)
    workflow.set_state("savings_achieved", savings)
    
    # Log action
    workflow.append_to_state("actions_taken", {
        "action": "cost_reduction",
        "savings": savings,
        "new_spent": new_spent
    })
    
    return f"Cost reduction implemented. Saved ${savings:,.2f}. New spending: ${new_spent:,.2f}"


def continue_development() -> str:
    """Continue with normal development"""
    # Add new features
    features = workflow.get_state("features", [])
    new_features = ["Feature A", "Feature B"]
    features.extend(new_features)
    workflow.set_state("features", features)
    
    # Update development status
    workflow.set_state("development_status", "active")
    
    # Log action
    workflow.append_to_state("actions_taken", {
        "action": "continue_development",
        "features_added": new_features
    })
    
    return f"Continuing development. Added features: {', '.join(new_features)}"


def expand_features() -> str:
    """Expand project with additional features"""
    # Add premium features
    features = workflow.get_state("features", [])
    premium_features = ["Premium Feature X", "Premium Feature Y", "Premium Feature Z"]
    features.extend(premium_features)
    workflow.set_state("features", features)
    
    # Increase budget allocation
    additional_budget = 20000
    current_budget = workflow.get_state("budget", 0)
    workflow.set_state("budget", current_budget + additional_budget)
    
    # Update status
    workflow.set_state("development_status", "expanded")
    
    # Log action
    workflow.append_to_state("actions_taken", {
        "action": "expand_features",
        "premium_features_added": premium_features,
        "budget_increased": additional_budget
    })
    
    return f"Expanded project scope. Added premium features and increased budget by ${additional_budget:,}"


def check_performance() -> str:
    """Check system performance and return status"""
    # Simulate performance metrics
    cpu_usage = workflow.get_state("cpu_usage", 45)  # percentage
    memory_usage = workflow.get_state("memory_usage", 60)  # percentage
    response_time = workflow.get_state("response_time", 200)  # milliseconds
    
    # Store performance metrics
    workflow.set_state("performance_metrics", {
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "response_time": response_time
    })
    
    # Determine performance status
    if cpu_usage > 80 or memory_usage > 85 or response_time > 500:
        return "poor_performance"
    elif cpu_usage > 60 or memory_usage > 70 or response_time > 300:
        return "moderate_performance"
    else:
        return "good_performance"


def optimize_performance() -> str:
    """Optimize system performance"""
    # Simulate optimization
    workflow.set_state("cpu_usage", 40)
    workflow.set_state("memory_usage", 50)
    workflow.set_state("response_time", 150)
    workflow.set_state("optimization_applied", True)
    
    # Log action
    workflow.append_to_state("actions_taken", {
        "action": "optimize_performance",
        "improvements": "Applied caching, code optimization, and resource cleanup"
    })
    
    return "Performance optimization completed. All metrics improved."


def scale_infrastructure() -> str:
    """Scale up infrastructure"""
    # Simulate scaling
    current_servers = workflow.get_state("server_count", 2)
    new_servers = current_servers + 2
    workflow.set_state("server_count", new_servers)
    workflow.set_state("infrastructure_scaled", True)
    
    # Log action
    workflow.append_to_state("actions_taken", {
        "action": "scale_infrastructure",
        "servers_added": 2,
        "total_servers": new_servers
    })
    
    return f"Infrastructure scaled. Added 2 servers. Total servers: {new_servers}"


def maintain_current_setup() -> str:
    """Maintain current setup without changes"""
    workflow.set_state("system_status", "stable")
    
    # Log action
    workflow.append_to_state("actions_taken", {
        "action": "maintain_current",
        "reason": "Performance is good, no changes needed"
    })
    
    return "System performing well. Maintaining current setup."


def generate_decision_report() -> str:
    """Generate report on all decisions made"""
    actions = workflow.get_state("actions_taken", [])
    budget_analysis = workflow.get_state("budget_analysis", {})
    performance_metrics = workflow.get_state("performance_metrics", {})
    
    report = """
    Decision Flow Report
    ===================
    
    Budget Analysis:
    """
    
    if budget_analysis:
        report += f"""
    - Budget: ${budget_analysis.get('budget', 0):,}
    - Spent: ${budget_analysis.get('spent', 0):,}
    - Remaining: ${budget_analysis.get('remaining', 0):,}
    - Percentage Spent: {budget_analysis.get('percentage_spent', 0):.1f}%
    - Alert Level: {workflow.get_state('budget_alert', 'unknown')}
    """
    
    report += "\n    Performance Metrics:\n"
    if performance_metrics:
        report += f"""
    - CPU Usage: {performance_metrics.get('cpu_usage', 0)}%
    - Memory Usage: {performance_metrics.get('memory_usage', 0)}%
    - Response Time: {performance_metrics.get('response_time', 0)}ms
    """
    
    report += "\n    Actions Taken:\n"
    for i, action in enumerate(actions, 1):
        report += f"    {i}. {action['action'].replace('_', ' ').title()}\n"
        for key, value in action.items():
            if key != 'action':
                report += f"       - {key}: {value}\n"
    
    # Add final state summary
    report += f"""
    
    Final State:
    - Features: {len(workflow.get_state('features', []))} total
    - Development Status: {workflow.get_state('development_status', 'unknown')}
    - System Status: {workflow.get_state('system_status', 'unknown')}
    """
    
    return report


# Create agents
finance_agent = Agent(
    name="FinanceAgent",
    role="Monitor budget and make financial decisions",
    goal="Ensure project stays within budget constraints",
    backstory="A financial expert who makes budget decisions",
    tools=[check_budget_status],
    llm="gpt-5-nano",
    verbose=True
)

cost_manager = Agent(
    name="CostManager",
    role="Implement cost reduction strategies",
    goal="Reduce costs when budget is tight",
    backstory="A cost optimization specialist",
    tools=[reduce_costs],
    llm="gpt-5-nano",
    verbose=True
)

development_agent = Agent(
    name="DevelopmentAgent",
    role="Manage feature development",
    goal="Develop features based on budget availability",
    backstory="A development manager who adapts to budget constraints",
    tools=[continue_development, expand_features],
    llm="gpt-5-nano",
    verbose=True
)

performance_agent = Agent(
    name="PerformanceAgent",
    role="Monitor and optimize system performance",
    goal="Ensure optimal system performance",
    backstory="A performance engineer",
    tools=[check_performance, optimize_performance, scale_infrastructure, maintain_current_setup],
    llm="gpt-5-nano",
    verbose=True
)

report_agent = Agent(
    name="ReportAgent",
    role="Generate comprehensive reports",
    goal="Document all decisions and actions taken",
    backstory="A reporting specialist",
    tools=[generate_decision_report],
    llm="gpt-5-nano",
    verbose=True
)

# Create conditional tasks
budget_decision_task = Task(
    name="budget_decision",
    description="Check current budget status and decide next action",
    expected_output="Budget status decision",
    agent=finance_agent,
    tools=[check_budget_status],
    task_type="decision",
    condition={
        "over_budget": ["cost_reduction_task"],
        "within_budget": ["continue_development_task"],
        "under_budget": ["expand_features_task"],
        "no_budget": ["report_task"]  # Skip to report if no budget
    }
)

cost_reduction_task = Task(
    name="cost_reduction_task",
    description="Implement cost reduction measures due to budget constraints",
    expected_output="Cost reduction confirmation",
    agent=cost_manager,
    tools=[reduce_costs],
    next_tasks=["performance_check_task"]
)

continue_development_task = Task(
    name="continue_development_task",
    description="Continue with planned development",
    expected_output="Development continuation confirmation",
    agent=development_agent,
    tools=[continue_development],
    next_tasks=["performance_check_task"]
)

expand_features_task = Task(
    name="expand_features_task",
    description="Expand project with additional premium features",
    expected_output="Feature expansion confirmation",
    agent=development_agent,
    tools=[expand_features],
    next_tasks=["performance_check_task"]
)

performance_check_task = Task(
    name="performance_check_task",
    description="Check system performance and decide on optimization needs",
    expected_output="Performance status decision",
    agent=performance_agent,
    tools=[check_performance],
    task_type="decision",
    condition={
        "poor_performance": ["optimize_performance_task"],
        "moderate_performance": ["scale_infrastructure_task"],
        "good_performance": ["maintain_setup_task"]
    }
)

optimize_performance_task = Task(
    name="optimize_performance_task",
    description="Optimize system performance due to poor metrics",
    expected_output="Performance optimization confirmation",
    agent=performance_agent,
    tools=[optimize_performance],
    next_tasks=["report_task"]
)

scale_infrastructure_task = Task(
    name="scale_infrastructure_task",
    description="Scale infrastructure to handle moderate load",
    expected_output="Infrastructure scaling confirmation",
    agent=performance_agent,
    tools=[scale_infrastructure],
    next_tasks=["report_task"]
)

maintain_setup_task = Task(
    name="maintain_setup_task",
    description="Maintain current setup as performance is good",
    expected_output="Setup maintenance confirmation",
    agent=performance_agent,
    tools=[maintain_current_setup],
    next_tasks=["report_task"]
)

report_task = Task(
    name="report_task",
    description="Generate comprehensive report of all decisions and actions",
    expected_output="Complete decision flow report",
    agent=report_agent,
    tools=[generate_decision_report]
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[finance_agent, cost_manager, development_agent, performance_agent, report_agent],
    tasks=[
        budget_decision_task,
        cost_reduction_task,
        continue_development_task,
        expand_features_task,
        performance_check_task,
        optimize_performance_task,
        scale_infrastructure_task,
        maintain_setup_task,
        report_task
    ],
    verbose=True,
    process="sequential"
)

# Test different scenarios by changing initial state
print("\n=== Scenario 1: Over Budget with Poor Performance ===")
workflow.set_state("budget", 100000)
workflow.set_state("spent", 92000)  # 92% spent - over budget
workflow.set_state("cpu_usage", 85)  # High CPU - poor performance
workflow.set_state("memory_usage", 88)
workflow.set_state("response_time", 600)
workflow.set_state("features", [])
workflow.set_state("actions_taken", [])

# Run workflow
result = workflow.start()

# To test other scenarios, uncomment and run:
"""
print("\n\n=== Scenario 2: Under Budget with Good Performance ===")
workflow.clear_state()
workflow.set_state("budget", 100000)
workflow.set_state("spent", 40000)  # 40% spent - under budget
workflow.set_state("cpu_usage", 35)  # Low usage - good performance
workflow.set_state("memory_usage", 45)
workflow.set_state("response_time", 150)
workflow.set_state("features", [])
workflow.set_state("actions_taken", [])
result = workflow.start()
"""