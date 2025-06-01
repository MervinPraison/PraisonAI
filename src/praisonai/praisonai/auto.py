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
    def __init__(self, topic="Movie Story writing about AI", agent_file="test.yaml", framework="crewai", config_list: Optional[List[Dict]] = None, overwrite=True):
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
        self.overwrite = overwrite
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

        # Check if we should merge with existing agents.yaml file when overwrite is False
        if not self.overwrite:
            yaml_data = self.merge_with_existing_agents(yaml_data)

        # Save to YAML file, maintaining the order
        with open(self.agent_file, 'w') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False)

    def merge_with_existing_agents(self, new_yaml_data):
        """
        Merge new agents with existing agents.yaml file if it exists.
        
        Args:
            new_yaml_data (dict): The new YAML data to merge
            
        Returns:
            dict: Merged YAML data
        """
        if not os.path.exists(self.agent_file):
            return new_yaml_data
            
        try:
            with open(self.agent_file, 'r') as f:
                existing_data = yaml.safe_load(f)
                
            if not existing_data or 'roles' not in existing_data:
                return new_yaml_data
                
            # Create merged data starting with existing data
            merged_data = existing_data.copy()
            
            # Combine topics if both exist
            existing_topic = existing_data.get('topic', '')
            new_topic = new_yaml_data.get('topic', '')
            if existing_topic and new_topic:
                merged_data['topic'] = f"{existing_topic} + {new_topic}"
            elif new_topic:
                merged_data['topic'] = new_topic
                
            # Keep existing framework, but update if new one is provided
            if new_yaml_data.get('framework'):
                merged_data['framework'] = new_yaml_data['framework']
                
            # Merge roles with conflict resolution
            for role_id, role_details in new_yaml_data['roles'].items():
                if role_id in merged_data['roles']:
                    # Handle conflict by renaming the new role
                    suffix = 1
                    while f"{role_id}_auto_{suffix}" in merged_data['roles']:
                        suffix += 1
                    new_role_id = f"{role_id}_auto_{suffix}"
                    merged_data['roles'][new_role_id] = role_details
                else:
                    merged_data['roles'][role_id] = role_details
                    
            # Merge dependencies
            existing_deps = merged_data.get('dependencies', [])
            new_deps = new_yaml_data.get('dependencies', [])
            merged_data['dependencies'] = existing_deps + [dep for dep in new_deps if dep not in existing_deps]
            
            return merged_data
            
        except yaml.YAMLError:
            logging.warning(f"Could not parse existing {self.agent_file}, using new data only")
            return new_yaml_data
        except Exception as e:
            logging.warning(f"Error merging with existing {self.agent_file}: {e}, using new data only")
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