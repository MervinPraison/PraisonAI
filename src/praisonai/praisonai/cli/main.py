# praisonai/cli/main.py

import sys
import argparse
from praisonai.version import __version__
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

from praisonai.auto import AutoGenerator
from praisonai.agents_generator import AgentsGenerator
from praisonai.inbuilt_tools import *
from praisonai.inc.config import generate_config

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
                # One-time deployment (backward compatible)
                from praisonai.deploy import CloudDeployer
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
        special_commands = ['chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research', 'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools', 'todo', 'docs', 'mcp', 'commit']
        
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
        
        # Image - vision processing
        parser.add_argument("--image", type=str, help="Path to image file for vision-based tasks")
        
        # Telemetry - usage monitoring
        parser.add_argument("--telemetry", action="store_true", help="Enable usage monitoring and analytics")
        
        # MCP - Model Context Protocol
        parser.add_argument("--mcp", type=str, help="MCP server command (e.g., 'npx -y @modelcontextprotocol/server-filesystem .')")
        parser.add_argument("--mcp-env", type=str, help="MCP environment variables (KEY=value,KEY2=value2)")
        
        # Fast Context - codebase search
        parser.add_argument("--fast-context", type=str, help="Path to search for relevant code context")
        
        # Handoff - agent delegation
        parser.add_argument("--handoff", type=str, help="Comma-separated agent roles for task delegation")
        
        # Auto Memory - automatic memory extraction
        parser.add_argument("--auto-memory", action="store_true", help="Enable automatic memory extraction")
        
        # Todo - task list generation
        parser.add_argument("--todo", action="store_true", help="Generate todo list from task")
        
        # Router - smart model selection
        parser.add_argument("--router", action="store_true", help="Auto-select best model based on task complexity")
        parser.add_argument("--router-provider", type=str, help="Preferred provider for router (openai, anthropic, google)")
        
        # Flow Display - visual workflow
        parser.add_argument("--flow-display", action="store_true", help="Enable visual workflow tracking")
        
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
                
                # Show recent memories
                print("\n[bold]Recent Short-term Memories:[/bold]")
                short_term = memory.get_short_term(limit=5)
                for i, item in enumerate(short_term, 1):
                    content = item.get('content', str(item))[:100]
                    print(f"  {i}. {content}")
                
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
                        import datetime
                        output_dir = os.path.join(os.getcwd(), "output", "workflows")
                        os.makedirs(output_dir, exist_ok=True)
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
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
                
            elif action == 'help' or action == '--help':
                print("[bold]Workflow Commands:[/bold]")
                print("  praisonai workflow list                  - List available workflows")
                print("  praisonai workflow run <name>            - Execute a workflow")
                print("  praisonai workflow run <file.yaml>       - Execute a YAML workflow")
                print("  praisonai workflow show <name>           - Show workflow details")
                print("  praisonai workflow create <name>         - Create a new workflow")
                print("  praisonai workflow validate <file.yaml>  - Validate a YAML workflow")
                print("  praisonai workflow template <name>       - Create from template")
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
        try:
            from praisonaiagents.workflows import WorkflowManager
            from rich import print
            from rich.table import Table
            from rich.console import Console
            
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
            
            print(f"[bold cyan]Running YAML workflow: {yaml_file}[/bold cyan]")
            if parsed_vars:
                print(f"[cyan]Variables: {parsed_vars}[/cyan]")
            
            # Load and execute the YAML workflow
            workflow = manager.load_yaml(yaml_file)
            
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
                
        except FileNotFoundError:
            print(f"[red]ERROR: YAML file not found: {yaml_file}[/red]")
        except Exception as e:
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
            
            console = Console()
            
            if not os.path.exists(yaml_file):
                print(f"[red]ERROR: File not found: {yaml_file}[/red]")
                return
            
            print(f"[cyan]Validating: {yaml_file}[/cyan]")
            
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
            
        except Exception as e:
            print(f"[red]✗ Validation failed: {e}[/red]")

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
            action: The knowledge action (add, search, list, clear, info)
            action_args: Additional arguments for the action
        """
        try:
            from .features.knowledge import KnowledgeHandler
            handler = KnowledgeHandler(verbose=True, workspace=os.getcwd())
            handler.execute(action, action_args)
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
            action: The docs action (list, show, create, delete)
            action_args: Additional arguments for the action
        """
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
                
            elif action == 'help' or action == '--help':
                print("[bold]MCP Commands:[/bold]")
                print("  praisonai mcp list                              - List all MCP configs")
                print("  praisonai mcp show <name>                       - Show specific config")
                print("  praisonai mcp create <name> <cmd> [args...]     - Create a new config")
                print("  praisonai mcp delete <name>                     - Delete a config")
                print("  praisonai mcp enable <name>                     - Enable a config")
                print("  praisonai mcp disable <name>                    - Disable a config")
                print("\n[bold]Config Location:[/bold]")
                print("  .praison/mcp/*.json, ~/.praison/mcp/*.json")
                print("\n[bold]Example:[/bold]")
                print("  praisonai mcp create filesystem npx -y @modelcontextprotocol/server-filesystem .")
            else:
                print(f"[red]Unknown mcp action: {action}[/red]")
                print("Use 'praisonai mcp help' for available commands")
                
        except ImportError as e:
            print(f"[red]ERROR: Failed to import mcp module: {e}[/red]")
            print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        except Exception as e:
            print(f"[red]ERROR: MCP command failed: {e}[/red]")

    def handle_commit_command(self, args: list):
        """
        Handle AI commit message generation.
        
        Generates a commit message based on staged changes using AI.
        
        Args:
            args: Additional arguments (e.g., --push to auto-push)
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
            
            # Get staged diff
            result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                capture_output=True,
                text=True
            )
            
            if not result.stdout.strip():
                print("[yellow]No staged changes. Use 'git add' to stage files first.[/yellow]")
                return
            
            # Get detailed diff for context
            diff_result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True,
                text=True
            )
            
            # Limit diff size for context
            diff_content = diff_result.stdout[:8000] if len(diff_result.stdout) > 8000 else diff_result.stdout
            
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
                import datetime
                output_dir = os.path.join(os.getcwd(), "output", "workflows")
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
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
            agent_config = {
                "name": "DirectAgent",
                "role": "Assistant",
                "goal": "Complete the given task",
                "backstory": "You are a helpful AI assistant"
            }
            
            # Add llm if specified
            if hasattr(self, 'args') and self.args.llm:
                # Check if max_tokens is specified - pass as dict config
                max_tokens = getattr(self.args, 'max_tokens', 16000)
                if max_tokens:
                    # Pass llm as dict with model and max_tokens
                    agent_config["llm"] = {"model": self.args.llm, "max_tokens": max_tokens}
                    print(f"[bold cyan]Max tokens set to: {max_tokens}[/bold cyan]")
                else:
                    agent_config["llm"] = self.args.llm
            
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
                    agent_config["history_in_context"] = self.args.history
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
                
                # Router - Smart model selection (must be before agent creation)
                if getattr(self.args, 'router', False):
                    from .features.router import RouterHandler
                    router = RouterHandler(verbose=getattr(self.args, 'verbose', False))
                    provider = getattr(self.args, 'router_provider', None)
                    selected_model = router.select_model(prompt, provider)
                    agent_config["llm"] = selected_model
                
                # Metrics - Token/cost tracking
                if getattr(self.args, 'metrics', False):
                    agent_config["metrics"] = True
                    print("[bold cyan]Metrics enabled - will display token usage and costs[/bold cyan]")
                
                # Telemetry - Usage monitoring
                if getattr(self.args, 'telemetry', False):
                    from .features.telemetry import TelemetryHandler
                    telemetry = TelemetryHandler(verbose=getattr(self.args, 'verbose', False))
                    telemetry.enable()
                
                # Auto Memory - Automatic memory extraction
                if getattr(self.args, 'auto_memory', False):
                    agent_config["auto_memory"] = True
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
                    agents = handoff_handler.create_agents_with_handoff(
                        handoff_handler.parse_agent_names(self.args.handoff),
                        agent_config.get('llm')
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
            
            # Image processing - Use ImageAgent instead
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
            
            # Flow Display - Visual workflow tracking
            if hasattr(self, 'args') and getattr(self.args, 'flow_display', False):
                from .features.flow_display import FlowDisplayHandler
                flow = FlowDisplayHandler(verbose=getattr(self.args, 'verbose', False))
                flow.display_workflow_start("Direct Prompt", ["DirectAgent"])
            
            agent = PraisonAgent(**agent_config)
            result = agent.start(prompt)
            
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
                auto_mem.post_process_result(result, {'user_id': getattr(self.args, 'user_id', None)})
            
            # Todo - Generate todo list from response
            if hasattr(self, 'args') and getattr(self.args, 'todo', False):
                from .features.todo import TodoHandler
                todo = TodoHandler(verbose=getattr(self.args, 'verbose', False))
                todo.post_process_result(result, True)
            
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
