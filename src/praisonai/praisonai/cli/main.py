# praisonai/cli/main.py

import sys
import argparse
import warnings
import os

# Suppress Pydantic serialization warnings from LiteLLM BEFORE any imports
# These warnings occur when LiteLLM's response objects have field mismatches
# Using both filterwarnings AND patching warnings.warn for complete suppression

warnings.filterwarnings("ignore", message=".*Pydantic serializer warnings.*")
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")
warnings.filterwarnings("ignore", message=".*Expected \\d+ fields but got.*")
warnings.filterwarnings("ignore", message=".*Expected `StreamingChoices`.*")
warnings.filterwarnings("ignore", message=".*Expected `Message`.*")
warnings.filterwarnings("ignore", message=".*serialized value may not be as expected.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")

# Patch warnings.showwarning to intercept ALL warnings including those from crewai's patched warn
# This is the final output function that actually displays warnings
_SUPPRESSED_PATTERNS = [
    "Pydantic serializer warnings",
    "PydanticSerializationUnexpectedValue",
    "Expected",  # Catches "Expected N fields but got M"
    "StreamingChoices",
    "serialized value may not be as expected",
    "duckduckgo_search",  # Suppress duckduckgo rename warning
]

_original_showwarning = warnings.showwarning

def _patched_showwarning(message, category, filename, lineno, file=None, line=None):
    msg_str = str(message)
    for pattern in _SUPPRESSED_PATTERNS:
        if pattern in msg_str:
            return
    if category is UserWarning and "pydantic" in filename.lower():
        return
    _original_showwarning(message, category, filename, lineno, file, line)

warnings.showwarning = _patched_showwarning

# Suppress crewai RuntimeWarning about module loading order (only in non-debug mode)
# This warning is harmless and occurs when running as `python -m praisonai.cli.main`
if os.environ.get('LOGLEVEL', 'INFO').upper() != 'DEBUG':
    warnings.filterwarnings(
        "ignore",
        message=".*found in sys.modules after import of package.*",
        category=RuntimeWarning
    )

from praisonai.version import __version__
import yaml
import time
from rich import print
from dotenv import load_dotenv
load_dotenv()
import shutil
import subprocess
import logging
import importlib

# Lazy imports for performance - these are imported when needed, not at module load
# from praisonai.auto import AutoGenerator  # Lazy: imported in auto/init commands
# from praisonai.agents_generator import AgentsGenerator  # Lazy: imported when running agents
# REMOVED: from praisonai.inbuilt_tools import * - causes ~3200ms crewai import
# REMOVED: from praisonai.inc.config import generate_config - causes ~3500ms langchain import

# Lazy import helpers for inbuilt_tools and config
def _get_inbuilt_tools():
    """Lazy import inbuilt_tools only when crewai/autogen features are used."""
    from praisonai import inbuilt_tools
    return inbuilt_tools

def _get_generate_config():
    """Lazy import generate_config only when training features are used."""
    from praisonai.inc.config import generate_config
    return generate_config

# Lazy import helpers for heavy modules
def _get_auto_generator():
    """Lazy import AutoGenerator to avoid loading heavy deps at CLI startup."""
    from praisonai.auto import AutoGenerator
    return AutoGenerator

def _get_agents_generator():
    """Lazy import AgentsGenerator to avoid loading heavy deps at CLI startup."""
    from praisonai.agents_generator import AgentsGenerator
    return AgentsGenerator

# Optional module imports with availability checks
CHAINLIT_AVAILABLE = False
GRADIO_AVAILABLE = False
CALL_MODULE_AVAILABLE = False
CREWAI_AVAILABLE = False
AUTOGEN_AVAILABLE = False
PRAISONAI_AVAILABLE = False
TRAIN_AVAILABLE = False
try:
    import importlib.util
    CHAINLIT_AVAILABLE = importlib.util.find_spec("chainlit") is not None
except ImportError:
    pass

def _get_chainlit_run():
    """Lazy import chainlit to avoid loading .env at startup"""
    # Create necessary directories and set CHAINLIT_APP_ROOT
    if "CHAINLIT_APP_ROOT" not in os.environ:
        chainlit_root = os.path.join(os.path.expanduser("~"), ".praison")
        os.environ["CHAINLIT_APP_ROOT"] = chainlit_root
    else:
        chainlit_root = os.environ["CHAINLIT_APP_ROOT"]
        
    os.makedirs(chainlit_root, exist_ok=True)
    os.makedirs(os.path.join(chainlit_root, ".files"), exist_ok=True)
    
    from chainlit.cli import chainlit_run
    return chainlit_run

# Use find_spec for fast availability checks (no actual import)
import importlib.util
GRADIO_AVAILABLE = importlib.util.find_spec("gradio") is not None
try:
    CALL_MODULE_AVAILABLE = importlib.util.find_spec("praisonai.api.call") is not None
except (ModuleNotFoundError, AttributeError):
    CALL_MODULE_AVAILABLE = False
CREWAI_AVAILABLE = importlib.util.find_spec("crewai") is not None
AUTOGEN_AVAILABLE = importlib.util.find_spec("autogen") is not None
PRAISONAI_AVAILABLE = importlib.util.find_spec("praisonaiagents") is not None
TRAIN_AVAILABLE = importlib.util.find_spec("unsloth") is not None

# Lazy import helpers for optional dependencies (defined after availability flags)
def _get_call_module():
    """Lazy import call module only when call feature is used.
    
    Raises:
        ImportError: If praisonai.api.call is not installed
    """
    if not CALL_MODULE_AVAILABLE:
        raise ImportError(
            "Call feature is not installed. Install with: pip install \"praisonai[call]\""
        )
    from praisonai.api import call as call_module
    return call_module

def _get_gradio():
    """Lazy import gradio only when gradio UI is used.
    
    Raises:
        ImportError: If gradio is not installed
    """
    if not GRADIO_AVAILABLE:
        raise ImportError(
            "Gradio is not installed. Install with: pip install gradio"
        )
    import gradio as gr
    return gr

def _get_autogen():
    """Lazy import autogen only when autogen framework is used.
    
    Raises:
        ImportError: If autogen is not installed
    """
    if not AUTOGEN_AVAILABLE:
        raise ImportError(
            "AutoGen is not installed. Install with: pip install \"praisonai[autogen]\""
        )
    import autogen
    return autogen

logging.basicConfig(level=os.environ.get('LOGLEVEL', 'WARNING') or 'WARNING', format='%(asctime)s - %(levelname)s - %(message)s')
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

class PraisonAI:
    def __init__(self, agent_file="agents.yaml", framework="", auto=False, init=False, agent_yaml=None, tools=None):
        """
        Initialize the PraisonAI object with default parameters.
        """
        self.agent_yaml = agent_yaml
        self._interactive_mode = False  # Flag for interactive TUI mode
        # Create config_list with AutoGen compatibility
        # Support multiple environment variable patterns for better compatibility
        # Priority order: MODEL_NAME > OPENAI_MODEL_NAME for model selection
        model_name = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        
        # Priority order for base_url: OPENAI_BASE_URL > OPENAI_API_BASE > OLLAMA_API_BASE
        # OPENAI_BASE_URL is the standard OpenAI SDK environment variable
        base_url = (
            os.environ.get("OPENAI_BASE_URL") or 
            os.environ.get("OPENAI_API_BASE") or
            os.environ.get("OLLAMA_API_BASE", "https://api.openai.com/v1")
        )
        
        api_key = os.environ.get("OPENAI_API_KEY")
        self.config_list = [
            {
                'model': model_name,
                'base_url': base_url,
                'api_key': api_key,
                'api_type': 'openai'        # AutoGen expects this field
            }
        ]
        self.agent_file = agent_file
        self.framework = framework
        self.auto = auto
        self.init = init
        self.tools = tools or []  # Store tool class names as a list

    def run(self):
        """
        Run the PraisonAI application.
        """
        return self.main()

    def read_stdin_if_available(self):
        """
        Read from stdin if it's available (when data is piped in).
        Returns the stdin content or None if no piped input is available.
        """
        try:
            # Check if stdin is not a terminal (i.e., has piped input)
            if not sys.stdin.isatty():
                stdin_content = sys.stdin.read().strip()
                return stdin_content if stdin_content else None
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
        # Store the original agent_file from constructor
        original_agent_file = self.agent_file
        
        # Parse args - this returns both args and unknown_args
        parse_result = self.parse_args()
        if isinstance(parse_result, tuple):
            args, unknown_args = parse_result
        else:
            args = parse_result
            unknown_args = []
        
        # Store args for use in handle_direct_prompt
        self.args = args
        invocation_cmd = "praisonai"
        version_string = f"PraisonAI version {__version__}"

        # Handle -p/--prompt flag - treat as direct prompt
        if getattr(args, 'prompt_flag', None):
            args.direct_prompt = args.prompt_flag
            args.command = None

        self.framework = args.framework or self.framework
        
        # Update config_list model if --model flag is provided
        if getattr(args, 'model', None):
            self.config_list[0]['model'] = args.model

        # Check for piped input from stdin
        stdin_input = self.read_stdin_if_available()
        
        # Check for file input if --file is provided
        file_input = self.read_file_if_provided(getattr(args, 'file', None))

        if args.command:
            # Handle persistence command
            if args.command == "persistence":
                from praisonai.cli.features.persistence import handle_persistence_command
                handle_persistence_command(unknown_args)
                return None
            
            # Handle schedule command
            if args.command == "schedule":
                from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
                # Check for subcommands (start, list, stop, logs, restart)
                subcommand = unknown_args[0] if unknown_args and not unknown_args[0].startswith('-') else None
                
                if subcommand in ['start', 'list', 'stop', 'logs', 'restart', 'delete', 'describe', 'save', 'stop-all', 'stats']:
                    exit_code = AgentSchedulerHandler.handle_daemon_command(subcommand, args, unknown_args[1:] if len(unknown_args) > 1 else [])
                else:
                    # Legacy mode: direct scheduling (foreground) or daemon mode
                    daemon_mode = getattr(args, 'daemon', False)
                    exit_code = AgentSchedulerHandler.handle_schedule_command(args, unknown_args, daemon_mode=daemon_mode)
                
                sys.exit(exit_code)
            elif args.command.startswith("tests.test") or args.command.startswith("tests/test"):  # Argument used for testing purposes
                print("test")
                return "test"
            else:
                # Handle --compare flag for CLI mode comparison
                if hasattr(args, 'compare') and args.compare:
                    from .features.compare import CompareHandler
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
                else:
                    self.agent_file = args.command
        elif hasattr(args, 'direct_prompt') and args.direct_prompt:
            # Only handle direct prompt if agent_file wasn't explicitly set in constructor
            if original_agent_file == "agents.yaml":  # Default value, so safe to use direct prompt
                # Handle --compare flag for CLI mode comparison
                if hasattr(args, 'compare') and args.compare:
                    from .features.compare import CompareHandler
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
                from praisonai.scheduler import create_scheduler
                
                # Load configuration from file if provided
                config = {"max_retries": args.max_retries}
                schedule_expr = args.schedule
                provider = args.provider
                
                if args.schedule_config:
                    try:
                        with open(args.schedule_config, 'r') as f:
                            file_config = yaml.safe_load(f)
                        
                        # Extract deployment config
                        deploy_config = file_config.get('deployment', {})
                        schedule_expr = schedule_expr or deploy_config.get('schedule')
                        provider = deploy_config.get('provider', provider)
                        config['max_retries'] = deploy_config.get('max_retries', config['max_retries'])
                        
                        # Apply environment variables if specified
                        env_vars = file_config.get('environment', {})
                        for key, value in env_vars.items():
                            os.environ[key] = str(value)
                            
                    except FileNotFoundError:
                        print(f"Configuration file not found: {args.schedule_config}")
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
                from praisonai.cli.features.deploy import DeployHandler
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
        # They no longer open Chainlit browser UI

        if getattr(args, 'realtime', False):
            self.create_realtime_interface()
            return

        if getattr(args, 'call', False):
            if not CALL_MODULE_AVAILABLE:
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
                from praisonai.setup.setup_conda_env import main as setup_conda_main
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
                    from praisonai.setup.setup_conda_env import main as setup_conda_main
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
            agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list)
            result = agents_generator.generate_crew_and_kickoff()
            print(result)
            return result
        elif args.init or self.init:
            temp_topic = args.init if args.init else self.init
            if isinstance(temp_topic, list):
                temp_topic = ' '.join(temp_topic)
            self.topic = temp_topic

            self.agent_file = "agents.yaml"
            AutoGenerator = _get_auto_generator()
            generator = AutoGenerator(topic=self.topic, framework=self.framework, agent_file=self.agent_file)
            self.agent_file = generator.generate(merge=getattr(args, 'merge', False))
            print(f"File {self.agent_file} created successfully")
            return f"File {self.agent_file} created successfully"

        if args.ui:
            if args.ui == "gradio":
                self.create_gradio_interface()
            elif args.ui == "chainlit":
                self.create_chainlit_interface()
            else:
                # Modify code to allow default UI
                AgentsGenerator = _get_agents_generator()
                agents_generator = AgentsGenerator(
                    self.agent_file,
                    self.framework,
                    self.config_list,
                    agent_yaml=self.agent_yaml,
                    tools=self.tools
                )
                result = agents_generator.generate_crew_and_kickoff()
                print(result)
                return result
        else:
            # n8n Integration - Export workflow to n8n and open in browser
            if getattr(args, 'n8n', False):
                from .features.n8n import N8nHandler
                n8n_handler = N8nHandler(
                    verbose=getattr(args, 'verbose', False),
                    n8n_url=getattr(args, 'n8n_url', 'http://localhost:5678'),
                    api_url=getattr(args, 'api_url', 'http://127.0.0.1:8005')
                )
                result = n8n_handler.execute(self.agent_file)
                return result
            
            # Flow Display - Show flow diagram WITHOUT executing (--flow-display flag)
            if getattr(args, 'flow_display', False):
                from .features.flow_display import FlowDisplayHandler
                flow_handler = FlowDisplayHandler(verbose=getattr(args, 'verbose', False))
                flow_handler.display_flow_diagram(self.agent_file)
                return  # Exit without executing
            
            # Always show flow diagram before execution (default behavior)
            try:
                from .features.flow_display import FlowDisplayHandler
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
                    from praisonai.replay import ContextTraceWriter
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
                agents_generator = AgentsGenerator(
                    self.agent_file,
                    self.framework,
                    self.config_list,
                    agent_yaml=self.agent_yaml,
                    tools=self.tools
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
            return default_args
        
        # Define special commands
        special_commands = ['chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research', 'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools', 'todo', 'docs', 'mcp', 'commit', 'serve', 'schedule', 'skills', 'profile', 'eval', 'agents', 'run', 'thinking', 'compaction', 'output', 'deploy', 'templates', 'recipe', 'endpoints', 'audio', 'embed', 'embedding', 'images', 'moderate', 'files', 'batches', 'vector-stores', 'rerank', 'ocr', 'assistants', 'fine-tuning', 'completions', 'messages', 'guardrails', 'rag', 'videos', 'a2a', 'containers', 'passthrough', 'responses', 'search', 'realtime-api', 'doctor', 'registry', 'package', 'install', 'uninstall', 'acp', 'debug', 'lsp', 'diag', 'browser', 'replay', 'bot', 'gateway', 'sandbox', 'wizard', 'migrate', 'security', 'persistence']
        
        parser = argparse.ArgumentParser(prog="praisonai", description="praisonAI command-line interface")
        parser.add_argument("--framework", choices=["crewai", "autogen", "praisonai"], help="Specify the framework")
        parser.add_argument("--ui", choices=["chainlit", "gradio"], help="Specify the UI framework (gradio or chainlit).")
        parser.add_argument("--auto", nargs=argparse.REMAINDER, help="Enable auto mode and pass arguments for it")
        parser.add_argument("--init", nargs=argparse.REMAINDER, help="Initialize agents with optional topic")
        parser.add_argument("command", nargs="?", help="Command to run or direct prompt")
        parser.add_argument("--deploy", action="store_true", help="Deploy the application")
        parser.add_argument("--schedule", type=str, help="Schedule deployment (e.g., 'daily', 'hourly', '*/6h', '3600')")
        parser.add_argument("--schedule-config", type=str, help="Path to scheduling configuration file")
        parser.add_argument("--provider", type=str, default="gcp", help="Deployment provider (gcp, aws, azure)")
        parser.add_argument("--max-retries", type=int, default=3, help="Maximum retry attempts for scheduled deployments")
        parser.add_argument("--model", type=str, help="Model name")
        parser.add_argument("--llm", type=str, help="LLM model to use for direct prompts")
        parser.add_argument("--hf", type=str, help="Hugging Face model name")
        parser.add_argument("--ollama", type=str, help="Ollama model name")
        parser.add_argument("--dataset", type=str, help="Dataset name for training", default="yahma/alpaca-cleaned")
        parser.add_argument("--realtime", action="store_true", help="Start the realtime voice interaction interface")
        parser.add_argument("--call", action="store_true", help="Start the PraisonAI Call server")
        parser.add_argument("--public", action="store_true", help="Use ngrok to expose the server publicly (only with --call)")
        parser.add_argument("--merge", action="store_true", help="Merge existing agents.yaml with auto-generated agents instead of overwriting")
        parser.add_argument("--claudecode", action="store_true", help="Enable Claude Code integration for file modifications and coding tasks")
        parser.add_argument("--file", "-f", type=str, help="Read input from a file and append it to the prompt")
        parser.add_argument("--url", type=str, help="Repository URL for context analysis")
        parser.add_argument("--goal", type=str, help="Goal for context engineering")
        parser.add_argument("--auto-analyze", action="store_true", help="Enable automatic analysis in context engineering")
        parser.add_argument("--research", action="store_true", help="Run deep research on a topic")
        parser.add_argument("--query-rewrite", action="store_true", help="Rewrite query for better results (works with any command)")
        parser.add_argument("--rewrite-tools", type=str, help="Tools for query rewriter (e.g., 'internet_search' or path to tools.py)")
        parser.add_argument("--expand-prompt", action="store_true", help="Expand short prompt into detailed prompt (works with any command)")
        parser.add_argument("--expand-tools", type=str, help="Tools for prompt expander (e.g., 'internet_search' or path to tools.py)")
        parser.add_argument("--tools", "-t", type=str, help="Path to tools.py file for research agent")
        parser.add_argument("--no-tools", action="store_true", help="Disable default built-in tools (for models that don't support tool calling)")
        parser.add_argument("--no-acp", action="store_true", help="Disable ACP tools (agentic file operations with plan/approve/apply)")
        parser.add_argument("--no-lsp", action="store_true", help="Disable LSP tools (code intelligence: symbols, definitions, references)")
        parser.add_argument("--save", "-s", action="store_true", help="Save research output to file (output/research/)")
        parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output for research")
        parser.add_argument("--web", "--web-search", action="store_true", help="Enable native web search (OpenAI, Gemini, Anthropic, xAI, Perplexity)")
        parser.add_argument("--web-fetch", action="store_true", help="Enable web fetch to retrieve URL content (Anthropic only)")
        parser.add_argument("--prompt-caching", action="store_true", help="Enable prompt caching to reduce costs (OpenAI, Anthropic, Bedrock, Deepseek)")
        
        # Planning Mode arguments
        parser.add_argument("--planning", action="store_true", help="Enable planning mode - create plan before execution")
        parser.add_argument("--planning-tools", type=str, help="Tools for planning research (path to tools.py or comma-separated tool names)")
        parser.add_argument("--planning-reasoning", action="store_true", help="Enable chain-of-thought reasoning in planning")
        parser.add_argument("--auto-approve-plan", action="store_true", help="Auto-approve generated plans without user confirmation")
        parser.add_argument("--max-tokens", type=int, default=16000, help="Maximum output tokens for agent responses (default: 16000)")
        parser.add_argument("--final-agent", type=str, help="Final agent instruction to process the output (e.g., 'Write a detailed blog post')")
        
        # Memory arguments
        parser.add_argument("--memory", action="store_true", help="Enable file-based memory for agent")
        parser.add_argument("--user-id", type=str, help="User ID for memory isolation")
        
        # Session management arguments
        parser.add_argument("--auto-save", type=str, metavar="NAME", help="Auto-save session with given name after each run")
        parser.add_argument("--history", type=int, metavar="N", help="Load history from last N sessions into context")
        
        # Rules arguments
        parser.add_argument("--include-rules", type=str, help="Include manual rules by name (comma-separated)")
        
        # Workflow arguments (uses global --memory, --save, --verbose, --planning flags)
        parser.add_argument("--workflow", type=str, help="Run inline workflow steps (format: 'step1:action1,step2:action2')")
        parser.add_argument("--workflow-var", action="append", help="Workflow variable in key=value format (can be used multiple times)")
        
        # Claude Memory Tool arguments
        parser.add_argument("--claude-memory", action="store_true", help="Enable Claude Memory Tool (Anthropic models only)")
        
        # New CLI Feature arguments (from cli_features module)
        # Guardrail - output validation
        parser.add_argument("--guardrail", type=str, help="Validate output with LLM guardrail (provide description)")
        
        # Metrics - token/cost tracking
        parser.add_argument("--metrics", action="store_true", help="Display token usage and cost metrics")
        
        # Image Description (Vision) - analyze existing images
        parser.add_argument("--image", type=str, help="Path to image file for vision-based description/analysis")
        
        # Image Generation - create new images from text
        parser.add_argument("--image-generate", action="store_true", dest="image_generate", 
                          help="Generate an image from the text prompt (use with --llm for model selection)")
        
        # Telemetry - usage monitoring
        parser.add_argument("--telemetry", action="store_true", help="Enable usage monitoring and analytics")
        
        # Profiling - unified execution profiling
        parser.add_argument("--profile", action="store_true", help="Enable profiling with timing breakdown")
        parser.add_argument("--profile-deep", action="store_true", dest="profile_deep", help="Enable deep profiling with call graph (higher overhead)")
        parser.add_argument("--profile-format", type=str, choices=["text", "json"], default="text", dest="profile_format", help="Profile output format")
        
        # MCP - Model Context Protocol
        parser.add_argument("--mcp", type=str, help="MCP server command (e.g., 'npx -y @modelcontextprotocol/server-filesystem .')")
        parser.add_argument("--mcp-env", type=str, help="MCP environment variables (KEY=value,KEY2=value2)")
        
        # Fast Context - codebase search
        parser.add_argument("--fast-context", type=str, help="Path to search for relevant code context")
        
        # Handoff - agent delegation with unified HandoffConfig
        parser.add_argument("--handoff", type=str, help="Comma-separated agent roles for task delegation")
        parser.add_argument("--handoff-policy", type=str, choices=["full", "summary", "none", "last_n"],
                          help="Context sharing policy for handoffs (default: summary)")
        parser.add_argument("--handoff-timeout", type=float, help="Timeout in seconds for handoff execution")
        parser.add_argument("--handoff-max-depth", type=int, help="Maximum handoff chain depth (default: 10)")
        parser.add_argument("--handoff-max-concurrent", type=int, help="Maximum concurrent handoffs (default: 3)")
        parser.add_argument("--handoff-detect-cycles", type=str, choices=["true", "false"],
                          help="Enable cycle detection in handoff chains (default: true)")
        
        # Auto Memory - automatic memory extraction
        parser.add_argument("--auto-memory", action="store_true", help="Enable automatic memory extraction")
        
        # Todo - task list generation
        parser.add_argument("--todo", action="store_true", help="Generate todo list from task")
        
        # Router - smart model selection
        parser.add_argument("--router", action="store_true", help="Auto-select best model based on task complexity")
        parser.add_argument("--router-provider", type=str, help="Preferred provider for router (openai, anthropic, google)")
        
        # AutoRag - automatic RAG retrieval decision
        parser.add_argument("--auto-rag", action="store_true", help="Enable automatic RAG retrieval (decides when to retrieve vs direct chat)")
        parser.add_argument("--rag-policy", type=str, choices=["auto", "always", "never"], default="auto",
                          help="RAG retrieval policy: auto (decide per query), always, never")
        parser.add_argument("--rag-top-k", type=int, default=5, help="Number of results to retrieve (default: 5)")
        parser.add_argument("--rag-hybrid", action="store_true", help="Enable hybrid retrieval (semantic + keyword)")
        parser.add_argument("--rag-rerank", action="store_true", help="Enable result reranking")
        
        # Flow Display - visual workflow
        parser.add_argument("--flow-display", action="store_true", help="Enable visual workflow tracking")
        
        # n8n Integration - export workflow to n8n
        parser.add_argument("--n8n", action="store_true", help="Export workflow to n8n and open in browser")
        parser.add_argument("--n8n-url", type=str, default="http://localhost:5678", help="n8n instance URL (default: http://localhost:5678)")
        parser.add_argument("--api-url", type=str, default="http://127.0.0.1:8005", help="PraisonAI API URL for n8n to call (default: http://127.0.0.1:8005)")
        
        # Serve - start API server for agents
        parser.add_argument("--serve", action="store_true", help="Start API server for agents (use with agents.yaml)")
        parser.add_argument("--port", type=int, default=8005, help="Server port (default: 8005)")
        parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")
        
        # Session management
        parser.add_argument("--resume", type=str, dest="resume_session", metavar="SESSION", help="Resume a session (use 'last' for most recent, or session ID)")
        
        # Direct prompt flag - alternative to positional command
        parser.add_argument("-p", "--prompt", type=str, dest="prompt_flag", help="Direct prompt to execute (alternative to positional argument)")
        
        # Autonomy Mode - control AI action approval
        parser.add_argument("--autonomy", type=str, choices=["suggest", "auto_edit", "full_auto"], help="Set autonomy mode for AI actions")
        
        # Tool Approval - control tool execution approval
        parser.add_argument("--trust", action="store_true", help="Auto-approve all tool executions (skip approval prompts)")
        parser.add_argument("--approve-level", type=str, choices=["low", "medium", "high", "critical"], 
                          help="Auto-approve tools up to this risk level (e.g., --approve-level high approves low/medium/high but prompts for critical)")
        
        # Sandbox Execution - secure command execution
        parser.add_argument("--sandbox", type=str, choices=["off", "basic", "strict"], help="Enable sandboxed command execution")
        
        # External Agent - use external AI CLI tools
        parser.add_argument("--external-agent", type=str, choices=["claude", "gemini", "codex", "cursor"],
                          help="Use external AI CLI tool (claude, gemini, codex, cursor)")
        
        # Compare - compare different CLI modes
        parser.add_argument("--compare", type=str, help="Compare CLI modes (comma-separated: basic,tools,research,planning)")
        parser.add_argument("--compare-output", type=str, help="Save comparison results to file")
        
        # Context Management - context budgeting, optimization, and monitoring
        parser.add_argument("--context-auto-compact", action="store_true", dest="context_auto_compact", 
                          help="Enable automatic context compaction (default in interactive mode)")
        parser.add_argument("--no-context-auto-compact", action="store_false", dest="context_auto_compact",
                          help="Disable automatic context compaction")
        parser.add_argument("--context-strategy", type=str, choices=["truncate", "sliding_window", "prune_tools", "summarize", "smart"],
                          help="Context optimization strategy (default: smart)")
        parser.add_argument("--context-threshold", type=float, metavar="0.0-1.0",
                          help="Trigger compaction at this utilization (default: 0.8)")
        parser.add_argument("--context-monitor", action="store_true", dest="context_monitor",
                          help="Enable real-time context monitoring (writes to context.txt)")
        parser.add_argument("--context-monitor-path", type=str, metavar="PATH",
                          help="Path for context monitor output (default: ./context.txt)")
        parser.add_argument("--context-monitor-format", type=str, choices=["human", "json"],
                          help="Context monitor output format (default: human)")
        parser.add_argument("--context-monitor-frequency", type=str, choices=["turn", "tool_call", "manual", "overflow"],
                          help="Context monitor update frequency (default: turn)")
        parser.add_argument("--context-redact", action="store_true", dest="context_redact",
                          help="Redact sensitive data in context monitor output (default: true)")
        parser.add_argument("--no-context-redact", action="store_false", dest="context_redact",
                          help="Disable sensitive data redaction in context monitor")
        parser.add_argument("--context-output-reserve", type=int, metavar="TOKENS",
                          help="Reserve tokens for model output (default: 8000)")
        
        # Agent Scheduler - for schedule command
        parser.add_argument("--interval", dest="schedule_interval", type=str, help="Schedule interval (e.g., 'hourly', '*/30m', 'daily')")
        parser.add_argument("--schedule-max-retries", dest="schedule_max_retries", type=int, help="Maximum retry attempts for scheduled execution")
        parser.add_argument("--timeout", type=int, help="Maximum execution time per run in seconds")
        parser.add_argument('--max-cost', type=float, help='Maximum total cost budget in USD')
        parser.add_argument('--daemon', action='store_true', help=argparse.SUPPRESS)  # Hidden flag for daemon mode
        
        # Rate Limiter - control API request rate
        parser.add_argument("--rpm", type=int, help="Rate limit: requests per minute for LLM calls")
        parser.add_argument("--tpm", type=int, help="Rate limit: tokens per minute for LLM calls (optional)")
        
        # Configurable Model - runtime model switching
        parser.add_argument("--configurable-model", action="store_true", help="Enable runtime model switching via config parameter")
        parser.add_argument("--temperature", type=float, help="Override temperature for LLM calls")
        parser.add_argument("--llm-provider", type=str, help="Override LLM provider (openai, anthropic, google, etc.)")
        
        # Ollama Provider - native Ollama integration
        parser.add_argument("--ollama-model", type=str, help="Ollama model name (e.g., llama3.2:3b, mistral, qwen2.5:7b)")
        parser.add_argument("--ollama-host", type=str, help="Ollama server host (default: http://localhost:11434)")
        
        # Tool calling reliability - for weak/local models like Ollama
        parser.add_argument("--max-tool-repairs", type=int, default=None,
                          help="Max tool call repair attempts (default: 2 for Ollama, 0 for others)")
        parser.add_argument("--force-tool-usage", type=str, choices=["auto", "always", "never"], default=None,
                          help="Force tool usage mode: auto (default for Ollama), always, never")
        
        # If we're in a test environment, parse with empty args to avoid pytest interference
        if in_test_env:
            args, unknown_args = parser.parse_known_args([])
        else:
            args, unknown_args = parser.parse_known_args()

        # Handle special cases first
        if unknown_args and unknown_args[0] == '-b' and unknown_args[1] == 'api:app':
            args.command = 'agents.yaml'
        if args.command == 'api:app' or args.command == '/app/api:app':
            args.command = 'agents.yaml'
        if args.command == 'ui':
            args.ui = 'chainlit'
        # chat and code commands are now terminal-native (handled by Typer commands)
        # They no longer set args.ui = 'chainlit' or open browser
        
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
            from praisonai.cli.features.acp import run_acp_command
            exit_code = run_acp_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle debug command - Debug and test interactive flows
        if args.command == 'debug':
            from praisonai.cli.features.debug import run_debug_command
            exit_code = run_debug_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle lsp command - LSP service lifecycle
        if args.command == 'lsp':
            from praisonai.cli.features.lsp_cli import run_lsp_command
            exit_code = run_lsp_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle diag command - Diagnostics export
        if args.command == 'diag':
            from praisonai.cli.features.diag import run_diag_command
            exit_code = run_diag_command(unknown_args)
            sys.exit(exit_code)
        
        # Handle replay command - context replay for debugging agent execution
        if args.command == 'replay':
            from .app import app as typer_app, register_commands
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
            if not CALL_MODULE_AVAILABLE:
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

            elif args.command == 'call':
                if not CALL_MODULE_AVAILABLE:
                    print("[red]ERROR: Call feature is not installed. Install with:[/red]")
                    print("\npip install \"praisonai[call]\"\n")
                    sys.exit(1)
                _get_call_module().main()
                sys.exit(0)

            elif args.command == 'realtime':
                if not CHAINLIT_AVAILABLE:
                    print("[red]ERROR: Realtime UI is not installed. Install with:[/red]")
                    print("\npip install \"praisonai[realtime]\"\n")
                    sys.exit(1)
                self.create_realtime_interface()
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
                if not CHAINLIT_AVAILABLE:
                    print("[red]ERROR: UI is not installed. Install with:[/red]")
                    print("\npip install \"praisonai[ui]\"\n")
                    sys.exit(1)
                self.create_chainlit_interface()
                sys.exit(0)

            elif args.command == 'context':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
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
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
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
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'help'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                user_id = getattr(args, 'user_id', None)
                self.handle_memory_command(action, action_args, user_id)
                sys.exit(0)

            elif args.command == 'rules':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_rules_command(action, action_args)
                sys.exit(0)

            elif args.command == 'workflow':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
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
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                self.handle_hooks_command(action)
                sys.exit(0)

            elif args.command == 'knowledge':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'help'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_knowledge_command(action, action_args)
                sys.exit(0)

            elif args.command == 'session':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_session_command(action, action_args)
                sys.exit(0)

            elif args.command == 'tools':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_tools_command(action, action_args)
                sys.exit(0)

            elif args.command == 'todo':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_todo_command(action, action_args)
                sys.exit(0)

            elif args.command == 'docs':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_docs_command(action, action_args)
                sys.exit(0)

            elif args.command == 'mcp':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                # Get action and arguments from remaining args
                action = unknown_args[0] if unknown_args else 'list'
                action_args = unknown_args[1:] if len(unknown_args) > 1 else []
                self.handle_mcp_command(action, action_args)
                sys.exit(0)

            elif args.command == 'commit':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                self.handle_commit_command(unknown_args)
                sys.exit(0)

            elif args.command == 'skills':
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                from .features.skills import handle_skills_command, add_skills_parser
                
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
                from .app import app as typer_app
                import sys as _sys
                _sys.argv = ['praisonai', 'profile'] + unknown_args
                typer_app()
                sys.exit(0)
            
            elif args.command == 'eval':
                # Eval command - evaluate model responses against expected outputs
                from .features.eval import handle_eval_command
                exit_code = handle_eval_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'audit':
                # Audit command - agent-centric compliance auditing
                from .commands.audit import audit as audit_cli
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
                from .features.templates import handle_templates_command
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
                from .features.recipe import handle_recipe_command
                exit_code = handle_recipe_command(recipe_args)
                sys.exit(exit_code)
            
            elif args.command == 'endpoints':
                # Endpoints command - unified client CLI for all server types
                from .features.endpoints import handle_endpoints_command
                exit_code = handle_endpoints_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'serve':
                # Serve command - launch PraisonAI servers
                from .features.serve import handle_serve_command
                exit_code = handle_serve_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'agents':
                # Agents command - run multiple agents with custom definitions
                if not PRAISONAI_AVAILABLE:
                    print("[red]ERROR: PraisonAI Agents is not installed. Install with:[/red]")
                    print("\npip install praisonaiagents\n")
                    sys.exit(1)
                
                from .features.agents import handle_agents_command, add_agents_parser
                
                # Create a parser for agents command
                agents_parser = argparse.ArgumentParser(prog="praisonai agents")
                agents_subparsers = agents_parser.add_subparsers(dest='agents_command', help='Agents commands')
                add_agents_parser(agents_subparsers)
                agents_args = agents_parser.parse_args(unknown_args)
                
                exit_code = handle_agents_command(agents_args)
                sys.exit(exit_code)
            
            elif args.command == 'run':
                # Run command - async jobs API for long-running tasks
                from .features.jobs import handle_run_command
                handle_run_command(unknown_args, verbose=getattr(args, 'verbose', False))
                sys.exit(0)
            
            elif args.command == 'thinking':
                # Thinking command - manage thinking budgets
                from .features.thinking import handle_thinking_command
                exit_code = handle_thinking_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'compaction':
                # Compaction command - manage context compaction
                from .features.compaction import handle_compaction_command
                exit_code = handle_compaction_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'output':
                # Output command - manage output styles
                from .features.output_style import handle_output_command
                exit_code = handle_output_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'deploy':
                # Deploy command - deploy agents as API/Docker/Cloud
                from .features.deploy import DeployHandler
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
                from .features.capabilities import CapabilitiesHandler
                
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
                    exit_code = handler(args, unknown_args)
                    sys.exit(exit_code if exit_code else 0)
            
            elif args.command == 'doctor':
                # Doctor command - comprehensive health checks and diagnostics
                from .features.doctor.handler import DoctorHandler
                handler = DoctorHandler()
                exit_code = handler.run(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'browser':
                # Browser agent command - delegate to browser CLI Typer app
                # Uses sys.argv replacement for proper arg passthrough (matches profile command pattern)
                from praisonai.browser.cli import app as browser_app
                import sys as _sys
                _sys.argv = ['praisonai', 'browser'] + unknown_args
                try:
                    browser_app()
                except SystemExit as e:
                    sys.exit(e.code if e.code else 0)
                sys.exit(0)
            
            elif args.command == 'replay':
                # Replay command - context replay for debugging agent execution
                # Routes to Typer CLI for replay commands (list, context, show, flow, delete, cleanup)
                from .app import app as typer_app, register_commands
                register_commands()
                import sys as _sys
                _sys.argv = ['praisonai', 'replay'] + unknown_args
                try:
                    typer_app()
                except SystemExit as e:
                    sys.exit(e.code if e.code else 0)
                sys.exit(0)
            
            elif args.command == 'registry':
                # Registry command - manage recipe registry server
                from .features.registry import RegistryHandler
                handler = RegistryHandler()
                exit_code = handler.handle(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'package':
                # Package command - pip-like package management
                from .features.package import PackageHandler
                handler = PackageHandler()
                exit_code = handler.handle(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'install':
                # Install command - shortcut for package install
                from .features.package import PackageHandler
                handler = PackageHandler()
                exit_code = handler.cmd_install(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'uninstall':
                # Uninstall command - shortcut for package uninstall
                from .features.package import PackageHandler
                handler = PackageHandler()
                exit_code = handler.cmd_uninstall(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'gateway':
                # Gateway command - WebSocket gateway for multi-agent coordination
                from .features.gateway import handle_gateway_command
                exit_code = handle_gateway_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'bot':
                # Bot command - messaging bot runtimes (Telegram, Discord, Slack)
                # Re-inject flags consumed by main parser into unknown_args for bot handler
                bot_args = list(unknown_args)
                if getattr(args, 'model', None) and '--model' not in bot_args and '-m' not in bot_args:
                    bot_args.extend(['--model', args.model])
                from .features.bots_cli import handle_bot_command
                exit_code = handle_bot_command(bot_args)
                sys.exit(exit_code)
            
            elif args.command == 'sandbox':
                # Sandbox command - secure code execution environment
                from .features.sandbox_cli import handle_sandbox_command
                exit_code = handle_sandbox_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'wizard':
                # Wizard command - interactive project setup
                from .features.wizard import handle_wizard_command
                exit_code = handle_wizard_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'migrate':
                # Migrate command - config migration between formats
                from .features.migrate import handle_migrate_command
                exit_code = handle_migrate_command(unknown_args)
                sys.exit(exit_code)
            
            elif args.command == 'security':
                # Security command - security audit and scanning
                from .features.audit_cli import handle_audit_command
                exit_code = handle_audit_command(unknown_args)
                sys.exit(exit_code)

        # Only check framework availability for agent-related operations
        if not args.command and (args.init or args.auto or args.framework):
            if not CREWAI_AVAILABLE and not AUTOGEN_AVAILABLE and not PRAISONAI_AVAILABLE:
                print("[red]ERROR: No framework is installed. Please install at least one framework:[/red]")
                print("\npip install \"praisonai\\[crewai]\"  # For CrewAI")
                print("pip install \"praisonai\\[autogen]\"  # For AutoGen")
                print("pip install \"praisonai\\[crewai,autogen]\"  # For both frameworks\n")
                print("pip install praisonaiagents # For Agents\n")  
                sys.exit(1)

        # Handle direct prompt if command is not a special command or file
        # Skip this during testing to avoid pytest arguments interfering
        if not in_test_env and args.command and not args.command.endswith('.yaml') and args.command not in special_commands:
            args.direct_prompt = args.command
            args.command = None

        return args, unknown_args

    def _rewrite_query(self, query: str, rewrite_tools: str = None, verbose: bool = False) -> str:
        """
        Rewrite query using QueryRewriterAgent.
        
        Args:
            query: The query to rewrite
            rewrite_tools: Tool names (comma-separated) or path to tools.py
            verbose: Enable verbose output
            
        Returns:
            Rewritten query or original if rewriting fails
        """
        try:
            from praisonaiagents import QueryRewriterAgent, RewriteStrategy
            from rich import print
            
            print("[bold cyan]Rewriting query for better results...[/bold cyan]")
            
            # Load rewrite tools if specified
            rewrite_tools_list = []
            if rewrite_tools:
                if os.path.isfile(rewrite_tools):
                    # Load from file
                    try:
                        import inspect
                        import importlib.util
                        spec = importlib.util.spec_from_file_location("rewrite_tools_module", rewrite_tools)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            for name, obj in inspect.getmembers(module):
                                if inspect.isfunction(obj) and not name.startswith('_'):
                                    rewrite_tools_list.append(obj)
                            if rewrite_tools_list:
                                print(f"[cyan]Loaded {len(rewrite_tools_list)} tools for query rewriter[/cyan]")
                    except Exception as e:
                        print(f"[yellow]Warning: Failed to load rewrite tools: {e}[/yellow]")
                else:
                    # Treat as comma-separated tool names
                    try:
                        from praisonaiagents.tools import TOOL_MAPPINGS
                        import praisonaiagents.tools as tools_module
                        
                        tool_names = [t.strip() for t in rewrite_tools.split(',')]
                        for tool_name in tool_names:
                            if tool_name in TOOL_MAPPINGS:
                                try:
                                    tool = getattr(tools_module, tool_name)
                                    rewrite_tools_list.append(tool)
                                except Exception as e:
                                    print(f"[yellow]Warning: Failed to load rewrite tool '{tool_name}': {e}[/yellow]")
                            else:
                                print(f"[yellow]Warning: Unknown rewrite tool '{tool_name}'[/yellow]")
                        if rewrite_tools_list:
                            print(f"[cyan]Using rewrite tools: {', '.join(tool_names)}[/cyan]")
                    except ImportError:
                        print("[yellow]Warning: Could not import tools module[/yellow]")
            
            rewriter = QueryRewriterAgent(
                model="gpt-4o-mini", 
                verbose=verbose, 
                tools=rewrite_tools_list if rewrite_tools_list else None
            )
            result = rewriter.rewrite(query, strategy=RewriteStrategy.AUTO)
            rewritten = result.primary_query
            
            print(f"[cyan]Original:[/cyan] {query}")
            print(f"[cyan]Rewritten:[/cyan] {rewritten}")
            
            return rewritten
            
        except ImportError:
            from rich import print
            print("[yellow]Warning: QueryRewriterAgent not available, using original query[/yellow]")
            return query
        except Exception as e:
            from rich import print
            print(f"[yellow]Warning: Query rewrite failed ({e}), using original query[/yellow]")
            return query

    def _rewrite_query_if_enabled(self, query: str) -> str:
        """
        Rewrite query using QueryRewriterAgent if --query-rewrite is enabled.
        Returns the rewritten query or original if rewriting is disabled/fails.
        """
        if not hasattr(self, 'args') or not getattr(self.args, 'query_rewrite', False):
            return query
        
        rewrite_tools = getattr(self.args, 'rewrite_tools', None)
        verbose = getattr(self.args, 'verbose', False)
        return self._rewrite_query(query, rewrite_tools, verbose)

    def _expand_prompt(self, prompt: str, expand_tools: str = None, verbose: bool = False) -> str:
        """
        Expand prompt using PromptExpanderAgent.
        
        Args:
            prompt: The prompt to expand
            expand_tools: Tool names (comma-separated) or path to tools.py
            verbose: Enable verbose output
            
        Returns:
            Expanded prompt or original if expansion fails
        """
        try:
            from praisonaiagents import PromptExpanderAgent, ExpandStrategy
            from rich import print
            
            print("[bold cyan]Expanding prompt for detailed execution...[/bold cyan]")
            
            # Load expand tools if specified
            expand_tools_list = []
            if expand_tools:
                if os.path.isfile(expand_tools):
                    # Load from file
                    try:
                        import inspect
                        import importlib.util
                        spec = importlib.util.spec_from_file_location("expand_tools_module", expand_tools)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            for name, obj in inspect.getmembers(module):
                                if inspect.isfunction(obj) and not name.startswith('_'):
                                    expand_tools_list.append(obj)
                            if expand_tools_list:
                                print(f"[cyan]Loaded {len(expand_tools_list)} tools for prompt expander[/cyan]")
                    except Exception as e:
                        print(f"[yellow]Warning: Failed to load expand tools: {e}[/yellow]")
                else:
                    # Treat as comma-separated tool names
                    try:
                        from praisonaiagents.tools import TOOL_MAPPINGS
                        import praisonaiagents.tools as tools_module
                        
                        tool_names = [t.strip() for t in expand_tools.split(',')]
                        for tool_name in tool_names:
                            if tool_name in TOOL_MAPPINGS:
                                try:
                                    tool = getattr(tools_module, tool_name)
                                    expand_tools_list.append(tool)
                                except Exception as e:
                                    print(f"[yellow]Warning: Failed to load expand tool '{tool_name}': {e}[/yellow]")
                            else:
                                print(f"[yellow]Warning: Unknown expand tool '{tool_name}'[/yellow]")
                        if expand_tools_list:
                            print(f"[cyan]Using expand tools: {', '.join(tool_names)}[/cyan]")
                    except ImportError:
                        print("[yellow]Warning: Could not import tools module[/yellow]")
            
            expander = PromptExpanderAgent(
                model="gpt-4o-mini", 
                verbose=verbose, 
                tools=expand_tools_list if expand_tools_list else None
            )
            result = expander.expand(prompt, strategy=ExpandStrategy.AUTO)
            expanded = result.expanded_prompt
            
            print(f"[cyan]Original:[/cyan] {prompt}")
            print(f"[cyan]Expanded:[/cyan] {expanded}")
            
            return expanded
            
        except ImportError:
            from rich import print
            print("[yellow]Warning: PromptExpanderAgent not available, using original prompt[/yellow]")
            return prompt
        except Exception as e:
            from rich import print
            print(f"[yellow]Warning: Prompt expansion failed ({e}), using original prompt[/yellow]")
            return prompt

    def _expand_prompt_if_enabled(self, prompt: str) -> str:
        """
        Expand prompt using PromptExpanderAgent if --expand-prompt is enabled.
        Returns the expanded prompt or original if expansion is disabled/fails.
        """
        if not hasattr(self, 'args') or not getattr(self.args, 'expand_prompt', False):
            return prompt
        
        expand_tools = getattr(self.args, 'expand_tools', None)
        verbose = getattr(self.args, 'verbose', False)
        return self._expand_prompt(prompt, expand_tools, verbose)

    def _load_tools(self, tools_path: str) -> list:
        """
        Load tools from a file path or comma-separated tool names.
        
        Args:
            tools_path: Path to tools.py file or comma-separated tool names
            
        Returns:
            List of tool functions
        """
        tools_list = []
        if not tools_path:
            return tools_list
            
        if os.path.isfile(tools_path):
            # Load from file
            try:
                import inspect
                spec = importlib.util.spec_from_file_location("tools_module", tools_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    for name, obj in inspect.getmembers(module):
                        if inspect.isfunction(obj) and not name.startswith('_'):
                            tools_list.append(obj)
                    if tools_list:
                        print(f"[cyan]Loaded {len(tools_list)} tools from {tools_path}[/cyan]")
            except Exception as e:
                print(f"[yellow]Warning: Failed to load tools from {tools_path}: {e}[/yellow]")
        else:
            # Treat as comma-separated tool names
            try:
                from praisonaiagents.tools import TOOL_MAPPINGS
                import praisonaiagents.tools as tools_module
                
                tool_names = [t.strip() for t in tools_path.split(',')]
                for tool_name in tool_names:
                    if tool_name in TOOL_MAPPINGS:
                        try:
                            tool = getattr(tools_module, tool_name)
                            tools_list.append(tool)
                        except Exception as e:
                            print(f"[yellow]Warning: Failed to load tool '{tool_name}': {e}[/yellow]")
                    else:
                        print(f"[yellow]Warning: Unknown tool '{tool_name}'[/yellow]")
                if tools_list:
                    print(f"[cyan]Loaded {len(tools_list)} built-in tools[/cyan]")
            except ImportError:
                print("[yellow]Warning: Could not import tools module[/yellow]")
        
        return tools_list

    def handle_memory_command(self, action: str, action_args: list, user_id: str = None):
        """
        Handle memory subcommand actions.
        
        Args:
            action: The memory action (show, add, search, clear, save, resume, etc.)
            action_args: Additional arguments for the action
            user_id: User ID for memory isolation
        """
        try:
            from praisonaiagents.memory import FileMemory
            from rich import print
            from rich.table import Table
            from rich.console import Console
            
            console = Console()
            memory = FileMemory(user_id=user_id or "default")
            
            if action == 'show':
                stats = memory.get_stats()
                table = Table(title="Memory Statistics")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")
                
                for key, value in stats.items():
                    table.add_row(str(key), str(value))
                
                console.print(table)
                
                # Show recent short-term memories
                print("\n[bold]Recent Short-term Memories:[/bold]")
                short_term = memory.get_short_term(limit=5)
                if short_term:
                    for i, item in enumerate(short_term, 1):
                        content = item.get('content', str(item))[:100]
                        print(f"  {i}. {content}")
                else:
                    print("  [dim]No short-term memories[/dim]")
                
                # Show long-term memories
                print("\n[bold]Long-term Memories:[/bold]")
                long_term = memory.get_long_term(limit=10)
                if long_term:
                    for i, item in enumerate(long_term, 1):
                        # Handle both dict and MemoryItem objects
                        if hasattr(item, 'content'):
                            content = str(item.content)[:100]
                            importance = getattr(item, 'importance', 0)
                        else:
                            content = item.get('content', str(item))[:100]
                            importance = item.get('importance', 0)
                        print(f"  {i}. [{importance:.1f}] {content}")
                else:
                    print("  [dim]No long-term memories[/dim]")
                
                # Show entities
                print("\n[bold]Entities:[/bold]")
                entities = memory.get_all_entities()
                if entities:
                    for entity in entities[:10]:
                        # Handle both dict and Entity objects
                        if hasattr(entity, 'name'):
                            name = entity.name
                            entity_type = getattr(entity, 'entity_type', 'unknown')
                        else:
                            name = entity.get('name', 'Unknown')
                            entity_type = entity.get('entity_type', 'unknown')
                        print(f"  • {name} ({entity_type})")
                else:
                    print("  [dim]No entities[/dim]")
                
            elif action == 'add':
                if not action_args:
                    print("[red]ERROR: Content required. Usage: praisonai memory add \"Your memory content\"[/red]")
                    return
                content = ' '.join(action_args)
                memory.add_long_term(content, importance=0.8)
                print(f"[green]✅ Added to long-term memory: {content[:50]}...[/green]")
                
            elif action == 'search':
                if not action_args:
                    print("[red]ERROR: Query required. Usage: praisonai memory search \"query\"[/red]")
                    return
                query = ' '.join(action_args)
                results = memory.search(query, limit=10)
                print(f"[bold]Search results for '{query}':[/bold]")
                for i, result in enumerate(results, 1):
                    content = result.get('content', str(result))[:100]
                    print(f"  {i}. {content}")
                    
            elif action == 'clear':
                target = action_args[0] if action_args else 'short'
                if target == 'all':
                    memory.clear_all()
                    print("[green]✅ All memory cleared[/green]")
                else:
                    memory.clear_short_term()
                    print("[green]✅ Short-term memory cleared[/green]")
                    
            elif action == 'save':
                if not action_args:
                    print("[red]ERROR: Session name required. Usage: praisonai memory save <session_name>[/red]")
                    return
                session_name = action_args[0]
                memory.save_session(session_name)
                print(f"[green]✅ Session saved: {session_name}[/green]")
                
            elif action == 'resume':
                if not action_args:
                    print("[red]ERROR: Session name required. Usage: praisonai memory resume <session_name>[/red]")
                    return
                session_name = action_args[0]
                memory.resume_session(session_name)
                print(f"[green]✅ Session resumed: {session_name}[/green]")
                
            elif action == 'sessions':
                sessions = memory.list_sessions()
                if sessions:
                    print("[bold]Saved Sessions:[/bold]")
                    for s in sessions:
                        print(f"  - {s.get('name', 'Unknown')} (saved: {s.get('saved_at', 'Unknown')})")
                else:
                    print("[yellow]No saved sessions found[/yellow]")
                    
            elif action == 'compress':
                print("[cyan]Compressing short-term memory...[/cyan]")
                # Note: compress requires an LLM function, so we'll just show stats
                stats = memory.get_stats()
                print(f"[green]Short-term items: {stats.get('short_term_count', 0)}[/green]")
                print("[yellow]Note: Full compression requires an LLM. Use programmatically with memory.compress(llm_func=...)[/yellow]")
                
            elif action == 'checkpoint':
                name = action_args[0] if action_args else None
                checkpoint_id = memory.create_checkpoint(name)
                print(f"[green]✅ Checkpoint created: {checkpoint_id}[/green]")
                
            elif action == 'restore':
                if not action_args:
                    print("[red]ERROR: Checkpoint ID required. Usage: praisonai memory restore <checkpoint_id>[/red]")
                    return
                checkpoint_id = action_args[0]
                memory.restore_checkpoint(checkpoint_id)
                print(f"[green]✅ Checkpoint restored: {checkpoint_id}[/green]")
                
            elif action == 'checkpoints':
                checkpoints = memory.list_checkpoints()
                if checkpoints:
                    print("[bold]Checkpoints:[/bold]")
                    for cp in checkpoints:
                        print(f"  - {cp.get('id', 'Unknown')} ({cp.get('name', 'Unnamed')})")
                else:
                    print("[yellow]No checkpoints found[/yellow]")
                    
            elif action == 'help' or action == '--help':
                print("[bold]Memory Commands:[/bold]")
                print("  praisonai memory show                    - Show memory statistics")
                print("  praisonai memory add <content>           - Add to long-term memory")
                print("  praisonai memory search <query>          - Search memories")
                print("  praisonai memory clear [short|all]       - Clear memory")
                print("  praisonai memory save <session_name>     - Save session")
                print("  praisonai memory resume <session_name>   - Resume session")
                print("  praisonai memory sessions                - List saved sessions")
                print("  praisonai memory compress                - Compress short-term memory")
                print("  praisonai memory checkpoint [name]       - Create checkpoint")
                print("  praisonai memory restore <checkpoint_id> - Restore checkpoint")
                print("  praisonai memory checkpoints             - List checkpoints")
                print("\n[bold]Options:[/bold]")
                print("  --user-id <id>                           - User ID for memory isolation")
            else:
                print(f"[red]Unknown memory action: {action}[/red]")
                print("Use 'praisonai memory help' for available commands")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import memory module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Memory command failed: {e}[/red]")

    def handle_rules_command(self, action: str, action_args: list):
        """
        Handle rules subcommand actions.
        
        Args:
            action: The rules action (list, show, create, delete, stats)
            action_args: Additional arguments for the action
        """
        try:
            from praisonaiagents.memory import RulesManager
            from rich import print
            from rich.table import Table
            from rich.console import Console
            
            console = Console()
            rules = RulesManager(workspace_path=os.getcwd())
            
            if action == 'list':
                all_rules = rules.get_all_rules()
                if all_rules:
                    table = Table(title="Loaded Rules")
                    table.add_column("Name", style="cyan")
                    table.add_column("Description", style="white")
                    table.add_column("Activation", style="green")
                    table.add_column("Priority", style="yellow")
                    
                    for rule in all_rules:
                        table.add_row(
                            rule.name,
                            rule.description[:50] + "..." if len(rule.description) > 50 else rule.description,
                            rule.activation,
                            str(rule.priority)
                        )
                    
                    console.print(table)
                else:
                    print("[yellow]No rules found. Create PRAISON.md, CLAUDE.md, or files in .praison/rules/[/yellow]")
                    
            elif action == 'show':
                if not action_args:
                    print("[red]ERROR: Rule name required. Usage: praisonai rules show <name>[/red]")
                    return
                rule_name = action_args[0]
                rule = rules.get_rule_by_name(rule_name)
                if rule:
                    print(f"[bold cyan]Rule: {rule.name}[/bold cyan]")
                    print(f"[bold]Description:[/bold] {rule.description}")
                    print(f"[bold]Activation:[/bold] {rule.activation}")
                    print(f"[bold]Priority:[/bold] {rule.priority}")
                    if rule.globs:
                        print(f"[bold]Globs:[/bold] {', '.join(rule.globs)}")
                    print(f"\n[bold]Content:[/bold]\n{rule.content}")
                else:
                    print(f"[red]Rule not found: {rule_name}[/red]")
                    
            elif action == 'create':
                if len(action_args) < 2:
                    print("[red]ERROR: Name and content required. Usage: praisonai rules create <name> <content>[/red]")
                    return
                rule_name = action_args[0]
                content = ' '.join(action_args[1:])
                rules.create_rule(
                    name=rule_name,
                    content=content,
                    description=f"Rule created via CLI: {rule_name}",
                    activation="always",
                    scope="workspace"
                )
                print(f"[green]✅ Rule created: {rule_name}[/green]")
                
            elif action == 'delete':
                if not action_args:
                    print("[red]ERROR: Rule name required. Usage: praisonai rules delete <name>[/red]")
                    return
                rule_name = action_args[0]
                rules.delete_rule(rule_name)
                print(f"[green]✅ Rule deleted: {rule_name}[/green]")
                
            elif action == 'stats':
                stats = rules.get_stats()
                table = Table(title="Rules Statistics")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")
                
                for key, value in stats.items():
                    if isinstance(value, dict):
                        table.add_row(str(key), str(value))
                    else:
                        table.add_row(str(key), str(value))
                
                console.print(table)
                
            elif action == 'help' or action == '--help':
                print("[bold]Rules Commands:[/bold]")
                print("  praisonai rules list                     - List all loaded rules")
                print("  praisonai rules show <name>              - Show specific rule details")
                print("  praisonai rules create <name> <content>  - Create a new rule")
                print("  praisonai rules delete <name>            - Delete a rule")
                print("  praisonai rules stats                    - Show rules statistics")
                print("\n[bold]Supported Rule Files:[/bold]")
                print("  PRAISON.md, CLAUDE.md, AGENTS.md, GEMINI.md")
                print("  .cursorrules, .windsurfrules")
                print("  .praison/rules/*.md, ~/.praison/rules/*.md")
            else:
                print(f"[red]Unknown rules action: {action}[/red]")
                print("Use 'praisonai rules help' for available commands")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import rules module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Rules command failed: {e}[/red]")

    def handle_workflow_command(self, action: str, action_args: list, variables: dict = None, args=None):
        """
        Handle workflow subcommand actions.
        
        Args:
            action: The workflow action (list, run, create, show)
            action_args: Additional arguments for the action
            variables: Workflow variables for substitution
            args: Parsed command line arguments
        """
        try:
            from praisonaiagents import Agent as PraisonAgent
            from praisonaiagents.memory import WorkflowManager
            from rich import print
            from rich.table import Table
            from rich.console import Console
            
            console = Console()
            manager = WorkflowManager(workspace_path=os.getcwd())
            
            if action == 'list':
                workflows = manager.list_workflows()
                if workflows:
                    table = Table(title="Available Workflows")
                    table.add_column("Name", style="cyan")
                    table.add_column("Description", style="white")
                    table.add_column("Steps", style="green")
                    
                    for workflow in workflows:
                        table.add_row(
                            workflow.name,
                            workflow.description[:50] + "..." if len(workflow.description) > 50 else workflow.description,
                            str(len(workflow.steps))
                        )
                    
                    console.print(table)
                else:
                    print("[yellow]No workflows found. Create files in .praison/workflows/[/yellow]")
                    
            elif action == 'run':
                if not action_args:
                    print("[red]ERROR: Workflow name required. Usage: praisonai workflow run <name>[/red]")
                    return
                workflow_name = action_args[0]
                
                # Check if it's a YAML file
                if workflow_name.endswith(('.yaml', '.yml')) and os.path.exists(workflow_name):
                    # Use new YAML workflow parser
                    self._run_yaml_workflow(workflow_name, action_args, variables, args)
                    return
                
                # Use global flags (--llm, --tools, --planning, --memory, --save, --verbose)
                workflow_llm = getattr(args, 'llm', None) if args else None
                workflow_tools_str = getattr(args, 'tools', None) if args else None
                workflow_planning = getattr(args, 'planning', False) if args else False
                workflow_verbose = getattr(args, 'verbose', False) if args else False
                workflow_memory = getattr(args, 'memory', False) if args else False
                workflow_save = getattr(args, 'save', False) if args else False
                
                # Load tools if specified
                workflow_tools = None
                if workflow_tools_str:
                    workflow_tools = self._load_tools(workflow_tools_str)
                    if workflow_tools:
                        print(f"[cyan]Loaded {len(workflow_tools)} tool(s) for workflow[/cyan]")
                
                # Initialize memory if enabled
                memory = None
                if workflow_memory:
                    try:
                        from praisonaiagents.memory import Memory
                        memory = Memory()
                        print("[cyan]Memory enabled for workflow[/cyan]")
                    except ImportError:
                        print("[yellow]Warning: Memory not available[/yellow]")
                
                # Create default agent for steps without agent_config
                default_agent = PraisonAgent(
                    name="WorkflowExecutor",
                    role="Task Executor",
                    goal="Execute workflow steps",
                    llm=workflow_llm,
                    tools=workflow_tools,
                    verbose=1 if workflow_verbose else 0
                )
                
                print(f"[bold cyan]Running workflow: {workflow_name}[/bold cyan]")
                if workflow_planning:
                    print("[cyan]Planning mode enabled[/cyan]")
                
                result = manager.execute(
                    workflow_name,
                    default_agent=default_agent,
                    default_llm=workflow_llm,
                    variables=variables or {},
                    memory=memory,
                    planning=workflow_planning,
                    verbose=1 if workflow_verbose else 0,
                    on_step=lambda step, i: print(f"[cyan]  → Step {i+1}: {step.name}[/cyan]"),
                    on_result=lambda step, output: print(f"[green]  ✓ Completed: {step.name}[/green]")
                )
                
                if result.get("success"):
                    print("[green]✅ Workflow completed successfully![/green]")
                    for step_result in result.get("results", []):
                        status = "✅" if step_result.get("status") == "success" else "❌"
                        print(f"  {status} {step_result.get('step', 'Unknown step')}")
                    
                    # Show final output
                    final_results = result.get("results", [])
                    if final_results:
                        last_output = final_results[-1].get("output", "")
                        if last_output:
                            print("\n[bold]Final Output:[/bold]")
                            print(last_output[:2000] + "..." if len(last_output) > 2000 else last_output)
                    
                    # Save output if requested
                    if workflow_save and final_results:
                        from datetime import datetime
                        output_dir = os.path.join(os.getcwd(), "output", "workflows")
                        os.makedirs(output_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        safe_name = workflow_name.replace(" ", "_").lower()
                        output_file = os.path.join(output_dir, f"{timestamp}_{safe_name}.md")
                        
                        with open(output_file, "w") as f:
                            f.write(f"# Workflow: {workflow_name}\n\n")
                            f.write(f"**Executed:** {timestamp}\n\n")
                            for step_result in final_results:
                                f.write(f"## {step_result.get('step', 'Unknown')}\n\n")
                                f.write(f"**Status:** {step_result.get('status', 'unknown')}\n\n")
                                if step_result.get("output"):
                                    f.write(f"{step_result['output']}\n\n")
                        
                        print(f"\n[green]✅ Output saved to: {output_file}[/green]")
                else:
                    print(f"[red]❌ Workflow failed: {result.get('error', 'Unknown error')}[/red]")
                    
            elif action == 'show':
                if not action_args:
                    print("[red]ERROR: Workflow name required. Usage: praisonai workflow show <name>[/red]")
                    return
                workflow_name = action_args[0]
                workflow = manager.get_workflow(workflow_name)
                if workflow:
                    print(f"[bold cyan]Workflow: {workflow.name}[/bold cyan]")
                    print(f"[bold]Description:[/bold] {workflow.description}")
                    print(f"\n[bold]Steps ({len(workflow.steps)}):[/bold]")
                    for i, step in enumerate(workflow.steps, 1):
                        print(f"  {i}. {step.name}: {step.action[:80]}...")
                    if workflow.variables:
                        print(f"\n[bold]Variables:[/bold] {workflow.variables}")
                else:
                    print(f"[red]Workflow not found: {workflow_name}[/red]")
                    
            elif action == 'create':
                if not action_args:
                    print("[red]ERROR: Workflow name required. Usage: praisonai workflow create <name>[/red]")
                    return
                workflow_name = action_args[0]
                
                # Create a simple template workflow
                manager.create_workflow(
                    name=workflow_name,
                    description=f"Workflow created via CLI: {workflow_name}",
                    steps=[
                        {"name": "Step 1", "action": "First step - edit this in .praison/workflows/"},
                        {"name": "Step 2", "action": "Second step - edit this in .praison/workflows/"}
                    ]
                )
                print(f"[green]✅ Workflow created: {workflow_name}[/green]")
                print(f"[cyan]Edit the workflow in .praison/workflows/{workflow_name}.md[/cyan]")
                
            elif action == 'validate':
                # Validate a YAML workflow file
                if not action_args:
                    print("[red]ERROR: YAML file required. Usage: praisonai workflow validate <file.yaml>[/red]")
                    return
                yaml_file = action_args[0]
                if not yaml_file.endswith(('.yaml', '.yml')):
                    print("[red]ERROR: File must be a YAML file (.yaml or .yml)[/red]")
                    return
                self._validate_yaml_workflow(yaml_file)
                
            elif action == 'template':
                # Create from template
                template_name = action_args[0] if action_args else None
                output_file = None
                for i, arg in enumerate(action_args):
                    if arg == '--output' and i + 1 < len(action_args):
                        output_file = action_args[i + 1]
                self._create_workflow_from_template(template_name, output_file)
            
            elif action == 'auto':
                # Auto-generate workflow from topic
                self._auto_generate_workflow(action_args)
                
            elif action == 'help' or action == '--help':
                print("[bold]Workflow Commands:[/bold]")
                print("  praisonai workflow list                  - List available workflows")
                print("  praisonai workflow run <name>            - Execute a workflow")
                print("  praisonai workflow run <file.yaml>       - Execute a YAML workflow")
                print("  praisonai workflow show <name>           - Show workflow details")
                print("  praisonai workflow create <name>         - Create a new workflow")
                print("  praisonai workflow validate <file.yaml>  - Validate a YAML workflow")
                print("  praisonai workflow template <name>       - Create from template")
                print('  praisonai workflow auto "topic"          - Auto-generate workflow')
                print("\n[bold]Templates:[/bold]")
                print("  simple, routing, parallel, loop, evaluator-optimizer")
                print("\n[bold]Options (uses global flags):[/bold]")
                print("  --workflow-var key=value                 - Set workflow variable (can be repeated)")
                print("  --var key=value                          - Set variable for YAML workflows")
                print("  --llm <model>                            - LLM model (e.g., openai/gpt-4o-mini)")
                print("  --tools <tools>                          - Tools (comma-separated, e.g., tavily)")
                print("  --planning                               - Enable planning mode")
                print("  --memory                                 - Enable memory")
                print("  --verbose                                - Enable verbose output")
                print("  --save                                   - Save output to file")
                print("\n[bold]Examples:[/bold]")
                print("  praisonai workflow run 'Research Blog' --tools tavily --save")
                print("  praisonai workflow run research.yaml --var topic='AI trends'")
                print("  praisonai workflow template routing --output my_workflow.yaml")
            else:
                print(f"[red]Unknown workflow action: {action}[/red]")
                print("Use 'praisonai workflow help' for available commands")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import workflow module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Workflow command failed: {e}[/red]")

    def _run_yaml_workflow(self, yaml_file: str, action_args: list, variables: dict = None, args=None):
        """
        Run a YAML workflow file using the new YAMLWorkflowParser.
        
        Args:
            yaml_file: Path to the YAML workflow file
            action_args: Additional arguments
            variables: Workflow variables
            args: Parsed command line arguments
        """
        # Initialize trace variables for cleanup
        trace_writer = None
        trace_emitter = None
        trace_emitter_token = None
        
        try:
            from praisonaiagents.workflows import WorkflowManager
            from rich import print
            from rich.table import Table
            from rich.console import Console
            import uuid
            
            console = Console()
            manager = WorkflowManager()
            
            # Parse --var arguments from action_args
            parsed_vars = variables or {}
            i = 0
            while i < len(action_args):
                if action_args[i] == "--var" and i + 1 < len(action_args):
                    var_str = action_args[i + 1]
                    if "=" in var_str:
                        key, value = var_str.split("=", 1)
                        parsed_vars[key.strip()] = value.strip()
                    i += 2
                else:
                    i += 1
            
            # Get verbose flag
            verbose = '--verbose' in action_args or '-v' in action_args or (getattr(args, 'verbose', False) if args else False)
            
            # Get save flag for replay trace
            save_replay = '--save' in action_args or '-s' in action_args or (getattr(args, 'save', False) if args else False)
            
            # Initialize replay trace writer if --save flag is set
            run_id = f"run-{uuid.uuid4().hex[:12]}"
            if save_replay:
                try:
                    from praisonai.replay import ContextTraceWriter
                    from praisonaiagents.trace.context_events import ContextTraceEmitter, set_context_emitter
                    from pathlib import Path
                    
                    trace_writer = ContextTraceWriter(session_id=run_id)
                    trace_emitter = ContextTraceEmitter(sink=trace_writer, session_id=run_id)
                    # Set as global emitter so agents can access it
                    trace_emitter_token = set_context_emitter(trace_emitter)
                    trace_emitter.session_start({"workflow": yaml_file, "run_id": run_id})
                    print(f"[cyan]📝 Replay trace enabled: {run_id}[/cyan]")
                except ImportError as e:
                    import logging
                    logging.debug(f"Replay module not available: {e}")
                except Exception as e:
                    import logging
                    logging.warning(f"Failed to initialize trace writer: {e}")
            
            print(f"[bold cyan]Running YAML workflow: {yaml_file}[/bold cyan]")
            if parsed_vars:
                print(f"[cyan]Variables: {parsed_vars}[/cyan]")
            
            # Auto-load tools.py from recipe directory if present
            import importlib.util
            from pathlib import Path
            
            yaml_path = Path(yaml_file).resolve()
            tools_file = yaml_path.parent / "tools.py"
            tool_registry = {}
            
            if tools_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location("recipe_tools", str(tools_file))
                    tools_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(tools_module)
                    
                    # Build registry from public callable functions
                    for name, obj in vars(tools_module).items():
                        if callable(obj) and not name.startswith('_'):
                            tool_registry[name] = obj
                    
                    if tool_registry:
                        print(f"[cyan]Loaded {len(tool_registry)} tools from tools.py: {', '.join(tool_registry.keys())}[/cyan]")
                except Exception as e:
                    print(f"[yellow]Warning: Failed to load tools.py: {e}[/yellow]")
            
            # Load and execute the YAML workflow with tool registry
            workflow = manager.load_yaml(yaml_file, tool_registry=tool_registry)
            
            # Show workflow info
            table = Table(title=f"Workflow: {workflow.name}")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Steps", str(len(workflow.steps)))
            table.add_row("Planning", str(workflow.planning))
            table.add_row("Reasoning", str(workflow.reasoning))
            console.print(table)
            
            # Merge variables
            if parsed_vars:
                workflow.variables.update(parsed_vars)
            
            # Set verbose
            if verbose:
                workflow.verbose = True
            
            # Set context management from CLI args
            context_auto_compact = getattr(args, 'context_auto_compact', None) if args else None
            context_strategy = getattr(args, 'context_strategy', None) if args else None
            context_threshold = getattr(args, 'context_threshold', None) if args else None
            
            if context_auto_compact is True or context_strategy or context_threshold:
                # Enable context management with CLI-specified options
                try:
                    from praisonaiagents.context import ManagerConfig
                    config_kwargs = {"auto_compact": True}
                    if context_strategy:
                        from praisonaiagents.context import OptimizerStrategy
                        strategy_map = {
                            "truncate": OptimizerStrategy.TRUNCATE,
                            "sliding_window": OptimizerStrategy.SLIDING_WINDOW,
                            "prune_tools": OptimizerStrategy.PRUNE_TOOLS,
                            "summarize": OptimizerStrategy.SUMMARIZE,
                            "smart": OptimizerStrategy.SMART,
                        }
                        config_kwargs["strategy"] = strategy_map.get(context_strategy, OptimizerStrategy.SMART)
                    if context_threshold:
                        config_kwargs["compact_threshold"] = context_threshold
                    workflow.context = ManagerConfig(**config_kwargs)
                    print(f"[cyan]Context management enabled (strategy={context_strategy or 'smart'}, threshold={context_threshold or 0.8})[/cyan]")
                except ImportError:
                    print("[yellow]Warning: Context management not available[/yellow]")
            
            # Execute
            print("\n[bold]Executing workflow...[/bold]\n")
            result = workflow.start("")
            
            if result.get("status") == "completed":
                print("\n[green]✅ Workflow completed successfully![/green]")
                
                # Show output
                if result.get("output"):
                    print("\n[bold]Output:[/bold]")
                    output = result["output"]
                    if len(output) > 2000:
                        print(output[:2000] + "...")
                    else:
                        print(output)
            else:
                print(f"\n[red]❌ Workflow failed: {result.get('error', 'Unknown error')}[/red]")
            
            # Close trace writer on completion
            if trace_emitter:
                trace_emitter.session_end()
                print(f"[cyan]📝 Replay trace saved: {run_id}[/cyan]")
            if trace_writer:
                trace_writer.close()
            # Reset global emitter
            if trace_emitter_token:
                from praisonaiagents.trace.context_events import reset_context_emitter
                reset_context_emitter(trace_emitter_token)
                
        except FileNotFoundError:
            # Cleanup trace on error
            if trace_emitter:
                trace_emitter.session_end()
            if trace_writer:
                trace_writer.close()
            if trace_emitter_token:
                from praisonaiagents.trace.context_events import reset_context_emitter
                reset_context_emitter(trace_emitter_token)
            print(f"[red]ERROR: YAML file not found: {yaml_file}[/red]")
        except Exception as e:
            # Cleanup trace on error
            if trace_emitter:
                trace_emitter.session_end()
            if trace_writer:
                trace_writer.close()
            if trace_emitter_token:
                from praisonaiagents.trace.context_events import reset_context_emitter
                reset_context_emitter(trace_emitter_token)
            print(f"[red]ERROR: YAML workflow failed: {e}[/red]")
            import traceback
            traceback.print_exc()

    def _validate_yaml_workflow(self, yaml_file: str):
        """
        Validate a YAML workflow file.
        
        Args:
            yaml_file: Path to the YAML workflow file
        """
        try:
            from praisonaiagents.workflows import YAMLWorkflowParser
            from rich import print
            from rich.table import Table
            from rich.console import Console
            import yaml
            
            console = Console()
            
            if not os.path.exists(yaml_file):
                print(f"[red]ERROR: File not found: {yaml_file}[/red]")
                return
            
            print(f"[cyan]Validating: {yaml_file}[/cyan]")
            
            # Load raw YAML to check for non-canonical names
            with open(yaml_file, 'r') as f:
                raw_data = yaml.safe_load(f)
            
            # Check for non-canonical names and suggest canonical ones
            suggestions = self._get_canonical_suggestions(raw_data)
            
            parser = YAMLWorkflowParser()
            workflow = parser.parse_file(yaml_file)
            
            # Show validation results
            table = Table(title="Workflow Validation")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Name", workflow.name)
            table.add_row("Description", getattr(workflow, 'description', 'N/A'))
            table.add_row("Steps", str(len(workflow.steps)))
            table.add_row("Variables", str(len(workflow.variables)))
            table.add_row("Planning", str(workflow.planning))
            table.add_row("Reasoning", str(workflow.reasoning))
            
            console.print(table)
            print("[green]✓ Workflow is valid![/green]")
            
            # Show suggestions for canonical names
            if suggestions:
                print()
                print("[yellow]💡 Suggestions for canonical field names:[/yellow]")
                for suggestion in suggestions:
                    print(f"   [dim]•[/dim] {suggestion}")
                print()
                print("[dim]Note: Both old and new names work, but canonical names are recommended.[/dim]")
            
        except Exception as e:
            print(f"[red]✗ Validation failed: {e}[/red]")
    
    def _get_canonical_suggestions(self, data: dict) -> list:
        """
        Check for non-canonical field names and return suggestions.
        
        Canonical names (A-I-G-S mnemonic):
        - Agents (not roles)
        - Instructions (not backstory)
        - Goal (same)
        - Steps (not tasks)
        
        Also:
        - name (not topic)
        - action (not description)
        
        Args:
            data: Raw YAML data
            
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        if not data:
            return suggestions
        
        # Check top-level keys
        if 'roles' in data:
            suggestions.append("Use 'agents' instead of 'roles'")
        
        if 'topic' in data and 'name' not in data:
            suggestions.append("Use 'name' instead of 'topic'")
        
        # Check agent fields
        agents_data = data.get('agents', data.get('roles', {}))
        for agent_id, agent_config in agents_data.items():
            if isinstance(agent_config, dict):
                if 'backstory' in agent_config:
                    suggestions.append(f"Agent '{agent_id}': Use 'instructions' instead of 'backstory'")
                
                # Check nested tasks
                if 'tasks' in agent_config:
                    suggestions.append(f"Agent '{agent_id}': Use 'steps' at top level instead of nested 'tasks'")
        
        # Check step fields
        steps_data = data.get('steps', [])
        for i, step in enumerate(steps_data):
            if isinstance(step, dict):
                if 'description' in step and 'action' not in step:
                    step_name = step.get('name', f'step {i+1}')
                    suggestions.append(f"Step '{step_name}': Use 'action' instead of 'description'")
                
                # Check parallel steps
                if 'parallel' in step:
                    for j, parallel_step in enumerate(step['parallel']):
                        if isinstance(parallel_step, dict):
                            if 'description' in parallel_step and 'action' not in parallel_step:
                                suggestions.append(f"Parallel step {j+1}: Use 'action' instead of 'description'")
        
        return suggestions

    def _create_workflow_from_template(self, template_name: str = None, output_file: str = None):
        """
        Create a workflow from a template.
        
        Uses templates from WorkflowHandler to avoid duplication.
        
        Args:
            template_name: Name of the template
            output_file: Output file path
        """
        from rich import print
        
        # Use templates from WorkflowHandler to avoid duplication
        try:
            from .features.workflow import WorkflowHandler
            templates = WorkflowHandler.TEMPLATES
        except ImportError:
            print("[red]ERROR: WorkflowHandler not available.[/red]")
            return
        
        if not template_name:
            print("[red]ERROR: Template name required.[/red]")
            print(f"[cyan]Available templates: {', '.join(templates.keys())}[/cyan]")
            return
        
        if template_name not in templates:
            print(f"[red]ERROR: Unknown template: {template_name}[/red]")
            print(f"[cyan]Available templates: {', '.join(templates.keys())}[/cyan]")
            return
        
        # Default output file
        if not output_file:
            output_file = f"{template_name}_workflow.yaml"
        
        # Check if file exists
        if os.path.exists(output_file):
            print(f"[red]ERROR: File already exists: {output_file}[/red]")
            return
        
        # Write template
        with open(output_file, 'w') as f:
            f.write(templates[template_name])
        
        print(f"[green]✓ Created workflow: {output_file}[/green]")
        print(f"[cyan]Run with: praisonai workflow run {output_file}[/cyan]")

    def _auto_generate_workflow(self, action_args: list):
        """
        Auto-generate a workflow from a topic description.
        
        Args:
            action_args: ["topic description", --pattern, <pattern>, --output, <file.yaml>]
        """
        from rich import print
        
        # Parse arguments
        topic = None
        pattern = "sequential"
        output_file = None
        
        i = 0
        while i < len(action_args):
            if action_args[i] == "--pattern" and i + 1 < len(action_args):
                pattern = action_args[i + 1]
                i += 2
            elif action_args[i] == "--output" and i + 1 < len(action_args):
                output_file = action_args[i + 1]
                i += 2
            elif not action_args[i].startswith("--") and topic is None:
                topic = action_args[i]
                i += 1
            else:
                i += 1
        
        if not topic:
            print('[red]Usage: praisonai workflow auto "topic" --pattern <pattern>[/red]')
            print("[cyan]Patterns: sequential, routing, parallel[/cyan]")
            return
        
        # Validate pattern
        valid_patterns = ["sequential", "routing", "parallel", "loop", "orchestrator-workers", "evaluator-optimizer"]
        if pattern not in valid_patterns:
            print(f"[red]Unknown pattern: {pattern}[/red]")
            print(f"[cyan]Valid patterns: {', '.join(valid_patterns)}[/cyan]")
            return
        
        # Default output file
        if not output_file:
            safe_name = "".join(c if c.isalnum() else "_" for c in topic[:30]).lower()
            output_file = f"{safe_name}_workflow.yaml"
        
        # Check if file exists
        if os.path.exists(output_file):
            print(f"[red]ERROR: File already exists: {output_file}[/red]")
            return
        
        print(f"[cyan]Generating {pattern} workflow for: {topic}[/cyan]")
        
        try:
            from praisonai.auto import WorkflowAutoGenerator
            
            generator = WorkflowAutoGenerator(
                topic=topic,
                workflow_file=output_file
            )
            
            result_path = generator.generate(pattern=pattern)
            
            print(f"[green]✓ Created workflow: {result_path}[/green]")
            print(f"[cyan]Run with: praisonai workflow run {output_file}[/cyan]")
            
        except ImportError:
            print("[red]Auto-generation requires litellm: pip install litellm[/red]")
        except Exception as e:
            print(f"[red]Generation failed: {e}[/red]")

    def handle_hooks_command(self, action: str):
        """
        Handle hooks subcommand actions.
        
        Args:
            action: The hooks action (list, stats, init)
        """
        try:
            from praisonaiagents.memory import HooksManager
            from rich import print
            from rich.table import Table
            from rich.console import Console
            import json
            
            console = Console()
            hooks = HooksManager(workspace_path=os.getcwd())
            
            if action == 'list':
                stats = hooks.get_stats()
                if stats.get('total_hooks', 0) > 0:
                    print("[bold]Configured Hooks:[/bold]")
                    for event in stats.get('events', []):
                        print(f"  - {event}")
                else:
                    print("[yellow]No hooks configured. Create .praison/hooks.json[/yellow]")
                    
            elif action == 'stats':
                stats = hooks.get_stats()
                table = Table(title="Hooks Statistics")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")
                
                for key, value in stats.items():
                    table.add_row(str(key), str(value))
                
                console.print(table)
                
            elif action == 'init':
                hooks_dir = os.path.join(os.getcwd(), ".praison")
                os.makedirs(hooks_dir, exist_ok=True)
                hooks_file = os.path.join(hooks_dir, "hooks.json")
                
                if os.path.exists(hooks_file):
                    print(f"[yellow]hooks.json already exists at {hooks_file}[/yellow]")
                else:
                    template = {
                        "enabled": True,
                        "timeout": 30,
                        "hooks": {
                            "pre_write_code": "./scripts/lint.sh",
                            "post_write_code": "./scripts/format.sh",
                            "pre_run_command": {
                                "command": "./scripts/validate.sh",
                                "timeout": 60,
                                "block_on_failure": True
                            }
                        }
                    }
                    with open(hooks_file, 'w') as f:
                        json.dump(template, f, indent=2)
                    print(f"[green]✅ Created hooks.json at {hooks_file}[/green]")
                    print("[cyan]Edit the file to configure your hooks[/cyan]")
                    
            elif action == 'help' or action == '--help':
                print("[bold]Hooks Commands:[/bold]")
                print("  praisonai hooks list                     - List configured hooks")
                print("  praisonai hooks stats                    - Show hooks statistics")
                print("  praisonai hooks init                     - Create hooks.json template")
                print("\n[bold]Hook Events:[/bold]")
                print("  pre_read_code, post_read_code")
                print("  pre_write_code, post_write_code")
                print("  pre_run_command, post_run_command")
                print("  pre_user_prompt, post_user_prompt")
                print("  pre_mcp_tool_use, post_mcp_tool_use")
            else:
                print(f"[red]Unknown hooks action: {action}[/red]")
                print("Use 'praisonai hooks help' for available commands")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import hooks module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Hooks command failed: {e}[/red]")

    def handle_knowledge_command(self, action: str, action_args: list):
        """
        Handle knowledge subcommand actions.
        
        Args:
            action: The knowledge action (add, query, list, clear, stats, help)
            action_args: Additional arguments for the action (may include flags)
        """
        try:
            from .features.knowledge import KnowledgeHandler
            
            # Parse flags from action_args
            vector_store = "chroma"
            retrieval_strategy = "basic"
            reranker = None
            index_type = "vector"
            query_mode = "default"
            session_id = None
            db = None
            workspace = os.getcwd()
            
            # Filter out flags and extract values
            filtered_args = []
            i = 0
            while i < len(action_args):
                arg = action_args[i]
                if arg in ("--vector-store", "--store"):
                    if i + 1 < len(action_args):
                        vector_store = action_args[i + 1]
                        i += 2
                        continue
                elif arg in ("--retrieval-strategy", "--retrieval", "--strategy"):
                    if i + 1 < len(action_args):
                        retrieval_strategy = action_args[i + 1]
                        i += 2
                        continue
                elif arg == "--reranker":
                    if i + 1 < len(action_args):
                        reranker = action_args[i + 1]
                        i += 2
                        continue
                elif arg in ("--index-type", "--index"):
                    if i + 1 < len(action_args):
                        index_type = action_args[i + 1]
                        i += 2
                        continue
                elif arg in ("--query-mode", "--mode"):
                    if i + 1 < len(action_args):
                        query_mode = action_args[i + 1]
                        i += 2
                        continue
                elif arg == "--session":
                    if i + 1 < len(action_args):
                        session_id = action_args[i + 1]
                        i += 2
                        continue
                elif arg == "--db":
                    if i + 1 < len(action_args):
                        db = action_args[i + 1]
                        i += 2
                        continue
                elif arg == "--workspace":
                    if i + 1 < len(action_args):
                        workspace = action_args[i + 1]
                        i += 2
                        continue
                filtered_args.append(arg)
                i += 1
            
            handler = KnowledgeHandler(
                verbose=True,
                workspace=workspace,
                vector_store=vector_store,
                retrieval_strategy=retrieval_strategy,
                reranker=reranker,
                index_type=index_type,
                query_mode=query_mode,
                session_id=session_id,
                db=db
            )
            handler.execute(action, filtered_args)
        except ImportError as e:
            print(f"[red]ERROR: Failed to import knowledge module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Knowledge command failed: {e}[/red]")

    def handle_session_command(self, action: str, action_args: list):
        """
        Handle session subcommand actions.
        
        Args:
            action: The session action (start, list, resume, delete, info)
            action_args: Additional arguments for the action
        """
        try:
            from .features.session import SessionHandler
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
            from .features.tools import ToolsHandler
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
            from .features.todo import TodoHandler
            handler = TodoHandler(verbose=True)
            handler.execute(action, action_args)
        except ImportError as e:
            print(f"[red]ERROR: Failed to import todo module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Todo command failed: {e}[/red]")

    def handle_docs_command(self, action: str, action_args: list):
        """
        Handle docs subcommand actions.
        
        Args:
            action: The docs action (list, show, create, delete, run, run-all, stats, etc.)
            action_args: Additional arguments for the action
        """
        # Code validation commands - delegate to typer app
        # Also handle 'cli' subcommand group for CLI validation
        code_validation_actions = {'run', 'run-all', 'stats', 'report', 'generate', 'serve', 'cli'}
        if action in code_validation_actions:
            from praisonai.cli.commands.docs import app as docs_app
            import typer
            # Build args list for typer
            typer_args = [action] + action_args
            try:
                typer.main.get_command(docs_app)(typer_args)
            except SystemExit as e:
                sys.exit(e.code if e.code is not None else 0)
            return
        
        try:
            from praisonaiagents.memory import DocsManager
            from rich import print
            from rich.table import Table
            from rich.console import Console
            
            console = Console()
            docs = DocsManager(workspace_path=os.getcwd())
            
            if action == 'list':
                all_docs = docs.list_docs()
                if all_docs:
                    table = Table(title="Project Documentation")
                    table.add_column("Name", style="cyan")
                    table.add_column("Description", style="white")
                    table.add_column("Priority", style="yellow")
                    table.add_column("Tags", style="green")
                    table.add_column("Scope", style="magenta")
                    
                    for doc in all_docs:
                        table.add_row(
                            doc["name"],
                            doc["description"][:40] + "..." if len(doc["description"]) > 40 else doc["description"],
                            str(doc["priority"]),
                            ", ".join(doc["tags"][:3]) if doc["tags"] else "",
                            doc["scope"]
                        )
                    
                    console.print(table)
                else:
                    print("[yellow]No docs found. Create files in .praison/docs/[/yellow]")
                    
            elif action == 'show':
                if not action_args:
                    print("[red]ERROR: Doc name required. Usage: praisonai docs show <name>[/red]")
                    return
                doc_name = action_args[0]
                doc = docs.get_doc(doc_name)
                if doc:
                    print(f"[bold cyan]Doc: {doc.name}[/bold cyan]")
                    print(f"[bold]Description:[/bold] {doc.description}")
                    print(f"[bold]Priority:[/bold] {doc.priority}")
                    if doc.tags:
                        print(f"[bold]Tags:[/bold] {', '.join(doc.tags)}")
                    print(f"\n[bold]Content:[/bold]\n{doc.content}")
                else:
                    print(f"[red]Doc not found: {doc_name}[/red]")
                    
            elif action == 'create':
                if len(action_args) < 2:
                    print("[red]ERROR: Name and content required. Usage: praisonai docs create <name> <content>[/red]")
                    return
                doc_name = action_args[0]
                content = ' '.join(action_args[1:])
                docs.create_doc(
                    name=doc_name,
                    content=content,
                    description=f"Doc created via CLI: {doc_name}",
                    scope="workspace"
                )
                print(f"[green]✅ Doc created: {doc_name}[/green]")
                
            elif action == 'delete':
                if not action_args:
                    print("[red]ERROR: Doc name required. Usage: praisonai docs delete <name>[/red]")
                    return
                doc_name = action_args[0]
                if docs.delete_doc(doc_name):
                    print(f"[green]✅ Doc deleted: {doc_name}[/green]")
                else:
                    print(f"[red]Doc not found: {doc_name}[/red]")
                
            elif action == 'help' or action == '--help':
                print("[bold]Docs Commands:[/bold]")
                print("  praisonai docs list                     - List all docs")
                print("  praisonai docs show <name>              - Show specific doc")
                print("  praisonai docs create <name> <content>  - Create a new doc")
                print("  praisonai docs delete <name>            - Delete a doc")
                print("\n[bold]Doc Location:[/bold]")
                print("  .praison/docs/*.md, ~/.praison/docs/*.md")
            else:
                print(f"[red]Unknown docs action: {action}[/red]")
                print("Use 'praisonai docs help' for available commands")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import docs module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: Docs command failed: {e}[/red]")

    def handle_mcp_command(self, action: str, action_args: list):
        """
        Handle mcp subcommand actions.
        
        Args:
            action: The mcp action (list, show, create, delete, enable, disable)
            action_args: Additional arguments for the action
        """
        try:
            from praisonaiagents.memory import MCPConfigManager
            from rich import print
            from rich.table import Table
            from rich.console import Console
            
            console = Console()
            mcp = MCPConfigManager(workspace_path=os.getcwd())
            
            if action == 'list':
                all_configs = mcp.list_configs()
                if all_configs:
                    table = Table(title="MCP Server Configurations")
                    table.add_column("Name", style="cyan")
                    table.add_column("Command", style="white")
                    table.add_column("Enabled", style="green")
                    table.add_column("Scope", style="magenta")
                    table.add_column("Description", style="yellow")
                    
                    for config in all_configs:
                        table.add_row(
                            config["name"],
                            config["command"],
                            "✅" if config["enabled"] else "❌",
                            config["scope"],
                            config["description"][:30] + "..." if len(config["description"]) > 30 else config["description"]
                        )
                    
                    console.print(table)
                else:
                    print("[yellow]No MCP configs found. Create files in .praison/mcp/[/yellow]")
                    
            elif action == 'show':
                if not action_args:
                    print("[red]ERROR: Config name required. Usage: praisonai mcp show <name>[/red]")
                    return
                config_name = action_args[0]
                config = mcp.get_config(config_name)
                if config:
                    print(f"[bold cyan]MCP Config: {config.name}[/bold cyan]")
                    print(f"[bold]Command:[/bold] {config.command}")
                    print(f"[bold]Args:[/bold] {' '.join(config.args)}")
                    print(f"[bold]Enabled:[/bold] {'Yes' if config.enabled else 'No'}")
                    print(f"[bold]Description:[/bold] {config.description}")
                    if config.env:
                        print("[bold]Environment:[/bold]")
                        for key, value in config.env.items():
                            # Mask sensitive values
                            masked = value[:4] + "..." if len(value) > 8 else "***"
                            print(f"  {key}: {masked}")
                else:
                    print(f"[red]MCP config not found: {config_name}[/red]")
                    
            elif action == 'create':
                if len(action_args) < 2:
                    print("[red]ERROR: Name and command required. Usage: praisonai mcp create <name> <command> [args...][/red]")
                    return
                config_name = action_args[0]
                command = action_args[1]
                args = action_args[2:] if len(action_args) > 2 else []
                mcp.create_config(
                    name=config_name,
                    command=command,
                    args=args,
                    description="MCP server created via CLI",
                    scope="workspace"
                )
                print(f"[green]✅ MCP config created: {config_name}[/green]")
                
            elif action == 'delete':
                if not action_args:
                    print("[red]ERROR: Config name required. Usage: praisonai mcp delete <name>[/red]")
                    return
                config_name = action_args[0]
                if mcp.delete_config(config_name):
                    print(f"[green]✅ MCP config deleted: {config_name}[/green]")
                else:
                    print(f"[red]MCP config not found: {config_name}[/red]")
                    
            elif action == 'enable':
                if not action_args:
                    print("[red]ERROR: Config name required. Usage: praisonai mcp enable <name>[/red]")
                    return
                config_name = action_args[0]
                if mcp.enable_config(config_name):
                    print(f"[green]✅ MCP config enabled: {config_name}[/green]")
                else:
                    print(f"[red]MCP config not found: {config_name}[/red]")
                    
            elif action == 'disable':
                if not action_args:
                    print("[red]ERROR: Config name required. Usage: praisonai mcp disable <name>[/red]")
                    return
                config_name = action_args[0]
                if mcp.disable_config(config_name):
                    print(f"[green]✅ MCP config disabled: {config_name}[/green]")
                else:
                    print(f"[red]MCP config not found: {config_name}[/red]")
                
            elif action == 'serve':
                # Start MCP server
                from praisonai.mcp_server.cli import handle_mcp_command as mcp_serve_handler
                exit_code = mcp_serve_handler(['serve'] + action_args)
                sys.exit(exit_code)
            
            elif action == 'list-tools':
                # List MCP tools
                from praisonai.mcp_server.cli import handle_mcp_command as mcp_serve_handler
                exit_code = mcp_serve_handler(['list-tools'] + action_args)
                sys.exit(exit_code)
            
            elif action == 'config-generate':
                # Generate client config
                from praisonai.mcp_server.cli import handle_mcp_command as mcp_serve_handler
                exit_code = mcp_serve_handler(['config-generate'] + action_args)
                sys.exit(exit_code)
            
            elif action == 'help' or action == '--help':
                print("[bold]MCP Commands:[/bold]")
                print("\n[bold cyan]Server Commands:[/bold cyan]")
                print("  praisonai mcp serve                             - Start MCP server (STDIO)")
                print("  praisonai mcp serve --transport http-stream     - Start HTTP Stream server")
                print("  praisonai mcp list-tools                        - List available MCP tools")
                print("  praisonai mcp config-generate --client claude-desktop  - Generate client config")
                print("\n[bold cyan]Config Management:[/bold cyan]")
                print("  praisonai mcp list                              - List all MCP configs")
                print("  praisonai mcp show <name>                       - Show specific config")
                print("  praisonai mcp create <name> <cmd> [args...]     - Create a new config")
                print("  praisonai mcp delete <name>                     - Delete a config")
                print("  praisonai mcp enable <name>                     - Enable a config")
                print("  praisonai mcp disable <name>                    - Disable a config")
                print("\n[bold]Config Location:[/bold]")
                print("  .praison/mcp/*.json, ~/.praison/mcp/*.json")
                print("\n[bold]Examples:[/bold]")
                print("  praisonai mcp serve --transport stdio")
                print("  praisonai mcp serve --transport http-stream --port 8080")
                print("  praisonai mcp create filesystem npx -y @modelcontextprotocol/server-filesystem .")
            else:
                print(f"[red]Unknown mcp action: {action}[/red]")
                print("Use 'praisonai mcp help' for available commands")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import mcp module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: MCP command failed: {e}[/red]")

    # Compiled regex patterns for sensitive data detection (compiled once, zero runtime cost)
    _SENSITIVE_PATTERNS = None
    
    @classmethod
    def _get_sensitive_patterns(cls):
        """Lazy-load and compile sensitive patterns only when needed."""
        if cls._SENSITIVE_PATTERNS is None:
            import re
            cls._SENSITIVE_PATTERNS = [
                # API Keys and Tokens
                (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "API Key"),
                (re.compile(r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Secret Key"),
                (re.compile(r'(?i)(access[_-]?token|accesstoken)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Access Token"),
                (re.compile(r'(?i)(auth[_-]?token|authtoken)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Auth Token"),
                # AWS
                (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key ID"),
                (re.compile(r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']?[a-zA-Z0-9/+=]{40}'), "AWS Secret Key"),
                # Passwords
                (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}'), "Password"),
                (re.compile(r'(?i)db[_-]?password\s*[=:]\s*["\']?[^\s"\']+'), "Database Password"),
                # Private Keys
                (re.compile(r'-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----'), "Private Key"),
                (re.compile(r'-----BEGIN PGP PRIVATE KEY BLOCK-----'), "PGP Private Key"),
                # GitHub/GitLab tokens
                (re.compile(r'ghp_[a-zA-Z0-9]{36}'), "GitHub Personal Access Token"),
                (re.compile(r'gho_[a-zA-Z0-9]{36}'), "GitHub OAuth Token"),
                (re.compile(r'glpat-[a-zA-Z0-9\-]{20,}'), "GitLab Personal Access Token"),
                # Slack
                (re.compile(r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}'), "Slack Token"),
                # Generic secrets
                (re.compile(r'(?i)(client[_-]?secret)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Client Secret"),
                (re.compile(r'(?i)(private[_-]?key)\s*[=:]\s*["\']?[a-zA-Z0-9_\-/+=]{20,}'), "Private Key Value"),
            ]
        return cls._SENSITIVE_PATTERNS
    
    # Sensitive file patterns (simple string matching - very fast)
    _SENSITIVE_FILES = {'.env', '.env.local', '.env.production', '.env.development',
                        'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
                        '.pem', '.key', '.p12', '.pfx', 'credentials', 'secrets.json',
                        'secrets.yaml', 'secrets.yml', '.htpasswd', '.netrc'}
    _SENSITIVE_EXTENSIONS = {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore'}

    def _check_sensitive_content(self, diff_content: str, staged_files: list) -> list:
        """
        Check for sensitive content in staged changes.
        
        Args:
            diff_content: The git diff content
            staged_files: List of staged file names
            
        Returns:
            List of (file, issue_type, match) tuples for detected issues
        """
        issues = []
        
        # Quick check for sensitive files by name/extension
        for file_path in staged_files:
            file_name = file_path.split('/')[-1].lower()
            # Check exact file names
            if file_name in self._SENSITIVE_FILES:
                issues.append((file_path, "Sensitive File", file_name))
                continue
            # Check extensions
            for ext in self._SENSITIVE_EXTENSIONS:
                if file_name.endswith(ext):
                    issues.append((file_path, "Sensitive Extension", ext))
                    break
        
        # Only scan diff content if it's not too large (performance guard)
        if len(diff_content) < 50000:
            patterns = self._get_sensitive_patterns()
            # Scan only added lines (lines starting with +)
            for line in diff_content.split('\n'):
                if line.startswith('+') and not line.startswith('+++'):
                    for pattern, issue_type in patterns:
                        match = pattern.search(line)
                        if match:
                            # Truncate match for display
                            matched_text = match.group(0)[:50] + '...' if len(match.group(0)) > 50 else match.group(0)
                            issues.append(("diff", issue_type, matched_text))
                            break  # One issue per line is enough
        
        return issues

    def handle_commit_command(self, args: list):
        """
        Handle AI commit message generation.
        
        Generates a commit message based on staged changes using AI.
        
        Args:
            args: Additional arguments:
                --push: Auto-push after commit
                -a, --auto: Full auto mode (stage, commit, push) - aborts on security issues
                --no-verify: Skip sensitive content check
        """
        try:
            import subprocess
            from rich import print
            from praisonaiagents import Agent
            
            # Check if we're in a git repository
            try:
                subprocess.run(["git", "rev-parse", "--git-dir"], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                print("[red]ERROR: Not in a git repository[/red]")
                return
            
            # Handle auto mode
            auto_mode = '-a' in args or '--auto' in args
            if auto_mode:
                print("[cyan]Auto-staging all changes...[/cyan]")
                subprocess.run(["git", "add", "-A"], capture_output=True)
            
            # Get staged diff
            result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                capture_output=True,
                text=True
            )
            
            if not result.stdout.strip():
                print("[yellow]No staged changes. Use 'git add' to stage files first, or use -a/--auto.[/yellow]")
                return
            
            # Get detailed diff for context
            diff_result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True,
                text=True
            )
            
            # Limit diff size for context
            diff_content = diff_result.stdout[:8000] if len(diff_result.stdout) > 8000 else diff_result.stdout
            
            # Security check for sensitive content (unless --no-verify)
            if '--no-verify' not in args:
                # Extract staged file names from stat output
                staged_files = [line.split('|')[0].strip() for line in result.stdout.strip().split('\n') if '|' in line]
                issues = self._check_sensitive_content(diff_result.stdout, staged_files)
                
                if issues:
                    print("\n[bold red]⚠️  SECURITY WARNING: Sensitive content detected![/bold red]")
                    for file_path, issue_type, match in issues:
                        print(f"  [red]• {issue_type}[/red] in [yellow]{file_path}[/yellow]: {match}")
                    print("\n[yellow]Options:[/yellow]")
                    print("  [c] Continue anyway (not recommended)")
                    print("  [a] Abort commit")
                    print("  [i] Ignore and add to .gitignore")
                    
                    # In auto mode, abort on security issues
                    if auto_mode:
                        print("[red]Auto mode aborted due to security concerns. Use --no-verify to skip.[/red]")
                        return
                    
                    sec_choice = input("\nYour choice [c/a/i]: ").strip().lower()
                    if sec_choice == 'a':
                        print("[yellow]Commit aborted due to security concerns.[/yellow]")
                        return
                    elif sec_choice == 'i':
                        # Add sensitive files to .gitignore
                        sensitive_file_paths = [f for f, t, _ in issues if t in ("Sensitive File", "Sensitive Extension")]
                        if sensitive_file_paths:
                            with open('.gitignore', 'a') as gi:
                                gi.write('\n# Auto-added by praisonai commit\n')
                                for fp in sensitive_file_paths:
                                    gi.write(f'{fp}\n')
                            print(f"[green]Added {len(sensitive_file_paths)} file(s) to .gitignore[/green]")
                            # Unstage the sensitive files
                            subprocess.run(["git", "reset", "HEAD", "--"] + sensitive_file_paths, capture_output=True)
                            print("[cyan]Unstaged sensitive files. Please re-run commit.[/cyan]")
                            return
                    # else continue
                    print("[yellow]Proceeding despite security warnings...[/yellow]")
            
            print("[bold]Staged changes:[/bold]")
            print(result.stdout)
            print("\n[bold]Generating commit message...[/bold]")
            
            # Create agent for commit message generation
            agent = Agent(
                name="CommitMessageGenerator",
                role="Git Commit Message Writer",
                goal="Generate clear, concise, and conventional commit messages",
                instructions="""You are an expert at writing git commit messages.
                
Follow the Conventional Commits specification:
- feat: A new feature
- fix: A bug fix
- docs: Documentation changes
- style: Code style changes (formatting, etc.)
- refactor: Code refactoring
- test: Adding or updating tests
- chore: Maintenance tasks

Format:
<type>(<scope>): <short description>

<optional body with more details>

Keep the first line under 72 characters.
Be specific about what changed and why.""",
                llm=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
            )
            
            prompt = f"""Generate a commit message for these changes:

{result.stdout}

Detailed diff:
{diff_content}

Provide ONLY the commit message, no explanations."""

            response = agent.chat(prompt)
            commit_message = response.strip()
            
            print("\n[bold green]Suggested commit message:[/bold green]")
            print(f"[cyan]{commit_message}[/cyan]")
            
            # In auto mode, skip confirmation and commit + push
            if auto_mode:
                subprocess.run(["git", "commit", "-m", commit_message], check=True)
                print("[green]✅ Committed successfully![/green]")
                subprocess.run(["git", "push"], check=True)
                print("[green]✅ Pushed to remote![/green]")
                return
            
            # Ask for confirmation
            print("\n[bold]Options:[/bold]")
            print("  [y] Use this message and commit")
            print("  [e] Edit the message")
            print("  [n] Cancel")
            
            choice = input("\nYour choice [y/e/n]: ").strip().lower()
            
            if choice == 'y':
                # Commit with the generated message
                subprocess.run(["git", "commit", "-m", commit_message], check=True)
                print("[green]✅ Committed successfully![/green]")
                
                # Check if --push was passed
                if '--push' in args:
                    subprocess.run(["git", "push"], check=True)
                    print("[green]✅ Pushed to remote![/green]")
                    
            elif choice == 'e':
                # Open editor with the message
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                    f.write(commit_message)
                    temp_path = f.name
                
                editor = os.environ.get('EDITOR', 'nano')
                subprocess.run([editor, temp_path])
                
                with open(temp_path, 'r') as f:
                    edited_message = f.read().strip()
                
                os.unlink(temp_path)
                
                if edited_message:
                    subprocess.run(["git", "commit", "-m", edited_message], check=True)
                    print("[green]✅ Committed successfully![/green]")
                else:
                    print("[yellow]Empty message, commit cancelled.[/yellow]")
            else:
                print("[yellow]Commit cancelled.[/yellow]")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import required module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except subprocess.CalledProcessError as e:
            print(f"[red]ERROR: Git command failed: {e}[/red]")
        except Exception as e:
            print(f"[red]ERROR: Commit command failed: {e}[/red]")

    def _save_output(self, prompt: str, result: str):
        """
        Save output to output/prompts/ folder.
        
        Args:
            prompt: The original prompt
            result: The output result to save
        """
        from datetime import datetime
        from rich import print
        
        # Create output directory
        output_dir = os.path.join(os.getcwd(), "output", "prompts")
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Create a safe filename from prompt (first 30 chars)
        safe_prompt = "".join(c if c.isalnum() or c in " -_" else "" for c in prompt[:30]).strip().replace(" ", "_")
        filename = f"{timestamp}_{safe_prompt}.md"
        filepath = os.path.join(output_dir, filename)
        
        # Write output
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Prompt\n\n{prompt}\n\n")
            f.write(f"# Output\n\n{result}\n")
        
        print(f"[green]✅ Output saved to: {filepath}[/green]")

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

    def handle_direct_prompt(self, prompt):
        """
        Handle direct prompt by creating a single agent and running it.
        
        Supports @mentions:
        - @file:path/to/file.py - Include file content
        - @web:query - Search the web
        - @doc:name - Include doc from .praison/docs/
        - @rule:name - Include specific rule
        - @url:https://... - Fetch URL content
        """
        # Check for profiling mode - use unified profiler
        if hasattr(self, 'args') and getattr(self.args, 'profile', False):
            return self._handle_profiled_prompt(prompt)
        
        # Check for inline workflow mode
        if hasattr(self, 'args') and getattr(self.args, 'workflow', None):
            return self._run_inline_workflow(prompt)
        
        # Process @mentions in the prompt
        mention_context = ""
        try:
            from praisonaiagents.tools.mentions import MentionsParser
            parser = MentionsParser(workspace_path=os.getcwd())
            if parser.has_mentions(prompt):
                mention_context, prompt = parser.process(prompt)
                if mention_context:
                    print("[bold cyan]Processing @mentions...[/bold cyan]")
        except ImportError:
            pass  # Mentions not available
        except Exception as e:
            logging.debug(f"Error processing mentions: {e}")
        
        # Apply query rewriting if enabled
        prompt = self._rewrite_query_if_enabled(prompt)
        # Apply prompt expansion if enabled
        prompt = self._expand_prompt_if_enabled(prompt)
        
        # Prepend mention context to prompt
        if mention_context:
            prompt = f"{mention_context}# Task:\n{prompt}"
        
        if PRAISONAI_AVAILABLE:
            from praisonaiagents import Agent as PraisonAgent
            
            agent_config = {
                "name": "DirectAgent",
                "role": "Assistant",
                "goal": "Complete the given task",
                "backstory": "You are a helpful AI assistant"
            }
            
            # Set output mode based on --verbose flag
            # Uses consolidated 'output' param instead of deprecated 'verbose'
            if hasattr(self, 'args') and getattr(self.args, 'verbose', False):
                agent_config["output"] = "verbose"
            else:
                agent_config["output"] = "minimal"
            
            # Load default tools (same as interactive mode) unless --no-tools is set
            if not getattr(self.args, 'no_tools', False):
                default_tools = self._load_interactive_tools()
                if default_tools:
                    agent_config["tools"] = default_tools
            else:
                agent_config["tools"] = []  # Explicitly set empty tools
            
            # Add llm if specified
            if hasattr(self, 'args') and self.args.llm:
                # Build LLM config dict
                llm_config = {"model": self.args.llm}
                
                # Add max_tokens if specified
                max_tokens = getattr(self.args, 'max_tokens', 16000)
                if max_tokens:
                    llm_config["max_tokens"] = max_tokens
                    logging.debug(f"Max tokens set to: {max_tokens}")
                
                # Add tool reliability settings (for weak models like Ollama)
                if getattr(self.args, 'max_tool_repairs', None) is not None:
                    llm_config["max_tool_repairs"] = self.args.max_tool_repairs
                if getattr(self.args, 'force_tool_usage', None) is not None:
                    llm_config["force_tool_usage"] = self.args.force_tool_usage
                
                agent_config["llm"] = llm_config
            
            # Add feature flags if enabled
            if hasattr(self, 'args'):
                if getattr(self.args, 'web_search', False):
                    agent_config["web_search"] = True
                if getattr(self.args, 'web_fetch', False):
                    agent_config["web_fetch"] = True
                if getattr(self.args, 'prompt_caching', False):
                    agent_config["prompt_caching"] = True
                
                # Load tools if specified (--tools flag)
                if getattr(self.args, 'tools', None):
                    tools_list = self._load_tools(self.args.tools)
                    if tools_list:
                        existing_tools = agent_config.get('tools', [])
                        if isinstance(existing_tools, list):
                            existing_tools.extend(tools_list)
                        else:
                            existing_tools = tools_list
                        agent_config['tools'] = existing_tools
                        print(f"[bold cyan]Tools loaded: {len(tools_list)} tool(s) available for agent[/bold cyan]")
                
                # Planning Mode
                if getattr(self.args, 'planning', False):
                    agent_config["planning"] = True
                    print("[bold cyan]Planning mode enabled - agent will create a plan before execution[/bold cyan]")
                    
                    # Load planning tools if specified
                    if getattr(self.args, 'planning_tools', None):
                        planning_tools_list = self._load_tools(self.args.planning_tools)
                        if planning_tools_list:
                            agent_config["planning_tools"] = planning_tools_list
                    # If no planning_tools but --tools is specified, use those for planning too
                    elif getattr(self.args, 'tools', None) and agent_config.get('tools'):
                        agent_config["planning_tools"] = agent_config['tools']
                        print("[cyan]Using --tools for planning as well[/cyan]")
                    
                    if getattr(self.args, 'planning_reasoning', False):
                        agent_config["planning_reasoning"] = True
                
                # Memory
                if getattr(self.args, 'memory', False):
                    agent_config["memory"] = True
                    print("[bold cyan]Memory enabled - agent will remember context across sessions[/bold cyan]")
                    
                    if getattr(self.args, 'user_id', None):
                        agent_config["user_id"] = self.args.user_id
                
                # Session management
                if getattr(self.args, 'auto_save', None):
                    agent_config["memory"] = True  # Auto-save requires memory
                    agent_config["auto_save"] = self.args.auto_save
                    print(f"[bold cyan]Auto-save enabled - session will be saved as '{self.args.auto_save}'[/bold cyan]")
                
                if getattr(self.args, 'history', None):
                    agent_config["memory"] = True  # History requires memory
                    # Note: history_in_context param removed - history loading now via context= param
                    print(f"[bold cyan]History enabled - loading context from last {self.args.history} session(s)[/bold cyan]")
                
                # Claude Memory Tool (Anthropic only)
                if getattr(self.args, 'claude_memory', False):
                    llm = getattr(self.args, 'llm', '')
                    if llm and 'anthropic' in llm.lower():
                        agent_config["claude_memory"] = True
                        print("[bold cyan]Claude Memory Tool enabled - Claude will autonomously manage memories[/bold cyan]")
                    else:
                        print("[yellow]Warning: --claude-memory requires an Anthropic model (--llm anthropic/...)[/yellow]")
                
                # ===== NEW CLI FEATURES INTEGRATION =====
                
                # Tool Approval - Auto-approve tools based on --trust or --approve-level
                if getattr(self.args, 'trust', False) or getattr(self.args, 'approve_level', None):
                    from praisonaiagents.approval import set_approval_callback, ApprovalDecision
                    
                    if getattr(self.args, 'trust', False):
                        # Auto-approve all tools
                        def auto_approve_all(function_name, arguments, risk_level):
                            return ApprovalDecision(approved=True, reason="Auto-approved via --trust flag")
                        set_approval_callback(auto_approve_all)
                        print("[bold yellow]⚠️  Trust mode enabled - all tool executions will be auto-approved[/bold yellow]")
                    elif getattr(self.args, 'approve_level', None):
                        # Auto-approve up to specified risk level
                        max_level = self.args.approve_level
                        risk_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
                        max_level_value = risk_order.get(max_level, 3)
                        
                        def level_based_approve(function_name, arguments, risk_level):
                            tool_level_value = risk_order.get(risk_level, 4)
                            if tool_level_value <= max_level_value:
                                return ApprovalDecision(approved=True, reason=f"Auto-approved (level {risk_level} <= {max_level})")
                            else:
                                # Signal to pause Live display before showing approval prompt
                                # This is handled by the approval_pending flag in status_info
                                from praisonaiagents.approval import console_approval_callback
                                return console_approval_callback(function_name, arguments, risk_level)
                        
                        set_approval_callback(level_based_approve)
                        print(f"[bold cyan]Auto-approve enabled for tools up to '{max_level}' risk level[/bold cyan]")
                
                # Router - Smart model selection (must be before agent creation)
                if getattr(self.args, 'router', False):
                    from .features.router import RouterHandler
                    router = RouterHandler(verbose=getattr(self.args, 'verbose', False))
                    provider = getattr(self.args, 'router_provider', None)
                    selected_model = router.select_model(prompt, provider)
                    agent_config["llm"] = selected_model
                
                # Metrics - Token/cost tracking (display happens AFTER execution)
                if getattr(self.args, 'metrics', False):
                    agent_config["metrics"] = True
                
                # Telemetry - Usage monitoring
                if getattr(self.args, 'telemetry', False):
                    from .features.telemetry import TelemetryHandler
                    telemetry = TelemetryHandler(verbose=getattr(self.args, 'verbose', False))
                    telemetry.enable()
                
                # Sandbox - Secure command execution (display only, actual sandboxing is in tool approval)
                sandbox_mode = getattr(self.args, 'sandbox', None)
                if sandbox_mode and sandbox_mode != 'off':
                    print(f"[bold green]🔒 Sandbox Mode: {sandbox_mode.upper()}[/bold green]")
                    print("[dim]Commands will be validated before execution[/dim]")
                
                # Auto Memory - Automatic memory extraction (handled post-processing, not as Agent param)
                if getattr(self.args, 'auto_memory', False):
                    print("[bold cyan]Auto Memory enabled - will extract and store memories[/bold cyan]")
                
                # MCP - Model Context Protocol tools
                if getattr(self.args, 'mcp', None):
                    from .features.mcp import MCPHandler
                    mcp_handler = MCPHandler(verbose=getattr(self.args, 'verbose', False))
                    mcp_tools = mcp_handler.create_mcp_tools(
                        self.args.mcp,
                        getattr(self.args, 'mcp_env', None)
                    )
                    if mcp_tools:
                        existing_tools = agent_config.get('tools', [])
                        if isinstance(existing_tools, list):
                            existing_tools.extend(list(mcp_tools))
                        else:
                            existing_tools = list(mcp_tools)
                        agent_config['tools'] = existing_tools
                
                # External Agent - Use external AI CLI tools directly
                if getattr(self.args, 'external_agent', None):
                    from rich.console import Console
                    ext_console = Console()
                    external_agent_name = self.args.external_agent
                    try:
                        from .features.external_agents import ExternalAgentsHandler
                        handler = ExternalAgentsHandler(verbose=getattr(self.args, 'verbose', False))
                        
                        # Get workspace from current directory (os is imported at module level)
                        workspace = os.getcwd()
                        
                        integration = handler.get_integration(external_agent_name, workspace=workspace)
                        
                        if integration.is_available:
                            ext_console.print(f"[bold cyan]🔌 Using external agent: {external_agent_name}[/bold cyan]")
                            
                            # Run the external agent directly instead of PraisonAI agent
                            import asyncio
                            try:
                                result = asyncio.run(integration.execute(prompt))
                                ext_console.print(f"\n[bold green]Result from {external_agent_name}:[/bold green]")
                                ext_console.print(result)
                                # Return empty string to avoid duplicate printing by caller
                                return ""
                            except Exception as e:
                                ext_console.print(f"[red]Error executing {external_agent_name}: {e}[/red]")
                                return None
                        else:
                            ext_console.print(f"[yellow]⚠️ External agent '{external_agent_name}' is not installed[/yellow]")
                            ext_console.print(f"[dim]Install with: {handler._get_install_instructions(external_agent_name)}[/dim]")
                            return None
                    except Exception as e:
                        ext_console.print(f"[red]Error setting up external agent: {e}[/red]")
                        return None
                
                # Fast Context - Codebase search
                if getattr(self.args, 'fast_context', None):
                    from .features.fast_context import FastContextHandler
                    fc_handler = FastContextHandler(verbose=getattr(self.args, 'verbose', False))
                    context = fc_handler.execute(query=prompt, path=self.args.fast_context)
                    if context:
                        prompt = f"{context}\n\n## Task\n{prompt}"
                        print("[bold cyan]Fast Context enabled - added relevant code context[/bold cyan]")
                
                # Handoff - Agent delegation (creates multiple agents)
                if getattr(self.args, 'handoff', None):
                    from .features.handoff import HandoffHandler
                    handoff_handler = HandoffHandler(verbose=getattr(self.args, 'verbose', False))
                    
                    # Parse handoff config options
                    detect_cycles = None
                    if getattr(self.args, 'handoff_detect_cycles', None):
                        detect_cycles = self.args.handoff_detect_cycles.lower() == 'true'
                    
                    agents = handoff_handler.create_agents_with_handoff(
                        handoff_handler.parse_agent_names(self.args.handoff),
                        llm=agent_config.get('llm'),
                        context_policy=getattr(self.args, 'handoff_policy', None),
                        timeout_seconds=getattr(self.args, 'handoff_timeout', None),
                        max_concurrent=getattr(self.args, 'handoff_max_concurrent', None),
                        max_depth=getattr(self.args, 'handoff_max_depth', None),
                        detect_cycles=detect_cycles,
                    )
                    if agents:
                        # Use first agent with handoff chain
                        result = agents[0].start(prompt)
                        
                        # Post-process with guardrail if enabled
                        if getattr(self.args, 'guardrail', None):
                            from .features.guardrail import GuardrailHandler
                            guardrail = GuardrailHandler(verbose=getattr(self.args, 'verbose', False))
                            guardrail.post_process_result(result, self.args.guardrail)
                        
                        # Save output if --save is enabled
                        if getattr(self.args, 'save', False):
                            self._save_output(prompt, result)
                        
                        return result
            
            # Image Description (Vision) - analyze existing images
            if hasattr(self, 'args') and getattr(self.args, 'image', None):
                from .features.image import ImageHandler
                image_handler = ImageHandler(verbose=getattr(self.args, 'verbose', False))
                result = image_handler.execute(
                    prompt=prompt,
                    image_path=self.args.image,
                    llm=agent_config.get('llm')
                )
                
                # Post-process with guardrail if enabled
                if getattr(self.args, 'guardrail', None):
                    from .features.guardrail import GuardrailHandler
                    guardrail = GuardrailHandler(verbose=getattr(self.args, 'verbose', False))
                    guardrail.post_process_result(result, self.args.guardrail)
                
                # Save output if --save is enabled
                if getattr(self.args, 'save', False):
                    self._save_output(prompt, result)
                
                return result
            
            # Image Generation - create new images from text
            if hasattr(self, 'args') and getattr(self.args, 'image_generate', False):
                from .features.image import ImageGenerateHandler
                image_gen_handler = ImageGenerateHandler(verbose=getattr(self.args, 'verbose', False))
                result = image_gen_handler.execute(
                    prompt=prompt,
                    llm=agent_config.get('llm')
                )
                
                # Format output for display
                if isinstance(result, dict):
                    if 'error' in result:
                        print(f"[red]Error: {result['error']}[/red]")
                    elif 'data' in result and len(result['data']) > 0:
                        image_url = result['data'][0].get('url', result['data'][0].get('b64_json', 'Generated'))
                        print(f"[green]Image generated successfully![/green]")
                        if 'url' in result['data'][0]:
                            print(f"URL: {result['data'][0]['url']}")
                
                return result
            
            # Flow Display - Visual workflow tracking
            if hasattr(self, 'args') and getattr(self.args, 'flow_display', False):
                from .features.flow_display import FlowDisplayHandler
                flow = FlowDisplayHandler(verbose=getattr(self.args, 'verbose', False))
                flow.display_workflow_start("Direct Prompt", ["DirectAgent"])
            
            agent = PraisonAgent(**agent_config)
            
            # AutoRag - Automatic RAG retrieval decision
            if hasattr(self, 'args') and getattr(self.args, 'auto_rag', False):
                from praisonaiagents import AutoRagAgent
                
                auto_rag_config = {
                    "retrieval_policy": getattr(self.args, 'rag_policy', 'auto'),
                    "top_k": getattr(self.args, 'rag_top_k', 5),
                    "hybrid": getattr(self.args, 'rag_hybrid', False),
                    "rerank": getattr(self.args, 'rag_rerank', False),
                }
                
                auto_rag = AutoRagAgent(agent=agent, **auto_rag_config)
                print(f"[bold cyan]AutoRag enabled - policy: {auto_rag_config['retrieval_policy']}[/bold cyan]")
                
                # Run with AutoRag wrapper
                is_verbose = agent_config.get("verbose", False)
                if not is_verbose:
                    from rich.live import Live
                    from rich.spinner import Spinner
                    from rich.panel import Panel
                    
                    with Live(Panel(Spinner("dots", text="Generating..."), border_style="cyan"), refresh_per_second=10, transient=True):
                        result = auto_rag.chat(prompt)
                else:
                    result = auto_rag.chat(prompt)
            else:
                # Run with minimal status display when verbose=False
                is_verbose = agent_config.get("verbose", False)
                if not is_verbose:
                    result = self._run_with_status_display(agent, prompt)
                else:
                    # Try start method first, fallback to chat
                    if hasattr(agent, 'start'):
                        result = agent.start(prompt)
                    else:
                        result = agent.chat(prompt)
            
            # ===== POST-PROCESSING WITH NEW FEATURES =====
            
            # Guardrail - Output validation
            if hasattr(self, 'args') and getattr(self.args, 'guardrail', None):
                from .features.guardrail import GuardrailHandler
                guardrail = GuardrailHandler(verbose=getattr(self.args, 'verbose', False))
                guardrail.post_process_result(result, self.args.guardrail)
            
            # Metrics - Display token usage
            if hasattr(self, 'args') and getattr(self.args, 'metrics', False):
                from .features.metrics import MetricsHandler
                metrics = MetricsHandler(verbose=getattr(self.args, 'verbose', False))
                agent_metrics = metrics.extract_metrics_from_agent(agent)
                if agent_metrics:
                    print(metrics.format_metrics(agent_metrics))
            
            # Auto Memory - Extract and store memories
            if hasattr(self, 'args') and getattr(self.args, 'auto_memory', False):
                from .features.auto_memory import AutoMemoryHandler
                auto_mem = AutoMemoryHandler(verbose=getattr(self.args, 'verbose', False))
                auto_mem.post_process_result(
                    result, 
                    {'user_id': getattr(self.args, 'user_id', None), 'user_message': prompt}
                )
            
            # Todo - Generate todo list from response
            if hasattr(self, 'args') and getattr(self.args, 'todo', False):
                from .features.todo import TodoHandler
                todo = TodoHandler(verbose=getattr(self.args, 'verbose', False))
                todo.post_process_result(result, True)
            
            # Telemetry - Display usage summary after execution
            if hasattr(self, 'args') and getattr(self.args, 'telemetry', False):
                from .features.telemetry import TelemetryHandler
                telemetry = TelemetryHandler(verbose=getattr(self.args, 'verbose', False))
                telemetry.post_process_result(result, True)
            
            # Flow Display - End workflow
            if hasattr(self, 'args') and getattr(self.args, 'flow_display', False):
                from .features.flow_display import FlowDisplayHandler
                flow = FlowDisplayHandler(verbose=getattr(self.args, 'verbose', False))
                flow.display_workflow_end(success=True)
            
            # Final Agent - Process output with a specialized agent
            if hasattr(self, 'args') and getattr(self.args, 'final_agent', None):
                final_instruction = self.args.final_agent
                print(f"\n[bold blue]📝 FINAL AGENT PROCESSING[/bold blue]")
                print(f"[dim]Instruction: {final_instruction}[/dim]\n")
                
                # Create a final agent with the same LLM config
                final_agent_config = {
                    "name": "FinalAgent",
                    "role": final_instruction,
                    "goal": f"Process the provided content and {final_instruction.lower()}",
                    "backstory": f"You are an expert at {final_instruction.lower()}. You take research content and transform it into polished, detailed output."
                }
                
                # Use same LLM config
                if agent_config.get("llm"):
                    final_agent_config["llm"] = agent_config["llm"]
                
                final_prompt = f"""Based on the following research content, {final_instruction.lower()}.

## Research Content:

{result}

## Instructions:
- Be comprehensive and detailed
- Include all relevant information from the research
- Structure the output professionally
- Do not omit any important details

Now, {final_instruction.lower()}:"""
                
                final_agent = PraisonAgent(**final_agent_config)
                result = final_agent.start(final_prompt)
                print(f"\n[bold green]✅ Final agent processing complete[/bold green]\n")
            
            # Save output if --save is enabled
            if hasattr(self, 'args') and getattr(self.args, 'save', False):
                self._save_output(prompt, result)
            
            return result
        elif CREWAI_AVAILABLE:
            from crewai import Agent, Task, Crew
            agent_config = {
                "name": "DirectAgent",
                "role": "Assistant",
                "goal": "Complete the given task",
                "backstory": "You are a helpful AI assistant"
            }
            
            # Add llm if specified
            if hasattr(self, 'args') and self.args.llm:
                agent_config["llm"] = self.args.llm
            
            agent = Agent(**agent_config)
            task = Task(
                description=prompt,
                agent=agent
            )
            crew = Crew(
                agents=[agent],
                tasks=[task]
            )
            return crew.kickoff()
        elif AUTOGEN_AVAILABLE:
            # Lazy import autogen only when needed
            autogen = _get_autogen()
            config_list = self.config_list
            # Add llm if specified
            if hasattr(self, 'args') and self.args.llm:
                config_list[0]['model'] = self.args.llm
                
            assistant = autogen.AssistantAgent(
                name="DirectAgent",
                llm_config={"config_list": config_list}
            )
            user_proxy = autogen.UserProxyAgent(
                name="UserProxy",
                code_execution_config={"work_dir": "coding"}
            )
            user_proxy.initiate_chat(assistant, message=prompt)
            return "Task completed"
        else:
            print("[red]ERROR: No framework is installed. Please install at least one framework:[/red]")
            print("\npip install \"praisonai\\[crewai]\"  # For CrewAI")
            print("pip install \"praisonai\\[autogen]\"  # For AutoGen")
            print("pip install \"praisonai\\[crewai,autogen]\"  # For both frameworks\n")
            print("pip install praisonaiagents # For Agents\n")  
            sys.exit(1)

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

    def _run_with_status_display(self, agent, prompt):
        """
        Run agent with minimal status display (spinner + tool/handoff updates).
        
        Shows:
        - "Generating..." with spinner while processing
        - Real-time tool call notifications via registered callback
        - Agent handoff notifications
        """
        import threading
        import time
        from rich.console import Console
        from rich.live import Live
        from rich.text import Text
        
        console = Console()
        
        # Import callback registration from praisonaiagents
        # Store in local variable for safe access throughout the function
        _sync_display_callbacks = None
        _register_display_callback = None
        try:
            from praisonaiagents import register_display_callback, sync_display_callbacks
            _sync_display_callbacks = sync_display_callbacks
            _register_display_callback = register_display_callback
        except ImportError:
            # Fallback if callbacks not available - just run agent directly
            try:
                result = agent.start(prompt)
            except AttributeError:
                # Try chat method if start not available
                result = agent.chat(prompt)
            if result:
                console.print(result)
            elif result == "" or result is None:
                console.print("[dim]No response generated[/dim]")
            return result
        
        # Get tool names for display
        tool_names = []
        if hasattr(agent, 'tools') and agent.tools:
            for tool in agent.tools:
                if hasattr(tool, '__name__'):
                    tool_names.append(tool.__name__)
                elif hasattr(tool, 'name'):
                    tool_names.append(tool.name)
        
        status_info = {
            'status': 'Generating...',
            'tool_calls': [],
            'handoffs': [],
            'done': False,
            'result': None,
            'error': None,
            'start_time': time.time(),
            'available_tools': tool_names,
            'approval_pending': False,  # Flag to pause Live display during approval
            'live_instance': None  # Reference to Live instance for stopping
        }
        
        def tool_call_callback(message):
            """Callback triggered when a tool is called."""
            # Extract tool name from message
            if "Calling function:" in message:
                # Format: "Calling function: function_name"
                parts = message.split("Calling function:")
                if len(parts) > 1:
                    tool_name = parts[1].strip()
                    if tool_name and tool_name not in status_info['tool_calls']:
                        status_info['tool_calls'].append(tool_name)
                        status_info['status'] = f"Using {tool_name}..."
            elif "Function " in message and " returned:" in message:
                # Format: "Function function_name returned: ..."
                # Tool execution completed, update status
                status_info['status'] = "Processing result..."
        
        # Register callback for tool calls (use local variable)
        _register_display_callback('tool_call', tool_call_callback)
        
        def build_status_display():
            """Build the status display text."""
            elapsed = time.time() - status_info['start_time']
            
            # Main status with spinner
            text = Text()
            text.append("⏳ ", style="cyan")
            text.append(f"{status_info['status']} ", style="bold")
            text.append(f"({elapsed:.1f}s)", style="dim")
            
            # Show available tools on first line
            if status_info['available_tools'] and not status_info['tool_calls']:
                tools_str = ', '.join(status_info['available_tools'][:3])
                if len(status_info['available_tools']) > 3:
                    tools_str += f" +{len(status_info['available_tools']) - 3} more"
                text.append(f"\n  🔧 Tools: {tools_str}", style="dim")
            
            # Show recent tool calls
            if status_info['tool_calls']:
                text.append("\n")
                for tool in status_info['tool_calls'][-3:]:  # Show last 3
                    text.append(f"  ⚙ {tool}", style="dim yellow")
                    text.append("\n")
            
            # Show handoffs
            if status_info['handoffs']:
                for handoff in status_info['handoffs'][-2:]:  # Show last 2
                    text.append(f"  → {handoff}", style="dim cyan")
                    text.append("\n")
            
            return text
        
        def run_agent():
            """Run the agent in background thread."""
            try:
                status_info['result'] = agent.start(prompt)
            except Exception as e:
                status_info['error'] = e
            finally:
                status_info['done'] = True
        
        # Set up approval callback that stops Live display before prompting
        # Only if not using --trust (which auto-approves everything)
        if not getattr(self.args, 'trust', False):
            from praisonaiagents.approval import set_approval_callback, ApprovalDecision
            from rich.prompt import Confirm
            from rich.panel import Panel
            
            def cli_approval_with_live_pause(function_name, arguments, risk_level):
                """Approval callback that stops Live display before prompting."""
                # Signal to stop Live display
                status_info['approval_pending'] = True
                
                # Wait a moment for Live to stop
                time.sleep(0.2)
                
                # Now show the approval prompt
                risk_colors = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "blue"}
                risk_color = risk_colors.get(risk_level, "white")
                
                tool_info = f"[bold]Function:[/] {function_name}\n"
                tool_info += f"[bold]Risk Level:[/] [{risk_color}]{risk_level.upper()}[/{risk_color}]\n"
                tool_info += "[bold]Arguments:[/]\n"
                for key, value in arguments.items():
                    str_value = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    tool_info += f"  {key}: {str_value}\n"
                
                console.print(Panel(tool_info.strip(), title="🔒 Tool Approval Required", border_style=risk_color))
                
                try:
                    approved = Confirm.ask(f"[{risk_color}]Execute this {risk_level} risk tool?[/{risk_color}]", default=False)
                    status_info['approval_pending'] = False
                    
                    if approved:
                        console.print("[green]✅ Approved[/green]")
                        return ApprovalDecision(approved=True, reason="User approved")
                    else:
                        console.print("[red]❌ Denied[/red]")
                        return ApprovalDecision(approved=False, reason="User denied")
                except (KeyboardInterrupt, EOFError):
                    status_info['approval_pending'] = False
                    console.print("\n[red]❌ Cancelled[/red]")
                    return ApprovalDecision(approved=False, reason="User cancelled")
            
            # Only set if not already set by --approve-level
            if not getattr(self.args, 'approve_level', None):
                set_approval_callback(cli_approval_with_live_pause)
        
        # Start agent in background thread
        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()
        
        # Show live status while processing
        try:
            with Live(build_status_display(), console=console, refresh_per_second=4, transient=True) as live:
                status_info['live_instance'] = live
                while not status_info['done']:
                    # Check if approval is pending - stop Live to show prompt
                    if status_info['approval_pending']:
                        break
                    live.update(build_status_display())
                    time.sleep(0.1)
            
            # If approval was pending, wait for it to complete then restart Live
            while status_info['approval_pending']:
                time.sleep(0.1)
            
            # Continue with Live display if not done
            if not status_info['done']:
                with Live(build_status_display(), console=console, refresh_per_second=4, transient=True) as live:
                    while not status_info['done']:
                        if status_info['approval_pending']:
                            break
                        live.update(build_status_display())
                        time.sleep(0.1)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted[/dim]")
            # Unregister callback (use local variable with None check)
            if _sync_display_callbacks is not None and 'tool_call' in _sync_display_callbacks:
                del _sync_display_callbacks['tool_call']
            return None
        
        # Wait for thread to complete
        thread.join(timeout=1.0)
        
        # Unregister callback to avoid memory leaks (use local variable with None check)
        if _sync_display_callbacks is not None and 'tool_call' in _sync_display_callbacks:
            del _sync_display_callbacks['tool_call']
        
        # Handle result
        if status_info['error']:
            console.print(f"[red]Error: {status_info['error']}[/red]")
            return None
        
        # Show tool calls that were made (if any)
        if status_info['tool_calls']:
            console.print(f"[dim]Tools used: {', '.join(status_info['tool_calls'])}[/dim]")
        
        # Get the result and print it directly here to ensure it's displayed
        result = status_info['result']
        if result:
            console.print(result)
        elif result == "" or result is None:
            console.print("[dim]No response generated[/dim]")
        
        return result

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
        from praisonaiagents import Agent, Agents
        
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
            praison = AgentManager(
                agents=agents_list, 
                tasks=tasks_list,
                process=process_type,
                verbose=1 if verbose else 0
            )
        else:
            praison = AgentManager(
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

    def create_chainlit_chat_interface(self):
        """
        Create a Chainlit interface for the chat application.
        """
        if CHAINLIT_AVAILABLE:
            import praisonai
            os.environ["CHAINLIT_PORT"] = "8084"
            root_path = os.path.join(os.path.expanduser("~"), ".praison")
            if "CHAINLIT_APP_ROOT" not in os.environ:
                os.environ["CHAINLIT_APP_ROOT"] = root_path
            chat_ui_path = os.path.join(os.path.dirname(praisonai.__file__), 'ui', 'chat.py')
            _get_chainlit_run()([chat_ui_path])
        else:
            print("ERROR: Chat UI is not installed. Please install it with 'pip install \"praisonai[chat]\"' to use the chat UI.")

    def create_code_interface(self):
        """
        Create a Chainlit interface for the code application.
        """
        if CHAINLIT_AVAILABLE:
            import praisonai
            os.environ["CHAINLIT_PORT"] = "8086"
            root_path = os.path.join(os.path.expanduser("~"), ".praison")
            if "CHAINLIT_APP_ROOT" not in os.environ:
                os.environ["CHAINLIT_APP_ROOT"] = root_path
            public_folder = os.path.join(os.path.dirname(__file__), 'public')
            if not os.path.exists(os.path.join(root_path, "public")):
                if os.path.exists(public_folder):
                    shutil.copytree(public_folder, os.path.join(root_path, "public"), dirs_exist_ok=True)
                    logging.info("Public folder copied successfully!")
                else:
                    logging.info("Public folder not found in the package.")
            else:
                logging.info("Public folder already exists.")
            code_ui_path = os.path.join(os.path.dirname(praisonai.__file__), 'ui', 'code.py')
            _get_chainlit_run()([code_ui_path])
        else:
            print("ERROR: Code UI is not installed. Please install it with 'pip install \"praisonai[code]\"' to use the code UI.")

    def create_gradio_interface(self):
        """
        Create a Gradio interface for generating agents and performing tasks.
        """
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
                agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list)
                result = agents_generator.generate_crew_and_kickoff()
                return result

            gr.Interface(
                fn=generate_crew_and_kickoff_interface,
                inputs=[gr.Textbox(lines=2, label="Auto Args"), gr.Dropdown(choices=["crewai", "autogen"], label="Framework")],
                outputs="textbox",
                title="Praison AI Studio",
                description="Create Agents and perform tasks",
                theme="default"
            ).launch()
        else:
            print("ERROR: Gradio is not installed. Please install it with 'pip install gradio' to use this feature.")

    def create_chainlit_interface(self):
        """
        Create a Chainlit interface for generating agents and performing tasks.
        """
        if CHAINLIT_AVAILABLE:
            import praisonai
            os.environ["CHAINLIT_PORT"] = "8082"
            public_folder = os.path.join(os.path.dirname(praisonai.__file__), 'public')
            if not os.path.exists("public"):
                if os.path.exists(public_folder):
                    shutil.copytree(public_folder, 'public', dirs_exist_ok=True)
                    logging.info("Public folder copied successfully!")
                else:
                    logging.info("Public folder not found in the package.")
            else:
                logging.info("Public folder already exists.")
            chainlit_ui_path = os.path.join(os.path.dirname(praisonai.__file__), 'ui', 'agents.py')
            _get_chainlit_run()([chainlit_ui_path])
        else:
            print("ERROR: Chainlit is not installed. Please install it with 'pip install \"praisonai[ui]\"' to use the UI.")

    def create_realtime_interface(self):
        """
        Create a Chainlit interface for the realtime voice interaction application.
        """
        if CHAINLIT_AVAILABLE:
            import praisonai
            os.environ["CHAINLIT_PORT"] = "8088"
            root_path = os.path.join(os.path.expanduser("~"), ".praison")
            if "CHAINLIT_APP_ROOT" not in os.environ:
                os.environ["CHAINLIT_APP_ROOT"] = root_path
            public_folder = os.path.join(os.path.dirname(praisonai.__file__), 'public')
            if not os.path.exists(os.path.join(root_path, "public")):
                if os.path.exists(public_folder):
                    shutil.copytree(public_folder, os.path.join(root_path, "public"), dirs_exist_ok=True)
                    logging.info("Public folder copied successfully!")
                else:
                    logging.info("Public folder not found in the package.")
            else:
                logging.info("Public folder already exists.")
            realtime_ui_path = os.path.join(os.path.dirname(praisonai.__file__), 'ui', 'realtime.py')
            _get_chainlit_run()([realtime_ui_path])
        else:
            print("ERROR: Realtime UI is not installed. Please install it with 'pip install \"praisonai[realtime]\"' to use the realtime UI.")

    def handle_context_command(self, url: str, goal: str, auto_analyze: bool = False) -> str:
        """
        Handle the context command by creating a ContextAgent and running it.
        
        Args:
            url: Repository URL for context analysis
            goal: Goal for context engineering
            auto_analyze: Enable automatic analysis (default: False)
            
        Returns:
            str: Result from context engineering
        """
        try:
            from praisonaiagents import ContextAgent
            print("[bold green]Starting Context Engineering...[/bold green]")
            print(f"URL: {url}")
            print(f"Goal: {goal}")
            print(f"Auto-analyze: {auto_analyze}")
            
            # Use the same model configuration pattern as other CLI commands
            # Priority order: MODEL_NAME > OPENAI_MODEL_NAME for model selection
            model_name = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
            
            # Create ContextAgent with user's LLM configuration
            agent = ContextAgent(llm=model_name, auto_analyze=auto_analyze)
            
            # Format input as expected by the start method: "url goal"
            input_text = f"{url} {goal}"
            
            # Execute the context engineering
            result = agent.start(input_text)
            
            print("\n[bold green]Context Engineering Complete![/bold green]")
            print(result)
            return result
            
        except ImportError as e:
            print(f"[red]ERROR: Failed to import ContextAgent: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
            sys.exit(1)
        except Exception as e:
            print(f"[red]ERROR: Context engineering failed: {e}[/red]")
            sys.exit(1)

    def handle_research_command(self, query: str, model: str = None, verbose: bool = False, save: bool = False, query_rewrite: bool = False, tools_path: str = None, rewrite_tools: str = None) -> str:
        """
        Handle the research command by creating a DeepResearchAgent and running it.
        
        Args:
            query: Research query/topic
            model: Model for deep research (optional, defaults to o4-mini-deep-research)
            verbose: Enable verbose output (default: False)
            save: Save output to file (default: False)
            query_rewrite: Rewrite query before research (default: False)
            tools_path: Path to tools.py file with custom tools (default: None)
            rewrite_tools: Tools for query rewriter (tool names or file path)
            
        Returns:
            str: Research report
        """
        try:
            from praisonaiagents import DeepResearchAgent
            
            # Suppress logging unless verbose
            if not verbose:
                logging.getLogger('google').setLevel(logging.WARNING)
                logging.getLogger('google.genai').setLevel(logging.WARNING)
                logging.getLogger('httpx').setLevel(logging.WARNING)
                logging.getLogger('httpcore').setLevel(logging.WARNING)
            
            # Rewrite query if requested
            if query_rewrite:
                query = self._rewrite_query(query, rewrite_tools, verbose)
            
            print("[bold green]Starting Deep Research...[/bold green]")
            print(f"Query: {query}")
            
            # Default model if not specified
            if not model:
                model = "o4-mini-deep-research"
            
            print(f"Model: {model}")
            
            # Load tools if specified
            tools_list = []
            if tools_path:
                # Check if it's a file path or comma-separated tool names
                if os.path.isfile(tools_path):
                    # Load from file
                    try:
                        import inspect
                        spec = importlib.util.spec_from_file_location("tools_module", tools_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            # Get all callable functions from the module
                            for name, obj in inspect.getmembers(module):
                                if inspect.isfunction(obj) and not name.startswith('_'):
                                    tools_list.append(obj)
                            if tools_list:
                                print(f"[cyan]Loaded {len(tools_list)} tools from {tools_path}[/cyan]")
                    except Exception as e:
                        print(f"[yellow]Warning: Failed to load tools from {tools_path}: {e}[/yellow]")
                else:
                    # Treat as comma-separated tool names (e.g., "internet_search,wiki_search")
                    try:
                        from praisonaiagents.tools import TOOL_MAPPINGS
                        import praisonaiagents.tools as tools_module
                        
                        tool_names = [t.strip() for t in tools_path.split(',')]
                        for tool_name in tool_names:
                            if tool_name in TOOL_MAPPINGS:
                                try:
                                    tool = getattr(tools_module, tool_name)
                                    tools_list.append(tool)
                                except Exception as e:
                                    print(f"[yellow]Warning: Failed to load tool '{tool_name}': {e}[/yellow]")
                            else:
                                print(f"[yellow]Warning: Unknown tool '{tool_name}'[/yellow]")
                        if tools_list:
                            print(f"[cyan]Loaded {len(tools_list)} built-in tools: {', '.join(tool_names)}[/cyan]")
                    except ImportError:
                        print("[yellow]Warning: Could not import tools module[/yellow]")
            
            # If tools are provided, use Agent with tools first, then DeepResearchAgent
            if tools_list:
                from praisonaiagents import Agent, Task, Agents
                
                # Create a research assistant agent with tools
                research_assistant = Agent(
                    name="Research Assistant",
                    role="Information Gatherer",
                    goal="Gather relevant information using available tools",
                    backstory="You are an expert at using tools to gather information for research.",
                    tools=tools_list,
                    llm="gpt-4o-mini", output="minimal"
                )
                
                # Create task to gather initial information
                gather_task = Task(
                    description=f"Use your tools to gather relevant information about: {query}",
                    expected_output="A summary of information gathered from the tools",
                    agent=research_assistant
                )
                
                print("[cyan]Gathering information with tools...[/cyan]")
                agents = AgentManager(agents=[research_assistant], tasks=[gather_task], verbose=0)
                tool_results = agents.start()
                
                # Enhance query with tool results
                enhanced_query = f"{query}\n\nAdditional context from tools:\n{tool_results}"
                print("[cyan]Tools context gathered, starting deep research...[/cyan]")
                
                # Create DeepResearchAgent
                agent = DeepResearchAgent(model=model)
                result = agent.research(enhanced_query)
            else:
                # Create DeepResearchAgent (verbose=True is default for streaming output)
                agent = DeepResearchAgent(model=model)
                
                # Execute the research
                result = agent.research(query)
            
            print("\n[bold green]Research Complete![/bold green]")
            print("\n" + "="*60)
            print(result.report)
            print("="*60)
            
            # Show citations if available
            if result.citations:
                print(f"\n[bold]Citations ({len(result.citations)}):[/bold]")
                for i, citation in enumerate(result.citations, 1):
                    title = getattr(citation, 'title', 'Untitled')
                    url = getattr(citation, 'url', '')
                    print(f"  {i}. {title}")
                    if url:
                        print(f"     {url}")
            
            # Save output to file if --save flag is set
            if save:
                import re
                # Get first 10 words from query for filename
                words = query.split()[:10]
                filename_base = ' '.join(words)
                # Sanitize filename: remove invalid characters
                filename_base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', filename_base)
                filename_base = filename_base.strip()[:100]  # Limit length
                if not filename_base:
                    filename_base = "research_output"
                
                # Create output directory
                output_dir = os.path.join(os.getcwd(), "output", "research")
                os.makedirs(output_dir, exist_ok=True)
                
                # Build markdown content
                md_content = f"# {query}\n\n"
                md_content += result.report
                if result.citations:
                    md_content += "\n\n## Citations\n\n"
                    for i, citation in enumerate(result.citations, 1):
                        title = getattr(citation, 'title', 'Untitled')
                        url = getattr(citation, 'url', '')
                        if url:
                            md_content += f"{i}. [{title}]({url})\n"
                        else:
                            md_content += f"{i}. {title}\n"
                
                # Save to file
                output_path = os.path.join(output_dir, f"{filename_base}.md")
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                
                print(f"\n[bold green]Saved to:[/bold green] {output_path}")
            
            return result.report
            
        except ImportError as e:
            print(f"[red]ERROR: Failed to import DeepResearchAgent: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
            sys.exit(1)
        except Exception as e:
            print(f"[red]ERROR: Research failed: {e}[/red]")
            sys.exit(1)

    def _start_interactive_mode(self, args):
        """
        Start interactive TUI mode with streaming responses and tool support.
        
        UX inspired by Gemini CLI, Codex CLI, and Claude Code:
        - Streaming text output (no boxes)
        - Tool status indicators
        - Built-in tools (file ops, shell, web search)
        - Autocomplete for slash commands and @file mentions
        - /compact for context compression
        - /model for model switching
        - /stats for token/cost tracking
        - /undo for reverting changes
        """
        try:
            from rich.console import Console
            import os
            
            console = Console()
            
            # Set interactive mode flag
            self._interactive_mode = True
            
            # Load interactive tools
            tools_list = self._load_interactive_tools()
            
            # Import message queue components
            from praisonai.cli.features.message_queue import (
                MessageQueue, StateManager, QueueDisplay, ProcessingState,
                LiveStatusDisplay
            )
            import threading
            import queue as queue_module
            
            # Create message queue and state manager
            message_queue = MessageQueue()
            state_manager = StateManager()
            queue_display = QueueDisplay(message_queue, state_manager)
            live_status = LiveStatusDisplay()
            processing_lock = threading.Lock()
            
            # Create execution queue for worker thread (TRUE ASYNC)
            execution_queue = queue_module.Queue()
            approval_request_queue = queue_module.Queue()
            approval_response_queue = queue_module.Queue()
            
            # Worker state for cross-thread communication
            # Enhanced with task-bound context for proper Q/A mapping
            worker_state = {
                'running': True,
                'current_task': None,  # Full task context object (FIFO head)
                'approval_pending': False,
                'waiting_for_approval_input': False,
                'completed_tasks': [],  # Queue of completed tasks to display (FIFO order)
                'error_tasks': [],  # Queue of error tasks to display
                'tool_activity': None,  # Current tool being used
                'last_status_line': None,  # For transient status updates
            }
            
            # Task counter for unique IDs (FIFO position tracking)
            task_counter = {'value': 0}
            
            # Check for verbose mode
            verbose_mode = getattr(args, 'verbose', False) if hasattr(args, 'verbose') else False
            
            # Initialize persistent session
            from praisonai.cli.session import get_session_store
            session_store = get_session_store()
            
            # Check for --resume flag or get/create session
            resume_session_id = getattr(args, 'resume_session', None)
            if resume_session_id == 'last':
                unified_session = session_store.get_last_session()
                if not unified_session:
                    unified_session = session_store.get_or_create()
            elif resume_session_id:
                unified_session = session_store.get_or_create(resume_session_id)
            else:
                unified_session = session_store.get_or_create()
            
            # Set model from args or session
            current_model = getattr(args, 'llm', None) or unified_session.current_model or os.environ.get('OPENAI_MODEL_NAME', 'gpt-4o-mini')
            unified_session.current_model = current_model
            
            # Session state (now backed by persistent UnifiedSession)
            session_state = {
                'show_profiling': False,
                'current_model': current_model,
                'conversation_history': unified_session.get_chat_history(),
                'total_input_tokens': unified_session.total_input_tokens,
                'total_output_tokens': unified_session.total_output_tokens,
                'total_cost': unified_session.total_cost,
                'request_count': unified_session.request_count,
                'undo_stack': [],  # Stack of (prompt, response) for undo
                'message_queue': message_queue,
                'state_manager': state_manager,
                'queue_display': queue_display,
                'live_status': live_status,
                'processing_lock': processing_lock,
                'execution_queue': execution_queue,  # Queue for worker thread
                'approval_request_queue': approval_request_queue,
                'approval_response_queue': approval_response_queue,
                'worker_state': worker_state,
                'unified_session': unified_session,  # Reference to persistent session
                'session_store': session_store,  # Reference to store for saving
            }
            
            # Initialize context manager with CLI flags
            context_config = {
                'auto_compact': getattr(args, 'context_auto_compact', True),  # Default True in interactive
                'strategy': getattr(args, 'context_strategy', 'smart'),
                'threshold': getattr(args, 'context_threshold', 0.8),
                'monitor_enabled': getattr(args, 'context_monitor', False),
                'monitor_path': getattr(args, 'context_monitor_path', './context.txt'),
                'monitor_format': getattr(args, 'context_monitor_format', 'human'),
                'monitor_frequency': getattr(args, 'context_monitor_frequency', 'turn'),
                'redact_sensitive': getattr(args, 'context_redact', True),
                'output_reserve': getattr(args, 'context_output_reserve', 8000),
            }
            session_state['context_config'] = context_config
            
            # Start the execution worker thread (TRUE ASYNC - runs in background)
            worker_thread = self._start_execution_worker(tools_list, console, session_state)
            
            # Try to use prompt_toolkit for autocomplete
            prompt_session = None
            try:
                from prompt_toolkit import PromptSession
                from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
                from prompt_toolkit.history import InMemoryHistory
                from praisonai.cli.features.at_mentions import CombinedCompleter
                
                # Create combined completer for / commands and @ mentions
                commands = ['help', 'exit', 'quit', 'clear', 'tools', 'profile', 'model', 'stats', 'compact', 'undo', 'queue', 'q']
                combined_completer = CombinedCompleter(
                    commands=commands,
                    root_dir=os.getcwd()
                )
                
                prompt_session = PromptSession(
                    message="❯ ",
                    completer=combined_completer,
                    auto_suggest=AutoSuggestFromHistory(),
                    history=InMemoryHistory(),
                    complete_while_typing=True
                )
            except ImportError:
                pass  # Fall back to simple input
            
            # Print welcome message
            console.print("\n[bold cyan]PraisonAI Interactive Mode[/bold cyan]")
            console.print("[dim]Type your prompt, use /help for commands, /exit to quit[/dim]")
            console.print(f"[dim]Model: {session_state['current_model']} | Tools: {len(tools_list)} | Session: {unified_session.session_id}[/dim]")
            if unified_session.message_count > 0:
                console.print(f"[dim]Resumed session with {unified_session.message_count} messages[/dim]")
            console.print("[dim]Use @file.txt to include file content | Queue messages while processing[/dim]\n")
            
            # Start display thread for status updates (non-blocking)
            import time
            from rich.panel import Panel
            
            display_running = {'value': True}
            
            def display_loop():
                """Background thread for status display - NEVER blocks input.
                
                FIFO-aligned display:
                - Default mode: Minimal, calm output. Just show response.
                - Verbose mode: Full task lifecycle with IDs, times, word counts.
                """
                while display_running['value']:
                    try:
                        # Check for completed tasks to display (FIFO order guaranteed)
                        if worker_state['completed_tasks']:
                            task = worker_state['completed_tasks'].pop(0)
                            response = task.get('response', '')
                            
                            # Clear any transient status line
                            if worker_state.get('last_status_line'):
                                console.print("\r" + " " * 80 + "\r", end="")
                                worker_state['last_status_line'] = None
                            
                            console.print()  # New line before response
                            
                            if verbose_mode:
                                # VERBOSE: Full task lifecycle with metadata
                                question = task.get('question', '')
                                task_id = task.get('task_id', 0)
                                elapsed = task.get('elapsed', 0)
                                word_count = len(response.split()) if response else 0
                                q_display = question[:80] + "..." if len(question) > 80 else question
                                
                                console.print(f"[bold cyan]─── Task #{task_id} completed ({elapsed:.1f}s, {word_count} words) ───[/bold cyan]")
                                console.print(f"[bold green]Q:[/bold green] {q_display}")
                                console.print(f"[bold blue]A:[/bold blue] ", end="")
                            
                            # Stream response (both modes)
                            if response:
                                words = response.split()
                                for i, word in enumerate(words):
                                    console.print(word + " ", end="")
                                    if i % 20 == 19:
                                        time.sleep(0.003)
                            console.print()
                            
                            if verbose_mode:
                                task_id = task.get('task_id', 0)
                                console.print(f"[dim]─── End Task #{task_id} ───[/dim]")
                            console.print()
                        
                        # Check for error tasks to display
                        if worker_state['error_tasks']:
                            task = worker_state['error_tasks'].pop(0)
                            error = task.get('error', '')
                            
                            # Clear transient status
                            if worker_state.get('last_status_line'):
                                console.print("\r" + " " * 80 + "\r", end="")
                                worker_state['last_status_line'] = None
                            
                            console.print()
                            if verbose_mode:
                                question = task.get('question', '')
                                task_id = task.get('task_id', 0)
                                q_display = question[:80] + "..." if len(question) > 80 else question
                                console.print(f"[bold red]─── Task #{task_id} failed ───[/bold red]")
                                console.print(f"[bold green]Q:[/bold green] {q_display}")
                            console.print(f"[red]Error: {error}[/red]")
                            console.print()
                        
                        # Check for approval requests
                        try:
                            approval_info = approval_request_queue.get_nowait()
                            
                            function_name = approval_info['function_name']
                            arguments = approval_info['arguments']
                            risk_level = approval_info['risk_level']
                            
                            risk_colors = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "blue"}
                            risk_color = risk_colors.get(risk_level, "white")
                            
                            # Clear transient status
                            if worker_state.get('last_status_line'):
                                console.print("\r" + " " * 80 + "\r", end="")
                                worker_state['last_status_line'] = None
                            
                            console.print()
                            
                            # Show approval panel (both modes)
                            tool_info = f"[bold]Function:[/] {function_name}\n"
                            tool_info += f"[bold]Risk Level:[/] [{risk_color}]{risk_level.upper()}[/{risk_color}]\n"
                            tool_info += "[bold]Arguments:[/]\n"
                            for key, value in arguments.items():
                                str_value = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                                tool_info += f"  {key}: {str_value}\n"
                            
                            console.print(Panel(tool_info.strip(), title="🔒 Tool Approval Required", border_style=risk_color))
                            console.print(f"[{risk_color}]Type 'y' to approve, 'n' to reject:[/{risk_color}] ", end="")
                            
                            worker_state['waiting_for_approval_input'] = True
                            
                        except queue_module.Empty:
                            pass
                        
                        # Show FIFO head status (transient, both modes)
                        current_task = worker_state.get('current_task')
                        if current_task and not worker_state.get('waiting_for_approval_input'):
                            queue_size = execution_queue.qsize()
                            prompt_preview = current_task.get('question', '')[:50]
                            if len(current_task.get('question', '')) > 50:
                                prompt_preview += "..."
                            
                            # Build status line
                            tool_activity = worker_state.get('tool_activity')
                            if tool_activity and tool_activity.get('status') == 'started':
                                tool_name = tool_activity.get('name', '')
                                status_line = f"⚙️  {tool_name}"
                            else:
                                status_line = f"⏳ Processing: {prompt_preview}"
                            
                            if queue_size > 0:
                                status_line += f" | 📋 {queue_size} waiting"
                            
                            # Only update if changed (avoid flicker)
                            if status_line != worker_state.get('last_status_line'):
                                console.print(f"\r[dim cyan]{status_line}[/dim cyan]" + " " * 20, end="\r")
                                worker_state['last_status_line'] = status_line
                        elif not current_task and worker_state.get('last_status_line'):
                            # Clear status when idle
                            console.print("\r" + " " * 80 + "\r", end="")
                            worker_state['last_status_line'] = None
                        
                        time.sleep(0.1)
                    except Exception:
                        pass
            
            # Start display thread
            display_thread = threading.Thread(target=display_loop, daemon=True, name="DisplayLoop")
            display_thread.start()
            
            running = True
            while running:
                try:
                    # Get user input (with autocomplete if available)
                    # This is NON-BLOCKING relative to LLM execution
                    # Status is shown by the display thread, not here
                    if prompt_session:
                        user_input = prompt_session.prompt().strip()
                    else:
                        user_input = input("❯ ").strip()
                    
                    if not user_input:
                        continue
                    
                    # Check if this is an approval response
                    if worker_state.get('waiting_for_approval_input'):
                        try:
                            from praisonaiagents.approval import ApprovalDecision
                            if user_input.lower() in ['y', 'yes', 'approve']:
                                console.print("[green]✅ Approved[/green]")
                                approval_response_queue.put(ApprovalDecision(approved=True, reason="User approved"))
                            else:
                                console.print("[red]❌ Denied[/red]")
                                approval_response_queue.put(ApprovalDecision(approved=False, reason="User denied"))
                            worker_state['waiting_for_approval_input'] = False
                            continue
                        except ImportError:
                            pass
                    
                    # Handle slash commands
                    if user_input.startswith("/"):
                        cmd_parts = user_input[1:].split(maxsplit=1)
                        cmd = cmd_parts[0].lower() if cmd_parts else ""
                        cmd_args = cmd_parts[1] if len(cmd_parts) > 1 else ""
                        
                        if cmd in ["exit", "quit", "q"]:
                            console.print("[dim]Goodbye![/dim]")
                            running = False
                            worker_state['running'] = False
                            display_running['value'] = False
                            continue
                        elif cmd == "help":
                            self._print_interactive_help(console)
                            continue
                        elif cmd == "clear":
                            console.clear()
                            continue
                        elif cmd == "tools":
                            console.print(f"[cyan]Available tools: {len(tools_list)}[/cyan]")
                            for tool in tools_list:
                                name = getattr(tool, '__name__', str(tool))
                                console.print(f"  • {name}")
                            continue
                        elif cmd == "profile":
                            session_state['show_profiling'] = not session_state['show_profiling']
                            status = "enabled" if session_state['show_profiling'] else "disabled"
                            console.print(f"[cyan]Profiling {status}[/cyan]")
                            continue
                        elif cmd == "model":
                            self._handle_model_command(console, cmd_args, session_state)
                            continue
                        elif cmd == "stats":
                            self._handle_stats_command(console, session_state)
                            continue
                        elif cmd == "compact":
                            self._handle_compact_command(console, session_state)
                            continue
                        elif cmd == "context":
                            self._handle_context_command(console, cmd_args, session_state)
                            continue
                        elif cmd == "undo":
                            self._handle_undo_command(console, session_state)
                            continue
                        elif cmd == "queue":
                            self._handle_queue_command(console, cmd_args, session_state)
                            continue
                        elif cmd == "session":
                            # Show session info
                            us = session_state.get('unified_session')
                            if us:
                                console.print(f"[cyan]Session ID:[/cyan] {us.session_id}")
                                console.print(f"[cyan]Messages:[/cyan] {us.message_count}")
                                console.print(f"[cyan]Created:[/cyan] {us.created_at}")
                                console.print(f"[cyan]Updated:[/cyan] {us.updated_at}")
                                console.print(f"[cyan]Total tokens:[/cyan] {us.total_input_tokens + us.total_output_tokens}")
                            continue
                        elif cmd == "history":
                            # Show conversation history
                            us = session_state.get('unified_session')
                            if us and us.messages:
                                console.print(f"[cyan]Conversation history ({len(us.messages)} messages):[/cyan]")
                                for i, msg in enumerate(us.messages[-10:]):  # Show last 10
                                    role = msg.get('role', 'unknown')
                                    content = msg.get('content', '')[:100]
                                    if len(msg.get('content', '')) > 100:
                                        content += "..."
                                    style = "green" if role == "user" else "blue"
                                    console.print(f"  [{style}]{role}:[/{style}] {content}")
                            else:
                                console.print("[dim]No conversation history[/dim]")
                            continue
                        elif cmd == "new":
                            # Start a new session
                            store = session_state.get('session_store')
                            if store:
                                new_session = store.get_or_create()
                                session_state['unified_session'] = new_session
                                session_state['conversation_history'] = []
                                session_state['total_input_tokens'] = 0
                                session_state['total_output_tokens'] = 0
                                session_state['request_count'] = 0
                                console.print(f"[cyan]Started new session: {new_session.session_id}[/cyan]")
                            continue
                        elif cmd == "status":
                            # Show current processing status
                            current = worker_state.get('current_prompt')
                            queue_size = execution_queue.qsize()
                            if current:
                                console.print(f"[cyan]Processing:[/cyan] {current}")
                            if queue_size > 0:
                                console.print(f"[cyan]Queued:[/cyan] {queue_size} messages")
                            if not current and queue_size == 0:
                                console.print("[dim]Idle - no messages processing[/dim]")
                            continue
                        else:
                            console.print(f"[yellow]Unknown command: /{cmd}. Type /help for available commands.[/yellow]")
                            continue
                    
                    # Process @file mentions before sending to LLM
                    processed_input = self._process_at_mentions(user_input, console)
                    
                    # Create task with unique ID and full context
                    task_counter['value'] += 1
                    task_id = task_counter['value']
                    
                    task = {
                        'task_id': task_id,
                        'prompt': processed_input,
                        'question': processed_input,  # Full question for Q/A mapping
                        'status': 'queued',
                        'queued_at': time.time(),
                    }
                    
                    # Submit to execution queue - THIS IS NON-BLOCKING (FIFO)
                    queue_size = execution_queue.qsize()
                    execution_queue.put(task)
                    
                    # Show queue status (minimal by default, verbose shows task IDs)
                    if verbose_mode:
                        q_preview = processed_input[:60] + "..." if len(processed_input) > 60 else processed_input
                        if queue_size > 0:
                            console.print(f"[dim cyan]📋 Task #{task_id} queued (FIFO position {queue_size + 1})[/dim cyan]")
                            console.print(f"[dim]   └─ {q_preview}[/dim]")
                        else:
                            console.print(f"[dim cyan]▶ Task #{task_id} started (FIFO head)[/dim cyan]")
                            console.print(f"[dim]   └─ {q_preview}[/dim]")
                    else:
                        # DEFAULT: Minimal, calm output
                        if queue_size > 0:
                            console.print(f"[dim]📋 Queued ({queue_size + 1} in queue)[/dim]")
                    
                except KeyboardInterrupt:
                    console.print("\n[dim]Use /exit to quit[/dim]")
                except EOFError:
                    running = False
                    
        except ImportError as e:
            print(f"[red]ERROR: Interactive mode requires rich: {e}[/red]")
            print("Install with: pip install rich")
            sys.exit(1)
        except Exception as e:
            print(f"[red]ERROR: Interactive mode failed: {e}[/red]")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def _load_interactive_tools(self):
        """
        Load tools for interactive mode using the canonical provider.
        
        This method uses the centralized interactive_tools module which provides:
        - ACP tools (acp_create_file, acp_edit_file, etc.) for safe file operations
        - LSP tools (lsp_list_symbols, lsp_find_definition, etc.) for code intelligence
        - Basic tools (read_file, write_file, etc.) for standard operations
        
        Tool groups can be disabled via:
        - CLI flags: --no-acp, --no-lsp
        - Env vars: PRAISON_TOOLS_DISABLE=acp,lsp
        """
        # Determine which groups to disable based on CLI args
        disable_groups = []
        if hasattr(self, 'args'):
            if getattr(self.args, 'no_acp', False):
                disable_groups.append('acp')
            if getattr(self.args, 'no_lsp', False):
                disable_groups.append('lsp')
        
        # Get workspace
        workspace = os.getcwd()
        
        try:
            from .features.interactive_tools import get_interactive_tools, ToolConfig
            
            # Create config
            config = ToolConfig.from_env()
            config.workspace = workspace
            
            # Apply CLI overrides
            if 'acp' in disable_groups:
                config.enable_acp = False
            if 'lsp' in disable_groups:
                config.enable_lsp = False
            
            # Get tools from canonical provider
            tools_list = get_interactive_tools(
                config=config,
                disable=disable_groups if disable_groups else None,
            )
            
            logging.debug(f"Loaded {len(tools_list)} interactive tools (ACP: {config.enable_acp}, LSP: {config.enable_lsp})")
            return tools_list
            
        except ImportError as e:
            logging.debug(f"Interactive tools provider not available: {e}")
            # Fallback to basic tools only
            return self._load_basic_tools_fallback()
    
    def _load_basic_tools_fallback(self):
        """Fallback to load basic tools when interactive_tools module unavailable."""
        tools_list = []
        try:
            from praisonaiagents.tools import (
                read_file as tool_read_file,
                write_file as tool_write_file,
                list_files as tool_list_files,
                execute_command,
                internet_search
            )
            tools_list = [tool_read_file, tool_write_file, tool_list_files, execute_command, internet_search]
        except ImportError:
            # Try individual imports
            try:
                from praisonaiagents.tools import read_file as tool_read_file
                tools_list.append(tool_read_file)
            except ImportError:
                pass
            try:
                from praisonaiagents.tools import write_file as tool_write_file
                tools_list.append(tool_write_file)
            except ImportError:
                pass
            try:
                from praisonaiagents.tools import list_files as tool_list_files
                tools_list.append(tool_list_files)
            except ImportError:
                pass
            try:
                from praisonaiagents.tools import execute_command
                tools_list.append(execute_command)
            except ImportError:
                pass
            try:
                from praisonaiagents.tools import internet_search
                tools_list.append(internet_search)
            except ImportError:
                pass
        return tools_list
    
    def _print_interactive_help(self, console):
        """Print help for interactive mode."""
        console.print("\n[bold]Commands:[/bold]")
        console.print("  /help          - Show this help")
        console.print("  /exit          - Exit interactive mode")
        console.print("  /clear         - Clear screen")
        console.print("  /tools         - List available tools")
        console.print("  /profile       - Toggle profiling (show timing breakdown)")
        console.print("  /model [name]  - Show or change current model")
        console.print("  /stats         - Show session statistics (tokens, cost)")
        console.print("  /compact       - Compress conversation history")
        console.print("  /undo          - Undo last response")
        console.print("  /queue         - Show queued messages")
        console.print("  /queue clear   - Clear message queue")
        console.print("\n[bold]Session Commands:[/bold]")
        console.print("  /session       - Show current session info")
        console.print("  /history       - Show conversation history")
        console.print("  /new           - Start a new session")
        console.print("\n[bold]@ Mentions:[/bold]")
        console.print("  @file.txt      - Include file content in prompt")
        console.print("  @src/          - Include directory listing")
        console.print("\n[bold]Features:[/bold]")
        console.print("  • File operations (read, write, list)")
        console.print("  • Shell command execution")
        console.print("  • Web search")
        console.print("  • Context compression for long sessions")
        console.print("  • Persistent sessions (auto-saved)")
        console.print("  • Queue messages while agent is processing")
        console.print("")
    
    def _process_at_mentions(self, user_input, console):
        """
        Process @file mentions in user input.
        
        Supports:
        - @file.txt - Include file content
        - @path/to/file - Include file content
        - @directory/ - Include directory listing
        
        Inspired by Gemini CLI and Claude Code @file syntax.
        """
        import re
        import os
        
        # Pattern to match @path (but not email addresses)
        # Must be at start or preceded by whitespace
        pattern = r'(?:^|\s)@([^\s@]+)'
        
        matches = re.findall(pattern, user_input)
        if not matches:
            return user_input
        
        processed_input = user_input
        file_contents = []
        
        for path in matches:
            # Clean up the path
            clean_path = path.strip()
            
            # Expand ~ to home directory
            if clean_path.startswith('~'):
                clean_path = os.path.expanduser(clean_path)
            
            # Make absolute if relative
            if not os.path.isabs(clean_path):
                clean_path = os.path.abspath(clean_path)
            
            try:
                if os.path.isfile(clean_path):
                    # Read file content
                    with open(clean_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Truncate if too large (>50KB)
                    if len(content) > 50000:
                        content = content[:50000] + "\n... [truncated, file too large]"
                    
                    file_contents.append(f"\n--- Content of {path} ---\n{content}\n--- End of {path} ---\n")
                    console.print(f"[dim]📄 Included: {path} ({len(content)} chars)[/dim]")
                    
                elif os.path.isdir(clean_path):
                    # List directory contents
                    try:
                        entries = os.listdir(clean_path)
                        # Filter out hidden files and common ignore patterns
                        entries = [e for e in entries if not e.startswith('.') and e not in ['node_modules', '__pycache__', 'venv', '.git']]
                        entries.sort()
                        
                        listing = "\n".join(f"  {e}" for e in entries[:50])
                        if len(entries) > 50:
                            listing += f"\n  ... and {len(entries) - 50} more files"
                        
                        file_contents.append(f"\n--- Directory listing of {path} ---\n{listing}\n--- End of {path} ---\n")
                        console.print(f"[dim]📁 Listed: {path} ({len(entries)} items)[/dim]")
                    except PermissionError:
                        console.print(f"[yellow]⚠ Permission denied: {path}[/yellow]")
                else:
                    console.print(f"[yellow]⚠ Not found: {path}[/yellow]")
                    
            except Exception as e:
                console.print(f"[yellow]⚠ Error reading {path}: {e}[/yellow]")
        
        # Remove @mentions from the original input and append file contents
        for path in matches:
            processed_input = processed_input.replace(f"@{path}", "")
        
        processed_input = processed_input.strip()
        if file_contents:
            processed_input = processed_input + "\n" + "\n".join(file_contents)
        
        return processed_input
    
    def _handle_model_command(self, console, args, session_state):
        """Handle /model command - show or change current model."""
        if not args:
            # Show current model
            console.print(f"[cyan]Current model: {session_state['current_model']}[/cyan]")
            console.print("\n[dim]Available models (examples):[/dim]")
            console.print("  • gpt-4o, gpt-4o-mini")
            console.print("  • claude-3-5-sonnet, claude-3-haiku")
            console.print("  • gemini-2.0-flash, gemini-1.5-pro")
            console.print("\n[dim]Usage: /model <model-name>[/dim]")
        else:
            # Change model
            new_model = args.strip()
            old_model = session_state['current_model']
            session_state['current_model'] = new_model
            console.print(f"[green]✓ Model changed: {old_model} → {new_model}[/green]")
    
    def _handle_stats_command(self, console, session_state):
        """Handle /stats command - show session statistics."""
        from praisonai.cli.features.cost_tracker import get_pricing
        
        console.print("\n[bold cyan]Session Statistics[/bold cyan]")
        console.print(f"  Model:          {session_state['current_model']}")
        console.print(f"  Requests:       {session_state['request_count']}")
        console.print(f"  Input tokens:   {session_state['total_input_tokens']:,}")
        console.print(f"  Output tokens:  {session_state['total_output_tokens']:,}")
        console.print(f"  Total tokens:   {session_state['total_input_tokens'] + session_state['total_output_tokens']:,}")
        
        # Calculate estimated cost
        try:
            pricing = get_pricing(session_state['current_model'])
            cost = pricing.calculate_cost(
                session_state['total_input_tokens'],
                session_state['total_output_tokens']
            )
            console.print(f"  Estimated cost: ${cost:.4f}")
        except Exception:
            pass
        
        # Show conversation history size
        history_len = len(session_state['conversation_history'])
        console.print(f"  History turns:  {history_len}")
        console.print("")
    
    def _handle_compact_command(self, console, session_state):
        """
        Handle /compact command - compress conversation history.
        
        Inspired by Claude Code's /compact and Gemini CLI's /compress.
        Uses LLM to summarize older conversation turns while keeping recent ones.
        """
        history = session_state['conversation_history']
        
        if len(history) < 4:
            console.print("[yellow]Not enough conversation history to compact (need at least 4 turns)[/yellow]")
            return
        
        console.print("[dim]Compacting conversation history...[/dim]")
        
        try:
            from praisonaiagents import Agent
            
            # Keep the last 2 turns (4 messages: 2 user + 2 assistant)
            keep_count = 4
            to_compress = history[:-keep_count] if len(history) > keep_count else []
            to_keep = history[-keep_count:] if len(history) > keep_count else history
            
            if not to_compress:
                console.print("[yellow]Not enough old history to compress[/yellow]")
                return
            
            # Format history for summarization
            history_text = ""
            for i, msg in enumerate(to_compress):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                if len(content) > 500:
                    content = content[:500] + "..."
                history_text += f"{role}: {content}\n\n"
            
            # Create summarization prompt
            summary_prompt = f"""Summarize the following conversation history into a concise state snapshot.
Focus on:
- Key facts and decisions made
- Important context that should be remembered
- Any ongoing tasks or goals

Conversation to summarize:
{history_text}

Provide a concise summary (max 200 words):"""
            
            # Use a lightweight agent for summarization
            summarizer = Agent(
                name="Summarizer",
                role="Conversation Summarizer",
                goal="Create concise summaries of conversations",
                backstory="You summarize conversations while preserving key information.",
                output="minimal",
                llm=session_state['current_model']
            )
            
            summary = summarizer.chat(summary_prompt, stream=False)
            
            # Replace old history with summary + recent turns
            new_history = [
                {"role": "system", "content": f"[Previous conversation summary]: {summary}"},
                *to_keep
            ]
            
            old_count = len(history)
            session_state['conversation_history'] = new_history
            new_count = len(new_history)
            
            console.print(f"[green]✓ Compacted {old_count} turns → {new_count} turns[/green]")
            console.print(f"[dim]Summary: {str(summary)[:100]}...[/dim]")
            
        except Exception as e:
            console.print(f"[red]Error compacting: {e}[/red]")
    
    def _handle_context_command(self, console, args, session_state):
        """
        Handle /context command - manage context budgeting and monitoring.
        
        Usage:
        - /context              - Show context stats
        - /context show         - Show summary + budgets
        - /context stats        - Token ledger table
        - /context budget       - Budget allocation details
        - /context dump         - Write snapshot now
        - /context on           - Enable monitoring
        - /context off          - Disable monitoring
        - /context path <path>  - Set snapshot path
        - /context format <fmt> - Set format (human/json)
        - /context frequency <f>- Set frequency
        - /context compact      - Trigger optimization
        """
        try:
            from praisonai.cli.features.context_manager import (
                handle_context_command,
                ContextManagerHandler,
            )
            
            # Get or create context manager
            context_manager = session_state.get("context_manager")
            if context_manager is None:
                context_manager = ContextManagerHandler(
                    model=session_state.get("current_model", "gpt-4o-mini"),
                    session_id=session_state.get("session_id", ""),
                )
                session_state["context_manager"] = context_manager
            
            handle_context_command(console, args, session_state, context_manager)
            
        except Exception as e:
            console.print(f"[red]Error handling context command: {e}[/red]")
    
    def _handle_undo_command(self, console, session_state):
        """
        Handle /undo command - undo the last response.
        
        Inspired by Codex CLI's /undo and Gemini CLI's /restore.
        Removes the last user prompt and assistant response from history.
        """
        history = session_state['conversation_history']
        undo_stack = session_state['undo_stack']
        
        if len(history) < 2:
            console.print("[yellow]Nothing to undo[/yellow]")
            return
        
        # Remove last assistant response and user prompt
        if len(history) >= 2:
            removed_assistant = history.pop()
            removed_user = history.pop()
            
            # Store in undo stack for potential redo
            undo_stack.append((removed_user, removed_assistant))
            
            console.print("[green]✓ Undone last turn[/green]")
            console.print(f"[dim]Removed: {str(removed_user.get('content', ''))[:50]}...[/dim]")
        else:
            console.print("[yellow]Not enough history to undo[/yellow]")
    
    def _handle_queue_command(self, console, args, session_state):
        """
        Handle /queue command - show or manage message queue.
        
        Usage:
        - /queue       - Show queued messages
        - /queue clear - Clear the queue
        - /queue remove N - Remove message at index N
        """
        message_queue = session_state.get('message_queue')
        state_manager = session_state.get('state_manager')
        queue_display = session_state.get('queue_display')
        
        if not message_queue:
            console.print("[yellow]Message queue not initialized[/yellow]")
            return
        
        args = args.strip().lower() if args else ""
        
        if args == "clear":
            count = message_queue.count
            message_queue.clear()
            console.print(f"[green]✓ Cleared {count} queued message(s)[/green]")
        elif args.startswith("remove "):
            try:
                index = int(args.split()[1])
                removed = message_queue.remove_at(index)
                if removed:
                    console.print(f"[green]✓ Removed: {removed[:50]}...[/green]")
                else:
                    console.print(f"[yellow]Invalid index: {index}[/yellow]")
            except (ValueError, IndexError):
                console.print("[yellow]Usage: /queue remove <index>[/yellow]")
        else:
            # Show queue status
            if state_manager:
                status = queue_display.format_status() if queue_display else ""
                if status:
                    console.print(f"[cyan]{status}[/cyan]")
            
            if message_queue.is_empty:
                console.print("[dim]No messages in queue[/dim]")
            else:
                console.print(f"\n[bold cyan]Queued Messages ({message_queue.count}):[/bold cyan]")
                for i, msg in enumerate(message_queue.get_all()):
                    display_msg = msg[:60] + "..." if len(msg) > 60 else msg
                    console.print(f"  {i}. ↳ {display_msg}")
                console.print("\n[dim]Use /queue clear to clear, /queue remove N to remove[/dim]")
    
    def _run_chat_mode(self, prompt, args):
        """
        Run a single prompt in interactive style (non-interactive mode for testing).
        
        Usage: praisonai "your prompt" --chat
               praisonai "your prompt" --chat-mode  (alias)
        
        This runs the prompt using the same agent/tools as interactive mode
        but exits after one response (useful for testing and scripting).
        """
        from rich.console import Console
        
        console = Console()
        self._interactive_mode = True  # Use interactive mode settings
        
        # Load tools
        tools_list = self._load_interactive_tools()
        
        console.print(f"[dim]Chat mode: {len(tools_list)} tools available[/dim]")
        console.print(f"[dim]Prompt: {prompt[:50]}{'...' if len(prompt) > 50 else ''}[/dim]\n")
        
        # Process the prompt with profiling enabled for testing
        self._process_interactive_prompt(prompt, tools_list, console, show_profiling=True)
        
        return None
    
    def _start_execution_worker(self, tools_list, console, session_state):
        """
        Start the background execution worker thread.
        
        This worker continuously processes messages from the queue,
        allowing the main input loop to remain non-blocking.
        """
        import threading
        import time
        import sys
        import queue as queue_module
        from rich.panel import Panel
        from praisonai.cli.features.message_queue import ProcessingState
        
        state_manager = session_state['state_manager']
        message_queue = session_state['message_queue']
        live_status = session_state['live_status']
        execution_queue = session_state['execution_queue']
        approval_request_queue = session_state['approval_request_queue']
        approval_response_queue = session_state['approval_response_queue']
        worker_state = session_state['worker_state']
        
        # Check if trust mode is enabled (via --trust flag or PRAISON_APPROVAL_MODE=auto env var)
        trust_mode = getattr(self.args, 'trust', False) if hasattr(self, 'args') else False
        approval_mode_env = os.environ.get("PRAISON_APPROVAL_MODE", "").lower()
        if approval_mode_env == "auto":
            trust_mode = True
        
        def worker_loop():
            """Main worker loop - processes execution queue."""
            while worker_state['running']:
                try:
                    # Wait for a message with timeout (allows checking running flag)
                    try:
                        task = execution_queue.get(timeout=0.5)
                    except queue_module.Empty:
                        continue
                    
                    # Extract task context
                    prompt = task.get('prompt', '')
                    task_id = task.get('task_id', 0)
                    question = task.get('question', prompt)
                    start_time = time.time()
                    
                    # Set processing state with full task context
                    state_manager.set_state(ProcessingState.PROCESSING)
                    task['status'] = 'running'
                    task['start_time'] = start_time
                    worker_state['current_task'] = task  # Full task context
                    live_status.clear()
                    live_status.update_status(f"Task #{task_id}: Thinking...")
                    
                    try:
                        from praisonaiagents import Agent
                        import logging
                        import warnings
                        
                        # Suppress noisy loggers
                        for logger_name in ["httpx", "httpcore", "duckduckgo_search", "crawl4ai"]:
                            logging.getLogger(logger_name).setLevel(logging.WARNING)
                        
                        # Set up approval callback
                        try:
                            from praisonaiagents.approval import set_approval_callback, ApprovalDecision
                            
                            if trust_mode:
                                def auto_approve_all(function_name, arguments, risk_level):
                                    return ApprovalDecision(approved=True, reason="Auto-approved via --trust flag")
                                set_approval_callback(auto_approve_all)
                            else:
                                def interactive_approval_callback(function_name, arguments, risk_level):
                                    """Request approval from main thread via queue."""
                                    approval_request_queue.put({
                                        'function_name': function_name,
                                        'arguments': arguments,
                                        'risk_level': risk_level
                                    })
                                    worker_state['approval_pending'] = True
                                    
                                    try:
                                        response = approval_response_queue.get(timeout=120)
                                        worker_state['approval_pending'] = False
                                        return response
                                    except queue_module.Empty:
                                        worker_state['approval_pending'] = False
                                        return ApprovalDecision(approved=False, reason="Approval timeout")
                                
                                set_approval_callback(interactive_approval_callback)
                        except ImportError:
                            pass
                        
                        with warnings.catch_warnings():
                            warnings.filterwarnings("ignore")
                            
                            model = session_state.get('current_model')
                            conversation_history = session_state.get('conversation_history', [])
                            
                            live_status.update_status("Creating agent...")
                            
                            # Build backstory with context
                            backstory = "You are a helpful AI assistant with access to tools for file operations, code intelligence, and shell commands."
                            if conversation_history:
                                recent = conversation_history[-10:]
                                context_lines = []
                                for msg in recent:
                                    role = msg.get('role', 'unknown')
                                    content = msg.get('content', '')[:200]
                                    context_lines.append(f"{role}: {content}")
                                if context_lines:
                                    backstory += "\n\nRecent conversation context:\n" + "\n".join(context_lines)
                            
                            agent = Agent(
                                name="Assistant",
                                role="Helpful AI Assistant",
                                goal="Help the user with their tasks",
                                backstory=backstory,
                                tools=tools_list if tools_list else None,
                                output="minimal",
                                llm=model
                            )
                            
                            live_status.update_status(f"Task #{task_id}: Calling LLM...")
                            
                            response = agent.chat(prompt, stream=False)
                            response_str = str(response) if response else ""
                            
                            # Calculate elapsed time
                            elapsed = time.time() - start_time
                            
                            # Store completed task for display with Q/A mapping
                            completed_task = {
                                'task_id': task_id,
                                'question': task.get('question', prompt),
                                'response': response_str,
                                'elapsed': elapsed,
                                'status': 'completed',
                            }
                            worker_state['completed_tasks'].append(completed_task)
                            
                            # Update session state
                            input_tokens = len(prompt) // 4
                            output_tokens = len(response_str) // 4
                            session_state['total_input_tokens'] += input_tokens
                            session_state['total_output_tokens'] += output_tokens
                            session_state['request_count'] += 1
                            session_state['conversation_history'].append({'role': 'user', 'content': prompt})
                            session_state['conversation_history'].append({'role': 'assistant', 'content': response_str})
                            
                            # Persist to UnifiedSession
                            if 'unified_session' in session_state and 'session_store' in session_state:
                                unified_session = session_state['unified_session']
                                unified_session.add_user_message(prompt)
                                unified_session.add_assistant_message(response_str)
                                unified_session.update_stats(input_tokens, output_tokens)
                                session_state['session_store'].save(unified_session)
                    
                    except Exception as e:
                        # Store error task for display with Q/A mapping
                        error_task = {
                            'task_id': task_id,
                            'question': task.get('question', prompt),
                            'error': str(e),
                            'status': 'failed',
                        }
                        worker_state['error_tasks'].append(error_task)
                    
                    finally:
                        worker_state['current_task'] = None
                        worker_state['tool_activity'] = None
                        state_manager.set_state(ProcessingState.IDLE)
                        live_status.clear()
                        execution_queue.task_done()
                
                except Exception as e:
                    import traceback
                    traceback.print_exc()
        
        # Start worker thread
        worker_thread = threading.Thread(target=worker_loop, daemon=True, name="ExecutionWorker")
        worker_thread.start()
        return worker_thread
    
    def _submit_prompt_to_worker(self, prompt, session_state):
        """
        Submit a prompt to the execution worker queue.
        
        This is NON-BLOCKING - returns immediately after queuing.
        """
        execution_queue = session_state['execution_queue']
        execution_queue.put({'prompt': prompt})
    
    def _process_interactive_prompt_async(self, prompt, tools_list, console, session_state=None):
        """
        DEPRECATED: This method is kept for backward compatibility.
        Use _submit_prompt_to_worker instead for true non-blocking behavior.
        """
        # Just submit to worker queue - non-blocking
        self._submit_prompt_to_worker(prompt, session_state)
    
    def _process_interactive_prompt(self, prompt, tools_list, console, show_profiling=False, session_state=None):
        """Process a prompt in interactive mode with streaming."""
        from rich.live import Live
        from rich.spinner import Spinner
        import sys
        import warnings
        import logging
        import time
        
        # Profiling timestamps
        timings = {}
        timings['start'] = time.time()
        
        # Store original log levels to restore later (no global impact)
        original_levels = {}
        loggers_to_suppress = ["httpx", "httpcore", "duckduckgo_search", "crawl4ai", "lib"]
        for logger_name in loggers_to_suppress:
            logger = logging.getLogger(logger_name)
            original_levels[logger_name] = logger.level
            logger.setLevel(logging.WARNING)
        
        # Temporarily filter warnings (scoped to this function)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*duckduckgo_search.*")
            warnings.filterwarnings("ignore", message=".*has been renamed.*")
        
        try:
            # Import agent
            timings['import_start'] = time.time()
            from praisonaiagents import Agent
            timings['import_end'] = time.time()
            
            # Set up auto-approval if PRAISON_APPROVAL_MODE=auto
            approval_mode_env = os.environ.get("PRAISON_APPROVAL_MODE", "").lower()
            trust_mode = getattr(self.args, 'trust', False) if hasattr(self, 'args') else False
            if approval_mode_env == "auto" or trust_mode:
                try:
                    from praisonaiagents.approval import set_approval_callback, ApprovalDecision
                    def auto_approve_all(function_name, arguments, risk_level):
                        return ApprovalDecision(approved=True, reason="Auto-approved via PRAISON_APPROVAL_MODE=auto")
                    set_approval_callback(auto_approve_all)
                except ImportError:
                    pass
            
            # Determine model to use
            model = None
            if session_state and session_state.get('current_model'):
                model = session_state['current_model']
            elif hasattr(self, 'args') and getattr(self.args, 'llm', None):
                model = self.args.llm
            
            # Show thinking indicator and create agent
            timings['agent_create_start'] = time.time()
            with Live(Spinner("dots", text="Thinking...", style="cyan"), console=console, refresh_per_second=10, transient=True):
                # Create agent with tools
                agent = Agent(
                    name="Assistant",
                    role="Helpful AI Assistant", 
                    goal="Help the user with their tasks",
                    backstory="You are a helpful AI assistant with access to tools for file operations, shell commands, and web search. Use tools when needed to complete tasks.",
                    tools=tools_list if tools_list else None,
                    output="minimal",  # Suppress verbose panels
                    llm=model
                )
            timings['agent_create_end'] = time.time()
            
            # Get response
            console.print()  # New line before response
            
            timings['llm_start'] = time.time()
            
            # Use chat method (streaming is handled internally by verbose mode)
            response = agent.chat(prompt, stream=False)
            
            timings['llm_end'] = time.time()
            
            # Check if tools were used by looking at agent's tool execution history
            if hasattr(agent, '_tool_calls') and agent._tool_calls:
                for tool_call in agent._tool_calls:
                    tool_name = tool_call.get('name', 'unknown')
                    console.print(f"[dim]⚙ Used tool: {tool_name}[/dim]")
            
            # Print response with simulated streaming effect
            timings['display_start'] = time.time()
            response_str = str(response) if response else ""
            if response_str:
                words = response_str.split()
                for i, word in enumerate(words):
                    console.print(word + " ", end="")
                    sys.stdout.flush()
                    if i % 15 == 14:  # Small pause every 15 words for streaming effect
                        time.sleep(0.005)
                console.print()  # Final newline
            timings['display_end'] = time.time()
            
            # Update session state with token estimates and history
            if session_state is not None:
                # Estimate tokens (rough: ~4 chars per token)
                input_tokens = len(prompt) // 4
                output_tokens = len(response_str) // 4
                
                session_state['total_input_tokens'] += input_tokens
                session_state['total_output_tokens'] += output_tokens
                session_state['request_count'] += 1
                
                # Add to conversation history
                session_state['conversation_history'].append({
                    'role': 'user',
                    'content': prompt
                })
                session_state['conversation_history'].append({
                    'role': 'assistant',
                    'content': response_str
                })
                
                # Persist to UnifiedSession
                if 'unified_session' in session_state and 'session_store' in session_state:
                    unified_session = session_state['unified_session']
                    unified_session.add_user_message(prompt)
                    unified_session.add_assistant_message(response_str)
                    unified_session.update_stats(input_tokens, output_tokens)
                    session_state['session_store'].save(unified_session)
            
            # Show profiling if enabled
            if show_profiling:
                timings['total'] = time.time() - timings['start']
                console.print("\n[dim]─── Profiling ───[/dim]")
                console.print(f"[dim]Import:      {(timings['import_end'] - timings['import_start'])*1000:.1f}ms[/dim]")
                console.print(f"[dim]Agent setup: {(timings['agent_create_end'] - timings['agent_create_start'])*1000:.1f}ms[/dim]")
                console.print(f"[dim]LLM call:    {(timings['llm_end'] - timings['llm_start'])*1000:.1f}ms[/dim]")
                console.print(f"[dim]Display:     {(timings['display_end'] - timings['display_start'])*1000:.1f}ms[/dim]")
                console.print(f"[dim]Total:       {timings['total']*1000:.1f}ms[/dim]")
            
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
        finally:
            # Restore original log levels (no global impact on main package)
            for logger_name, level in original_levels.items():
                logging.getLogger(logger_name).setLevel(level)

if __name__ == "__main__":
    praison_ai = PraisonAI()
    praison_ai.main()
