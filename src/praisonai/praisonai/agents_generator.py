# praisonai/agents_generator.py

import sys
import os
import inspect
import logging
import threading
import re
import keyword
import difflib
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, Any, Optional, List

from .version import __version__

# Import new architecture components
from .framework_adapters.base import FrameworkAdapter
from .framework_adapters.registry import FrameworkAdapterRegistry, get_default_registry

logger = logging.getLogger("praisonai.agents_generator")


def _rich_print(*args, **kwargs):
    """Lazy alias for rich.print — pays the import cost only on first use."""
    from rich import print as _rp
    return _rp(*args, **kwargs)


def _yaml_safe_load(stream):
    """Lazy alias for yaml.safe_load."""
    import yaml
    return yaml.safe_load(stream)


def _get_default_adapter_registry():
    """Lazy import for the adapter registry — defers entry-point discovery."""
    from .framework_adapters.registry import get_default_registry
    return get_default_registry()

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



_DEFAULT_TOOL_TIMEOUT_WORKERS = 32


def _resolve_tool_timeout_workers():
    """Resolve the timeout worker count, tolerating a bad env value.

    A typo or non-positive ``PRAISONAI_TOOL_TIMEOUT_WORKERS`` must not crash
    every timed tool call; we warn and fall back to the safe default instead.
    """
    raw = os.environ.get("PRAISONAI_TOOL_TIMEOUT_WORKERS")
    if raw is None:
        return _DEFAULT_TOOL_TIMEOUT_WORKERS
    try:
        workers = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid PRAISONAI_TOOL_TIMEOUT_WORKERS=%r; using default of %d.",
            raw, _DEFAULT_TOOL_TIMEOUT_WORKERS,
        )
        return _DEFAULT_TOOL_TIMEOUT_WORKERS
    if workers < 1:
        logger.warning(
            "PRAISONAI_TOOL_TIMEOUT_WORKERS must be >= 1 (got %d); using default of %d.",
            workers, _DEFAULT_TOOL_TIMEOUT_WORKERS,
        )
        return _DEFAULT_TOOL_TIMEOUT_WORKERS
    return workers


def _wrap_with_timeout(tool, timeout_seconds: float, executor_factory):
    """Enforce a per-call timeout on a tool, sync or async.

    For async tools the underlying task is cancelled on timeout. For sync tools
    the call runs in an instance-owned bounded thread pool obtained from
    ``executor_factory``; on timeout we best-effort cancel the future and log a
    warning. Note: a synchronous call that has already started cannot be forcibly
    interrupted, so background work may continue executing — the returned payload
    flags this with ``background_work_may_continue``.
    """
    if timeout_seconds is None or timeout_seconds <= 0 or not callable(tool):
        return tool
    
    import asyncio
    import concurrent.futures
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
        executor = executor_factory()
        future = executor.submit(tool, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            # Best-effort cancel; only effective if the future has not started.
            # A started sync call cannot be interrupted, so warn operators that
            # the worker may keep running (and its side effects may still occur).
            cancelled = future.cancel()
            logger.warning(
                "Tool %r exceeded %.1fs (cancel=%s); worker may continue "
                "executing in the background.",
                getattr(tool, "__name__", repr(tool)),
                timeout_seconds, cancelled,
            )
            return json.dumps({
                "error": "tool_timeout",
                "tool": getattr(tool, "__name__", repr(tool)),
                "timeout_seconds": timeout_seconds,
                "background_work_may_continue": not cancelled,
            })
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
    def __init__(self, agent_file, framework, config_list, log_level=None, agent_callback=None, task_callback=None, agent_yaml=None, tools=None, cli_config=None, adapter_registry=None, tool_timeout_executor=None):
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
        
        # Initialize tool resolver (single source of truth for tool resolution)
        from .tool_resolver import ToolResolver
        self.tool_resolver = ToolResolver()
        
        # DI-friendly: tests/multi-tenant runtimes pass their own registry;
        # CLI users get the process default.
        self._adapter_registry = adapter_registry or _get_default_adapter_registry()

        # Instance-owned tool-timeout executor so multi-tenant runtimes can scope
        # it per session (no process-wide singleton). Created lazily on first use
        # to avoid spawning threads for generators that never time a sync tool.
        # A caller-supplied executor is treated as borrowed and never shut down.
        self._tool_timeout_executor = tool_timeout_executor
        self._owns_tool_timeout_executor = tool_timeout_executor is None
        self._tool_timeout_executor_lock = threading.Lock()
        
        # Defer framework adapter creation until YAML is loaded
        # This fixes the issue where empty framework string fails before YAML framework is read
        self.framework_adapter = None

    def _get_tool_timeout_executor(self):
        """Lazily create this generator's bounded sync-tool-timeout thread pool.

        The pool is owned by the instance (not a module global), so concurrent
        sessions / tenants never share workers and a stuck tool in one session
        cannot starve another.
        """
        import concurrent.futures

        with self._tool_timeout_executor_lock:
            if self._tool_timeout_executor is None:
                self._tool_timeout_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=_resolve_tool_timeout_workers(),
                    thread_name_prefix=f"praisonai-tool-timeout-{id(self):x}",
                )
            # Capture the reference inside the lock so a concurrent close() can
            # never null the attribute out between the check and the return.
            return self._tool_timeout_executor

    def _wrap_tool_with_timeout(self, tool, timeout_seconds):
        """Wrap a tool with this generator's instance-owned timeout executor."""
        return _wrap_with_timeout(tool, timeout_seconds, self._get_tool_timeout_executor)

    def close(self):
        """Release the owned tool-timeout executor; safe to call repeatedly."""
        with self._tool_timeout_executor_lock:
            if self._owns_tool_timeout_executor and self._tool_timeout_executor is not None:
                self._tool_timeout_executor.shutdown(wait=False, cancel_futures=True)
                self._tool_timeout_executor = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

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
        agent_level_fields = ['tool_timeout', 'tool_retry_policy', 'planning_tools', 'autonomy', 'planning', 'web', 'web_fetch']
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
        
        # Select framework and resolve adapter variant
        framework_name = self.framework or config.get('framework', 'praisonai')
        adapter = self._select_framework(framework_name, config)
        
        # Validate framework availability
        from .framework_adapters.validators import assert_framework_available
        assert_framework_available(adapter.name)
        
        # Validate cli_backend compatibility
        self._validate_cli_backend_compatibility(config, adapter.name)
        
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
        tools_dict = self.tool_resolver.resolve_all_from_yaml(config)
        for tool_class in self.tools:
            if isinstance(tool_class, type):
                try:
                    tools_dict[tool_class.__name__] = tool_class()
                except (TypeError, ValueError, RuntimeError) as e:
                    self.logger.warning(f"Failed to instantiate tool class {tool_class.__name__}: {e}")
        return tools_dict
    
    def _select_framework(self, framework: str, config: Dict[str, Any]) -> Any:
        """Select and resolve the appropriate framework adapter.
        
        Args:
            framework: The base framework name (e.g., "autogen", "crewai")
            config: Framework configuration
            
        Returns:
            The resolved FrameworkAdapter instance
        """
        # Get the base adapter
        adapter = self._get_framework_adapter(framework)
        
        # Let the adapter resolve its own variant using the standardized resolve() method
        # This replaces the old resolve_variant approach and follows the Protocol
        resolved_adapter = adapter.resolve(config=config)
        
        return resolved_adapter
    
    def _validate_cli_backend_compatibility(self, config, framework):
        """Validate that cli_backend and runtime are only used with compatible frameworks."""
        # Check if any agent/role defines cli_backend or runtime
        all_entities = {
            **config.get('roles', {}),
            **config.get('agents', {}),
        }
        
        has_cli_backend = any(
            isinstance(details, dict) and details.get('cli_backend')
            for details in all_entities.values()
        )
        
        has_runtime = any(
            isinstance(details, dict) and details.get('runtime')
            for details in all_entities.values()
        )
        
        # Check for model-scoped runtime in models section
        has_model_runtime = False
        models_config = config.get('models', {})
        if isinstance(models_config, dict):
            has_model_runtime = any(
                isinstance(model_config, dict) and model_config.get('runtime')
                for model_config in models_config.values()
            )
        
        # Check for provider-scoped runtime in providers section
        has_provider_runtime = False
        providers_config = config.get('providers', {})
        if isinstance(providers_config, dict):
            has_provider_runtime = any(
                isinstance(provider_config, dict) and provider_config.get('runtime_default')
                for provider_config in providers_config.values()
            )
        
        if (has_cli_backend or has_runtime or has_model_runtime or has_provider_runtime) and framework != 'praisonai':
            runtime_features = []
            if has_cli_backend:
                runtime_features.append('cli_backend')
            if has_runtime:
                runtime_features.append('runtime')
            if has_model_runtime:
                runtime_features.append('models.*.runtime')
            if has_provider_runtime:
                runtime_features.append('providers.*.runtime_default')
            
            features_str = ', '.join(runtime_features)
            self.logger.error(
                f"Runtime features ({features_str}) are not supported for framework='{framework}'. "
                f"Remove these fields from your YAML or switch to framework='praisonai'."
            )
            raise ValueError(
                f"Runtime features require framework='praisonai', but framework='{framework}' was specified"
            )

    def _validate_agents_config(self, config):
        """
        Validate agent configuration with fail-fast validation and aggregated errors.
        
        Args:
            config (dict): The parsed YAML configuration
            
        Raises:
            ValueError: If configuration has validation errors
        """
        # Use the new comprehensive validator
        from .config.validator import ConfigValidator
        
        # Use existing tool resolver if available
        validator = ConfigValidator(tool_resolver=self.tool_resolver)
        
        # Check for strict mode from environment or config
        import os
        strict_mode = os.getenv('PRAISONAI_VALIDATE_STRICT', 'false').lower() == 'true'
        
        # Validate configuration
        result = validator.validate_config(config, strict=strict_mode)
        
        # Log warnings
        for warning in result.warnings:
            self.logger.warning(warning)
        
        # If there are errors, fail fast with aggregated error message
        if not result.valid:
            error_msg = f"Configuration validation failed with {len(result.errors)} error(s):\n"
            for i, error in enumerate(result.errors, 1):
                error_msg += f"  {i}. {error}\n"
            
            # Include warnings if any
            if result.warnings:
                error_msg += f"\nAdditionally, there are {len(result.warnings)} warning(s):\n"
                for i, warning in enumerate(result.warnings, 1):
                    error_msg += f"  {i}. {warning}\n"
            
            self.logger.error(error_msg)
            raise ValueError(error_msg)



    def _load_config(self):
        """Load configuration from agent file or agent_yaml."""
        if self.agent_yaml:
            config = _yaml_safe_load(self.agent_yaml)
        else:
            if self.agent_file in ('/app/api:app', 'api:app'):
                self.agent_file = 'agents.yaml'
            try:
                with open(self.agent_file, 'r') as f:
                    config = _yaml_safe_load(f)
            except FileNotFoundError:
                _rich_print(f"File not found: {self.agent_file}")
                return None
        
        # Apply CLI config overrides to both paths (agent_yaml and agent_file)
        if self.cli_config:
            self._merge_cli_config(config, self.cli_config)
        return config

    def _is_workflow_yaml(self, config):
        """Check if configuration is workflow mode YAML."""
        process_type = config.get('process', 'sequential')
        has_steps = 'steps' in config
        has_workflow_config = 'workflow' in config
        workflow_type = config.get('type')
        return (
            process_type == 'workflow'
            or (has_steps and has_workflow_config)
            or workflow_type in {'job', 'hybrid'}
        )

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
        config = self._load_config()
        if config is None:
            return
        if self._is_workflow_yaml(config):
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
        config = self._load_config()
        if config is None:
            return
        if self._is_workflow_yaml(config):
            return await self._arun_yaml_workflow(config)

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

        from .framework_adapters.workflow_framework import (
            framework_from_config,
            validate_workflow_framework,
        )
        effective_framework = (self.framework or framework_from_config(config))
        validate_workflow_framework(
            effective_framework,
            source="agents.yaml workflow section",
        )
        
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

        from .framework_adapters.workflow_framework import (
            framework_from_config,
            validate_workflow_framework,
        )
        effective_framework = (self.framework or framework_from_config(config))
        validate_workflow_framework(
            effective_framework,
            source="agents.yaml workflow section",
        )
        
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
