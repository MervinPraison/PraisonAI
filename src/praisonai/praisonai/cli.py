# praisonai/cli.py

import sys
import argparse
from .version import __version__
import yaml
import os
import time
from rich import print
from dotenv import load_dotenv
load_dotenv()
import shutil
import subprocess
import logging
import importlib

from .auto import AutoGenerator
from .agents_generator import AgentsGenerator
from .inbuilt_tools import *
from .inc.config import generate_config

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

try:
    import gradio as gr
    GRADIO_AVAILABLE = True
except ImportError:
    pass

try:
    import praisonai.api.call as call_module
    CALL_MODULE_AVAILABLE = True
except ImportError:
    pass

try:
    import crewai
    CREWAI_AVAILABLE = True
except ImportError:
    pass

try:
    import autogen
    AUTOGEN_AVAILABLE = True
except ImportError:
    pass

try:
    from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, PraisonAIAgents
    PRAISONAI_AVAILABLE = True
except ImportError:
    pass

try:
    from unsloth import FastLanguageModel
    TRAIN_AVAILABLE = True
except ImportError:
    pass

logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO'), format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('alembic').setLevel(logging.ERROR)
logging.getLogger('gradio').setLevel(logging.ERROR)
logging.getLogger('gradio').setLevel(os.environ.get('GRADIO_LOGLEVEL', 'WARNING'))
logging.getLogger('rust_logger').setLevel(logging.WARNING)
logging.getLogger('duckduckgo').setLevel(logging.ERROR)
logging.getLogger('_client').setLevel(logging.ERROR)

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
        # Create config_list with AutoGen compatibility
        # Support multiple environment variable patterns for better compatibility
        # Priority order: MODEL_NAME > OPENAI_MODEL_NAME for model selection
        model_name = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME", "gpt-5-nano")
        
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
        
        args = self.parse_args()
        # Store args for use in handle_direct_prompt
        self.args = args
        invocation_cmd = "praisonai"
        version_string = f"PraisonAI version {__version__}"

        self.framework = args.framework or self.framework

        # Check for piped input from stdin
        stdin_input = self.read_stdin_if_available()
        
        # Check for file input if --file is provided
        file_input = self.read_file_if_provided(getattr(args, 'file', None))

        if args.command:
            if args.command.startswith("tests.test") or args.command.startswith("tests/test"):  # Argument used for testing purposes
                print("test")
                return "test"
            else:
                # Combine command with any available inputs (stdin and/or file)
                combined_inputs = []
                if stdin_input:
                    combined_inputs.append(stdin_input)
                if file_input:
                    combined_inputs.append(file_input)
                
                if combined_inputs:
                    combined_prompt = f"{args.command} {' '.join(combined_inputs)}"
                    result = self.handle_direct_prompt(combined_prompt)
                    print(result)
                    return result
                else:
                    self.agent_file = args.command
        elif hasattr(args, 'direct_prompt') and args.direct_prompt:
            # Only handle direct prompt if agent_file wasn't explicitly set in constructor
            if original_agent_file == "agents.yaml":  # Default value, so safe to use direct prompt
                # Combine direct prompt with any available inputs (stdin and/or file)
                prompt_parts = [args.direct_prompt]
                if stdin_input:
                    prompt_parts.append(stdin_input)
                if file_input:
                    prompt_parts.append(file_input)
                prompt = ' '.join(prompt_parts)
                result = self.handle_direct_prompt(prompt)
                print(result)
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
                print(result)
                return result
        # If no command or direct_prompt, preserve agent_file from constructor (don't overwrite)

        if args.deploy:
            if args.schedule or args.schedule_config:
                # Scheduled deployment
                from .scheduler import create_scheduler
                
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
                # One-time deployment (backward compatible)
                from .deploy import CloudDeployer
                deployer = CloudDeployer()
                deployer.run_commands()
            return

        if getattr(args, 'chat', False):
            self.create_chainlit_chat_interface()
            return

        if getattr(args, 'code', False):
            self.create_code_interface()
            return

        if getattr(args, 'realtime', False):
            self.create_realtime_interface()
            return

        if getattr(args, 'call', False):
            call_args = []
            if args.public:
                call_args.append('--public')
            call_module.main(call_args)
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
                config = generate_config(
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
                config = generate_config(
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
            generator = AutoGenerator(topic=self.topic, framework=self.framework, agent_file=self.agent_file)
            self.agent_file = generator.generate(merge=getattr(args, 'merge', False))
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
            return default_args
        
        # Define special commands
        special_commands = ['chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research']
        
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
        parser.add_argument("--save", "-s", action="store_true", help="Save research output to file (output/research/)")
        parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output for research")
        parser.add_argument("--web-search", action="store_true", help="Enable native web search (OpenAI, Gemini, Anthropic, xAI, Perplexity)")
        parser.add_argument("--web-fetch", action="store_true", help="Enable web fetch to retrieve URL content (Anthropic only)")
        parser.add_argument("--prompt-caching", action="store_true", help="Enable prompt caching to reduce costs (OpenAI, Anthropic, Bedrock, Deepseek)")
        
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
        if args.command == 'chat':
            args.ui = 'chainlit'
            args.chat = True
        if args.command == 'code':
            args.ui = 'chainlit'
            args.code = True
        
        # Handle --claudecode flag for code command
        if getattr(args, 'claudecode', False):
            os.environ["PRAISONAI_CLAUDECODE_ENABLED"] = "true"
        if args.command == 'realtime':
            args.realtime = True
        if args.command == 'call':
            args.call = True

        # Handle both command and flag versions for call
        if args.command == 'call' or args.call:
            if not CALL_MODULE_AVAILABLE:
                print("[red]ERROR: Call feature is not installed. Install with:[/red]")
                print("\npip install \"praisonai[call]\"\n")
                sys.exit(1)
            
            call_args = []
            if args.public:
                call_args.append('--public')
            call_module.main(call_args)
            sys.exit(0)

        # Handle special commands
        if args.command in special_commands:
            if args.command == 'chat':
                if not CHAINLIT_AVAILABLE:
                    print("[red]ERROR: Chat UI is not installed. Install with:[/red]")
                    print("\npip install \"praisonai[chat]\"\n")
                    sys.exit(1)
                try:
                    self.create_chainlit_chat_interface()
                except ModuleNotFoundError as e:
                    missing_module = str(e).split("'")[1]
                    print(f"[red]ERROR: Missing dependency {missing_module}. Install with:[/red]")
                    print(f"\npip install \"praisonai[chat]\"\n")
                    sys.exit(1)
                sys.exit(0)

            elif args.command == 'code':
                if not CHAINLIT_AVAILABLE:
                    print("[red]ERROR: Code UI is not installed. Install with:[/red]")
                    print("\npip install \"praisonai[code]\"\n")
                    sys.exit(1)
                try:
                    self.create_code_interface()
                except ModuleNotFoundError as e:
                    missing_module = str(e).split("'")[1]
                    print(f"[red]ERROR: Missing dependency {missing_module}. Install with:[/red]")
                    print(f"\npip install \"praisonai[code]\"\n")
                    sys.exit(1)
                sys.exit(0)

            elif args.command == 'call':
                if not CALL_MODULE_AVAILABLE:
                    print("[red]ERROR: Call feature is not installed. Install with:[/red]")
                    print("\npip install \"praisonai[call]\"\n")
                    sys.exit(1)
                call_module.main()
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

        # Only check framework availability for agent-related operations
        if not args.command and (args.init or args.auto or args.framework):
            if not CREWAI_AVAILABLE and not AUTOGEN_AVAILABLE and not PRAISONAI_AVAILABLE:
                print("[red]ERROR: No framework is installed. Please install at least one framework:[/red]")
                print("\npip install \"praisonai\\[crewai]\"  # For CrewAI")
                print("pip install \"praisonai\\[autogen]\"  # For AutoGen")
                print("pip install \"praisonai\\[crewai,autogen]\"  # For both frameworks\n")
                print("pip install praisonaiagents # For PraisonAIAgents\n")  
                sys.exit(1)

        # Handle direct prompt if command is not a special command or file
        # Skip this during testing to avoid pytest arguments interfering
        if not in_test_env and args.command and not args.command.endswith('.yaml') and args.command not in special_commands:
            args.direct_prompt = args.command
            args.command = None

        return args

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

    def handle_direct_prompt(self, prompt):
        """
        Handle direct prompt by creating a single agent and running it.
        """
        # Apply query rewriting if enabled
        prompt = self._rewrite_query_if_enabled(prompt)
        # Apply prompt expansion if enabled
        prompt = self._expand_prompt_if_enabled(prompt)
        
        if PRAISONAI_AVAILABLE:
            agent_config = {
                "name": "DirectAgent",
                "role": "Assistant",
                "goal": "Complete the given task",
                "backstory": "You are a helpful AI assistant"
            }
            
            # Add llm if specified
            if hasattr(self, 'args') and self.args.llm:
                agent_config["llm"] = self.args.llm
            
            # Add feature flags if enabled
            if hasattr(self, 'args'):
                if getattr(self.args, 'web_search', False):
                    agent_config["web_search"] = True
                if getattr(self.args, 'web_fetch', False):
                    agent_config["web_fetch"] = True
                if getattr(self.args, 'prompt_caching', False):
                    agent_config["prompt_caching"] = True
            
            agent = PraisonAgent(**agent_config)
            result = agent.start(prompt)
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
            print("pip install praisonaiagents # For PraisonAIAgents\n")  
            sys.exit(1)

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
            def generate_crew_and_kickoff_interface(auto_args, framework):
                self.framework = framework
                self.agent_file = "test.yaml"
                generator = AutoGenerator(topic=auto_args, framework=self.framework)
                self.agent_file = generator.generate()
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
            model_name = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME", "gpt-5-nano")
            
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
                from praisonaiagents import Agent, Task, PraisonAIAgents
                
                # Create a research assistant agent with tools
                research_assistant = Agent(
                    name="Research Assistant",
                    role="Information Gatherer",
                    goal="Gather relevant information using available tools",
                    backstory="You are an expert at using tools to gather information for research.",
                    tools=tools_list,
                    llm="gpt-4o-mini",
                    verbose=False
                )
                
                # Create task to gather initial information
                gather_task = Task(
                    description=f"Use your tools to gather relevant information about: {query}",
                    expected_output="A summary of information gathered from the tools",
                    agent=research_assistant
                )
                
                print("[cyan]Gathering information with tools...[/cyan]")
                agents = PraisonAIAgents(agents=[research_assistant], tasks=[gather_task], verbose=0)
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

if __name__ == "__main__":
    praison_ai = PraisonAI()
    praison_ai.main()
