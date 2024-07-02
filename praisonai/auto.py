from openai import OpenAI
from pydantic import BaseModel
from typing import Dict, List, Optional
import instructor
import os
import json
import yaml
from rich import print
import logging
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO').upper(), format='%(asctime)s - %(levelname)s - %(message)s')

# Define Pydantic models outside of the generate method
class TaskDetails(BaseModel):
    description: str
    expected_output: str

class RoleDetails(BaseModel):
    role: str
    goal: str
    backstory: str
    tasks: Dict[str, TaskDetails]
    tools: List[str]

class TeamStructure(BaseModel):
    roles: Dict[str, RoleDetails]

class AutoGenerator:
    def __init__(self, topic="Movie Story writing about AI", agent_file="test.yaml", framework="crewai", config_list: Optional[List[Dict]] = None):
        """
        Initialize the AutoGenerator class with the specified topic, agent file, and framework.
        Note: autogen framework is different from this AutoGenerator class.

        Args:
            topic (str, optional): The topic for the generated team structure. Defaults to "Movie Story writing about AI".
            agent_file (str, optional): The name of the YAML file to save the generated team structure. Defaults to "test.yaml".
            framework (str, optional): The framework for the generated team structure. Defaults to "crewai".
            config_list (Optional[List[Dict]], optional): A list containing the configuration details for the OpenAI API. 
                                                          If None, it defaults to using environment variables or hardcoded values.
        Attributes:
            config_list (list): A list containing the configuration details for the OpenAI API.
            topic (str): The specified topic for the generated team structure.
            agent_file (str): The specified name of the YAML file to save the generated team structure.
            framework (str): The specified framework for the generated team structure.
            client (instructor.Client): An instance of the instructor.Client class initialized with the specified OpenAI API configuration.
        """
        self.config_list = config_list or [
            {
                'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
                'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
                'api_key': os.environ.get("OPENAI_API_KEY")
            }
        ]
        self.topic = topic
        self.agent_file = agent_file
        self.framework = framework or "crewai"
        self.client = instructor.patch(
            OpenAI(
                base_url=self.config_list[0]['base_url'],
                api_key=os.getenv("OPENAI_API_KEY"),
            ),
            mode=instructor.Mode.JSON,
        )

    def generate(self):
        """
        Generates a team structure for the specified topic.

        Args:
            None

        Returns:
            str: The full path of the YAML file containing the generated team structure.

        Raises:
            Exception: If the generation process fails.

        Usage:
            generator = AutoGenerator(framework="crewai", topic="Create a movie script about Cat in Mars")
            path = generator.generate()
            print(path)
        """
        response = self.client.chat.completions.create(
            model=self.config_list[0]['model'],
            response_model=TeamStructure,
            max_retries=10,
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output complex team structures."},
                {"role": "user", "content": self.get_user_content()}
            ]
        )
        json_data = json.loads(response.model_dump_json())
        self.convert_and_save(json_data)
        full_path = os.path.abspath(self.agent_file)
        return full_path

    def convert_and_save(self, json_data):
        """Converts the provided JSON data into the desired YAML format and saves it to a file.

        Args:
            json_data (dict): The JSON data representing the team structure.
            topic (str, optional): The topic to be inserted into the YAML. Defaults to "Artificial Intelligence".
            agent_file (str, optional): The name of the YAML file to save. Defaults to "test.yaml".
        """

        yaml_data = {
            "framework": self.framework,
            "topic": self.topic,
            "roles": {},
            "dependencies": []
        }

        for role_id, role_details in json_data['roles'].items():
            yaml_data['roles'][role_id] = {
                "backstory": "" + role_details['backstory'],
                "goal": role_details['goal'],
                "role": role_details['role'],
                "tasks": {},
                # "tools": role_details.get('tools', []),
                "tools": ['']
            }

            for task_id, task_details in role_details['tasks'].items():
                yaml_data['roles'][role_id]['tasks'][task_id] = {
                    "description": "" + task_details['description'],
                    "expected_output": "" + task_details['expected_output']
                }

        # Save to YAML file, maintaining the order
        with open(self.agent_file, 'w') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False)

    def get_user_content(self):
        """
        Generates a prompt for the OpenAI API to generate a team structure.

        Args:
            None

        Returns:
            str: The prompt for the OpenAI API.

        Usage:
            generator = AutoGenerator(framework="crewai", topic="Create a movie script about Cat in Mars")
            prompt = generator.get_user_content()
            print(prompt)
        """
        user_content = """Generate a team structure for  \"""" + self.topic + """\" task. 
No Input data will be provided to the team.
The team will work in sequence. First role will pass the output to the next role, and so on.
The last role will generate the final output.
Think step by step.
With maximum 3 roles, each with 1 task. Include role goals, backstories, task descriptions, and expected outputs.
List of Available Tools: CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool, DirectoryReadTool, FileReadTool, TXTSearchTool, JSONSearchTool, MDXSearchTool, PDFSearchTool, RagTool, ScrapeElementFromWebsiteTool, ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool, YoutubeChannelSearchTool, YoutubeVideoSearchTool.
Only use Available Tools. Do Not use any other tools. 
Example Below: 
Use below example to understand the structure of the output. 
The final role you create should satisfy the provided task: """ + self.topic + """.
{
"roles": {
"narrative_designer": {
"role": "Narrative Designer",
"goal": "Create AI storylines",
"backstory": "Skilled in narrative development for AI, with a focus on story resonance.",
"tools": ["ScrapeWebsiteTool"],
"tasks": {
"story_concept_development": {
"description": "Craft a unique AI story concept with depth and engagement using concept from this page the content https://www.asthebirdfliesblog.com/posts/how-to-write-book-story-development .",
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
        """
        return user_content

    
# generator = AutoGenerator(framework="crewai", topic="Create a movie script about Cat in Mars")
# print(generator.generate())