from praisonaiagents import Agent, Task, PraisonAIAgents
import time
from typing import Dict, List
import asyncio

def collect_environmental_data():
    """Simulates environmental data collection"""
    data = {
        "temperature": {
            "current": 25 + (time.time() % 10),
            "historical": [24, 25, 26, 24, 23],
            "trend": "increasing"
        },
        "humidity": {
            "current": 60 + (time.time() % 20),
            "historical": [65, 62, 58, 63, 61],
            "trend": "stable"
        },
        "air_quality": {
            "pm25": 35 + (time.time() % 15),
            "co2": 415 + (time.time() % 30),
            "trend": "deteriorating"
        }
    }
    return data

def analyze_urban_factors():
    """Simulates urban environment analysis"""
    factors = {
        "building_density": 75 + (time.time() % 20),
        "green_spaces": 25 + (time.time() % 10),
        "traffic_flow": {
            "peak_hours": [8, 17],
            "congestion_level": "high"
        },
        "heat_islands": [
            {"location": "downtown", "intensity": "high"},
            {"location": "industrial", "intensity": "medium"}
        ]
    }
    return factors

def model_microclimate(env_data: Dict, urban_factors: Dict):
    """Models microclimate conditions"""
    models = []
    locations = ["downtown", "residential", "industrial", "parks"]
    
    for location in locations:
        models.append({
            "location": location,
            "temperature_delta": 2 + (time.time() % 3),
            "air_quality_impact": "moderate" if "park" in location else "significant",
            "humidity_variation": 5 + (time.time() % 5)
        })
    return models

def predict_impacts(models: List[Dict]):
    """Predicts climate impacts"""
    predictions = []
    for model in models:
        predictions.append({
            "location": model["location"],
            "health_impact": "high" if model["air_quality_impact"] == "significant" else "medium",
            "energy_consumption": {
                "cooling_need": model["temperature_delta"] * 10,
                "trend": "increasing" if model["temperature_delta"] > 2.5 else "stable"
            },
            "livability_score": 70 - (model["temperature_delta"] * 5)
        })
    return predictions

def generate_adaptation_strategies(predictions: List[Dict]):
    """Generates adaptation strategies"""
    strategies = []
    for pred in predictions:
        if pred["health_impact"] == "high":
            strategies.append({
                "location": pred["location"],
                "actions": [
                    "increase_green_spaces",
                    "traffic_reduction",
                    "building_retrofitting"
                ],
                "priority": "immediate",
                "cost_estimate": "high"
            })
        else:
            strategies.append({
                "location": pred["location"],
                "actions": [
                    "tree_planting",
                    "cool_roofs"
                ],
                "priority": "medium",
                "cost_estimate": "moderate"
            })
    return strategies

# Create specialized agents
environmental_monitor = Agent(
    name="Environmental Monitor",
    role="Data Collection",
    goal="Collect environmental data",
    instructions="Monitor and collect climate data",
    tools=[collect_environmental_data]
)

urban_analyzer = Agent(
    name="Urban Analyzer",
    role="Urban Analysis",
    goal="Analyze urban environment",
    instructions="Assess urban factors affecting climate",
    tools=[analyze_urban_factors]
)

climate_modeler = Agent(
    name="Climate Modeler",
    role="Climate Modeling",
    goal="Model microclimate conditions",
    instructions="Create detailed climate models",
    tools=[model_microclimate]
)

impact_predictor = Agent(
    name="Impact Predictor",
    role="Impact Analysis",
    goal="Predict climate impacts",
    instructions="Assess potential climate impacts",
    tools=[predict_impacts]
)

strategy_generator = Agent(
    name="Strategy Generator",
    role="Strategy Development",
    goal="Generate adaptation strategies",
    instructions="Develop climate adaptation strategies",
    tools=[generate_adaptation_strategies]
)

# Create workflow tasks
monitoring_task = Task(
    name="collect_data",
    description="Collect environmental data",
    expected_output="Environmental measurements",
    agent=environmental_monitor,
    is_start=True,
    next_tasks=["analyze_urban"]
)

urban_task = Task(
    name="analyze_urban",
    description="Analyze urban factors",
    expected_output="Urban analysis",
    agent=urban_analyzer,
    next_tasks=["model_climate"]
)

modeling_task = Task(
    name="model_climate",
    description="Model microclimate",
    expected_output="Climate models",
    agent=climate_modeler,
    context=[monitoring_task, urban_task],
    next_tasks=["predict_impacts"]
)

prediction_task = Task(
    name="predict_impacts",
    description="Predict climate impacts",
    expected_output="Impact predictions",
    agent=impact_predictor,
    next_tasks=["generate_strategies"]
)

strategy_task = Task(
    name="generate_strategies",
    description="Generate adaptation strategies",
    expected_output="Adaptation strategies",
    agent=strategy_generator,
    task_type="decision",
    condition={
        "immediate": ["collect_data"],  # Continuous monitoring for high priority
        "medium": "",  # End workflow for medium priority
        "low": ""  # End workflow for low priority
    }
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[environmental_monitor, urban_analyzer, climate_modeler,
            impact_predictor, strategy_generator],
    tasks=[monitoring_task, urban_task, modeling_task,
           prediction_task, strategy_task],
    process="workflow",
    verbose=True
)

async def main():
    print("\nStarting Climate Impact Prediction Workflow...")
    print("=" * 50)
    
    # Run workflow
    results = await workflow.astart()
    
    # Print results
    print("\nClimate Impact Analysis Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            print(f"\nTask: {task_id}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())