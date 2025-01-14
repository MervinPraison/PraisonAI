from praisonaiagents import Agent, Task, PraisonAIAgents
import time
from typing import Dict, List

def monitor_utilities():
    """Simulates utility usage monitoring"""
    readings = {
        "power": {
            "consumption": int(time.time()) % 1000,
            "peak_hours": ["morning", "evening"],
            "grid_load": "medium"
        },
        "water": {
            "consumption": int(time.time()) % 500,
            "pressure": "normal",
            "quality": "good"
        },
        "traffic": {
            "congestion": "high",
            "peak_zones": ["downtown", "industrial"],
            "incidents": 2
        }
    }
    return readings

def analyze_patterns():
    """Simulates usage pattern analysis"""
    patterns = [
        {"type": "daily_cycle", "confidence": 0.85, "trend": "increasing"},
        {"type": "weekly_cycle", "confidence": 0.92, "trend": "stable"},
        {"type": "seasonal", "confidence": 0.78, "trend": "decreasing"}
    ]
    return patterns[int(time.time()) % 3]

def optimize_resources(readings: Dict, patterns: Dict):
    """Simulates resource optimization"""
    optimizations = {
        "power": {
            "action": "load_balancing",
            "target_zones": ["residential", "commercial"],
            "expected_savings": "15%"
        },
        "water": {
            "action": "pressure_adjustment",
            "target_zones": ["industrial"],
            "expected_savings": "8%"
        },
        "traffic": {
            "action": "signal_timing",
            "target_zones": ["downtown"],
            "expected_impact": "20% reduction"
        }
    }
    return optimizations

def implement_changes(optimizations: Dict):
    """Simulates implementation of optimization changes"""
    success_rates = {
        "load_balancing": 0.95,
        "pressure_adjustment": 0.88,
        "signal_timing": 0.85
    }
    return {"status": "implemented", "success_rate": success_rates[optimizations["power"]["action"]]}

def monitor_feedback():
    """Simulates monitoring of optimization feedback"""
    feedbacks = ["positive", "neutral", "negative"]
    return feedbacks[int(time.time()) % 3]

# Create specialized agents
utility_monitor = Agent(
    name="Utility Monitor",
    role="Resource Monitoring",
    goal="Monitor city utility usage",
    instructions="Track and report utility consumption patterns",
    tools=[monitor_utilities]
)

pattern_analyzer = Agent(
    name="Pattern Analyzer",
    role="Pattern Analysis",
    goal="Analyze usage patterns",
    instructions="Identify and analyze resource usage patterns",
    tools=[analyze_patterns]
)

resource_optimizer = Agent(
    name="Resource Optimizer",
    role="Resource Optimization",
    goal="Optimize resource allocation",
    instructions="Generate resource optimization strategies",
    tools=[optimize_resources]
)

implementation_agent = Agent(
    name="Implementation Agent",
    role="Change Implementation",
    goal="Implement optimization changes",
    instructions="Execute optimization strategies",
    tools=[implement_changes]
)

feedback_monitor = Agent(
    name="Feedback Monitor",
    role="Feedback Monitoring",
    goal="Monitor optimization results",
    instructions="Track and analyze optimization feedback",
    tools=[monitor_feedback]
)

# Create workflow tasks
monitoring_task = Task(
    name="monitor_utilities",
    description="Monitor utility usage",
    expected_output="Current utility readings",
    agent=utility_monitor,
    is_start=True,
    next_tasks=["analyze_patterns"]
)

pattern_task = Task(
    name="analyze_patterns",
    description="Analyze usage patterns",
    expected_output="Usage patterns analysis",
    agent=pattern_analyzer,
    next_tasks=["optimize_resources"]
)

optimization_task = Task(
    name="optimize_resources",
    description="Generate optimization strategies",
    expected_output="Resource optimization plans",
    agent=resource_optimizer,
    next_tasks=["implement_changes"],
    context=[monitoring_task, pattern_task]
)

implementation_task = Task(
    name="implement_changes",
    description="Implement optimization changes",
    expected_output="Implementation status",
    agent=implementation_agent,
    next_tasks=["monitor_feedback"]
)

feedback_task = Task(
    name="monitor_feedback",
    description="Monitor optimization feedback",
    expected_output="Optimization feedback",
    agent=feedback_monitor,
    task_type="decision",
    condition={
        "negative": ["monitor_utilities"],  # Start over if negative feedback
        "neutral": ["optimize_resources"],  # Adjust optimization if neutral
        "positive": ""  # End workflow if positive
    }
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[utility_monitor, pattern_analyzer, resource_optimizer, 
            implementation_agent, feedback_monitor],
    tasks=[monitoring_task, pattern_task, optimization_task, 
           implementation_task, feedback_task],
    process="workflow",
    verbose=True
)

def main():
    print("\nStarting Smart City Resource Optimization Workflow...")
    print("=" * 50)
    
    # Run workflow
    results = workflow.start()
    
    # Print results
    print("\nOptimization Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            print(f"\nTask: {task_id}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    main()