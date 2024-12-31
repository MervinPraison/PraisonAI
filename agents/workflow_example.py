from praisonaiagents import Agent, Task, PraisonAIAgents
import random
from typing import List, Dict, Union
import json

def random_data_of_individuals() -> List[Dict]:
    """Generate random individual data"""
    names = ["John", "Jane", "Mike", "Sarah", "David", "Emma"]
    jobs = ["Engineer", "Doctor", "Teacher", "Artist", "Developer"]
    cities = ["New York", "London", "Tokyo", "Paris", "Berlin"]
    
    data = []
    for _ in range(random.randint(3, 7)):
        person = {
            "name": random.choice(names),
            "age": random.randint(25, 65),
            "job": random.choice(jobs),
            "city": random.choice(cities),
            "salary": random.randint(30000, 120000)
        }
        data.append(person)
    return data

def process_data_of_individuals(data: Union[List[Dict], Dict, str]) -> Dict:
    """Process individual data by adding categories and analysis"""
    try:
        # Handle string input by trying to parse it as JSON
        if isinstance(data, str):
            data = json.loads(data)
        
        # Handle single record
        if isinstance(data, dict):
            person = data
            remaining = 0
        # Handle first record from list
        elif isinstance(data, list):
            if len(data) == 0:
                raise ValueError("Empty data list")
            person = data[0]
            remaining = len(data) - 1
        else:
            raise ValueError("Input must be a dictionary or list with at least one record")
        
        processed_person = person.copy()
        
        # Add salary category
        if person["salary"] < 50000:
            processed_person["salary_category"] = "entry"
        elif person["salary"] < 90000:
            processed_person["salary_category"] = "mid"
        else:
            processed_person["salary_category"] = "senior"
        
        # Add age group
        if person["age"] < 35:
            processed_person["age_group"] = "young"
        elif person["age"] < 50:
            processed_person["age_group"] = "mid"
        else:
            processed_person["age_group"] = "senior"
        
        # Add processing status
        if remaining > 0:
            processed_person["processing_status"] = f"more records to process ({remaining} remaining)"
        else:
            processed_person["processing_status"] = "all records processed"
            
        return processed_person
        
    except Exception as e:
        return {"error": str(e), "processing_status": "error occurred"}

# Create agents
data_agent = Agent(
    name="DataCollector",
    role="Data collection specialist",
    goal="Collect and validate data about individuals",
    backstory="Expert in gathering and validating demographic data",
    tools=[random_data_of_individuals],
    self_reflect=False
)

process_agent = Agent(
    name="DataProcessor",
    role="Data processor",
    goal="Process and categorize individual data",
    backstory="Expert in data analysis and categorization",
    tools=[process_data_of_individuals],
    self_reflect=False
)

# Create tasks with workflow logic
collect_task = Task(
    name="collect_data",
    description="Collect random individual data using the random_data_of_individuals tool",
    expected_output="List of individual records with basic information",
    agent=data_agent,
    is_start=True,
    next_tasks=["validate_data"]
)

validate_task = Task(
    name="validate_data",
    description="""Validate the collected data. Check if:
    1. All required fields are present (name, age, job, city, salary)
    2. Age is between 25 and 65
    3. Salary is between 30000 and 120000""",
    expected_output="Validation result indicating if data is valid or invalid",
    agent=data_agent,
    task_type="decision",
    condition={
        "valid": ["process_data"],
        "invalid": ["collect_data"]
    }
)

process_task = Task(
    name="process_data",
    description="""Process one record at a time from the input data.
    Current progress will be shown in Loop Status.
    
    For the current record:
    1. Use process_data_of_individuals tool to add categories
    2. Return the processed record
    
    The system will automatically handle looping through all records.""",
    expected_output="Processed record with categories and status",
    agent=process_agent,
    task_type="loop",
    condition={
        "more records to process": ["process_data"],  # Continue loop
        "all records processed": []  # End loop
    },
    context=[collect_task]  # Explicitly include collect_task for data
)

# Create PraisonAIAgents instance with workflow process
workflow = PraisonAIAgents(
    agents=[data_agent, process_agent],
    tasks=[collect_task, validate_task, process_task],
    verbose=1,
    process="workflow"
)

# Run the workflow
result = workflow.start()

# Print results
print("\nWorkflow Results:")
print("----------------")
for task_id, task in workflow.tasks.items():
    print(f"\nTask: {task.name}")
    print(f"Status: {task.status}")
    if task.result:
        print("Output:")
        try:
            # Try to format as pretty JSON
            import json
            output = json.loads(task.result.raw)
            print(json.dumps(output, indent=2))
        except:
            # If not JSON, print raw output
            print(task.result.raw[:500] + "..." if len(task.result.raw) > 500 else task.result.raw) 