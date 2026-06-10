# praisonai/agents_generator.py

import sys
from .version import __version__
import yaml, os
from rich import print
from dotenv import load_dotenv
from .auto import AutoGenerator
from .inc import PraisonAIModel
import inspect
from pathlib import Path
import importlib
import importlib.util
import os
import logging
import re
import keyword
import difflib

# Import new architecture components
from .framework_adapters.base import FrameworkAdapter
from .framework_adapters.registry import FrameworkAdapterRegistry, get_default_registry
from .tool_registry import ToolRegistry

# Import availability flags
# Compatibility imports - now handled by centralized detection
# (inbuilt_tools still defines these but they're read-only compatibility)

# BaseTool import is now handled centrally by ToolResolver

# Framework availability detection (lazy via __getattr__)
from ._framework_availability import is_available

# Lazy constants mapping for backward compatibility
_AVAIL = {
    "PRAISONAI_TOOLS_AVAILABLE": "praisonai_tools",
    "CREWAI_AVAILABLE": "crewai",
    "AUTOGEN_AVAILABLE": "autogen",
    "AG2_AVAILABLE": "ag2",
    "PRAISONAI_AVAILABLE": "praisonaiagents",
    "AGENTOPS_AVAILABLE": "agentops",
}

__all__ = list(_AVAIL.keys())

def __getattr__(name):
    """Lazy attribute access for framework availability constants.
    
    This allows backward compatibility while avoiding import-time probing.
    Only probes the framework when the constant is actually accessed.
    """
    if name in _AVAIL:
        return is_available(_AVAIL[name])
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __dir__():
    return sorted(set(globals()) | set(_AVAIL))

# Framework adapter registry - now uses proper registry pattern
# This replaces the hardcoded FRAMEWORK_ADAPTERS dict

# Note: OTEL_SDK_DISABLED moved to CLI entry point per issue requirements



def _wrap_with_timeout(tool, timeout_seconds: float):
    """Enforce per-call timeout on a tool, sync or async, without
    leaking the worker thread/task on timeout.
    """
    if timeout_seconds is None or timeout_seconds <= 0 or not callable(tool):
        return tool
    
    import asyncio
    import functools
    import inspect
    import json
    
    if inspect.iscoroutinefunction(tool):
        @functools.wraps(tool)
        async def _async_wrapped(*args, **kwargs):
            try:
                return await asyncio.wait_for(tool(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                return json.dumps({
                    "error": "tool_timeout",
                    "tool": getattr(tool, "__name__", repr(tool)),
                    "timeout_seconds": timeout_seconds,
                })
        return _async_wrapped

    @functools.wraps(tool)
    def _sync_wrapped(*args, **kwargs):
        import queue
        import threading

        result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

        def _runner():
            try:
                result_queue.put((True, tool(*args, **kwargs)))
            except BaseException as exc:
                result_queue.put((False, exc))

        # Daemon thread avoids blocking process shutdown if the tool call hangs.
        worker = threading.Thread(target=_runner, daemon=True)
        worker.start()
        worker.join(timeout_seconds)

        if worker.is_alive():
            return json.dumps({
                "error": "tool_timeout",
                "tool": getattr(tool, "__name__", repr(tool)),
                "timeout_seconds": timeout_seconds,
            })

        try:
            success, payload = result_queue.get_nowait()
        except queue.Empty:
            # Defensive fallback: if the worker exits without publishing a result,
            # avoid blocking indefinitely and surface an execution failure.
            return json.dumps({
                "error": "tool_execution_error",
                "tool": getattr(tool, "__name__", repr(tool)),
                "detail": "worker_exited_without_result",
            })

        if success:
            return payload
        raise payload
    return _sync_wrapped


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

def _resolve_yaml_cli_backend(cli_backend_config, logger):
    """Resolve a YAML ``cli_backend`` field to a CliBackendProtocol instance.
    Deprecated wrapper. Use praisonai.cli_backends.resolve_cli_backend_config directly.
    """
    from praisonai.cli_backends import resolve_cli_backend_config
    return resolve_cli_backend_config(cli_backend_config)


class AgentsGenerator:
    def __init__(self, agent_file, framework, config_list, log_level=None, agent_callback=None, task_callback=None, agent_yaml=None, tools=None, cli_config=None, adapter_registry=None):
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
            cli_config (dict, optional): CLI configuration to override YAML settings. Defaults to None.
            adapter_registry (FrameworkAdapterRegistry, optional): Registry for framework adapters. Defaults to process default.

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
        self.cli_config = cli_config or {}  # Store CLI configuration overrides
        # Use namespaced logger - no hot-path basicConfig calls
        from ._logging import get_logger
        self.logger = get_logger("agents_generator")
        
        # Set level if provided, but don't mutate root logger
        if log_level:
            if isinstance(log_level, str):
                self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
            else:
                self.logger.setLevel(log_level)
        elif os.environ.get('LOGLEVEL'):
            self.logger.setLevel(getattr(logging, os.environ.get('LOGLEVEL', 'INFO').upper(), logging.INFO))
        
        # Keep tool registry for backward compatibility with autogen adapters
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_builtin_autogen_adapters(_suppress_deprecation_warning=True)
        
        # Initialize tool resolver with the registry wired in (single source of truth for tool resolution)
        from .tool_resolver import ToolResolver
        self.tool_resolver = ToolResolver(registry=self.tool_registry)
        
        # DI-friendly: tests/multi-tenant runtimes pass their own registry;
        # CLI users get the process default.
        self._adapter_registry = adapter_registry or get_default_registry()
        
        # Get framework adapter (availability already validated at CLI entry)
        self.framework_adapter = self._get_framework_adapter(framework)

    def _get_framework_adapter(self, framework: str) -> FrameworkAdapter:
        """
        Get the appropriate framework adapter for the given framework.
        
        Args:
            framework: Name of the framework
            
        Returns:
            Framework adapter instance
            
        Raises:
            ValueError: If framework is not supported
        """
        return self._adapter_registry.create(framework)

    def _merge_cli_config(self, config, cli_config):
        """
        Merge CLI configuration with YAML configuration.
        
        CLI configuration takes precedence over YAML configuration for:
        - Global config fields (acp, lsp) -> config.config
        - Agent-level fields (trust, tool_timeout, planning_tools, autonomy, guardrail, approval) -> applied to all agents
        
        Args:
            config (dict): The parsed YAML configuration
            cli_config (dict): The CLI configuration to merge
        """
        self.logger.debug(f"Merging CLI config: {cli_config}")
        
        # Handle global config overrides (acp, lsp)
        if 'acp' in cli_config or 'lsp' in cli_config:
            if 'config' not in config:
                config['config'] = {}
            
            if 'acp' in cli_config:
                config['config']['acp'] = cli_config['acp']
                self.logger.debug(f"CLI override: acp = {cli_config['acp']}")
            
            if 'lsp' in cli_config:
                config['config']['lsp'] = cli_config['lsp'] 
                self.logger.debug(f"CLI override: lsp = {cli_config['lsp']}")
        
        # Handle agent-level overrides using unified approach
        agent_level_fields = ['tool_timeout', 'planning_tools', 'autonomy', 'planning', 'web', 'web_fetch']
        agent_overrides = {k: v for k, v in cli_config.items() if k in agent_level_fields}
        
        # Handle handoff configuration - convert CLI flags into handoff dict
        handoff_fields = ['handoff', 'handoff_policy', 'handoff_timeout', 'handoff_max_depth', 'handoff_max_concurrent', 'handoff_detect_cycles']
        if any(field in cli_config for field in handoff_fields):
            handoff_config = {}
            if 'handoff' in cli_config:
                # Convert comma-separated roles to list
                handoff_roles = [role.strip() for role in cli_config['handoff'].split(',') if role.strip()]
                handoff_config['to'] = handoff_roles
            if 'handoff_policy' in cli_config:
                handoff_config['policy'] = cli_config['handoff_policy']
            if 'handoff_timeout' in cli_config:
                handoff_config['timeout'] = cli_config['handoff_timeout']
            if 'handoff_max_depth' in cli_config:
                handoff_config['max_depth'] = cli_config['handoff_max_depth']
            if 'handoff_max_concurrent' in cli_config:
                handoff_config['max_concurrent'] = cli_config['handoff_max_concurrent']
            if 'handoff_detect_cycles' in cli_config:
                handoff_config['detect_cycles'] = cli_config['handoff_detect_cycles'].lower() == 'true'
            
            if handoff_config:
                agent_overrides['handoff'] = handoff_config
        
        # Handle approval configuration using unified spec
        approval_fields = ['trust', 'approval', 'approve_all_tools', 'approval_timeout', 'approve_level']
        if any(field in cli_config for field in approval_fields):
            from ._approval_spec import ApprovalSpec
            
            # Create a mock args object for CLI parsing
            class MockArgs:
                def __init__(self, cli_config):
                    for field in approval_fields:
                        setattr(self, field, cli_config.get(field))
                    self.guardrail = cli_config.get('guardrail')
            
            spec = ApprovalSpec.from_cli(MockArgs(cli_config))
            if spec.enabled:
                agent_overrides['approval'] = spec.to_dict()
            
        # Handle guardrail separately
        if 'guardrail' in cli_config:
            agent_overrides['guardrails'] = cli_config['guardrail']
        
        if agent_overrides:
            # Apply to all agents in the config
            roles = config.get('roles', {})
            agents = config.get('agents', {})
            
            # Apply to 'roles' section (canonical format)
            for role_name, role_config in roles.items():
                for field, value in agent_overrides.items():
                    role_config[field] = value
                    self.logger.debug(f"CLI override for role {role_name}: {field} = {value}")
            
            # Apply to 'agents' section (backward compatibility)
            for agent_name, agent_config in agents.items():
                for field, value in agent_overrides.items():
                    agent_config[field] = value
                    self.logger.debug(f"CLI override for agent {agent_name}: {field} = {value}")

    def _prepare_for_run(self, config):
        """
        Single source of truth for YAML normalisation, validation,
        CLI-backend compatibility, tool resolution, AutoGen version
        selection, and adapter resolution. Used by BOTH sync and async.
        """
        # Canonical format conversion: 'agents' -> 'roles', 'instructions' -> 'backstory'
        if 'agents' in config and 'roles' not in config:
            config['roles'] = {}
            for agent_name, agent_config in config['agents'].items():
                role_config = dict(agent_config) if agent_config else {}
                # Convert 'instructions' to 'backstory' if present
                if 'instructions' in role_config and 'backstory' not in role_config:
                    role_config['backstory'] = role_config['instructions']
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
        
        # Validate agents configuration for typos in field names
        self._validate_agents_config(config)
        
        # Build tools dictionary using shared logic
        tools_dict = self._build_tools_dict(config)
        
        # Select framework with AutoGen version logic
        framework = self._select_autogen_version(
            self.framework or config.get('framework', 'crewai'),
            config,
        )
        
        # Get and resolve adapter
        adapter = self._get_framework_adapter(framework).resolve()
        
        # Validate framework availability
        from .framework_adapters.validators import assert_framework_available
        assert_framework_available(adapter.name)
        
        # Validate cli_backend compatibility
        self._validate_cli_backend_compatibility(config, framework)
        
        # Initialize observability hooks
        from .observability.hooks import init_observability
        init_observability(adapter.name)
        
        # Run adapter setup hooks
        adapter.setup(framework_tag=adapter.name)
        
        # Update framework reference if resolution changed it
        self.framework = adapter.name
        self.framework_adapter = adapter
        
        return {
            'adapter': adapter,
            'config': config,
            'topic': topic,
            'tools_dict': tools_dict,
        }
    
    def _build_tools_dict(self, config):
        """Shared tool resolution logic for sync and async paths."""
        tools_dict = {}
        
        # Demand-driven tool resolution - only resolve tools actually used in YAML
        if is_available("crewai") or is_available("autogen") or is_available("praisonaiagents") or is_available("ag2"):
            try:
                # Collect all tool names mentioned in the YAML config
                needed_tools: set[str] = set()
                for role_cfg in config.get('roles', {}).values():
                    for t in role_cfg.get('tools') or []:
                        if isinstance(t, str) and t.strip():
                            needed_tools.add(t.strip())
                    for task_cfg in (role_cfg.get('tasks') or {}).values():
                        if not isinstance(task_cfg, dict):
                            continue
                        for t in task_cfg.get('tools') or []:
                            if isinstance(t, str) and t.strip():
                                needed_tools.add(t.strip())

                # Resolve only the tools actually referenced in YAML
                for tool_name in needed_tools:
                    try:
                        resolved_tool = self.tool_resolver.resolve(tool_name)
                        if resolved_tool is None:
                            self.logger.warning(f"Tool '{tool_name}' not found")
                            continue
                        tools_dict[tool_name] = (
                            resolved_tool() if inspect.isclass(resolved_tool) else resolved_tool
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize tool '{tool_name}': {e}")
                        continue
                            
            except Exception as e:
                self.logger.warning(f"Error collecting YAML tool references: {e}")
            
            # Add tools from class names - use tool_resolver to check tool validity
            for tool_class in self.tools:
                if isinstance(tool_class, type):
                    try:
                        tool_instance = tool_class()
                        tool_name = tool_class.__name__
                        tools_dict[tool_name] = tool_instance
                        self.logger.debug(f"Added tool: {tool_name}")
                    except Exception as e:
                        self.logger.warning(f"Failed to instantiate tool class {tool_class.__name__}: {e}")

        root_directory = os.getcwd()
        tools_py_path = os.path.join(root_directory, 'tools.py')
        tools_dir_path = Path(root_directory) / 'tools'
        
        # Use consolidated ToolResolver for tools.py loading
        tools_dict.update(self.tool_resolver.get_local_tool_classes())
        if os.path.isfile(tools_py_path):
            self.logger.debug("tools.py exists in the root directory. Loading tools.py and skipping tools folder.")
        elif tools_dir_path.is_dir():
            tools_dict.update(self.tool_resolver.get_local_tool_classes_from_dir(tools_dir_path))
            if tools_dict:
                self.logger.debug("tools folder exists in the root directory")
        
        return tools_dict
    
    def _select_autogen_version(self, framework, config):
        """Shared AutoGen version selection logic for sync and async paths."""
        if framework == "autogen":
            autogen_v4_adapter = self._get_framework_adapter("autogen_v4")
            autogen_v2_adapter = self._get_framework_adapter("autogen")
            
            autogen_version = str(
                config.get('autogen_version', os.environ.get("AUTOGEN_VERSION", "auto"))
            ).lower()
            use_v4 = False
            
            if autogen_version == "v0.4" and autogen_v4_adapter.is_available():
                use_v4 = True
            elif autogen_version == "v0.2" and autogen_v2_adapter.is_available():
                use_v4 = False
            elif autogen_version == "auto":
                use_v4 = autogen_v4_adapter.is_available()
            else:
                use_v4 = autogen_v4_adapter.is_available() and not autogen_v2_adapter.is_available()
            
            framework = "autogen_v4" if use_v4 else "autogen"
        
        # Initialize AgentOps if configured
        agentops_api_key = os.getenv("AGENTOPS_API_KEY")
        if agentops_api_key:
            try:
                import agentops
                agentops.init(agentops_api_key, default_tags=[framework])
            except ImportError:
                pass
        
        return framework
    
    def _validate_cli_backend_compatibility(self, config, framework):
        """Validate that cli_backend is only used with compatible frameworks."""
        # Check if any agent/role defines cli_backend (support both key names)
        all_entities = {
            **config.get('roles', {}),
            **config.get('agents', {}),
        }
        has_cli_backend = any(
            isinstance(details, dict) and details.get('cli_backend')
            for details in all_entities.values()
        )
        
        if has_cli_backend and framework != 'praisonai':
            self.logger.error(
                f"cli_backend is not supported for framework='{framework}'. "
                f"Remove cli_backend from your YAML or switch to framework='praisonai'."
            )
            raise ValueError(
                f"cli_backend requires framework='praisonai', but framework='{framework}' was specified"
            )

    def _validate_agents_config(self, config):
        """
        Validate agent configuration for typos in field names and provide suggestions.
        
        Args:
            config (dict): The parsed YAML configuration
        """
        known_fields = {
            'role', 'goal', 'instructions', 'backstory', 'tools', 'toolsets', 'tasks', 'llm',
            'function_calling_llm', 'allow_delegation', 'max_iter', 'max_rpm',
            'max_execution_time', 'verbose', 'cache', 'system_template',
            'prompt_template', 'response_template', 'tool_timeout', 'planning_tools',
            'planning', 'autonomy', 'guardrails', 'streaming', 'stream',
            'approval', 'skills', 'cli_backend', 'reflection', 'handoff', 'web', 'web_fetch'
        }

        for section_name in ('agents', 'roles'):
            section = config.get(section_name, {})
            if not isinstance(section, dict):
                continue

            entity_name = 'agent' if section_name == 'agents' else 'role'
            for name, section_config in section.items():
                if not isinstance(section_config, dict):
                    continue

                for field_name in section_config:
                    if field_name in known_fields:
                        continue

                    close_matches = difflib.get_close_matches(
                        field_name,
                        known_fields,
                        n=1,
                        cutoff=0.6
                    )
                    suggestion = f" Did you mean '{close_matches[0]}'?" if close_matches else ""
                    self.logger.warning(
                        f"Unknown field '{field_name}' in {entity_name} '{name}'.{suggestion}"
                    )

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
        Load function tools from a user-supplied module (gated by PRAISONAI_ALLOW_LOCAL_TOOLS).

        Parameters:
            module_path (str): The path to the module containing the tools.

        Returns:
            dict: A dictionary containing the names of the tools as keys and the corresponding functions or objects as values.
                  Returns an empty dict if the module cannot be loaded (path missing, loading blocked by PRAISONAI_ALLOW_LOCAL_TOOLS, or any other load error).
        """
        from ._safe_loader import load_user_module
        module = load_user_module(module_path, name="tools_module")
        if module is None:
            return {}
        return {name: obj for name, obj in inspect.getmembers(module, self.is_function_or_decorated)}
    
    def load_tools_from_module_class(self, module_path):
        """
        Load BaseTool / langchain tool classes from a user-supplied module (gated by PRAISONAI_ALLOW_LOCAL_TOOLS).
        """
        from ._safe_loader import load_user_module
        module = load_user_module(module_path, name="tools_module")
        if module is None:
            return {}
        return self.tool_resolver._extract_tool_classes(module)

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

        # Apply CLI configuration overrides to YAML config
        if self.cli_config:
            # Merge CLI configuration with YAML config
            self._merge_cli_config(config, self.cli_config)

        # Check if this is a workflow-mode YAML (process: workflow or has steps section)
        process_type = config.get('process', 'sequential')
        has_steps = 'steps' in config
        has_workflow_config = 'workflow' in config
        
        if process_type == 'workflow' or (has_steps and has_workflow_config):
            # Route to YAMLWorkflowParser for advanced workflow patterns
            return self._run_yaml_workflow(config)

        # Use shared preparation logic
        prep = self._prepare_for_run(config)
        
        self.logger.info(f"Using framework: {prep['adapter'].name}")
        return prep['adapter'].run(
            prep['config'],
            self.config_list,
            prep['topic'],
            tools_dict=prep['tools_dict'],
            agent_callback=getattr(self, 'agent_callback', None),
            task_callback=getattr(self, 'task_callback', None),
            cli_config=getattr(self, 'cli_config', None),
        )

    async def agenerate_crew_and_kickoff(self):
        """
        Async version of generate_crew_and_kickoff.
        Generates a crew of agents and initiates tasks based on the provided configuration.
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

        # Apply CLI configuration overrides to YAML config
        if self.cli_config:
            # Merge CLI configuration with YAML config
            self._merge_cli_config(config, self.cli_config)

        # Check if this is a workflow-mode YAML (process: workflow or has steps section)
        process_type = config.get('process', 'sequential')
        has_steps = 'steps' in config
        has_workflow_config = 'workflow' in config
        
        if process_type == 'workflow' or (has_steps and has_workflow_config):
            return await self._arun_yaml_workflow(config)
        else:
            return await self._arun_framework(config)

    async def _arun_framework(self, config):
        """Async version of _run_framework with shared preparation logic."""
        # Use shared preparation logic
        prep = self._prepare_for_run(config)
        
        self.logger.info(f"Using framework: {prep['adapter'].name}")
        return await prep['adapter'].arun(
            prep['config'],
            self.config_list,
            prep['topic'],
            tools_dict=prep['tools_dict'],
            agent_callback=getattr(self, 'agent_callback', None),
            task_callback=getattr(self, 'task_callback', None),
            cli_config=getattr(self, 'cli_config', None),
        )

    async def _arun_yaml_workflow(self, config):
        """
        Async version of _run_yaml_workflow using YAMLWorkflowParser.
        
        This method handles agents.yaml files that have:
        - process: workflow
        
        Args:
            config: YAML configuration dictionary
            
        Returns:
            str: Workflow execution result
        """
        if not is_available("praisonaiagents"):
            raise ImportError("PraisonAI is not installed. Please install it with 'pip install praisonaiagents'")
        
        try:
            from praisonaiagents.workflows import YAMLWorkflowParser
        except ImportError as err:
            raise ImportError("YAMLWorkflowParser not available. Please update praisonaiagents.") from err
        
        # Ensure name is present
        if 'name' not in config:
            config['name'] = config.get('topic', 'Workflow')
        
        # Pass model from config_list to workflow as default_llm
        if self.config_list and self.config_list[0].get('model'):
            model_from_cli = self.config_list[0]['model']
            if 'workflow' not in config:
                config['workflow'] = {}
            if 'default_llm' not in config['workflow']:
                config['workflow']['default_llm'] = model_from_cli
        
        import yaml as yaml_module
        yaml_content = yaml_module.dump(config, default_flow_style=False)
        
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        input_data = config.get('input', config.get('topic', ''))
        
        self.logger.info(f"Starting async YAML workflow with topic: {input_data}")
        
        if hasattr(workflow, 'astart'):
            result = await workflow.astart(input_data)
        else:
            import asyncio
            result = await asyncio.to_thread(workflow.start, input_data)
            
        if result.get("status") == "completed":
            return result.get("output", "Workflow completed successfully")
        else:
            return f"Workflow failed: {result.get('error', 'Unknown error')}"

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
        if not is_available("praisonaiagents"):
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


# Standalone function for backward compatibility with tests
def safe_format(template, **kwargs):
    """
    Safe string formatting that preserves JSON/dict literals while substituting variables.
    
    This function only substitutes placeholders that look like identifiers (e.g., {topic})
    while preserving JSON structures like {"level": 2}.
    
    Args:
        template (str): Template string with placeholders
        **kwargs: Values to substitute
        
    Returns:
        str: Formatted string with safe substitutions
    """
    # Use the same regex-based substitution logic as BaseFrameworkAdapter._format_template
    def replace_placeholder(match):
        placeholder = match.group(1)
        return str(kwargs.get(placeholder, match.group(0)))
    
    # Only replace placeholders that look like identifiers
    return re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', replace_placeholder, template)
