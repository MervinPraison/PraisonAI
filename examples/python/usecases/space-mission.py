from praisonaiagents import Agent, Task, PraisonAIAgents
import time
from typing import Dict, List
import asyncio

def analyze_mission_parameters():
    """Simulates mission parameter analysis"""
    parameters = {
        "duration": 180,  # days
        "crew_size": 4,
        "orbital_parameters": {
            "altitude": 400,  # km
            "inclination": 51.6,  # degrees
            "period": 92.68  # minutes
        },
        "mission_objectives": [
            "scientific_research",
            "satellite_deployment",
            "space_station_maintenance"
        ]
    }
    return parameters

def calculate_resource_requirements(params: Dict):
    """Calculates required resources"""
    requirements = {
        "life_support": {
            "oxygen": params["duration"] * params["crew_size"] * 0.84,  # kg
            "water": params["duration"] * params["crew_size"] * 2.5,  # liters
            "food": params["duration"] * params["crew_size"] * 1.8   # kg
        },
        "power": {
            "daily_consumption": 30 + (params["crew_size"] * 5),  # kWh
            "peak_demand": 45 + (params["crew_size"] * 8),  # kW
            "backup_capacity": 72  # hours
        },
        "propellant": {
            "main_engine": 2000,  # kg
            "attitude_control": 500,  # kg
            "reserve": 300  # kg
        }
    }
    return requirements

def plan_contingencies(requirements: Dict):
    """Plans contingency scenarios"""
    contingencies = [
        {
            "scenario": "power_failure",
            "probability": 0.05,
            "impact": "critical",
            "resources_needed": {
                "backup_power": requirements["power"]["daily_consumption"] * 3,
                "repair_equipment": ["solar_panel_kit", "power_distribution_unit"]
            }
        },
        {
            "scenario": "life_support_malfunction",
            "probability": 0.03,
            "impact": "severe",
            "resources_needed": {
                "oxygen_reserve": requirements["life_support"]["oxygen"] * 0.2,
                "repair_parts": ["filter_system", "pressure_regulators"]
            }
        }
    ]
    return contingencies[int(time.time()) % 2]

def optimize_allocation(requirements: Dict, contingencies: Dict):
    """Optimizes resource allocation"""
    allocation = {
        "primary_resources": {
            "life_support": {
                "nominal": requirements["life_support"],
                "buffer": 0.15  # 15% buffer
            },
            "power": {
                "nominal": requirements["power"],
                "buffer": 0.2   # 20% buffer
            }
        },
        "contingency_resources": {
            "type": contingencies["scenario"],
            "allocation": contingencies["resources_needed"],
            "priority": "high" if contingencies["impact"] == "critical" else "medium"
        }
    }
    return allocation

def simulate_mission_scenarios(allocation: Dict):
    """Simulates various mission scenarios"""
    scenarios = {
        "nominal_operations": {
            "success_rate": 0.95,
            "resource_utilization": 0.85,
            "efficiency_rating": 0.9
        },
        "emergency_scenarios": [
            {
                "type": "power_reduction",
                "duration": 48,  # hours
                "impact": "moderate",
                "resolution_success": 0.88
            },
            {
                "type": "life_support_adjustment",
                "duration": 24,  # hours
                "impact": "minor",
                "resolution_success": 0.92
            }
        ]
    }
    return scenarios

# Create specialized agents
mission_analyzer = Agent(
    name="Mission Analyzer",
    role="Mission Analysis",
    goal="Analyze mission parameters",
    instructions="Evaluate mission requirements and constraints",
    tools=[analyze_mission_parameters]
)

resource_calculator = Agent(
    name="Resource Calculator",
    role="Resource Calculation",
    goal="Calculate resource requirements",
    instructions="Determine required resources for mission",
    tools=[calculate_resource_requirements]
)

contingency_planner = Agent(
    name="Contingency Planner",
    role="Contingency Planning",
    goal="Plan for contingencies",
    instructions="Develop contingency scenarios and plans",
    tools=[plan_contingencies]
)

resource_optimizer = Agent(
    name="Resource Optimizer",
    role="Resource Optimization",
    goal="Optimize resource allocation",
    instructions="Optimize resource distribution",
    tools=[optimize_allocation]
)

scenario_simulator = Agent(
    name="Scenario Simulator",
    role="Scenario Simulation",
    goal="Simulate mission scenarios",
    instructions="Simulate various mission scenarios",
    tools=[simulate_mission_scenarios]
)

# Create workflow tasks
mission_task = Task(
    name="analyze_mission",
    description="Analyze mission parameters",
    expected_output="Mission parameters",
    agent=mission_analyzer,
    is_start=True,
    next_tasks=["calculate_resources"]
)

resource_task = Task(
    name="calculate_resources",
    description="Calculate resource requirements",
    expected_output="Resource requirements",
    agent=resource_calculator,
    next_tasks=["plan_contingencies"]
)

contingency_task = Task(
    name="plan_contingencies",
    description="Plan contingencies",
    expected_output="Contingency plans",
    agent=contingency_planner,
    context=[resource_task],
    next_tasks=["optimize_resources"]
)

optimization_task = Task(
    name="optimize_resources",
    description="Optimize resource allocation",
    expected_output="Resource allocation",
    agent=resource_optimizer,
    context=[resource_task, contingency_task],
    next_tasks=["simulate_scenarios"]
)

simulation_task = Task(
    name="simulate_scenarios",
    description="Simulate scenarios",
    expected_output="Simulation results",
    agent=scenario_simulator,
    task_type="decision",
    condition={
        "nominal_operations": "",  # End workflow if nominal
        "emergency_scenarios": ["optimize_resources"]  # Reoptimize if emergency
    }
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[mission_analyzer, resource_calculator, contingency_planner,
            resource_optimizer, scenario_simulator],
    tasks=[mission_task, resource_task, contingency_task,
           optimization_task, simulation_task],
    process="workflow",
    verbose=True
)

async def main():
    print("\nStarting Space Mission Resource Optimization Workflow...")
    print("=" * 50)
    
    # Run workflow
    results = await workflow.astart()
    
    # Print results
    print("\nResource Optimization Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            print(f"\nTask: {task_id}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())