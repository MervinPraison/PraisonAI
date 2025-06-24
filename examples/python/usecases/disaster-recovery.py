from praisonaiagents import Agent, Task, PraisonAIAgents
import time
from typing import Dict, List
import asyncio

# Utility Functions
def check_network_status():
    """Simulates network connectivity check across different channels"""
    return {
        "main_network": int(time.time()) % 2 == 0,
        "backup_network": int(time.time()) % 3 == 0,
        "mesh_network": True,
        "satellite_link": int(time.time()) % 4 == 0,
        "cellular_network": int(time.time()) % 2 == 1
    }

def assess_emergency_level():
    """Evaluates emergency severity level"""
    levels = [
        {
            "severity": "critical",
            "affected_areas": ["downtown", "industrial_zone"],
            "population_impact": 50000,
            "infrastructure_damage": "severe"
        },
        {
            "severity": "high",
            "affected_areas": ["residential_zone"],
            "population_impact": 25000,
            "infrastructure_damage": "moderate"
        },
        {
            "severity": "medium",
            "affected_areas": ["suburban_area"],
            "population_impact": 10000,
            "infrastructure_damage": "light"
        }
    ]
    return levels[int(time.time()) % 3]

def assess_resources():
    """Assesses available emergency resources"""
    return {
        "medical": {
            "ambulances": 20 - (int(time.time()) % 5),
            "field_hospitals": 3,
            "medical_teams": 15 - (int(time.time()) % 3),
            "supplies": {
                "availability": 75,
                "distribution_centers": ["central", "north", "south"],
                "critical_items": ["medications", "blood_supplies", "emergency_kits"]
            }
        },
        "fire_rescue": {
            "fire_trucks": 15 - (int(time.time()) % 4),
            "rescue_teams": 10,
            "equipment": {
                "availability": 85,
                "locations": ["main_station", "sub_stations"],
                "critical_items": ["breathing_apparatus", "rescue_tools"]
            }
        },
        "law_enforcement": {
            "patrol_units": 30 - (int(time.time()) % 6),
            "special_units": 5,
            "equipment": {
                "availability": 90,
                "distribution": "citywide",
                "critical_items": ["communication_devices", "crowd_control"]
            }
        },
        "utilities": {
            "power_crews": 8,
            "water_teams": 6,
            "emergency_generators": 12 - (int(time.time()) % 4),
            "water_supplies": {
                "availability": 70,
                "distribution_points": ["north", "south", "east", "west"]
            }
        }
    }

def prioritize_needs(emergency: Dict, resources: Dict):
    """Determines priority of resource allocation"""
    priorities = []
    
    # Calculate medical priorities
    if emergency["severity"] == "critical":
        medical_priority = {
            "type": "medical",
            "urgency": "immediate",
            "required_resources": {
                "ambulances": min(10, resources["medical"]["ambulances"]),
                "medical_teams": min(8, resources["medical"]["medical_teams"])
            }
        }
        priorities.append(medical_priority)
    
    # Calculate rescue priorities
    if emergency["infrastructure_damage"] in ["severe", "moderate"]:
        rescue_priority = {
            "type": "fire_rescue",
            "urgency": "high",
            "required_resources": {
                "fire_trucks": min(5, resources["fire_rescue"]["fire_trucks"]),
                "rescue_teams": min(4, resources["fire_rescue"]["rescue_teams"])
            }
        }
        priorities.append(rescue_priority)
    
    # Calculate law enforcement priorities
    if emergency["population_impact"] > 20000:
        law_priority = {
            "type": "law_enforcement",
            "urgency": "high",
            "required_resources": {
                "patrol_units": min(15, resources["law_enforcement"]["patrol_units"]),
                "special_units": min(2, resources["law_enforcement"]["special_units"])
            }
        }
        priorities.append(law_priority)
    
    return priorities

def generate_distribution_plan(priorities: List[Dict]):
    """Creates resource distribution and deployment plan"""
    plan = {
        "immediate_actions": [],
        "short_term_actions": [],
        "coordination_points": []
    }
    
    for priority in priorities:
        if priority["urgency"] == "immediate":
            plan["immediate_actions"].append({
                "type": priority["type"],
                "resources": priority["required_resources"],
                "deployment_time": "immediate",
                "coordination": "central_command"
            })
        elif priority["urgency"] == "high":
            plan["short_term_actions"].append({
                "type": priority["type"],
                "resources": priority["required_resources"],
                "deployment_time": "within_1_hour",
                "coordination": "local_command"
            })
            
    # Add coordination points
    plan["coordination_points"] = [
        {
            "location": "central_command",
            "coordinates": {"lat": 34.0522, "lon": -118.2437},
            "communication_channels": ["radio", "satellite", "mesh_network"]
        },
        {
            "location": "mobile_command_1",
            "coordinates": {"lat": 34.0622, "lon": -118.2537},
            "communication_channels": ["radio", "mesh_network"]
        }
    ]
    
    return plan

def execute_distribution(plan: Dict):
    """Simulates the execution of the distribution plan"""
    execution_results = {
        "status": "in_progress",
        "completed_actions": [],
        "pending_actions": [],
        "resource_updates": {}
    }
    
    # Simulate immediate actions execution
    for action in plan["immediate_actions"]:
        success_rate = 0.9 if action["deployment_time"] == "immediate" else 0.95
        if time.time() % 10 > (1 - success_rate) * 10:
            execution_results["completed_actions"].append({
                "action": action,
                "status": "completed",
                "completion_time": time.time()
            })
        else:
            execution_results["pending_actions"].append({
                "action": action,
                "status": "delayed",
                "estimated_delay": "30_minutes"
            })
    
    # Update resource status
    execution_results["resource_updates"] = {
        "medical_units_deployed": len([a for a in execution_results["completed_actions"] 
                                     if a["action"]["type"] == "medical"]),
        "rescue_units_deployed": len([a for a in execution_results["completed_actions"] 
                                    if a["action"]["type"] == "fire_rescue"]),
        "coordination_status": "operational"
    }
    
    return execution_results

def monitor_effectiveness(execution_results: Dict):
    """Monitors the effectiveness of the response"""
    monitoring = {
        "response_metrics": {
            "deployment_speed": calculate_deployment_speed(execution_results),
            "resource_utilization": calculate_resource_utilization(execution_results),
            "coordination_efficiency": calculate_coordination_efficiency(execution_results)
        },
        "areas_for_improvement": identify_improvements(execution_results),
        "real_time_updates": generate_updates(execution_results)
    }
    return monitoring

def calculate_deployment_speed(results: Dict) -> float:
    """Calculates deployment speed efficiency"""
    completed = len(results["completed_actions"])
    total = completed + len(results["pending_actions"])
    return (completed / total) * 100 if total > 0 else 0

def calculate_resource_utilization(results: Dict) -> float:
    """Calculates resource utilization efficiency"""
    return 85.0 + (time.time() % 10)  # Simulated value

def calculate_coordination_efficiency(results: Dict) -> float:
    """Calculates coordination efficiency"""
    return 90.0 + (time.time() % 5)  # Simulated value

def identify_improvements(results: Dict) -> List[Dict]:
    """Identifies areas for improvement"""
    return [
        {
            "area": "resource_deployment",
            "suggestion": "optimize_routes",
            "priority": "high" if len(results["pending_actions"]) > 2 else "medium"
        },
        {
            "area": "coordination",
            "suggestion": "enhance_communication_protocols",
            "priority": "medium"
        }
    ]

def generate_updates(results: Dict) -> List[Dict]:
    """Generates real-time status updates"""
    return [
        {
            "timestamp": time.time(),
            "type": "status_update",
            "content": f"Deployed {len(results['completed_actions'])} units"
        },
        {
            "timestamp": time.time(),
            "type": "resource_update",
            "content": f"Resource utilization at {calculate_resource_utilization(results)}%"
        }
    ]

# Create specialized agents
network_monitor = Agent(
    name="Network Monitor",
    role="Network Status",
    goal="Monitor network connectivity",
    instructions="Track network status across all channels",
    tools=[check_network_status]
)

emergency_assessor = Agent(
    name="Emergency Assessor",
    role="Emergency Assessment",
    goal="Assess emergency situation",
    instructions="Evaluate emergency severity and impact",
    tools=[assess_emergency_level]
)

resource_assessor = Agent(
    name="Resource Assessor",
    role="Resource Assessment",
    goal="Assess available resources",
    instructions="Monitor and assess resource availability",
    tools=[assess_resources]
)

priority_analyzer = Agent(
    name="Priority Analyzer",
    role="Need Prioritization",
    goal="Prioritize resource needs",
    instructions="Analyze and prioritize resource requirements",
    tools=[prioritize_needs]
)

distribution_planner = Agent(
    name="Distribution Planner",
    role="Plan Generation",
    goal="Generate distribution plans",
    instructions="Create efficient resource distribution plans",
    tools=[generate_distribution_plan]
)

execution_manager = Agent(
    name="Execution Manager",
    role="Plan Execution",
    goal="Execute distribution plan",
    instructions="Manage and execute resource distribution",
    tools=[execute_distribution]
)

effectiveness_monitor = Agent(
    name="Effectiveness Monitor",
    role="Response Monitoring",
    goal="Monitor response effectiveness",
    instructions="Track and analyze response effectiveness",
    tools=[monitor_effectiveness]
)

# Create workflow tasks
network_task = Task(
    name="check_network",
    description="Check network status",
    expected_output="Network connectivity status",
    agent=network_monitor,
    is_start=True,
    task_type="decision",
    condition={
        "True": ["assess_emergency"],  # Proceed if any network is available
        "False": ""  # Exit if no network available
    }
)

emergency_task = Task(
    name="assess_emergency",
    description="Assess emergency situation",
    expected_output="Emergency assessment",
    agent=emergency_assessor,
    next_tasks=["assess_resources"]
)

resource_task = Task(
    name="assess_resources",
    description="Assess resource availability",
    expected_output="Resource assessment",
    agent=resource_assessor,
    next_tasks=["analyze_priorities"]
)

priority_task = Task(
    name="analyze_priorities",
    description="Analyze resource priorities",
    expected_output="Prioritized needs",
    agent=priority_analyzer,
    context=[emergency_task, resource_task],
    next_tasks=["plan_distribution"]
)

planning_task = Task(
    name="plan_distribution",
    description="Plan resource distribution",
    expected_output="Distribution plan",
    agent=distribution_planner,
    next_tasks=["execute_distribution"]
)

execution_task = Task(
    name="execute_distribution",
    description="Execute distribution plan",
    expected_output="Execution results",
    agent=execution_manager,
    next_tasks=["monitor_effectiveness"]
)

monitoring_task = Task(
    name="monitor_effectiveness",
    description="Monitor response effectiveness",
    expected_output="Effectiveness analysis",
    agent=effectiveness_monitor,
    task_type="decision",
    condition={
        "success": ["assess_emergency"],  # Continue monitoring if successful
        "needs_improvement": ["plan_distribution"],  # Replan if improvements needed
        "critical_issues": ["assess_resources"]  # Reassess resources if critical issues
    }
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[network_monitor, emergency_assessor, resource_assessor,
            priority_analyzer, distribution_planner, execution_manager,
            effectiveness_monitor],
    tasks=[network_task, emergency_task, resource_task,
           priority_task, planning_task, execution_task,
           monitoring_task],
    process="workflow",
    verbose=True
)

async def main():
    print("\nStarting Disaster Recovery Network Workflow...")
    print("=" * 50)
    
    # Run workflow
    results = await workflow.astart()
    
    # Print results
    print("\nDisaster Recovery Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            print(f"\nTask: {task_id}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())