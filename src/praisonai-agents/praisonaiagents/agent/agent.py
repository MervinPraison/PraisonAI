import os
import time
import json
import logging
from praisonaiagents._logging import get_logger
import asyncio
import contextlib
import threading
import concurrent.futures
from typing import List, Optional, Any, Dict, Union, Literal, TYPE_CHECKING, Callable, Generator
from collections import OrderedDict
import inspect

# Decomposed agent functionality - real implementations in mixin files
from .chat_mixin import ChatMixin
from .execution_mixin import ExecutionMixin
from .memory_mixin import MemoryMixin
from .async_memory_mixin import AsyncMemoryMixin
from .tool_execution import ToolExecutionMixin
from .chat_handler import ChatHandlerMixin
from .session_manager import SessionManagerMixin
from .async_safety import AsyncSafeState

# Module-level logger for thread safety errors and debugging
logger = get_logger(__name__)

# ============================================================================
# Performance: Lazy imports for heavy dependencies
# Rich, LLM, and display utilities are only imported when needed (output=verbose)
# This reduces import time from ~420ms to ~20ms for silent mode
# ============================================================================

# Lazy-loaded modules (populated on first use, protected by _lazy_import_lock)
_lazy_import_lock = threading.Lock()
_rich_console = None
_rich_live = None
_llm_module = None
_main_module = None
_hooks_module = None
_stream_emitter_class = None

def _get_console():
    """Lazy load rich.console.Console (thread-safe)."""
    global _rich_console
    if _rich_console is None:
        with _lazy_import_lock:
            if _rich_console is None:
                from rich.console import Console
                _rich_console = Console
    return _rich_console

def _get_live():
    """Lazy load rich.live.Live (thread-safe)."""
    global _rich_live
    if _rich_live is None:
        with _lazy_import_lock:
            if _rich_live is None:
                from rich.live import Live
                _rich_live = Live
    return _rich_live

def _get_llm_functions():
    """Lazy load LLM functions (thread-safe)."""
    global _llm_module
    if _llm_module is None:
        with _lazy_import_lock:
            if _llm_module is None:
                from ..llm import get_openai_client, process_stream_chunks
                _llm_module = {
                    'get_openai_client': get_openai_client,
                    'process_stream_chunks': process_stream_chunks,
                }
    return _llm_module

def _get_display_functions():
    """Lazy load display functions from main module (thread-safe)."""
    global _main_module
    if _main_module is None:
        with _lazy_import_lock:
            if _main_module is None:
                from ..main import (
                    display_error,
                    display_instruction,
                    display_interaction,
                    display_generating,
                    display_self_reflection,
                    ReflectionOutput,
                    adisplay_instruction,
                    execute_sync_callback
                )
                _main_module = {
                    'display_error': display_error,
                    'display_instruction': display_instruction,
                    'display_interaction': display_interaction,
                    'display_generating': display_generating,
                    'display_self_reflection': display_self_reflection,
                    'ReflectionOutput': ReflectionOutput,
                    'adisplay_instruction': adisplay_instruction,
                    'execute_sync_callback': execute_sync_callback,
                }
    return _main_module

def _get_hooks_module():
    """Lazy load hooks module for HookRunner and HookRegistry (thread-safe)."""
    global _hooks_module
    if _hooks_module is None:
        with _lazy_import_lock:
            if _hooks_module is None:
                from ..hooks import HookRunner, HookRegistry
                _hooks_module = {
                    'HookRunner': HookRunner,
                    'HookRegistry': HookRegistry,
                }
    return _hooks_module

def _get_stream_emitter():
    """Lazy load StreamEventEmitter class (thread-safe)."""
    global _stream_emitter_class
    if _stream_emitter_class is None:
        with _lazy_import_lock:
            if _stream_emitter_class is None:
                from ..streaming.events import StreamEventEmitter
                _stream_emitter_class = StreamEventEmitter
    return _stream_emitter_class

# File extensions that indicate a file path (for output parameter detection)
_FILE_EXTENSIONS = frozenset({'.txt', '.md', '.json', '.yaml', '.yml', '.html', '.csv', '.log', '.xml', '.rst'})

def _is_file_path(value: str) -> bool:
    """Check if a string looks like a file path (not a preset name).
    
    Used to detect when output="path/to/file.txt" should be treated as
    output_file instead of a preset name.
    
    Args:
        value: String to check
        
    Returns:
        True if the string looks like a file path
    """
    # Contains path separator
    if '/' in value or '\\' in value:
        return True
    # Ends with common file extension
    lower = value.lower()
    for ext in _FILE_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False

# ============================================================================
# Performance: Module-level imports for param resolution (moved from __init__)
# These imports are lightweight and avoid per-Agent import overhead
# ============================================================================
from ..config.param_resolver import resolve, ArrayMode
from ..config.presets import (
    OUTPUT_PRESETS, EXECUTION_PRESETS, MEMORY_PRESETS, MEMORY_URL_SCHEMES,
    WEB_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS, CACHING_PRESETS,
    DEFAULT_OUTPUT_MODE,
)
from ..config.feature_configs import (
    OutputConfig, ExecutionConfig, MemoryConfig, KnowledgeConfig,
    PlanningConfig, ReflectionConfig, GuardrailConfig, WebConfig,
    TemplateConfig, CachingConfig, HooksConfig, SkillsConfig,
)

# Default tool output limit (16000 chars ≈ 4000 tokens)
# Increased to allow full page content from search tools while still preventing overflow
# Applied even when context management is disabled to prevent runaway tool outputs
DEFAULT_TOOL_OUTPUT_LIMIT = 16000

class ServerRegistry:
    """Registry for API server state per-port."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._server_started = {}  # Dict of port -> started boolean
        self._registered_agents = {}  # Dict of port -> Dict of path -> agent_id  
        self._shared_apps = {}  # Dict of port -> FastAPI app
    
    @staticmethod
    def get_default_instance():
        """Get default global registry for backward compatibility."""
        if not hasattr(ServerRegistry, '_default_instance'):
            ServerRegistry._default_instance = ServerRegistry()
        return ServerRegistry._default_instance
    
    def is_server_started(self, port: int) -> bool:
        with self._lock:
            return self._server_started.get(port, False)
    
    def set_server_started(self, port: int, started: bool) -> None:
        with self._lock:
            self._server_started[port] = started
    
    def get_shared_app(self, port: int):
        with self._lock:
            return self._shared_apps.get(port)
    
    def set_shared_app(self, port: int, app) -> None:
        with self._lock:
            self._shared_apps[port] = app
    
    def register_agent(self, port: int, path: str, agent_id: str) -> None:
        with self._lock:
            if port not in self._registered_agents:
                self._registered_agents[port] = {}
            self._registered_agents[port][path] = agent_id
    
    def get_registered_agents(self, port: int) -> dict:
        with self._lock:
            return self._registered_agents.get(port, {}).copy()

# Backward compatibility - use default instance
def _get_default_server_registry() -> ServerRegistry:
    return ServerRegistry.get_default_instance()

# Don't import FastAPI dependencies here - use lazy loading instead

if TYPE_CHECKING:
    from ..approval.protocols import ApprovalConfig, ApprovalProtocol
    from ..config.feature_configs import LearnConfig, MemoryConfig
    from ..context.models import ContextConfig
    from ..context.manager import ContextManager
    from ..knowledge.knowledge import Knowledge
    from ..agent.autonomy import AutonomyConfig
    from ..task.task import Task
    from .handoff import Handoff, HandoffConfig, HandoffResult
    from ..rag.models import RAGResult, ContextPack
    from ..eval.results import EvaluationLoopResult

# Import structured error from central errors module
from ..errors import BudgetExceededError

class Agent(ToolExecutionMixin, ChatHandlerMixin, SessionManagerMixin, ChatMixin, ExecutionMixin, MemoryMixin, AsyncMemoryMixin):
    # Class-level counter for generating unique display names for nameless agents
    _agent_counter = 0
    _agent_counter_lock = threading.Lock()
    # Class-level cache for environment variables (avoid repeated os.environ.get)
    # Protected by _env_cache_lock for thread safety
    _env_cache_lock = threading.Lock()
    _env_output_mode = None
    _env_output_checked = False
    _default_model = None
    _default_model_checked = False
    
    @property
    def _hook_runner(self):
        """Lazy-loaded HookRunner for event-based hooks (zero overhead when not used)."""
        if self.__hook_runner is None:
            hooks_mod = _get_hooks_module()
            self.__hook_runner = hooks_mod['HookRunner'](
                registry=self._hooks_registry_param if isinstance(self._hooks_registry_param, hooks_mod['HookRegistry']) else None,
                cwd=os.getcwd()
            )
        return self.__hook_runner
    
    @property
    def stream_emitter(self) -> Optional[Any]:
        """Lazy-loaded StreamEventEmitter for real-time events (zero overhead when not used)."""
        if self.__stream_emitter is None:
            self.__stream_emitter = _get_stream_emitter()()
        return self.__stream_emitter
    
    @stream_emitter.setter
    def stream_emitter(self, value: Optional[Any]) -> None:
        """Allow setting stream_emitter directly."""
        self.__stream_emitter = value
    
    @classmethod
    def _get_env_output_mode(cls):
        """Get cached PRAISONAI_OUTPUT env var value (thread-safe)."""
        if not cls._env_output_checked:
            with cls._env_cache_lock:
                if not cls._env_output_checked:
                    cls._env_output_mode = os.environ.get('PRAISONAI_OUTPUT', '').lower()
                    cls._env_output_checked = True
        return cls._env_output_mode
    
    @classmethod
    def _get_default_model(cls):
        """Get cached default model name from OPENAI_MODEL_NAME env var (thread-safe)."""
        if not cls._default_model_checked:
            with cls._env_cache_lock:
                if not cls._default_model_checked:
                    cls._default_model = os.getenv('OPENAI_MODEL_NAME', 'gpt-4o-mini')
                    cls._default_model_checked = True
        return cls._default_model
    
    @classmethod
    def _configure_logging(cls):
        """Configure logging settings once for all agent instances."""
        # Configure logging to suppress unwanted outputs
        get_logger("litellm").setLevel(logging.WARNING)
        
        # Allow httpx logging when LOGLEVEL=debug, otherwise suppress it
        loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
        if loglevel == 'DEBUG':
            get_logger("httpx").setLevel(logging.INFO)
            get_logger("httpcore").setLevel(logging.INFO)
        else:
            get_logger("httpx").setLevel(logging.WARNING)
            get_logger("httpcore").setLevel(logging.WARNING)
    
    @classmethod
    def from_template(
        cls,
        uri: str,
        config: Optional[Dict[str, Any]] = None,
        offline: bool = False,
        **kwargs
    ) -> 'Agent':
        """
        Create an Agent from a template.
        
        Args:
            uri: Template URI (local path, package ref, or github ref)
                Examples:
                - "./my-template" (local path)
                - "transcript-generator" (default recipes repo)
                - "github:owner/repo/template@v1.0.0" (GitHub with version)
                - "package:agent_recipes/transcript-generator" (installed package)
            config: Optional configuration overrides
            offline: If True, only use cached templates (no network)
            **kwargs: Additional Agent constructor arguments
            
        Returns:
            Configured Agent instance
            
        Example:
            ```python
            from praisonaiagents import Agent
            
            # From default recipes repo
            agent = Agent.from_template("transcript-generator")
            result = agent.chat("Transcribe ./audio.mp3")
            
            # With config overrides
            agent = Agent.from_template(
                "data-transformer",
                config={"output_format": "json"},
                verbose=True
            )
            ```
        """
        try:
            # Lazy import to avoid circular dependencies and keep core SDK lean
            from praisonai.templates.loader import create_agent_from_template
            return create_agent_from_template(uri, config=config, offline=offline, **kwargs)
        except ImportError:
            raise ImportError(
                "Template support requires the 'praisonai' package. "
                "Install with: pip install praisonai"
            )
    
    def _generate_tool_definition(self, function_name):
        """
        Generate a tool definition from a function name by inspecting the function.
        """
        logging.debug(f"Attempting to generate tool definition for: {function_name}")
        
        # First try to get the tool definition if it exists
        tool_def_name = f"{function_name}_definition"
        tool_def = globals().get(tool_def_name)
        logging.debug(f"Looking for {tool_def_name} in globals: {tool_def is not None}")
        
        if not tool_def:
            import __main__
            tool_def = getattr(__main__, tool_def_name, None)
            logging.debug(f"Looking for {tool_def_name} in __main__: {tool_def is not None}")
        
        if tool_def:
            logging.debug(f"Found tool definition: {tool_def}")
            return tool_def

        # Try to find the function in the agent's tools list first
        func = None
        for tool in self.tools:
            if callable(tool) and getattr(tool, '__name__', '') == function_name:
                func = tool
                break
        
        logging.debug(f"Looking for {function_name} in agent tools: {func is not None}")
        
        # If not found in tools, try globals and main
        if not func:
            func = globals().get(function_name)
            logging.debug(f"Looking for {function_name} in globals: {func is not None}")
            
            if not func:
                import __main__
                func = getattr(__main__, function_name, None)
                logging.debug(f"Looking for {function_name} in __main__: {func is not None}")

        if not func or not callable(func):
            logging.debug(f"Function {function_name} not found or not callable")
            return None

        import inspect
        # Langchain tools
        if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
            original_func = func
            func = func.run
            function_name = original_func.__name__
        # CrewAI tools
        elif inspect.isclass(func) and hasattr(func, '_run'):
            original_func = func
            func = func._run
            function_name = original_func.__name__

        sig = inspect.signature(func)
        logging.debug(f"Function signature: {sig}")
        
        # Skip self, *args, **kwargs, so they don't get passed in arguments
        parameters_list = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            parameters_list.append((name, param))

        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Parse docstring for parameter descriptions
        docstring = inspect.getdoc(func)
        logging.debug(f"Function docstring: {docstring}")
        
        param_descriptions = {}
        if docstring:
            import re
            param_section = re.split(r'\s*Args:\s*', docstring)
            logging.debug(f"Param section split: {param_section}")
            if len(param_section) > 1:
                param_lines = param_section[1].split('\n')
                for line in param_lines:
                    line = line.strip()
                    if line and ':' in line:
                        param_name, param_desc = line.split(':', 1)
                        param_descriptions[param_name.strip()] = param_desc.strip()
        
        logging.debug(f"Parameter descriptions: {param_descriptions}")

        for name, param in parameters_list:
            param_type = "string"  # Default type
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == list:
                    param_type = "array"
                elif param.annotation == dict:
                    param_type = "object"
            
            param_info = {"type": param_type}
            if name in param_descriptions:
                param_info["description"] = param_descriptions[name]
            
            parameters["properties"][name] = param_info
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(name)
        
        logging.debug(f"Generated parameters: {parameters}")

        # Extract description from docstring
        description = docstring.split('\n')[0] if docstring else f"Function {function_name}"
        
        tool_def = {
            "type": "function",
            "function": {
                "name": function_name,
                "description": description,
                "parameters": parameters
            }
        }
        logging.debug(f"Generated tool definition: {tool_def}")
        return tool_def

    def __init__(
        self,
        # Core identity
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        # LLM configuration
        llm: Optional[Union[str, Any]] = None,
        model: Optional[Union[str, Any]] = None,  # Alias for llm=
        base_url: Optional[str] = None,  # Kept separate (connection/auth)
        api_key: Optional[str] = None,  # Kept separate (connection/auth)
        # Tools
        tools: Optional[List[Any]] = None,
        allow_delegation: bool = False,  # Deprecated: use handoffs= instead
        allow_code_execution: Optional[bool] = False,  # Deprecated: use execution=ExecutionConfig(code_execution=True)
        code_execution_mode: Literal["safe", "unsafe"] = "safe",  # Deprecated: use execution=ExecutionConfig(code_mode="safe")
        handoffs: Optional[List[Union['Agent', 'Handoff']]] = None,
        # Session management (deprecated standalone params - use config objects)
        auto_save: Optional[str] = None,  # Deprecated: use memory=MemoryConfig(auto_save="name")
        rate_limiter: Optional[Any] = None,  # Deprecated: use execution=ExecutionConfig(rate_limiter=obj)
        # ============================================================
        # CONSOLIDATED FEATURE PARAMS (agent-centric API)
        # Each follows: False=disabled, True=defaults, Config=custom
        # ============================================================
        memory: Optional[Union[bool, str, 'MemoryConfig', 'MemoryManager']] = None,
        knowledge: Optional[Union[bool, str, List[str], 'KnowledgeConfig', 'Knowledge']] = None,
        planning: Optional[Union[bool, str, 'PlanningConfig']] = False,
        reflection: Optional[Union[bool, str, 'ReflectionConfig']] = None,
        guardrails: Optional[Union[bool, str, Callable, 'GuardrailConfig']] = None,
        web: Optional[Union[bool, str, 'WebConfig']] = None,
        context: Optional[Union[bool, str, Dict[str, Any], 'ContextConfig', 'ContextManager']] = None,
        autonomy: Optional[Union[bool, str, Dict[str, Any], 'AutonomyConfig']] = None,
        verification_hooks: Optional[List[Any]] = None,  # Deprecated: use autonomy=AutonomyConfig(verification_hooks=[...])
        output: Optional[Union[bool, str, Dict[str, Any], 'OutputConfig']] = None,
        execution: Optional[Union[bool, str, Dict[str, Any], 'ExecutionConfig']] = None,
        templates: Optional[Union[Dict[str, Any], 'TemplateConfig']] = None,
        caching: Optional[Union[bool, str, Dict[str, Any], 'CachingConfig']] = None,
        hooks: Optional[Union[List[Any], Dict[str, Any], 'HooksConfig']] = None,
        skills: Optional[Union[List[str], str, Dict[str, Any], 'SkillsConfig']] = None,
        approval: Optional[Union[bool, str, Dict[str, Any], 'ApprovalConfig', 'ApprovalProtocol']] = None,
        tool_timeout: Optional[int] = None,  # P8/G11: Timeout in seconds for each tool call
        learn: Optional[Union[bool, str, Dict[str, Any], 'LearnConfig']] = None,  # Continuous learning (peer to memory)
        backend: Optional[Any] = None,  # External managed agent backend (e.g., ManagedAgentIntegration)
    ):
        """Initialize an Agent instance.

        Args:
            name: Agent name for identification and logging. Defaults to "Agent".
            role: Role/job title defining expertise (e.g., "Data Analyst").
            goal: Primary objective the agent aims to achieve.
            backstory: Background context shaping personality and decisions.
            instructions: Direct instructions (overrides role/goal/backstory). Recommended for simple agents.
            llm: Model name string ("gpt-4o", "anthropic/claude-3-sonnet") or LLM object.
                Defaults to OPENAI_MODEL_NAME env var or "gpt-4o-mini".
            model: Alias for llm parameter.
            base_url: Custom LLM endpoint URL (e.g., for Ollama). Kept separate for auth.
            api_key: API key for LLM provider. Kept separate for auth.
            tools: List of tools, functions, callables, or MCP instances.
            allow_delegation: **Deprecated** — use ``handoffs=`` instead.
            allow_code_execution: **Deprecated** — use ``execution=ExecutionConfig(code_execution=True)``.
            code_execution_mode: **Deprecated** — use ``execution=ExecutionConfig(code_mode="safe")``.
            handoffs: List of Agent or Handoff objects for agent-to-agent collaboration.
            auto_save: **Deprecated** — use ``memory=MemoryConfig(auto_save="name")``.
            rate_limiter: **Deprecated** — use ``execution=ExecutionConfig(rate_limiter=obj)``.
            memory: Memory system configuration. Accepts:
                - bool: True enables defaults, False disables
                - MemoryConfig: Custom configuration
                - MemoryManager: Pre-configured instance
            knowledge: Knowledge sources. Accepts:
                - bool: True enables defaults
                - List[str]: File paths, URLs, or text content
                - KnowledgeConfig: Custom configuration
            planning: Planning mode. Accepts:
                - bool: True enables with defaults
                - PlanningConfig: Custom configuration
            reflection: Self-reflection. Accepts:
                - bool: True enables with defaults
                - ReflectionConfig: Custom configuration
            guardrails: Output validation. Accepts:
                - bool: True enables with defaults
                - Callable: Validation function
                - GuardrailConfig: Custom configuration
            web: Web search/fetch. Accepts:
                - bool: True enables with defaults
                - WebConfig: Custom configuration
            context: Context management. Accepts:
                - bool: True enables with defaults
                - str: Preset name ("sliding_window", "summarize", "truncate")
                - Dict[str, Any]: ContextConfig fields
                - ContextConfig: Custom configuration
                - ContextManager: Pre-configured instance
            autonomy: Autonomy settings. Accepts:
                - bool: True enables with defaults
                - str: Level preset ("suggest", "auto_edit", "full_auto")
                - Dict[str, Any]: Configuration dict
                - AutonomyConfig: Custom configuration
            verification_hooks: **Deprecated** — use ``autonomy=AutonomyConfig(verification_hooks=[...])``.
                Still works for backward compatibility.
            output: Output configuration. Accepts:
                - bool: True=default OutputConfig, False=disabled
                - str: Preset name ("silent", "actions", "verbose", "json", "stream")
                - Dict[str, Any]: Config overrides (e.g. {"verbose": 2, "stream": True})
                - OutputConfig: Custom configuration
                Controls: verbose, markdown, stream, metrics, reasoning_steps
            execution: Execution configuration. Accepts:
                - bool: True=default ExecutionConfig, False=disabled
                - str: Preset name ("fast", "balanced", "thorough")
                - Dict[str, Any]: Config overrides (e.g. {"max_iter": 10, "max_rpm": 60})
                - ExecutionConfig: Custom configuration
                Controls: max_iter, max_rpm, max_execution_time, max_retry_limit
            templates: Template configuration. Accepts:
                - Dict[str, Any]: Template fields (e.g. {"system": "...", "prompt": "..."})
                - TemplateConfig: Custom configuration
                Controls: system_template, prompt_template, response_template
            caching: Caching configuration. Accepts:
                - bool: True enables with defaults
                - CachingConfig: Custom configuration
            hooks: Event hooks. Accepts:
                - List: List of hook callables
                - HooksConfig: Custom configuration
            skills: Agent skills. Accepts:
                - List[str]: Skill directory paths
                - SkillsConfig: Custom configuration
            learn: Continuous learning configuration. Accepts:
                - bool: True enables with defaults (AGENTIC mode), False disables
                - str: Mode string ("disabled", "agentic", "propose")
                - Dict[str, Any]: Config fields (e.g. {"mode": "agentic", "backend": "sqlite"})
                - LearnConfig: Custom configuration
                Learning is a first-class citizen, peer to memory. It captures patterns,
                preferences, and insights from interactions to improve future responses.
            backend: External managed agent backend for hybrid execution. Accepts:
                - ManagedAgentIntegration: External managed agent service
                - None: Use local execution (default)
                When provided, agent can delegate execution to managed infrastructure
                for long-running tasks or when local resources are constrained.

        Raises:
            ValueError: If all of name, role, goal, backstory, and instructions are None.
            ImportError: If memory or LLM features are requested but dependencies are not installed.

        Note:
            Many legacy parameters have been consolidated into config objects:
            - verbose, markdown, stream, metrics, reasoning_steps → output=
            - max_iter, max_rpm, max_execution_time, max_retry_limit → execution=
            - self_reflect, max_reflect, min_reflect, reflect_llm → reflection=
            - guardrail, max_guardrail_retries → guardrails=
            - system_template, prompt_template, response_template → templates=
            - cache, prompt_caching → caching=
            - web_search, web_fetch → web=
            - allow_delegation → handoffs=
            - allow_code_execution, code_execution_mode → execution=
            - auto_save → memory=MemoryConfig(auto_save=)
            - rate_limiter → execution=ExecutionConfig(rate_limiter=)
            - verification_hooks → autonomy=AutonomyConfig(verification_hooks=)
        """
        # Add check at start if memory is requested
        if memory is not None:
            try:
                from ..memory.memory import Memory  # noqa: F401
                _ = Memory  # Silence unused import warning - we just check availability
            except ImportError:
                raise ImportError(
                    "Memory features requested in Agent but memory dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[memory]\""
                )

        # Handle backward compatibility for required fields
        if all(x is None for x in [name, role, goal, backstory, instructions]):
            raise ValueError("At least one of name, role, goal, backstory, or instructions must be provided")

        # Configure logging only once at the class level
        if not hasattr(Agent, '_logging_configured'):
            Agent._configure_logging()
            Agent._logging_configured = True

        # ============================================================
        # CONFIG-DRIVEN DEFAULTS (apply before parameter resolution)
        # Precedence: Explicit params > Config file > Built-in defaults
        # Only applies when param is None (not explicitly set)
        # ============================================================
        from ..config.loader import apply_config_defaults, get_default
        
        # Apply config defaults for LLM if not explicitly set
        if llm is None and model is None:
            config_model = get_default("model")
            if config_model:
                llm = config_model
        
        # Apply config defaults for base_url if not explicitly set
        if base_url is None:
            config_base_url = get_default("base_url")
            if config_base_url:
                base_url = config_base_url
        
        # Apply config defaults for feature params (memory, knowledge, etc.)
        # These use apply_config_defaults which handles enabled=True/False logic
        if memory is None:
            memory = apply_config_defaults("memory", memory, MemoryConfig)
        if knowledge is None:
            knowledge = apply_config_defaults("knowledge", knowledge, KnowledgeConfig)
        if planning is False:  # Only override if explicitly False (default)
            config_planning = apply_config_defaults("planning", None, PlanningConfig)
            if config_planning:
                planning = config_planning
        if reflection is None:
            reflection = apply_config_defaults("reflection", reflection, ReflectionConfig)
        if web is None:
            web = apply_config_defaults("web", web, WebConfig)
        if output is None:
            output = apply_config_defaults("output", output, OutputConfig)
        if execution is None:
            execution = apply_config_defaults("execution", execution, ExecutionConfig)
        if caching is None:
            caching = apply_config_defaults("caching", caching, CachingConfig)
        if autonomy is None:
            # AutonomyConfig is in agent/autonomy.py - use dict for config defaults
            autonomy = apply_config_defaults("autonomy", autonomy, None)

        # ============================================================
        # DEPRECATION WARNINGS for params consolidated into configs
        # Old params still work but emit warnings pointing to new API
        # ============================================================
        from ..utils.deprecation import warn_deprecated_param
        
        if allow_delegation:
            warn_deprecated_param(
                "allow_delegation",
                since="1.0.0",
                removal="2.0.0",
                alternative="use 'handoffs=[other_agent]' instead",
                stacklevel=3
            )
        if allow_code_execution:
            warn_deprecated_param(
                "allow_code_execution", 
                since="1.0.0",
                removal="2.0.0",
                alternative="use 'execution=ExecutionConfig(code_execution=True)' instead",
                stacklevel=3
            )
        if code_execution_mode != "safe":
            warn_deprecated_param(
                "code_execution_mode",
                since="1.0.0", 
                removal="2.0.0",
                alternative='use \'execution=ExecutionConfig(code_mode="unsafe")\' instead',
                stacklevel=3
            )
        if auto_save is not None:
            warn_deprecated_param(
                "auto_save",
                since="1.0.0",
                removal="2.0.0", 
                alternative='use \'memory=MemoryConfig(auto_save="name")\' instead',
                stacklevel=3
            )
        if rate_limiter is not None:
            warn_deprecated_param(
                "rate_limiter",
                since="1.0.0",
                removal="2.0.0",
                alternative="use 'execution=ExecutionConfig(rate_limiter=obj)' instead",
                stacklevel=3
            )
        if verification_hooks is not None:
            warn_deprecated_param(
                "verification_hooks",
                since="1.0.0", 
                removal="2.0.0",
                alternative="use 'autonomy=AutonomyConfig(verification_hooks=[...])' instead",
                stacklevel=3
            )

        # ============================================================
        # CONSOLIDATED PARAMS EXTRACTION (agent-centric API)
        # Uses unified resolver: Instance > Config > Array > String > Bool > Default
        # Note: Imports moved to module level for performance
        # ============================================================
        
        # Initialize extracted values with defaults
        user_id = None
        session_id = None
        db = None
        auto_memory = None
        claude_memory = None
        self_reflect = False
        max_reflect = 3
        min_reflect = 1
        reflect_llm = None
        reflect_prompt = None
        guardrail = None
        max_guardrail_retries = 3
        web_search = None
        web_fetch = None
        plan_mode = False
        planning_tools = None
        planning_reasoning = False
        policy = None
        background = None
        checkpoints = None
        output_style = None
        thinking_budget = None
        skills_dirs = None
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve OUTPUT param - FAST PATH for common cases
        # DEFAULT: "silent" mode (zero overhead, fastest performance)
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None -> silent defaults (use cached env var)
        if output is None:
            env_output = Agent._get_env_output_mode()
            if env_output and env_output in OUTPUT_PRESETS:
                output = env_output
            else:
                output = DEFAULT_OUTPUT_MODE
            _has_explicit_output = False
        else:
            _has_explicit_output = True
        
        # Fast path: string preset lookup (most common case)
        if isinstance(output, str):
            output_lower = output.lower()
            preset_value = OUTPUT_PRESETS.get(output_lower)
            if preset_value is not None:
                _output_config = OutputConfig(**preset_value) if isinstance(preset_value, dict) else preset_value
            elif _is_file_path(output):
                # String looks like a file path - use as output_file
                _output_config = OutputConfig(output_file=output)
            else:
                _output_config = OutputConfig()  # Default silent
        elif isinstance(output, OutputConfig):
            _output_config = output
        else:
            # Complex case: use full resolver
            _output_config = resolve(
                value=output,
                param_name="output",
                config_class=OutputConfig,
                presets=OUTPUT_PRESETS,
                array_mode=ArrayMode.PRESET_OVERRIDE,
                default=OutputConfig(),
            )
        if _output_config:
            verbose = _output_config.verbose
            markdown = _output_config.markdown
            stream = _output_config.stream
            metrics = _output_config.metrics
            reasoning_steps = _output_config.reasoning_steps
            output_style = getattr(_output_config, 'style', None)
            actions_trace = getattr(_output_config, 'actions_trace', False)  # Default False (silent)
            json_output = getattr(_output_config, 'json_output', False)
            status_trace = getattr(_output_config, 'status_trace', False)  # New: clean inline status
            simple_output = getattr(_output_config, 'simple_output', False)  # status preset: no timestamps
            editor_output = getattr(_output_config, 'editor_output', False)  # Editor: Step N display
            output_file = getattr(_output_config, 'output_file', None)  # Auto-save to file
            output_template = getattr(_output_config, 'template', None)  # Response template
            tool_output_limit = getattr(_output_config, 'tool_output_limit', DEFAULT_TOOL_OUTPUT_LIMIT)
        else:
            # Fallback defaults match silent mode (zero overhead)
            verbose, markdown, stream, metrics, reasoning_steps = False, False, False, False, False
            actions_trace = False  # No callbacks by default
            json_output = False
            status_trace = False
            simple_output = False
            editor_output = False
            tool_output_limit = DEFAULT_TOOL_OUTPUT_LIMIT
        
        # Enable editor output mode if configured (beginner-friendly, takes priority)
        # Shows: Step 1: 📄 Creating file: path → ✓ Done
        if editor_output:
            try:
                from ..output.editor import enable_editor_output, is_editor_output_enabled
                if not is_editor_output_enabled():
                    enable_editor_output(use_color=True)
            except ImportError:
                pass  # Editor module not available
        # Enable trace output mode if configured
        # This provides timestamped inline status with duration
        elif status_trace:
            try:
                from ..output.trace import enable_trace_output, is_trace_output_enabled
                if not is_trace_output_enabled():
                    enable_trace_output(use_color=True, show_timestamps=True)
            except ImportError:
                pass  # Trace module not available
        # Enable status output mode if configured (simple progress, no timestamps)
        # This registers callbacks to capture tool calls and final output
        elif actions_trace:
            try:
                from ..output.status import enable_status_output, is_status_output_enabled
                if not is_status_output_enabled():
                    output_format = "jsonl" if json_output else "text"
                    # simple_output=True means status preset (no timestamps)
                    # metrics=True means debug preset (show token/cost info)
                    enable_status_output(
                        redact=True,
                        use_color=True,
                        format=output_format,
                        show_timestamps=not simple_output,
                        show_metrics=metrics
                    )
            except ImportError:
                pass  # Status module not available
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve EXECUTION param - FAST PATH for common cases
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None -> default config (skip resolve() call)
        if execution is None:
            _exec_config = ExecutionConfig()
        elif isinstance(execution, ExecutionConfig):
            _exec_config = execution
        elif isinstance(execution, str):
            preset_value = EXECUTION_PRESETS.get(execution.lower())
            if preset_value is not None:
                _exec_config = ExecutionConfig(**preset_value) if isinstance(preset_value, dict) else preset_value
            else:
                _exec_config = ExecutionConfig()
        else:
            _exec_config = resolve(
                value=execution,
                param_name="execution",
                config_class=ExecutionConfig,
                presets=EXECUTION_PRESETS,
                array_mode=ArrayMode.PRESET_OVERRIDE,
                default=ExecutionConfig(),
            )
        if _exec_config:
            max_iter = _exec_config.max_iter
            max_rpm = _exec_config.max_rpm
            max_execution_time = _exec_config.max_execution_time
            max_retry_limit = _exec_config.max_retry_limit
            # Extract consolidated fields (config takes precedence over deprecated standalone params)
            if _exec_config.rate_limiter is not None:
                rate_limiter = _exec_config.rate_limiter
            if _exec_config.code_execution:
                allow_code_execution = True
            if _exec_config.code_mode != "safe":
                code_execution_mode = _exec_config.code_mode
            # Budget guard extraction
            _max_budget = getattr(_exec_config, 'max_budget', None)
            _on_budget_exceeded = getattr(_exec_config, 'on_budget_exceeded', 'stop') or 'stop'
        else:
            max_iter, max_rpm, max_execution_time, max_retry_limit = 20, None, None, 2
            _max_budget = None
            _on_budget_exceeded = 'stop'
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve TEMPLATES param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None -> no templates (skip resolve() call)
        if templates is None:
            _template_config = None
        elif isinstance(templates, TemplateConfig):
            _template_config = templates
        elif isinstance(templates, dict):
            _template_config = TemplateConfig(**templates)
        else:
            _template_config = resolve(
                value=templates,
                param_name="templates",
                config_class=TemplateConfig,
                default=None,
            )
        if _template_config:
            system_template = _template_config.system
            prompt_template = _template_config.prompt
            response_template = _template_config.response
            use_system_prompt = _template_config.use_system_prompt
        else:
            system_template, prompt_template, response_template, use_system_prompt = None, None, None, True
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve CACHING param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None -> default caching, False -> disabled
        if caching is None:
            _caching_config = CachingConfig()
        elif caching is False:
            _caching_config = None
        elif caching is True:
            _caching_config = CachingConfig()
        elif isinstance(caching, CachingConfig):
            _caching_config = caching
        else:
            _caching_config = resolve(
                value=caching,
                param_name="caching",
                config_class=CachingConfig,
                presets=CACHING_PRESETS,
                default=CachingConfig(),
            )
        if _caching_config:
            cache = _caching_config.enabled
            prompt_caching = _caching_config.prompt_caching
        elif caching is False:
            cache, prompt_caching = False, None
        else:
            cache, prompt_caching = True, None
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve HOOKS param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        _hooks_list = []
        step_callback = None
        # Fast path: None -> no hooks (skip resolve() call)
        if hooks is None:
            _hooks_config = None
        elif isinstance(hooks, list):
            _hooks_config = hooks  # Passthrough list directly
        elif isinstance(hooks, HooksConfig):
            _hooks_config = hooks
        else:
            _hooks_config = resolve(
                value=hooks,
                param_name="hooks",
                config_class=HooksConfig,
                array_mode=ArrayMode.PASSTHROUGH,
                default=None,
            )
        if _hooks_config is not None:
            if isinstance(_hooks_config, list):
                _hooks_list = _hooks_config
            elif isinstance(_hooks_config, HooksConfig):
                step_callback = _hooks_config.on_step
                _hooks_list = _hooks_config.middleware or []
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve SKILLS param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        _skills = None
        skills_dirs = None
        # Fast path: None -> no skills (skip resolve() call)
        if skills is None:
            _skills_config = None
        elif isinstance(skills, list):
            _skills_config = SkillsConfig(sources=skills)
        elif isinstance(skills, SkillsConfig):
            _skills_config = skills
        else:
            _skills_config = resolve(
                value=skills,
                param_name="skills",
                config_class=SkillsConfig,
                array_mode=ArrayMode.SOURCES,
                string_mode="path_as_source",
                default=None,
            )
        if _skills_config is not None:
            if isinstance(_skills_config, SkillsConfig):
                _skills = _skills_config.paths
                skills_dirs = _skills_config.dirs
            elif isinstance(_skills_config, list):
                _skills = _skills_config
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve MEMORY param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None/False -> no memory (skip resolve() call)
        if memory is None or memory is False:
            _memory_config = None
        elif memory is True:
            _memory_config = MemoryConfig()
        elif isinstance(memory, MemoryConfig):
            _memory_config = memory
        elif hasattr(memory, 'search') and hasattr(memory, 'add'):
            _memory_config = memory  # Memory instance passthrough
        elif hasattr(memory, 'database_url'):
            _memory_config = memory  # db() instance passthrough
        else:
            _memory_config = resolve(
                value=memory,
                param_name="memory",
                config_class=MemoryConfig,
                presets=MEMORY_PRESETS,
                url_schemes=MEMORY_URL_SCHEMES,
                instance_check=lambda v: (hasattr(v, 'search') and hasattr(v, 'add')) or hasattr(v, 'database_url'),
                array_mode=ArrayMode.SINGLE_OR_LIST,
                default=None,
            )
        
        # Extract values from resolved memory config
        if _memory_config is not None:
            if hasattr(_memory_config, 'database_url'):
                # It's a db() instance - pass through
                db = _memory_config
                memory = True
            elif isinstance(_memory_config, MemoryConfig):
                user_id = _memory_config.user_id
                session_id = _memory_config.session_id
                db = _memory_config.db
                auto_memory = _memory_config.auto_memory
                claude_memory = _memory_config.claude_memory
                # Extract auto_save from MemoryConfig (takes precedence over standalone param)
                if _memory_config.auto_save is not None:
                    auto_save = _memory_config.auto_save
                # Convert to internal format
                backend = _memory_config.backend
                if hasattr(backend, 'value'):
                    backend = backend.value
                # If learn is enabled, pass as dict to trigger full Memory class
                if _memory_config.learn:
                    memory = _memory_config.to_dict()
                elif backend == "file":
                    memory = True
                elif _memory_config.config:
                    memory = _memory_config.config
                else:
                    memory = backend
            elif hasattr(_memory_config, 'search') and hasattr(_memory_config, 'add'):
                # Memory instance - pass through
                pass
        elif memory is False:
            memory = None
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve LEARN param - FAST PATH (top-level, peer to memory)
        # learn= is a first-class citizen, independent of memory=
        # ─────────────────────────────────────────────────────────────────────
        from ..config.feature_configs import LearnConfig
        
        _learn_config = None
        
        # Top-level learn= takes precedence over memory.learn
        if learn is not None:
            # Explicit top-level learn= param
            if learn is False:
                _learn_config = None
            elif learn is True:
                # learn=True shorthand enables AGENTIC mode (auto-learning)
                from ..memory.learn.protocols import LearnMode
                _learn_config = LearnConfig(mode=LearnMode.AGENTIC)
            elif isinstance(learn, LearnConfig):
                _learn_config = learn
            elif isinstance(learn, dict):
                _learn_config = LearnConfig(**learn)
            elif isinstance(learn, str):
                # String mode: "disabled", "agentic", "propose"
                from ..memory.learn.protocols import LearnMode
                if learn == "disabled":
                    _learn_config = None
                elif learn == "agentic":
                    _learn_config = LearnConfig(mode=LearnMode.AGENTIC)
                elif learn == "propose":
                    _learn_config = LearnConfig(mode=LearnMode.PROPOSE)
                else:
                    # Unknown string mode, disable learning
                    _learn_config = None
            else:
                logging.warning(
                    "Unsupported learn= value %r; expected bool, dict, or LearnConfig. "
                    "Learning disabled.", learn
                )
                _learn_config = None
        elif _memory_config is not None and isinstance(_memory_config, MemoryConfig):
            # Fallback to memory.learn for backward compatibility
            if _memory_config.learn:
                if _memory_config.learn is True:
                    # learn=True shorthand enables AGENTIC mode
                    from ..memory.learn.protocols import LearnMode
                    _learn_config = LearnConfig(mode=LearnMode.AGENTIC)
                elif isinstance(_memory_config.learn, LearnConfig):
                    _learn_config = _memory_config.learn
                elif isinstance(_memory_config.learn, dict):
                    _learn_config = LearnConfig(**_memory_config.learn)
        
        # If learn is enabled but memory is not, we need to enable memory for learn to work
        if _learn_config is not None and memory is None:
            # Enable minimal memory for learn to work
            memory = {"learn": _learn_config.to_dict() if hasattr(_learn_config, 'to_dict') else _learn_config}
        elif _learn_config is not None and isinstance(memory, dict):
            # Merge learn config into memory dict
            memory["learn"] = _learn_config.to_dict() if hasattr(_learn_config, 'to_dict') else _learn_config
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve HISTORY from MemoryConfig - FAST PATH
        # History is enabled via memory="history" preset or MemoryConfig(history=True)
        # ─────────────────────────────────────────────────────────────────────
        _history_enabled = False
        _history_limit = 10
        _history_session_id = None
        
        # Check if memory config has history settings
        if _memory_config is not None and isinstance(_memory_config, MemoryConfig):
            if _memory_config.history:
                _history_enabled = True
                _history_limit = _memory_config.history_limit
                # Use explicit session_id from MemoryConfig if provided
                if _memory_config.session_id:
                    _history_session_id = _memory_config.session_id
        
        # Use auto_save session if no explicit session and history is enabled
        if _history_enabled and _history_session_id is None and auto_save:
            _history_session_id = auto_save
        
        # Auto-generate session_id when history=True but no session_id set
        # This ensures _init_session_store() can create the store
        if _history_enabled and session_id is None and _history_session_id is not None:
            session_id = _history_session_id
        elif _history_enabled and session_id is None and _history_session_id is None:
            import hashlib as _hl
            _agent_hash = _hl.sha256((name or "agent").encode()).hexdigest()[:8]
            # Backward compat: check if legacy md5-based session exists first
            _legacy_hash = _hl.md5((name or "agent").encode()).hexdigest()[:8]
            _legacy_id = f"history_{_legacy_hash}"
            _new_id = f"history_{_agent_hash}"
            # Prefer legacy if it exists on disk, else use new SHA-256 ID
            import os as _os
            _session_dir = _os.path.join(_os.path.expanduser("~"), ".praisonai", "sessions")
            if _os.path.exists(_os.path.join(_session_dir, f"{_legacy_id}.json")):
                session_id = _legacy_id  # preserve existing history
            else:
                session_id = _new_id
            _history_session_id = session_id
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve KNOWLEDGE param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        retrieval_config = None
        embedder_config = None
        
        # Fast path: None/False -> no knowledge (skip resolve() call)
        if knowledge is None or knowledge is False:
            _knowledge_config = None
        elif knowledge is True:
            _knowledge_config = KnowledgeConfig()
        elif isinstance(knowledge, KnowledgeConfig):
            _knowledge_config = knowledge
        elif isinstance(knowledge, list):
            _knowledge_config = KnowledgeConfig(sources=knowledge)
        elif hasattr(knowledge, 'search') and hasattr(knowledge, 'add'):
            _knowledge_config = knowledge  # Knowledge instance passthrough
        else:
            _knowledge_config = resolve(
                value=knowledge,
                param_name="knowledge",
                config_class=KnowledgeConfig,
                instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
                array_mode=ArrayMode.SOURCES_WITH_CONFIG,
                string_mode="path_as_source",
                default=None,
            )
        
        if _knowledge_config is not None:
            if hasattr(_knowledge_config, 'search') and hasattr(_knowledge_config, 'add'):
                # Knowledge instance - pass through
                knowledge = _knowledge_config
            elif isinstance(_knowledge_config, KnowledgeConfig):
                embedder_config = _knowledge_config.embedder_config
                if _knowledge_config.config:
                    retrieval_config = _knowledge_config.config
                else:
                    retrieval_config = {
                        'top_k': _knowledge_config.retrieval_k,
                        'threshold': _knowledge_config.retrieval_threshold,
                        'rerank': _knowledge_config.rerank,
                        'rerank_model': _knowledge_config.rerank_model,
                    }
                knowledge = _knowledge_config.sources if _knowledge_config.sources else None
            elif isinstance(_knowledge_config, list):
                knowledge = _knowledge_config
        elif knowledge is False:
            knowledge = None
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve PLANNING param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None/False -> no planning (skip resolve() call)
        if planning is None or planning is False:
            _planning_config = None
        elif planning is True:
            _planning_config = PlanningConfig()
        elif isinstance(planning, PlanningConfig):
            _planning_config = planning
        else:
            _planning_config = resolve(
                value=planning,
                param_name="planning",
                config_class=PlanningConfig,
                presets=PLANNING_PRESETS,
                string_mode="llm_model",
                array_mode=ArrayMode.PRESET_OVERRIDE,
                default=None,
            )
        
        if _planning_config is not None:
            if isinstance(_planning_config, PlanningConfig):
                planning = True
                planning_tools = _planning_config.tools
                planning_reasoning = _planning_config.reasoning
                plan_mode = _planning_config.read_only
            else:
                planning = bool(_planning_config)
        elif planning is True:
            pass  # Keep as True
        else:
            planning = False
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve REFLECTION param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None/False -> no reflection (skip resolve() call)
        if reflection is None or reflection is False:
            _reflection_config = None
        elif reflection is True:
            _reflection_config = ReflectionConfig()
        elif isinstance(reflection, ReflectionConfig):
            _reflection_config = reflection
        else:
            _reflection_config = resolve(
                value=reflection,
                param_name="reflection",
                config_class=ReflectionConfig,
                presets=REFLECTION_PRESETS,
                array_mode=ArrayMode.PRESET_OVERRIDE,
                default=None,
            )
        
        if _reflection_config is not None:
            if isinstance(_reflection_config, ReflectionConfig):
                self_reflect = True
                min_reflect = _reflection_config.min_iterations
                max_reflect = _reflection_config.max_iterations
                reflect_llm = _reflection_config.llm
                reflect_prompt = _reflection_config.prompt
            else:
                self_reflect = bool(_reflection_config)
        elif reflection is True:
            self_reflect = True
        elif reflection is False:
            self_reflect = False
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve GUARDRAILS param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None/False -> no guardrails (skip resolve() call)
        if guardrails is None or guardrails is False:
            _guardrails_config = None
        elif callable(guardrails) and not isinstance(guardrails, type):
            _guardrails_config = guardrails  # Callable passthrough
        elif isinstance(guardrails, GuardrailConfig):
            _guardrails_config = guardrails
        elif isinstance(guardrails, str):
            # String could be LLM prompt - passthrough for later processing
            _guardrails_config = guardrails
        else:
            from .._resolver_helpers import resolve_guardrails as _resolve_guardrails
            _guardrails_config = _resolve_guardrails(
                value=guardrails,
                config_class=GuardrailConfig,
            )
        
        if _guardrails_config is not None:
            if callable(_guardrails_config) and not isinstance(_guardrails_config, type):
                # Callable validator function
                guardrail = _guardrails_config
            elif isinstance(_guardrails_config, GuardrailConfig):
                guardrail = _guardrails_config.validator or _guardrails_config.llm_validator
                max_guardrail_retries = _guardrails_config.max_retries
            elif isinstance(_guardrails_config, str):
                # LLM validator prompt
                guardrail = _guardrails_config
        
        # ─────────────────────────────────────────────────────────────────────
        # Resolve WEB param - FAST PATH
        # ─────────────────────────────────────────────────────────────────────
        # Fast path: None/False -> no web (skip resolve() call)
        if web is None or web is False:
            _web_config = None
        elif web is True:
            _web_config = WebConfig()
        elif isinstance(web, WebConfig):
            _web_config = web
        else:
            _web_config = resolve(
                value=web,
                param_name="web",
                config_class=WebConfig,
                presets=WEB_PRESETS,
                array_mode=ArrayMode.PRESET_OVERRIDE,
                default=None,
            )
        
        if _web_config is not None:
            if isinstance(_web_config, WebConfig):
                web_search = _web_config.search
                web_fetch = _web_config.fetch
            else:
                web_search = bool(_web_config)
                web_fetch = bool(_web_config)
        elif web is True:
            web_search = True
            web_fetch = True
        elif web is False:
            web_search = False
            web_fetch = False
        
        # ============================================================
        # END CONSOLIDATED PARAMS EXTRACTION
        # ============================================================
        
        # Initialize autonomy features (agent-centric escalation/doom-loop)
        self._init_autonomy(autonomy, verification_hooks=verification_hooks)

        # If instructions are provided, use them to set role, goal, and backstory
        if instructions:
            # Only use explicitly provided name, don't auto-generate from instructions
            # Auto-generation was producing confusing names like "You Are Agent" from
            # instructions like "You are a helpful assistant"
            if name:
                self.name = name
                self._agent_index = None  # Named agents don't need an index
            else:
                # Don't auto-generate - None signals "no explicit name provided"
                # Display logic will skip Agent Info panel when name is None
                self.name = None
                # Assign unique index for display_name
                with Agent._agent_counter_lock:
                    Agent._agent_counter += 1
                    self._agent_index = Agent._agent_counter
            self.role = role or "Assistant"
            self.goal = goal or instructions
            self.backstory = backstory or instructions
            # Set self_reflect to False by default for instruction-based agents
            self.self_reflect = False if self_reflect is None else self_reflect
        else:
            # Use provided values or defaults
            self.name = name or "Agent"
            self._agent_index = None  # Named agents don't need an index
            self.role = role or "Assistant"
            self.goal = goal or "Help the user with their tasks"
            self.backstory = backstory or "I am an AI assistant"
            # Default to True for traditional agents if not specified
            self.self_reflect = True if self_reflect is None else self_reflect
        
        self.instructions = instructions
        # Check for model name in environment variable if not provided
        self._using_custom_llm = False
        # Flag to track if final result has been displayed to prevent duplicates
        self._final_display_shown = False
        
        # Store hooks for middleware system (zero overhead when empty)
        self._hooks = _hooks_list if _hooks_list else []
        self._middleware_manager = None  # Lazy init
        
        # Lazy init for HookRunner and StreamEventEmitter (zero overhead when not used)
        self.__hook_runner = None  # Will be initialized on first access
        self.__stream_emitter = None  # Will be initialized on first access
        self._hooks_registry_param = hooks  # Store for lazy init
        
        # Handle llm= deprecation: model= is the preferred parameter name
        # llm= still works but shows deprecation warning
        if llm is not None and model is None:
            warn_deprecated_param(
                "llm",
                since="1.0.0",
                removal="2.0.0", 
                alternative="use 'model' instead. Example: Agent(model='gpt-4o-mini')",
                stacklevel=3
            )
        # model= is the preferred parameter (no warning)
        if model is not None:
            llm = model  # model= takes precedence
        
        # Store rate limiter (optional, zero overhead when None)
        self._rate_limiter = rate_limiter
        
        # Store OpenAI client parameters for lazy initialization (kept separate)
        self._openai_api_key = api_key
        self._openai_base_url = base_url
        self.__openai_client = None
        
        # Expose base_url and api_key as properties for tests
        self.base_url = base_url
        self.api_key = api_key

        # If base_url is provided, always create a custom LLM instance
        if base_url:
            try:
                from ..llm.llm import LLM
                # Handle different llm parameter types with base_url
                if isinstance(llm, dict):
                    # Merge base_url and api_key into the dict
                    llm_config = llm.copy()
                    llm_config['base_url'] = base_url
                    if api_key:
                        llm_config['api_key'] = api_key
                    llm_config['metrics'] = metrics
                    self.llm_instance = LLM(**llm_config)
                    self.llm = llm.get('model', Agent._get_default_model())
                else:
                    # Create LLM with model string and base_url (cached for performance)
                    model_name = llm or Agent._get_default_model()
                    self.llm_instance = LLM(
                        model=model_name,
                        base_url=base_url,
                        api_key=api_key,
                        metrics=metrics,
                        web_search=web_search,
                        web_fetch=web_fetch,
                        prompt_caching=prompt_caching,
                        claude_memory=claude_memory
                    )
                    self.llm = model_name
                self._using_custom_llm = True
            except ImportError as e:
                raise ImportError(
                    "LLM features requested but dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[llm]\""
                ) from e
        # If the user passes a dictionary (for advanced configuration)
        elif isinstance(llm, dict) and "model" in llm:
            try:
                from ..llm.llm import LLM
                # Add api_key if provided and not in dict
                if api_key and 'api_key' not in llm:
                    llm = llm.copy()
                    llm['api_key'] = api_key
                # Add metrics parameter
                llm = llm.copy()
                llm['metrics'] = metrics
                self.llm_instance = LLM(**llm)  # Pass all dict items as kwargs
                self._using_custom_llm = True
                self.llm = llm.get('model', Agent._get_default_model())
            except ImportError as e:
                raise ImportError(
                    "LLM features requested but dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[llm]\""
                ) from e
        # If the user passes a string with a slash (provider/model)
        elif isinstance(llm, str) and "/" in llm:
            try:
                from ..llm.llm import LLM
                # Pass the entire string so LiteLLM can parse provider/model
                llm_params = {'model': llm}
                if api_key:
                    llm_params['api_key'] = api_key
                llm_params['metrics'] = metrics
                llm_params['web_search'] = web_search
                llm_params['web_fetch'] = web_fetch
                llm_params['prompt_caching'] = prompt_caching
                llm_params['claude_memory'] = claude_memory
                self.llm_instance = LLM(**llm_params)
                self._using_custom_llm = True
                self.llm = llm
                
                # Ensure tools are properly accessible when using custom LLM
                if tools:
                    logging.debug(f"Tools passed to Agent with custom LLM: {tools}")
                    # Store the tools for later use
                    self.tools = tools
            except ImportError as e:
                raise ImportError(
                    "LLM features requested but dependencies not installed. "
                    "Please install with: pip install \"praisonaiagents[llm]\""
                ) from e
        # Otherwise, fall back to OpenAI environment/name (cached for performance)
        else:
            self.llm = llm or Agent._get_default_model()
        # Handle tools parameter - ensure it's always a list
        if callable(tools):
            # If a single function/callable is passed, wrap it in a list
            self.tools = [tools]
        elif isinstance(tools, str):
            # Single tool name string - resolve from registry
            self.tools = self._resolve_tool_names([tools])
        elif isinstance(tools, (list, tuple)):
            # Check if list contains strings (tool names) that need resolution
            if tools and all(isinstance(t, str) for t in tools):
                self.tools = self._resolve_tool_names(tools)
            else:
                self.tools = list(tools)
        else:
            self.tools = tools or []
        
        # Inject default tools for autonomy mode (after self.tools is initialized)
        # ONLY inject if caller didn't provide tools - avoid duplicates with CLI/wrapper tools
        if self.autonomy_enabled and hasattr(self, '_autonomy_config_obj'):
            config = self._autonomy_config_obj
            if config.default_tools is not None:
                # User provided custom default tools via AutonomyConfig
                self.tools.extend(config.default_tools)
            elif not self.tools:
                # Only inject AUTONOMY_PROFILE if no tools were provided by caller
                # This prevents duplicates when CLI/wrapper already provides tools
                try:
                    from ..tools.profiles import AUTONOMY_PROFILE
                    from .. import tools as tools_module
                    resolved_tools = []
                    for tool_name in AUTONOMY_PROFILE.tools:
                        try:
                            tool = getattr(tools_module, tool_name)
                            if tool is not None:
                                resolved_tools.append(tool)
                        except AttributeError:
                            pass  # Tool not available, skip
                    self.tools.extend(resolved_tools)
                except ImportError:
                    # Fallback to ast-grep tools if profiles not available
                    try:
                        from ..tools.ast_grep_tool import get_ast_grep_tools
                        self.tools.extend(get_ast_grep_tools())
                    except ImportError:
                        pass  # No default tools available
        
        self.max_iter = max_iter
        self.max_rpm = max_rpm
        self.max_execution_time = max_execution_time
        self._memory_instance = None
        self._init_memory(memory, user_id)
        self.verbose = verbose
        self._has_explicit_output_config = _has_explicit_output  # Track if user set output mode
        self.tool_output_limit = tool_output_limit  # Configurable tool output limit
        self.allow_delegation = allow_delegation
        self.step_callback = step_callback
        # Token budget guard (zero overhead when _max_budget is None)
        self._max_budget = _max_budget
        self._on_budget_exceeded = _on_budget_exceeded
        self._total_cost = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._llm_call_count = 0
        self.cache = cache
        self.system_template = system_template
        self.prompt_template = prompt_template
        self.response_template = response_template
        self.allow_code_execution = allow_code_execution
        self.max_retry_limit = max_retry_limit
        self.code_execution_mode = code_execution_mode
        self.embedder_config = embedder_config
        self.knowledge = knowledge
        self.use_system_prompt = use_system_prompt
        # Async-safe chat_history with dual-lock protection
        self.__chat_history_state = AsyncSafeState([])
        
        # Async-safe snapshot/redo stack lock - always available even when autonomy is disabled
        self.__snapshot_state = AsyncSafeState(None)
        self.markdown = markdown
        self.stream = stream
        self.metrics = metrics
        self.max_reflect = max_reflect
        self.min_reflect = min_reflect
        self.reflect_prompt = reflect_prompt
        # Use the same model selection logic for reflect_llm (cached for performance)
        self.reflect_llm = reflect_llm or Agent._get_default_model()
        self._console = None  # Lazy load console when needed
        
        # Initialize system prompt
        self.system_prompt = f"""{self.backstory}\n
Your Role: {self.role}\n
Your Goal: {self.goal}
        """

        # Lazy generate unique ID when needed
        self._agent_id = None

        # Store user_id
        self.user_id = user_id or "praison"
        self.reasoning_steps = reasoning_steps
        self.plan_mode = plan_mode  # Read-only mode for planning
        self.planning = planning  # Enable planning mode
        self.planning_tools = planning_tools  # Tools for planning phase
        self.planning_reasoning = planning_reasoning  # Enable reasoning during planning
        self._planning_agent = None  # Lazy loaded PlanningAgent
        self.web_search = web_search
        self.web_fetch = web_fetch
        self.prompt_caching = prompt_caching
        self.claude_memory = claude_memory
        
        # Session management
        self.auto_save = auto_save  # Session name for auto-saving
        
        # Initialize rules manager for persistent context (like Cursor/Windsurf)
        # NOTE: Lazy initialization - rules are loaded only when accessed (performance optimization)
        self._rules_manager = None
        self._rules_manager_initialized = False
        
        # Handle web_search fallback: inject DuckDuckGo tool for unsupported models
        if web_search and not self._model_supports_web_search():
            from ..tools.duckduckgo_tools import internet_search
            # Check if internet_search is not already in tools
            tool_names = [getattr(t, '__name__', str(t)) for t in self.tools]
            if 'internet_search' not in tool_names and 'duckduckgo' not in tool_names:
                self.tools.append(internet_search)
                logging.info("Model does not support native web search. Added DuckDuckGo fallback tool.")
        
        # Raise error if web_fetch is explicitly enabled but model doesn't support it
        # Web fetch is only supported by Anthropic/Claude models
        if web_fetch and not self._model_supports_web_fetch():
            raise ValueError(
                f"web_fetch is only supported on Anthropic/Claude models. "
                f"Model '{self.llm}' does not support web fetch. "
                f"Either use a Claude model (e.g., 'anthropic/claude-sonnet-4') or disable fetch with web=WebConfig(fetch=False)."
            )
        
        # Initialize guardrail settings
        self.guardrail = guardrail
        self.max_guardrail_retries = max_guardrail_retries
        self._guardrail_fn = None
        self._setup_guardrail()
        
        # Initialize approval backend (agent-centric approval)
        # True = AutoApproveBackend, False/None = registry fallback,
        # object = custom backend (dangerous tools only),
        # ApprovalConfig = full control (all_tools, timeout, etc.)
        # str = permission preset ("safe", "read_only", "full")
        from ..approval.protocols import ApprovalConfig
        self._perm_deny = frozenset()  # Permission tier deny set (empty = no denials)
        self._perm_allow = None        # Permission tier allow set (None = allow all)
        if isinstance(approval, str) and approval not in ('True', 'False'):
            # Permission preset: "safe", "read_only", "full"
            from ..approval.registry import PERMISSION_PRESETS
            preset_deny = PERMISSION_PRESETS.get(approval)
            if preset_deny is not None:
                self._perm_deny = preset_deny
                self._approval_backend = None
                self._approve_all_tools = False
                self._approval_timeout = 0
            else:
                # Unknown string — treat as no approval
                self._approval_backend = None
                self._approve_all_tools = False
                self._approval_timeout = 0
        elif approval is True:
            from ..approval.backends import AutoApproveBackend
            self._approval_backend = AutoApproveBackend()
            self._approve_all_tools = False
            self._approval_timeout = 0  # 0 = use backend default
        elif approval is False or approval is None:
            self._approval_backend = None
            self._approve_all_tools = False
            self._approval_timeout = 0
        elif isinstance(approval, ApprovalConfig):
            self._approval_backend = approval.backend
            self._approve_all_tools = approval.all_tools
            self._approval_timeout = approval.timeout  # None = indefinite, 0 = backend default
        elif isinstance(approval, dict):
            # Dict config: convert to ApprovalConfig
            approval_config = ApprovalConfig(**approval)
            self._approval_backend = approval_config.backend
            self._approve_all_tools = approval_config.all_tools
            self._approval_timeout = approval_config.timeout
        else:
            # Plain backend object — dangerous tools only, backend default timeout
            self._approval_backend = approval
            self._approve_all_tools = False
            self._approval_timeout = 0
        
        # Per-agent autonomy→approval bridge (G-BRIDGE-1 fix)
        # If autonomy level is full_auto and no explicit approval was set,
        # auto-approve all tools for this agent (no global env var).
        autonomy_level = getattr(self, '_autonomy_level_for_approval', None)
        if autonomy_level == "full_auto" and (approval is False or approval is None):
            from ..approval.backends import AutoApproveBackend
            self._approval_backend = AutoApproveBackend()
        # Pending approvals for async (non-blocking) mode
        self._pending_approvals = {}
        
        # P8/G11: Tool timeout - prevent slow tools from blocking
        self._tool_timeout = tool_timeout
        
        # Cache for system prompts and formatted tools with eager thread-safe lock
        # Use OrderedDict for LRU behavior
        self._system_prompt_cache = OrderedDict()
        self._formatted_tools_cache = OrderedDict()
        self.__cache_lock = threading.RLock()  # Eager initialization to prevent race conditions
        # Limit cache size to prevent unbounded growth
        self._max_cache_size = 100

        # Process handoffs and convert them to tools
        self.handoffs = handoffs if handoffs else []
        self._process_handoffs()

        # Initialize unified retrieval configuration
        # retrieval_config is the SINGLE configuration surface (extracted from knowledge= param)
        self._retrieval_config = None
        if retrieval_config is not None:
            from ..rag.retrieval_config import RetrievalConfig
            if isinstance(retrieval_config, RetrievalConfig):
                self._retrieval_config = retrieval_config
            elif isinstance(retrieval_config, dict):
                self._retrieval_config = RetrievalConfig.from_dict(retrieval_config)
        
        # Check if knowledge parameter has any values
        if not knowledge:
            self.knowledge = None
            self._knowledge_sources = None
            self._knowledge_processed = True  # No knowledge to process
            self._rag_instance = None
        else:
            # Check if knowledge is a Knowledge instance (shared knowledge)
            if hasattr(knowledge, 'search') and hasattr(knowledge, 'add'):
                # It's a Knowledge instance - use directly
                self.knowledge = knowledge
                self._knowledge_sources = None
                self._knowledge_processed = True
            else:
                # It's a list of sources - store for lazy processing
                self._knowledge_sources = knowledge
                self._knowledge_processed = False
                self.knowledge = None  # Will be initialized on first use
            self._rag_instance = None  # Lazy loaded RAG instance
            
            # Create default retrieval config if knowledge provided but no config
            if self._retrieval_config is None:
                from ..rag.retrieval_config import RetrievalConfig
                self._retrieval_config = RetrievalConfig()

        # Agent Skills configuration (lazy loaded for zero performance impact)
        self._skills = _skills
        self._skills_dirs = skills_dirs
        self._skill_manager = None  # Lazy loaded
        self._skills_initialized = False

        # Database persistence (lazy - no imports until used)
        self._db = db
        self._session_id = session_id
        self._db_initialized = False
        
        # Session store for JSON-based persistence (lazy - no imports until used)
        # Used when session_id is provided but no DB adapter
        self._session_store = None
        self._session_store_initialized = False
        
        # History injection settings (for auto-injecting session history into context)
        self._history_enabled = _history_enabled
        self._history_limit = _history_limit
        self._history_session_id = _history_session_id
        
        # Learning configuration (top-level, peer to memory)
        # Stored for access via agent._learn_config
        self._learn_config = _learn_config

        # Agent-centric feature instances (lazy loaded for zero performance impact)
        self._auto_memory = auto_memory
        self._policy = policy
        self._background = background
        self._checkpoints = checkpoints
        self._output_style = output_style
        self._thinking_budget = thinking_budget
        
        # Context management (lazy loaded for zero overhead when disabled)
        # Smart default: auto-enable context when tools are present
        if context is None and self.tools:
            # Tools present but no explicit context setting - auto-enable
            self._context_param = True
        else:
            self._context_param = context  # Store raw param for lazy init
        self._context_manager = None  # Lazy initialized on first use
        self._context_manager_initialized = False
        self._session_dedup_cache = None  # Shared session cache from workflow
        
        # Action trace mode - handled via display callbacks, not separate emitter
        self._actions_trace = actions_trace
        
        # Output file and template - for auto-saving response to file
        self._output_file = output_file if _output_config else None
        self._output_template = output_template if _output_config else None

        # Backend - external managed agent backend for hybrid execution
        self.backend = backend

        # Telemetry - lazy initialized via property for performance
        self.__telemetry = None
        self.__telemetry_initialized = False

    @property
    def _telemetry(self):
        """Lazy-loaded telemetry instance for performance."""
        if not self.__telemetry_initialized:
            try:
                from ..telemetry import get_telemetry
                self.__telemetry = get_telemetry()
            except (ImportError, AttributeError):
                self.__telemetry = None
            self.__telemetry_initialized = True
        return self.__telemetry

    @property
    def chat_history(self):
        """Get chat history (read-only access, use context managers for modifications)."""
        return self.__chat_history_state.get()
    
    @chat_history.setter
    def chat_history(self, value):
        """Set chat history (updates the underlying async-safe state)."""
        self.__chat_history_state.value = value
    
    @property
    def _history_lock(self):
        """Get appropriate lock for chat history based on execution context."""
        return self.__chat_history_state

    @property
    def _cache_lock(self):
        """Thread-safe cache lock."""
        return self.__cache_lock

    @property
    def _snapshot_lock(self):
        """Async-safe snapshot/redo stack lock."""
        return self.__snapshot_state
    
    
    @property
    def auto_memory(self) -> Optional[bool]:
        """AutoMemory instance for automatic memory extraction."""
        return self._auto_memory
    
    @auto_memory.setter
    def auto_memory(self, value: Optional[bool]) -> None:
        self._auto_memory = value

    @property
    def policy(self) -> Optional[Any]:
        """PolicyEngine instance for execution control."""
        return self._policy
    
    @policy.setter
    def policy(self, value: Optional[Any]) -> None:
        self._policy = value

    @property
    def background(self) -> Optional[bool]:
        """BackgroundRunner instance for async task execution."""
        return self._background
    
    @background.setter
    def background(self, value: Optional[bool]) -> None:
        self._background = value

    @property
    def checkpoints(self) -> Optional[bool]:
        """CheckpointService instance for file-level undo/restore."""
        return self._checkpoints
    
    @checkpoints.setter
    def checkpoints(self, value: Optional[bool]) -> None:
        self._checkpoints = value

    @property
    def output_style(self) -> Optional[str]:
        """OutputStyle instance for response formatting."""
        return self._output_style
    
    @output_style.setter
    def output_style(self, value: Optional[str]) -> None:
        self._output_style = value

    @property
    def thinking_budget(self) -> Optional[int]:
        """ThinkingBudget instance for extended thinking control."""
        return self._thinking_budget
    
    @thinking_budget.setter
    def thinking_budget(self, value: Optional[int]) -> None:
        self._thinking_budget = value

    @property
    def total_cost(self) -> float:
        """Cumulative USD cost of all LLM calls in this agent run."""
        return self._total_cost

    @property
    def cost_summary(self) -> dict:
        """Summary of cost and token usage.

        Returns:
            dict with keys: tokens_in, tokens_out, cost, llm_calls
        """
        return {
            "tokens_in": self._total_tokens_in,
            "tokens_out": self._total_tokens_out,
            "cost": self._total_cost,
            "llm_calls": self._llm_call_count,
        }

    @property
    def context_manager(self) -> Optional[Any]:
        """
        ContextManager instance for unified context management.
        
        Lazy initialized on first access when context=True or context=ManagerConfig.
        Returns None when context=False (zero overhead).
        
        Example:
            agent = Agent(instructions="...", context=True)
            # Access manager for advanced operations
            if agent.context_manager:
                stats = agent.context_manager.get_stats()
        """
        if self._context_manager_initialized:
            return self._context_manager
        
        # Initialize based on context param type
        if self._context_param is False or self._context_param is None:
            # Zero overhead - no context management
            self._context_manager = None
            self._context_manager_initialized = True
            return None
        
        # Lazy import to avoid overhead when not used
        try:
            from ..context import ContextManager, ManagerConfig
        except ImportError:
            # Context module not available
            self._context_manager = None
            self._context_manager_initialized = True
            return None
        
        if self._context_param is True:
            # Enable with safe defaults
            self._context_manager = ContextManager(
                model=self.llm if isinstance(self.llm, str) else "gpt-4o-mini",
                agent_name=self.name or "Agent",
                session_cache=self._session_dedup_cache,  # Share session cache from workflow
                llm_summarize_fn=self._create_llm_summarize_fn(),  # Auto-wire LLM summarization
            )
        elif isinstance(self._context_param, ManagerConfig):
            # Use provided ManagerConfig
            self._context_manager = ContextManager(
                model=self.llm if isinstance(self.llm, str) else "gpt-4o-mini",
                config=self._context_param,
                agent_name=self.name or "Agent",
                session_cache=self._session_dedup_cache,  # Share session cache from workflow
                llm_summarize_fn=self._create_llm_summarize_fn() if self._context_param.llm_summarize else None,
            )
        elif hasattr(self._context_param, 'auto_compact') and hasattr(self._context_param, 'tool_output_max'):
            # ContextConfig from YAML - convert to ManagerConfig
            try:
                from ..context.models import ContextConfig as _ContextConfig
                if isinstance(self._context_param, _ContextConfig):
                    # Build ManagerConfig from ContextConfig fields
                    manager_config = ManagerConfig(
                        auto_compact=self._context_param.auto_compact,
                        compact_threshold=self._context_param.compact_threshold,
                        strategy=self._context_param.strategy,
                        output_reserve=self._context_param.output_reserve,
                        default_tool_output_max=self._context_param.tool_output_max,  # Map field name
                        protected_tools=list(self._context_param.protected_tools),
                        keep_recent_turns=self._context_param.keep_recent_turns,
                        monitor_enabled=self._context_param.monitor.enabled if self._context_param.monitor else False,
                    )
                    # Check if llm_summarize is enabled in ContextConfig
                    llm_summarize_enabled = getattr(self._context_param, 'llm_summarize', False)
                    if llm_summarize_enabled:
                        manager_config.llm_summarize = True
                    self._context_manager = ContextManager(
                        model=self.llm if isinstance(self.llm, str) else "gpt-4o-mini",
                        config=manager_config,
                        agent_name=self.name or "Agent",
                        session_cache=self._session_dedup_cache,  # Share session cache from workflow
                        llm_summarize_fn=self._create_llm_summarize_fn() if llm_summarize_enabled else None,
                    )
                else:
                    self._context_manager = None
            except Exception as e:
                logging.debug(f"ContextConfig conversion failed: {e}")
                self._context_manager = None
        elif hasattr(self._context_param, 'process'):
            # Already a ContextManager instance
            self._context_manager = self._context_param
        elif isinstance(self._context_param, str):
            # String preset: "sliding_window", "summarize", "truncate"
            from ..config.presets import CONTEXT_PRESETS
            preset_config = CONTEXT_PRESETS.get(self._context_param)
            if preset_config is not None:
                # Convert preset to ContextConfig, then to ManagerConfig
                try:
                    from ..context.models import ContextConfig as _ContextConfig
                    context_config = _ContextConfig(**preset_config)
                    manager_config = ManagerConfig(
                        auto_compact=context_config.auto_compact,
                        compact_threshold=context_config.compact_threshold,
                        strategy=context_config.strategy,
                        output_reserve=context_config.output_reserve,
                        default_tool_output_max=context_config.tool_output_max,
                        protected_tools=list(context_config.protected_tools),
                        keep_recent_turns=context_config.keep_recent_turns,
                        monitor_enabled=context_config.monitor.enabled if context_config.monitor else False,
                    )
                    self._context_manager = ContextManager(
                        model=self.llm if isinstance(self.llm, str) else "gpt-4o-mini",
                        config=manager_config,
                        agent_name=self.name or "Agent",
                        session_cache=self._session_dedup_cache,
                        llm_summarize_fn=None,
                    )
                except Exception as e:
                    logging.debug(f"Context preset conversion failed: {e}")
                    self._context_manager = None
            else:
                # Unknown string preset, disable
                self._context_manager = None
        elif isinstance(self._context_param, dict):
            # Dict config: convert to ContextConfig, then to ManagerConfig
            try:
                from ..context.models import ContextConfig as _ContextConfig
                context_config = _ContextConfig(**self._context_param)
                manager_config = ManagerConfig(
                    auto_compact=context_config.auto_compact,
                    compact_threshold=context_config.compact_threshold,
                    strategy=context_config.strategy,
                    output_reserve=context_config.output_reserve,
                    default_tool_output_max=context_config.tool_output_max,
                    protected_tools=list(context_config.protected_tools),
                    keep_recent_turns=context_config.keep_recent_turns,
                    monitor_enabled=context_config.monitor.enabled if context_config.monitor else False,
                )
                llm_summarize_enabled = self._context_param.get('llm_summarize', False)
                self._context_manager = ContextManager(
                    model=self.llm if isinstance(self.llm, str) else "gpt-4o-mini",
                    config=manager_config,
                    agent_name=self.name or "Agent",
                    session_cache=self._session_dedup_cache,
                    llm_summarize_fn=self._create_llm_summarize_fn() if llm_summarize_enabled else None,
                )
            except Exception as e:
                logging.debug(f"Context dict conversion failed: {e}")
                self._context_manager = None
        else:
            # Unknown type, disable
            self._context_manager = None
        
        self._context_manager_initialized = True
        return self._context_manager
    
    @context_manager.setter
    def context_manager(self, value):
        """Set context manager directly."""
        self._context_manager = value
        self._context_manager_initialized = True

    def _create_llm_summarize_fn(self) -> Optional[Callable]:
        """
        Create an LLM summarization function using the agent's LLM.
        
        Returns a function that can be used by the context optimizer to
        intelligently summarize conversation history.
        
        Returns:
            Callable that takes (messages, max_tokens) and returns summary string,
            or None if LLM is not available.
        """
        def llm_summarize(messages: List[Dict[str, Any]], max_tokens: int = 500) -> str:
            """Summarize messages using the agent's LLM."""
            try:
                # Build summarization prompt
                conversation_text = "\n".join([
                    f"{m.get('role', 'unknown')}: {m.get('content', '')[:500]}"
                    for m in messages if m.get('content')
                ])
                
                prompt = f"""Summarize the following conversation in a concise way that preserves key information, decisions, and context. Keep the summary under {max_tokens} tokens.

Conversation:
{conversation_text}

Summary:"""
                
                # Use agent's LLM to generate summary
                client = _get_llm_functions()['get_openai_client'](self.llm, self.base_url, self.api_key)
                model_name = self.llm if isinstance(self.llm, str) else "gpt-4o-mini"
                
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=0.3,
                )
                
                return response.choices[0].message.content or "[Summary unavailable]"
            except Exception as e:
                logging.debug(f"LLM summarization failed: {e}")
                return f"[Previous conversation summary - {len(messages)} messages]"
        
        return llm_summarize

    @property
    def console(self) -> Optional[Any]:
        """Lazily initialize Rich Console only when needed AND verbose is True."""
        # Only return console if verbose mode is enabled
        # This prevents panels from being shown in status/silent modes
        if not self.verbose:
            return None
        if self._console is None:
            from rich.console import Console
            self._console = _get_console()()
        return self._console
    
    @property
    def skill_manager(self) -> Optional[Any]:
        """Lazily initialize SkillManager only when skills are accessed."""
        if self._skill_manager is None and (self._skills or self._skills_dirs):
            from ..skills import SkillManager
            self._skill_manager = SkillManager()
            
            # Add explicit skill paths
            if self._skills:
                for skill_path in self._skills:
                    self._skill_manager.add_skill(skill_path)
            
            # Discover skills from directories
            if self._skills_dirs:
                self._skill_manager.discover(self._skills_dirs, include_defaults=False)
            
            self._skills_initialized = True
            
            # Auto-add skill execution tools if not already present
            self._add_skill_tools()
        return self._skill_manager
    
    def _add_skill_tools(self):
        """Add tools required for skill execution (read_file, run_skill_script).
        
        Uses lazy imports from praisonaiagents.tools to avoid performance impact
        when skills are not used.
        """
        # Check if tools already include required capabilities
        tool_names = set()
        for tool in self.tools:
            if callable(tool) and hasattr(tool, '__name__'):
                tool_names.add(tool.__name__)
            elif hasattr(tool, 'name'):
                tool_names.add(tool.name)
        
        # Add read_file if not present
        if 'read_file' not in tool_names:
            try:
                from ..tools import read_file
                self.tools.append(read_file)
                logging.debug("Added read_file tool for skill support")
            except ImportError:
                logging.warning("Could not import read_file tool for skills")
        
        # Add run_skill_script from skill_tools module
        if 'run_skill_script' not in tool_names:
            try:
                from ..tools.skill_tools import create_skill_tools
                # Create skill tools with current working directory
                skill_tools = create_skill_tools()
                self.tools.append(skill_tools.run_skill_script)
                logging.debug("Added run_skill_script tool for skill support")
            except ImportError as e:
                logging.warning(f"Could not import skill_tools: {e}")
    
    def get_skills_prompt(self) -> str:
        """Get the XML prompt for available skills.
        
        Returns:
            XML string with <available_skills> block, or empty string if no skills
        """
        if self.skill_manager is None:
            return ""
        return self.skill_manager.to_prompt()
    
    @property
    def _openai_client(self):
        """Lazily initialize OpenAI client only when needed."""
        if self.__openai_client is None:
            try:
                self.__openai_client = _get_llm_functions()['get_openai_client'](
                    api_key=self._openai_api_key, 
                    base_url=self._openai_base_url
                )
            except ValueError as e:
                # If we're using a custom LLM, we might not need the OpenAI client
                # Return None and let the calling code handle it
                if self._using_custom_llm:
                    return None
                else:
                    raise e
        return self.__openai_client

    @property
    def agent_id(self) -> str:
        """Lazily generate agent ID when first accessed."""
        if self._agent_id is None:
            import uuid
            self._agent_id = str(uuid.uuid4())
        return self._agent_id
    
    @property
    def display_name(self) -> str:
        """Safe display name that never returns None.
        
        Returns the agent's name if set, otherwise returns 'Agent N' where N is a unique index.
        Use this for UI display, logging, and string operations where None would cause errors.
        """
        if self.name:
            return self.name
        # Use unique index for nameless agents
        if hasattr(self, '_agent_index') and self._agent_index is not None:
            return f"Agent {self._agent_index}"
        return "Agent"
    
    def _init_autonomy(self, autonomy: Any, verification_hooks: Optional[List[Any]] = None) -> None:
        """Initialize autonomy features (agent-centric escalation/doom-loop).
        
        Args:
            autonomy: True, False, dict config, or AutonomyConfig
            verification_hooks: Optional list of verification hooks
        """
        # Initialize verification hooks (always available, even without autonomy)
        self._verification_hooks = verification_hooks or []
        
        if autonomy is None or autonomy is False:
            self.autonomy_enabled = False
            self.autonomy_config = {}
            self._autonomy_trigger = None
            self._doom_loop_tracker = None
            self._file_snapshot = None
            self._snapshot_stack = []
            self._redo_stack = []
            self._autonomy_turn_tool_count = 0
            self._consecutive_no_tool_turns = 0
            self._doom_recovery_active = False
            return
        
        self.autonomy_enabled = True
        
        # Lazy import to avoid overhead when not used
        from .autonomy import AutonomyConfig, AutonomyTrigger, DoomLoopTracker
        
        if autonomy is True:
            config = AutonomyConfig()
        elif isinstance(autonomy, dict):
            config = AutonomyConfig.from_dict(autonomy)
            # Extract verification_hooks from dict if provided
            if "verification_hooks" in autonomy and not verification_hooks:
                self._verification_hooks = autonomy.get("verification_hooks", [])
        elif isinstance(autonomy, AutonomyConfig):
            config = autonomy
            # Extract verification_hooks from AutonomyConfig if provided
            if autonomy.verification_hooks and not verification_hooks:
                self._verification_hooks = autonomy.verification_hooks
        elif isinstance(autonomy, str):
            # String preset: "suggest", "auto_edit", "full_auto"
            from ..config.presets import AUTONOMY_PRESETS
            preset_config = AUTONOMY_PRESETS.get(autonomy)
            if preset_config is not None:
                config = AutonomyConfig.from_dict(preset_config)
            else:
                # Unknown string preset — disable autonomy
                self.autonomy_enabled = False
                self.autonomy_config = {}
                self._autonomy_trigger = None
                self._doom_loop_tracker = None
                self._file_snapshot = None
                self._snapshot_stack = []
                self._redo_stack = []
                self._autonomy_turn_tool_count = 0
                self._consecutive_no_tool_turns = 0
                self._doom_recovery_active = False
                return
        else:
            self.autonomy_enabled = False
            self.autonomy_config = {}
            self._autonomy_trigger = None
            self._doom_loop_tracker = None
            self._file_snapshot = None
            self._snapshot_stack = []
            self._redo_stack = []
            self._autonomy_turn_tool_count = 0
            self._consecutive_no_tool_turns = 0
            self._doom_recovery_active = False
            return
        
        # Preserve ALL AutonomyConfig fields in the dict (G14 fix: no lossy extraction)
        self.autonomy_config = {
            "enabled": config.enabled,
            "level": config.level,
            "mode": config.mode,
            "max_iterations": config.max_iterations,
            "doom_loop_threshold": config.doom_loop_threshold,
            "auto_escalate": config.auto_escalate,
            "observe": config.observe,
            "completion_promise": config.completion_promise,
            "clear_context": config.clear_context,
            "track_changes": config.effective_track_changes,
            "snapshot_dir": config.snapshot_dir,
            "default_tools": config.default_tools,
        }
        # Also preserve any extra user-provided keys from dict input
        if isinstance(autonomy, dict):
            for k, v in autonomy.items():
                if k not in self.autonomy_config:
                    self.autonomy_config[k] = v
        
        # Store the AutonomyConfig object for typed access
        self._autonomy_config_obj = config
        
        self._autonomy_trigger = AutonomyTrigger()
        self._doom_loop_tracker = DoomLoopTracker(threshold=config.doom_loop_threshold)
        self._doom_recovery_active = False
        
        # Initialize FileSnapshot for filesystem tracking (lazy import)
        self._file_snapshot = None
        self._snapshot_stack = []  # Stack of snapshot hashes for undo/redo
        self._redo_stack = []  # Redo stack
        if config.effective_track_changes:
            try:
                from ..snapshot import FileSnapshot
                import os
                self._file_snapshot = FileSnapshot(
                    project_path=os.getcwd(),
                    snapshot_dir=config.snapshot_dir,
                )
            except Exception as e:
                logger.debug(f"FileSnapshot init failed (git may not be available): {e}")
        
        # Wire ObservabilityHooks when observe=True (G-UNUSED-2 fix)
        if config.observe:
            from ..escalation.observability import ObservabilityHooks
            self._observability_hooks = ObservabilityHooks()
        else:
            self._observability_hooks = None
        
        # Wire level → approval bridge (G3 fix)
        self._bridge_autonomy_level(config.level)
    
    # ================================================================
    # Filesystem tracking convenience methods (powered by FileSnapshot)
    # ================================================================
    
    def undo(self) -> bool:
        """Undo the last set of file changes.
        
        Restores files to the state before the last autonomous iteration.
        Requires ``autonomy=AutonomyConfig(track_changes=True)``.
        
        Returns:
            True if undo was successful, False if nothing to undo.
            
        Example::
        
            agent = Agent(autonomy="full_auto")
            result = agent.start("Refactor utils.py")
            agent.undo()  # Restore original files
        """
        if self._file_snapshot is None:
            return False
        
        with self._snapshot_lock:
            if not self._snapshot_stack:
                return False
            try:
                target_hash = self._snapshot_stack.pop()
                # Get current hash before restore (for redo)
                current_hash = self._file_snapshot.get_current_hash()
                if current_hash:
                    self._redo_stack.append(current_hash)
                self._file_snapshot.restore(target_hash)
                return True
            except Exception as e:
                logger.debug(f"Undo failed: {e}")
                return False
    
    def redo(self) -> bool:
        """Redo a previously undone set of file changes.
        
        Re-applies file changes that were reverted by :meth:`undo`.
        
        Returns:
            True if redo was successful, False if nothing to redo.
        """
        if self._file_snapshot is None:
            return False
        
        with self._snapshot_lock:
            if not self._redo_stack:
                return False
            try:
                target_hash = self._redo_stack.pop()
                current_hash = self._file_snapshot.get_current_hash()
                if current_hash:
                    self._snapshot_stack.append(current_hash)
                self._file_snapshot.restore(target_hash)
                return True
            except Exception as e:
                logger.debug(f"Redo failed: {e}")
                return False
    
    def diff(self, from_hash: Optional[str] = None):
        """Get file diffs from autonomous execution.
        
        Returns a list of :class:`FileDiff` objects showing what files
        were modified, with additions/deletions counts.
        
        Args:
            from_hash: Base commit hash to diff from. If None, uses the
                first snapshot (pre-autonomous state).
        
        Returns:
            List of FileDiff objects, or empty list if tracking not enabled.
            
        Example::
        
            agent = Agent(autonomy="full_auto")
            result = agent.start("Refactor utils.py")
            for d in agent.diff():
                print(f"{d.status}: {d.path} (+{d.additions}/-{d.deletions})")
        """
        if self._file_snapshot is None:
            return []
        try:
            base = from_hash
            if base is None:
                # Protect snapshot stack read with lock to prevent TOCTOU with undo/redo
                with self._snapshot_lock:
                    if self._snapshot_stack:
                        base = self._snapshot_stack[0]
            if base is None:
                return []
            return self._file_snapshot.diff(base)
        except Exception as e:
            logger.debug(f"Diff failed: {e}")
            return []
    
    def analyze_prompt(self, prompt: str) -> set:
        """Analyze prompt for autonomy signals.
        
        Args:
            prompt: The user prompt
            
        Returns:
            Set of detected signal names
        """
        if not self.autonomy_enabled or self._autonomy_trigger is None:
            return set()
        return self._autonomy_trigger.analyze(prompt)
    
    def get_recommended_stage(self, prompt: str) -> str:
        """Get recommended execution stage for prompt.
        
        Args:
            prompt: The user prompt
            
        Returns:
            Stage name as string (direct, heuristic, planned, autonomous)
        """
        if not self.autonomy_enabled or self._autonomy_trigger is None:
            return "direct"
        
        signals = self._autonomy_trigger.analyze(prompt)
        stage = self._autonomy_trigger.recommend_stage(signals)
        return stage.name.lower()
    
    def _record_action(self, action_type: str, args: dict, result: Any, success: bool) -> None:
        """Record an action for doom loop tracking.
        
        Args:
            action_type: Type of action
            args: Action arguments
            result: Action result
            success: Whether action succeeded
        """
        if self._doom_loop_tracker is not None:
            self._doom_loop_tracker.record(action_type, args, result, success)
    
    def _is_doom_loop(self) -> bool:
        """Check if we're in a doom loop.
        
        Returns:
            True if doom loop detected
        """
        if self._doom_loop_tracker is None:
            return False
        return self._doom_loop_tracker.is_doom_loop()
    
    def _reset_doom_loop(self) -> None:
        """Reset doom loop tracking."""
        if self._doom_loop_tracker is not None:
            self._doom_loop_tracker.reset()
    
    @staticmethod
    def _is_completion_signal(response_text: str) -> bool:
        """Check if response contains a completion signal using word boundaries.
        
        Uses regex word boundaries to avoid false positives like
        'abandoned' matching 'done' or 'unfinished' matching 'finished'.
        
        Args:
            response_text: The agent response to check
            
        Returns:
            True if a completion signal is detected
        """
        import re
        response_lower = response_text.lower()
        # Negation patterns that should NOT be treated as completion
        _NEGATION_RE = re.compile(
            r'\b(?:not|never|no longer|hardly|barely|isn\'t|aren\'t|wasn\'t|weren\'t|hasn\'t|haven\'t|hadn\'t|won\'t|wouldn\'t|can\'t|couldn\'t|shouldn\'t|don\'t|doesn\'t|didn\'t)\b'
            r'.{0,20}'   # up to 20 chars between negation and keyword
        )
        # Word-boundary patterns to avoid substring false positives
        _COMPLETION_PATTERNS = [
            (re.compile(r'\btask\s+completed?\b'), False),         # no negation check needed
            (re.compile(r'\bcompleted\s+successfully\b'), False),
            (re.compile(r'\ball\s+done\b'), False),
            (re.compile(r'\bdone\b'), True),          # 'done' needs negation check
            (re.compile(r'\bfinished\b'), True),      # 'finished' needs negation check
        ]
        for pattern, needs_negation_check in _COMPLETION_PATTERNS:
            match = pattern.search(response_lower)
            if match:
                if needs_negation_check:
                    # Check if a negation word precedes the match within 30 chars
                    start = max(0, match.start() - 30)
                    prefix = response_lower[start:match.start()]
                    if _NEGATION_RE.search(prefix):
                        continue  # Skip — negated completion
                    # Also check "not X yet" pattern
                    end = min(len(response_lower), match.end() + 10)
                    suffix = response_lower[match.end():end]
                    if 'yet' in suffix:
                        neg_prefix = response_lower[max(0, match.start() - 15):match.start()]
                        if 'not' in neg_prefix:
                            continue
                return True
        return False
    
    def _get_doom_recovery(self) -> str:
        """Get doom loop recovery action from tracker.
        
        Returns:
            Recovery action string: continue, retry_different, escalate_model,
            request_help, or abort
        """
        if self._doom_loop_tracker is None:
            return "continue"
        return self._doom_loop_tracker.get_recovery_action()
    
    def _bridge_autonomy_level(self, level: str) -> None:
        """Bridge autonomy level to per-agent approval backend (G3/G-BRIDGE-1 fix).
        
        Sets a flag so the approval backend setup (later in __init__) can
        configure per-agent approval based on autonomy level.
        Does NOT use global env var — ensures multi-agent isolation.
        
        Args:
            level: Autonomy level string (suggest, auto_edit, full_auto)
        """
        # Store the requested autonomy level for the approval setup to use.
        # The actual _approval_backend is configured later in __init__
        # (after _init_autonomy), so we set a flag here.
        self._autonomy_level_for_approval = level
    
    def run_autonomous(
        self,
        prompt: str,
        max_iterations: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        completion_promise: Optional[str] = None,
        clear_context: bool = False,
    ):
        """Run an autonomous task execution loop.
        
        This method executes a task autonomously, using the agent's tools
        and capabilities to complete the task. It handles:
        - Progressive escalation based on task complexity
        - Doom loop detection and recovery
        - Iteration limits and timeouts
        - Completion detection (keyword-based or promise-based)
        - Optional context clearing between iterations
        
        Args:
            prompt: The task to execute
            max_iterations: Override max iterations (default from config)
            timeout_seconds: Timeout in seconds (default: no timeout)
            completion_promise: Optional string that signals completion when 
                wrapped in <promise>TEXT</promise> tags in the response
            clear_context: Whether to clear chat history between iterations
                (forces agent to rely on external state like files)
            
        Returns:
            AutonomyResult with success status, output, and metadata
            
        Raises:
            ValueError: If autonomy is not enabled
            
        Example:
            agent = Agent(instructions="...", autonomy=True)
            result = agent.run_autonomous(
                "Refactor the auth module",
                completion_promise="DONE",
                clear_context=True
            )
            if result.success:
                print(result.output)
        """
        from .autonomy import AutonomyResult
        import time as time_module
        from datetime import datetime, timezone
        
        if not self.autonomy_enabled:
            raise ValueError(
                "Autonomy must be enabled to use run_autonomous(). "
                "Create agent with autonomy=True or autonomy={...}"
            )
        
        # Take initial snapshot before autonomous execution starts
        # NOTE: Snapshot tracking is disabled by default for performance (G12 fix)
        # FileSnapshot.track() walks entire project and is too slow for large codebases
        # Enable with autonomy={"snapshot": True} if needed
        if self._file_snapshot is not None and self.autonomy_config.get("snapshot", False):
            try:
                snap_info = self._file_snapshot.track(message="pre-autonomous")
                with self._snapshot_lock:
                    self._snapshot_stack.append(snap_info.commit_hash)
                    self._redo_stack.clear()
            except Exception as e:
                logging.debug(f"Pre-autonomous snapshot failed: {e}")
        
        start_time = time_module.time()
        started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        iterations = 0
        actions_taken = []
        
        # Get config values
        config_max_iter = self.autonomy_config.get("max_iterations", 20)
        effective_max_iter = max_iterations if max_iterations is not None else config_max_iter
        
        # Get completion_promise from config if not provided as param
        effective_promise = completion_promise
        if effective_promise is None:
            effective_promise = self.autonomy_config.get("completion_promise")
        
        # Get clear_context from config if not explicitly set
        effective_clear_context = clear_context
        if not clear_context:
            effective_clear_context = self.autonomy_config.get("clear_context", False)
        
        # Analyze prompt and get recommended stage
        stage = self.get_recommended_stage(prompt)
        
        # Reset doom loop tracker for new task
        self._reset_doom_loop()
        
        # P3/G2: Import callback helper for autonomy events
        from ..main import execute_sync_callback
        
        try:
            # Execute the autonomous loop
            while iterations < effective_max_iter:
                iterations += 1
                
                # P3/G2: Emit autonomy_iteration callback for CLI visibility
                execute_sync_callback('autonomy_iteration',
                    iteration=iterations,
                    max_iterations=effective_max_iter,
                    stage=stage
                )
                
                # Check timeout
                if timeout_seconds and (time_module.time() - start_time) > timeout_seconds:
                    return AutonomyResult(
                        success=False,
                        output="Task timed out",
                        completion_reason="timeout",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                
                # Execute one turn using the agent's chat method
                # Always use the original prompt (prompt re-injection)
                # Reset per-turn tool count for no-tool-call detection
                self._autonomy_turn_tool_count = 0
                try:
                    response = self.chat(prompt)
                except Exception as e:
                    return AutonomyResult(
                        success=False,
                        output=str(e),
                        completion_reason="error",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        error=str(e),
                        started_at=started_at,
                    )
                
                response_str = str(response)
                
                # Record response text for content streaming loop detection
                if self._doom_loop_tracker is not None:
                    self._doom_loop_tracker.record_response(response_str)
                
                # Record the action for doom loop tracking (G1 fix: was missing)
                # Use response hash only — iteration was removed because it made
                # every fingerprint unique, preventing doom loop detection.
                self._record_action(
                    "chat", 
                    {"response_hash": hash(response_str[:500])}, 
                    response_str[:200], 
                    True
                )
                
                # Check doom loop AFTER recording action so detector sees
                # the current iteration's fingerprint (repositioned from top
                # of loop for correct detection timing).
                if self._is_doom_loop():
                    recovery = self._get_doom_recovery()
                    
                    # P3/G2: Emit doom loop callback for CLI visibility
                    execute_sync_callback('autonomy_doom_loop',
                        iteration=iterations,
                        recovery_action=recovery
                    )
                    
                    obs = getattr(self, '_observability_hooks', None)
                    if obs is not None:
                        from ..escalation.observability import EventType as _EvtType
                        obs.emit(_EvtType.STEP_END, {
                            "doom_loop": True,
                            "recovery_action": recovery,
                            "iteration": iterations,
                        })
                    if recovery == "retry_different":
                        prompt = prompt + "\n\n[System: Previous approach repeated. Try a completely different strategy.]"
                        if self._doom_loop_tracker is not None:
                            self._doom_loop_tracker.clear_actions()
                        self._consecutive_no_tool_turns = 0
                        self._doom_recovery_active = True
                        continue
                    elif recovery == "escalate_model":
                        prompt = prompt + "\n\n[System: You are stuck in a loop. CRITICAL: Check that all tool argument names exactly match the function signature. Do NOT add '=' to argument names. Use only the documented parameter names.]"
                        if self._doom_loop_tracker is not None:
                            self._doom_loop_tracker.clear_actions()
                        self._consecutive_no_tool_turns = 0
                        self._doom_recovery_active = True
                        continue
                    elif recovery == "request_help":
                        return AutonomyResult(
                            success=False,
                            output="Task needs human guidance (doom loop recovery exhausted)",
                            completion_reason="needs_help",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                    else:
                        return AutonomyResult(
                            success=False,
                            output="Task stopped due to repeated actions (doom loop)",
                            completion_reason="doom_loop",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                
                # Record for action history
                actions_taken.append({
                    "iteration": iterations,
                    "response": response_str[:500],
                })
                
                # Observability logging via ObservabilityHooks (G-UNUSED-2 fix)
                obs = getattr(self, '_observability_hooks', None)
                if obs is not None:
                    from ..escalation.observability import EventType as _EvtType
                    obs.increment_step()
                    obs.emit(_EvtType.STEP_END, {
                        "iteration": iterations,
                        "stage": stage,
                        "response_len": len(response_str),
                        "agent_name": getattr(self, 'name', None),
                    })
                elif self.autonomy_config.get("observe"):
                    get_logger(__name__).info(
                        f"[autonomy] iteration={iterations} stage={stage} "
                        f"response_len={len(response_str)}"
                    )
                
                # Auto-save session after each iteration (memory integration)
                self._auto_save_session()
                
                # ─────────────────────────────────────────────────────────────
                # TOOL-CALL COMPLETION: If the model used tools this turn AND
                # produced a substantive response, the inner loop completed
                # the task naturally (model stopped calling tools = done).
                # This is the same signal the CLI/wrapper path trusts.
                # ─────────────────────────────────────────────────────────────
                if self._autonomy_turn_tool_count > 0 and len(response_str) > 100:
                    # P3/G2: Emit completion callback
                    execute_sync_callback('autonomy_complete',
                        completion_reason="tool_completion",
                        iterations=iterations,
                        duration_seconds=time_module.time() - start_time
                    )
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="tool_completion",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                # Auto-escalate stage if stuck (G11 fix: wire auto_escalate)
                if (self.autonomy_config.get("auto_escalate")
                        and iterations > 1
                        and stage in ("direct", "heuristic")):
                    stage_order = ["direct", "heuristic", "planned", "autonomous"]
                    idx = stage_order.index(stage) if stage in stage_order else 0
                    if idx < len(stage_order) - 1:
                        prev_stage = stage
                        stage = stage_order[idx + 1]
                        
                        # P3/G2: Emit stage change callback for CLI visibility
                        execute_sync_callback('autonomy_stage_change',
                            from_stage=prev_stage,
                            to_stage=stage
                        )
                        
                        if obs is not None:
                            obs.emit(_EvtType.STAGE_ESCALATE, {"from": prev_stage, "to": stage})
                
                # Check for completion promise FIRST (structured signal)
                if effective_promise:
                    promise_tag = f"<promise>{effective_promise}</promise>"
                    if promise_tag in response_str:
                        # P3/G2: Emit completion callback
                        execute_sync_callback('autonomy_complete',
                            completion_reason="promise",
                            iterations=iterations,
                            duration_seconds=time_module.time() - start_time
                        )
                        return AutonomyResult(
                            success=True,
                            output=response_str,
                            completion_reason="promise",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                
                # Check for keyword-based completion signals (word-boundary, G-COMPLETION-1 fix)
                if self._is_completion_signal(response_str):
                    # P3/G2: Emit completion callback
                    execute_sync_callback('autonomy_complete',
                        completion_reason="goal",
                        iterations=iterations,
                        duration_seconds=time_module.time() - start_time
                    )
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="goal",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                # For DIRECT stage, complete after first response
                if stage == "direct":
                    # P3/G2: Emit completion callback
                    execute_sync_callback('autonomy_complete',
                        completion_reason="goal",
                        iterations=iterations,
                        duration_seconds=time_module.time() - start_time
                    )
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="goal",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                # Clear context between iterations if enabled
                if effective_clear_context:
                    self.clear_history()
                
                # No-tool-call termination: if model makes no tool calls for 2+
                # consecutive turns, treat as completion signal.
                # Skip first iteration (model may be planning).
                # Suppressed when doom recovery is active — once a doom loop
                # is detected, no_tool_calls (a success exit) should not fire;
                # the doom loop system manages termination instead.
                if (self._autonomy_turn_tool_count == 0 and iterations > 1
                        and not self._doom_recovery_active):
                    self._consecutive_no_tool_turns += 1
                    if self._consecutive_no_tool_turns >= 2:
                        execute_sync_callback('autonomy_complete',
                            completion_reason="no_tool_calls",
                            iterations=iterations,
                            duration_seconds=time_module.time() - start_time
                        )
                        return AutonomyResult(
                            success=True,
                            output=response_str,
                            completion_reason="no_tool_calls",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                else:
                    self._consecutive_no_tool_turns = 0
            
            # Max iterations reached
            # P3/G2: Emit completion callback for max iterations
            execute_sync_callback('autonomy_complete',
                completion_reason="max_iterations",
                iterations=iterations,
                duration_seconds=time_module.time() - start_time
            )
            return AutonomyResult(
                success=False,
                output="Max iterations reached",
                completion_reason="max_iterations",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time_module.time() - start_time,
                started_at=started_at,
            )
        
        except KeyboardInterrupt:
            return AutonomyResult(
                success=False,
                output="Task cancelled by user",
                completion_reason="cancelled",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time_module.time() - start_time,
                started_at=started_at,
            )
        except Exception as e:
            return AutonomyResult(
                success=False,
                output=str(e),
                completion_reason="error",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time_module.time() - start_time,
                error=str(e),
                started_at=started_at,
            )
    
    async def run_autonomous_async(
        self,
        prompt: str,
        max_iterations: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        completion_promise: Optional[str] = None,
        clear_context: bool = False,
    ):
        """Async variant of run_autonomous() for concurrent agent execution.
        
        This method executes a task autonomously using async I/O, enabling
        multiple agents to run concurrently without blocking. It handles:
        - Progressive escalation based on task complexity
        - Doom loop detection and recovery
        - Iteration limits and timeouts
        - Completion detection (keyword-based or promise-based)
        - Optional context clearing between iterations
        
        Args:
            prompt: The task to execute
            max_iterations: Override max iterations (default from config)
            timeout_seconds: Timeout in seconds (default: no timeout)
            completion_promise: Optional string that signals completion when 
                wrapped in <promise>TEXT</promise> tags in the response
            clear_context: Whether to clear chat history between iterations
                (forces agent to rely on external state like files)
            
        Returns:
            AutonomyResult with success status, output, and metadata
            
        Raises:
            ValueError: If autonomy is not enabled
            
        Example:
            import asyncio
            
            async def main():
                agent = Agent(instructions="...", autonomy=True)
                result = await agent.run_autonomous_async(
                    "Refactor the auth module",
                    completion_promise="DONE",
                    clear_context=True
                )
                if result.success:
                    print(result.output)
            
            asyncio.run(main())
        """
        from .autonomy import AutonomyResult
        import time as time_module
        from datetime import datetime, timezone
        import asyncio
        
        if not self.autonomy_enabled:
            raise ValueError(
                "Autonomy must be enabled to use run_autonomous_async(). "
                "Create agent with autonomy=True or autonomy={...}"
            )
        
        start_time = time_module.time()
        started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        iterations = 0
        actions_taken = []
        
        # Get config values
        config_max_iter = self.autonomy_config.get("max_iterations", 20)
        effective_max_iter = max_iterations if max_iterations is not None else config_max_iter
        
        # Get completion_promise from config if not provided as param
        effective_promise = completion_promise
        if effective_promise is None:
            effective_promise = self.autonomy_config.get("completion_promise")
        
        # Get clear_context from config if not explicitly set
        effective_clear_context = clear_context
        if not clear_context:
            effective_clear_context = self.autonomy_config.get("clear_context", False)
        
        # Analyze prompt and get recommended stage
        stage = self.get_recommended_stage(prompt)
        
        # Reset doom loop tracker for new task
        self._reset_doom_loop()
        
        try:
            # Execute the autonomous loop
            while iterations < effective_max_iter:
                iterations += 1
                
                # Check timeout
                if timeout_seconds and (time_module.time() - start_time) > timeout_seconds:
                    return AutonomyResult(
                        success=False,
                        output="Task timed out",
                        completion_reason="timeout",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                
                # Execute one turn using the agent's async chat method
                # Always use the original prompt (prompt re-injection)
                # Reset per-turn tool count for no-tool-call detection
                self._autonomy_turn_tool_count = 0
                try:
                    response = await self.achat(prompt)
                except Exception as e:
                    return AutonomyResult(
                        success=False,
                        output=str(e),
                        completion_reason="error",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        error=str(e),
                        started_at=started_at,
                    )
                
                response_str = str(response)
                
                # Record response text for content streaming loop detection
                if self._doom_loop_tracker is not None:
                    self._doom_loop_tracker.record_response(response_str)
                
                # Record the action for doom loop tracking (G1 fix: was missing)
                # Use response hash only — iteration was removed because it made
                # every fingerprint unique, preventing doom loop detection.
                self._record_action(
                    "chat", 
                    {"response_hash": hash(response_str[:500])}, 
                    response_str[:200], 
                    True
                )
                
                # Check doom loop AFTER recording action so detector sees
                # the current iteration's fingerprint (repositioned from top
                # of loop for correct detection timing).
                if self._is_doom_loop():
                    recovery = self._get_doom_recovery()
                    obs = getattr(self, '_observability_hooks', None)
                    if obs is not None:
                        from ..escalation.observability import EventType as _EvtType
                        obs.emit(_EvtType.STEP_END, {
                            "doom_loop": True,
                            "recovery_action": recovery,
                            "iteration": iterations,
                        })
                    if recovery == "retry_different":
                        prompt = prompt + "\n\n[System: Previous approach repeated. Try a completely different strategy.]"
                        if self._doom_loop_tracker is not None:
                            self._doom_loop_tracker.clear_actions()
                        self._consecutive_no_tool_turns = 0
                        self._doom_recovery_active = True
                        continue
                    elif recovery == "escalate_model":
                        prompt = prompt + "\n\n[System: You are stuck in a loop. CRITICAL: Check that all tool argument names exactly match the function signature. Do NOT add '=' to argument names. Use only the documented parameter names.]"
                        if self._doom_loop_tracker is not None:
                            self._doom_loop_tracker.clear_actions()
                        self._consecutive_no_tool_turns = 0
                        self._doom_recovery_active = True
                        continue
                    elif recovery == "request_help":
                        return AutonomyResult(
                            success=False,
                            output="Task needs human guidance (doom loop recovery exhausted)",
                            completion_reason="needs_help",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                    else:
                        return AutonomyResult(
                            success=False,
                            output="Task stopped due to repeated actions (doom loop)",
                            completion_reason="doom_loop",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                
                # Record for action history
                actions_taken.append({
                    "iteration": iterations,
                    "response": response_str[:500],
                })
                
                # Observability logging via ObservabilityHooks (G-UNUSED-2 fix)
                obs = getattr(self, '_observability_hooks', None)
                if obs is not None:
                    from ..escalation.observability import EventType as _EvtType
                    obs.increment_step()
                    obs.emit(_EvtType.STEP_END, {
                        "iteration": iterations,
                        "stage": stage,
                        "response_len": len(response_str),
                        "agent_name": getattr(self, 'name', None),
                    })
                elif self.autonomy_config.get("observe"):
                    get_logger(__name__).info(
                        f"[autonomy-async] iteration={iterations} stage={stage} "
                        f"response_len={len(response_str)}"
                    )
                
                # Auto-save session after each async iteration (memory integration)
                self._auto_save_session()
                
                # ─────────────────────────────────────────────────────────────
                # TOOL-CALL COMPLETION: If the model used tools this turn AND
                # produced a substantive response, the inner loop completed
                # the task naturally (model stopped calling tools = done).
                # ─────────────────────────────────────────────────────────────
                if self._autonomy_turn_tool_count > 0 and len(response_str) > 100:
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="tool_completion",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                # Auto-escalate stage if stuck (G11 fix: wire auto_escalate)
                if (self.autonomy_config.get("auto_escalate")
                        and iterations > 1
                        and stage in ("direct", "heuristic")):
                    stage_order = ["direct", "heuristic", "planned", "autonomous"]
                    idx = stage_order.index(stage) if stage in stage_order else 0
                    if idx < len(stage_order) - 1:
                        stage = stage_order[idx + 1]
                        if obs is not None:
                            obs.emit(_EvtType.STAGE_ESCALATE, {"from": stage_order[idx], "to": stage})
                
                # Check for completion promise FIRST (structured signal)
                if effective_promise:
                    promise_tag = f"<promise>{effective_promise}</promise>"
                    if promise_tag in response_str:
                        return AutonomyResult(
                            success=True,
                            output=response_str,
                            completion_reason="promise",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                
                # Check for keyword-based completion signals (word-boundary, G-COMPLETION-1 fix)
                if self._is_completion_signal(response_str):
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="goal",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                # For DIRECT stage, complete after first response
                if stage == "direct":
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="goal",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time_module.time() - start_time,
                        started_at=started_at,
                    )
                
                # Clear context between iterations if enabled
                if effective_clear_context:
                    self.clear_history()
                
                # No-tool-call termination: if model makes no tool calls for 2+
                # consecutive turns, treat as completion signal.
                # Suppressed when doom recovery is active — once a doom loop
                # is detected, no_tool_calls (a success exit) should not fire;
                # the doom loop system manages termination instead.
                if (self._autonomy_turn_tool_count == 0 and iterations > 1
                        and not self._doom_recovery_active):
                    self._consecutive_no_tool_turns += 1
                    if self._consecutive_no_tool_turns >= 2:
                        return AutonomyResult(
                            success=True,
                            output=response_str,
                            completion_reason="no_tool_calls",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time_module.time() - start_time,
                            started_at=started_at,
                        )
                else:
                    self._consecutive_no_tool_turns = 0
                
                # Yield control to allow other async tasks to run
                await asyncio.sleep(0)
            
            # Final auto-save before returning
            self._auto_save_session()
            
            # Max iterations reached
            return AutonomyResult(
                success=False,
                output="Max iterations reached",
                completion_reason="max_iterations",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time_module.time() - start_time,
                started_at=started_at,
            )
        
        except (KeyboardInterrupt, asyncio.CancelledError):
            return AutonomyResult(
                success=False,
                output="Task cancelled",
                completion_reason="cancelled",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time_module.time() - start_time,
                started_at=started_at,
            )
        except Exception as e:
            return AutonomyResult(
                success=False,
                output=str(e),
                completion_reason="error",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time_module.time() - start_time,
                error=str(e),
                started_at=started_at,
            )
    
    def handoff_to(
        self,
        target_agent: 'Agent',
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        config: Optional['HandoffConfig'] = None,
    ) -> 'HandoffResult':
        """
        Programmatically hand off a task to another agent.
        
        This is the unified programmatic handoff API that replaces delegate().
        It uses the same Handoff mechanism as LLM-driven handoffs but can be
        called directly from code.
        
        Args:
            target_agent: The agent to hand off to
            prompt: The task/prompt to pass to target agent
            context: Optional additional context dictionary
            config: Optional HandoffConfig for advanced settings
            
        Returns:
            HandoffResult with response or error
            
        Example:
            ```python
            result = agent_a.handoff_to(agent_b, "Complete this analysis")
            if result.success:
                print(result.response)
            ```
        """
        from .handoff import Handoff, HandoffConfig
        
        handoff_obj = Handoff(
            agent=target_agent,
            config=config or HandoffConfig(),
        )
        return handoff_obj.execute_programmatic(self, prompt, context)
    
    def run_until(
        self,
        prompt: str,
        criteria: str,
        threshold: float = 8.0,
        max_iterations: int = 5,
        mode: str = "optimize",
        on_iteration: Optional[Callable[[Any], None]] = None,
        verbose: bool = False,
    ) -> "EvaluationLoopResult":
        """
        Run agent iteratively until output meets quality criteria.
        
        This method implements the "Ralph Loop" pattern: run agent → judge output
        → improve based on feedback → repeat until threshold met.
        
        Args:
            prompt: The prompt to send to the agent
            criteria: Evaluation criteria for the Judge (e.g., "Response is thorough")
            threshold: Score threshold for success (default: 8.0, scale 1-10)
            max_iterations: Maximum iterations before stopping (default: 5)
            mode: "optimize" (stop on success) or "review" (run all iterations)
            on_iteration: Optional callback called after each iteration
            verbose: Enable verbose logging
            
        Returns:
            EvaluationLoopResult with iteration history and final score
            
        Example:
            ```python
            agent = Agent(name="analyzer", instructions="Analyze systems")
            result = agent.run_until(
                "Analyze the auth flow",
                criteria="Analysis is thorough and actionable",
                threshold=8.0,
            )
            print(result.final_score)  # 8.5
            print(result.success)      # True
            ```
        """
        from ..eval.loop import EvaluationLoop
        
        loop = EvaluationLoop(
            agent=self,
            criteria=criteria,
            threshold=threshold,
            max_iterations=max_iterations,
            mode=mode,
            on_iteration=on_iteration,
            verbose=verbose,
        )
        return loop.run(prompt)
    
    async def run_until_async(
        self,
        prompt: str,
        criteria: str,
        threshold: float = 8.0,
        max_iterations: int = 5,
        mode: str = "optimize",
        on_iteration: Optional[Callable[[Any], None]] = None,
        verbose: bool = False,
    ) -> "EvaluationLoopResult":
        """
        Async version of run_until().
        
        Run agent iteratively until output meets quality criteria.
        
        Args:
            prompt: The prompt to send to the agent
            criteria: Evaluation criteria for the Judge
            threshold: Score threshold for success (default: 8.0)
            max_iterations: Maximum iterations before stopping (default: 5)
            mode: "optimize" (stop on success) or "review" (run all iterations)
            on_iteration: Optional callback called after each iteration
            verbose: Enable verbose logging
            
        Returns:
            EvaluationLoopResult with iteration history and final score
        """
        from ..eval.loop import EvaluationLoop
        
        loop = EvaluationLoop(
            agent=self,
            criteria=criteria,
            threshold=threshold,
            max_iterations=max_iterations,
            mode=mode,
            on_iteration=on_iteration,
            verbose=verbose,
        )
        return await loop.run_async(prompt)
    
    async def handoff_to_async(
        self,
        target_agent: 'Agent',
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        config: Optional['HandoffConfig'] = None,
    ) -> 'HandoffResult':
        """
        Asynchronously hand off a task to another agent.
        
        This is the async version of handoff_to() with concurrency control
        and timeout support.
        
        Args:
            target_agent: The agent to hand off to
            prompt: The task/prompt to pass to target agent
            context: Optional additional context dictionary
            config: Optional HandoffConfig for advanced settings
            
        Returns:
            HandoffResult with response or error
            
        Example:
            ```python
            result = await agent_a.handoff_to_async(agent_b, "Complete this analysis")
            if result.success:
                print(result.response)
            ```
        """
        from .handoff import Handoff, HandoffConfig
        
        handoff_obj = Handoff(
            agent=target_agent,
            config=config or HandoffConfig(),
        )
        return await handoff_obj.execute_async(self, prompt, context)
    
    def _create_subagent(
        self,
        profile: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> 'Agent':
        """Create a subagent with the specified profile.
        
        Args:
            profile: Agent profile name
            context: Additional context
            
        Returns:
            Configured Agent instance
        """
        from ..agents.profiles import get_profile, BUILTIN_PROFILES
        
        # Get profile config
        profile_config = get_profile(profile) if profile in BUILTIN_PROFILES else None
        
        if profile_config:
            return Agent(
                name=f"subagent_{profile}",
                instructions=profile_config.system_prompt,
            )
        else:
            # Default subagent
            return Agent(
                name=f"subagent_{profile}",
                instructions=f"You are a {profile} assistant.",
            )
    
    def _run_verification_hooks(self) -> List[Dict[str, Any]]:
        """Run all registered verification hooks.
        
        Returns:
            List of verification results
        """
        results = []
        if hasattr(self, '_verification_hooks') and self._verification_hooks:
            for hook in self._verification_hooks:
                try:
                    result = hook.run()
                    results.append({
                        "hook": hook.name,
                        "success": result.get("success", False) if isinstance(result, dict) else getattr(result, 'success', False),
                        "output": result.get("output", "") if isinstance(result, dict) else getattr(result, 'output', ""),
                    })
                except Exception as e:
                    results.append({
                        "hook": getattr(hook, 'name', 'unknown'),
                        "success": False,
                        "error": str(e),
                    })
        return results

    def get_available_tools(self) -> List[Any]:
        """
        Get tools available to this agent, filtered by plan_mode if enabled.
        
        In plan_mode, only read-only tools are available to prevent
        modifications during the planning phase.
        
        Returns:
            List of available tools
        """
        if not self.plan_mode:
            return self.tools
            
        # Filter to read-only tools only
        from ..planning import RESTRICTED_TOOLS
        
        filtered_tools = []
        for tool in self.tools:
            tool_name = getattr(tool, '__name__', str(tool)).lower()
            
            # Check if tool is in restricted list
            is_restricted = any(
                restricted.lower() in tool_name 
                for restricted in RESTRICTED_TOOLS
            )
            
            if not is_restricted:
                filtered_tools.append(tool)
                
        return filtered_tools
    
    def _model_supports_web_search(self) -> bool:
        """
        Check if the agent's model supports native web search via LiteLLM.
        
        Returns:
            bool: True if the model supports native web search, False otherwise
        """
        from ..llm.model_capabilities import supports_web_search
        
        # Get the model name
        if hasattr(self, 'llm_instance') and self.llm_instance:
            model_name = self.llm_instance.model
        elif hasattr(self, 'llm') and self.llm:
            model_name = self.llm
        else:
            model_name = "gpt-4o-mini"
        
        return supports_web_search(model_name)
    
    def _model_supports_web_fetch(self) -> bool:
        """
        Check if the agent's model supports web fetch via LiteLLM.
        
        Web fetch allows the model to retrieve full content from specific URLs.
        Currently only supported by Anthropic Claude models.
        
        Returns:
            bool: True if the model supports web fetch, False otherwise
        """
        from ..llm.model_capabilities import supports_web_fetch
        
        # Get the model name
        if hasattr(self, 'llm_instance') and self.llm_instance:
            model_name = self.llm_instance.model
        elif hasattr(self, 'llm') and self.llm:
            model_name = self.llm
        else:
            model_name = "gpt-4o-mini"
        
        return supports_web_fetch(model_name)
    
    def _model_supports_prompt_caching(self) -> bool:
        """
        Check if the agent's model supports prompt caching via LiteLLM.
        
        Prompt caching allows caching parts of prompts to reduce costs and latency.
        Supported by OpenAI, Anthropic, Bedrock, and Deepseek.
        
        Returns:
            bool: True if the model supports prompt caching, False otherwise
        """
        from ..llm.model_capabilities import supports_prompt_caching
        
        # Get the model name
        if hasattr(self, 'llm_instance') and self.llm_instance:
            model_name = self.llm_instance.model
        elif hasattr(self, 'llm') and self.llm:
            model_name = self.llm
        else:
            model_name = "gpt-4o-mini"
        
        return supports_prompt_caching(model_name)
    
    @property
    def rules_manager(self) -> Optional[Any]:
        """
        Lazy-initialized RulesManager for persistent rules/instructions.
        
        This property initializes the RulesManager only when first accessed,
        avoiding expensive filesystem operations during agent instantiation.
        
        Returns:
            RulesManager instance or None if not available
        """
        if not self._rules_manager_initialized:
            self._init_rules_manager()
        return self._rules_manager
    
    def _init_rules_manager(self):
        """
        Initialize RulesManager for persistent rules/instructions.
        
        Automatically discovers rules from:
        - ~/.praisonai/rules/ (global)
        - .praisonai/rules/ (workspace)
        - Subdirectory rules
        
        NOTE: This is called lazily via the rules_manager property for performance.
        """
        self._rules_manager_initialized = True
        try:
            from ..memory.rules_manager import RulesManager
            import os
            
            # Get workspace path (current working directory)
            workspace_path = os.getcwd()
            
            self._rules_manager = RulesManager(
                workspace_path=workspace_path,
                verbose=1 if self.verbose else 0
            )
            
            # Log discovered rules
            stats = self._rules_manager.get_stats()
            if stats["total_rules"] > 0:
                logging.debug(f"RulesManager: Discovered {stats['total_rules']} rules")
        except ImportError:
            logging.debug("RulesManager not available")
            self._rules_manager = None
        except Exception as e:
            logging.debug(f"Could not initialize RulesManager: {e}")
            self._rules_manager = None
    
    def get_rules_context(self, file_path: Optional[str] = None, include_manual: Optional[List[str]] = None) -> str:
        """
        Get rules context for the current conversation.
        
        Args:
            file_path: Optional file path for glob-based rule matching
            include_manual: Optional list of manual rule names to include (via @mention)
            
        Returns:
            Formatted rules context string
        """
        if not self.rules_manager:
            return ""
        
        return self.rules_manager.build_rules_context(
            file_path=file_path,
            include_manual=include_manual
        )
    
    def _init_memory(self, memory, user_id: Optional[str] = None):
        """
        Initialize memory based on the memory parameter.
        
        Args:
            memory: Can be:
                - True: Use FileMemory with default settings
                - False/None: No memory
                - "file": Use FileMemory
                - "sqlite": Use existing Memory class with SQLite
                - dict: Configuration for memory
                - Memory/FileMemory instance: Use directly
            user_id: User identifier for memory isolation
        """
        self.memory = memory
        
        if memory is None or memory is False:
            self._memory_instance = None
            return
        
        # Determine user_id
        mem_user_id = user_id or getattr(self, 'user_id', None) or "default"
        
        if memory is True or memory == "file":
            # Use FileMemory (zero dependencies)
            from ..memory.file_memory import FileMemory
            self._memory_instance = FileMemory(
                user_id=mem_user_id,
                verbose=1 if getattr(self, 'verbose', False) else 0
            )
        elif isinstance(memory, str) and memory in ("sqlite", "chromadb", "mem0", "mongodb", "redis", "postgres"):
            # Use full Memory class with specific provider
            try:
                from ..memory.memory import Memory
                config = {"provider": memory if memory != "sqlite" else "rag"}
                self._memory_instance = Memory(config)
            except ImportError:
                logging.warning(f"Memory provider '{memory}' requires additional dependencies. Falling back to FileMemory.")
                from ..memory.file_memory import FileMemory
                self._memory_instance = FileMemory(user_id=mem_user_id)
        elif isinstance(memory, dict):
            # Configuration dict
            provider = memory.get("provider", memory.get("backend", "file"))
            learn_enabled = memory.get("learn", False)
            
            # Use full Memory class if learn is enabled (requires LearnManager)
            if learn_enabled:
                try:
                    from ..memory.memory import Memory
                    self._memory_instance = Memory(memory)
                except ImportError:
                    logging.warning("Memory with learn requires additional dependencies. Falling back to FileMemory (learn disabled).")
                    from ..memory.file_memory import FileMemory
                    self._memory_instance = FileMemory(user_id=memory.get("user_id", mem_user_id))
            elif provider == "file":
                from ..memory.file_memory import FileMemory
                self._memory_instance = FileMemory(
                    user_id=memory.get("user_id", mem_user_id),
                    config=memory
                )
            else:
                try:
                    from ..memory.memory import Memory
                    self._memory_instance = Memory(memory)
                except ImportError:
                    logging.warning("Full Memory class requires additional dependencies. Falling back to FileMemory.")
                    from ..memory.file_memory import FileMemory
                    self._memory_instance = FileMemory(user_id=mem_user_id)
        elif isinstance(memory, str):
            # Unknown string backend - fall back to FileMemory with warning
            logging.warning(f"Unknown memory backend '{memory}'. Falling back to FileMemory.")
            from ..memory.file_memory import FileMemory
            self._memory_instance = FileMemory(user_id=mem_user_id)
        else:
            # Assume it's already a memory instance
            self._memory_instance = memory
    
    def get_memory_context(self, query: Optional[str] = None) -> str:
        """
        Get memory context for the current conversation.
        
        Args:
            query: Optional query to focus the context
            
        Returns:
            Formatted memory context string
        """
        if not self._memory_instance:
            return ""
        
        if hasattr(self._memory_instance, 'get_context'):
            return self._memory_instance.get_context(query=query)
        
        return ""
    
    def get_learn_context(self) -> str:
        """
        Get learning context for injection into system prompt.
        
        Returns learned preferences, insights, and patterns when memory="learn"
        is enabled. Returns empty string when learn is not enabled (zero overhead).
        
        Returns:
            Formatted learning context string, or empty string if learn not enabled
        """
        if not self._memory_instance:
            return ""
        
        if hasattr(self._memory_instance, 'get_learn_context'):
            return self._memory_instance.get_learn_context()
        
        return ""
    
    def store_memory(self, content: str, memory_type: str = "short_term", **kwargs: Any) -> None:
        """
        Store content in memory.
        
        Args:
            content: Content to store
            memory_type: Type of memory (short_term, long_term, entity, episodic)
            **kwargs: Additional arguments for the memory method
        """
        if not self._memory_instance:
            return
        
        # Use protocol names first (store_*), fallback to legacy names (add_*)
        if memory_type == "short_term":
            if hasattr(self._memory_instance, 'store_short_term'):
                self._memory_instance.store_short_term(content, **kwargs)
            elif hasattr(self._memory_instance, 'add_short_term'):
                self._memory_instance.add_short_term(content, **kwargs)
        elif memory_type == "long_term":
            if hasattr(self._memory_instance, 'store_long_term'):
                self._memory_instance.store_long_term(content, **kwargs)
            elif hasattr(self._memory_instance, 'add_long_term'):
                self._memory_instance.add_long_term(content, **kwargs)
        elif memory_type == "entity" and hasattr(self._memory_instance, 'add_entity'):
            self._memory_instance.add_entity(content, **kwargs)
        elif memory_type == "episodic" and hasattr(self._memory_instance, 'add_episodic'):
            self._memory_instance.add_episodic(content, **kwargs)
    
    def _display_memory_info(self):
        """Display memory information to user in a friendly format."""
        if not self._memory_instance:
            return
        
        # Only display once per chat session
        if hasattr(self, '_memory_displayed') and self._memory_displayed:
            return
        self._memory_displayed = True
        
        stats = self._memory_instance.get_stats()
        short_count = stats.get('short_term_count', 0)
        long_count = stats.get('long_term_count', 0)
        entity_count = stats.get('entity_count', 0)
        storage_path = stats.get('storage_path', '')
        
        total_memories = short_count + long_count + entity_count
        
        if total_memories > 0:
            from rich.panel import Panel
            from rich.text import Text
            
            # Build memory info text
            info_parts = []
            if long_count > 0:
                info_parts.append(f"💾 {long_count} long-term")
            if short_count > 0:
                info_parts.append(f"⚡ {short_count} short-term")
            if entity_count > 0:
                info_parts.append(f"👤 {entity_count} entities")
            
            memory_text = Text()
            memory_text.append("🧠 Memory loaded: ", style="bold cyan")
            memory_text.append(" | ".join(info_parts))
            memory_text.append(f"\n📁 Storage: {storage_path}", style="dim")
            
            self.console.print(Panel(
                memory_text,
                title="[bold]Agent Memory[/bold]",
                border_style="cyan",
                expand=False
            ))
    
    @property
    def llm_model(self) -> Optional[str]:
        """Unified property to get the LLM model regardless of configuration type.
        
        Returns:
            The LLM model/instance being used by this agent.
            - For standard models: returns the model string (e.g., "gpt-4o-mini")
            - For custom LLM instances: returns the LLM instance object
            - For provider models: returns the LLM instance object
        """
        if hasattr(self, 'llm_instance') and self.llm_instance:
            return self.llm_instance
        elif hasattr(self, 'llm') and self.llm:
            return self.llm
        else:
            # Default fallback
            return "gpt-4o-mini"

    def _ensure_knowledge_processed(self):
        """Ensure knowledge is initialized and processed when first accessed."""
        if not self._knowledge_processed and self._knowledge_sources:
            # Initialize Knowledge with config from retrieval_config
            from praisonaiagents.knowledge import Knowledge
            
            knowledge_config = None
            if self._retrieval_config is not None:
                knowledge_config = self._retrieval_config.to_knowledge_config()
            
            self.knowledge = Knowledge(knowledge_config)
            
            # Process all knowledge sources
            for source in self._knowledge_sources:
                self._process_knowledge(source)
            
            self._knowledge_processed = True
    
    @property
    def retrieval_config(self) -> Optional[Any]:
        """Get the unified retrieval configuration."""
        return self._retrieval_config
    
    @property
    def rag(self) -> Optional[Any]:
        """
        Lazy-loaded RAG instance for advanced retrieval with citations.
        
        Returns RAG instance configured with agent's knowledge and retrieval_config.
        Returns None if no knowledge is configured.
        
        Usage:
            agent = Agent(knowledge=["doc.pdf"], retrieval_config={"citations": True})
            result = agent.rag.query("What is the main finding?")
            print(result.answer)
            for citation in result.citations:
                print(f"[{citation.id}] {citation.source}")
        """
        # Check if we have knowledge (either sources or direct instance)
        if not self._knowledge_sources and self.knowledge is None:
            return None
        
        if self._rag_instance is None:
            self._ensure_knowledge_processed()
            if self.knowledge:
                try:
                    from praisonaiagents.rag import RAG, RAGConfig
                    
                    # Build RAGConfig from unified retrieval_config
                    rag_config_obj = RAGConfig()
                    if self._retrieval_config is not None:
                        rag_dict = self._retrieval_config.to_rag_config()
                        for key, value in rag_dict.items():
                            if hasattr(rag_config_obj, key):
                                setattr(rag_config_obj, key, value)
                    
                    # Get LLM instance for RAG
                    llm = None
                    if hasattr(self, 'llm_instance') and self.llm_instance:
                        llm = self.llm_instance
                    
                    self._rag_instance = RAG(
                        knowledge=self.knowledge,
                        config=rag_config_obj,
                        llm=llm,
                    )
                except ImportError:
                    logging.warning("RAG module not available. Install with: pip install 'praisonaiagents[rag]'")
                    return None
        
        return self._rag_instance
    
    def _get_knowledge_context(self, query: str, use_rag: bool = False) -> tuple:
        """
        Get knowledge context for a query using unified retrieval pipeline.
        
        Args:
            query: The user's question/prompt
            use_rag: If True, use RAG pipeline for token-aware context building
            
        Returns:
            Tuple of (context_string, citations_list or None)
        """
        # Check if we have knowledge (sources or direct instance)
        if not self._knowledge_sources and self.knowledge is None:
            return "", None
        
        self._ensure_knowledge_processed()
        
        if not self.knowledge:
            return "", None
        
        # Use RAG pipeline for token-aware context building (DRY - single path)
        if use_rag and self.rag:
            try:
                context_pack = self.rag.retrieve(query, user_id=self.user_id, agent_id=self.agent_id)
                return context_pack.context, context_pack.citations
            except Exception as e:
                logging.warning(f"RAG retrieve failed, falling back to basic retrieval: {e}")
        
        # Fallback: basic retrieval with token-aware formatting
        try:
            from praisonaiagents.rag.context import build_context
            
            search_results = self.knowledge.search(query, agent_id=self.agent_id)
            if not search_results:
                return "", None
            
            # Normalize results format (filter out None values, handle None metadata)
            # Normalize results format (filter out None values, handle None metadata)
            if hasattr(search_results, "results") and isinstance(getattr(search_results, "results"), list):
                search_results = getattr(search_results, "results")
            elif isinstance(search_results, dict) and 'results' in search_results:
                search_results = search_results['results']
                
            if isinstance(search_results, list):
                results = []
                for r in search_results:
                    if r is None:
                        continue
                    if isinstance(r, dict):
                        text = r.get('memory', '') or r.get('text', '') or ''
                        metadata = r.get('metadata') or {}
                    else:
                        text = getattr(r, 'text', None) or getattr(r, 'memory', None) or ''
                        metadata = getattr(r, 'metadata', None)
                        if metadata is None:
                            metadata = {}
                    
                    if text:
                        results.append({"text": str(text), "metadata": metadata})
            else:
                results = [{"text": str(search_results), "metadata": {}}] if search_results else []
            
            # Use token-aware context building (same as RAG pipeline)
            max_tokens = 4000
            if self._retrieval_config:
                max_tokens = self._retrieval_config.max_context_tokens
            
            context, _ = build_context(results, max_tokens=max_tokens)
            return context, None
            
        except ImportError:
            # Fallback to simple concatenation if RAG context module not available
            search_results = self.knowledge.search(query, agent_id=self.agent_id)
            if not search_results:
                return "", None
            
            if isinstance(search_results, dict) and 'results' in search_results:
                # CRITICAL: Handle None results and get 'memory' field safely
                parts = []
                for result in search_results['results']:
                    if result is not None:
                        memory = result.get('memory', '') or ''
                        if memory:
                            parts.append(memory)
                knowledge_content = "\n".join(parts)
            else:
                knowledge_content = "\n".join(search_results) if isinstance(search_results, list) else str(search_results)
            
            return knowledge_content, None
    
    def retrieve(self, query: str, **kwargs) -> "ContextPack":
        """
        Retrieve context from knowledge without LLM generation.
        
        Returns a ContextPack that can be passed to chat_with_context().
        This enables conditional retrieval - only retrieve when needed.
        
        Args:
            query: Search query
            **kwargs: Additional arguments (top_k, rerank, etc.)
            
        Returns:
            ContextPack with context string and citations (no LLM call)
            
        Raises:
            ValueError: If no knowledge is configured
            ImportError: If RAG module is not available
            
        Usage:
            agent = Agent(knowledge=["docs/"], retrieval_config={"citations": True})
            context = agent.retrieve("What are the key findings?")
            print(f"Found {len(context.citations)} sources")
            response = agent.chat_with_context("Summarize", context)
        """
        if not self._knowledge_sources and self.knowledge is None:
            raise ValueError("No knowledge configured. Add knowledge=[] to Agent init.")
        
        if not self.rag:
            raise ImportError("RAG module not available. Install with: pip install 'praisonaiagents[rag]'")
        
        kwargs.setdefault('user_id', self.user_id)
        kwargs.setdefault('agent_id', self.agent_id)
        
        return self.rag.retrieve(query, **kwargs)
    
    def query(self, question: str, **kwargs) -> "RAGResult":
        """
        Query knowledge and get a structured answer with citations.
        
        This is the recommended method for getting answers with source citations.
        Returns a structured result with answer, citations, context used, and metadata.
        
        Args:
            question: The question to answer
            **kwargs: Additional arguments (top_k, rerank, etc.)
            
        Returns:
            RAGResult with answer, citations, context_used, and metadata
            
        Raises:
            ValueError: If no knowledge is configured
            ImportError: If RAG module is not available
            
        Usage:
            agent = Agent(knowledge=["doc.pdf"], retrieval_config={"citations": True})
            result = agent.query("What is the main finding?")
            print(result.answer)
            for citation in result.citations:
                print(f"  [{citation.id}] {citation.source}")
        """
        if not self._knowledge_sources and self.knowledge is None:
            raise ValueError("No knowledge configured. Add knowledge=[] to Agent init.")
        
        if not self.rag:
            raise ImportError("RAG module not available. Install with: pip install 'praisonaiagents[rag]'")
        
        kwargs.setdefault('user_id', self.user_id)
        kwargs.setdefault('agent_id', self.agent_id)
        
        return self.rag.query(question, **kwargs)
    
    def rag_query(self, question: str, **kwargs) -> "RAGResult":
        """
        Query knowledge using RAG pipeline with citations.
        
        This is the recommended way to get answers with citations from an agent's knowledge.
        
        Args:
            question: The question to answer
            **kwargs: Additional arguments passed to RAG.query()
            
        Returns:
            RAGResult with answer, citations, context_used, and metadata
            
        Raises:
            ValueError: If no knowledge sources are configured
            ImportError: If RAG module is not available
            
        Usage:
            agent = Agent(knowledge=["doc.pdf"], rag_config={"include_citations": True})
            result = agent.rag_query("What is the main finding?")
            print(result.answer)
            for citation in result.citations:
                print(f"[{citation.id}] {citation.source}: {citation.text[:100]}")
        """
        if not self._knowledge_sources:
            raise ValueError("No knowledge sources configured. Add knowledge=[] to Agent init.")
        
        if not self.rag:
            raise ImportError("RAG module not available. Install with: pip install 'praisonaiagents[rag]'")
        
        # Pass agent context
        kwargs.setdefault('user_id', self.user_id)
        kwargs.setdefault('agent_id', self.agent_id)
        
        return self.rag.query(question, **kwargs)
    
    def chat_with_context(
        self,
        message: str,
        context: "ContextPack",
        *,
        citations_mode: str = "append",
        **kwargs,
    ) -> str:
        """
        Chat with pre-retrieved context.
        
        This method allows AutoRagAgent or manual workflows to inject 
        pre-retrieved context into the agent's chat, enabling conditional 
        retrieval without duplicating RAG logic.
        
        Args:
            message: User message/question
            context: ContextPack from RAG.retrieve()
            citations_mode: How to include citations (append/hidden/none)
            **kwargs: Additional arguments passed to chat()
            
        Returns:
            Agent response with optional citations
            
        Usage:
            from praisonaiagents import AutoRagAgent
            
            auto_rag = AutoRagAgent(agent=my_agent)
            result = auto_rag.chat("What are the key findings?")
            
            # Or manually:
            context_pack = rag.retrieve("What are the key findings?")
            response = agent.chat_with_context("What are the key findings?", context_pack)
        """
        # Build augmented prompt with context
        augmented_prompt = f"""Based on the following context, answer the question.

Context:
{context.context}

Question: {message}

Answer:"""
        
        # Call chat with augmented prompt
        response = self.chat(augmented_prompt, **kwargs)
        
        # Add citations if configured
        if citations_mode == "append" and context.has_citations:
            sources = "\n\nSources:\n"
            for citation in context.citations:
                sources += f"  [{citation.id}] {citation.source}\n"
            response = response + sources
        
        return response
    
    def _process_knowledge(self, knowledge_item):
        """Process and store knowledge from a file path, URL, or string."""
        try:
            if os.path.exists(knowledge_item):
                # It's a file path
                self.knowledge.add(knowledge_item, user_id=self.user_id, agent_id=self.agent_id)
            elif knowledge_item.startswith("http://") or knowledge_item.startswith("https://"):
                # It's a URL
                pass
            else:
                # It's a string content
                self.knowledge.store(knowledge_item, user_id=self.user_id, agent_id=self.agent_id)
        except Exception as e:
            logging.error(f"Error processing knowledge item: {knowledge_item}, error: {e}")

    def _setup_guardrail(self):
        """Setup the guardrail function based on the provided guardrail parameter."""
        if self.guardrail is None:
            self._guardrail_fn = None
            return
            
        if callable(self.guardrail):
            # Validate function signature
            sig = inspect.signature(self.guardrail)
            positional_args = [
                param for param in sig.parameters.values()
                if param.default is inspect.Parameter.empty
            ]
            if len(positional_args) != 1:
                raise ValueError("Agent guardrail function must accept exactly one parameter (TaskOutput)")
            
            # Check return annotation if present
            from typing import get_args, get_origin
            return_annotation = sig.return_annotation
            if return_annotation != inspect.Signature.empty:
                return_annotation_args = get_args(return_annotation)
                if not (
                    get_origin(return_annotation) is tuple
                    and len(return_annotation_args) == 2
                    and return_annotation_args[0] is bool
                    and (
                        return_annotation_args[1] is Any
                        or return_annotation_args[1] is str
                        or str(return_annotation_args[1]).endswith('TaskOutput')
                        or str(return_annotation_args[1]).startswith('typing.Union')
                    )
                ):
                    raise ValueError(
                        "If return type is annotated, it must be Tuple[bool, Any] or Tuple[bool, Union[str, TaskOutput]]"
                    )
            
            self._guardrail_fn = self.guardrail
        elif isinstance(self.guardrail, str):
            # Create LLM-based guardrail
            from ..guardrails import LLMGuardrail
            llm = getattr(self, 'llm', None) or getattr(self, 'llm_instance', None)
            self._guardrail_fn = LLMGuardrail(description=self.guardrail, llm=llm)
        else:
            raise ValueError("Agent guardrail must be either a callable or a string description")

    def _process_handoffs(self):
        """Process handoffs and convert them to tools that can be used by the agent."""
        if not self.handoffs:
            return
            
        # Import here to avoid circular imports
        from .handoff import Handoff
        
        for handoff_item in self.handoffs:
            try:
                if isinstance(handoff_item, Handoff):
                    # Convert Handoff object to a tool function
                    tool_func = handoff_item.to_tool_function(self)
                    self.tools.append(tool_func)
                elif hasattr(handoff_item, 'name') and hasattr(handoff_item, 'chat'):
                    # Direct agent reference - create a simple handoff
                    from .handoff import handoff
                    handoff_obj = handoff(handoff_item)
                    tool_func = handoff_obj.to_tool_function(self)
                    self.tools.append(tool_func)
                else:
                    logging.warning(
                        f"Invalid handoff item type: {type(handoff_item)}. "
                        "Expected Agent or Handoff instance."
                    )
            except Exception as e:
                logging.error(f"Failed to process handoff item {handoff_item}: {e}")

    def _process_guardrail(self, task_output):
        """Process the guardrail validation for a task output.
        
        Args:
            task_output: The task output to validate
            
        Returns:
            GuardrailResult: The result of the guardrail validation
        """
        from ..guardrails import GuardrailResult
        
        if not self._guardrail_fn:
            return GuardrailResult(success=True, result=task_output)
        
        try:
            # Call the guardrail function
            result = self._guardrail_fn(task_output)
            
            # Convert the result to a GuardrailResult
            return GuardrailResult.from_tuple(result)
            
        except Exception as e:
            logging.error(f"Agent {self.name}: Error in guardrail validation: {e}")
            # On error, return failure
            return GuardrailResult(
                success=False,
                result=None,
                error=f"Agent guardrail validation error: {str(e)}"
            )

    def _apply_guardrail_with_retry(self, response_text, prompt, temperature=1.0, tools=None, task_name=None, task_description=None, task_id=None):
        """Apply guardrail validation with retry logic.
        
        Args:
            response_text: The response to validate
            prompt: Original prompt for regeneration if needed
            temperature: Temperature for regeneration
            tools: Tools for regeneration
            
        Returns:
            str: The validated response text or None if validation fails after retries
        """
        if not self._guardrail_fn:
            return response_text
            
        from ..main import TaskOutput
        
        retry_count = 0
        current_response = response_text
        
        while retry_count <= self.max_guardrail_retries:
            # Create TaskOutput object
            task_output = TaskOutput(
                description="Agent response output",
                raw=current_response,
                agent=self.name
            )
            
            # Process guardrail
            guardrail_result = self._process_guardrail(task_output)
            
            if guardrail_result.success:
                logging.info(f"Agent {self.name}: Guardrail validation passed")
                # Return the potentially modified result
                if guardrail_result.result and hasattr(guardrail_result.result, 'raw'):
                    return guardrail_result.result.raw
                elif guardrail_result.result:
                    return str(guardrail_result.result)
                else:
                    return current_response
            
            # Guardrail failed
            if retry_count >= self.max_guardrail_retries:
                raise Exception(
                    f"Agent {self.name} response failed guardrail validation after {self.max_guardrail_retries} retries. "
                    f"Last error: {guardrail_result.error}"
                )
            
            retry_count += 1
            logging.warning(f"Agent {self.name}: Guardrail validation failed (retry {retry_count}/{self.max_guardrail_retries}): {guardrail_result.error}")
            
            # Regenerate response for retry
            try:
                retry_prompt = f"{prompt}\n\nNote: Previous response failed validation due to: {guardrail_result.error}. Please provide an improved response."
                response = self._chat_completion([{"role": "user", "content": retry_prompt}], temperature, tools, task_name=task_name, task_description=task_description, task_id=task_id)
                if response and response.choices:
                    content = response.choices[0].message.content
                    current_response = content.strip() if content else ""
                else:
                    raise Exception("Failed to generate retry response")
            except Exception as e:
                logging.error(f"Agent {self.name}: Error during guardrail retry: {e}")
                # If we can't regenerate, fail the guardrail
                raise Exception(
                    f"Agent {self.name} guardrail retry failed: {e}"
                )
        
        return current_response
    
    def _get_tools_cache_key(self, tools):
        """Generate a cache key for tools list."""
        if tools is None:
            return "none"
        if not tools:
            return "empty"
        # Create a simple hash based on tool names
        tool_names = []
        for tool in tools:
            if callable(tool) and hasattr(tool, '__name__'):
                tool_names.append(tool.__name__)
            elif isinstance(tool, dict) and 'function' in tool and 'name' in tool['function']:
                tool_names.append(tool['function']['name'])
            elif isinstance(tool, str):
                tool_names.append(tool)
        return "|".join(sorted(tool_names))
    

    # -------------------------------------------------------------------------
    #                       History Management Methods
    # -------------------------------------------------------------------------
    
    
    @contextlib.contextmanager
    

    # -------------------------------------------------------------------------
    #                       Resource Lifecycle Management
    # -------------------------------------------------------------------------
    
    def close(self) -> None:
        """Synchronously close the agent and clean up resources."""
        if getattr(self, '_closed', False):
            return

        # Memory cleanup
        try:
            memory = getattr(self, "_memory_instance", None)
            if memory and hasattr(memory, 'close_connections'):
                memory.close_connections()
        except Exception as e:
            logger.warning(f"Memory cleanup failed: {e}")

        # MCP cleanup  
        try:
            if hasattr(self, '_mcp_clients') and self._mcp_clients:
                for client_name, client in self._mcp_clients.items():
                    if hasattr(client, 'close'):
                        client.close()
                self._mcp_clients.clear()
        except Exception as e:
            logger.warning(f"MCP cleanup failed: {e}")

        # Server registry cleanup
        try:
            self._cleanup_server_registrations()
        except Exception as e:
            logger.warning(f"Server cleanup failed: {e}")

        # Background tasks cleanup
        try:
            for task in getattr(self, '_background_tasks', []):
                if hasattr(task, 'cancel'):
                    task.cancel()
        except Exception as e:
            logger.warning(f"Task cleanup failed: {e}")

        # Always set closed flag
        self._closed = True
    
    async def aclose(self) -> None:
        """Async version of close() for async context managers."""
        try:
            # Close memory connections asynchronously if supported
            if hasattr(self, 'memory') and self.memory:
                if hasattr(self.memory, 'aclose'):
                    await self.memory.aclose()
                elif hasattr(self.memory, 'close_connections'):
                    self.memory.close_connections()
            
            # Close MCP sessions asynchronously if supported
            if hasattr(self, '_mcp_clients') and self._mcp_clients:
                for client in self._mcp_clients.values():
                    if hasattr(client, 'aclose'):
                        await client.aclose()
                    elif hasattr(client, 'close'):
                        client.close()
                self._mcp_clients.clear()
            
            # Clean up server registrations and tasks
            self._cleanup_server_registrations()
            
            if hasattr(self, '_background_tasks'):
                for task in self._background_tasks:
                    if hasattr(task, 'cancel'):
                        task.cancel()
                    # Wait for cancellation to complete
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            self._closed = True
            
        except Exception as e:
            logger.warning(f"Error during async agent cleanup: {e}")
    
    def _cleanup_server_registrations(self) -> None:
        """Clean up global server registry entries for this agent."""
        if getattr(self, '_agent_id', None) is None:
            return  # No ID generated, nothing registered
            
        try:
            agent_id = self._agent_id
            with _server_lock:
                # Remove from _registered_agents
                ports_to_clean = []
                for port, path_dict in _registered_agents.items():
                    paths_to_remove = []
                    for path, registered_id in path_dict.items():
                        if registered_id == agent_id:
                            paths_to_remove.append(path)
                    
                    for path in paths_to_remove:
                        del path_dict[path]
                    
                    # If no paths left for this port, mark port for cleanup
                    if not path_dict:
                        ports_to_clean.append(port)
                
                # Clean up empty port entries
                for port in ports_to_clean:
                    _registered_agents.pop(port, None)
                    _server_started.pop(port, None)
                    # Note: We don't clean up _shared_apps here as other agents might be using them
                    
        except Exception as e:
            import sys
            if sys.meta_path is not None:
                try:
                    logger.warning(f"Error cleaning up server registrations: {e}")
                except Exception:
                    pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up resources."""
        self.close()
    
    async def __aenter__(self):
        """Async context manager entry.""" 
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - clean up resources."""
        await self.aclose()
    
    def __del__(self):
        """Destructor safely does nothing to avoid GC pollution in test loops."""
        pass
        
    @property
    def is_closed(self) -> bool:
        """Returns True if the agent has been closed."""
        return getattr(self, '_closed', False)

    def __str__(self):
        return f"Agent(name='{self.name}', role='{self.role}', goal='{self.goal}')"

