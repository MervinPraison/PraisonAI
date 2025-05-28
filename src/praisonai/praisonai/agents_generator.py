# praisonai/agents_generator.py

import sys
from .version import __version__
import yaml, os
from rich import print
from dotenv import load_dotenv
from .auto import AutoGenerator
from .inbuilt_tools import *
from .inc import PraisonAIModel
import inspect
from pathlib import Path
import importlib
import importlib.util
import os
import logging

# Framework-specific imports with availability checks
CREWAI_AVAILABLE = False
AUTOGEN_AVAILABLE = False
PRAISONAI_TOOLS_AVAILABLE = False
AGENTOPS_AVAILABLE = False
PRAISONAI_AVAILABLE = False

try:
    from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, PraisonAIAgents
    PRAISONAI_AVAILABLE = True
except ImportError:
    pass

try:
    from crewai import Agent, Task, Crew
    from crewai.telemetry import Telemetry
    CREWAI_AVAILABLE = True
except ImportError:
    pass

try:
    import autogen
    AUTOGEN_AVAILABLE = True
except ImportError:
    pass

try:
    import agentops
    AGENTOPS_AVAILABLE = True
    AGENTOPS_API_KEY = os.getenv("AGENTOPS_API_KEY")
    if not AGENTOPS_API_KEY:
        AGENTOPS_AVAILABLE = False
except ImportError:
    pass

# Only try to import praisonai_tools if either CrewAI or AutoGen is available
if CREWAI_AVAILABLE or AUTOGEN_AVAILABLE or PRAISONAI_AVAILABLE:
    try:
        from praisonai_tools import (
            CodeDocsSearchTool, CSVSearchTool, DirectorySearchTool, DOCXSearchTool, DirectoryReadTool,
            FileReadTool, TXTSearchTool, JSONSearchTool, MDXSearchTool, PDFSearchTool, RagTool,
            ScrapeElementFromWebsiteTool, ScrapeWebsiteTool, WebsiteSearchTool, XMLSearchTool, 
            YoutubeChannelSearchTool, YoutubeVideoSearchTool, BaseTool
        )
        PRAISONAI_TOOLS_AVAILABLE = True
    except ImportError:
        # If import fails, define BaseTool as a simple base class
        class BaseTool:
            pass

os.environ["OTEL_SDK_DISABLED"] = "true"

def noop(*args, **kwargs):
    pass

def disable_crewai_telemetry():
    if CREWAI_AVAILABLE:
        for attr in dir(Telemetry):
            if callable(getattr(Telemetry, attr)) and not attr.startswith("__"):
                setattr(Telemetry, attr, noop)

# Only disable telemetry if CrewAI is available
if CREWAI_AVAILABLE:
    disable_crewai_telemetry()

class AgentsGenerator:
    def __init__(self, agent_file, framework, config_list, log_level=None, agent_callback=None, task_callback=None, agent_yaml=None, tools=None):
        """
        Initialize the AgentsGenerator object.

        Parameters:
            agent_file (str): The path to the agent file.
            framework (str): The framework to be used for the agents.
            config_list (list): A list of configurations for the agents.
            log_level (int, optional): The logging level to use. Defaults to logging.INFO.
            agent_callback (callable, optional): A callback function to be executed after each agent step.
            task_callback (callable, optional): A callback function to be executed after each tool run.
            agent_yaml (str, optional): The content of the YAML file. Defaults to None.
            tools (dict, optional): A dictionary containing the tools to be used for the agents. Defaults to None.

        Attributes:
            agent_file (str): The path to the agent file.
            framework (str): The framework to be used for the agents.
            config_list (list): A list of configurations for the agents.
            log_level (int): The logging level to use.
            agent_callback (callable, optional): A callback function to be executed after each agent step.
            task_callback (callable, optional): A callback function to be executed after each tool run.
            tools (dict): A dictionary containing the tools to be used for the agents.
        """
        self.agent_file = agent_file
        self.framework = framework
        self.config_list = config_list
        self.log_level = log_level
        self.agent_callback = agent_callback
        self.task_callback = task_callback
        self.agent_yaml = agent_yaml
        self.tools = tools or []  # Store tool class names as a list
        self.log_level = log_level or logging.getLogger().getEffectiveLevel()
        if self.log_level == logging.NOTSET:
            self.log_level = os.environ.get('LOGLEVEL', 'INFO').upper()
        
        logging.basicConfig(level=self.log_level, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.log_level)
        
        # Validate framework availability
        if framework == "crewai" and not CREWAI_AVAILABLE:
            raise ImportError("CrewAI is not installed. Please install it with 'pip install praisonai[crewai]'")
        elif framework == "autogen" and not AUTOGEN_AVAILABLE:
            raise ImportError("AutoGen is not installed. Please install it with 'pip install praisonai[autogen]'")
        elif framework == "praisonai" and not PRAISONAI_AVAILABLE:
            raise ImportError("PraisonAI is not installed. Please install it with 'pip install praisonaiagents'")

    def is_function_or_decorated(self, obj):
        """
        Checks if the given object is a function or has a __call__ method.

        Parameters:
            obj (object): The object to be checked.

        Returns:
            bool: True if the object is a function or has a __call__ method, False otherwise.
        """
        return inspect.isfunction(obj) or hasattr(obj, '__call__')

    def load_tools_from_module(self, module_path):
        """
        Loads tools from a specified module path.

        Parameters:
            module_path (str): The path to the module containing the tools.

        Returns:
            dict: A dictionary containing the names of the tools as keys and the corresponding functions or objects as values.

        Raises:
            FileNotFoundError: If the specified module path does not exist.
        """
        spec = importlib.util.spec_from_file_location("tools_module", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {name: obj for name, obj in inspect.getmembers(module, self.is_function_or_decorated)}
    
    def load_tools_from_module_class(self, module_path):
        """
        Loads tools from a specified module path containing classes that inherit from BaseTool 
        or are part of langchain_community.tools package.
        """
        spec = importlib.util.spec_from_file_location("tools_module", module_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            return {name: obj() for name, obj in inspect.getmembers(module, 
                lambda x: inspect.isclass(x) and (
                    x.__module__.startswith('langchain_community.tools') or 
                    (PRAISONAI_TOOLS_AVAILABLE and issubclass(x, BaseTool))
                ) and x is not BaseTool)}
        except ImportError as e:
            self.logger.warning(f"Error loading tools from {module_path}: {e}")
            return {}

    def load_tools_from_package(self, package_path):
        """
        Loads tools from a specified package path containing modules with functions or classes.

        Parameters:
            package_path (str): The path to the package containing the tools.

        Returns:
            dict: A dictionary containing the names of the tools as keys and the corresponding initialized instances of the classes as values.

        Raises:
            FileNotFoundError: If the specified package path does not exist.

        This function iterates through all the .py files in the specified package path, excluding those that start with "__". For each file, it imports the corresponding module and checks if it contains any functions or classes that can be loaded as tools. The function then returns a dictionary containing the names of the tools as keys and the corresponding initialized instances of the classes as values.
        """
        tools_dict = {}
        for module_file in os.listdir(package_path):
            if module_file.endswith('.py') and not module_file.startswith('__'):
                module_name = f"{package_path.name}.{module_file[:-3]}"  # Remove .py for import
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module, self.is_function_or_decorated):
                    tools_dict[name] = obj
        return tools_dict

    def load_tools_from_tools_py(self):
        """
        Imports and returns all contents from tools.py file.
        Also adds the tools to the global namespace.

        Returns:
            list: A list of callable functions with proper formatting
        """
        tools_list = []
        try:
            # Try to import tools.py from current directory
            spec = importlib.util.spec_from_file_location("tools", "tools.py")
            self.logger.debug(f"Spec: {spec}")
            if spec is None:
                self.logger.debug("tools.py not found in current directory")
                return tools_list

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get all module attributes except private ones and classes
            for name, obj in inspect.getmembers(module):
                if (not name.startswith('_') and 
                    callable(obj) and 
                    not inspect.isclass(obj)):
                    # Add the function to global namespace
                    globals()[name] = obj
                    # Add to tools list
                    tools_list.append(obj)
                    self.logger.debug(f"Loaded and globalized tool function: {name}")

            self.logger.debug(f"Loaded {len(tools_list)} tool functions from tools.py")
            self.logger.debug(f"Tools list: {tools_list}")
            
        except FileNotFoundError:
            self.logger.debug("tools.py not found in current directory")
        except Exception as e:
            self.logger.warning(f"Error loading tools from tools.py: {e}")
            
        return tools_list

    def generate_crew_and_kickoff(self):
        """
        Generates a crew of agents and initiates tasks based on the provided configuration.

        Parameters:
            agent_file (str): The path to the agent file.
            framework (str): The framework to be used for the agents.
            config_list (list): A list of configurations for the agents.

        Returns:
            str: The output of the tasks performed by the crew of agents.

        Raises:
            FileNotFoundError: If the specified agent file does not exist.

        This function first loads the agent configuration from the specified file. It then initializes the tools required for the agents based on the specified framework. If the specified framework is "autogen", it loads the LLM configuration dynamically and creates an AssistantAgent for each role in the configuration. It then adds tools to the agents if specified in the configuration. Finally, it prepares tasks for the agents based on the configuration and initiates the tasks using the crew of agents. If the specified framework is not "autogen", it creates a crew of agents and initiates tasks based on the configuration.
        """
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
                return

        topic = config['topic']
        tools_dict = {}
        
        # Only try to use praisonai_tools if it's available and needed
        if PRAISONAI_TOOLS_AVAILABLE and (CREWAI_AVAILABLE or AUTOGEN_AVAILABLE or PRAISONAI_AVAILABLE):
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
            
            # Add tools from class names
            for tool_class in self.tools:
                if isinstance(tool_class, type) and issubclass(tool_class, BaseTool):
                    tool_name = tool_class.__name__
                    tools_dict[tool_name] = tool_class()
                    self.logger.debug(f"Added tool: {tool_name}")

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

        if framework == "autogen":
            if not AUTOGEN_AVAILABLE:
                raise ImportError("AutoGen is not installed. Please install it with 'pip install praisonai[autogen]'")
            if AGENTOPS_AVAILABLE:
                agentops.init(os.environ.get("AGENTOPS_API_KEY"), default_tags=["autogen"])
            return self._run_autogen(config, topic, tools_dict)
        elif framework == "praisonai":
            if not PRAISONAI_AVAILABLE:
                raise ImportError("PraisonAI is not installed. Please install it with 'pip install praisonaiagents'")
            if AGENTOPS_AVAILABLE:
                agentops.init(os.environ.get("AGENTOPS_API_KEY"), default_tags=["praisonai"])
            return self._run_praisonai(config, topic, tools_dict)
        else:  # framework=crewai
            if not CREWAI_AVAILABLE:
                raise ImportError("CrewAI is not installed. Please install it with 'pip install praisonai[crewai]'")
            if AGENTOPS_AVAILABLE:
                agentops.init(os.environ.get("AGENTOPS_API_KEY"), default_tags=["crewai"])
            return self._run_crewai(config, topic, tools_dict)

    def _run_autogen(self, config, topic, tools_dict):
        """
        Run agents using the AutoGen framework.
        
        Args:
            config (dict): Configuration dictionary
            topic (str): The topic to process
            tools_dict (dict): Dictionary of available tools
            
        Returns:
            str: Result of the agent interactions
        """
        llm_config = {"config_list": self.config_list}
        
        # Set up user proxy agent
        user_proxy = autogen.UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: (x.get("content") or "").rstrip().rstrip(".").lower().endswith("terminate") or "TERMINATE" in (x.get("content") or ""),
            code_execution_config={
                "work_dir": "coding",
                "use_docker": False,
            }
        )
        
        agents = {}
        tasks = []
        
        # Create agents and tasks from config
        for role, details in config['roles'].items():
            agent_name = details['role'].format(topic=topic).replace("{topic}", topic)
            agent_goal = details['goal'].format(topic=topic)
            
            # Create AutoGen assistant agent
            agents[role] = autogen.AssistantAgent(
                name=agent_name,
                llm_config=llm_config,
                system_message=details['backstory'].format(topic=topic) + 
                             ". Must Reply \"TERMINATE\" in the end when everything is done.",
            )
            
            # Add tools to agent if specified
            for tool in details.get('tools', []):
                if tool in tools_dict:
                    try:
                        tool_class = globals()[f'autogen_{type(tools_dict[tool]).__name__}']
                        self.logger.debug(f"Found {tool_class.__name__} for {tool}")
                        tool_class(agents[role], user_proxy)
                    except KeyError:
                        self.logger.warning(f"Warning: autogen_{type(tools_dict[tool]).__name__} function not found. Skipping this tool.")
                        continue

            # Prepare tasks
            for task_name, task_details in details.get('tasks', {}).items():
                description_filled = task_details['description'].format(topic=topic)
                expected_output_filled = task_details['expected_output'].format(topic=topic)
                
                chat_task = {
                    "recipient": agents[role],
                    "message": description_filled,
                    "summary_method": "last_msg",
                }
                tasks.append(chat_task)

        # Execute tasks
        response = user_proxy.initiate_chats(tasks)
        result = "### Output ###\n" + response[-1].summary if hasattr(response[-1], 'summary') else ""
        
        if AGENTOPS_AVAILABLE:
            agentops.end_session("Success")
            
        return result

    def _run_crewai(self, config, topic, tools_dict):
        """
        Run agents using the CrewAI framework.
        
        Args:
            config (dict): Configuration dictionary
            topic (str): The topic to process
            tools_dict (dict): Dictionary of available tools
            
        Returns:
            str: Result of the agent interactions
        """
        agents = {}
        tasks = []
        tasks_dict = {}

        # Create agents from config
        for role, details in config['roles'].items():
            role_filled = details['role'].format(topic=topic)
            goal_filled = details['goal'].format(topic=topic)
            backstory_filled = details['backstory'].format(topic=topic)
            
            # Get agent tools
            agent_tools = [tools_dict[tool] for tool in details.get('tools', []) 
                         if tool in tools_dict]
            
            # Configure LLM
            llm_model = details.get('llm')
            if llm_model:
                llm = PraisonAIModel(
                    model=llm_model.get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-4o",
                    base_url=self.config_list[0].get('base_url') if self.config_list else None,
                    api_key=self.config_list[0].get('api_key') if self.config_list else None
                ).get_model()
            else:
                llm = PraisonAIModel(
                    base_url=self.config_list[0].get('base_url') if self.config_list else None,
                    api_key=self.config_list[0].get('api_key') if self.config_list else None
                ).get_model()

            # Configure function calling LLM
            function_calling_llm_model = details.get('function_calling_llm')
            if function_calling_llm_model:
                function_calling_llm = PraisonAIModel(
                    model=function_calling_llm_model.get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-4o",
                    base_url=self.config_list[0].get('base_url') if self.config_list else None,
                    api_key=self.config_list[0].get('api_key') if self.config_list else None
                ).get_model()
            else:
                function_calling_llm = PraisonAIModel(
                    base_url=self.config_list[0].get('base_url') if self.config_list else None,
                    api_key=self.config_list[0].get('api_key') if self.config_list else None
                ).get_model()

            # Create CrewAI agent
            agent = Agent(
                role=role_filled,
                goal=goal_filled,
                backstory=backstory_filled,
                tools=agent_tools,
                allow_delegation=details.get('allow_delegation', False),
                llm=llm,
                function_calling_llm=function_calling_llm,
                max_iter=details.get('max_iter') or 15,
                max_rpm=details.get('max_rpm') or None,
                max_execution_time=details.get('max_execution_time') or None,
                verbose=details.get('verbose', True),
                cache=details.get('cache', True),
                system_template=details.get('system_template') or None,
                prompt_template=details.get('prompt_template') or None,
                response_template=details.get('response_template') or None,
            )
            
            # Set agent callback if provided
            if self.agent_callback:
                agent.step_callback = self.agent_callback

            agents[role] = agent

            # Create tasks for the agent
            for task_name, task_details in details.get('tasks', {}).items():
                description_filled = task_details['description'].format(topic=topic)
                expected_output_filled = task_details['expected_output'].format(topic=topic)

                task = Task(
                    description=description_filled,
                    expected_output=expected_output_filled,
                    agent=agent,
                    tools=task_details.get('tools', []),
                    async_execution=task_details.get('async_execution', False),
                    context=[],
                    config=task_details.get('config', {}),
                    output_json=task_details.get('output_json'),
                    output_pydantic=task_details.get('output_pydantic'),
                    output_file=task_details.get('output_file', ""),
                    callback=task_details.get('callback'),
                    human_input=task_details.get('human_input', False),
                    create_directory=task_details.get('create_directory', False)
                )
                
                # Set task callback if provided
                if self.task_callback:
                    task.callback = self.task_callback

                tasks.append(task)
                tasks_dict[task_name] = task

        # Set up task contexts
        for role, details in config['roles'].items():
            for task_name, task_details in details.get('tasks', {}).items():
                task = tasks_dict[task_name]
                context_tasks = [tasks_dict[ctx] for ctx in task_details.get('context', []) 
                               if ctx in tasks_dict]
                task.context = context_tasks

        # Create and run the crew
        crew = Crew(
            agents=list(agents.values()),
            tasks=tasks,
            verbose=True
        )
        
        self.logger.debug("Final Crew Configuration:")
        self.logger.debug(f"Agents: {crew.agents}")
        self.logger.debug(f"Tasks: {crew.tasks}")

        response = crew.kickoff()
        result = f"### Task Output ###\n{response}"
        
        if AGENTOPS_AVAILABLE:
            agentops.end_session("Success")
            
        return result

    def _run_praisonai(self, config, topic, tools_dict):
        """
        Run agents using the PraisonAI framework.
        """
        agents = {}
        tasks = []
        tasks_dict = {}

        # Load tools once at the beginning
        tools_list = self.load_tools_from_tools_py()
        self.logger.debug(f"Loaded tools: {tools_list}")

        # Create agents from config
        for role, details in config['roles'].items():
            role_filled = details['role'].format(topic=topic)
            goal_filled = details['goal'].format(topic=topic)
            backstory_filled = details['backstory'].format(topic=topic)
            
            # Pass all loaded tools to the agent
            agent = PraisonAgent(
                name=role_filled,
                role=role_filled,
                goal=goal_filled,
                backstory=backstory_filled,
                tools=tools_list,  # Pass the entire tools list to the agent
                allow_delegation=details.get('allow_delegation', False),
                llm=details.get('llm', {}).get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-4o",
                function_calling_llm=details.get('function_calling_llm', {}).get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-4o",
                max_iter=details.get('max_iter', 15),
                max_rpm=details.get('max_rpm'),
                max_execution_time=details.get('max_execution_time'),
                verbose=details.get('verbose', True),
                cache=details.get('cache', True),
                system_template=details.get('system_template'),
                prompt_template=details.get('prompt_template'),
                response_template=details.get('response_template'),
                reflect_llm=details.get('reflect_llm', {}).get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-4o",
                min_reflect=details.get('min_reflect', 1),
                max_reflect=details.get('max_reflect', 3),
            )
            
            if self.agent_callback:
                agent.step_callback = self.agent_callback

            agents[role] = agent
            self.logger.debug(f"Created agent {role_filled} with tools: {agent.tools}")

            # Create tasks for the agent
            for task_name, task_details in details.get('tasks', {}).items():
                description_filled = task_details['description'].format(topic=topic)
                expected_output_filled = task_details['expected_output'].format(topic=topic)

                task = PraisonTask(
                    description=description_filled,
                    expected_output=expected_output_filled,
                    agent=agent,
                    tools=tools_list,  # Pass the same tools list to the task
                    async_execution=task_details.get('async_execution', False),
                    context=[],
                    config=task_details.get('config', {}),
                    output_json=task_details.get('output_json'),
                    output_pydantic=task_details.get('output_pydantic'),
                    output_file=task_details.get('output_file', ""),
                    callback=task_details.get('callback'),
                    create_directory=task_details.get('create_directory', False)
                )

                self.logger.debug(f"Created task {task_name} with tools: {task.tools}")
                
                if self.task_callback:
                    task.callback = self.task_callback

                tasks.append(task)
                tasks_dict[task_name] = task

        # Set up task contexts
        for role, details in config['roles'].items():
            for task_name, task_details in details.get('tasks', {}).items():
                task = tasks_dict[task_name]
                context_tasks = [tasks_dict[ctx] for ctx in task_details.get('context', []) 
                            if ctx in tasks_dict]
                task.context = context_tasks

        # Create and run the PraisonAI agents
        memory = config.get('memory', False)
        self.logger.debug(f"Memory: {memory}")
        if config.get('process') == 'hierarchical':
            agents = PraisonAIAgents(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True,
                process="hierarchical",
                manager_llm=config.get('manager_llm') or os.environ.get("MODEL_NAME") or "openai/gpt-4o",
                memory=memory
            )
        else:
            agents = PraisonAIAgents(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True,
                memory=memory
            )

        self.logger.debug("Final Configuration:")
        self.logger.debug(f"Agents: {agents.agents}")
        self.logger.debug(f"Tasks: {agents.tasks}")

        response = agents.start()
        self.logger.debug(f"Result: {response}")
        result = ""
        
        if AGENTOPS_AVAILABLE:
            agentops.end_session("Success")
            
        return result