import sys
from .version import __version__
import yaml, os
from rich import print
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from crewai.telemetry import Telemetry
load_dotenv()
import autogen
import argparse
from .auto import AutoGenerator
from praisonai_tools import (
    CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool, DirectoryReadTool,
    FileReadTool, TXTSearchTool, JSONSearchTool, MDXSearchTool, PDFSearchTool, RagTool,
    ScrapeElementFromWebsiteTool, ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool, YoutubeChannelSearchTool,
    YoutubeVideoSearchTool
)
from .inbuilt_tools import *
from .inc import PraisonAIModel
import inspect
from pathlib import Path
import importlib
import importlib.util
from praisonai_tools import BaseTool
import os
import logging

agentops_exists = False
try:
    import agentops
    agentops_exists = True
except ImportError:
    agentops_exists = False

os.environ["OTEL_SDK_DISABLED"] = "true"

def noop(*args, **kwargs):
    pass

def disable_crewai_telemetry():
    for attr in dir(Telemetry):
        if callable(getattr(Telemetry, attr)) and not attr.startswith("__"):
            setattr(Telemetry, attr, noop)
            
disable_crewai_telemetry()

class AgentsGenerator:
    def __init__(self, agent_file, framework, config_list, log_level=None, agent_callback=None, task_callback=None, agent_yaml=None):
        self.agent_file = agent_file
        self.framework = framework
        self.config_list = config_list
        self.log_level = log_level
        self.agent_callback = agent_callback
        self.task_callback = task_callback
        self.agent_yaml = agent_yaml
        self.log_level = log_level or logging.getLogger().getEffectiveLevel()
        if self.log_level == logging.NOTSET:
            self.log_level = os.environ.get('LOGLEVEL', 'INFO').upper()
        
        logging.basicConfig(level=self.log_level, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.log_level)
        
        if agentops_exists:
            agentops.init(os.environ.get("AGENTOPS_API_KEY"))

    @agentops.record_function('is_function_or_decorated')
    def is_function_or_decorated(self, obj):
        return inspect.isfunction(obj) or hasattr(obj, '__call__')

    @agentops.record_function('load_tools_from_module')
    def load_tools_from_module(self, module_path):
        spec = importlib.util.spec_from_file_location("tools_module", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {name: obj for name, obj in inspect.getmembers(module, self.is_function_or_decorated)}
    
    @agentops.record_function('load_tools_from_module_class')
    def load_tools_from_module_class(self, module_path):
        spec = importlib.util.spec_from_file_location("tools_module", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {name: obj() for name, obj in inspect.getmembers(module, lambda x: inspect.isclass(x) and (x.__module__.startswith('langchain_community.tools') or issubclass(x, BaseTool)) and x is not BaseTool)}

    @agentops.record_function('load_tools_from_package')
    def load_tools_from_package(self, package_path):
        tools_dict = {}
        for module_file in os.listdir(package_path):
            if module_file.endswith('.py') and not module_file.startswith('__'):
                module_name = f"{package_path.name}.{module_file[:-3]}"
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module, self.is_function_or_decorated):
                    tools_dict[name] = obj
        return tools_dict

    @agentops.record_function('generate_crew_and_kickoff')
    def generate_crew_and_kickoff(self):
        if self.agent_yaml:
            config = yaml.safe_load(self.agent_yaml)
        else:
            if self.agent_file == '/app/api:app' or self.agent_file == 'api:app':
                self.agent_file = 'agents.yaml'
            try:
                with open(self.agent_file, 'r') as f:
                    config = yaml.safe_load(f)
            except FileNotFoundError:
                print(f"File not found: {self.agent_file}")
                agentops.record_event('file_not_found', {'file': self.agent_file})
                return

        topic = config['topic']
        tools_dict = {
            'CodeDocsSearchTool': CodeDocsSearchTool(),
            'CSVSearchTool': CSVSearchTool(),
            'DirectorySearchTool': DirectorySearchTool(),
            'DOCXSearchTool': DOCXSearchTool(),
            'DirectoryReadTool': DirectoryReadTool(),
            'FileReadTool': FileReadTool(),
            'TXTSearchTool': TXTSearchTool(),
            'JSONSearchTool': JSONSearchTool(),
            'MDXSearchTool': MDXSearchTool(),
            'PDFSearchTool': PDFSearchTool(),
            'RagTool': RagTool(),
            'ScrapeElementFromWebsiteTool': ScrapeElementFromWebsiteTool(),
            'ScrapeWebsiteTool': ScrapeWebsiteTool(),
            'WebsiteSearchTool': WebsiteSearchTool(),
            'XMLSearchTool': XMLSearchTool(),
            'YoutubeChannelSearchTool': YoutubeChannelSearchTool(),
            'YoutubeVideoSearchTool': YoutubeVideoSearchTool(),
        }
        root_directory = os.getcwd()
        tools_py_path = os.path.join(root_directory, 'tools.py')
        tools_dir_path = Path(root_directory) / 'tools'
        
        if os.path.isfile(tools_py_path):
            tools_dict.update(self.load_tools_from_module_class(tools_py_path))
            self.logger.debug("tools.py exists in the root directory. Loading tools.py and skipping tools folder.")
        elif tools_dir_path.is_dir():
            tools_dict.update(self.load_tools_from_module_class(tools_dir_path))
            self.logger.debug("tools folder exists in the root directory")
        
        framework = self.framework or config.get('framework')

        agents = {}
        tasks = []
        if framework == "autogen":
            llm_config = {"config_list": self.config_list}
            
            if agentops_exists:
                agentops.add_tags(["autogen"])
            user_proxy = autogen.UserProxyAgent(
                name="User",
                human_input_mode="NEVER",
                is_termination_msg=lambda x: (x.get("content") or "").rstrip().rstrip(".").lower().endswith("terminate") or "TERMINATE" in (x.get("content") or ""),
                code_execution_config={
                    "work_dir": "coding",
                    "use_docker": False,
                },
            )
            
            for role, details in config['roles'].items():
                agent_name = details['role'].format(topic=topic).replace("{topic}", topic)
                agent_goal = details['goal'].format(topic=topic)
                agents[role] = autogen.AssistantAgent(
                    name=agent_name,
                    llm_config=llm_config,
                    system_message=details['backstory'].format(topic=topic)+". Must Reply \"TERMINATE\" in the end when everything is done.",
                )
                for tool in details.get('tools', []):
                    if tool in tools_dict:
                        try:
                            tool_class = globals()[f'autogen_{type(tools_dict[tool]).__name__}']
                            print(f"Found {tool_class.__name__} for {tool}")
                        except KeyError:
                            print(f"Warning: autogen_{type(tools_dict[tool]).__name__} function not found. Skipping this tool.")
                            continue
                        tool_class(agents[role], user_proxy)

                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = task_details['description'].format(topic=topic)
                    expected_output_filled = task_details['expected_output'].format(topic=topic)
                    
                    chat_task = {
                        "recipient": agents[role],
                        "message": description_filled,
                        "summary_method": "last_msg", 
                    }
                    tasks.append(chat_task)
            
            agentops.record_event('autogen_tasks_created', {'num_tasks': len(tasks)})
            response = user_proxy.initiate_chats(tasks)
            result = "### Output ###\n"+response[-1].summary if hasattr(response[-1], 'summary') else ""
            agentops.record_event('autogen_tasks_completed', {'result_length': len(result)})
        else: # framework=crewai
            if agentops_exists:
                agentops.add_tags(["crewai"])
            
            tasks_dict = {}
            
            for role, details in config['roles'].items():
                role_filled = details['role'].format(topic=topic)
                goal_filled = details['goal'].format(topic=topic)
                backstory_filled = details['backstory'].format(topic=topic)
                
                agent_tools = [tools_dict[tool] for tool in details.get('tools', []) if tool in tools_dict]
                
                llm_model = details.get('llm')
                if llm_model:
                    llm = PraisonAIModel(
                        model=llm_model.get("model", os.environ.get("MODEL_NAME", "openai/gpt-4o")),
                    ).get_model()
                else:
                    llm = PraisonAIModel().get_model()

                function_calling_llm_model = details.get('function_calling_llm')
                if function_calling_llm_model:
                    function_calling_llm = PraisonAIModel(
                        model=function_calling_llm_model.get("model", os.environ.get("MODEL_NAME", "openai/gpt-4o")),
                    ).get_model()
                else:
                    function_calling_llm = PraisonAIModel().get_model()
                
                agent = Agent(
                    role=role_filled, 
                    goal=goal_filled, 
                    backstory=backstory_filled, 
                    tools=agent_tools, 
                    allow_delegation=details.get('allow_delegation', False),
                    llm=llm,
                    function_calling_llm=function_calling_llm,
                    max_iter=details.get('max_iter', 15),
                    max_rpm=details.get('max_rpm'),
                    max_execution_time=details.get('max_execution_time'),
                    verbose=details.get('verbose', True),
                    cache=details.get('cache', True),
                    system_template=details.get('system_template'),
                    prompt_template=details.get('prompt_template'),
                    response_template=details.get('response_template'),
                )
                
                if self.agent_callback:
                    agent.step_callback = self.agent_callback

                agents[role] = agent

                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = task_details['description'].format(topic=topic)
                    expected_output_filled = task_details['expected_output'].format(topic=topic)

                    task = Task(
                        description=description_filled,
                        expected_output=expected_output_filled,
                        agent=agent,
                        tools=task_details.get('tools', []),
                        async_execution=task_details.get('async_execution') if task_details.get('async_execution') is not None else False,
                        context=[],
                        config=task_details.get('config') if task_details.get('config') is not None else {},
                        output_json=task_details.get('output_json') if task_details.get('output_json') is not None else None,
                        output_pydantic=task_details.get('output_pydantic') if task_details.get('output_pydantic') is not None else None,
                        output_file=task_details.get('output_file') if task_details.get('output_file') is not None else "",
                        callback=task_details.get('callback') if task_details.get('callback') is not None else None,
                        human_input=task_details.get('human_input') if task_details.get('human_input') is not None else False,
                        create_directory=task_details.get('create_directory') if task_details.get('create_directory') is not None else False
                    )
                    
                    if self.task_callback:
                        task.callback = self.task_callback

                    tasks.append(task)
                    tasks_dict[task_name] = task
            
            for role, details in config['roles'].items():
                for task_name, task_details in details.get('tasks', {}).items():
                    task = tasks_dict[task_name]
                    context_tasks = [tasks_dict[ctx] for ctx in task_details.get('context', []) if ctx in tasks_dict]
                    task.context = context_tasks

            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=2
            )
            
            self.logger.debug("Final Crew Configuration:")
            self.logger.debug(f"Agents: {crew.agents}")
            self.logger.debug(f"Tasks: {crew.tasks}")

            agentops.record_event('crewai_tasks_created', {'num_tasks': len(tasks), 'num_agents': len(agents)})
            response = crew.kickoff()
            result = f"### Task Output ###\n{response}"
            agentops.record_event('crewai_tasks_completed', {'result_length': len(result)})

        if agentops_exists:
            agentops.end_session("Success")
        return result

# End the session when the program exits
import atexit

# End the session when the program exits
import atexit

def end_session():
    if agentops_exists:
        agentops.end_session("Success")

atexit.register(end_session)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and run agents based on a YAML configuration.")
    parser.add_argument("agent_file", help="Path to the YAML file containing agent configurations")
    parser.add_argument("--framework", choices=["autogen", "crewai"], default="crewai", help="Framework to use for agent generation")
    parser.add_argument("--log_level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level")
    args = parser.parse_args()

    generator = AgentsGenerator(args.agent_file, args.framework, config_list=None, log_level=args.log_level)
    result = generator.generate_crew_and_kickoff()
    print(result)

# Additional utility functions or classes can be added here if needed

# Example of how to use the AgentsGenerator class:
# 
# if __name__ == "__main__":
#     agent_file = "path/to/your/agents.yaml"
#     framework = "crewai"  # or "autogen"
#     config_list = [...]  # Your config list for autogen framework
#     
#     generator = AgentsGenerator(agent_file, framework, config_list)
#     result = generator.generate_crew_and_kickoff()
#     print(result)