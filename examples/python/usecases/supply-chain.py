from praisonaiagents import Agent, Task, PraisonAIAgents
import time
from typing import Dict, List

def monitor_global_events():
    """Simulates monitoring of global events"""
    events = [
        {"type": "natural_disaster", "severity": "high", "region": "Asia"},
        {"type": "political_unrest", "severity": "medium", "region": "Europe"},
        {"type": "economic_crisis", "severity": "critical", "region": "Americas"}
    ]
    return events[int(time.time()) % 3]

def analyze_supply_impact(event: Dict):
    """Simulates impact analysis on supply chain"""
    impact_matrix = {
        "natural_disaster": {"delay": "severe", "cost": "high", "risk_level": 9},
        "political_unrest": {"delay": "moderate", "cost": "medium", "risk_level": 6},
        "economic_crisis": {"delay": "significant", "cost": "extreme", "risk_level": 8}
    }
    return impact_matrix.get(event["type"])

def generate_mitigation_strategies(impact: Dict):
    """Simulates generation of mitigation strategies"""
    strategies = {
        "severe": ["activate_backup_suppliers", "emergency_logistics_routing"],
        "moderate": ["increase_buffer_stock", "alternative_transport"],
        "significant": ["diversify_suppliers", "hedge_currency_risks"]
    }
    return strategies.get(impact["delay"], ["review_supply_chain"])

# Create specialized agents
monitor_agent = Agent(
    name="Global Monitor",
    role="Event Monitoring",
    goal="Monitor and identify global events affecting supply chain",
    instructions="Track and report significant global events",
    tools=[monitor_global_events]
)

impact_analyzer = Agent(
    name="Impact Analyzer",
    role="Impact Assessment",
    goal="Analyze event impact on supply chain",
    instructions="Assess potential disruptions and risks",
    tools=[analyze_supply_impact]
)

strategy_generator = Agent(
    name="Strategy Generator",
    role="Strategy Development",
    goal="Generate mitigation strategies",
    instructions="Develop strategies to address identified risks",
    tools=[generate_mitigation_strategies]
)

# Create workflow tasks
monitoring_task = Task(
    name="monitor_events",
    description="Monitor global events affecting supply chain",
    expected_output="Identified global events",
    agent=monitor_agent,
    is_start=True,
    task_type="decision",
    condition={
        "high": ["analyze_impact"],
        "medium": ["analyze_impact"],
        "critical": ["analyze_impact"]
    }
)

impact_task = Task(
    name="analyze_impact",
    description="Analyze impact on supply chain",
    expected_output="Impact assessment",
    agent=impact_analyzer,
    next_tasks=["generate_strategies"]
)

strategy_task = Task(
    name="generate_strategies",
    description="Generate mitigation strategies",
    expected_output="List of mitigation strategies",
    agent=strategy_generator,
    context=[monitoring_task, impact_task]
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[monitor_agent, impact_analyzer, strategy_generator],
    tasks=[monitoring_task, impact_task, strategy_task],
    process="workflow",
    verbose=True
)

def main():
    print("\nStarting Supply Chain Risk Management Workflow...")
    print("=" * 50)
    
    # Run workflow
    results = workflow.start()
    
    # Print results
    print("\nRisk Management Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            print(f"\nTask: {task_id}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    main()