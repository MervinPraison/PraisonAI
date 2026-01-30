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
import re
import keyword

# Framework-specific imports with availability checks
CREWAI_AVAILABLE = False
AUTOGEN_AVAILABLE = False
AUTOGEN_V4_AVAILABLE = False
PRAISONAI_TOOLS_AVAILABLE = False
AGENTOPS_AVAILABLE = False
PRAISONAI_AVAILABLE = False

try:
    from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, Agents
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
    from autogen_agentchat.agents import AssistantAgent as AutoGenV4AssistantAgent
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
    from autogen_agentchat.messages import TextMessage
    from autogen_core import CancellationToken
    AUTOGEN_V4_AVAILABLE = True
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


def safe_format(template: str, **kwargs) -> str:
    """
    Safely format a string template, preserving JSON-like curly braces.
    
    This handles cases where templates contain Gutenberg block syntax like
    {"level":2} which would cause KeyError with standard .format().
    
    Uses a two-pass approach:
    1. Escape all {{ and }} (already escaped braces)
    2. Only substitute known variable placeholders
    
    Args:
        template: String template with {variable} placeholders
        **kwargs: Variable substitutions to apply
        
    Returns:
        Formatted string with variables substituted and JSON preserved
        
    Example:
        >>> safe_format('Use <!-- wp:heading {"level":2} --> for {topic}', topic='AI')
        'Use <!-- wp:heading {"level":2} --> for AI'
    """
    import re
    
    # Pattern to match {word} but not {"key": or {number} patterns
    # This matches simple variable names like {topic}, {style}, etc.
    def replace_var(match):
        var_name = match.group(1)
        if var_name in kwargs:
            return str(kwargs[var_name])
        # If not in kwargs, leave it as-is (don't raise KeyError)
        return match.group(0)
    
    # Match {variable_name} where variable_name is a valid Python identifier
    # but NOT {" (JSON start) or {number (like {2})
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    
    return re.sub(pattern, replace_var, template)


def noop(*args, **kwargs):
    pass

def sanitize_agent_name_for_autogen_v4(name):
    """
    Sanitize agent name to be a valid Python identifier for AutoGen v0.4.
    
    Args:
        name (str): The original agent name
        
    Returns:
        str: A valid Python identifier
    """
    # Convert to string and replace invalid characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
    
    # Collapse only very excessive underscores (5 or more) to reduce extreme cases
    sanitized = re.sub(r'_{5,}', '_', sanitized)
    
    # Remove trailing underscores only if not part of a dunder pattern and only if singular
    if sanitized.endswith('_') and not sanitized.endswith('__') and sanitized != '_':
        sanitized = sanitized.rstrip('_')
    
    # Ensure it starts with a letter or underscore (not a digit)
    if sanitized and sanitized[0].isdigit():
        sanitized = 'agent_' + sanitized
    
    # Handle empty string or only invalid characters (including single underscore from all invalid chars)
    if not sanitized or sanitized == '_':
        sanitized = 'agent'
    
    # Check if it's a Python keyword and append underscore if so
    if keyword.iskeyword(sanitized):
        sanitized += '_'
    
    return sanitized

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
        elif framework == "autogen" and not (AUTOGEN_AVAILABLE or AUTOGEN_V4_AVAILABLE):
            raise ImportError("AutoGen is not installed. Please install it with 'pip install praisonai[autogen]' for v0.2 or 'pip install praisonai[autogen-v4]' for v0.4")
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

        # Check if this is a workflow-mode YAML (process: workflow or has steps section)
        process_type = config.get('process', 'sequential')
        has_steps = 'steps' in config
        has_workflow_config = 'workflow' in config
        
        if process_type == 'workflow' or (has_steps and has_workflow_config):
            # Route to YAMLWorkflowParser for advanced workflow patterns
            return self._run_yaml_workflow(config)

        # Canonical format conversion: 'agents' -> 'roles', 'instructions' -> 'backstory'
        # This ensures backward compatibility while supporting the new canonical format
        if 'agents' in config and 'roles' not in config:
            config['roles'] = {}
            for agent_name, agent_config in config['agents'].items():
                role_config = dict(agent_config) if agent_config else {}
                # Convert 'instructions' to 'backstory' if present
                if 'instructions' in role_config and 'backstory' not in role_config:
                    role_config['backstory'] = role_config.pop('instructions')
                # Ensure required fields have defaults
                if 'role' not in role_config:
                    role_config['role'] = agent_name.replace('_', ' ').title()
                if 'goal' not in role_config:
                    role_config['goal'] = role_config.get('backstory', 'Complete the assigned task')
                if 'backstory' not in role_config:
                    role_config['backstory'] = f'You are a {role_config["role"]}'
                config['roles'][agent_name] = role_config

        # Get workflow input: 'input' is canonical, 'topic' is alias for backward compatibility
        topic = config.get('input', config.get('topic', ''))
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
            if not (AUTOGEN_AVAILABLE or AUTOGEN_V4_AVAILABLE):
                raise ImportError("AutoGen is not installed. Please install it with 'pip install praisonai[autogen]' for v0.2 or 'pip install praisonai[autogen-v4]' for v0.4")
            
            # Choose autogen version based on availability and environment preference
            # AUTOGEN_VERSION can be set to "v0.2" or "v0.4" to force a specific version
            autogen_version = os.environ.get("AUTOGEN_VERSION", "auto").lower()
            
            use_v4 = False
            if autogen_version == "v0.4" and AUTOGEN_V4_AVAILABLE:
                use_v4 = True
            elif autogen_version == "v0.2" and AUTOGEN_AVAILABLE:
                use_v4 = False
            elif autogen_version == "auto":
                # Default preference: use v0.4 if available, fallback to v0.2
                use_v4 = AUTOGEN_V4_AVAILABLE
            else:
                # Fallback to whatever is available
                use_v4 = AUTOGEN_V4_AVAILABLE and not AUTOGEN_AVAILABLE
            
            if AGENTOPS_AVAILABLE:
                version_tag = "autogen-v4" if use_v4 else "autogen-v2"
                agentops.init(os.environ.get("AGENTOPS_API_KEY"), default_tags=[version_tag])
            
            if use_v4:
                self.logger.info("Using AutoGen v0.4")
                return self._run_autogen_v4(config, topic, tools_dict)
            else:
                self.logger.info("Using AutoGen v0.2")
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

    def _run_yaml_workflow(self, config):
        """
        Run a YAML workflow using the YAMLWorkflowParser.
        
        This method handles agents.yaml files that have:
        - process: workflow
        - steps section with workflow patterns (route, parallel, loop, repeat)
        
        Args:
            config (dict): The parsed YAML configuration
            
        Returns:
            str: Result of the workflow execution
        """
        if not PRAISONAI_AVAILABLE:
            raise ImportError("PraisonAI is not installed. Please install it with 'pip install praisonaiagents'")
        
        try:
            from praisonaiagents.workflows import YAMLWorkflowParser
        except ImportError:
            raise ImportError("YAMLWorkflowParser not available. Please update praisonaiagents.")
        
        # Ensure name is present (YAMLWorkflowParser handles roles->agents conversion)
        if 'name' not in config:
            config['name'] = config.get('topic', 'Workflow')
        
        # Pass model from config_list to workflow as default_llm
        if self.config_list and self.config_list[0].get('model'):
            model_from_cli = self.config_list[0]['model']
            # Set default_llm in workflow config if not already set
            if 'workflow' not in config:
                config['workflow'] = {}
            if 'default_llm' not in config['workflow']:
                config['workflow']['default_llm'] = model_from_cli
        
        # Convert config back to YAML string for parser
        # Note: YAMLWorkflowParser handles 'roles' to 'agents' conversion internally
        import yaml as yaml_module
        yaml_content = yaml_module.dump(config, default_flow_style=False)
        
        # Parse and execute
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Get input: 'input' is canonical, 'topic' is alias for backward compatibility
        input_data = config.get('input', config.get('topic', ''))
        
        # Execute workflow
        self.logger.debug(f"Running workflow: {workflow.name}")
        result = workflow.start(input_data)
        
        if result.get("status") == "completed":
            return result.get("output", "Workflow completed successfully")
        else:
            return f"Workflow failed: {result.get('error', 'Unknown error')}"

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
            agent_name = safe_format(details['role'], topic=topic).replace("{topic}", topic)
            agent_goal = safe_format(details['goal'], topic=topic)
            
            # Create AutoGen assistant agent
            agents[role] = autogen.AssistantAgent(
                name=agent_name,
                llm_config=llm_config,
                system_message=safe_format(details['backstory'], topic=topic) + 
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
                description_filled = safe_format(task_details['description'], topic=topic)
                expected_output_filled = safe_format(task_details['expected_output'], topic=topic)
                
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

    def _run_autogen_v4(self, config, topic, tools_dict):
        """
        Run agents using the AutoGen v0.4 framework with async, event-driven architecture.
        
        Args:
            config (dict): Configuration dictionary
            topic (str): The topic to process
            tools_dict (dict): Dictionary of available tools
            
        Returns:
            str: Result of the agent interactions
        """
        import asyncio
        
        async def run_autogen_v4_async():
            # Create model client for v0.4
            model_config = self.config_list[0] if self.config_list else {}
            model_client = OpenAIChatCompletionClient(
                model=model_config.get('model', 'gpt-5-nano'),
                api_key=model_config.get('api_key', os.environ.get("OPENAI_API_KEY")),
                base_url=model_config.get('base_url', "https://api.openai.com/v1")
            )
            
            agents = []
            combined_tasks = []
            
            # Create agents from config
            for role, details in config['roles'].items():
                # For AutoGen v0.4, ensure agent name is a valid Python identifier
                agent_name = safe_format(details['role'], topic=topic).replace("{topic}", topic)
                agent_name = sanitize_agent_name_for_autogen_v4(agent_name)
                backstory = safe_format(details['backstory'], topic=topic)
                
                # Convert tools for v0.4 - simplified tool passing
                agent_tools = []
                for tool_name in details.get('tools', []):
                    if tool_name in tools_dict:
                        tool_instance = tools_dict[tool_name]
                        # For v0.4, we can pass the tool's run method directly if it's callable
                        if hasattr(tool_instance, 'run') and callable(tool_instance.run):
                            agent_tools.append(tool_instance.run)
                
                # Create v0.4 AssistantAgent
                assistant = AutoGenV4AssistantAgent(
                    name=agent_name,
                    system_message=backstory + ". Must reply with 'TERMINATE' when the task is complete.",
                    model_client=model_client,
                    tools=agent_tools,
                    reflect_on_tool_use=True
                )
                
                agents.append(assistant)
                
                # Collect all task descriptions for sequential execution
                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = safe_format(task_details['description'], topic=topic)
                    combined_tasks.append(description_filled)
            
            if not agents:
                return "No agents created from configuration"
            
            # Create termination conditions
            text_termination = TextMentionTermination("TERMINATE")
            max_messages_termination = MaxMessageTermination(max_messages=20)
            termination_condition = text_termination | max_messages_termination
            
            # Create RoundRobinGroupChat for parallel/sequential execution
            group_chat = RoundRobinGroupChat(
                agents,
                termination_condition=termination_condition,
                max_turns=len(agents) * 3  # Allow multiple rounds
            )
            
            # Combine all tasks into a single task description
            task_description = f"Topic: {topic}\n\nTasks to complete:\n" + "\n".join(
                f"{i+1}. {task}" for i, task in enumerate(combined_tasks)
            )
            
            # Run the group chat
            try:
                result = await group_chat.run(task=task_description)
                
                # Extract the final message content
                if result.messages:
                    final_message = result.messages[-1]
                    if hasattr(final_message, 'content'):
                        return f"### AutoGen v0.4 Output ###\n{final_message.content}"
                    else:
                        return f"### AutoGen v0.4 Output ###\n{str(final_message)}"
                else:
                    return "### AutoGen v0.4 Output ###\nNo messages generated"
                    
            except Exception as e:
                self.logger.error(f"Error in AutoGen v0.4 execution: {str(e)}")
                return f"### AutoGen v0.4 Error ###\n{str(e)}"
            
            finally:
                # Close the model client
                await model_client.close()
        
        # Run the async function
        try:
            return asyncio.run(run_autogen_v4_async())
        except Exception as e:
            self.logger.error(f"Error running AutoGen v0.4: {str(e)}")
            return f"### AutoGen v0.4 Error ###\n{str(e)}"

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
            role_filled = safe_format(details['role'], topic=topic)
            goal_filled = safe_format(details['goal'], topic=topic)
            backstory_filled = safe_format(details['backstory'], topic=topic)
            
            # Get agent tools
            agent_tools = [tools_dict[tool] for tool in details.get('tools', []) 
                         if tool in tools_dict]
            
            # Configure LLM
            llm_model = details.get('llm')
            if llm_model:
                llm = PraisonAIModel(
                    model=llm_model.get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-5-nano",
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
                    model=function_calling_llm_model.get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-5-nano",
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
                description_filled = safe_format(task_details['description'], topic=topic)
                expected_output_filled = safe_format(task_details['expected_output'], topic=topic)

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
        
        Tool resolution order:
        1. Local tools.py (backward compat, custom tools)
        2. YAML tools: field resolved via ToolResolver
        3. Built-in tools from praisonaiagents.tools
        """
        agents = {}
        tasks = []
        tasks_dict = {}

        # Import tool resolver (lazy import to avoid circular deps)
        from praisonai.tool_resolver import ToolResolver
        tool_resolver = ToolResolver()
        
        # Load tools from local tools.py (backward compat)
        tools_list = self.load_tools_from_tools_py()
        self.logger.debug(f"Loaded tools from tools.py: {tools_list}")

        # Create agents from config
        for role, details in config['roles'].items():
            role_filled = safe_format(details['role'], topic=topic)
            goal_filled = safe_format(details['goal'], topic=topic)
            backstory_filled = safe_format(details['backstory'], topic=topic)
            
            # Resolve tools for this agent from YAML tools: field
            yaml_tool_names = details.get('tools', [])
            agent_tools = list(tools_list)  # Start with local tools.py tools
            
            if yaml_tool_names:
                # Resolve each tool name from YAML
                for tool_name in yaml_tool_names:
                    if not tool_name or not isinstance(tool_name, str):
                        continue
                    tool_name = tool_name.strip()
                    
                    # Check if already in tools_list (from tools.py)
                    already_loaded = any(
                        getattr(t, '__name__', None) == tool_name or 
                        getattr(t, 'name', None) == tool_name
                        for t in agent_tools
                    )
                    
                    if not already_loaded:
                        resolved_tool = tool_resolver.resolve(tool_name)
                        if resolved_tool is not None:
                            agent_tools.append(resolved_tool)
                            self.logger.debug(f"Resolved tool '{tool_name}' for agent {role}")
                        else:
                            self.logger.warning(f"Tool '{tool_name}' not found for agent {role}")
            
            # Get LLM from config or environment
            llm_config = details.get('llm', {})
            llm_model = llm_config.get("model") if isinstance(llm_config, dict) else llm_config
            llm_model = llm_model or os.environ.get("MODEL_NAME") or "gpt-4o-mini"
            
            agent = PraisonAgent(
                name=role_filled,
                role=role_filled,
                goal=goal_filled,
                backstory=backstory_filled,
                instructions=details.get('instructions'),
                tools=agent_tools,  # Pass resolved tools to the agent
                allow_delegation=details.get('allow_delegation', False),
                llm=llm_model,
                reflection=details.get('reflection', False),
            )
            
            if self.agent_callback:
                agent.step_callback = self.agent_callback

            agents[role] = agent
            self.logger.debug(f"Created agent {role_filled} with tools: {agent.tools}")

            # Create tasks for the agent
            agent_tasks = details.get('tasks', {})
            
            # If no tasks defined, auto-generate one from instructions/backstory
            if not agent_tasks:
                # Use instructions or backstory as the task description
                task_description = details.get('instructions') or backstory_filled
                auto_task = PraisonTask(
                    description=task_description,
                    expected_output="Complete the assigned task successfully.",
                    agent=agent,
                )
                tasks.append(auto_task)
                tasks_dict[f"{role}_auto_task"] = auto_task
                self.logger.debug(f"Auto-generated task for agent {role_filled}")
            else:
                for task_name, task_details in agent_tasks.items():
                    description_filled = safe_format(task_details['description'], topic=topic)
                    expected_output_filled = safe_format(task_details['expected_output'], topic=topic)

                    task = PraisonTask(
                        description=description_filled,
                        expected_output=expected_output_filled,
                        agent=agent,
                        tools=agent_tools,  # Pass resolved tools to the task
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
            agents = AgentManager(
                agents=list(agents.values()),
                tasks=tasks,
                process="hierarchical",
                manager_llm=config.get('manager_llm') or os.environ.get("MODEL_NAME") or "gpt-4o-mini",
                memory=memory
            )
        else:
            agents = AgentManager(
                agents=list(agents.values()),
                tasks=tasks,
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