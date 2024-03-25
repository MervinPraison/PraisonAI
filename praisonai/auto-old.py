from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Dict
import instructor
import os
import json

config_list = [
    {
        'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-4-turbo-preview"),
        'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
    }
]

task = "Movie Story writing"

# Define new Pydantic models to represent the script writing team structure
class TaskDetails(BaseModel):
    description: str
    expected_output: str

class RoleDetails(BaseModel):
    role: str
    goal: str
    backstory: str
    tasks: Dict[str, TaskDetails]

class TeamStructure(BaseModel):
    roles: Dict[str, RoleDetails]

# Enables `response_model` in create call with the new model
client = instructor.patch(
    OpenAI(
        base_url=config_list[0]['base_url'],
        api_key=os.getenv("OPENAI_API_KEY"),
    ),
    mode=instructor.Mode.JSON,
)

response = client.chat.completions.create(
  model=config_list[0]['model'],
  response_model=TeamStructure,
  max_retries=10,
  messages=[
    {"role": "system", "content": "You are a helpful assistant designed to output complex team structures."},
    {"role": "user", "content": 
"""Generate a team structure for """ + task + """ task. 
No Input data will be provided to the team.
The team will work in sequence. First role will pass the output to the next role, and so on.
The last role will generate the final output.
Think step by step.
With maximum 3 roles, each with 1 task. Include role goals, backstories, task descriptions, and expected outputs.
Output Structure:
{
"roles": {
"<role_id>": {
"role": "<role_name>",
"goal": "<role_goal>",
"backstory": "<role_backstory>",
"tasks": {
"<task_id>": {
"description": "<task_description>",
"expected_output": "<task_expected_output>"
}
}
},
"<role_id>": {
"role": "<role_name>",
"goal": "<role_goal>",
"backstory": "<role_backstory>",
"tasks": {
"<task_id>": {
"description": "<task_description>",
"expected_output": "<task_expected_output>"
}
}
}
}
}
Example Below:
{
"roles": {
"narrative_designer": {
"role": "Narrative Designer",
"goal": "Create AI storylines",
"backstory": "Skilled in narrative development for AI, with a focus on story resonance.",
"tasks": {
"story_concept_development": {
"description": "Craft a unique AI story concept with depth and engagement.",
"expected_output": "Document with narrative arcs, character bios, and settings."
}
}
},
"scriptwriter": {
"role": "Scriptwriter",
"goal": "Write scripts from AI concepts",
"backstory": "Expert in dialogue and script structure, translating concepts into scripts.",
"tasks": {
"scriptwriting_task": {
"description": "Turn narrative concepts into scripts, including dialogue and scenes.",
"expected_output": "Production-ready script with dialogue and scene details."
}
}
}
}
}
"""}
  ]
)

print(response.model_dump_json(indent=2))

import yaml

def convert_and_save(json_data, topic="Artificial Intelligence", filename="test.yaml"):
    """Converts the provided JSON data into the desired YAML format and saves it to a file.

    Args:
        json_data (dict): The JSON data representing the team structure.
        topic (str, optional): The topic to be inserted into the YAML. Defaults to "Artificial Intelligence".
        filename (str, optional): The name of the YAML file to save. Defaults to "test.yaml".
    """

    yaml_data = {
        "framework": "crewai",
        "topic": topic,
        "roles": {},
        "dependencies": []
    }

    # Process roles in the order they appear in JSON
    for role_id, role_details in json_data['roles'].items():
        yaml_data['roles'][role_id] = {
            "backstory": "" + role_details['backstory'],
            "goal": role_details['goal'],
            "role": role_details['role'],
            "tasks": {}
        }

        for task_id, task_details in role_details['tasks'].items():
            yaml_data['roles'][role_id]['tasks'][task_id] = {
                "description": "" + task_details['description'],
                "expected_output": "" + task_details['expected_output']
            }

    # Save to YAML file, maintaining the order
    with open(filename, 'w') as f:
        yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False)
    
json_data = json.loads(response.model_dump_json())
convert_and_save(json_data) 