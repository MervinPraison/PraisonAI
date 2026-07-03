"""PraisonAI CLI class — C8.4 legacy shell."""

from __future__ import annotations

import sys
import argparse
import warnings
import os
import json
import yaml
import time
from rich import print
from dotenv import load_dotenv
import shutil
import subprocess
import logging
import importlib

from praisonai_code._version import get_package_version
from praisonai_code._framework_availability import is_available
from praisonai_code._logging import configure_cli_logging
from .env_security import (
    _BLOCKED_ENV_KEYS,
    _BLOCKED_ENV_KEYS_UPPER,
    _load_env_once,
    _validate_env_key,
)

__version__ = get_package_version()

if os.environ.get('LOGLEVEL', 'INFO').upper() != 'DEBUG':
    warnings.filterwarnings(
        "ignore",
        message=".*found in sys.modules after import of package.*",
        category=RuntimeWarning
    )

# Lazy import helpers for inbuilt_tools and config
def _get_inbuilt_tools():
    """Lazy import inbuilt_tools only when crewai/autogen features are used."""
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_inbuilt_tools()

def _get_generate_config():
    """Lazy import generate_config only when training features are used."""
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_generate_config()

# Lazy import helpers for heavy modules
def _get_auto_generator():
    """Lazy import AutoGenerator to avoid loading heavy deps at CLI startup."""
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_auto_generator()

def _get_agents_generator():
    """Lazy import AgentsGenerator to avoid loading heavy deps at CLI startup."""
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_agents_generator()


def _get_call_module():
    """Lazy import call module only when call feature is used.
    
    Raises:
        ImportError: If praisonai.api.call is not installed
    """
    import importlib.util
    if not importlib.util.find_spec("praisonai.api.call"):
        raise ImportError(
            "Call feature is not installed. Install with: pip install \"praisonai[call]\""
        )
    from praisonai_code._wrapper_bridge import import_wrapper_module
    _mod = import_wrapper_module('praisonai.api')
    call_module = getattr(_mod, 'call')
    return call_module

def _get_gradio():
    """Lazy import gradio only when gradio UI is used.
    
    Raises:
        ImportError: If gradio is not installed
    """
    if not _compute_availability_flag("GRADIO_AVAILABLE"):
        raise ImportError(
            "Gradio is not installed. Install with: pip install gradio"
        )
    import gradio as gr
    return gr

def _fw_registry_module():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.framework_adapters.registry")


def _fw_validators_module():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.framework_adapters.validators")


def _fw_workflow_module():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.framework_adapters.workflow_framework")


def _get_autogen():
    """Resolve the autogen framework via the canonical adapter registry.

    Routing through ``framework_adapters.registry`` keeps a single source of
    truth for framework availability (honouring any user-registered adapter
    via the ``praisonai.framework_adapters`` entry-point group) instead of a
    parallel hand-rolled import path.

    Raises:
        ImportError: If autogen is not installed
    """
    get_default_registry = _fw_registry_module().get_default_registry
    # Use resolve() (returns the adapter class without the strict run()-signature
    # validation that create() applies) because "autogen" maps to the family
    # *router* adapter, whose run() intentionally does not implement the full
    # execution protocol. This still honours any user-registered "autogen"
    # adapter discovered via the praisonai.framework_adapters entry points.
    adapter = get_default_registry().resolve("autogen")()
    hint = getattr(adapter, "install_hint", 'pip install "praisonai-frameworks[autogen]"')
    if not adapter.is_available():
        raise ImportError(f"AutoGen is not installed. {hint}")
    # The family adapter's is_available() is True if *any* variant (v0.2/v0.4/AG2)
    # is present, but this helper returns the classic ``autogen`` (v0.2) module.
    # Guard the bare import so a future-enabled v0.4/AG2-only environment surfaces
    # the actionable install hint instead of a raw ModuleNotFoundError.
    try:
        import autogen
    except ImportError as e:
        raise ImportError(f"AutoGen is not installed. {hint}") from e
    return autogen

# Configure root logging only at CLI entrypoint
from praisonai_code._logging import configure_cli_logging
configure_cli_logging(os.environ.get('LOGLEVEL', 'WARNING') or 'WARNING')
logging.getLogger('alembic').setLevel(logging.ERROR)
logging.getLogger('gradio').setLevel(logging.ERROR)
logging.getLogger('gradio').setLevel(os.environ.get('GRADIO_LOGLEVEL', 'WARNING'))
logging.getLogger('rust_logger').setLevel(logging.WARNING)
logging.getLogger('duckduckgo').setLevel(logging.ERROR)
logging.getLogger('_client').setLevel(logging.ERROR)
# Suppress praisonaiagents INFO logs unless LOGLEVEL is explicitly set to debug/info
if os.environ.get('LOGLEVEL', '').upper() not in ('DEBUG', 'INFO'):
    logging.getLogger('praisonaiagents').setLevel(logging.WARNING)
    logging.getLogger('praisonaiagents.llm').setLevel(logging.WARNING)
    logging.getLogger('praisonaiagents.llm.llm').setLevel(logging.WARNING)

def stream_subprocess(command, env=None):
    """
    Execute a subprocess command and stream the output to the terminal in real-time.

    Args:
        command (list): A list containing the command and its arguments.
        env (dict, optional): Environment variables for the subprocess.
    """
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=env
    )

    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        sys.stdout.flush()  # Ensure output is flushed immediately

    process.stdout.close()
    return_code = process.wait()

    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)

# Use centralized availability detection
from praisonai_code._framework_availability import is_available

# Optional-dependency availability flags are resolved lazily so that merely
# importing this module (e.g. for `praisonai --help`) does not walk the
# meta-path with find_spec() for every optional dependency on every cold start.
#
# Maps the public flag name -> the framework key understood by is_available().
_AVAILABILITY_FLAGS = {
    "GRADIO_AVAILABLE": "gradio",
    "CREWAI_AVAILABLE": "crewai",
    "AUTOGEN_AVAILABLE": "autogen",
    "PRAISONAI_AVAILABLE": "praisonaiagents",
    "TRAIN_AVAILABLE": "unsloth",
}


def _compute_availability_flag(name):
    """Compute a single availability flag without caching into globals()."""
    if name in _AVAILABILITY_FLAGS:
        return is_available(_AVAILABILITY_FLAGS[name])
    if name == "CALL_MODULE_AVAILABLE":
        try:
            import importlib.util
            return importlib.util.find_spec("praisonai.api.call") is not None
        except (ModuleNotFoundError, AttributeError):
            return False
    raise AttributeError(name)


def _ensure_availability_flags():
    """Populate the module-level availability flags on first use.

    Internal code references these as bare names (e.g. ``if CREWAI_AVAILABLE``)
    which cannot trigger PEP 562 ``__getattr__``; calling this at the start of
    command execution binds them into globals() so those references resolve
    while keeping plain ``import`` cheap.
    """
    g = globals()
    for flag in (*_AVAILABILITY_FLAGS, "CALL_MODULE_AVAILABLE"):
        if flag not in g:
            g[flag] = _compute_availability_flag(flag)


# Module-level __getattr__ for backward compatibility with external access.
# This lazily computes the flag on first attribute access and caches it.
def __getattr__(name):
    if name in _AVAILABILITY_FLAGS or name == "CALL_MODULE_AVAILABLE":
        value = _compute_availability_flag(name)
        globals()[name] = value  # cache so subsequent bare-name refs resolve
        return value
    raise AttributeError(name)

class PraisonAI:
    def __init__(self, agent_file="agents.yaml", framework="", auto=False, init=False, agent_yaml=None, tools=None):
        """
        Initialize the PraisonAI object with default parameters.
        """
        # Initialize telemetry defaults (moved from lazy __getattr__ hook).
        # Optional: the wrapper package is not required for the standalone
        # praisonai-code hot path, so skip silently when it is absent.
        from praisonai_code._wrapper_bridge import optional_wrapper_attr
        _ensure_telemetry_defaults = optional_wrapper_attr(
            "praisonai", "_ensure_telemetry_defaults"
        )
        if _ensure_telemetry_defaults is not None:
            _ensure_telemetry_defaults()
        self.agent_yaml = agent_yaml
        self._interactive_mode = False  # Flag for interactive TUI mode
        # Create config_list with AutoGen compatibility
        # Resolve LLM endpoint configuration from environment variables
        from praisonai_code.llm.config import build_config_list
        self.config_list = build_config_list()
        self.agent_file = agent_file
        self.framework = framework
        
        # Validate framework availability early to fail fast
        if self.framework:
            try:
                _fw_validators_module().assert_framework_available(self.framework)
            except ImportError as e:
                print(f"ERROR: {e}")
                sys.exit(1)
        
        self.auto = auto
        self.init = init
        self.tools = tools or []  # Store tool class names as a list

    def run(self):
        """
        Run the PraisonAI application.
        """
        return self.main()

    @staticmethod
    def _require_agents():
        """Exit with an install hint if praisonaiagents is unavailable.

        Single source of truth for the "needs praisonaiagents" guard so the same
        check is not duplicated across every command branch.
        """
        _ensure_availability_flags()
        if not globals().get("PRAISONAI_AVAILABLE", False):
            print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
            print("\npip install praisonaiagents\n")
            sys.exit(1)

    def read_stdin_if_available(self):
        """
        Read from stdin if it's available (when data is piped in).
        Returns the stdin content or None if no piped input is available.
        """
        try:
            # Check if stdin is not a terminal (i.e., has piped input)
            if not sys.stdin.isatty():
                import select
                # Non-blocking check: only read if data is actually available.
                # Without this, sys.stdin.read() blocks forever in non-TTY
                # environments (subprocesses, CI/CD, IDE terminals, Docker)
                # where stdin is a pipe with no EOF.
                if select.select([sys.stdin], [], [], 0.0)[0]:
                    stdin_content = sys.stdin.read().strip()
                    return stdin_content if stdin_content else None
                return None
        except Exception:
            # If there's any error reading stdin, ignore it
            pass
        return None

    def read_file_if_provided(self, file_path):
        """
        Read content from a file if the file path is provided.
        Returns the file content or None if file cannot be read.
        """
        if not file_path:
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read().strip()
                return file_content if file_content else None
        except FileNotFoundError:
            print(f"[red]ERROR: File not found: {file_path}[/red]")
            sys.exit(1)
        except Exception as e:
            print(f"[red]ERROR: Failed to read file: {e}[/red]")
            sys.exit(1)

    def main(self):
        """
        The main function of the PraisonAI object. It parses the command-line arguments,
        initializes the necessary attributes, and then calls the appropriate methods based on the
        provided arguments.
        """
        # Load environment variables from .env file
        _load_env_once()

        # Bind optional-dependency availability flags into module globals so the
        # bare-name references used throughout command handling resolve. This is
        # deferred to command execution to keep plain `import` cheap.
        _ensure_availability_flags()

        # Warning filters now installed via Typer callback for CLI-only usage
        
        # Telemetry defaults now handled in PraisonAI.__init__ with Langfuse awareness
        
        # Store the original agent_file from constructor
        original_agent_file = self.agent_file
        
        # Parse args - this returns both args and unknown_args
        preserved_args = getattr(self, 'args', None)
        parse_result = self.parse_args()
        if isinstance(parse_result, tuple):
            args, unknown_args = parse_result
        else:
            args = parse_result
            unknown_args = []
        
        # Preserve project session flags set by ``praison run`` before parse_args()
        if preserved_args and getattr(preserved_args, 'cli_project_sessions', False):
            for attr in ('auto_save', 'resume_session', 'cli_project_sessions'):
                if hasattr(preserved_args, attr):
                    setattr(args, attr, getattr(preserved_args, attr))
        
        # Store args for use in handle_direct_prompt
        self.args = args
        invocation_cmd = "praisonai"
        version_string = f"PraisonAI version {__version__}"
        

        # Handle -p/--prompt flag - treat as direct prompt
        if getattr(args, 'prompt_flag', None):
            args.direct_prompt = args.prompt_flag
            args.command = None

        self.framework = args.framework or self.framework
        
        # Validate framework availability early to fail fast
        if self.framework:
            try:
                _fw_validators_module().assert_framework_available(self.framework)
            except ImportError as e:
                print(f"ERROR: {e}")
                sys.exit(1)
        
        # Update config_list model if --model flag is provided
        if getattr(args, 'model', None):
            self.config_list[0]['model'] = args.model
            # Bridge --model to args.llm so direct prompts also use it
            # (args.llm is what handle_direct_prompt checks for Agent config)
            if not getattr(args, 'llm', None):
                args.llm = args.model

        # Check for piped input from stdin
        stdin_input = self.read_stdin_if_available()
        
        # Check for file input if --file is provided
        file_input = self.read_file_if_provided(getattr(args, 'file', None))

        if args.command:
            # Handle persistence command
            if args.command == "persistence":
                from ..features.persistence import handle_persistence_command
                handle_persistence_command(unknown_args)
                return None
            
            # Handle schedule command
            if args.command == "schedule":
                from ..features.agent_scheduler import AgentSchedulerHandler
                # Check for subcommands (start, list, stop, logs, restart)
                subcommand = unknown_args[0] if unknown_args and not unknown_args[0].startswith('-') else None
                
                if subcommand in ['start', 'list', 'stop', 'logs', 'restart', 'delete', 'describe', 'save', 'stop-all', 'stats']:
                    exit_code = AgentSchedulerHandler.handle_daemon_command(subcommand, args, unknown_args[1:] if len(unknown_args) > 1 else [])
                else:
                    # Legacy mode: direct scheduling (foreground) or daemon mode
                    daemon_mode = getattr(args, 'daemon', False)
                    exit_code = AgentSchedulerHandler.handle_schedule_command(args, unknown_args, daemon_mode=daemon_mode)
                
                sys.exit(exit_code)
            
            # Handle backends command
            elif args.command == "backends":
                subcommand = unknown_args[0] if unknown_args and not unknown_args[0].startswith('-') else None
                
                if subcommand == "list" or subcommand is None:
                    # List registered CLI backends
                    try:
                        from praisonai_code.cli_backends import list_cli_backends
                        backends = list_cli_backends()
                        for backend in backends:
                            print(backend)
                        return ""
                    except ImportError:
                        print("[red]CLI backends not available[/red]")
                        return None
                else:
                    print(f"[red]Unknown backends subcommand: {subcommand}[/red]")
                    print("Available subcommands: list")
                    return None
            
            elif args.command.startswith("tests.test") or args.command.startswith("tests/test"):  # Argument used for testing purposes
                print("test")
                return "test"
            else:
                # Handle --compare flag for CLI mode comparison
                if hasattr(args, 'compare') and args.compare:
                    from ..features.compare import CompareHandler
                    handler = CompareHandler(verbose=getattr(args, 'verbose', False))
                    result = handler.execute(
                        args.command,
                        args.compare,
                        model=getattr(args, 'llm', None),
                        output_path=getattr(args, 'compare_output', None)
                    )
                    return result
                
                # Combine command with any available inputs (stdin and/or file)
                combined_inputs = []
                if stdin_input:
                    combined_inputs.append(stdin_input)
                if file_input:
                    combined_inputs.append(file_input)
                
                if combined_inputs:
                    combined_prompt = f"{args.command} {' '.join(combined_inputs)}"
                    result = self.handle_direct_prompt(combined_prompt)
                    # Result already printed by handle_direct_prompt, don't print again
                    return result
                elif os.path.isfile(args.command) or args.command.lower().endswith((".yaml", ".yml")):
                    # Treat as an agent file when it is an existing file or a YAML path
                    self.agent_file = args.command
                else:
                    # Bare positional that isn't a file/YAML path: run it as a one-shot prompt
                    result = self.handle_direct_prompt(args.command)
                    # Result already printed by handle_direct_prompt, don't print again
                    return result
        elif hasattr(args, 'direct_prompt') and args.direct_prompt:
            # Only handle direct prompt if agent_file wasn't explicitly set in constructor
            if original_agent_file == "agents.yaml":  # Default value, so safe to use direct prompt
                # Handle --compare flag for CLI mode comparison
                if hasattr(args, 'compare') and args.compare:
                    from ..features.compare import CompareHandler
                    handler = CompareHandler(verbose=getattr(args, 'verbose', False))
                    result = handler.execute(
                        args.direct_prompt,
                        args.compare,
                        model=getattr(args, 'llm', None),
                        output_path=getattr(args, 'compare_output', None)
                    )
                    return result
                
                # Combine direct prompt with any available inputs (stdin and/or file)
                prompt_parts = [args.direct_prompt]
                if stdin_input:
                    prompt_parts.append(stdin_input)
                if file_input:
                    prompt_parts.append(file_input)
                prompt = ' '.join(prompt_parts)
                result = self.handle_direct_prompt(prompt)
                # Result already printed by handle_direct_prompt, don't print again
                return result
            else:
                # Agent file was explicitly set, ignore direct prompt and use the file
                pass
        elif stdin_input or file_input:
            # If only stdin/file input is provided (no command), use it as direct prompt
            if original_agent_file == "agents.yaml":  # Default value, so safe to use input as prompt
                # Combine any available inputs
                inputs = []
                if stdin_input:
                    inputs.append(stdin_input)
                if file_input:
                    inputs.append(file_input)
                combined_input = ' '.join(inputs)
                result = self.handle_direct_prompt(combined_input)
                # Result already printed by handle_direct_prompt, don't print again
                return result
        # If no command or direct_prompt, preserve agent_file from constructor (don't overwrite)

        if args.deploy:
            if args.schedule or args.schedule_config:
                # Scheduled deployment
                from praisonai_code._wrapper_bridge import import_wrapper_module
                _mod = import_wrapper_module('praisonai.scheduler')
                create_scheduler = getattr(_mod, 'create_scheduler')
                
                # Load configuration from file if provided
                config = {"max_retries": args.max_retries}
                schedule_expr = args.schedule
                provider = args.provider
                
                if args.schedule_config:
                    try:
                        with open(args.schedule_config, 'r') as f:
                            file_config = yaml.safe_load(f)
                        if file_config is None:
                            file_config = {}
                        if not isinstance(file_config, dict):
                            raise ValueError("Schedule config must be a YAML mapping")
                        
                        # Extract deployment config
                        deploy_config = file_config.get('deployment', {})
                        if deploy_config is None:
                            deploy_config = {}
                        if not isinstance(deploy_config, dict):
                            raise ValueError("'deployment' must be a mapping")
                        schedule_expr = schedule_expr or deploy_config.get('schedule')
                        provider = deploy_config.get('provider', provider)
                        config['max_retries'] = deploy_config.get('max_retries', config['max_retries'])
                        
                        # Apply environment variables if specified
                        env_vars = file_config.get('environment', {})
                        if not isinstance(env_vars, dict):
                            raise ValueError("'environment' must be a mapping of KEY: value pairs")
                        # Validate all keys first (fail-closed) before mutating os.environ
                        validated_env = {}
                        for key, value in env_vars.items():
                            _validate_env_key(key)
                            validated_env[key] = str(value)
                        os.environ.update(validated_env)
                            
                    except FileNotFoundError:
                        print(f"Configuration file not found: {args.schedule_config}")
                        sys.exit(1)
                    except ValueError as e:
                        print(f"Invalid schedule configuration: {e}")
                        sys.exit(1)
                    except yaml.YAMLError as e:
                        print(f"Error parsing configuration file: {e}")
                        sys.exit(1)
                
                if not schedule_expr:
                    print("Error: Schedule expression required. Use --schedule or specify in config file.")
                    sys.exit(1)
                
                scheduler = create_scheduler(provider=provider, config=config)
                
                print(f"Starting scheduled deployment with schedule: {schedule_expr}")
                print(f"Provider: {provider}")
                print(f"Max retries: {config['max_retries']}")
                print("Press Ctrl+C to stop the scheduler")
                
                if scheduler.start(schedule_expr, config['max_retries']):
                    try:
                        # Keep the main thread alive
                        while scheduler.is_running:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\nStopping scheduler...")
                        scheduler.stop()
                        print("Scheduler stopped successfully")
                else:
                    print("Failed to start scheduler")
                    sys.exit(1)
            else:
                # One-time deployment using new deploy system
                from ..features.deploy import DeployHandler
                handler = DeployHandler()
                
                # Create args object for handler
                class DeployArgs:
                    def __init__(self):
                        self.file = "agents.yaml"
                        self.type = None
                        self.provider = args.provider if hasattr(args, 'provider') else 'gcp'
                        self.json = False
                        self.background = False
                
                handler.handle_deploy(DeployArgs())
            return

        # chat and code commands are now terminal-native (handled by Typer commands)

        if getattr(args, 'realtime', False):
            try:
                from praisonai_code._wrapper_bridge import import_wrapper_module
                _mod = import_wrapper_module('praisonai.cli.commands.ui')
                _launch_aiui_app = getattr(_mod, '_launch_aiui_app')
                _launch_aiui_app("ui_realtime", "ui_realtime", 8085, "127.0.0.1", None, False, "Realtime Voice")
            except ImportError:
                print("\033[91mERROR: Realtime UI is not installed.\033[0m")
                print('Install with: pip install "praisonai[ui]"')
                sys.exit(1)
            return

        if getattr(args, 'call', False):
            import importlib.util
            call_available = importlib.util.find_spec("praisonai.api.call") is not None
            if not call_available:
                print("[red]ERROR: Call feature is not installed. Install with:[/red]")
                print("\npip install \"praisonai[call]\"\n")
                return
            call_args = []
            if args.public:
                call_args.append('--public')
            _get_call_module().main(call_args)
            return

        if args.command == 'train':
            if not TRAIN_AVAILABLE:
                print("[red]ERROR: Training dependencies not installed. Install with:[/red]")
                print("\npip install \"praisonai[train]\"")
                print("Or run: praisonai train init\n")
                sys.exit(1)
            package_root = os.path.dirname(os.path.abspath(__file__))
            config_yaml_destination = os.path.join(os.getcwd(), 'config.yaml')

            if not os.path.exists(config_yaml_destination):
                config = _get_generate_config()(
                    model_name=args.model,
                    hf_model_name=args.hf,
                    ollama_model_name=args.ollama,
                    dataset=[{
                        "name": args.dataset
                    }]
                )
                with open('config.yaml', 'w') as f:
                    yaml.dump(config, f, default_flow_style=False, indent=2)
            elif args.model or args.hf or args.ollama or (args.dataset and args.dataset != "yahma/alpaca-cleaned"):
                config = _get_generate_config()(
                    model_name=args.model,
                    hf_model_name=args.hf,
                    ollama_model_name=args.ollama,
                    dataset=[{
                        "name": args.dataset
                    }]
                )
                with open('config.yaml', 'w') as f:
                    yaml.dump(config, f, default_flow_style=False, indent=2)
            else:
                with open(config_yaml_destination, 'r') as f:
                    config = yaml.safe_load(f)

            # Overwrite huggingface_save and ollama_save if --hf or --ollama are provided
            if args.hf:
                config["huggingface_save"] = "true"
            if args.ollama:
                config["ollama_save"] = "true"

            if 'init' in sys.argv:
                from praisonai_code._wrapper_bridge import import_wrapper_module
                _mod = import_wrapper_module('praisonai.setup.setup_conda_env')
                setup_conda_main = getattr(_mod, 'main')
                setup_conda_main()
                print("All packages installed")
                return

            # Check if conda is available and environment exists
            conda_available = True
            conda_env_exists = False
            
            try:
                result = subprocess.check_output(['conda', 'env', 'list'])
                if 'praison_env' in result.decode('utf-8'):
                    print("Conda environment 'praison_env' found.")
                    conda_env_exists = True
                else:
                    print("Conda environment 'praison_env' not found. Setting it up...")
                    from praisonai_code._wrapper_bridge import import_wrapper_module
                    _mod = import_wrapper_module('praisonai.setup.setup_conda_env')
                    setup_conda_main = getattr(_mod, 'main')
                    setup_conda_main()
                    print("All packages installed.")
                    # Check again if environment was created successfully
                    try:
                        result = subprocess.check_output(['conda', 'env', 'list'])
                        conda_env_exists = 'praison_env' in result.decode('utf-8')
                    except subprocess.CalledProcessError:
                        conda_env_exists = False
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("Conda not available or failed to check environment.")
                conda_available = False

            train_args = sys.argv[2:]  # Get all arguments after 'train'
            
            # Check if this is a vision model - handle all case variations
            model_name = config.get("model_name", "").lower()
            is_vision_model = any(x in model_name for x in ["-vl-", "-vl", "vl-", "-vision-", "-vision", "vision-", "visionmodel"])
            
            # Choose appropriate training script
            if is_vision_model:
                train_script_path = os.path.join(package_root, 'train_vision.py')
                print("Using vision training script for VL model...")
            else:
                train_script_path = os.path.join(package_root, 'train.py')
                print("Using standard training script...")

            # Set environment variables
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'

            # Try conda run first, fallback to direct Python execution
            if conda_available and conda_env_exists:
                try:
                    print("Attempting to run training using conda environment...")
                    stream_subprocess(['conda', 'run', '--no-capture-output', '--name', 'praison_env', 'python', '-u', train_script_path, 'train'], env=env)
                except subprocess.CalledProcessError as e:
                    print(f"Conda run failed with error: {e}")
                    print("Falling back to direct Python execution...")
                    stream_subprocess([sys.executable, '-u', train_script_path, 'train'], env=env)
            else:
                print("Conda environment not available, using direct Python execution...")
                stream_subprocess([sys.executable, '-u', train_script_path, 'train'], env=env)
            return

        if args.auto or self.auto:
            temp_topic = args.auto if args.auto else self.auto
            if isinstance(temp_topic, list):
                temp_topic = ' '.join(temp_topic)
            self.topic = temp_topic

            self.agent_file = "test.yaml"
            AutoGenerator = _get_auto_generator()
            generator = AutoGenerator(topic=self.topic, framework=self.framework, agent_file=self.agent_file)
            self.agent_file = generator.generate(merge=getattr(args, 'merge', False))
            AgentsGenerator = _get_agents_generator()
            # Extract CLI configuration for YAML CLI parity
            cli_config = self._extract_cli_config_for_yaml()
            agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list, cli_config=cli_config)
            result = agents_generator.generate_crew_and_kickoff()
            print(result)
            return result
        elif args.init or self.init:
            temp_topic = args.init if args.init else self.init
            if isinstance(temp_topic, list):
                temp_topic = ' '.join(temp_topic)
            self.topic = temp_topic

            self.agent_file = "agents.yaml"

            # Pre-flight: ensure an LLM provider credential is configured before
            # calling the LLM. Without this, a user with no API key (or a
            # non-OpenAI key for an OpenAI-default model) gets a raw stack trace
            # instead of clear, actionable guidance.
            import praisonai_code.cli.main as _cli_main
            preflight = _cli_main._provider_preflight_message()
            if preflight:
                print(preflight)
                return preflight

            AutoGenerator = _get_auto_generator()
            generator = AutoGenerator(topic=self.topic, framework=self.framework, agent_file=self.agent_file)
            self.agent_file = generator.generate(merge=getattr(args, 'merge', False))
            print(f"File {self.agent_file} created successfully")
            return f"File {self.agent_file} created successfully"

        if args.ui:
            if args.ui == "gradio":
                self.create_gradio_interface()
            elif args.ui == "chainlit":
                # Deprecation warning and route to new aiui agents interface
                print("\n\033[93mWARNING: --ui chainlit is deprecated and will be removed in a future release.\033[0m")
                print("Launching the new aiui-based agents interface instead...")
                self.create_aiui_agents_interface()
            else:
                # Modify code to allow default UI
                AgentsGenerator = _get_agents_generator()
                # Extract CLI configuration for YAML CLI parity
                cli_config = self._extract_cli_config_for_yaml()
                agents_generator = AgentsGenerator(
                    self.agent_file,
                    self.framework,
                    self.config_list,
                    agent_yaml=self.agent_yaml,
                    tools=self.tools,
                    cli_config=cli_config
                )
                result = agents_generator.generate_crew_and_kickoff()
                print(result)
                return result
        else:
            # n8n Integration - Export workflow to n8n and open in browser
            if getattr(args, 'n8n', False):
                from ..features.n8n import N8nHandler
                n8n_handler = N8nHandler(
                    verbose=getattr(args, 'verbose', False),
                    n8n_url=getattr(args, 'n8n_url', 'http://localhost:5678'),
                    api_url=getattr(args, 'api_url', None),
                    port=getattr(args, 'port', 8005)
                )
                result = n8n_handler.execute(self.agent_file)
                return result
            
            # Flow Display - Show flow diagram WITHOUT executing (--flow-display flag)
            if getattr(args, 'flow_display', False):
                from ..features.flow_display import FlowDisplayHandler
                flow_handler = FlowDisplayHandler(verbose=getattr(args, 'verbose', False))
                flow_handler.display_flow_diagram(self.agent_file)
                return  # Exit without executing
            
            # Always show flow diagram before execution (default behavior)
            try:
                from ..features.flow_display import FlowDisplayHandler
                flow_handler = FlowDisplayHandler(verbose=getattr(args, 'verbose', False))
                flow_handler.display_flow_diagram(self.agent_file, show_footer=False)
            except Exception:
                pass  # Continue even if flow display fails
            
            # Initialize trace variables for cleanup
            trace_writer = None
            trace_emitter = None
            trace_emitter_token = None
            
            # Get save flag for replay trace
            save_replay = getattr(args, 'save', False)
            
            # Initialize replay trace writer if --save flag is set
            import uuid
            run_id = f"run-{uuid.uuid4().hex[:12]}"
            if save_replay:
                try:
                    from praisonai_code._wrapper_bridge import import_wrapper_module
                    _mod = import_wrapper_module('praisonai.replay')
                    ContextTraceWriter = getattr(_mod, 'ContextTraceWriter')
                    from praisonaiagents.trace.context_events import ContextTraceEmitter, set_context_emitter
                    
                    trace_writer = ContextTraceWriter(session_id=run_id)
                    trace_emitter = ContextTraceEmitter(sink=trace_writer, session_id=run_id)
                    # Set as global emitter so agents can access it
                    trace_emitter_token = set_context_emitter(trace_emitter)
                    trace_emitter.session_start({"agents_file": self.agent_file, "run_id": run_id})
                    print(f"[cyan]📝 Replay trace enabled: {run_id}[/cyan]")
                except ImportError as e:
                    import logging
                    logging.debug(f"Replay module not available: {e}")
                except Exception as e:
                    import logging
                    logging.warning(f"Failed to initialize trace writer: {e}")
            
            try:
                AgentsGenerator = _get_agents_generator()
                # Extract CLI configuration for YAML CLI parity 
                cli_config = self._extract_cli_config_for_yaml()
                agents_generator = AgentsGenerator(
                    self.agent_file,
                    self.framework,
                    self.config_list,
                    agent_yaml=self.agent_yaml,
                    tools=self.tools,
                    cli_config=cli_config
                )
                result = agents_generator.generate_crew_and_kickoff()
                print(result)
                
                # Close trace writer on success
                if trace_emitter:
                    trace_emitter.session_end()
                    print(f"[cyan]📝 Replay trace saved: {run_id}[/cyan]")
                if trace_writer:
                    trace_writer.close()
                # Reset global emitter
                if trace_emitter_token:
                    from praisonaiagents.trace.context_events import reset_context_emitter
                    reset_context_emitter(trace_emitter_token)
                
                return result
            except Exception as e:
                # Cleanup trace on error
                if trace_emitter:
                    trace_emitter.session_end()
                if trace_writer:
                    trace_writer.close()
                if trace_emitter_token:
                    from praisonaiagents.trace.context_events import reset_context_emitter
                    reset_context_emitter(trace_emitter_token)
                raise

    def parse_args(self):
        """
        Parse the command-line arguments for the PraisonAI CLI.
        """
        # Seed availability flags so bare-name reads resolve even when this
        # method is reached directly (e.g. tests, library callers) rather than
        # through main(). Idempotent and cheap after the first call.
        _ensure_availability_flags()

        # Check if we're running in a test environment
        in_test_env = (
            'pytest' in sys.argv[0] or 
            'unittest' in sys.argv[0] or
            any(arg.startswith('tests.') or arg.startswith('tests/') for arg in sys.argv[1:3]) or  # Check for test module paths
            'PYTEST_CURRENT_TEST' in os.environ
        )
        
        # Check if we're being used as a library (not from praisonai CLI)
        # Skip CLI parsing to avoid conflicts with applications like Fabric
        is_library_usage = (
            'praisonai' not in sys.argv[0] and
            not in_test_env
        )
        
        if is_library_usage:
            # Return default args when used as library to prevent CLI conflicts
            default_args = argparse.Namespace()
            default_args.framework = None
            default_args.ui = None
            default_args.auto = None
            default_args.init = None
            default_args.command = None
            default_args.deploy = False
            default_args.schedule = None
            default_args.schedule_config = None
            default_args.provider = "gcp"
            default_args.max_retries = 3
            default_args.model = None
            default_args.llm = None
            default_args.hf = None
            default_args.ollama = None
            default_args.dataset = "yahma/alpaca-cleaned"
            default_args.realtime = False
            default_args.call = False
            default_args.public = False
            default_args.chat_mode = False
            default_args.include_rules = None
            default_args.no_rules = False
            return default_args
        
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _ab = import_wrapper_module("praisonai.cli.legacy.dispatch.argparse_builder")
        args, unknown_args, special_commands = _ab.build_argument_parser(in_test_env)

        # Handle special cases first
        if len(unknown_args) >= 2 and unknown_args[0] == '-b' and unknown_args[1] == 'api:app':
            args.command = 'agents.yaml'
        if args.command == 'api:app' or args.command == '/app/api:app':
            args.command = 'agents.yaml'
        if args.command == 'ui':
            # UI command — routes to Typer CLI for clean chat UI (praisonaiui)
            pass
        # chat and code commands are now terminal-native (handled by Typer commands)
        # Legacy --ui handling is preserved via the deprecation path above
        
        # Handle --claudecode flag for code command
        if getattr(args, 'claudecode', False):
            os.environ["PRAISONAI_CLAUDECODE_ENABLED"] = "true"
        if args.command == 'realtime':
            args.realtime = True
        if args.command == 'call':
            args.call = True
        if args.command == 'serve':
            args.serve = True

        # Handle serve command - start API server for agents
        if args.command == 'serve' or args.serve:
            self._handle_serve_command(args, unknown_args)
            sys.exit(0)

        # Handle ACP command - Agent Client Protocol server for IDE integration
        if args.command == 'acp':
            from ..features.acp import run_acp_command
            exit_code = run_acp_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle debug command - Debug and test interactive flows
        if args.command == 'debug':
            from ..features.debug import run_debug_command
            exit_code = run_debug_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle lsp command - LSP service lifecycle
        if args.command == 'lsp':
            from ..features.lsp_cli import run_lsp_command
            exit_code = run_lsp_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle diag command - Diagnostics export
        if args.command == 'diag':
            from ..features.diag import run_diag_command
            exit_code = run_diag_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle replay command - context replay for debugging agent execution
        if args.command == 'replay':
            from ..app import app as typer_app, register_commands
            register_commands()
            import sys as _sys
            _sys.argv = ['praisonai', 'replay'] + unknown_args
            try:
                typer_app()
            except SystemExit as e:
                sys.exit(e.code if e.code else 0)
            sys.exit(0)

        # Handle both command and flag versions for call
        if args.command == 'call' or args.call:
            import importlib.util
            if not importlib.util.find_spec("praisonai.api.call"):
                print("[red]ERROR: Call feature is not installed. Install with:[/red]")
                print("\npip install \"praisonai[call]\"\n")
                sys.exit(1)
            
            call_args = []
            if args.public:
                call_args.append('--public')
            _get_call_module().main(call_args)
            sys.exit(0)

        # Handle special commands
        if args.command in special_commands:
            # chat and code commands are now terminal-native (handled by Typer commands)
            # They no longer open Chainlit browser UI
            if args.command == 'chat':
                # Terminal-native chat mode
                self._start_interactive_mode(args)
                sys.exit(0)

            elif args.command == 'code':
                # Terminal-native code mode
                os.environ["PRAISONAI_CODE_MODE"] = "true"
                self._start_interactive_mode(args)
                sys.exit(0)


            elif args.command == 'realtime':
                try:
                    from praisonai_code._wrapper_bridge import import_wrapper_module
                    _mod = import_wrapper_module('praisonai.cli.commands.ui')
                    _launch_aiui_app = getattr(_mod, '_launch_aiui_app')
                    _launch_aiui_app("ui_realtime", "ui_realtime", 8085, "127.0.0.1", None, False, "Realtime Voice")
                except ImportError:
                    print("\033[91mERROR: Realtime UI is not installed.\033[0m")
                    print('Install with: pip install "praisonai[ui]"')
                    sys.exit(1)
                sys.exit(0)

            elif args.command == 'train':
                if not TRAIN_AVAILABLE:
                    print("[red]ERROR: Training dependencies not installed. Install with:[/red]")
                    print("\npip install \"praisonai[train]\"")
                    print("Or run: praisonai train init\n")
                    sys.exit(1)
                package_root = os.path.dirname(os.path.abspath(__file__))
                config_yaml_destination = os.path.join(os.getcwd(), 'config.yaml')

            elif args.command == 'ui':
                # UI command — Clean Chat UI (praisonaiui)
                # Routes to Typer CLI for ui command (launches clean chat)
                from ..app import app as typer_app, register_commands
                register_commands()
                import sys as _sys
                _sys.argv = ['praisonai', 'ui'] + unknown_args
                try:
                    typer_app()
                except SystemExit as e:
                    sys.exit(e.code if e.code else 0)
                sys.exit(0)

            elif args.command == 'context':
                self._require_agents()
                
                if not args.url:
                    print("[red]ERROR: --url is required for context command[/red]")
                    print("Usage: praisonai context --url <repository_url> --goal <goal> [--auto-analyze]")
                    sys.exit(1)
                
                if not args.goal:
                    print("[red]ERROR: --goal is required for context command[/red]")
                    print("Usage: praisonai context --url <repository_url> --goal <goal> [--auto-analyze]")
                    sys.exit(1)
                
                self.handle_context_command(args.url, args.goal, getattr(args, 'auto_analyze', False))
                sys.exit(0)

            elif args.command == 'research':
                self._require_agents()
                
                # Get the research query from remaining args
                research_query = ' '.join(unknown_args) if unknown_args else None
                if not research_query:
                    print("[red]ERROR: Research query is required[/red]")
                    print("Usage: praisonai research \"Your research query\"")
                    print("       praisonai research --model deep-research-pro \"Your query\"")
                    sys.exit(1)
                
                research_model = getattr(args, 'model', None)
                verbose = getattr(args, 'verbose', False)
                save = getattr(args, 'save', False)
                query_rewrite = getattr(args, 'query_rewrite', False)
                rewrite_tools = getattr(args, 'rewrite_tools', None)
                tools_path = getattr(args, 'tools', None)
                self.handle_research_command(research_query, research_model, verbose, save, query_rewrite, tools_path, rewrite_tools)
                sys.exit(0)

            elif args.command == 'memory':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'help'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                user_id = getattr(args, 'user_id', None)
                self.handle_memory_command(action, action_args, user_id)
                sys.exit(0)

            elif args.command == 'rules':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_rules_command(action, action_args)
                sys.exit(0)

            elif args.command == 'workflow':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                workflow_vars = {}
                if getattr(args, 'workflow_var', None):
                    for var in args.workflow_var:
                        if '=' in var:
                            key, value = var.split('=', 1)
                            workflow_vars[key] = value
                self.handle_workflow_command(action, action_args, workflow_vars, args)
                sys.exit(0)

            elif args.command == 'hooks':
                self._require_agents()
                
                # Get action from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                self.handle_hooks_command(action)
                sys.exit(0)

            elif args.command == 'knowledge':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'help'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_knowledge_command(action, action_args)
                sys.exit(0)

            elif args.command == 'session':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_session_command(action, action_args)
                sys.exit(0)

            elif args.command == 'tools':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_tools_command(action, action_args)
                sys.exit(0)

            elif args.command == 'todo':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_todo_command(action, action_args)
                sys.exit(0)

            elif args.command == 'docs':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_docs_command(action, action_args)
                sys.exit(0)

            elif args.command == 'mcp':
                self._require_agents()
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_mcp_command(action, action_args)
                sys.exit(0)

            elif args.command == 'commit':
                self._require_agents()
                
                self.handle_commit_command(unknown_args)
                sys.exit(0)

            elif args.command == 'skills':
                self._require_agents()
                
                from ..features.skills import handle_skills_command, add_skills_parser
                
                # Create a parser for skills command
                skills_parser = argparse.ArgumentParser(prog="praisonai skills")
                skills_subparsers = skills_parser.add_subparsers(dest='skills_command', help='Skills commands')
                add_skills_parser(skills_subparsers)
                skills_args = skills_parser.parse_args(unknown_args)
                
                exit_code = handle_skills_command(skills_args)
                sys.exit(exit_code)
            
            elif args.command == 'profile':
                # Profile command - delegate to Typer CLI for new profiler
                # This routes to commands/profile.py which has query, imports, startup subcommands
                from ..app import app as typer_app, register_commands
                register_commands()
                import sys as _sys
                _sys.argv = ['praisonai', 'profile'] + unknown_args
                typer_app()
                sys.exit(0)
            
            elif args.command == 'eval':
                # Eval command - evaluate model responses against expected outputs
                from ..features.eval import handle_eval_command
                exit_code = handle_eval_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'audit':
                # Audit command - agent-centric compliance auditing
                from ..commands.audit import audit as audit_cli
                import click
                # Parse subcommand and args
                if unknown_args and unknown_args[0] == 'agent-centric':
                    # Build click args
                    click_args = unknown_args[1:]
                    try:
                        audit_cli.main(['agent-centric'] + click_args, standalone_mode=False)
                    except click.exceptions.Exit as e:
                        sys.exit(e.exit_code)
                    except SystemExit as e:
                        sys.exit(e.code if e.code else 0)
                else:
                    print("Usage: praisonai audit agent-centric [--scan|--fix|--check] PATH")
                    print("\nOptions:")
                    print("  --scan PATH      Scan path for compliance")
                    print("  --fix PATH       Fix non-compliant files")
                    print("  --check PATH     Check and fail if non-compliant")
                    print("  --json           Output as JSON")
                    print("  --line-limit N   Line limit for header scan (default: 40)")
                    print("  --verbose, -v    Verbose output")
                sys.exit(0)
            
            elif args.command == 'templates':
                # Templates command - manage and run templates/recipes
                from ..features.templates import handle_templates_command
                exit_code = handle_templates_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'recipe':
                # Recipe command - new unified recipe system
                # Re-inject flags consumed by main parser into unknown_args for recipe handler
                recipe_args = list(unknown_args)
                if getattr(args, 'save', False) and '--save' not in recipe_args:
                    recipe_args.append('--save')
                if getattr(args, 'verbose', False) and '--verbose' not in recipe_args:
                    recipe_args.append('--verbose')
                if getattr(args, 'profile', False) and '--profile' not in recipe_args:
                    recipe_args.append('--profile')
                if getattr(args, 'profile_deep', False) and '--deep-profile' not in recipe_args:
                    recipe_args.append('--deep-profile')
                # Re-inject memory flag for judge command (consumed by main parser)
                if getattr(args, 'memory', False) and '--memory' not in recipe_args:
                    recipe_args.append('--memory')
                from ..features.recipe import handle_recipe_command
                exit_code = handle_recipe_command(recipe_args)
                sys.exit(exit_code)
            
            elif args.command == 'endpoints':
                # Endpoints command - unified client CLI for all server types
                from ..features.endpoints import handle_endpoints_command
                exit_code = handle_endpoints_command(unknown_args)
                sys.exit(exit_code)
            
            
            elif args.command == 'agents':
                # Agents command - run multiple agents with custom definitions
                self._require_agents()
                
                from ..features.agents import handle_agents_command, add_agents_parser
                
                # Create a parser for agents command
                agents_parser = argparse.ArgumentParser(prog="praisonai agents")
                agents_subparsers = agents_parser.add_subparsers(dest='agents_command', help='Agents commands')
                add_agents_parser(agents_subparsers)
                agents_args = agents_parser.parse_args(unknown_args)
                
                exit_code = handle_agents_command(agents_args)
                sys.exit(exit_code)
            
            elif args.command == 'run':
                # Run command - async jobs API for long-running tasks
                from ..features.jobs import handle_run_command
                handle_run_command(unknown_args, verbose=getattr(args, 'verbose', False))
                sys.exit(0)
            
            elif args.command == 'managed':
                # Managed agents — delegate to Typer app
                from ..commands.managed import app as managed_app
                managed_app(unknown_args)
                sys.exit(0)
            
            elif args.command == 'thinking':
                # Thinking command - manage thinking budgets
                from ..features.thinking import handle_thinking_command
                exit_code = handle_thinking_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'compaction':
                # Compaction command - manage context compaction
                from ..features.compaction import handle_compaction_command
                exit_code = handle_compaction_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'output':
                # Output command - manage output styles
                from ..features.output_style import handle_output_command
                exit_code = handle_output_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'deploy':
                # Deploy command - deploy agents as API/Docker/Cloud
                from ..features.deploy import DeployHandler
                handler = DeployHandler()
                
                # Parse deploy subcommand from unknown_args
                if unknown_args:
                    subcommand = unknown_args[0] if unknown_args else None
                    sub_args = unknown_args[1:] if len(unknown_args) > 1 else []
                    
                    # Create args namespace for handler
                    import argparse as ap
                    deploy_args = ap.Namespace()
                    # Use file from main args if provided, otherwise default
                    deploy_args.file = getattr(args, 'file', None) or 'agents.yaml'
                    deploy_args.all = False
                    deploy_args.verbose = False
                    deploy_args.background = False
                    deploy_args.yes = False
                    deploy_args.force = False
                    deploy_args.provider = getattr(args, 'provider', None)
                    deploy_args.type = None
                    deploy_args.background = False
                    
                    # Parse sub_args (may override main args)
                    i = 0
                    while i < len(sub_args):
                        arg = sub_args[i]
                        if arg in ['--file', '-f'] and i + 1 < len(sub_args):
                            deploy_args.file = sub_args[i + 1]
                            i += 2
                        elif arg == '--json':
                            deploy_args.json = True
                            i += 1
                        elif arg == '--verbose':
                            deploy_args.verbose = True
                            i += 1
                        elif arg == '--all':
                            deploy_args.all = True
                            i += 1
                        elif arg == '--provider' and i + 1 < len(sub_args):
                            deploy_args.provider = sub_args[i + 1]
                            i += 2
                        elif arg == '--type' and i + 1 < len(sub_args):
                            deploy_args.type = sub_args[i + 1]
                            i += 2
                        elif arg == '--background':
                            deploy_args.background = True
                            i += 1
                        elif arg in ['--yes', '-y']:
                            deploy_args.yes = True
                            i += 1
                        elif arg == '--force':
                            deploy_args.force = True
                            i += 1
                        else:
                            i += 1
                    
                    if subcommand == 'doctor':
                        handler.handle_doctor(deploy_args)
                    elif subcommand == 'init':
                        handler.handle_init(deploy_args)
                    elif subcommand == 'validate':
                        handler.handle_validate(deploy_args)
                    elif subcommand == 'plan':
                        handler.handle_plan(deploy_args)
                    elif subcommand == 'status':
                        handler.handle_status(deploy_args)
                    elif subcommand == 'destroy':
                        handler.handle_destroy(deploy_args)
                    elif subcommand == 'run' or subcommand in ['api', 'docker', 'cloud']:
                        if subcommand in ['api', 'docker', 'cloud']:
                            deploy_args.type = subcommand
                        handler.handle_deploy(deploy_args)
                    else:
                        print(f"Unknown deploy subcommand: {subcommand}")
                        print("Available: doctor, init, validate, plan, status, destroy, run, api, docker, cloud")
                        sys.exit(1)
                else:
                    # No subcommand - show help
                    print("Deploy commands:")
                    print("  praisonai deploy doctor [--all] [--provider aws|azure|gcp] [--json]")
                    print("  praisonai deploy init [--file FILE] [--type api|docker|cloud]")
                    print("  praisonai deploy validate [--file FILE] [--json]")
                    print("  praisonai deploy plan [--file FILE] [--json]")
                    print("  praisonai deploy status [--file FILE] [--json] [--verbose]")
                    print("  praisonai deploy destroy [--file FILE] [--yes] [--force] [--json]")
                    print("  praisonai deploy run [--file FILE] [--type api|docker|cloud] [--provider aws|azure|gcp]")
                    print("  praisonai deploy api [--file FILE]")
                    print("  praisonai deploy docker [--file FILE]")
                    print("  praisonai deploy cloud --provider aws|azure|gcp [--file FILE]")
                sys.exit(0)
            
            # Capabilities CLI commands
            elif args.command in ['audio', 'embed', 'embedding', 'images', 'moderate', 'files', 'batches', 
                                  'vector-stores', 'rerank', 'ocr', 'assistants', 'fine-tuning',
                                  'completions', 'messages', 'guardrails', 'rag', 'videos',
                                  'a2a', 'containers', 'passthrough', 'responses', 'search',
                                  'realtime-api']:
                from ..features.capabilities import CapabilitiesHandler
                
                cmd_map = {
                    'audio': CapabilitiesHandler.handle_audio,
                    'embed': CapabilitiesHandler.handle_embed,
                    'embedding': CapabilitiesHandler.handle_embed,  # Alias for embed
                    'images': CapabilitiesHandler.handle_images,
                    'moderate': CapabilitiesHandler.handle_moderate,
                    'files': CapabilitiesHandler.handle_files,
                    'batches': CapabilitiesHandler.handle_batches,
                    'vector-stores': CapabilitiesHandler.handle_vector_stores,
                    'rerank': CapabilitiesHandler.handle_rerank,
                    'ocr': CapabilitiesHandler.handle_ocr,
                    'assistants': CapabilitiesHandler.handle_assistants,
                    'fine-tuning': CapabilitiesHandler.handle_fine_tuning,
                    'completions': CapabilitiesHandler.handle_completions,
                    'messages': CapabilitiesHandler.handle_messages,
                    'guardrails': CapabilitiesHandler.handle_guardrails,
                    'rag': CapabilitiesHandler.handle_rag,
                    'videos': CapabilitiesHandler.handle_videos,
                    'a2a': CapabilitiesHandler.handle_a2a,
                    'containers': CapabilitiesHandler.handle_containers,
                    'passthrough': CapabilitiesHandler.handle_passthrough,
                    'responses': CapabilitiesHandler.handle_responses,
                    'search': CapabilitiesHandler.handle_search,
                    'realtime-api': CapabilitiesHandler.handle_realtime,
                }
                
                handler = cmd_map.get(args.command)
                if handler:
                    try:
                        exit_code = handler(args, unknown_args)
                    except ImportError as e:
                        print(f"ERROR: {e}")
                        sys.exit(1)
                    sys.exit(exit_code if exit_code else 0)
            
            elif args.command == 'doctor':
                # Doctor command - comprehensive health checks and diagnostics
                from ..features.doctor.handler import DoctorHandler
                handler = DoctorHandler()
                exit_code = handler.run(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'browser':
                # Browser agent command - delegate to browser CLI Typer app
                # Uses sys.argv replacement for proper arg passthrough (matches profile command pattern)
                from praisonai_code._wrapper_bridge import import_wrapper_module
                _mod = import_wrapper_module('praisonai.browser.cli')
                browser_app = getattr(_mod, 'app')
                import sys as _sys
                _sys.argv = ['praisonai', 'browser'] + unknown_args
                try:
                    browser_app()
                except SystemExit as e:
                    sys.exit(e.code if e.code else 0)
                sys.exit(0)
            
            
            elif args.command == 'claw':
                # Claw command - 🦞 PraisonAI Dashboard (full UI)
                # Routes to Typer CLI for claw command (launches AIUI dashboard)
                from ..app import app as typer_app, register_commands
                register_commands()
                import sys as _sys
                _sys.argv = ['praisonai', 'claw'] + unknown_args
                try:
                    typer_app()
                except SystemExit as e:
                    sys.exit(e.code if e.code else 0)
                sys.exit(0)

            elif args.command in ('flow', 'dashboard'):
                # Flow/Dashboard commands - delegate to Typer CLI
                from ..app import app as typer_app, register_commands
                register_commands()
                import sys as _sys
                _sys.argv = ['praisonai', args.command] + unknown_args
                try:
                    typer_app()
                except SystemExit as e:
                    sys.exit(e.code if e.code else 0)
                sys.exit(0)
            
            elif args.command == 'registry':
                # Registry command - manage recipe registry server
                from ..features.registry import RegistryHandler
                handler = RegistryHandler()
                exit_code = handler.handle(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'package':
                # Package command - pip-like package management
                from ..features.package import PackageHandler
                handler = PackageHandler()
                exit_code = handler.handle(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'install':
                # Install command - shortcut for package install
                from ..features.package import PackageHandler
                handler = PackageHandler()
                exit_code = handler.cmd_install(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'uninstall':
                # Uninstall command - shortcut for package uninstall
                from ..features.package import PackageHandler
                handler = PackageHandler()
                exit_code = handler.cmd_uninstall(unknown_args)
                sys.exit(exit_code)
            
            elif args.command in ('gateway', 'bot'):
                from praisonai_code._wrapper_bridge import import_wrapper_module
                _ld = import_wrapper_module("praisonai.cli.legacy.dispatch.legacy_dispatch")
                exit_code = _ld.run_wrapper_feature(args.command, self, args, unknown_args)
                sys.exit(exit_code if exit_code is not None else 1)
            
            elif args.command == 'sandbox':
                # Sandbox command - secure code execution environment
                from ..features.sandbox_cli import handle_sandbox_command
                exit_code = handle_sandbox_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'wizard':
                # Wizard command - interactive project setup
                from ..features.wizard import handle_wizard_command
                exit_code = handle_wizard_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'migrate':
                # Migrate command - config migration between formats
                from ..features.migrate import handle_migrate_command
                exit_code = handle_migrate_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'security':
                # Security command - security audit and scanning
                from ..features.audit_cli import handle_audit_command
                exit_code = handle_audit_command(unknown_args)
                sys.exit(exit_code)

            elif args.command == 'paths':
                # Paths command - storage path inspection
                # Routes to Typer CLI for paths commands (show)
                from ..app import app as typer_app, register_commands
                register_commands()
                import sys as _sys
                _sys.argv = ['praisonai', 'paths'] + unknown_args
                try:
                    typer_app()
                except SystemExit as e:
                    sys.exit(e.code if e.code else 0)
                sys.exit(0)

        # Only check framework availability for agent-related operations
        if not args.command and (args.init or args.auto or args.framework):
            try:
                list_framework_choices = _fw_registry_module().list_framework_choices
                if not list_framework_choices():
                    print("[red]ERROR: No framework adapter is installed.[/red]")
                    print("\npip install praisonaiagents  # native PraisonAI")
                    print("pip install \"praisonai-frameworks[crewai]\"  # CrewAI")
                    print("pip install \"praisonai-frameworks[autogen]\"  # AutoGen")
                    print("pip install \"praisonai-frameworks[openai-agents]\"  # OpenAI Agents SDK")
                    print("pip install \"praisonai-frameworks[agno]\"  # Agno")
                    print("pip install \"praisonai-frameworks[google-adk]\"  # Google ADK\n")
                    sys.exit(1)
            except ImportError:
                if not CREWAI_AVAILABLE and not AUTOGEN_AVAILABLE and not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: No framework is installed. Please install at least one framework:[/red]")
                    print("\npip install \"praisonai-frameworks\\[crewai]\"  # For CrewAI")
                    print("pip install \"praisonai-frameworks\\[autogen]\"  # For AutoGen")
                    print("pip install \"praisonai-frameworks\\[openai-agents]\"  # OpenAI Agents SDK")
                    print("pip install \"praisonai-frameworks\\[agno]\"  # Agno")
                    print("pip install \"praisonai-frameworks\\[google-adk]\"  # Google ADK")
                    print("pip install \"praisonai-frameworks\\[crewai,autogen]\"  # Multiple frameworks\n")
                    print("pip install praisonaiagents # For Agents\n")
                    sys.exit(1)

        # Handle direct prompt if command is not a special command or file
        # Skip this during testing to avoid pytest arguments interfering
        # A bare positional is treated as a one-shot prompt unless it is an
        # existing file or a YAML agent-file path (case-insensitive .yaml/.yml).
        if (
            not in_test_env
            and args.command
            and args.command not in special_commands
            and not os.path.isfile(args.command)
            and not args.command.lower().endswith((".yaml", ".yml"))
        ):
            args.direct_prompt = args.command
            args.command = None

        return args, unknown_args







    def handle_session_command(self, action: str, action_args: list):
        """
        Handle session subcommand actions.
        
        Args:
            action: The session action (start, list, resume, delete, info)
            action_args: Additional arguments for the action
        """
        try:
            from ..features.session import SessionHandler
            handler = SessionHandler(verbose=True)
            handler.execute(action, action_args)
        except ImportError as e:
            print(f"[red]ERROR: Failed to import session module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Session command failed: {e}[/red]")

    def handle_tools_command(self, action: str, action_args: list):
        """
        Handle tools subcommand actions.
        
        Args:
            action: The tools action (list, info, search)
            action_args: Additional arguments for the action
        """
        try:
            from ..features.tools import ToolsHandler
            handler = ToolsHandler(verbose=True)
            handler.execute(action, action_args)
        except ImportError as e:
            print(f"[red]ERROR: Failed to import tools module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Tools command failed: {e}[/red]")

    def handle_todo_command(self, action: str, action_args: list):
        """
        Handle todo subcommand actions.
        
        Args:
            action: The todo action (list, add, complete, delete, clear)
            action_args: Additional arguments for the action
        """
        try:
            from ..features.todo import TodoHandler
            handler = TodoHandler(verbose=True)
            handler.execute(action, action_args)
        except ImportError as e:
            print(f"[red]ERROR: Failed to import todo module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Todo command failed: {e}[/red]")






    def _run_inline_workflow(self, initial_prompt):
        """
        Run an inline workflow without a .md template file.
        
        Format: --workflow "step1:action1,step2:action2"
        Or: --workflow "Research,Write Blog" (uses prompt as context)
        
        Args:
            initial_prompt: The initial prompt/context for the workflow
            
        Returns:
            Final output from the workflow
        """
        from praisonaiagents import Agent as PraisonAgent
        from rich import print
        
        workflow_str = self.args.workflow
        
        # Parse workflow steps
        steps = []
        for step_def in workflow_str.split(","):
            step_def = step_def.strip()
            if ":" in step_def:
                name, action = step_def.split(":", 1)
                steps.append({"name": name.strip(), "action": action.strip()})
            else:
                # Just a step name, use it as both name and action
                steps.append({"name": step_def, "action": step_def})
        
        if not steps:
            print("[red]ERROR: No workflow steps defined[/red]")
            return ""
        
        # Use global flags (--llm, --tools, --planning, --memory, --save, --verbose)
        workflow_llm = getattr(self.args, 'llm', None)
        workflow_tools_str = getattr(self.args, 'tools', None)
        workflow_planning = getattr(self.args, 'planning', False)
        workflow_verbose = getattr(self.args, 'verbose', False)
        workflow_memory = getattr(self.args, 'memory', False)
        workflow_save = getattr(self.args, 'save', False)
        
        # Load tools
        workflow_tools = None
        if workflow_tools_str:
            workflow_tools = self._load_tools(workflow_tools_str)
            if workflow_tools:
                print(f"[cyan]Loaded {len(workflow_tools)} tool(s) for workflow[/cyan]")
        
        # Initialize memory if enabled (memory will be passed to agent when supported)
        if workflow_memory:
            print("[cyan]Memory enabled for workflow (shared across steps)[/cyan]")
        
        print(f"[bold cyan]Running inline workflow with {len(steps)} steps[/bold cyan]")
        if workflow_planning:
            print("[cyan]Planning mode enabled[/cyan]")
        
        # Execute workflow steps sequentially with context passing
        context = initial_prompt
        results = []
        
        for i, step in enumerate(steps):
            step_name = step["name"]
            step_action = step["action"]
            
            print(f"[cyan]  → Step {i+1}: {step_name}[/cyan]")
            
            # Build prompt with context
            if i == 0:
                full_prompt = f"{step_action}\n\nContext:\n{context}"
            else:
                full_prompt = f"{step_action}\n\nContext from previous steps:\n{context}"
            
            # Create agent for this step
            agent = PraisonAgent(
                name=f"{step_name}Agent",
                role=step_name,
                goal=step_action,
                llm=workflow_llm,
                tools=workflow_tools,
                verbose=1 if workflow_verbose else 0
            )
            
            try:
                output = agent.chat(full_prompt)
                results.append({"step": step_name, "status": "success", "output": output})
                context = output  # Pass output to next step
                print(f"[green]  ✓ Completed: {step_name}[/green]")
            except Exception as e:
                results.append({"step": step_name, "status": "failed", "error": str(e)})
                print(f"[red]  ✗ Failed: {step_name} - {e}[/red]")
                break
        
        # Show final output
        if results:
            last_output = results[-1].get("output", "")
            if last_output:
                print("\n[bold]Final Output:[/bold]")
                print(last_output[:2000] + "..." if len(last_output) > 2000 else last_output)
            
            # Save if requested
            if workflow_save:
                from datetime import datetime
                output_dir = os.path.join(os.getcwd(), "output", "workflows")
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                output_file = os.path.join(output_dir, f"{timestamp}_inline_workflow.md")
                
                with open(output_file, "w") as f:
                    f.write("# Inline Workflow\n\n")
                    f.write(f"**Executed:** {timestamp}\n\n")
                    f.write(f"**Initial Prompt:** {initial_prompt}\n\n")
                    for step_result in results:
                        f.write(f"## {step_result.get('step', 'Unknown')}\n\n")
                        f.write(f"**Status:** {step_result.get('status', 'unknown')}\n\n")
                        if step_result.get("output"):
                            f.write(f"{step_result['output']}\n\n")
                
                print(f"\n[green]✅ Output saved to: {output_file}[/green]")
        
        return results[-1].get("output", "") if results else ""

    def _execute_agent_with_budget_handling(self, agent, method_name, *args, **kwargs):
        """Run ``agent.<method_name>(*args, **kwargs)`` with a graceful
        BudgetExceededError handler.

        Wrapper-only fix (no core SDK changes). Users configure budgets via
        ``execution=ExecutionConfig(max_budget=...)`` on the Agent — per
        AGENTS.md §5.3 there is NO top-level ``max_budget=`` parameter on
        Agent.__init__ (avoids parameter bloat).

        When the budget is hit this prints a single-line actionable error
        message and exits with code 1 instead of leaking a raw traceback.
        Any other exception is re-raised unchanged.
        """
        from praisonaiagents.errors import BudgetExceededError
        try:
            return getattr(agent, method_name)(*args, **kwargs)
        except BudgetExceededError as e:
            from rich import print as rich_print
            rich_print(
                f"[red]Budget limit exceeded: {e!s}. "
                "Hint: set budget via "
                "execution=ExecutionConfig(max_budget=1.00) on your Agent.[/red]"
            )
            sys.exit(1)

    def _extract_cli_config_for_yaml(self):
        """
        Extract CLI configuration that should be passed to YAML processing.
        
        Returns:
            dict: CLI configuration for the missing CLI parity features
        """
        if not hasattr(self, 'args'):
            return {}
            
        cli_config = {}
        
        # Extract --trust flag
        if getattr(self.args, 'trust', False):
            cli_config['trust'] = True
            
        # Extract --tool-timeout flag  
        tool_timeout = getattr(self.args, 'tool_timeout', None)
        if tool_timeout is not None:
            cli_config['tool_timeout'] = tool_timeout
        
        # Extract --tool-retry-* flags for retry policy
        retry_attempts = getattr(self.args, 'tool_retry_attempts', 3)
        retry_delay = getattr(self.args, 'tool_retry_delay', 1000)
        retry_backoff = getattr(self.args, 'tool_retry_backoff', 2.0)
        retry_on_str = getattr(self.args, 'tool_retry_on', "timeout,rate_limit,connection_error")
        retry_on = set(error_type.strip() for error_type in retry_on_str.split(',') if error_type.strip())
        
        if retry_attempts > 1:  # Only create retry policy if retries are enabled
            from praisonaiagents.tools.retry import RetryPolicy
            cli_config['tool_retry_policy'] = RetryPolicy(
                max_attempts=retry_attempts,
                initial_delay_ms=retry_delay,
                backoff_factor=retry_backoff,
                retry_on=retry_on
            )
            
        # Extract --planning-tools flag
        planning_tools = getattr(self.args, 'planning_tools', None)
        if planning_tools:
            cli_config['planning_tools'] = planning_tools

        # Extract --planning flag
        if getattr(self.args, 'planning', False):
            cli_config['planning'] = True

        # Extract web flags
        if getattr(self.args, 'web', False):
            cli_config['web'] = True
        if getattr(self.args, 'web_fetch', False):
            cli_config['web_fetch'] = True
            
        # Extract --acp flag
        if getattr(self.args, 'acp', False):
            cli_config['acp'] = True
            
        # Extract --lsp flag
        if getattr(self.args, 'lsp', False):
            cli_config['lsp'] = True
            
        # Extract new agent-level CLI flags for YAML parity
        autonomy = getattr(self.args, 'autonomy', None)
        if autonomy is not None:
            cli_config['autonomy'] = autonomy
            
        guardrail = getattr(self.args, 'guardrail', None)
        if guardrail is not None:
            cli_config['guardrail'] = guardrail
            
        approval = getattr(self.args, 'approval', None)
        if approval is not None:
            cli_config['approval'] = approval
            
        approve_all_tools = getattr(self.args, 'approve_all_tools', None)
        if approve_all_tools is not None:
            cli_config['approve_all_tools'] = approve_all_tools
            
        approval_timeout = getattr(self.args, 'approval_timeout', None)
        if approval_timeout is not None:
            cli_config['approval_timeout'] = approval_timeout
            
        # Extract streaming configuration for YAML CLI parity
        stream = getattr(self.args, 'stream', False)
        stream_metrics = getattr(self.args, 'stream_metrics', False)
        if stream or stream_metrics:
            cli_config['stream'] = stream or stream_metrics
            if stream_metrics:
                cli_config['stream_metrics'] = True

        # Extract handoff configuration for YAML CLI parity
        handoff = getattr(self.args, 'handoff', None)
        if handoff:
            cli_config['handoff'] = handoff

        handoff_policy = getattr(self.args, 'handoff_policy', None)
        if handoff_policy is not None:
            cli_config['handoff_policy'] = handoff_policy

        handoff_timeout = getattr(self.args, 'handoff_timeout', None)
        if handoff_timeout is not None:
            cli_config['handoff_timeout'] = handoff_timeout

        handoff_max_depth = getattr(self.args, 'handoff_max_depth', None)
        if handoff_max_depth is not None:
            cli_config['handoff_max_depth'] = handoff_max_depth

        handoff_max_concurrent = getattr(self.args, 'handoff_max_concurrent', None)
        if handoff_max_concurrent is not None:
            cli_config['handoff_max_concurrent'] = handoff_max_concurrent

        handoff_detect_cycles = getattr(self.args, 'handoff_detect_cycles', None)
        if handoff_detect_cycles is not None:
            cli_config['handoff_detect_cycles'] = handoff_detect_cycles

        if getattr(self.args, 'cli_project_sessions', False):
            from ..state.project_sessions import build_cli_memory_config
            memory_cfg = build_cli_memory_config(
                getattr(self.args, 'resume_session', None),
                getattr(self.args, 'auto_save', None),
            )
            if memory_cfg is not None:
                cli_config['memory'] = memory_cfg
            
        return cli_config


    def _handle_profiled_prompt(self, prompt):
        """
        Handle direct prompt with unified profiling enabled.
        
        Uses the unified execution module for consistent profiling across
        CLI direct invocation and profile command.
        """
        from .execution import ExecutionRequest, Profiler, ProfilerConfig
        
        # Build execution request
        model = None
        if hasattr(self, 'args') and self.args.llm:
            model = self.args.llm
        
        request = ExecutionRequest(
            prompt=prompt,
            agent_name="DirectAgent",
            model=model,
            stream=False,
        )
        
        # Create profiler config from flags
        deep = getattr(self.args, 'profile_deep', False)
        output_format = getattr(self.args, 'profile_format', 'text')
        
        config = ProfilerConfig(
            layer=2 if deep else 1,
            show_callers=deep,
            show_callees=deep,
            output_format=output_format,
        )
        
        # Run with profiling
        print("[bold cyan]🔬 Starting profiled execution...[/bold cyan]")
        if deep:
            print("[yellow]⚠️  Deep profiling enabled - higher overhead[/yellow]")
        
        profiler = Profiler(config)
        result, report = profiler.profile_sync(request, invocation_method="cli_direct")
        
        # Output profile report
        if output_format == "json":
            print(report.to_json())
        else:
            print(report.to_text())
        
        # Return the actual result for any downstream processing
        return result.output

    def _resolve_display_mode(self):
        """Map CLI flags to a display mode string.
        
        Priority: --output > --flow > --display (deprecated) > -v/-q > default.
        Returns one of: 'silent', 'quiet', 'verbose', 'debug', 'json', 'jsonl', 'flow', 'status', 'cursor'.
        """
        # Machine formats take highest priority
        output_fmt = getattr(self.args, 'output_format', None)
        if output_fmt:
            return output_fmt  # "json", "jsonl", or "cursor"
        
        # --flow is an independent feature flag
        if getattr(self.args, 'flow', False) or getattr(self.args, 'flow_display', False):
            return 'flow'
        
        # Check Typer global state (for Typer subcommands)
        try:
            from ..app import state as typer_state
            if typer_state.quiet:
                return 'quiet'
            if hasattr(typer_state, 'output_format'):
                if typer_state.output_format.value == 'json':
                    return 'json'
                elif typer_state.output_format.value == 'stream-json':
                    return 'jsonl'
            if typer_state.screen_reader:
                return 'verbose'  # Accessible: timestamps but no spinners
        except (ImportError, AttributeError):
            pass
        
        # Verbosity ladder: -v/-vv/-q/-qq
        v = getattr(self.args, 'verbose', 0)
        q = getattr(self.args, 'quiet', 0)
        if q >= 2:
            return 'silent'
        if q >= 1:
            return 'quiet'
        if v >= 2:
            return 'debug'
        if v >= 1:
            return 'verbose'
        
        return 'editor'  # Default: User-friendly editor-style output

    def _handle_serve_command(self, args, unknown_args):
        """
        Handle the serve command - start API server for agents.
        
        Supports:
        - Sequential workflows with agents and steps
        - Workflow patterns: route, parallel, loop, repeat
        - All process types: sequential, workflow, hierarchical
        
        Usage:
            praisonai serve agents.yaml
            praisonai serve agents.yaml --port 8005 --host 0.0.0.0
            praisonai agents.yaml --serve
        """
        import yaml
        from praisonaiagents import Agent, AgentTeam
        
        # Determine the YAML file path
        yaml_file = None
        
        # Check if command is 'serve' and there's a file in unknown_args
        if args.command == 'serve' and unknown_args:
            yaml_file = unknown_args[0]
        # Check if command itself is a yaml file (praisonai agents.yaml --serve)
        elif args.command and args.command.endswith('.yaml'):
            yaml_file = args.command
        # Default to agents.yaml
        else:
            yaml_file = 'agents.yaml'
        
        # Check if file exists
        if not os.path.exists(yaml_file):
            print(f"[red]ERROR: File not found: {yaml_file}[/red]")
            print("\nUsage:")
            print("  praisonai serve agents.yaml")
            print("  praisonai serve agents.yaml --port 8005")
            print("  praisonai agents.yaml --serve")
            sys.exit(1)
        
        print(f"📄 Loading workflow from: {yaml_file}")
        
        # Load YAML file
        with open(yaml_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Extract agents
        agents_config = config.get('agents', config.get('roles', {}))
        agents_dict = {}  # Map agent_id to Agent instance
        agents_list = []
        
        for agent_id, agent_config in agents_config.items():
            if isinstance(agent_config, dict):
                agent = Agent(
                    name=agent_config.get('name', agent_id.title()),
                    role=agent_config.get('role', ''),
                    goal=agent_config.get('goal', ''),
                    backstory=agent_config.get('backstory', ''),
                    instructions=agent_config.get('instructions', ''),
                    llm=agent_config.get('llm', 'gpt-4o-mini'), output="minimal"
                )
                agents_dict[agent_id] = agent
                agents_list.append(agent)
                print(f"  ✓ Loaded agent: {agent.name}")
        
        if not agents_list:
            print("[red]ERROR: No agents found in YAML file[/red]")
            sys.exit(1)
        
        # Extract tasks from steps (if defined)
        steps = config.get('steps', [])
        tasks_list = []
        
        # Detect advanced workflow patterns
        has_route = any(isinstance(s, dict) and 'route' in s for s in steps)
        has_parallel = any(isinstance(s, dict) and 'parallel' in s for s in steps)
        has_loop = any(isinstance(s, dict) and 'loop' in s for s in steps)
        has_repeat = any(isinstance(s, dict) and 'repeat' in s for s in steps)
        
        if has_route or has_parallel or has_loop or has_repeat:
            patterns = []
            if has_route: patterns.append("route")
            if has_parallel: patterns.append("parallel")
            if has_loop: patterns.append("loop")
            if has_repeat: patterns.append("repeat")
            print(f"\n🔀 Detected workflow patterns: {', '.join(patterns)}")
        
        if steps:
            from praisonaiagents import Task
            print(f"\n📋 Loading workflow steps...")
            
            # First pass: create all tasks
            task_name_map = {}  # Map step names to Task objects for context/next_tasks
            for i, step in enumerate(steps):
                if isinstance(step, dict):
                    # Handle advanced patterns
                    if 'route' in step:
                        print(f"  ✓ Loaded routing step: {step.get('name', f'route_{i+1}')}")
                        continue  # Route steps are handled by workflow process
                    if 'parallel' in step:
                        parallel_tasks = step.get('parallel', [])
                        print(f"  ✓ Loaded parallel step: {len(parallel_tasks)} concurrent tasks")
                        for j, pt in enumerate(parallel_tasks):
                            if isinstance(pt, dict):
                                agent_id = pt.get('agent', '')
                                action = pt.get('action', pt.get('description', ''))
                                if agent_id in agents_dict:
                                    task = Task(
                                        name=f"parallel_{i}_{j}",
                                        description=action,
                                        agent=agents_dict[agent_id],
                                        expected_output=pt.get('expected_output', 'Completed task output'),
                                        async_execution=True,  # Parallel tasks run async
                                    )
                                    tasks_list.append(task)
                                    task_name_map[f"parallel_{i}_{j}"] = task
                        continue
                    if 'loop' in step:
                        loop_config = step.get('loop', {})
                        print(f"  ✓ Loaded loop step: over '{loop_config.get('over', 'items')}'")
                        continue  # Loop steps are handled by workflow process
                    if 'repeat' in step:
                        repeat_config = step.get('repeat', {})
                        print(f"  ✓ Loaded repeat step: until '{repeat_config.get('until', 'done')}'")
                        continue  # Repeat steps are handled by workflow process
                    
                    # Standard step
                    agent_id = step.get('agent', '')
                    action = step.get('action', step.get('description', ''))
                    task_name = step.get('name', f"step_{i+1}")
                    
                    if agent_id in agents_dict:
                        task = Task(
                            name=task_name,
                            description=action,
                            agent=agents_dict[agent_id],
                            expected_output=step.get('expected_output', 'Completed task output'),
                            task_type=step.get('task_type', 'task'),
                            is_start=step.get('is_start', i == 0),
                            async_execution=step.get('async_execution', False),
                            output_file=step.get('output_file'),
                        )
                        tasks_list.append(task)
                        task_name_map[task_name] = task
                        print(f"  ✓ Loaded step {i+1}: {agent_id} → {action[:50]}...")
            
            # Second pass: set up next_tasks and context relationships
            for i, step in enumerate(steps):
                if isinstance(step, dict) and 'agent' in step:
                    task_name = step.get('name', f"step_{i+1}")
                    if task_name in task_name_map:
                        task = task_name_map[task_name]
                        
                        # Set next_tasks if specified
                        next_tasks = step.get('next_tasks', [])
                        if next_tasks:
                            task.next_tasks = next_tasks
                        
                        # Set context if specified
                        context_refs = step.get('context', [])
                        if context_refs:
                            task.context = [task_name_map[ref] for ref in context_refs if ref in task_name_map]
                        
                        # Set condition for workflow branching
                        condition = step.get('condition', {})
                        if condition:
                            task.condition = condition
        
        port = args.port
        host = args.host
        
        # Extract process type from workflow config (default: sequential)
        workflow_config = config.get('workflow', {})
        process_type = workflow_config.get('process', 'sequential')
        verbose = workflow_config.get('verbose', False)
        
        # Also check top-level process key
        if 'process' in config:
            process_type = config['process']
        
        print(f"\n🚀 Starting PraisonAI API server...")
        print(f"   Host: {host}")
        print(f"   Port: {port}")
        print(f"   Agents: {len(agents_list)}")
        if tasks_list:
            print(f"   Tasks: {len(tasks_list)}")
        print(f"   Process: {process_type}")
        
        # Create and launch - with tasks if defined
        if tasks_list:
            praison = AgentTeam(
                agents=agents_list, 
                tasks=tasks_list,
                process=process_type,
                verbose=1 if verbose else 0
            )
        else:
            praison = AgentTeam(
                agents=agents_list,
                process=process_type,
                verbose=1 if verbose else 0
            )
        praison.launch(port=port, host=host)
        
        # Keep the main thread alive to prevent exit
        print("\n✅ Server running. Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Server stopped.")

    def create_gradio_interface(self):
        """
        Create a Gradio interface for generating agents and performing tasks.
        """
        # Seed availability flags so bare-name reads resolve when invoked
        # directly rather than through main().
        _ensure_availability_flags()
        if GRADIO_AVAILABLE:
            # Lazy import gradio only when needed
            gr = _get_gradio()
            
            def generate_crew_and_kickoff_interface(auto_args, framework):
                self.framework = framework
                self.agent_file = "test.yaml"
                AutoGenerator = _get_auto_generator()
                generator = AutoGenerator(topic=auto_args, framework=self.framework)
                self.agent_file = generator.generate()
                AgentsGenerator = _get_agents_generator()
                # Extract CLI configuration for YAML CLI parity
                cli_config = self._extract_cli_config_for_yaml()
                agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list, cli_config=cli_config)
                result = agents_generator.generate_crew_and_kickoff()
                return result

            try:
                list_framework_choices = _fw_registry_module().list_framework_choices
                _gradio_frameworks = list_framework_choices(include_unavailable=True) or [
                    "crewai", "autogen", "praisonai",
                ]
            except ImportError:
                _gradio_frameworks = ["crewai", "autogen", "praisonai"]

            gr.Interface(
                fn=generate_crew_and_kickoff_interface,
                inputs=[
                    gr.Textbox(lines=2, label="Auto Args"),
                    gr.Dropdown(choices=_gradio_frameworks, label="Framework"),
                ],
                outputs="textbox",
                title="Praison AI Studio",
                description="Create Agents and perform tasks",
                theme="default"
            ).launch()
        else:
            print("ERROR: Gradio is not installed. Please install it with 'pip install gradio' to use this feature.")

    def create_aiui_agents_interface(self):
        """
        Create an aiui-based agents interface (replaces Chainlit).
        
        Routes to the new `praisonai ui agents` subcommand.
        """
        try:
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module('praisonai.cli.commands.ui')
            _launch_aiui_app = getattr(_mod, '_launch_aiui_app')
            print("🤖 Launching PraisonAI Agents Dashboard (aiui)...")
            _launch_aiui_app(
                app_dir="ui_agents",
                default_app_name="ui_agents",
                port=8082,  # Use same port as old Chainlit agents
                host="127.0.0.1",
                app_file=None,
                reload=False,
                ui_name="Agents Dashboard"
            )
        except ImportError:
            print("ERROR: PraisonAI UI (aiui) is not installed. Please install it with 'pip install \"praisonai[ui]\"' to use the agents dashboard.")

    def handle_memory_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_memory_command")(self, *args, **kwargs)

    def handle_rules_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_rules_command")(self, *args, **kwargs)

    def handle_hooks_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_hooks_command")(self, *args, **kwargs)

    def handle_knowledge_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_knowledge_command")(self, *args, **kwargs)

    def handle_docs_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_docs_command")(self, *args, **kwargs)

    def handle_mcp_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_mcp_command")(self, *args, **kwargs)

    def handle_commit_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_commit_command")(self, *args, **kwargs)

    def handle_context_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_context_command")(self, *args, **kwargs)

    def handle_research_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "handle_research_command")(self, *args, **kwargs)

    def _check_sensitive_content(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "_check_sensitive_content")(self, *args, **kwargs)

    def _clean_commit_message(self, raw: str):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "_clean_commit_message")(raw)

    def _get_sensitive_patterns(self):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.subcommand_handlers")
        return getattr(_mod, "_get_sensitive_patterns")()

    def handle_workflow_command(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.workflow_commands")
        return getattr(_mod, "handle_workflow_command")(self, *args, **kwargs)

    def _run_yaml_workflow(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.workflow_commands")
        return getattr(_mod, "_run_yaml_workflow")(self, *args, **kwargs)

    def _validate_yaml_workflow(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.workflow_commands")
        return getattr(_mod, "_validate_yaml_workflow")(self, *args, **kwargs)

    def _get_canonical_suggestions(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.workflow_commands")
        return getattr(_mod, "_get_canonical_suggestions")(self, *args, **kwargs)

    def _create_workflow_from_template(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.workflow_commands")
        return getattr(_mod, "_create_workflow_from_template")(self, *args, **kwargs)

    def _auto_generate_workflow(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.workflow_commands")
        return getattr(_mod, "_auto_generate_workflow")(self, *args, **kwargs)

    def _rewrite_query(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "_rewrite_query")(self, *args, **kwargs)

    def _rewrite_query_if_enabled(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "_rewrite_query_if_enabled")(self, *args, **kwargs)

    def _expand_prompt(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "_expand_prompt")(self, *args, **kwargs)

    def _expand_prompt_if_enabled(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "_expand_prompt_if_enabled")(self, *args, **kwargs)

    def _load_tools(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "_load_tools")(self, *args, **kwargs)

    def _load_toolsets(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "_load_toolsets")(self, *args, **kwargs)

    def _save_output(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "_save_output")(self, *args, **kwargs)

    def handle_direct_prompt(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.direct_prompt")
        return getattr(_mod, "handle_direct_prompt")(self, *args, **kwargs)

    def _start_interactive_mode(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.interactive_legacy")
        return getattr(_mod, "_start_interactive_mode")(self, *args, **kwargs)

    def _load_interactive_tools(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.interactive_legacy")
        return getattr(_mod, "_load_interactive_tools")(self, *args, **kwargs)

    def _run_chat_mode(self, *args, **kwargs):
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module("praisonai.cli.legacy.interactive_legacy")
        return getattr(_mod, "_run_chat_mode")(self, *args, **kwargs)


if __name__ == "__main__":
    from praisonai_code.cli._warnings import install_warning_filters
    install_warning_filters()
    praison_ai = PraisonAI()
    praison_ai.main()
