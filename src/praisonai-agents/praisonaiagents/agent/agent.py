import os
import time
import json
import logging
import asyncio
import contextlib
from typing import List, Optional, Any, Dict, Union, Literal, TYPE_CHECKING, Callable, Generator
import inspect

# ============================================================================
# Performance: Lazy imports for heavy dependencies
# Rich, LLM, and display utilities are only imported when needed (output=verbose)
# This reduces import time from ~420ms to ~20ms for silent mode
# ============================================================================

# Lazy-loaded modules (populated on first use)
_rich_console = None
_rich_live = None
_llm_module = None
_main_module = None
_hooks_module = None
_stream_emitter_class = None

def _get_console():
    """Lazy load rich.console.Console."""
    global _rich_console
    if _rich_console is None:
        from rich.console import Console
        _rich_console = Console
    return _rich_console

def _get_live():
    """Lazy load rich.live.Live."""
    global _rich_live
    if _rich_live is None:
        from rich.live import Live
        _rich_live = Live
    return _rich_live

def _get_llm_functions():
    """Lazy load LLM functions."""
    global _llm_module
    if _llm_module is None:
        from ..llm import get_openai_client, process_stream_chunks
        _llm_module = {
            'get_openai_client': get_openai_client,
            'process_stream_chunks': process_stream_chunks,
        }
    return _llm_module

def _get_display_functions():
    """Lazy load display functions from main module."""
    global _main_module
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
    """Lazy load hooks module for HookRunner and HookRegistry."""
    global _hooks_module
    if _hooks_module is None:
        from ..hooks import HookRunner, HookRegistry
        _hooks_module = {
            'HookRunner': HookRunner,
            'HookRegistry': HookRegistry,
        }
    return _hooks_module

def _get_stream_emitter():
    """Lazy load StreamEventEmitter class."""
    global _stream_emitter_class
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

# Global variables for API server
_server_started = {}  # Dict of port -> started boolean
_registered_agents = {}  # Dict of port -> Dict of path -> agent_id
_shared_apps = {}  # Dict of port -> FastAPI app

# Don't import FastAPI dependencies here - use lazy loading instead

if TYPE_CHECKING:
    from ..task.task import Task
    from .handoff import Handoff, HandoffConfig, HandoffResult
    from ..rag.models import RAGResult, ContextPack

class Agent:
    # Class-level counter for generating unique display names for nameless agents
    _agent_counter = 0
    # Class-level cache for environment variables (avoid repeated os.environ.get)
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
    def stream_emitter(self):
        """Lazy-loaded StreamEventEmitter for real-time events (zero overhead when not used)."""
        if self.__stream_emitter is None:
            self.__stream_emitter = _get_stream_emitter()()
        return self.__stream_emitter
    
    @stream_emitter.setter
    def stream_emitter(self, value):
        """Allow setting stream_emitter directly."""
        self.__stream_emitter = value
    
    @classmethod
    def _get_env_output_mode(cls):
        """Get cached PRAISONAI_OUTPUT env var value."""
        if not cls._env_output_checked:
            cls._env_output_mode = os.environ.get('PRAISONAI_OUTPUT', '').lower()
            cls._env_output_checked = True
        return cls._env_output_mode
    
    @classmethod
    def _get_default_model(cls):
        """Get cached default model name from OPENAI_MODEL_NAME env var."""
        if not cls._default_model_checked:
            cls._default_model = os.getenv('OPENAI_MODEL_NAME', 'gpt-4o-mini')
            cls._default_model_checked = True
        return cls._default_model
    
    @classmethod
    def _configure_logging(cls):
        """Configure logging settings once for all agent instances."""
        # Configure logging to suppress unwanted outputs
        logging.getLogger("litellm").setLevel(logging.WARNING)
        
        # Allow httpx logging when LOGLEVEL=debug, otherwise suppress it
        loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
        if loglevel == 'DEBUG':
            logging.getLogger("httpx").setLevel(logging.INFO)
            logging.getLogger("httpcore").setLevel(logging.INFO)
        else:
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("httpcore").setLevel(logging.WARNING)
    
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
        allow_delegation: bool = False,
        allow_code_execution: Optional[bool] = False,
        code_execution_mode: Literal["safe", "unsafe"] = "safe",
        handoffs: Optional[List[Union['Agent', 'Handoff']]] = None,
        # Session management
        auto_save: Optional[str] = None,
        rate_limiter: Optional[Any] = None,
        # ============================================================
        # CONSOLIDATED FEATURE PARAMS (agent-centric API)
        # Each follows: False=disabled, True=defaults, Config=custom
        # ============================================================
        memory: Optional[Any] = None,  # Union[bool, MemoryConfig, MemoryManager]
        knowledge: Optional[Union[bool, List[str], Any]] = None,  # Union[bool, list, KnowledgeConfig, Knowledge]
        planning: Optional[Union[bool, Any]] = False,  # Union[bool, PlanningConfig]
        reflection: Optional[Union[bool, Any]] = None,  # Union[bool, ReflectionConfig]
        guardrails: Optional[Union[bool, Callable, Any]] = None,  # Union[bool, Callable, GuardrailConfig]
        web: Optional[Union[bool, Any]] = None,  # Union[bool, WebConfig]
        context: Optional[Union[bool, Any]] = None,  # Union[bool, ManagerConfig, ContextManager] - None=smart default
        autonomy: Optional[Union[bool, Dict[str, Any], Any]] = None,  # Union[bool, dict, AutonomyConfig]
        verification_hooks: Optional[List[Any]] = None,  # List of VerificationHook instances
        output: Optional[Union[str, Any]] = None,  # Union[str preset, OutputConfig]
        execution: Optional[Union[str, Any]] = None,  # Union[str preset, ExecutionConfig]
        templates: Optional[Any] = None,  # TemplateConfig
        caching: Optional[Union[bool, Any]] = None,  # Union[bool, CachingConfig]
        hooks: Optional[Union[List[Any], Any]] = None,  # Union[list, HooksConfig]
        skills: Optional[Union[List[str], Any]] = None,  # Union[list, SkillsConfig]
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
            allow_delegation: Allow task delegation to other agents. Defaults to False.
            allow_code_execution: Enable code execution during tasks. Defaults to False.
            code_execution_mode: "safe" (restricted) or "unsafe" (full access). Defaults to "safe".
            handoffs: List of Agent or Handoff objects for agent-to-agent collaboration.
            auto_save: Session name for automatic session saving.
            rate_limiter: Rate limiter instance for API call throttling.
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
                - ManagerConfig: Custom configuration
            autonomy: Autonomy settings. Accepts:
                - bool: True enables with defaults
                - Dict: Configuration dict
                - AutonomyConfig: Custom configuration
            verification_hooks: List of VerificationHook instances for output verification.
            output: Output configuration. Accepts:
                - str: Preset name ("silent", "actions", "verbose", "json", "stream")
                - OutputConfig: Custom configuration
                Controls: verbose, markdown, stream, metrics, reasoning_steps
            execution: Execution configuration. Accepts:
                - str: Preset name ("fast", "balanced", "thorough")
                - ExecutionConfig: Custom configuration
                Controls: max_iter, max_rpm, max_execution_time, max_retry_limit
            templates: Template configuration (TemplateConfig).
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
            output_file = getattr(_output_config, 'output_file', None)  # Auto-save to file
            output_template = getattr(_output_config, 'template', None)  # Response template
        else:
            # Fallback defaults match silent mode (zero overhead)
            verbose, markdown, stream, metrics, reasoning_steps = False, False, False, False, False
            actions_trace = False  # No callbacks by default
            json_output = False
            status_trace = False
            simple_output = False
        
        # Enable trace output mode if configured (takes priority)
        # This provides timestamped inline status with duration
        if status_trace:
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
        else:
            max_iter, max_rpm, max_execution_time, max_retry_limit = 20, None, None, 2
        
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
                # Convert to internal format
                backend = _memory_config.backend
                if hasattr(backend, 'value'):
                    backend = backend.value
                if backend == "file":
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
        
        # Handle model= alias for llm= (NO warnings - both are valid)
        if llm is None and model is not None:
            llm = model  # model= is an alias for llm=
        
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
        self.max_iter = max_iter
        self.max_rpm = max_rpm
        self.max_execution_time = max_execution_time
        self._memory_instance = None
        self._init_memory(memory, user_id)
        self.verbose = verbose
        self._has_explicit_output_config = _has_explicit_output  # Track if user set output mode
        self.allow_delegation = allow_delegation
        self.step_callback = step_callback
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
        # Thread-safe chat_history with lazy lock for concurrent access
        self.chat_history = []
        self.__history_lock = None  # Lazy initialized
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
        
        # Cache for system prompts and formatted tools with lazy thread-safe lock
        self._system_prompt_cache = {}
        self._formatted_tools_cache = {}
        self.__cache_lock = None  # Lazy initialized RLock
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
    def _history_lock(self):
        """Lazy-loaded history lock for thread-safe chat history access."""
        if self.__history_lock is None:
            import threading
            self.__history_lock = threading.Lock()
        return self.__history_lock

    @property
    def _cache_lock(self):
        """Lazy-loaded cache lock for thread-safe cache access."""
        if self.__cache_lock is None:
            import threading
            self.__cache_lock = threading.RLock()
        return self.__cache_lock

    @property
    def auto_memory(self):
        """AutoMemory instance for automatic memory extraction."""
        return self._auto_memory
    
    @auto_memory.setter
    def auto_memory(self, value):
        self._auto_memory = value

    @property
    def policy(self):
        """PolicyEngine instance for execution control."""
        return self._policy
    
    @policy.setter
    def policy(self, value):
        self._policy = value

    @property
    def background(self):
        """BackgroundRunner instance for async task execution."""
        return self._background
    
    @background.setter
    def background(self, value):
        self._background = value

    @property
    def checkpoints(self):
        """CheckpointService instance for file-level undo/restore."""
        return self._checkpoints
    
    @checkpoints.setter
    def checkpoints(self, value):
        self._checkpoints = value

    @property
    def output_style(self):
        """OutputStyle instance for response formatting."""
        return self._output_style
    
    @output_style.setter
    def output_style(self, value):
        self._output_style = value

    @property
    def thinking_budget(self):
        """ThinkingBudget instance for extended thinking control."""
        return self._thinking_budget
    
    @thinking_budget.setter
    def thinking_budget(self, value):
        self._thinking_budget = value

    @property
    def context_manager(self):
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
    def console(self):
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
    def skill_manager(self):
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
    def agent_id(self):
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
            return
        
        self.autonomy_enabled = True
        
        # Lazy import to avoid overhead when not used
        from .autonomy import AutonomyConfig, AutonomyTrigger, DoomLoopTracker
        
        if autonomy is True:
            self.autonomy_config = {}
            config = AutonomyConfig()
        elif isinstance(autonomy, dict):
            self.autonomy_config = autonomy.copy()
            config = AutonomyConfig.from_dict(autonomy)
            # Extract verification_hooks from dict if provided
            if "verification_hooks" in autonomy and not verification_hooks:
                self._verification_hooks = autonomy.get("verification_hooks", [])
        elif isinstance(autonomy, AutonomyConfig):
            self.autonomy_config = {
                "max_iterations": autonomy.max_iterations,
                "doom_loop_threshold": autonomy.doom_loop_threshold,
                "auto_escalate": autonomy.auto_escalate,
            }
            config = autonomy
        else:
            self.autonomy_enabled = False
            self.autonomy_config = {}
            self._autonomy_trigger = None
            self._doom_loop_tracker = None
            return
        
        self._autonomy_trigger = AutonomyTrigger()
        self._doom_loop_tracker = DoomLoopTracker(threshold=config.doom_loop_threshold)
    
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
        return stage.value
    
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
                
                # Check doom loop
                if self._is_doom_loop():
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
                
                # Execute one turn using the agent's chat method
                # Always use the original prompt (prompt re-injection)
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
                
                # Record the action
                actions_taken.append({
                    "iteration": iterations,
                    "response": str(response)[:500],
                })
                
                response_str = str(response)
                
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
                
                # Check for keyword-based completion signals (fallback)
                response_lower = response_str.lower()
                completion_signals = [
                    "task completed", "task complete", "done",
                    "finished", "completed successfully",
                ]
                
                if any(signal in response_lower for signal in completion_signals):
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
                
                # Check doom loop
                if self._is_doom_loop():
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
                
                # Execute one turn using the agent's async chat method
                # Always use the original prompt (prompt re-injection)
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
                
                # Record the action
                actions_taken.append({
                    "iteration": iterations,
                    "response": str(response)[:500],
                })
                
                response_str = str(response)
                
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
                
                # Check for keyword-based completion signals (fallback)
                response_lower = response_str.lower()
                completion_signals = [
                    "task completed", "task complete", "done",
                    "finished", "completed successfully",
                ]
                
                if any(signal in response_lower for signal in completion_signals):
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
                
                # Yield control to allow other async tasks to run
                await asyncio.sleep(0)
            
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
    def rules_manager(self):
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
        - ~/.praison/rules/ (global)
        - .praison/rules/ (workspace)
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
        elif isinstance(memory, str) and memory in ("sqlite", "chromadb", "mem0", "mongodb"):
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
            provider = memory.get("provider", "file")
            if provider == "file":
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
    
    def store_memory(self, content: str, memory_type: str = "short_term", **kwargs):
        """
        Store content in memory.
        
        Args:
            content: Content to store
            memory_type: Type of memory (short_term, long_term, entity, episodic)
            **kwargs: Additional arguments for the memory method
        """
        if not self._memory_instance:
            return
        
        if memory_type == "short_term" and hasattr(self._memory_instance, 'add_short_term'):
            self._memory_instance.add_short_term(content, **kwargs)
        elif memory_type == "long_term" and hasattr(self._memory_instance, 'add_long_term'):
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
    def llm_model(self):
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
    def retrieval_config(self):
        """Get the unified retrieval configuration."""
        return self._retrieval_config
    
    @property
    def rag(self):
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
            if isinstance(search_results, dict) and 'results' in search_results:
                results = []
                for r in search_results['results']:
                    if r is None:
                        continue
                    text = r.get('memory', '') or ''
                    metadata = r.get('metadata') or {}  # Handle None metadata
                    if text:
                        results.append({"text": text, "metadata": metadata})
            elif isinstance(search_results, list):
                results = [{"text": str(r), "metadata": {}} for r in search_results if r is not None and str(r)]
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
    
    def _build_system_prompt(self, tools=None):
        """Build the system prompt with tool information.
        
        Args:
            tools: Optional list of tools to use (defaults to self.tools)
            
        Returns:
            str: The system prompt or None if use_system_prompt is False
        """
        if not self.use_system_prompt:
            return None
        
        # Check cache first (skip cache if memory is enabled since context is dynamic)
        if not self._memory_instance:
            tools_key = self._get_tools_cache_key(tools)
            cache_key = f"{self.role}:{self.goal}:{tools_key}"
            
            if cache_key in self._system_prompt_cache:
                return self._system_prompt_cache[cache_key]
        else:
            cache_key = None  # Don't cache when memory is enabled
            
        system_prompt = f"""{self.backstory}\n
Your Role: {self.role}\n
Your Goal: {self.goal}"""
        
        # Add rules context if rules manager is enabled (lazy initialization)
        if self._rules_manager_initialized and self._rules_manager:
            rules_context = self.get_rules_context()
            if rules_context:
                system_prompt += f"\n\n## Rules (Guidelines you must follow)\n{rules_context}"
        
        # Add memory context if memory is enabled
        if self._memory_instance:
            memory_context = self.get_memory_context()
            if memory_context:
                system_prompt += f"\n\n## Memory (Information you remember about the user)\n{memory_context}"
                # Display memory info to user if verbose
                if self.verbose:
                    self._display_memory_info()
        
        # Add skills prompt if skills are configured
        if self._skills or self._skills_dirs:
            skills_prompt = self.get_skills_prompt()
            if skills_prompt:
                system_prompt += f"\n\n## Available Skills\n{skills_prompt}"
                system_prompt += "\n\nWhen a skill is relevant to the task, read its SKILL.md file to get detailed instructions. If the skill has scripts in its scripts/ directory, you can execute them using the execute_code or run_script tool."
        
        # Add tool usage instructions if tools are available
        # Use provided tools or fall back to self.tools
        tools_to_use = tools if tools is not None else self.tools
        if tools_to_use:
            tool_names = []
            for tool in tools_to_use:
                try:
                    if callable(tool) and hasattr(tool, '__name__'):
                        tool_names.append(tool.__name__)
                    elif isinstance(tool, dict) and isinstance(tool.get('function'), dict) and 'name' in tool['function']:
                        tool_names.append(tool['function']['name'])
                    elif isinstance(tool, str):
                        tool_names.append(tool)
                    elif hasattr(tool, "to_openai_tool"):
                        # Handle MCP tools
                        openai_tools = tool.to_openai_tool()
                        if isinstance(openai_tools, list):
                            for t in openai_tools:
                                if isinstance(t, dict) and 'function' in t and 'name' in t['function']:
                                    tool_names.append(t['function']['name'])
                        elif isinstance(openai_tools, dict) and 'function' in openai_tools:
                            tool_names.append(openai_tools['function']['name'])
                except (AttributeError, KeyError, TypeError) as e:
                    logging.warning(f"Could not extract tool name from {tool}: {e}")
                    continue
            
            if tool_names:
                system_prompt += f"\n\nYou have access to the following tools: {', '.join(tool_names)}. Use these tools when appropriate to help complete your tasks. Always use tools when they can help provide accurate information or perform actions."
        
        # Cache the generated system prompt (only if cache_key is set, i.e., memory not enabled)
        # Simple cache size limit to prevent unbounded growth
        if cache_key and len(self._system_prompt_cache) < self._max_cache_size:
            self._system_prompt_cache[cache_key] = system_prompt
        return system_prompt

    def _build_response_format(self, schema_model):
        """Build response_format dict for native structured output.
        
        Args:
            schema_model: Pydantic model or dict schema
            
        Returns:
            Dict suitable for response_format parameter, or None if not applicable
        """
        if not schema_model:
            return None
        
        def _add_additional_properties_false(schema):
            """Recursively add additionalProperties: false and required array to all object schemas."""
            if isinstance(schema, dict):
                if schema.get('type') == 'object':
                    schema['additionalProperties'] = False
                    # Add required array with all property keys (OpenAI strict mode requirement)
                    if 'properties' in schema:
                        schema['required'] = list(schema['properties'].keys())
                # Recurse into properties
                if 'properties' in schema:
                    for prop in schema['properties'].values():
                        _add_additional_properties_false(prop)
                # Recurse into items (for arrays)
                if 'items' in schema:
                    _add_additional_properties_false(schema['items'])
                # Recurse into $defs
                if '$defs' in schema:
                    for def_schema in schema['$defs'].values():
                        _add_additional_properties_false(def_schema)
            return schema
        
        def _wrap_array_in_object(schema):
            """Wrap array schema in object since OpenAI requires root type to be object."""
            if schema.get('type') == 'array':
                return {
                    'type': 'object',
                    'properties': {
                        'items': schema
                    },
                    'required': ['items'],
                    'additionalProperties': False
                }
            return schema
        
        # Handle Pydantic model
        if hasattr(schema_model, 'model_json_schema'):
            schema = schema_model.model_json_schema()
            schema = _add_additional_properties_false(schema)
            schema = _wrap_array_in_object(schema)
            name = getattr(schema_model, '__name__', 'response')
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": name,
                    "schema": schema,
                    "strict": True
                }
            }
        
        # Handle dict schema (inline JSON schema from YAML)
        if isinstance(schema_model, dict):
            schema = schema_model.copy()
            schema = _add_additional_properties_false(schema)
            schema = _wrap_array_in_object(schema)
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": schema,
                    "strict": True
                }
            }
        
        return None

    def _supports_native_structured_output(self):
        """Check if current model supports native structured output via response_format.
        
        Auto-detects based on model capabilities using LiteLLM.
        
        Returns:
            bool: True if model supports response_format with json_schema
        """
        try:
            from ..llm.model_capabilities import supports_structured_outputs
            return supports_structured_outputs(self.llm)
        except Exception:
            return False

    def _build_messages(self, prompt, temperature=1.0, output_json=None, output_pydantic=None, tools=None, use_native_format=False):
        """Build messages list for chat completion.
        
        Args:
            prompt: The user prompt (str or list)
            temperature: Temperature for the chat
            output_json: Optional Pydantic model for JSON output
            output_pydantic: Optional Pydantic model for JSON output (alias)
            tools: Optional list of tools to use (defaults to self.tools)
            use_native_format: If True, skip text injection (native response_format will be used)
            
        Returns:
            Tuple of (messages list, original prompt)
        """
        messages = []
        original_prompt = None
        
        # Use openai_client's build_messages method if available
        if self._openai_client is not None:
            messages, original_prompt = self._openai_client.build_messages(
                prompt=prompt,
                system_prompt=self._build_system_prompt(
                    tools=tools,
                ),
                chat_history=self.chat_history,
                output_json=None if use_native_format else output_json,
                output_pydantic=None if use_native_format else output_pydantic
            )
        else:
            # Build messages manually
            system_prompt = self._build_system_prompt(
                tools=tools,
            )
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Add chat history
            if self.chat_history:
                messages.extend(self.chat_history)
            
            # Add user prompt
            if isinstance(prompt, list):
                messages.extend(prompt)
                original_prompt = prompt
            else:
                messages.append({"role": "user", "content": str(prompt)})
                original_prompt = str(prompt)
            
            # Add JSON format instruction if needed (only when not using native format)
            if not use_native_format and (output_json or output_pydantic):
                schema_model = output_pydantic or output_json
                # Handle Pydantic model
                if hasattr(schema_model, 'model_json_schema'):
                    import json
                    json_instruction = f"\nPlease respond with valid JSON matching this schema: {json.dumps(schema_model.model_json_schema())}"
                    messages[-1]["content"] += json_instruction
                # Handle inline dict schema (Option A from YAML)
                elif isinstance(schema_model, dict):
                    import json
                    json_instruction = f"\nPlease respond with valid JSON matching this schema: {json.dumps(schema_model)}"
                    messages[-1]["content"] += json_instruction
        
        return messages, original_prompt

    def _format_tools_for_completion(self, tools=None):
        """Format tools for OpenAI completion API.
        
        Supports:
        - Pre-formatted OpenAI tools (dicts with type='function')
        - Lists of pre-formatted tools
        - Callable functions
        - String function names
        - Objects with to_openai_tool() method
        
        Args:
            tools: List of tools in various formats or None to use self.tools
            
        Returns:
            List of formatted tools or empty list
        """
        if tools is None:
            tools = self.tools
        
        if not tools:
            return []
        
        # Check cache first
        tools_key = self._get_tools_cache_key(tools)
        if tools_key in self._formatted_tools_cache:
            return self._formatted_tools_cache[tools_key]
            
        formatted_tools = []
        for tool in tools:
            # Handle pre-formatted OpenAI tools
            if isinstance(tool, dict) and tool.get('type') == 'function':
                # Validate nested dictionary structure before accessing
                if 'function' in tool and isinstance(tool['function'], dict) and 'name' in tool['function']:
                    formatted_tools.append(tool)
                else:
                    logging.warning(f"Skipping malformed OpenAI tool: missing function or name")
            # Handle lists of tools
            elif isinstance(tool, list):
                for subtool in tool:
                    if isinstance(subtool, dict) and subtool.get('type') == 'function':
                        # Validate nested dictionary structure before accessing
                        if 'function' in subtool and isinstance(subtool['function'], dict) and 'name' in subtool['function']:
                            formatted_tools.append(subtool)
                        else:
                            logging.warning(f"Skipping malformed OpenAI tool in list: missing function or name")
            # Handle string tool names
            elif isinstance(tool, str):
                tool_def = self._generate_tool_definition(tool)
                if tool_def:
                    formatted_tools.append(tool_def)
                else:
                    logging.warning(f"Could not generate definition for tool: {tool}")
            # Handle objects with to_openai_tool method (MCP tools)
            elif hasattr(tool, "to_openai_tool"):
                openai_tools = tool.to_openai_tool()
                # MCP tools can return either a single tool or a list of tools
                if isinstance(openai_tools, list):
                    formatted_tools.extend(openai_tools)
                elif openai_tools is not None:
                    formatted_tools.append(openai_tools)
            # Handle callable functions
            elif callable(tool):
                tool_def = self._generate_tool_definition(tool.__name__)
                if tool_def:
                    formatted_tools.append(tool_def)
            else:
                logging.warning(f"Tool {tool} not recognized")
        
        # Validate JSON serialization before returning
        if formatted_tools:
            try:
                json.dumps(formatted_tools)  # Validate serialization
            except (TypeError, ValueError) as e:
                logging.error(f"Tools are not JSON serializable: {e}")
                return []
        
        # Cache the formatted tools
        # Simple cache size limit to prevent unbounded growth
        if len(self._formatted_tools_cache) < self._max_cache_size:
            self._formatted_tools_cache[tools_key] = formatted_tools
        return formatted_tools

    def generate_task(self) -> 'Task':
        """Generate a Task object from the agent's instructions"""
        from ..task.task import Task
        
        description = self.instructions if self.instructions else f"Execute task as {self.role} with goal: {self.goal}"
        expected_output = "Complete the assigned task successfully"
        
        return Task(
            name=self.name,
            description=description,
            expected_output=expected_output,
            agent=self,
            tools=self.tools
        )

    def _resolve_tool_names(self, tool_names):
        """Resolve tool names to actual tool instances from registry.
        
        Args:
            tool_names: List of tool name strings
            
        Returns:
            List of resolved tool instances
        """
        resolved = []
        try:
            from ..tools.registry import get_registry
            registry = get_registry()
            
            for name in tool_names:
                tool = registry.get(name)
                if tool is not None:
                    resolved.append(tool)
                else:
                    logging.warning(f"Tool '{name}' not found in registry")
        except ImportError:
            logging.warning("Tool registry not available, cannot resolve tool names")
        
        return resolved

    def _cast_arguments(self, func, arguments):
        """Cast arguments to their expected types based on function signature."""
        if not callable(func) or not arguments:
            return arguments
        
        try:
            sig = inspect.signature(func)
            casted_args = {}
            
            for param_name, arg_value in arguments.items():
                if param_name in sig.parameters:
                    param = sig.parameters[param_name]
                    if param.annotation != inspect.Parameter.empty:
                        # Handle common type conversions
                        if param.annotation == int and isinstance(arg_value, (str, float)):
                            try:
                                casted_args[param_name] = int(float(arg_value))
                            except (ValueError, TypeError):
                                casted_args[param_name] = arg_value
                        elif param.annotation == float and isinstance(arg_value, (str, int)):
                            try:
                                casted_args[param_name] = float(arg_value)
                            except (ValueError, TypeError):
                                casted_args[param_name] = arg_value
                        elif param.annotation == bool and isinstance(arg_value, str):
                            casted_args[param_name] = arg_value.lower() in ('true', '1', 'yes', 'on')
                        else:
                            casted_args[param_name] = arg_value
                    else:
                        casted_args[param_name] = arg_value
                else:
                    casted_args[param_name] = arg_value
            
            return casted_args
        except Exception as e:
            logging.debug(f"Type casting failed for {getattr(func, '__name__', 'unknown function')}: {e}")
            return arguments

    def execute_tool(self, function_name, arguments):
        """
        Execute a tool dynamically based on the function name and arguments.
        Injects agent state for tools with Injected[T] parameters.
        """
        logging.debug(f"{self.name} executing tool {function_name} with arguments: {arguments}")
        
        # NOTE: tool_call callback is triggered by display_tool_call in openai_client.py
        # Do NOT call it here to avoid duplicate output
        
        # Set up injection context for tools with Injected parameters
        from ..tools.injected import AgentState
        state = AgentState(
            agent_id=self.name,
            run_id=getattr(self, '_current_run_id', 'unknown'),
            session_id=getattr(self, '_session_id', None) or 'default',
            last_user_message=self.chat_history[-1].get('content') if self.chat_history else None,
            metadata={'agent_name': self.name}
        )
        
        # Execute within injection context
        return self._execute_tool_with_context(function_name, arguments, state)
    
    def _execute_tool_with_context(self, function_name, arguments, state):
        """Execute tool within injection context, with optional output truncation."""
        from ..tools.injected import with_injection_context
        from ..trace.context_events import get_context_emitter
        import time as _time
        
        # Emit tool call start event (zero overhead when not set)
        _trace_emitter = get_context_emitter()
        _trace_emitter.tool_call_start(self.name, function_name, arguments)
        _tool_start_time = _time.time()
        
        try:
            # Trigger BEFORE_TOOL hook
            from ..hooks import HookEvent, BeforeToolInput
            before_tool_input = BeforeToolInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.BEFORE_TOOL,
                timestamp=str(_time.time()),
                agent_name=self.name,
                tool_name=function_name,
                tool_input=arguments
            )
            tool_hook_results = self._hook_runner.execute_sync(HookEvent.BEFORE_TOOL, before_tool_input, target=function_name)
            if self._hook_runner.is_blocked(tool_hook_results):
                logging.warning(f"Tool {function_name} execution blocked by BEFORE_TOOL hook")
                return f"Execution of {function_name} was blocked by security policy."
            
            # Update arguments if modified by hooks
            for res in tool_hook_results:
                if res.output and res.output.modified_data:
                    arguments.update(res.output.modified_data)

            with with_injection_context(state):
                result = self._execute_tool_impl(function_name, arguments)
            
            # Apply tool output truncation to prevent context overflow
            # Uses context manager budget if enabled, otherwise applies default limit
            if result:
                try:
                    result_str = str(result)
                    
                    if self.context_manager:
                        # Use context-aware truncation with configured budget
                        truncated = self._truncate_tool_output(function_name, result_str)
                    else:
                        # Apply default limit even without context management
                        # This prevents runaway tool outputs from causing overflow
                        if len(result_str) > DEFAULT_TOOL_OUTPUT_LIMIT:
                            # Use smart truncation format that judge recognizes as OK
                            tail_size = min(DEFAULT_TOOL_OUTPUT_LIMIT // 5, 2000)
                            head = result_str[:DEFAULT_TOOL_OUTPUT_LIMIT - tail_size]
                            tail = result_str[-tail_size:] if tail_size > 0 else ""
                            truncated = f"{head}\n...[{len(result_str):,} chars, showing first/last portions]...\n{tail}"
                        else:
                            truncated = result_str
                    
                    if len(truncated) < len(result_str):
                        logging.debug(f"Truncated {function_name} output from {len(result_str)} to {len(truncated)} chars")
                        # For dicts, truncate large string fields (e.g., raw_content from search)
                        if isinstance(result, dict):
                            max_field_chars = DEFAULT_TOOL_OUTPUT_LIMIT if not self.context_manager else None
                            result = self._truncate_dict_fields(result, function_name, max_field_chars)
                        else:
                            result = truncated
                except Exception as e:
                    logging.debug(f"Tool truncation skipped: {e}")
            
            # Emit tool call end event (truncation handled by context_events.py)
            _duration_ms = (_time.time() - _tool_start_time) * 1000
            _trace_emitter.tool_call_end(self.name, function_name, str(result) if result else None, _duration_ms)
            
            # Trigger AFTER_TOOL hook
            from ..hooks import HookEvent, AfterToolInput
            after_tool_input = AfterToolInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.AFTER_TOOL,
                timestamp=str(_time.time()),
                agent_name=self.name,
                tool_name=function_name,
                tool_input=arguments,
                tool_output=result,
                execution_time_ms=(_time.time() - _tool_start_time) * 1000
            )
            self._hook_runner.execute_sync(HookEvent.AFTER_TOOL, after_tool_input, target=function_name)
            
            return result
        except Exception as e:
            # Emit tool call end with error
            _duration_ms = (_time.time() - _tool_start_time) * 1000
            _trace_emitter.tool_call_end(self.name, function_name, None, _duration_ms, str(e))
            
            # Trigger OnError hook if needed (optional future step)
            raise
            
    def _trigger_after_agent_hook(self, prompt, response, start_time, tools_used=None):
        """Trigger AFTER_AGENT hook and return response."""
        from ..hooks import HookEvent, AfterAgentInput
        after_agent_input = AfterAgentInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.AFTER_AGENT,
            timestamp=str(time.time()),
            agent_name=self.name,
            prompt=prompt if isinstance(prompt, str) else str(prompt),
            response=response or "",
            tools_used=tools_used or [],
            total_tokens=0,
            execution_time_ms=(time.time() - start_time) * 1000
        )
        self._hook_runner.execute_sync(HookEvent.AFTER_AGENT, after_agent_input)
        return response

    
    def _calculate_llm_cost(self, prompt_tokens: int, completion_tokens: int, response: any = None) -> float:
        """Calculate estimated cost for LLM call.
        
        Uses litellm for accurate pricing (1000+ models) when available,
        falls back to built-in pricing table otherwise.
        
        Args:
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion
            response: Optional LLM response object for more accurate cost calculation
            
        Returns:
            Estimated cost in USD
        """
        from praisonaiagents.utils.cost_utils import calculate_llm_cost
        return calculate_llm_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=self.llm,
            response=response,
        )
    
    def _truncate_dict_fields(self, data: dict, tool_name: str, max_field_chars: int = None) -> dict:
        """Truncate large string fields in a dict to prevent context overflow."""
        if max_field_chars is None:
            # Use tool budget from context manager (default 5000 tokens * 4 chars/token = 20000 chars)
            max_tokens = self.context_manager.get_tool_budget(tool_name) if self.context_manager else 5000
            max_field_chars = max_tokens * 4
        
        result = {}
        for key, value in data.items():
            if isinstance(value, str) and len(value) > max_field_chars:
                # Smart truncate large string fields preserving head and tail
                head_limit = int(max_field_chars * 0.8)
                tail_limit = int(max_field_chars * 0.15)
                head = value[:head_limit]
                tail = value[-tail_limit:] if tail_limit > 0 else ""
                result[key] = f"{head}\n...[{len(value):,} chars, showing first/last portions]...\n{tail}"
                logging.debug(f"Smart truncated field '{key}' from {len(value)} to ~{max_field_chars} chars")
            elif isinstance(value, dict):
                result[key] = self._truncate_dict_fields(value, tool_name, max_field_chars)
            elif isinstance(value, list):
                result[key] = [
                    self._truncate_dict_fields(item, tool_name, max_field_chars) if isinstance(item, dict)
                    else (self._smart_truncate_str(item, max_field_chars) if isinstance(item, str) and len(item) > max_field_chars else item)
                    for item in value
                ]
            else:
                result[key] = value
        return result
    
    def _smart_truncate_str(self, text: str, max_chars: int) -> str:
        """Smart truncate a string preserving head and tail."""
        if len(text) <= max_chars:
            return text
        head_limit = int(max_chars * 0.8)
        tail_limit = int(max_chars * 0.15)
        head = text[:head_limit]
        tail = text[-tail_limit:] if tail_limit > 0 else ""
        return f"{head}\n...[{len(text):,} chars, showing first/last portions]...\n{tail}"
    
    def _execute_tool_impl(self, function_name, arguments):
        """Internal tool execution implementation."""

        # Check if approval is required for this tool
        from ..approval import is_approval_required, console_approval_callback, get_risk_level, mark_approved, get_approval_callback, is_env_auto_approve, is_yaml_approved
        if is_approval_required(function_name):
            # Skip approval if auto-approve env var is set or tool is YAML-approved
            if is_env_auto_approve() or is_yaml_approved(function_name):
                logging.debug(f"Tool {function_name} auto-approved (env={is_env_auto_approve()}, yaml={is_yaml_approved(function_name)})")
                mark_approved(function_name)
            else:
                risk_level = get_risk_level(function_name)
                logging.debug(f"Tool {function_name} requires approval (risk level: {risk_level})")
                
                # Use global approval callback or default console callback
                callback = get_approval_callback() or console_approval_callback
                
                try:
                    decision = callback(function_name, arguments, risk_level)
                    if not decision.approved:
                        error_msg = f"Tool execution denied: {decision.reason}"
                        logging.warning(error_msg)
                        return {"error": error_msg, "approval_denied": True}
                    
                    # Mark as approved in context to prevent double approval in decorator
                    mark_approved(function_name)
                    
                    # Use modified arguments if provided
                    if decision.modified_args:
                        arguments = decision.modified_args
                        logging.info(f"Using modified arguments: {arguments}")
                        
                except Exception as e:
                    error_msg = f"Error during approval process: {str(e)}"
                    logging.error(error_msg)
                    return {"error": error_msg, "approval_error": True}

        # Special handling for MCP tools
        # Check if tools is an MCP instance with the requested function name
        MCP = None
        try:
            from ..mcp.mcp import MCP
        except ImportError:
            pass  # MCP not available
        
        # Helper function to execute MCP tool
        def _execute_mcp_tool(mcp_instance, func_name, args):
            """Execute a tool from an MCP instance."""
            # Handle SSE MCP client
            if hasattr(mcp_instance, 'is_sse') and mcp_instance.is_sse:
                if hasattr(mcp_instance, 'sse_client'):
                    for tool in mcp_instance.sse_client.tools:
                        if tool.name == func_name:
                            logging.debug(f"Found matching SSE MCP tool: {func_name}")
                            return True, tool(**args)
            # Handle HTTP Stream MCP client
            if hasattr(mcp_instance, 'is_http_stream') and mcp_instance.is_http_stream:
                if hasattr(mcp_instance, 'http_stream_client'):
                    for tool in mcp_instance.http_stream_client.tools:
                        if tool.name == func_name:
                            logging.debug(f"Found matching HTTP Stream MCP tool: {func_name}")
                            return True, tool(**args)
            # Handle WebSocket MCP client
            if hasattr(mcp_instance, 'is_websocket') and mcp_instance.is_websocket:
                if hasattr(mcp_instance, 'websocket_client'):
                    for tool in mcp_instance.websocket_client.tools:
                        if tool.name == func_name:
                            logging.debug(f"Found matching WebSocket MCP tool: {func_name}")
                            return True, tool(**args)
            # Handle stdio MCP client
            if hasattr(mcp_instance, 'runner'):
                for mcp_tool in mcp_instance.runner.tools:
                    if hasattr(mcp_tool, 'name') and mcp_tool.name == func_name:
                        logging.debug(f"Found matching MCP tool: {func_name}")
                        return True, mcp_instance.runner.call_tool(func_name, args)
            return False, None
        
        # Check if tools is a single MCP instance
        if MCP is not None and isinstance(self.tools, MCP):
            logging.debug(f"Looking for MCP tool {function_name}")
            found, result = _execute_mcp_tool(self.tools, function_name, arguments)
            if found:
                return result
        
        # Check if tools is a list that may contain MCP instances
        if isinstance(self.tools, (list, tuple)):
            for tool in self.tools:
                if MCP is not None and isinstance(tool, MCP):
                    logging.debug(f"Looking for MCP tool {function_name} in MCP instance")
                    found, result = _execute_mcp_tool(tool, function_name, arguments)
                    if found:
                        return result

        # Try to find the function in the agent's tools list first
        func = None
        for tool in self.tools if isinstance(self.tools, (list, tuple)) else []:
            # Check for BaseTool instances (plugin system)
            from ..tools.base import BaseTool
            if isinstance(tool, BaseTool) and tool.name == function_name:
                func = tool
                break
            # Check for FunctionTool (decorated functions)
            if hasattr(tool, 'name') and getattr(tool, 'name', None) == function_name:
                func = tool
                break
            if (callable(tool) and getattr(tool, '__name__', '') == function_name) or \
               (inspect.isclass(tool) and tool.__name__ == function_name):
                func = tool
                break
        
        if func is None:
            # Check the global tool registry for plugins
            try:
                from ..tools.registry import get_registry
                registry = get_registry()
                func = registry.get(function_name)
            except ImportError:
                pass
        
        if func is None:
            # If not found in tools or registry, try globals and main
            func = globals().get(function_name)
            if not func:
                import __main__
                func = getattr(__main__, function_name, None)

        if func:
            try:
                # BaseTool instances (plugin system) - call run() method
                from ..tools.base import BaseTool
                if isinstance(func, BaseTool):
                    casted_arguments = self._cast_arguments(func.run, arguments)
                    return func.run(**casted_arguments)
                
                # Langchain: If it's a class with run but not _run, instantiate and call run
                if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
                    instance = func()
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance.run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance.run, run_params)
                    return instance.run(**casted_params)

                # CrewAI: If it's a class with an _run method, instantiate and call _run
                elif inspect.isclass(func) and hasattr(func, '_run'):
                    instance = func()
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance._run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance._run, run_params)
                    return instance._run(**casted_params)

                # Otherwise treat as regular function
                elif callable(func):
                    casted_arguments = self._cast_arguments(func, arguments)
                    return func(**casted_arguments)
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Error executing tool {function_name}: {error_msg}")
                return {"error": error_msg}
        
        error_msg = f"Tool '{function_name}' is not callable"
        logging.error(error_msg)
        return {"error": error_msg}

    def clear_history(self):
        self.chat_history = []

    # -------------------------------------------------------------------------
    #                       History Management Methods
    # -------------------------------------------------------------------------
    
    def prune_history(self, keep_last: int = 5) -> int:
        """
        Prune chat history to keep only the last N messages.
        
        Useful for cleaning up large history after image analysis sessions
        to prevent context window saturation.
        
        Args:
            keep_last: Number of recent messages to keep
            
        Returns:
            Number of messages deleted
        """
        with self._history_lock:
            if len(self.chat_history) <= keep_last:
                return 0
            
            deleted_count = len(self.chat_history) - keep_last
            self.chat_history = self.chat_history[-keep_last:]
            return deleted_count
    
    def delete_history(self, index: int) -> bool:
        """
        Delete a specific message from chat history by index.
        
        Supports negative indexing (-1 for last message, etc.).
        
        Args:
            index: Message index (0-based, supports negative indexing)
            
        Returns:
            True if deleted, False if index out of range
        """
        with self._history_lock:
            try:
                del self.chat_history[index]
                return True
            except IndexError:
                return False
    
    def delete_history_matching(self, pattern: str) -> int:
        """
        Delete all messages matching a pattern.
        
        Useful for removing all image-related messages after processing.
        
        Args:
            pattern: Substring to match in message content
            
        Returns:
            Number of messages deleted
        """
        with self._history_lock:
            original_len = len(self.chat_history)
            self.chat_history = [
                msg for msg in self.chat_history
                if pattern.lower() not in msg.get("content", "").lower()
            ]
            return original_len - len(self.chat_history)
    
    def get_history_size(self) -> int:
        """Get the current number of messages in chat history."""
        return len(self.chat_history)
    
    @contextlib.contextmanager
    def ephemeral(self):
        """
        Context manager for ephemeral conversations.
        
        Messages within this block are NOT permanently stored in chat_history.
        History is restored to pre-block state after exiting.
        
        Example:
            with agent.ephemeral():
                response = agent.chat("[IMAGE] Analyze this")
                # After block, history is restored - image NOT persisted
        """
        # Save current history state
        with self._history_lock:
            saved_history = self.chat_history.copy()
        
        try:
            yield
        finally:
            # Restore history to pre-block state
            with self._history_lock:
                self.chat_history = saved_history
    
    def _build_multimodal_prompt(
        self, 
        prompt: str, 
        attachments: Optional[List[str]] = None
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Build a multimodal prompt from text and attachments.
        
        This is a DRY helper used by chat/achat/run/arun/start/astart.
        Attachments are ephemeral - only text is stored in history.
        
        Args:
            prompt: Text query (ALWAYS stored in chat_history)
            attachments: Image/file paths for THIS turn only (NEVER stored)
            
        Returns:
            Either a string (no attachments) or multimodal message list
        """
        if not attachments:
            return prompt
        
        # Build multimodal content list
        content = [{"type": "text", "text": prompt}]
        
        for attachment in attachments:
            # Handle image files
            if isinstance(attachment, str):
                import os
                import base64
                
                if os.path.isfile(attachment):
                    # File path - read and encode
                    ext = os.path.splitext(attachment)[1].lower()
                    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                        try:
                            with open(attachment, 'rb') as f:
                                data = base64.b64encode(f.read()).decode('utf-8')
                            media_type = {
                                '.jpg': 'image/jpeg',
                                '.jpeg': 'image/jpeg',
                                '.png': 'image/png',
                                '.gif': 'image/gif',
                                '.webp': 'image/webp',
                            }.get(ext, 'image/jpeg')
                            content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{data}"}
                            })
                            logging.debug(f"Successfully encoded image attachment: {attachment} ({len(data)} bytes base64)")
                        except Exception as e:
                            logging.warning(f"Failed to load attachment {attachment}: {e}")
                elif attachment.startswith(('http://', 'https://', 'data:')):
                    # URL or data URI
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": attachment}
                    })
            elif isinstance(attachment, dict):
                # Already structured content
                content.append(attachment)
        
        return content

    def __str__(self):
        return f"Agent(name='{self.name}', role='{self.role}', goal='{self.goal}')"

    def _process_stream_response(self, messages, temperature, start_time, formatted_tools=None, reasoning_steps=False):
        """Internal helper for streaming response processing with real-time events."""
        if self._openai_client is None:
            return None
            
        return self._openai_client.process_stream_response(
            messages=messages,
            model=self.llm,
            temperature=temperature,
            tools=formatted_tools,
            start_time=start_time,
            console=self.console,
            display_fn=_get_display_functions()['display_generating'] if self.verbose else None,
            reasoning_steps=reasoning_steps,
            stream_callback=self.stream_emitter.emit,
            emit_events=True
        )

    def _chat_completion(self, messages, temperature=1.0, tools=None, stream=True, reasoning_steps=False, task_name=None, task_description=None, task_id=None, response_format=None):
        start_time = time.time()
        
        # Trigger BEFORE_LLM hook
        from ..hooks import HookEvent, BeforeLLMInput
        before_llm_input = BeforeLLMInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.BEFORE_LLM,
            timestamp=str(time.time()),
            agent_name=self.name,
            messages=messages,
            model=self.llm if isinstance(self.llm, str) else str(self.llm),
            temperature=temperature
        )
        self._hook_runner.execute_sync(HookEvent.BEFORE_LLM, before_llm_input)
        
        logging.debug(f"{self.name} sending messages to LLM: {messages}")
        
        # Emit LLM request trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.llm_request(
            self.name,
            messages_count=len(messages),
            tokens_used=0,  # Estimated before call
            model=self.llm if isinstance(self.llm, str) else None,
            messages=messages,  # Include full messages for context replay
        )

        # Use the new _format_tools_for_completion helper method
        formatted_tools = self._format_tools_for_completion(tools)

        try:
            # Use the custom LLM instance if available
            if self._using_custom_llm and hasattr(self, 'llm_instance'):
                if stream:
                    # Debug logs for tool info
                    if formatted_tools:
                        logging.debug(f"Passing {len(formatted_tools)} formatted tools to LLM instance: {formatted_tools}")
                    
                    # Use the LLM instance for streaming responses
                    final_response = self.llm_instance.get_response(
                        prompt=messages[1:],  # Skip system message as LLM handles it separately  
                        system_prompt=messages[0]['content'] if messages and messages[0]['role'] == 'system' else None,
                        temperature=temperature,
                        tools=formatted_tools if formatted_tools else None,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        stream=stream,
                        console=self.console,
                        execute_tool_fn=self.execute_tool,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[getattr(t, '__name__', str(t)) for t in self.tools] if self.tools else None,
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id,
                        reasoning_steps=reasoning_steps
                    )
                else:
                    # Non-streaming with custom LLM - don't show streaming-like behavior
                    if False:  # Don't use display_generating when stream=False to avoid streaming-like behavior
                        # This block is disabled to maintain consistency with the OpenAI path fix
                        with _get_live()(
                            _get_display_functions()['display_generating']("", start_time),
                            console=self.console,
                            refresh_per_second=4,
                        ) as live:
                            final_response = self.llm_instance.get_response(
                                prompt=messages[1:],
                                system_prompt=messages[0]['content'] if messages and messages[0]['role'] == 'system' else None,
                                temperature=temperature,
                                tools=formatted_tools if formatted_tools else None,
                                verbose=self.verbose,
                                markdown=self.markdown,
                                stream=stream,
                                console=self.console,
                                execute_tool_fn=self.execute_tool,
                                agent_name=self.name,
                                agent_role=self.role,
                                agent_tools=[getattr(t, '__name__', str(t)) for t in self.tools] if self.tools else None,
                                task_name=task_name,
                                task_description=task_description,
                                task_id=task_id,
                                reasoning_steps=reasoning_steps
                            )
                    else:
                        final_response = self.llm_instance.get_response(
                            prompt=messages[1:],
                            system_prompt=messages[0]['content'] if messages and messages[0]['role'] == 'system' else None,
                            temperature=temperature,
                            tools=formatted_tools if formatted_tools else None,
                            verbose=self.verbose,
                            markdown=self.markdown,
                            stream=stream,
                            console=self.console,
                            execute_tool_fn=self.execute_tool,
                            agent_name=self.name,
                            agent_role=self.role,
                            agent_tools=[getattr(t, '__name__', str(t)) for t in self.tools] if self.tools else None,
                            task_name=task_name,
                            task_description=task_description,
                            task_id=task_id,
                            reasoning_steps=reasoning_steps
                        )
            else:
                # Use the standard OpenAI client approach with tool support
                # Note: openai_client expects tools in various formats and will format them internally
                # But since we already have formatted_tools, we can pass them directly
                if self._openai_client is None:
                    raise ValueError("OpenAI client is not initialized. Please provide OPENAI_API_KEY or use a custom LLM provider.")
                
                # Build kwargs including response_format if provided
                chat_kwargs = {
                    "messages": messages,
                    "model": self.llm,
                    "temperature": temperature,
                    "tools": formatted_tools,  # Already formatted for OpenAI
                    "execute_tool_fn": self.execute_tool,
                    "stream": stream,
                    "console": self.console if (self.verbose or stream) else None,
                    "display_fn": self._display_generating if self.verbose else None,
                    "reasoning_steps": reasoning_steps,
                    "verbose": self.verbose,
                    "max_iterations": 10
                }
                if response_format:
                    chat_kwargs["response_format"] = response_format
                
                final_response = self._openai_client.chat_completion_with_tools(**chat_kwargs)

            # Emit LLM response trace event with token usage
            _duration_ms = (time.time() - start_time) * 1000
            _prompt_tokens = 0
            _completion_tokens = 0
            _cost_usd = 0.0
            
            # Extract token usage from response if available
            if final_response:
                _usage = getattr(final_response, 'usage', None)
                if _usage:
                    _prompt_tokens = getattr(_usage, 'prompt_tokens', 0) or 0
                    _completion_tokens = getattr(_usage, 'completion_tokens', 0) or 0
                    # Calculate cost using litellm (if available) or fallback pricing
                    _cost_usd = self._calculate_llm_cost(_prompt_tokens, _completion_tokens, response=final_response)
            
            _trace_emitter.llm_response(
                self.name,
                duration_ms=_duration_ms,
                response_content=str(final_response) if final_response else None,
                prompt_tokens=_prompt_tokens,
                completion_tokens=_completion_tokens,
                cost_usd=_cost_usd,
            )
            
            # Trigger AFTER_LLM hook
            from ..hooks import HookEvent, AfterLLMInput
            after_llm_input = AfterLLMInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.AFTER_LLM,
                timestamp=str(time.time()),
                agent_name=self.name,
                messages=messages,
                response=str(final_response),
                model=self.llm if isinstance(self.llm, str) else str(self.llm),
                latency_ms=(time.time() - start_time) * 1000
            )
            self._hook_runner.execute_sync(HookEvent.AFTER_LLM, after_llm_input)
            
            return final_response

        except Exception as e:
            error_str = str(e).lower()
            
            # Check if this is a context overflow error
            context_overflow_phrases = [
                "maximum context length",
                "context window is too long", 
                "context length exceeded",
                "context_length_exceeded",
                "token limit",
                "too many tokens"
            ]
            is_overflow = any(phrase in error_str for phrase in context_overflow_phrases)
            
            if is_overflow and self.context_manager:
                # Attempt overflow recovery with emergency truncation
                logging.warning(f"[{self.name}] Context overflow detected, attempting recovery...")
                try:
                    from ..context.budgeter import get_model_limit
                    from ..context.tokens import estimate_messages_tokens
                    
                    model_name = self.llm if isinstance(self.llm, str) else "gpt-4o-mini"
                    model_limit = get_model_limit(model_name)
                    target = int(model_limit * 0.7)  # Target 70% of limit for safety
                    
                    # Apply emergency truncation
                    truncated_messages = self.context_manager.emergency_truncate(messages, target)
                    
                    logging.info(
                        f"[{self.name}] Emergency truncation: {estimate_messages_tokens(messages)} -> "
                        f"{estimate_messages_tokens(truncated_messages)} tokens"
                    )
                    
                    # Retry with truncated messages (recursive call with truncated context)
                    return self._chat_completion(
                        truncated_messages, temperature, tools, stream, 
                        reasoning_steps, task_name, task_description, task_id, response_format
                    )
                except Exception as recovery_error:
                    logging.error(f"[{self.name}] Overflow recovery failed: {recovery_error}")
            
            # Emit LLM response trace event on error
            _duration_ms = (time.time() - start_time) * 1000
            _trace_emitter.llm_response(
                self.name,
                duration_ms=_duration_ms,
                finish_reason="error",
                response_content=str(e),  # Include error for context replay
            )
            _get_display_functions()['display_error'](f"Error in chat completion: {e}")
            return None
    
    def _execute_callback_and_display(self, prompt: str, response: str, generation_time: float, task_name=None, task_description=None, task_id=None):
        """Helper method to execute callbacks and display interaction.
        
        This centralizes the logic for callback execution and display to avoid duplication.
        """
        # Always execute callbacks for status/trace output (regardless of LLM backend)
        _get_display_functions()['execute_sync_callback'](
            'interaction',
            message=prompt,
            response=response,
            markdown=self.markdown,
            generation_time=generation_time,
            agent_name=self.name,
            agent_role=self.role,
            agent_tools=[getattr(t, '__name__', str(t)) for t in self.tools] if self.tools else None,
            task_name=task_name,
            task_description=task_description, 
            task_id=task_id
        )
        # Always display final interaction when verbose is True to ensure consistent formatting
        # This ensures both OpenAI and custom LLM providers (like Gemini) show formatted output
        if self.verbose and not self._final_display_shown:
            _get_display_functions()['display_interaction'](prompt, response, markdown=self.markdown, 
                              generation_time=generation_time, console=self.console,
                              agent_name=self.name,
                              agent_role=self.role,
                              agent_tools=[getattr(t, '__name__', str(t)) for t in self.tools] if self.tools else None,
                              task_name=None,  # Not available in this context
                              task_description=None,  # Not available in this context
                              task_id=None)  # Not available in this context
            self._final_display_shown = True
    
    def _display_generating(self, content: str, start_time: float):
        """Display function for generating animation with agent info."""
        from rich.panel import Panel
        from rich.markdown import Markdown
        elapsed = time.time() - start_time
        
        # Show content if provided (for both streaming and progressive display)
        if content:
            display_content = Markdown(content) if self.markdown else content
            return Panel(
                display_content,
                title=f"[bold]{self.name}[/bold] - Generating... {elapsed:.1f}s",
                border_style="green",
                expand=False
            )
        # else:
        #     # No content yet: show generating message
        #     return Panel(
        #         f"[bold cyan]Generating response...[/bold cyan]",
        #         title=f"[bold]{self.name}[/bold] - {elapsed:.1f}s",
        #         border_style="cyan",
        #         expand=False
        #     )

    def _apply_context_management(
        self,
        messages: list,
        system_prompt: str = "",
        tools: list = None,
    ) -> tuple:
        """
        Apply context management before LLM call.
        
        Handles auto-compaction when context exceeds threshold.
        Zero overhead when context=False.
        
        Args:
            messages: Current chat history
            system_prompt: System prompt content
            tools: Tool schemas
            
        Returns:
            Tuple of (processed_messages, context_result_dict)
            context_result_dict contains optimization metadata if applied
        """
        # Fast path: no context management
        if not self.context_manager:
            return messages, None
        
        try:
            # Process through context manager
            result = self.context_manager.process(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools or [],
                trigger="turn",
            )
            
            optimized = result.get("messages", messages)
            
            # Log if optimization occurred
            if result.get("optimized"):
                logging.debug(
                    f"[{self.name}] Context optimized: "
                    f"{result.get('tokens_before', 0)} -> {result.get('tokens_after', 0)} tokens "
                    f"(saved {result.get('tokens_saved', 0)})"
                )
            
            # HARD LIMIT CHECK: If still over model limit, apply emergency truncation
            try:
                from ..context.budgeter import get_model_limit
                from ..context.tokens import estimate_messages_tokens
                
                model_name = self.llm if isinstance(self.llm, str) else "gpt-4o-mini"
                model_limit = get_model_limit(model_name)
                current_tokens = estimate_messages_tokens(optimized)
                
                # If over 95% of limit, apply emergency truncation
                if current_tokens > model_limit * 0.95:
                    logging.warning(
                        f"[{self.name}] Context at {current_tokens} tokens (limit: {model_limit}), "
                        f"applying emergency truncation"
                    )
                    target = int(model_limit * 0.8)  # Target 80% of limit
                    optimized = self.context_manager.emergency_truncate(optimized, target)
                    result["emergency_truncated"] = True
                    result["tokens_after"] = estimate_messages_tokens(optimized)
            except Exception as e:
                logging.debug(f"Hard limit check skipped: {e}")
            
            return optimized, result
            
        except Exception as e:
            # Context management should never break the chat flow
            logging.warning(f"Context management error (continuing without): {e}")
            return messages, None

    def _truncate_tool_output(self, tool_name: str, output: str) -> str:
        """
        Truncate tool output according to configured budget.
        
        Zero overhead when context=False.
        
        Args:
            tool_name: Name of the tool
            output: Raw tool output
            
        Returns:
            Truncated output if over budget, otherwise original
        """
        if not self.context_manager:
            return output
        
        try:
            return self.context_manager.truncate_tool_output(tool_name, output)
        except Exception as e:
            logging.warning(f"Tool output truncation error: {e}")
            return output

    def _init_db_session(self):
        """Initialize DB session if db adapter is provided (lazy, first chat only)."""
        if self._db is None or self._db_initialized:
            return
        
        # Generate session_id if not provided: default to per-hour ID (YYYYMMDDHH-agentname)
        if self._session_id is None:
            import hashlib
            from datetime import datetime, timezone
            # Per-hour session ID: YYYYMMDDHH (UTC) + agent name hash for uniqueness
            hour_str = datetime.now(timezone.utc).strftime("%Y%m%d%H")
            agent_hash = hashlib.md5(self.name.encode()).hexdigest()[:6]
            self._session_id = f"{hour_str}-{agent_hash}"
        
        # Call db adapter's on_agent_start to get previous messages
        try:
            history = self._db.on_agent_start(
                agent_name=self.name,
                session_id=self._session_id,
                user_id=self.user_id,
                metadata={"role": self.role, "goal": self.goal}
            )
            
            # Restore chat history from previous session
            if history:
                for msg in history:
                    self.chat_history.append({
                        "role": msg.role,
                        "content": msg.content
                    })
                logging.info(f"Resumed session {self._session_id} with {len(history)} messages")
        except Exception as e:
            logging.warning(f"Failed to initialize DB session: {e}")
        
        self._db_initialized = True
        self._current_run_id = None  # Track current run
    
    def _init_session_store(self):
        """
        Initialize session store for JSON-based persistence (lazy, first chat only).
        
        This is used when session_id is provided but no DB adapter.
        Enables automatic session persistence with zero configuration.
        """
        if self._session_store_initialized:
            return
        
        # Only initialize if session_id is provided and no DB adapter
        if self._session_id is None or self._db is not None:
            self._session_store_initialized = True
            return
        
        try:
            from ..session import get_default_session_store
            self._session_store = get_default_session_store()
            
            # Restore chat history from previous session
            history = self._session_store.get_chat_history(self._session_id)
            if history:
                # Only restore if chat_history is empty (avoid duplicates)
                if not self.chat_history:
                    for msg in history:
                        self.chat_history.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                    logging.info(f"Restored session {self._session_id} with {len(history)} messages from JSON store")
            
            # Set agent info
            self._session_store.set_agent_info(
                self._session_id,
                agent_name=self.name,
                user_id=self.user_id,
            )
        except Exception as e:
            logging.warning(f"Failed to initialize session store: {e}")
            self._session_store = None
        
        self._session_store_initialized = True

    def _start_run(self, input_content: str):
        """Start a new run (turn) for persistence tracking."""
        if self._db is None:
            return
        
        import uuid
        self._current_run_id = f"run-{uuid.uuid4().hex[:12]}"
        
        try:
            if hasattr(self._db, 'on_run_start'):
                self._db.on_run_start(
                    session_id=self._session_id,
                    run_id=self._current_run_id,
                    input_content=input_content,
                    metadata={"agent_name": self.name}
                )
        except Exception as e:
            logging.warning(f"Failed to start run: {e}")

    def _end_run(self, output_content: str, status: str = "completed", metrics: dict = None):
        """End the current run (turn)."""
        if self._db is None or self._current_run_id is None:
            return
        
        try:
            if hasattr(self._db, 'on_run_end'):
                self._db.on_run_end(
                    session_id=self._session_id,
                    run_id=self._current_run_id,
                    output_content=output_content,
                    status=status,
                    metrics=metrics or {},
                    metadata={"agent_name": self.name}
                )
        except Exception as e:
            logging.warning(f"Failed to end run: {e}")
        
        self._current_run_id = None

    def _persist_message(self, role: str, content: str):
        """Persist a message to the DB or session store."""
        # Try DB adapter first
        if self._db is not None:
            try:
                if role == "user":
                    self._db.on_user_message(self._session_id, content)
                elif role == "assistant":
                    self._db.on_agent_message(self._session_id, content)
            except Exception as e:
                logging.warning(f"Failed to persist message to DB: {e}")
            return
        
        # Fall back to session store (JSON-based)
        if self._session_store is not None and self._session_id is not None:
            try:
                if role == "user":
                    self._session_store.add_user_message(self._session_id, content)
                elif role == "assistant":
                    self._session_store.add_assistant_message(self._session_id, content)
            except Exception as e:
                logging.warning(f"Failed to persist message to session store: {e}")

    @property
    def session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._session_id

    def chat(self, prompt, temperature=1.0, tools=None, output_json=None, output_pydantic=None, reasoning_steps=False, stream=None, task_name=None, task_description=None, task_id=None, config=None, force_retrieval=False, skip_retrieval=False, attachments=None, tool_choice=None):
        """
        Chat with the agent.
        
        Args:
            prompt: Text query that WILL be stored in chat_history
            attachments: Optional list of image/file paths that are ephemeral
                        (used for THIS turn only, NEVER stored in history).
                        Supports: file paths, URLs, or data URIs.
            tool_choice: Optional tool choice mode ('auto', 'required', 'none').
                        'required' forces the LLM to call a tool before responding.
            ...other args...
        """
        # Emit context trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.agent_start(self.name, {"role": self.role, "goal": self.goal})
        
        try:
            return self._chat_impl(prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice)
        finally:
            _trace_emitter.agent_end(self.name)
    
    def _chat_impl(self, prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice=None):
        """Internal chat implementation (extracted for trace wrapping)."""
        # Apply rate limiter if configured (before any LLM call)
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()
        
        # Process ephemeral attachments (DRY - builds multimodal prompt)
        # IMPORTANT: Original text 'prompt' is stored in history, attachments are NOT
        llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt
        
        # Apply response template if configured (DRY: TemplateConfig.response is canonical,
        # OutputConfig.template is fallback for backward compatibility)
        effective_template = self.response_template or self._output_template
        if effective_template:
            template_instruction = f"\n\nIMPORTANT: Format your response according to this template:\n{effective_template}"
            if isinstance(llm_prompt, str):
                llm_prompt = llm_prompt + template_instruction
            elif isinstance(llm_prompt, list):
                # For multimodal prompts, append to the last text content
                for i in range(len(llm_prompt) - 1, -1, -1):
                    if isinstance(llm_prompt[i], dict) and llm_prompt[i].get('type') == 'text':
                        llm_prompt[i]['text'] = llm_prompt[i]['text'] + template_instruction
                        break
        
        # Initialize DB session on first chat (lazy)
        self._init_db_session()
        
        # Initialize session store for JSON-based persistence (lazy)
        # This enables automatic session persistence when session_id is provided
        self._init_session_store()
        
        # Start a new run for this chat turn
        prompt_str = prompt if isinstance(prompt, str) else str(prompt)
        self._start_run(prompt_str)

        # Trigger BEFORE_AGENT hook
        from ..hooks import HookEvent, BeforeAgentInput
        before_agent_input = BeforeAgentInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.BEFORE_AGENT,
            timestamp=str(time.time()),
            agent_name=self.name,
            prompt=prompt_str,
            conversation_history=self.chat_history,
            tools_available=[t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
        )
        hook_results = self._hook_runner.execute_sync(HookEvent.BEFORE_AGENT, before_agent_input)
        if self._hook_runner.is_blocked(hook_results):
            logging.warning(f"Agent {self.name} execution blocked by BEFORE_AGENT hook")
            return None
        
        # Update prompt if modified by hooks
        for res in hook_results:
            if res.output and res.output.modified_data and "prompt" in res.output.modified_data:
                prompt = res.output.modified_data["prompt"]
                llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt

        # Reset the final display flag for each new conversation
        self._final_display_shown = False
        
        # Log all parameter values when in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            param_info = {
                "prompt": str(prompt)[:100] + "..." if isinstance(prompt, str) and len(str(prompt)) > 100 else str(prompt),
                "temperature": temperature,
                "tools": [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools] if tools else None,
                "output_json": str(output_json.__class__.__name__) if output_json else None,
                "output_pydantic": str(output_pydantic.__class__.__name__) if output_pydantic else None,
                "reasoning_steps": reasoning_steps,
                "agent_name": self.name,
                "agent_role": self.role,
                "agent_goal": self.goal
            }
            logging.debug(f"Agent.chat parameters: {json.dumps(param_info, indent=2, default=str)}")
        
        start_time = time.time()
        reasoning_steps = reasoning_steps or self.reasoning_steps
        # Use agent's stream setting if not explicitly provided
        if stream is None:
            stream = self.stream
        
        # Unified retrieval handling with policy-based decision
        # Uses token-aware context building (DRY - same path as RAG pipeline)
        if self._knowledge_sources or self.knowledge is not None:
            if not self._knowledge_processed:
                self._ensure_knowledge_processed()
            
            # Determine if we should retrieve based on policy
            should_retrieve = False
            if self._retrieval_config is not None:
                should_retrieve = self._retrieval_config.should_retrieve(
                    prompt if isinstance(prompt, str) else str(prompt),
                    force=force_retrieval,
                    skip=skip_retrieval
                )
            elif not skip_retrieval:
                # No config but knowledge exists - retrieve by default unless skipped
                should_retrieve = True if force_retrieval else (self.knowledge is not None)
            
            if should_retrieve and self.knowledge:
                # Use unified retrieval path with token-aware context building
                knowledge_context, _ = self._get_knowledge_context(
                    prompt if isinstance(prompt, str) else str(prompt),
                    use_rag=True  # Use RAG pipeline for token-aware context
                )
                if knowledge_context:
                    # Format with safety boundaries
                    if self._retrieval_config and self._retrieval_config.context_template:
                        formatted_context = self._retrieval_config.context_template.format(
                            context=knowledge_context
                        )
                    else:
                        formatted_context = f"<retrieved_context>\n{knowledge_context}\n</retrieved_context>"
                    
                    # Append formatted knowledge to the prompt
                    prompt = f"{prompt}\n\n{formatted_context}"

        if self._using_custom_llm:
            try:
                # Special handling for MCP tools when using provider/model format
                # Fix: Handle empty tools list properly - use self.tools if tools is None or empty
                if tools is None or (isinstance(tools, list) and len(tools) == 0):
                    tool_param = self.tools
                else:
                    tool_param = tools
                
                # Convert MCP tool objects to OpenAI format if needed
                if tool_param is not None:
                    MCP = None
                    try:
                        from ..mcp.mcp import MCP
                    except ImportError:
                        pass
                    if MCP is not None and isinstance(tool_param, MCP) and hasattr(tool_param, 'to_openai_tool'):
                        # Single MCP instance
                        logging.debug("Converting single MCP tool to OpenAI format")
                        openai_tool = tool_param.to_openai_tool()
                        if openai_tool:
                            # Handle both single tool and list of tools
                            if isinstance(openai_tool, list):
                                tool_param = openai_tool
                            else:
                                tool_param = [openai_tool]
                            logging.debug(f"Converted MCP tool: {tool_param}")
                    elif isinstance(tool_param, (list, tuple)):
                        # List that may contain MCP instances - convert each MCP to OpenAI format
                        converted_tools = []
                        for t in tool_param:
                            if MCP is not None and isinstance(t, MCP) and hasattr(t, 'to_openai_tool'):
                                logging.debug("Converting MCP instance in list to OpenAI format")
                                openai_tools = t.to_openai_tool()
                                if isinstance(openai_tools, list):
                                    converted_tools.extend(openai_tools)
                                elif openai_tools:
                                    converted_tools.append(openai_tools)
                            else:
                                # Keep non-MCP tools as-is
                                converted_tools.append(t)
                        tool_param = converted_tools
                        logging.debug(f"Converted {len(converted_tools)} tools from list")
                
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize prompt content for consistent chat history storage
                normalized_content = prompt
                if isinstance(prompt, list):
                    # Extract text from multimodal prompts
                    normalized_content = next((item["text"] for item in prompt if item.get("type") == "text"), "")
                
                # Prevent duplicate messages
                if not (self.chat_history and 
                        self.chat_history[-1].get("role") == "user" and 
                        self.chat_history[-1].get("content") == normalized_content):
                    # Add user message to chat history BEFORE LLM call so handoffs can access it
                    self.chat_history.append({"role": "user", "content": normalized_content})
                    # Persist user message to DB
                    self._persist_message("user", normalized_content)
                
                try:
                    # Apply context management before LLM call (auto-compaction)
                    # Zero overhead when context=False
                    system_prompt_for_llm = self._build_system_prompt(tools)
                    processed_history, context_result = self._apply_context_management(
                        messages=self.chat_history,
                        system_prompt=system_prompt_for_llm,
                        tools=tool_param,
                    )
                    
                    # Pass everything to LLM class
                    # Use llm_prompt (which includes multimodal content if attachments present)
                    # Build LLM call kwargs
                    llm_kwargs = dict(
                        prompt=llm_prompt,
                        system_prompt=system_prompt_for_llm,
                        chat_history=processed_history,
                        temperature=temperature,
                        tools=tool_param,
                        output_json=output_json,
                        output_pydantic=output_pydantic,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        reflection=self.self_reflect,
                        max_reflect=self.max_reflect,
                        min_reflect=self.min_reflect,
                        console=self.console,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools if tools is not None else self.tools)],
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id,
                        execute_tool_fn=self.execute_tool,
                        reasoning_steps=reasoning_steps,
                        stream=stream
                    )
                    
                    # Pass tool_choice if specified (auto, required, none)
                    # Also check for YAML-configured tool_choice on the agent
                    effective_tool_choice = tool_choice or getattr(self, '_yaml_tool_choice', None)
                    if effective_tool_choice:
                        llm_kwargs['tool_choice'] = effective_tool_choice
                    
                    response_text = self.llm_instance.get_response(**llm_kwargs)

                    self.chat_history.append({"role": "assistant", "content": response_text})
                    # Persist assistant message to DB
                    self._persist_message("assistant", response_text)

                    # Log completion time if in debug mode
                    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.chat completed in {total_time:.2f} seconds")

                    # Apply guardrail validation for custom LLM response
                    try:
                        validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools, task_name, task_description, task_id)
                        # Execute callback and display after validation
                        self._execute_callback_and_display(prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                        return self._trigger_after_agent_hook(prompt, validated_response, start_time)
                    except Exception as e:
                        logging.error(f"Agent {self.name}: Guardrail validation failed for custom LLM: {e}")
                        # Rollback chat history on guardrail failure
                        self.chat_history = self.chat_history[:chat_history_length]
                        return None
                except Exception as e:
                    # Rollback chat history if LLM call fails
                    self.chat_history = self.chat_history[:chat_history_length]
                    _get_display_functions()['display_error'](f"Error in LLM chat: {e}")
                    return None
            except Exception as e:
                _get_display_functions()['display_error'](f"Error in LLM chat: {e}")
                return None
        else:
            # Determine if we should use native structured output
            schema_model = output_pydantic or output_json
            use_native_format = False
            response_format = None
            
            if schema_model and self._supports_native_structured_output():
                # Model supports native structured output - build response_format
                response_format = self._build_response_format(schema_model)
                if response_format:
                    use_native_format = True
                    logging.debug(f"Agent {self.name} using native structured output with response_format")
            
            # Use the new _build_messages helper method
            # Pass llm_prompt (which includes multimodal content if attachments present)
            messages, original_prompt = self._build_messages(
                llm_prompt, temperature, output_json, output_pydantic,
                use_native_format=use_native_format
            )
            
            # Store chat history length for potential rollback
            chat_history_length = len(self.chat_history)
            
            # Normalize original_prompt for consistent chat history storage
            normalized_content = original_prompt
            if isinstance(original_prompt, list):
                # Extract text from multimodal prompts
                normalized_content = next((item["text"] for item in original_prompt if item.get("type") == "text"), "")
            
            # Prevent duplicate messages
            if not (self.chat_history and 
                    self.chat_history[-1].get("role") == "user" and 
                    self.chat_history[-1].get("content") == normalized_content):
                # Add user message to chat history BEFORE LLM call so handoffs can access it
                self.chat_history.append({"role": "user", "content": normalized_content})
                # Persist user message to DB (OpenAI path)
                self._persist_message("user", normalized_content)

            reflection_count = 0
            start_time = time.time()
            
            # Apply context management before LLM call (auto-compaction)
            # Zero overhead when context=False
            system_prompt_content = messages[0].get("content", "") if messages and messages[0].get("role") == "system" else ""
            processed_messages, context_result = self._apply_context_management(
                messages=messages,
                system_prompt=system_prompt_content,
                tools=tools,
            )
            # Use processed messages for the LLM call
            messages = processed_messages
            
            # Wrap entire while loop in try-except for rollback on any failure
            try:
                while True:
                    try:
                        if self.verbose:
                            # Handle both string and list prompts for instruction display
                            display_text = prompt
                            if isinstance(prompt, list):
                                # Extract text content from multimodal prompt
                                display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                            
                            if display_text and str(display_text).strip():
                                # Pass agent information to display_instruction
                                agent_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
                                _get_display_functions()['display_instruction'](
                                    f"Agent {self.name} is processing prompt: {display_text}", 
                                    console=self.console,
                                    agent_name=self.name,
                                    agent_role=self.role,
                                    agent_tools=agent_tools
                                )

                        response = self._chat_completion(messages, temperature=temperature, tools=tools if tools else None, reasoning_steps=reasoning_steps, stream=stream, task_name=task_name, task_description=task_description, task_id=task_id, response_format=response_format)
                        if not response:
                            # Rollback chat history on response failure
                            self.chat_history = self.chat_history[:chat_history_length]
                            return None

                        # Handle None content (can happen with tool calls or empty responses)
                        content = response.choices[0].message.content
                        response_text = content.strip() if content else ""

                        # Handle output_json or output_pydantic if specified
                        if output_json or output_pydantic:
                            # Add to chat history and return raw response
                            # User message already added before LLM call via _build_messages
                            self.chat_history.append({"role": "assistant", "content": response_text})
                            # Persist assistant message to DB
                            self._persist_message("assistant", response_text)
                            # Apply guardrail validation even for JSON output
                            try:
                                validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                # Execute callback after validation
                                self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                return validated_response
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed for JSON output: {e}")
                                # Rollback chat history on guardrail failure
                                self.chat_history = self.chat_history[:chat_history_length]
                                return None

                        if not self.self_reflect:
                            # User message already added before LLM call via _build_messages
                            self.chat_history.append({"role": "assistant", "content": response_text})
                            # Persist assistant message to DB (non-reflect path)
                            self._persist_message("assistant", response_text)
                            if self.verbose:
                                logging.debug(f"Agent {self.name} final response: {response_text}")
                            # Return only reasoning content if reasoning_steps is True
                            if reasoning_steps and hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
                                # Apply guardrail to reasoning content
                                try:
                                    validated_reasoning = self._apply_guardrail_with_retry(response.choices[0].message.reasoning_content, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_reasoning, time.time() - start_time, task_name, task_description, task_id)
                                    return self._trigger_after_agent_hook(original_prompt, validated_reasoning, start_time)
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed for reasoning content: {e}")
                                    # Rollback chat history on guardrail failure
                                    self.chat_history = self.chat_history[:chat_history_length]
                                    return None
                            # Apply guardrail to regular response
                            try:
                                validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                # Execute callback after validation
                                self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                return validated_response
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed: {e}")
                                # Rollback chat history on guardrail failure
                                self.chat_history = self.chat_history[:chat_history_length]
                                return None

                        reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
{self.reflect_prompt if self.reflect_prompt else "Identify any flaws, improvements, or actions."}
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
                        """
                        logging.debug(f"{self.name} reflection attempt {reflection_count+1}, sending prompt: {reflection_prompt}")
                        messages.append({"role": "user", "content": reflection_prompt})

                        try:
                            # Check if we're using a custom LLM (like Gemini)
                            if self._using_custom_llm or self._openai_client is None:
                                # For custom LLMs, we need to handle reflection differently
                                # Use non-streaming to get complete JSON response
                                reflection_response = self._chat_completion(messages, temperature=temperature, tools=None, stream=False, reasoning_steps=False, task_name=task_name, task_description=task_description, task_id=task_id)
                                
                                if not reflection_response or not reflection_response.choices:
                                    raise Exception("No response from reflection request")
                                
                                reflection_content = reflection_response.choices[0].message.content
                                reflection_text = reflection_content.strip() if reflection_content else ""
                                
                                # Clean the JSON output
                                cleaned_json = self.clean_json_output(reflection_text)
                                
                                # Parse the JSON manually
                                reflection_data = json.loads(cleaned_json)
                                
                                # Create a reflection output object manually
                                class CustomReflectionOutput:
                                    def __init__(self, data):
                                        self.reflection = data.get('reflection', '')
                                        self.satisfactory = data.get('satisfactory', 'no').lower()
                                
                                reflection_output = _get_display_functions()['ReflectionOutput'](reflection_data)
                            else:
                                # Use OpenAI's structured output for OpenAI models
                                reflection_response = self._openai_client.sync_client.beta.chat.completions.parse(
                                    model=self.reflect_llm if self.reflect_llm else self.llm,
                                    messages=messages,
                                    temperature=temperature,
                                    response_format=_get_display_functions()['ReflectionOutput']
                                )

                                reflection_output = reflection_response.choices[0].message.parsed

                            if self.verbose:
                                _get_display_functions()['display_self_reflection'](f"Agent {self.name} self reflection (using {self.reflect_llm if self.reflect_llm else self.llm}): reflection='{reflection_output.reflection}' satisfactory='{reflection_output.satisfactory}'", console=self.console)

                            messages.append({"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"})

                            # Only consider satisfactory after minimum reflections
                            if reflection_output.satisfactory == "yes" and reflection_count >= self.min_reflect - 1:
                                if self.verbose:
                                    _get_display_functions()['display_self_reflection']("Agent marked the response as satisfactory after meeting minimum reflections", console=self.console)
                                # User message already added before LLM call via _build_messages
                                self.chat_history.append({"role": "assistant", "content": response_text})
                                # Apply guardrail validation after satisfactory reflection
                                try:
                                    validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                    self._end_run(validated_response, "completed", {"duration_ms": (time.time() - start_time) * 1000})
                                    return validated_response
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed after reflection: {e}")
                                    # Rollback chat history on guardrail failure
                                    self.chat_history = self.chat_history[:chat_history_length]
                                    self._end_run(None, "error", {"error": str(e)})
                                    return None

                            # Check if we've hit max reflections
                            if reflection_count >= self.max_reflect - 1:
                                if self.verbose:
                                    _get_display_functions()['display_self_reflection']("Maximum reflection count reached, returning current response", console=self.console)
                                # User message already added before LLM call via _build_messages
                                self.chat_history.append({"role": "assistant", "content": response_text})
                                # Apply guardrail validation after max reflections
                                try:
                                    validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                    return validated_response
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed after max reflections: {e}")
                                    # Rollback chat history on guardrail failure
                                    self.chat_history = self.chat_history[:chat_history_length]
                                    return None
                            
                            # If not satisfactory and not at max reflections, continue with regeneration
                            logging.debug(f"{self.name} reflection count {reflection_count + 1}, continuing reflection process")
                            messages.append({"role": "user", "content": "Now regenerate your response using the reflection you made"})
                            # For custom LLMs during reflection, always use non-streaming to ensure complete responses
                            use_stream = self.stream if not self._using_custom_llm else False
                            response = self._chat_completion(messages, temperature=temperature, tools=None, stream=use_stream, task_name=task_name, task_description=task_description, task_id=task_id)
                            content = response.choices[0].message.content
                            response_text = content.strip() if content else ""
                            reflection_count += 1
                            continue  # Continue the loop for more reflections

                        except Exception as e:
                                _get_display_functions()['display_error'](f"Error in parsing self-reflection json {e}. Retrying", console=self.console)
                                logging.error("Reflection parsing failed.", exc_info=True)
                                messages.append({"role": "assistant", "content": "Self Reflection failed."})
                                reflection_count += 1
                                continue  # Continue even after error to try again
                    except Exception:
                        # Catch any exception from the inner try block and re-raise to outer handler
                        raise
            except Exception as e:
                # Catch any exceptions that escape the while loop
                _get_display_functions()['display_error'](f"Unexpected error in chat: {e}", console=self.console)
                # Rollback chat history
                self.chat_history = self.chat_history[:chat_history_length]
                return None

    def clean_json_output(self, output: str) -> str:
        """Clean and extract JSON from response text."""
        cleaned = output.strip()
        # Remove markdown code blocks if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned  

    async def achat(self, prompt: str, temperature=1.0, tools=None, output_json=None, output_pydantic=None, reasoning_steps=False, task_name=None, task_description=None, task_id=None, attachments=None):
        """Async version of chat method with self-reflection support.
        
        Args:
            prompt: Text query that WILL be stored in chat_history
            attachments: Optional list of image/file paths that are ephemeral
                        (used for THIS turn only, NEVER stored in history).
        """
        # Emit context trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.agent_start(self.name, {"role": self.role, "goal": self.goal})
        
        try:
            return await self._achat_impl(prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, task_name, task_description, task_id, attachments, _trace_emitter)
        finally:
            _trace_emitter.agent_end(self.name)
    
    async def _achat_impl(self, prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, task_name, task_description, task_id, attachments, _trace_emitter):
        """Internal async chat implementation (extracted for trace wrapping)."""
        # Process ephemeral attachments (DRY - builds multimodal prompt)
        # IMPORTANT: Original text 'prompt' is stored in history, attachments are NOT
        llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt
        
        # Trigger BEFORE_AGENT hook
        from ..hooks import HookEvent, BeforeAgentInput
        before_agent_input = BeforeAgentInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.BEFORE_AGENT,
            timestamp=str(time.time()),
            agent_name=self.name,
            prompt=prompt if isinstance(prompt, str) else str(prompt),
            conversation_history=self.chat_history,
            tools_available=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools or self.tools)]
        )
        hook_results = await self._hook_runner.execute(HookEvent.BEFORE_AGENT, before_agent_input)
        if self._hook_runner.is_blocked(hook_results):
            logging.warning(f"Agent {self.name} execution blocked by BEFORE_AGENT hook")
            return None
            
        # Update prompt if modified by hooks
        for res in hook_results:
            if res.output and res.output.modified_data and "prompt" in res.output.modified_data:
                prompt = res.output.modified_data["prompt"]
                llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt
        
        # Track execution via telemetry
        if hasattr(self, '_telemetry') and self._telemetry:
            self._telemetry.track_agent_execution(self.name, success=True)
            
        # Reset the final display flag for each new conversation
        self._final_display_shown = False
        
        # Log all parameter values when in debug mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            param_info = {
                "prompt": str(prompt)[:100] + "..." if isinstance(prompt, str) and len(str(prompt)) > 100 else str(prompt),
                "temperature": temperature,
                "tools": [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools] if tools else None,
                "output_json": str(output_json.__class__.__name__) if output_json else None,
                "output_pydantic": str(output_pydantic.__class__.__name__) if output_pydantic else None,
                "reasoning_steps": reasoning_steps,
                "agent_name": self.name,
                "agent_role": self.role,
                "agent_goal": self.goal
            }
            logging.debug(f"Agent.achat parameters: {json.dumps(param_info, indent=2, default=str)}")
        
        start_time = time.time()
        reasoning_steps = reasoning_steps or self.reasoning_steps
        try:
            # Default to self.tools if tools argument is None
            if tools is None:
                tools = self.tools

            # Search for existing knowledge if any knowledge is provided
            if self._knowledge_sources and not self._knowledge_processed:
                self._ensure_knowledge_processed()
            
            if self.knowledge:
                search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
                if search_results:
                    if isinstance(search_results, dict) and 'results' in search_results:
                        knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                    else:
                        knowledge_content = "\n".join(search_results)
                    prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"

            if self._using_custom_llm:
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize prompt content for consistent chat history storage
                normalized_content = prompt
                if isinstance(prompt, list):
                    # Extract text from multimodal prompts
                    normalized_content = next((item["text"] for item in prompt if item.get("type") == "text"), "")
                
                # Prevent duplicate messages
                if not (self.chat_history and 
                        self.chat_history[-1].get("role") == "user" and 
                        self.chat_history[-1].get("content") == normalized_content):
                    # Add user message to chat history BEFORE LLM call so handoffs can access it
                    self.chat_history.append({"role": "user", "content": normalized_content})
                
                try:
                    response_text = await self.llm_instance.get_response_async(
                        prompt=prompt,
                        system_prompt=self._build_system_prompt(tools),
                        chat_history=self.chat_history,
                        temperature=temperature,
                        tools=tools,
                        output_json=output_json,
                        output_pydantic=output_pydantic,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        reflection=self.self_reflect,
                        max_reflect=self.max_reflect,
                        min_reflect=self.min_reflect,
                        console=self.console,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools if tools is not None else self.tools)],
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id,
                        execute_tool_fn=self.execute_tool_async,
                        reasoning_steps=reasoning_steps
                    )

                    self.chat_history.append({"role": "assistant", "content": response_text})

                    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                    
                    # Apply guardrail validation for custom LLM response
                    try:
                        validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools, task_name, task_description, task_id)
                        # Execute callback after validation
                        self._execute_callback_and_display(normalized_content, validated_response, time.time() - start_time, task_name, task_description, task_id)
                        return validated_response
                    except Exception as e:
                        logging.error(f"Agent {self.name}: Guardrail validation failed for custom LLM: {e}")
                        # Rollback chat history on guardrail failure
                        self.chat_history = self.chat_history[:chat_history_length]
                        return None
                except Exception as e:
                    # Rollback chat history if LLM call fails
                    self.chat_history = self.chat_history[:chat_history_length]
                    _get_display_functions()['display_error'](f"Error in LLM chat: {e}")
                    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
                    return None

            # For OpenAI client
            # Use the new _build_messages helper method
            messages, original_prompt = self._build_messages(prompt, temperature, output_json, output_pydantic)
            
            # Store chat history length for potential rollback
            chat_history_length = len(self.chat_history)
            
            # Normalize original_prompt for consistent chat history storage
            normalized_content = original_prompt
            if isinstance(original_prompt, list):
                # Extract text from multimodal prompts
                normalized_content = next((item["text"] for item in original_prompt if item.get("type") == "text"), "")
            
            # Prevent duplicate messages
            if not (self.chat_history and 
                    self.chat_history[-1].get("role") == "user" and 
                    self.chat_history[-1].get("content") == normalized_content):
                # Add user message to chat history BEFORE LLM call so handoffs can access it
                self.chat_history.append({"role": "user", "content": normalized_content})

            reflection_count = 0
            start_time = time.time()

            while True:
                try:
                    if self.verbose:
                        display_text = prompt
                        if isinstance(prompt, list):
                            display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                        
                        if display_text and str(display_text).strip():
                            agent_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
                            await _get_display_functions()['adisplay_instruction'](
                                f"Agent {self.name} is processing prompt: {display_text}",
                                console=self.console,
                                agent_name=self.name,
                                agent_role=self.role,
                                agent_tools=agent_tools
                            )

                    # Use the new _format_tools_for_completion helper method
                    formatted_tools = self._format_tools_for_completion(tools)
                    
                    # Check if OpenAI client is available
                    if self._openai_client is None:
                        error_msg = "OpenAI client is not initialized. Please provide OPENAI_API_KEY or use a custom LLM provider."
                        _get_display_functions()['display_error'](error_msg)
                        return None

                    # Make the API call based on the type of request
                    if tools:
                        response = await self._openai_client.async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=temperature,
                            tools=formatted_tools,
                        )
                        result = await self._achat_completion(response, tools)
                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                            total_time = time.time() - start_time
                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                        # Execute callback after tool completion
                        self._execute_callback_and_display(original_prompt, result, time.time() - start_time, task_name, task_description, task_id)
                        return result
                    elif output_json or output_pydantic:
                        response = await self._openai_client.async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=temperature,
                            response_format={"type": "json_object"}
                        )
                        response_text = response.choices[0].message.content
                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                            total_time = time.time() - start_time
                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                        # Execute callback after JSON/Pydantic completion
                        self._execute_callback_and_display(original_prompt, response_text, time.time() - start_time, task_name, task_description, task_id)
                        return response_text
                    else:
                        response = await self._openai_client.async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=temperature
                        )
                        
                        response_text = response.choices[0].message.content
                        
                        # Handle self-reflection if enabled
                        if self.self_reflect:
                            reflection_count = 0
                            
                            while True:
                                reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
{self.reflect_prompt if self.reflect_prompt else "Identify any flaws, improvements, or actions."}
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
                                """
                                
                                # Add reflection prompt to messages
                                reflection_messages = messages + [
                                    {"role": "assistant", "content": response_text},
                                    {"role": "user", "content": reflection_prompt}
                                ]
                                
                                try:
                                    # Check if OpenAI client is available for self-reflection
                                    if self._openai_client is None:
                                        # For custom LLMs, self-reflection with structured output is not supported
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection'](f"Agent {self.name}: Self-reflection with structured output is not supported for custom LLM providers. Skipping reflection.", console=self.console)
                                        # Return the original response without reflection
                                        self.chat_history.append({"role": "user", "content": original_prompt})
                                        self.chat_history.append({"role": "assistant", "content": response_text})
                                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                                            total_time = time.time() - start_time
                                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                                        return response_text
                                    
                                    reflection_response = await self._openai_client.async_client.beta.chat.completions.parse(
                                        model=self.reflect_llm if self.reflect_llm else self.llm,
                                        messages=reflection_messages,
                                        temperature=temperature,
                                        response_format=_get_display_functions()['ReflectionOutput']
                                    )
                                    
                                    reflection_output = reflection_response.choices[0].message.parsed
                                    
                                    if self.verbose:
                                        _get_display_functions()['display_self_reflection'](f"Agent {self.name} self reflection (using {self.reflect_llm if self.reflect_llm else self.llm}): reflection='{reflection_output.reflection}' satisfactory='{reflection_output.satisfactory}'", console=self.console)
                                    
                                    # Only consider satisfactory after minimum reflections
                                    if reflection_output.satisfactory == "yes" and reflection_count >= self.min_reflect - 1:
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection']("Agent marked the response as satisfactory after meeting minimum reflections", console=self.console)
                                        break
                                    
                                    # Check if we've hit max reflections
                                    if reflection_count >= self.max_reflect - 1:
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection']("Maximum reflection count reached, returning current response", console=self.console)
                                        break
                                    
                                    # Regenerate response based on reflection
                                    regenerate_messages = reflection_messages + [
                                        {"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"},
                                        {"role": "user", "content": "Now regenerate your response using the reflection you made"}
                                    ]
                                    
                                    new_response = await self._openai_client.async_client.chat.completions.create(
                                        model=self.llm,
                                        messages=regenerate_messages,
                                        temperature=temperature
                                    )
                                    response_text = new_response.choices[0].message.content
                                    reflection_count += 1
                                    
                                except Exception as e:
                                    if self.verbose:
                                        _get_display_functions()['display_error'](f"Error in parsing self-reflection json {e}. Retrying", console=self.console)
                                    logging.error("Reflection parsing failed.", exc_info=True)
                                    reflection_count += 1
                                    if reflection_count >= self.max_reflect:
                                        break
                                    continue
                        
                        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                            total_time = time.time() - start_time
                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                        
                        # Apply guardrail validation for OpenAI client response
                        try:
                            validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                            # Execute callback after validation
                            self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                            return validated_response
                        except Exception as e:
                            logging.error(f"Agent {self.name}: Guardrail validation failed for OpenAI client: {e}")
                            # Rollback chat history on guardrail failure
                            self.chat_history = self.chat_history[:chat_history_length]
                            return None
                except Exception as e:
                    _get_display_functions()['display_error'](f"Error in chat completion: {e}")
                    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
                    return None
        except Exception as e:
            _get_display_functions()['display_error'](f"Error in achat: {e}")
            if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                total_time = time.time() - start_time
                logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
            return None

    async def _achat_completion(self, response, tools, reasoning_steps=False):
        """Async version of _chat_completion method"""
        try:
            message = response.choices[0].message
            if not hasattr(message, 'tool_calls') or not message.tool_calls:
                return message.content

            results = []
            for tool_call in message.tool_calls:
                try:
                    function_name = tool_call.function.name
                    # Parse JSON arguments safely 
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as json_error:
                        logging.error(f"Failed to parse tool arguments as JSON: {json_error}")
                        arguments = {}
                    
                    # Find the matching tool
                    tool = next((t for t in tools if t.__name__ == function_name), None)
                    if not tool:
                        _get_display_functions()['display_error'](f"Tool {function_name} not found")
                        continue
                    
                    # Check if the tool is async
                    if asyncio.iscoroutinefunction(tool):
                        result = await tool(**arguments)
                    else:
                        # Run sync function in executor to avoid blocking
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, lambda: tool(**arguments))
                    
                    results.append(result)
                except Exception as e:
                    _get_display_functions()['display_error'](f"Error executing tool {function_name}: {e}")
                    results.append(None)

            # If we have results, format them into a response
            if results:
                formatted_results = "\n".join([str(r) for r in results if r is not None])
                if formatted_results:
                    messages = [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "assistant", "content": "Here are the tool results:"},
                        {"role": "user", "content": formatted_results + "\nPlease process these results and provide a final response."}
                    ]
                    try:
                        final_response = await self._openai_client.async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=1.0,
                            stream=True
                        )
                        full_response_text = ""
                        reasoning_content = ""
                        chunks = []
                        start_time = time.time()
                        
                        # Process stream without display_generating since streaming is active
                        async for chunk in final_response:
                            chunks.append(chunk)
                            if chunk.choices[0].delta.content:
                                full_response_text += chunk.choices[0].delta.content
                            
                            if reasoning_steps and hasattr(chunk.choices[0].delta, "reasoning_content"):
                                rc = chunk.choices[0].delta.reasoning_content
                                if rc:
                                    reasoning_content += rc
                        
                        self.console.print()
                        
                        final_response = _get_llm_functions()['process_stream_chunks'](chunks)
                        # Return only reasoning content if reasoning_steps is True
                        if reasoning_steps and hasattr(final_response.choices[0].message, 'reasoning_content') and final_response.choices[0].message.reasoning_content:
                            return final_response.choices[0].message.reasoning_content
                        return final_response.choices[0].message.content if final_response else full_response_text

                    except Exception as e:
                        _get_display_functions()['display_error'](f"Error in final chat completion: {e}")
                        return formatted_results
                return formatted_results
            return None
        except Exception as e:
            _get_display_functions()['display_error'](f"Error in _achat_completion: {e}")
            return None

    async def arun(self, prompt: str, **kwargs):
        """Async version of run() - silent, non-streaming, returns structured result.
        
        Production-friendly async execution. Does not stream or display output.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments passed to achat()
            
        Returns:
            The agent's response as a string
        """
        # Remove stream from kwargs since achat() doesn't accept it
        kwargs.pop('stream', None)
        return await self.achat(prompt, **kwargs)

    async def astart(self, prompt: str, **kwargs):
        """Async version of start() - interactive, streaming-aware.
        
        Beginner-friendly async execution. Streams by default when in TTY.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments passed to achat()
            
        Returns:
            The agent's response as a string
        """
        import sys
        
        # Determine streaming behavior (same logic as start())
        stream_requested = kwargs.get('stream')
        if stream_requested is None:
            if getattr(self, 'stream', None) is not None:
                stream_requested = self.stream
            else:
                stream_requested = sys.stdout.isatty()
        
        kwargs['stream'] = stream_requested
        return await self.achat(prompt, **kwargs)

    def run(self, prompt: str, **kwargs):
        """Execute agent silently and return structured result.
        
        Production-friendly execution. Always uses silent mode with no streaming
        or verbose display, regardless of TTY status. Use this for programmatic,
        scripted, or automated usage where you want just the result.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments:
                - stream (bool): Force streaming if True. Default: False
                - output (str): Output preset override (rarely needed)
                
        Returns:
            The agent's response as a string
            
        Example:
            ```python
            agent = Agent(instructions="You are helpful")
            result = agent.run("What is 2+2?")  # Silent, returns "4"
            print(result)
            ```
            
        Note:
            Unlike .start() which enables verbose output in TTY for interactive
            use, .run() is always silent. This makes it suitable for:
            - Production pipelines
            - Automated scripts
            - Background processing
            - API endpoints
        """
        # Production defaults: no streaming, no display
        if 'stream' not in kwargs:
            kwargs['stream'] = False
        
        # Substitute dynamic variables ({{today}}, {{now}}, {{uuid}}, etc.)
        if prompt and "{{" in prompt:
            from praisonaiagents.utils.variables import substitute_variables
            prompt = substitute_variables(prompt, {})
        
        # Load history context
        self._load_history_context()
        
        # Check if planning mode is enabled
        if self.planning:
            result = self._start_with_planning(prompt, **kwargs)
        else:
            result = self.chat(prompt, **kwargs)
        
        # Auto-save session if enabled
        self._auto_save_session()
        
        return result
    
    def _get_planning_agent(self):
        """Lazy load PlanningAgent for planning mode."""
        if self._planning_agent is None and self.planning:
            from ..planning import PlanningAgent
            self._planning_agent = PlanningAgent(
                llm=self.llm if hasattr(self, 'llm') else (self.llm_instance.model if hasattr(self, 'llm_instance') else "gpt-4o-mini"),
                tools=self.planning_tools,
                reasoning=self.planning_reasoning,
                verbose=1 if self.verbose else 0
            )
        return self._planning_agent
    
    def _start_with_planning(self, prompt: str, **kwargs):
        """Execute with planning mode - creates plan then executes each step."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        
        console = _get_console()()
        
        # Step 1: Create the plan
        console.print("\n[bold blue]📋 PLANNING PHASE[/bold blue]")
        console.print("[dim]Creating implementation plan...[/dim]\n")
        
        planner = self._get_planning_agent()
        plan = planner.create_plan_sync(request=prompt, agents=[self])
        
        if not plan or not plan.steps:
            console.print("[yellow]⚠️ Planning failed, falling back to direct execution[/yellow]")
            return self.chat(prompt, **kwargs)
        
        # Display the plan
        console.print(Panel(
            Markdown(plan.to_markdown()),
            title="[bold green]Generated Plan[/bold green]",
            border_style="green"
        ))
        
        # Step 2: Execute each step
        console.print("\n[bold blue]🚀 EXECUTION PHASE[/bold blue]\n")
        
        results = []
        context = ""
        
        for i, step in enumerate(plan.steps):
            progress = (i + 1) / len(plan.steps)
            bar_length = 30
            filled = int(bar_length * progress)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            console.print(f"[dim]Progress: [{bar}] {progress * 100:.0f}%[/dim]")
            console.print(f"\n[bold]📌 Step {i + 1}/{len(plan.steps)}:[/bold] {step.description[:60]}...")
            
            # Build prompt with context from previous steps
            step_prompt = step.description
            if context:
                step_prompt = f"{step.description}\n\nContext from previous steps:\n{context}"
            
            # Execute the step
            result = self.chat(step_prompt, **kwargs)
            results.append({"step": i + 1, "description": step.description, "result": result})
            
            # Update context for next step (use full result, not truncated)
            context += f"\n\nStep {i + 1} result: {result if result else 'No result'}"
            
            console.print(f"   [green]✅ Completed[/green]")
        
        console.print(f"\n[bold green]🎉 EXECUTION COMPLETE[/bold green]")
        console.print(f"[dim]Progress: [{'█' * bar_length}] 100%[/dim]")
        console.print(f"Completed {len(plan.steps)}/{len(plan.steps)} steps!\n")
        
        # Compile all results into a comprehensive final output
        if len(results) > 1:
            # Create a compilation prompt
            all_results_text = "\n\n".join([
                f"## Step {r['step']}: {r['description']}\n\n{r['result']}" 
                for r in results
            ])
            
            compilation_prompt = f"""You are tasked with compiling a comprehensive, detailed report from the following research steps.

IMPORTANT: Write a DETAILED and COMPREHENSIVE report. Do NOT summarize or compress the information. 
Include ALL relevant details, data, statistics, and findings from each step.
Organize the information logically with clear sections and subsections.

## Research Results to Compile:

{all_results_text}

## Instructions:
1. Combine all the information into a single, well-organized document
2. Preserve ALL details, numbers, statistics, and specific findings
3. Use clear headings and subheadings
4. Do not omit any important information
5. Make it comprehensive and detailed

Write the complete compiled report:"""
            
            console.print("\n[bold blue]📝 COMPILING FINAL REPORT[/bold blue]")
            console.print("[dim]Creating comprehensive output from all steps...[/dim]\n")
            
            final_result = self.chat(compilation_prompt, **kwargs)
            return final_result
        
        # Return the single result if only one step
        return results[0]["result"] if results else None

    def switch_model(self, new_model: str) -> None:
        """
        Switch the agent's LLM model while preserving conversation history.
        
        Args:
            new_model: The new model name to switch to (e.g., "gpt-4o", "claude-3-sonnet")
        """
        # Store the new model name
        self.llm = new_model
        
        # Recreate the LLM instance with the new model
        try:
            from ..llm.llm import LLM
            self._llm_instance = LLM(
                model=new_model,
                base_url=self._openai_base_url,
                api_key=self._openai_api_key,
            )
            self._using_custom_llm = True
        except ImportError:
            # If LLM class not available, just update the model string
            pass
        
        # Chat history is preserved in self.chat_history (no action needed)

    def start(self, prompt: str = None, **kwargs):
        """Start the agent interactively with verbose output.
        
        Beginner-friendly execution. Defaults to verbose output with streaming
        when running in a TTY. Use this for interactive/terminal usage where 
        you want to see output in real-time with rich formatting.
        
        Args:
            prompt: The input prompt to process. If not provided, uses the 
                    agent's instructions as the task (useful when instructions
                    already describe what the agent should do).
            **kwargs: Additional arguments:
                - stream (bool | None): Override streaming. None = auto-detect TTY
                - output (str): Output preset override (e.g., "silent", "verbose")
                
        Returns:
            - If streaming: Generator yielding response chunks
            - If not streaming: The complete response as a string
            
        Example:
            ```python
            # Minimal usage - instructions IS the task
            agent = Agent(instructions="Research AI trends and summarize")
            result = agent.start()  # Uses instructions as task
            
            # With explicit prompt (overrides/adds to instructions)
            agent = Agent(instructions="You are a helpful assistant")
            result = agent.start("What is 2+2?")  # Uses prompt as task
            ```
            
        Note:
            Unlike .run() which is always silent (production use), .start()
            enables verbose output by default when in a TTY for beginner-friendly
            interactive use. Use .run() for programmatic/scripted usage.
        """
        import sys
        
        # If no prompt provided, use instructions as the task
        if prompt is None:
            prompt = self.instructions or "Hello"
        
        # Substitute dynamic variables ({{today}}, {{now}}, {{uuid}}, etc.)
        if prompt and "{{" in prompt:
            from praisonaiagents.utils.variables import substitute_variables
            prompt = substitute_variables(prompt, {})
        
        # Load history from past sessions
        self._load_history_context()
        
        # Determine if we're in an interactive TTY
        is_tty = sys.stdout.isatty()
        
        # Determine streaming behavior
        # Priority: explicit kwarg > agent's stream attribute > TTY detection
        stream_requested = kwargs.get('stream')
        if stream_requested is None:
            # Check agent's stream attribute first
            if getattr(self, 'stream', None) is not None:
                stream_requested = self.stream
            else:
                # Auto-detect: stream if stdout is a TTY (interactive terminal)
                stream_requested = is_tty
        
        # ─────────────────────────────────────────────────────────────────────
        # Enable verbose output in TTY for beginner-friendly interactive use
        # Priority: agent's explicit output config > start() override > TTY auto
        # ─────────────────────────────────────────────────────────────────────
        original_verbose = self.verbose
        original_markdown = self.markdown
        output_override = kwargs.pop('output', None)  # Pop to prevent passing to chat()
        
        # Check if agent was configured with explicit output mode (not default)
        # If so, respect it and don't auto-enable verbose for TTY
        has_explicit_output = getattr(self, '_has_explicit_output_config', False)
        
        try:
            # Apply output override from start() call if provided
            if output_override:
                # Apply explicit output preset for this call
                from ..config.presets import OUTPUT_PRESETS
                if output_override in OUTPUT_PRESETS:
                    preset = OUTPUT_PRESETS[output_override]
                    self.verbose = preset.get('verbose', False)
                    self.markdown = preset.get('markdown', False)
            # Only auto-enable verbose for TTY if NO explicit output was configured
            elif is_tty and not has_explicit_output:
                self.verbose = True
                self.markdown = True
            
            # Check if planning mode is enabled
            if self.planning:
                result = self._start_with_planning(prompt, **kwargs)
            elif stream_requested:
                # Return a generator for streaming response
                kwargs['stream'] = True
                result = self._start_stream(prompt, **kwargs)
            else:
                # Return regular chat response with animated working status
                kwargs['stream'] = False
                
                # Show animated status during LLM call if verbose
                if self.verbose and is_tty:
                    from ..main import PRAISON_COLORS, sync_display_callbacks
                    import threading
                    import time as time_module
                    
                    console = _get_console()()
                    start_time = time_module.time()
                    
                    # ─────────────────────────────────────────────────────────────
                    # Shared state for dynamic status messages (thread-safe)
                    # Updated by callbacks during tool execution
                    # ─────────────────────────────────────────────────────────────
                    current_status = ["Analyzing query..."]
                    tools_called = []
                    
                    # Register a temporary callback to track tool calls
                    def status_tool_callback(**kwargs):
                        tool_name = kwargs.get('tool_name', '')
                        if tool_name:
                            tools_called.append(tool_name)
                            current_status[0] = f"Calling tool: {tool_name}..."
                    
                    # Store original callback and register ours
                    original_tool_callback = sync_display_callbacks.get('tool_call')
                    sync_display_callbacks['tool_call'] = status_tool_callback
                    
                    # Animation state
                    result_holder = [None]
                    error_holder = [None]
                    
                    # Temporarily disable verbose in chat to prevent duplicate output
                    original_verbose_chat = self.verbose
                    
                    def run_chat():
                        try:
                            # Suppress verbose during animation - we'll display result ourselves
                            self.verbose = False
                            current_status[0] = "Sending to LLM..."
                            result_holder[0] = self.chat(prompt, **kwargs)
                            current_status[0] = "Finalizing response..."
                        except Exception as e:
                            error_holder[0] = e
                        finally:
                            self.verbose = original_verbose_chat
                            # Restore original callback
                            if original_tool_callback:
                                sync_display_callbacks['tool_call'] = original_tool_callback
                            elif 'tool_call' in sync_display_callbacks:
                                del sync_display_callbacks['tool_call']
                    
                    # Start chat in background thread
                    chat_thread = threading.Thread(target=run_chat)
                    chat_thread.start()
                    
                    from rich.panel import Panel
                    from rich.text import Text
                    from rich.markdown import Markdown
                    
                    # ─────────────────────────────────────────────────────────────
                    # Smart Agent Info: Only show if user provided meaningful info
                    # Skip if using defaults ("Agent"/"Assistant") with single agent
                    # ─────────────────────────────────────────────────────────────
                    has_custom_name = self.name and self.name not in ("Agent", "agent", None, "")
                    has_custom_role = self.role and self.role not in ("Assistant", "AI Assistant", "assistant", None, "")
                    has_tools = bool(self.tools)
                    
                    show_agent_info = has_custom_name or has_custom_role or has_tools
                    
                    agent_panel = None
                    if show_agent_info:
                        agent_info_parts = []
                        if has_custom_name:
                            agent_info_parts.append(f"[bold {PRAISON_COLORS['task']}]👤 Agent:[/] [{PRAISON_COLORS['agent_text']}]{self.name}[/]")
                        if has_custom_role:
                            agent_info_parts.append(f"[bold {PRAISON_COLORS['metrics']}]Role:[/] [{PRAISON_COLORS['agent_text']}]{self.role}[/]")
                        if has_tools:
                            tools_list = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools][:5]
                            tools_str = ", ".join(f"[italic {PRAISON_COLORS['response']}]{tool}[/]" for tool in tools_list)
                            agent_info_parts.append(f"[bold {PRAISON_COLORS['agent']}]Tools:[/] {tools_str}")
                        
                        agent_panel = Panel(
                            "\n".join(agent_info_parts), 
                            border_style=PRAISON_COLORS["agent"], 
                            title="[bold]Agent Info[/]", 
                            title_align="left", 
                            padding=(1, 2)
                        )
                    
                    # Create task panel
                    task_panel = Panel.fit(
                        Markdown(prompt) if self.markdown else Text(prompt),
                        title="Task",
                        border_style=PRAISON_COLORS["task"]
                    )
                    
                    # Show initial panels (agent info if applicable, then task)
                    if agent_panel:
                        console.print(agent_panel)
                    console.print(task_panel)
                    
                    # ─────────────────────────────────────────────────────────────
                    # Animate with Rich.Status showing DYNAMIC status from callbacks
                    # ─────────────────────────────────────────────────────────────
                    with console.status(
                        f"[bold yellow]Working...[/]  {current_status[0]}", 
                        spinner="dots",
                        spinner_style="yellow"
                    ) as status:
                        last_status = current_status[0]
                        while chat_thread.is_alive():
                            time_module.sleep(0.15)  # More responsive updates
                            # Only update if status changed (reduces flicker)
                            if current_status[0] != last_status:
                                last_status = current_status[0]
                            status.update(f"[bold yellow]Working...[/]  {current_status[0]}")
                    
                    # Calculate elapsed time
                    elapsed = time_module.time() - start_time
                    
                    # Re-raise any error from chat
                    if error_holder[0]:
                        raise error_holder[0]
                    
                    result = result_holder[0]
                    
                    # Display response panel
                    response_panel = Panel.fit(
                        Markdown(str(result)) if self.markdown else Text(str(result)),
                        title=f"Response ({elapsed:.1f}s)",
                        border_style=PRAISON_COLORS["response"]
                    )
                    console.print(response_panel)
                    
                    # Show tool activity summary if tools were called (deduplicated)
                    if tools_called:
                        # Use dict.fromkeys to preserve order while removing duplicates
                        unique_tools = list(dict.fromkeys(tools_called))
                        tools_summary = ", ".join(unique_tools)
                        console.print(f"[dim]🔧 Tools used: {tools_summary}[/dim]")
                else:
                    result = self.chat(prompt, **kwargs)
            
            # Auto-save session if enabled
            self._auto_save_session()
            
            # Auto-save output to file if configured
            if result and self._output_file:
                self._save_output_to_file(str(result))
            
            return result
        finally:
            # Restore original output settings
            self.verbose = original_verbose
            self.markdown = original_markdown
    
    def iter_stream(self, prompt: str, **kwargs):
        """Stream agent response as an iterator of chunks.
        
        App-friendly streaming. Yields response chunks without terminal display.
        Use this for building custom UIs or processing streams programmatically.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments:
                - display (bool): Show terminal output. Default: False
                - output (str): Output preset override
                
        Yields:
            str: Response chunks as they are generated
            
        Example:
            ```python
            agent = Agent(instructions="You are helpful")
            
            # Process stream programmatically
            full_response = ""
            for chunk in agent.iter_stream("Tell me a story"):
                full_response += chunk
                # Custom processing here
            
            # Or collect all at once
            response = "".join(agent.iter_stream("Hello"))
            ```
        """
        # Load history context
        self._load_history_context()
        
        # Force streaming, no display by default (app-friendly)
        kwargs['stream'] = True
        
        # Use the internal streaming generator
        for chunk in self._start_stream(prompt, **kwargs):
            yield chunk
        
        # Auto-save session if enabled
        self._auto_save_session()
    
    def _load_history_context(self):
        """Load history from past sessions into context.
        
        Note: This functionality is now handled via context= param with ManagerConfig.
        This method is kept for backward compatibility but is a no-op.
        Use context=ManagerConfig(history_sessions=N) to load past sessions.
        """
        pass
    
    def _auto_save_session(self):
        """Auto-save session if auto_save is enabled."""
        if not self.auto_save or not self._memory_instance:
            return
        
        try:
            # Filter out history markers before saving
            clean_history = [
                {k: v for k, v in msg.items() if k != "_from_history"}
                for msg in self.chat_history
            ]
            
            self._memory_instance.save_session(
                name=self.auto_save,
                conversation_history=clean_history,
                metadata={"agent_name": self.name, "user_id": self.user_id}
            )
            logging.debug(f"Auto-saved session: {self.auto_save}")
        except Exception as e:
            logging.debug(f"Error auto-saving session: {e}")

    def _save_output_to_file(self, content: str) -> bool:
        """Save agent output to file if output_file is configured.
        
        Args:
            content: The response content to save
            
        Returns:
            True if file was saved, False otherwise
        """
        if not self._output_file:
            return False
        
        try:
            import os
            
            # Expand user home directory and resolve path
            file_path = os.path.expanduser(self._output_file)
            file_path = os.path.abspath(file_path)
            
            # Create parent directories if they don't exist
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            # Write content to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(content))
            
            # Print success message to terminal
            print(f"✅ Output saved to {file_path}")
            logging.debug(f"Output saved to file: {file_path}")
            return True
            
        except Exception as e:
            logging.warning(f"Failed to save output to file '{self._output_file}': {e}")
            print(f"⚠️ Failed to save output to {self._output_file}: {e}")
            return False

    def _start_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Stream generator for real-time response chunks."""
        try:
            # Reset the final display flag for each new conversation
            self._final_display_shown = False
            
            # Temporarily disable verbose mode to prevent console output conflicts during streaming
            original_verbose = self.verbose
            self.verbose = False
            
            # For custom LLM path, use the new get_response_stream generator
            if self._using_custom_llm:
                # Handle knowledge search
                actual_prompt = prompt
                if self._knowledge_sources and not self._knowledge_processed:
                    self._ensure_knowledge_processed()
                
                if self.knowledge:
                    search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
                    if search_results:
                        if isinstance(search_results, dict) and 'results' in search_results:
                            knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                        else:
                            knowledge_content = "\n".join(search_results)
                        actual_prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"
                
                # Handle tools properly
                tools = kwargs.get('tools', self.tools)
                if tools is None or (isinstance(tools, list) and len(tools) == 0):
                    tool_param = self.tools
                else:
                    tool_param = tools
                
                # Convert MCP tools if needed
                if tool_param is not None:
                    MCP = None
                    try:
                        from ..mcp.mcp import MCP
                    except ImportError:
                        pass
                    if MCP is not None and isinstance(tool_param, MCP) and hasattr(tool_param, 'to_openai_tool'):
                        openai_tool = tool_param.to_openai_tool()
                        if openai_tool:
                            if isinstance(openai_tool, list):
                                tool_param = openai_tool
                            else:
                                tool_param = [openai_tool]
                
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize prompt content for chat history
                normalized_content = actual_prompt
                if isinstance(actual_prompt, list):
                    normalized_content = next((item["text"] for item in actual_prompt if item.get("type") == "text"), "")
                
                # Prevent duplicate messages in chat history
                if not (self.chat_history and 
                        self.chat_history[-1].get("role") == "user" and 
                        self.chat_history[-1].get("content") == normalized_content):
                    self.chat_history.append({"role": "user", "content": normalized_content})
                
                try:
                    # Use the new streaming generator from LLM class
                    response_content = ""
                    for chunk in self.llm_instance.get_response_stream(
                        prompt=actual_prompt,
                        system_prompt=self._build_system_prompt(tool_param),
                        chat_history=self.chat_history,
                        temperature=kwargs.get('temperature', 1.0),
                        tools=tool_param,
                        output_json=kwargs.get('output_json'),
                        output_pydantic=kwargs.get('output_pydantic'),
                        verbose=False,  # Keep verbose false for streaming
                        markdown=self.markdown,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tool_param or [])],
                        task_name=kwargs.get('task_name'),
                        task_description=kwargs.get('task_description'),
                        task_id=kwargs.get('task_id'),
                        execute_tool_fn=self.execute_tool
                    ):
                        response_content += chunk
                        yield chunk
                    
                    # Add complete response to chat history
                    if response_content:
                        self.chat_history.append({"role": "assistant", "content": response_content})
                        
                except Exception as e:
                    # Rollback chat history on error
                    self.chat_history = self.chat_history[:chat_history_length]
                    logging.error(f"Custom LLM streaming error: {e}")
                    raise
                    
            else:
                # For OpenAI-style models, implement proper streaming without display
                # Handle knowledge search
                actual_prompt = prompt
                if self._knowledge_sources and not self._knowledge_processed:
                    self._ensure_knowledge_processed()
                
                if self.knowledge:
                    search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
                    if search_results:
                        if isinstance(search_results, dict) and 'results' in search_results:
                            knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                        else:
                            knowledge_content = "\n".join(search_results)
                        actual_prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"
                
                # Handle tools properly
                tools = kwargs.get('tools', self.tools)
                if tools is None or (isinstance(tools, list) and len(tools) == 0):
                    tool_param = self.tools
                else:
                    tool_param = tools
                
                # Build messages using the helper method
                messages, original_prompt = self._build_messages(actual_prompt, kwargs.get('temperature', 1.0), 
                                                               kwargs.get('output_json'), kwargs.get('output_pydantic'))
                
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize original_prompt for consistent chat history storage
                normalized_content = original_prompt
                if isinstance(original_prompt, list):
                    normalized_content = next((item["text"] for item in original_prompt if item.get("type") == "text"), "")
                
                # Prevent duplicate messages in chat history
                if not (self.chat_history and 
                        self.chat_history[-1].get("role") == "user" and 
                        self.chat_history[-1].get("content") == normalized_content):
                    self.chat_history.append({"role": "user", "content": normalized_content})
                
                try:
                    # Check if OpenAI client is available
                    if self._openai_client is None:
                        raise ValueError("OpenAI client is not initialized. Please provide OPENAI_API_KEY or use a custom LLM provider.")
                    
                    # Format tools for OpenAI
                    formatted_tools = self._format_tools_for_completion(tool_param)
                    
                    # Create streaming completion directly without display function
                    completion_args = {
                        "model": self.llm,
                        "messages": messages,
                        "temperature": kwargs.get('temperature', 1.0),
                        "stream": True
                    }
                    if formatted_tools:
                        completion_args["tools"] = formatted_tools
                    
                    completion = self._openai_client.sync_client.chat.completions.create(**completion_args)
                    
                    # Stream the response chunks without display
                    response_text = ""
                    tool_calls_data = []
                    
                    for chunk in completion:
                        delta = chunk.choices[0].delta
                        
                        # Handle text content
                        if delta.content is not None:
                            chunk_content = delta.content
                            response_text += chunk_content
                            yield chunk_content
                        
                        # Handle tool calls (accumulate but don't yield as chunks)
                        if hasattr(delta, 'tool_calls') and delta.tool_calls:
                            for tool_call_delta in delta.tool_calls:
                                # Extend tool_calls_data list to accommodate the tool call index
                                while len(tool_calls_data) <= tool_call_delta.index:
                                    tool_calls_data.append({'id': '', 'function': {'name': '', 'arguments': ''}})
                                
                                # Accumulate tool call data
                                if tool_call_delta.id:
                                    tool_calls_data[tool_call_delta.index]['id'] = tool_call_delta.id
                                if tool_call_delta.function.name:
                                    tool_calls_data[tool_call_delta.index]['function']['name'] = tool_call_delta.function.name
                                if tool_call_delta.function.arguments:
                                    tool_calls_data[tool_call_delta.index]['function']['arguments'] += tool_call_delta.function.arguments
                    
                    # Handle any tool calls that were accumulated
                    if tool_calls_data:
                        # Add assistant message with tool calls to chat history
                        assistant_message = {"role": "assistant", "content": response_text}
                        if tool_calls_data:
                            assistant_message["tool_calls"] = [
                                {
                                    "id": tc['id'],
                                    "type": "function", 
                                    "function": tc['function']
                                } for tc in tool_calls_data if tc['id']
                            ]
                        self.chat_history.append(assistant_message)
                        
                        # Execute tool calls and add results to chat history
                        for tool_call in tool_calls_data:
                            if tool_call['id'] and tool_call['function']['name']:
                                try:
                                    # Parse JSON arguments safely 
                                    try:
                                        parsed_args = json.loads(tool_call['function']['arguments']) if tool_call['function']['arguments'] else {}
                                    except json.JSONDecodeError as json_error:
                                        logging.error(f"Failed to parse tool arguments as JSON: {json_error}")
                                        parsed_args = {}
                                    
                                    tool_result = self.execute_tool(
                                        tool_call['function']['name'], 
                                        parsed_args
                                    )
                                    # Add tool result to chat history
                                    self.chat_history.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call['id'],
                                        "content": str(tool_result)
                                    })
                                except Exception as tool_error:
                                    logging.error(f"Tool execution error in streaming: {tool_error}")
                                    # Add error result to chat history
                                    self.chat_history.append({
                                        "role": "tool", 
                                        "tool_call_id": tool_call['id'],
                                        "content": f"Error: {str(tool_error)}"
                                    })
                    else:
                        # Add complete response to chat history (text-only response)
                        if response_text:
                            self.chat_history.append({"role": "assistant", "content": response_text})
                        
                except Exception as e:
                    # Rollback chat history on error
                    self.chat_history = self.chat_history[:chat_history_length]
                    logging.error(f"OpenAI streaming error: {e}")
                    # Fall back to simulated streaming
                    response = self.chat(prompt, **kwargs)
                    if response:
                        words = str(response).split()
                        chunk_size = max(1, len(words) // 20)
                        for i in range(0, len(words), chunk_size):
                            chunk_words = words[i:i + chunk_size]
                            chunk = ' '.join(chunk_words)
                            if i + chunk_size < len(words):
                                chunk += ' '
                            yield chunk
            
            # Restore original verbose mode
            self.verbose = original_verbose
                    
        except Exception as e:
            # Restore verbose mode on any error
            self.verbose = original_verbose
            # Graceful fallback to non-streaming if streaming fails
            logging.warning(f"Streaming failed, falling back to regular response: {e}")
            response = self.chat(prompt, **kwargs)
            if response:
                yield response

    def execute(self, task, context=None):
        """Execute a task synchronously - backward compatibility method"""
        if hasattr(task, 'description'):
            prompt = task.description
        elif isinstance(task, str):
            prompt = task
        else:
            prompt = str(task)
        return self.chat(prompt)

    async def aexecute(self, task, context=None):
        """Execute a task asynchronously - backward compatibility method"""
        if hasattr(task, 'description'):
            prompt = task.description
        elif isinstance(task, str):
            prompt = task
        else:
            prompt = str(task)
        # Extract task info if available
        task_name = getattr(task, 'name', None)
        task_description = getattr(task, 'description', None)
        task_id = getattr(task, 'id', None)
        return await self.achat(prompt, task_name=task_name, task_description=task_description, task_id=task_id)

    async def execute_tool_async(self, function_name: str, arguments: Dict[str, Any]) -> Any:
        """Async version of execute_tool"""
        try:
            logging.info(f"Executing async tool: {function_name} with arguments: {arguments}")
            
            # Check if approval is required for this tool
            from ..approval import is_approval_required, request_approval, is_env_auto_approve, is_yaml_approved, mark_approved
            if is_approval_required(function_name):
                # Skip approval if auto-approve env var is set or tool is YAML-approved
                if is_env_auto_approve() or is_yaml_approved(function_name):
                    logging.debug(f"Tool {function_name} auto-approved (env={is_env_auto_approve()}, yaml={is_yaml_approved(function_name)})")
                    mark_approved(function_name)
                else:
                    decision = await request_approval(function_name, arguments)
                    if not decision.approved:
                        error_msg = f"Tool execution denied: {decision.reason}"
                        logging.warning(error_msg)
                        return {"error": error_msg, "approval_denied": True}
                    
                    # Use modified arguments if provided
                    if decision.modified_args:
                        arguments = decision.modified_args
                        logging.info(f"Using modified arguments: {arguments}")
            
            # Try to find the function in the agent's tools list first
            func = None
            for tool in self.tools:
                if (callable(tool) and getattr(tool, '__name__', '') == function_name):
                    func = tool
                    break
            
            if func is None:
                logging.error(f"Function {function_name} not found in tools")
                return {"error": f"Function {function_name} not found in tools"}

            try:
                if inspect.iscoroutinefunction(func):
                    logging.debug(f"Executing async function: {function_name}")
                    result = await func(**arguments)
                else:
                    logging.debug(f"Executing sync function in executor: {function_name}")
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: func(**arguments))
                
                # Ensure result is JSON serializable
                logging.debug(f"Raw result from tool: {result}")
                if result is None:
                    return {"result": None}
                try:
                    json.dumps(result)  # Test serialization
                    return result
                except TypeError:
                    logging.warning(f"Result not JSON serializable, converting to string: {result}")
                    return {"result": str(result)}

            except Exception as e:
                logging.error(f"Error executing {function_name}: {str(e)}", exc_info=True)
                return {"error": f"Error executing {function_name}: {str(e)}"}

        except Exception as e:
            logging.error(f"Error in execute_tool_async: {str(e)}", exc_info=True)
            return {"error": f"Error in execute_tool_async: {str(e)}"}

    def launch(self, path: str = '/', port: int = 8000, host: str = '0.0.0.0', debug: bool = False, protocol: str = "http"):
        """
        Launch the agent as an HTTP API endpoint or an MCP server.
        
        Args:
            path: API endpoint path (default: '/') for HTTP, or base path for MCP.
            port: Server port (default: 8000)
            host: Server host (default: '0.0.0.0')
            debug: Enable debug mode for uvicorn (default: False)
            protocol: "http" to launch as FastAPI, "mcp" to launch as MCP server.
            
        Returns:
            None
        """
        if protocol == "http":
            global _server_started, _registered_agents, _shared_apps
            
            # Try to import FastAPI dependencies - lazy loading
            try:
                import uvicorn
                from fastapi import FastAPI, HTTPException, Request
                from fastapi.responses import JSONResponse
                from pydantic import BaseModel
                import threading
                import time
                import asyncio
                
                # Define the request model here since we need pydantic
                class AgentQuery(BaseModel):
                    query: str
                    
            except ImportError as e:
                # Check which specific module is missing
                missing_module = str(e).split("No module named '")[-1].rstrip("'")
                _get_display_functions()['display_error'](f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
                logging.error(f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
                print(f"\nTo add API capabilities, install the required dependencies:")
                print(f"pip install {missing_module}")
                print("\nOr install all API dependencies with:")
                print("pip install 'praisonaiagents[api]'")
                return None
                
            # Initialize port-specific collections if needed
            if port not in _registered_agents:
                _registered_agents[port] = {}
                
            # Initialize shared FastAPI app if not already created for this port
            if _shared_apps.get(port) is None:
                _shared_apps[port] = FastAPI(
                    title=f"PraisonAI Agents API (Port {port})",
                    description="API for interacting with PraisonAI Agents"
                )
                
                # Add a root endpoint with a welcome message
                @_shared_apps[port].get("/")
                async def root():
                    return {
                        "message": f"Welcome to PraisonAI Agents API on port {port}. See /docs for usage.",
                        "endpoints": list(_registered_agents[port].keys())
                    }
                
                # Add healthcheck endpoint
                @_shared_apps[port].get("/health")
                async def healthcheck():
                    return {
                        "status": "ok", 
                        "endpoints": list(_registered_agents[port].keys())
                    }
            
            # Normalize path to ensure it starts with /
            if not path.startswith('/'):
                path = f'/{path}'
                
            # Check if path is already registered for this port
            if path in _registered_agents[port]:
                logging.warning(f"Path '{path}' is already registered on port {port}. Please use a different path.")
                print(f"⚠️ Warning: Path '{path}' is already registered on port {port}.")
                # Use a modified path to avoid conflicts
                original_path = path
                path = f"{path}_{self.agent_id[:6]}"
                logging.warning(f"Using '{path}' instead of '{original_path}'")
                print(f"🔄 Using '{path}' instead")
            
            # Register the agent to this path
            _registered_agents[port][path] = self.agent_id
            
            # Define the endpoint handler
            @_shared_apps[port].post(path)
            async def handle_agent_query(request: Request, query_data: Optional[AgentQuery] = None):
                # Handle both direct JSON with query field and form data
                if query_data is None:
                    try:
                        request_data = await request.json()
                        if "query" not in request_data:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                        query = request_data["query"]
                    except Exception:
                        # Fallback to form data or query params
                        form_data = await request.form()
                        if "query" in form_data:
                            query = form_data["query"]
                        else:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                else:
                    query = query_data.query
                    
                try:
                    # Use async version if available, otherwise use sync version
                    if asyncio.iscoroutinefunction(self.chat):
                        response = await self.achat(query, task_name=None, task_description=None, task_id=None)
                    else:
                        # Run sync function in a thread to avoid blocking
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(None, lambda p=query: self.chat(p))
                    
                    return {"response": response}
                except Exception as e:
                    logging.error(f"Error processing query: {str(e)}", exc_info=True)
                    return JSONResponse(
                        status_code=500,
                        content={"error": f"Error processing query: {str(e)}"}
                    )
            
            print(f"🚀 Agent '{self.name}' available at http://{host}:{port}")
            
            # Start the server if it's not already running for this port
            if not _server_started.get(port, False):
                # Mark the server as started first to prevent duplicate starts
                _server_started[port] = True
                
                # Start the server in a separate thread
                def run_server():
                    try:
                        print(f"✅ FastAPI server started at http://{host}:{port}")
                        print(f"📚 API documentation available at http://{host}:{port}/docs")
                        print(f"🔌 Available endpoints: {', '.join(list(_registered_agents[port].keys()))}")
                        uvicorn.run(_shared_apps[port], host=host, port=port, log_level="debug" if debug else "info")
                    except Exception as e:
                        logging.error(f"Error starting server: {str(e)}", exc_info=True)
                        print(f"❌ Error starting server: {str(e)}")
                
                # Run server in a background thread
                server_thread = threading.Thread(target=run_server, daemon=True)
                server_thread.start()
                
                # Wait for a moment to allow the server to start and register endpoints
                time.sleep(0.5)
            else:
                # If server is already running, wait a moment to make sure the endpoint is registered
                time.sleep(0.1)
                print(f"🔌 Available endpoints on port {port}: {', '.join(list(_registered_agents[port].keys()))}")
            
            # Get the stack frame to check if this is the last launch() call in the script
            import inspect
            stack = inspect.stack()
            
            # If this is called from a Python script (not interactive), try to detect if it's the last launch call
            if len(stack) > 1 and stack[1].filename.endswith('.py'):
                caller_frame = stack[1]
                caller_line = caller_frame.lineno
                
                try:
                    # Read the file to check if there are more launch calls after this one
                    with open(caller_frame.filename, 'r') as f:
                        lines = f.readlines()
                    
                    # Check if there are more launch() calls after the current line
                    has_more_launches = False
                    for line_content in lines[caller_line:]: # renamed line to line_content
                        if '.launch(' in line_content and not line_content.strip().startswith('#'):
                            has_more_launches = True
                            break
                    
                    # If this is the last launch call, block the main thread
                    if not has_more_launches:
                        try:
                            print("\nAll agents registered for HTTP mode. Press Ctrl+C to stop the servers.")
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            print("\nServers stopped")
                except Exception as e:
                    # If something goes wrong with detection, block anyway to be safe
                    logging.error(f"Error in launch detection: {e}")
                    try:
                        print("\nKeeping HTTP servers alive. Press Ctrl+C to stop.")
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nServers stopped")
            return None
            
        elif protocol == "mcp":
            try:
                import uvicorn
                from mcp.server.fastmcp import FastMCP
                from mcp.server.sse import SseServerTransport
                from starlette.applications import Starlette
                from starlette.requests import Request
                from starlette.routing import Mount, Route
                from mcp.server import Server as MCPServer  # noqa: F401 - imported for availability check
                import threading
                import time
                import inspect
                import asyncio  # Import asyncio in the MCP scope
                # logging is already imported at the module level
                
            except ImportError as e:
                missing_module = str(e).split("No module named '")[-1].rstrip("'")
                _get_display_functions()['display_error'](f"Missing dependency: {missing_module}. Required for launch() method with MCP mode.")
                logging.error(f"Missing dependency: {missing_module}. Required for launch() method with MCP mode.")
                print(f"\nTo add MCP capabilities, install the required dependencies:")
                print(f"pip install {missing_module} mcp praison-mcp starlette uvicorn") # Added mcp, praison-mcp, starlette, uvicorn
                print("\nOr install all MCP dependencies with relevant packages.")
                return None

            mcp_server_instance_name = f"{self.name}_mcp_server" if self.name else "agent_mcp_server"
            mcp = FastMCP(mcp_server_instance_name)

            # Determine the MCP tool name based on self.name
            actual_mcp_tool_name = f"execute_{self.name.lower().replace(' ', '_').replace('-', '_')}_task" if self.name \
                else "execute_task"

            @mcp.tool(name=actual_mcp_tool_name)
            async def execute_agent_task(prompt: str) -> str:
                """Executes the agent's primary task with the given prompt."""
                logging.info(f"MCP tool '{actual_mcp_tool_name}' called with prompt: {prompt}")
                try:
                    # Ensure self.achat is used as it's the async version and pass its tools
                    if hasattr(self, 'achat') and asyncio.iscoroutinefunction(self.achat):
                        response = await self.achat(prompt, tools=self.tools, task_name=None, task_description=None, task_id=None)
                    elif hasattr(self, 'chat'): # Fallback for synchronous chat
                        # Use copy_context_to_callable to propagate contextvars (needed for trace emission)
                        from ..trace.context_events import copy_context_to_callable
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(None, copy_context_to_callable(lambda p=prompt: self.chat(p, tools=self.tools)))
                    else:
                        logging.error(f"Agent {self.name} has no suitable chat or achat method for MCP tool.")
                        return f"Error: Agent {self.name} misconfigured for MCP."
                    return response if response is not None else "Agent returned no response."
                except Exception as e:
                    logging.error(f"Error in MCP tool '{actual_mcp_tool_name}': {e}", exc_info=True)
                    return f"Error executing task: {str(e)}"

            # Normalize base_path for MCP routes
            base_path = path.rstrip('/')
            sse_path = f"{base_path}/sse"
            messages_path_prefix = f"{base_path}/messages" # Prefix for message posting
            
            # Ensure messages_path ends with a slash for Mount
            if not messages_path_prefix.endswith('/'):
                messages_path_prefix += '/'


            sse_transport = SseServerTransport(messages_path_prefix) # Pass the full prefix

            async def handle_sse_connection(request: Request) -> None:
                logging.debug(f"SSE connection request received from {request.client} for path {request.url.path}")
                async with sse_transport.connect_sse(
                        request.scope,
                        request.receive,
                        request._send,  # noqa: SLF001
                ) as (read_stream, write_stream):
                    await mcp._mcp_server.run( # Use the underlying server from FastMCP
                        read_stream,
                        write_stream,
                        mcp._mcp_server.create_initialization_options(),
                    )
            
            starlette_app = Starlette(
                debug=debug,
                routes=[
                    Route(sse_path, endpoint=handle_sse_connection),
                    Mount(messages_path_prefix, app=sse_transport.handle_post_message),
                ],
            )

            print(f"🚀 Agent '{self.name}' MCP server starting on http://{host}:{port}")
            print(f"📡 MCP SSE endpoint available at {sse_path}")
            print(f"📢 MCP messages post to {messages_path_prefix}")
            # Instead of trying to extract tool names, hardcode the known tool name
            tool_names = [actual_mcp_tool_name]  # Use the determined dynamic tool name
            print(f"🛠️ Available MCP tools: {', '.join(tool_names)}")

            # Uvicorn server running logic (similar to HTTP mode but standalone for MCP)
            def run_mcp_server():
                try:
                    uvicorn.run(starlette_app, host=host, port=port, log_level="debug" if debug else "info")
                except Exception as e:
                    logging.error(f"Error starting MCP server: {str(e)}", exc_info=True)
                    print(f"❌ Error starting MCP server: {str(e)}")

            server_thread = threading.Thread(target=run_mcp_server, daemon=True)
            server_thread.start()
            time.sleep(0.5) # Allow server to start

            # Blocking logic for MCP mode
            import inspect # Already imported but good for clarity
            stack = inspect.stack()
            if len(stack) > 1 and stack[1].filename.endswith('.py'):
                caller_frame = stack[1]
                caller_line = caller_frame.lineno
                try:
                    with open(caller_frame.filename, 'r') as f:
                        lines = f.readlines()
                    has_more_launches = False
                    for line_content in lines[caller_line:]: # renamed line to line_content
                        if '.launch(' in line_content and not line_content.strip().startswith('#'):
                            has_more_launches = True
                            break
                    if not has_more_launches:
                        try:
                            print("\nAgent MCP server running. Press Ctrl+C to stop.")
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            print("\nMCP Server stopped")
                except Exception as e:
                    logging.error(f"Error in MCP launch detection: {e}")
                    try:
                        print("\nKeeping MCP server alive. Press Ctrl+C to stop.")
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nMCP Server stopped")
            return None
        else:
            _get_display_functions()['display_error'](f"Invalid protocol: {protocol}. Choose 'http' or 'mcp'.")
            return None 