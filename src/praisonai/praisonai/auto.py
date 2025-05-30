from openai import OpenAI
from pydantic import BaseModel
from typing import Dict, List, Optional
import instructor
import os
import json
import yaml
from rich import print
import logging

# Framework-specific imports with availability checks
CREWAI_AVAILABLE = False
AUTOGEN_AVAILABLE = False
PRAISONAI_TOOLS_AVAILABLE = False
PRAISONAI_AVAILABLE = False

try:
    from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, PraisonAIAgents
    PRAISONAI_AVAILABLE = True
except ImportError:
    pass

try:
    from crewai import Agent, Task, Crew
    CREWAI_AVAILABLE = True
except ImportError:
    pass

try:
    import autogen
    AUTOGEN_AVAILABLE = True
except ImportError:
    pass

try:
    from praisonai_tools import (
        CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool,
        DirectoryReadTool, FileReadTool, TXTSearchTool, JSONSearchTool,
        MDXSearchTool, PDFSearchTool, RagTool, ScrapeElementFromWebsiteTool,
        ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool,
        YoutubeChannelSearchTool, YoutubeVideoSearchTool
    )
    PRAISONAI_TOOLS_AVAILABLE = True
except ImportError:
    PRAISONAI_TOOLS_AVAILABLE = False

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
        """
        # Validate framework availability and show framework-specific messages
        if framework == "crewai" and not CREWAI_AVAILABLE:
            raise ImportError("""
CrewAI is not installed. Please install with:
    pip install "praisonai[crewai]"
""")
        elif framework == "autogen" and not AUTOGEN_AVAILABLE:
            raise ImportError("""
AutoGen is not installed. Please install with:
    pip install "praisonai[autogen]"
""")
        elif framework == "praisonai" and not PRAISONAI_AVAILABLE:
            raise ImportError("""
Praisonai is not installed. Please install with:
    pip install praisonaiagents
""")

        # Only show tools message if using a framework and tools are needed
        if (framework in ["crewai", "autogen"]) and not PRAISONAI_TOOLS_AVAILABLE:
            logging.warning(f"""
Tools are not available for {framework}. To use tools, install:
    pip install "praisonai[{framework}]"
""")

        # Support multiple environment variable patterns for better compatibility
        # Priority order: MODEL_NAME > OPENAI_MODEL_NAME for model selection
        model_name = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
        
        # Priority order for base_url: OPENAI_BASE_URL > OPENAI_API_BASE > OLLAMA_API_BASE
        # OPENAI_BASE_URL is the standard OpenAI SDK environment variable
        base_url = (
            os.environ.get("OPENAI_BASE_URL") or 
            os.environ.get("OPENAI_API_BASE") or
            os.environ.get("OLLAMA_API_BASE", "https://api.openai.com/v1")
        )
        
        self.config_list = config_list or [
            {
                'model': model_name,
                'base_url': base_url,
                'api_key': os.environ.get("OPENAI_API_KEY")
            }
        ]
        self.topic = topic
        self.agent_file = agent_file
        self.framework = framework or "praisonai"
        self.client = instructor.patch(
            OpenAI(
                base_url=self.config_list[0]['base_url'],
                api_key=self.config_list[0]['api_key'],
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

        # Check for existing agents.yaml and merge if it exists
        if os.path.exists("agents.yaml"):
            yaml_data = self.merge_with_existing_agents(yaml_data, "agents.yaml")

        # Save to YAML file, maintaining the order
        with open(self.agent_file, 'w') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False)

    def merge_with_existing_agents(self, new_yaml_data, existing_file_path):
        """Merge new auto-generated agents with existing agents.yaml file.
        
        Args:
            new_yaml_data (dict): The newly generated YAML data
            existing_file_path (str): Path to existing agents.yaml file
            
        Returns:
            dict: Merged YAML data containing both existing and new agents
        """
        try:
            with open(existing_file_path, 'r') as f:
                existing_data = yaml.safe_load(f)
            
            if not existing_data or 'roles' not in existing_data:
                print(f"Warning: {existing_file_path} exists but has no valid roles. Using auto-generated agents only.")
                return new_yaml_data
                
            # Start with existing data as base
            merged_data = existing_data.copy()
            
            # Update framework and topic if they exist in new data
            if 'framework' in new_yaml_data:
                merged_data['framework'] = new_yaml_data['framework']
            if 'topic' in new_yaml_data:
                # Combine topics if both exist, otherwise use new topic
                if 'topic' in existing_data and existing_data['topic'] != new_yaml_data['topic']:
                    merged_data['topic'] = f"{existing_data['topic']} + {new_yaml_data['topic']}"
                else:
                    merged_data['topic'] = new_yaml_data['topic']
            
            # Merge roles - add new roles while preserving existing ones
            existing_roles = merged_data.get('roles', {})
            new_roles = new_yaml_data.get('roles', {})
            
            # Add all new roles with conflict resolution
            for role_id, role_details in new_roles.items():
                if role_id in existing_roles:
                    # Handle role name conflicts by appending suffix
                    original_role_id = role_id
                    counter = 1
                    while role_id in existing_roles:
                        role_id = f"{original_role_id}_auto_{counter}"
                        counter += 1
                    print(f"Role '{original_role_id}' already exists. Auto-generated role renamed to '{role_id}'")
                
                merged_data['roles'][role_id] = role_details
                
            # Merge dependencies
            existing_deps = merged_data.get('dependencies', [])
            new_deps = new_yaml_data.get('dependencies', [])
            merged_data['dependencies'] = existing_deps + [dep for dep in new_deps if dep not in existing_deps]
            
            print(f"Successfully merged {len(new_roles)} auto-generated roles with {len(existing_roles)} existing roles from {existing_file_path}")
            return merged_data
            
        except Exception as e:
            print(f"Warning: Could not merge with {existing_file_path}: {e}. Using auto-generated agents only.")
            return new_yaml_data

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