from praisonaiagents import Agent, Task, PraisonAIAgents
import random
from typing import List, Dict, Union
import json
from pydantic import BaseModel

# Add Pydantic models for data validation
class Person(BaseModel):
    name: str
    age: int
    job: str
    city: str
    salary: int

class ProcessedPerson(Person):
    salary_category: str
    age_group: str
    processing_status: str

class DataList(BaseModel):
    items: List[Dict]

class ValidationResult(BaseModel):
    validation_result: str
    details: str = ""

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
        print("\n[DEBUG] process_data_of_individuals input:", data)
        print("[DEBUG] Current workflow state:")
        print("- total_records:", workflow.get_state("total_records"))
        print("- current_index:", workflow.get_state("current_index"))
        print("- remaining:", workflow.get_state("remaining"))

        # Get the items list from the collect_task result
        collect_result = None
        for task in workflow.tasks.values():
            if task.name == "collect_data" and task.result:
                try:
                    collect_data = json.loads(task.result.raw)
                    collect_result = collect_data.get("items", [])
                    print("[DEBUG] Found collect_data items:", len(collect_result))
                except:
                    print("[DEBUG] Failed to parse collect_data result")

        # Handle string input by trying to parse it as JSON
        if isinstance(data, str):
            if ":" in data and not data.strip().startswith("{"):
                # Convert string format to dictionary
                pairs = [pair.strip() for pair in data.split(",")]
                data_dict = {}
                for pair in pairs:
                    key, value = pair.split(":")
                    key = key.strip().lower()
                    value = value.strip()
                    if key == "age" or key == "salary":
                        value = int(value)
                    data_dict[key] = value
                data = data_dict
            else:
                data = json.loads(data)
            print("[DEBUG] Parsed data:", data)

        # Handle single record
        if isinstance(data, dict):
            person = data
            # Initialize total records if not set
            total_records = workflow.get_state("total_records")
            if total_records is None and collect_result:
                total_records = len(collect_result)
                workflow.set_state("total_records", total_records)
                print(f"[DEBUG] Initialized total_records to {total_records}")

            current_index = workflow.get_state("current_index", 0)
            total_records = total_records or 1
            remaining = total_records - (current_index + 1)
            workflow.set_state("remaining", remaining)
            print(f"[DEBUG] Processing record {current_index + 1}/{total_records}")

        elif isinstance(data, list):
            if len(data) == 0:
                raise ValueError("Empty data list")
            person = data[0]
            workflow.set_state("total_records", len(data))
            workflow.set_state("current_index", 0)
            workflow.set_state("remaining", len(data) - 1)
            print(f"[DEBUG] First record from list of {len(data)} items")
        else:
            raise ValueError("Input must be a dictionary or list with at least one record")

        processed_person = person.copy()
        
        # Add salary category
        salary = person.get("salary", 0)
        if salary < 50000:
            processed_person["salary_category"] = "entry"
        elif salary < 90000:
            processed_person["salary_category"] = "mid"
        else:
            processed_person["salary_category"] = "senior"
        
        # Add age group
        age = person.get("age", 0)
        if age < 35:
            processed_person["age_group"] = "young"
        elif age < 50:
            processed_person["age_group"] = "mid"
        else:
            processed_person["age_group"] = "senior"
        
        # Add processing status using workflow state
        remaining = workflow.get_state("remaining", 0)
        current_index = workflow.get_state("current_index", 0)
        total_records = workflow.get_state("total_records", 1)
        
        # Update current index for next iteration
        workflow.set_state("current_index", current_index + 1)
        
        print(f"[DEBUG] Status check - remaining: {remaining}, current_index: {current_index}, total_records: {total_records}")
        
        if remaining <= 0 and current_index >= total_records - 1:
            print("[DEBUG] Setting status to 'all records processed'")
            processed_person["processing_status"] = "all records processed"
        else:
            print(f"[DEBUG] More records to process. Remaining: {remaining}")
            processed_person["processing_status"] = f"more records to process ({remaining} remaining)"
            
        print("[DEBUG] Final processed person:", processed_person)
        return processed_person
        
    except Exception as e:
        print(f"[DEBUG] Error processing data: {str(e)}")
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

# Modify tasks to use Pydantic models
collect_task = Task(
    description="Collect random individual data using the random_data_of_individuals tool. Return as a JSON object with 'items' array.",
    expected_output="List of individual records with basic information",
    agent=data_agent,
    name="collect_data",
    tools=[random_data_of_individuals],
    is_start=True,
    next_tasks=["validate_data"],
    output_json=DataList
)

validate_task = Task(
    description="""Validate the collected data. Check if:
    1. All required fields are present (name, age, job, city, salary)
    2. Age is between 25 and 65
    3. Salary is between 30000 and 120000
    Return validation_result as 'valid' or 'invalid' with optional details.""",
    expected_output="Validation result indicating if data is valid or invalid",
    agent=data_agent,
    name="validate_data",
    task_type="decision",
    condition={
        "valid": ["process_data"],
        "invalid": ["collect_data"]
    },
    output_json=ValidationResult
)

process_task = Task(
    description="""Process one record at a time from the input data.
    Current progress will be shown in Loop Status.
    
    For the current record:
    1. Use process_data_of_individuals tool to add categories
    2. Return the processed record with remaining count
    
    Current remaining: {remaining}
    Current item: {current_item}
    
    Process this record and indicate if more records remain.""",
    expected_output="Processed record with categories and status",
    agent=process_agent,
    name="process_data",
    tools=[process_data_of_individuals],
    task_type="loop",
    condition={
        "more records to process": ["process_data"],
        "all records processed": []
    },
    context=[collect_task],
    output_json=ProcessedPerson
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