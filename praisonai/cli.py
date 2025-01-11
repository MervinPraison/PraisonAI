# praisonai/cli.py

import sys
import argparse
from .version import __version__
import yaml
import os
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

try:
    # Create necessary directories and set CHAINLIT_APP_ROOT
    if "CHAINLIT_APP_ROOT" not in os.environ:
        chainlit_root = os.path.join(os.path.expanduser("~"), ".praison")
        os.environ["CHAINLIT_APP_ROOT"] = chainlit_root
    else:
        chainlit_root = os.environ["CHAINLIT_APP_ROOT"]
        
    os.makedirs(chainlit_root, exist_ok=True)
    os.makedirs(os.path.join(chainlit_root, ".files"), exist_ok=True)
    
    from chainlit.cli import chainlit_run
    CHAINLIT_AVAILABLE = True
except ImportError:
    pass

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
    from crewai import Agent, Task, Crew
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
        self.config_list = [
            {
                'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
                'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
                'api_key': os.environ.get("OPENAI_API_KEY")
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
        self.main()

    def main(self):
        """
        The main function of the PraisonAI object. It parses the command-line arguments,
        initializes the necessary attributes, and then calls the appropriate methods based on the
        provided arguments.
        """
        args = self.parse_args()
        invocation_cmd = "praisonai"
        version_string = f"PraisonAI version {__version__}"

        self.framework = args.framework or self.framework

        if args.command:
            if args.command.startswith("tests.test"):  # Argument used for testing purposes
                print("test")
            else:
                self.agent_file = args.command

        if args.deploy:
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
            package_root = os.path.dirname(os.path.abspath(__file__))
            config_yaml_destination = os.path.join(os.getcwd(), 'config.yaml')

            # Create config.yaml only if it doesn't exist or --model or --dataset is provided
            if not os.path.exists(config_yaml_destination) or args.model or args.dataset:
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

            try:
                result = subprocess.check_output(['conda', 'env', 'list'])
                if 'praison_env' in result.decode('utf-8'):
                    print("Conda environment 'praison_env' found.")
                else:
                    raise subprocess.CalledProcessError(1, 'grep')
            except subprocess.CalledProcessError:
                print("Conda environment 'praison_env' not found. Setting it up...")
                from praisonai.setup.setup_conda_env import main as setup_conda_main
                setup_conda_main()
                print("All packages installed.")

            train_args = sys.argv[2:]  # Get all arguments after 'train'
            train_script_path = os.path.join(package_root, 'train.py')

            # Set environment variables
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'

            stream_subprocess(['conda', 'run', '--no-capture-output', '--name', 'praison_env', 'python', '-u', train_script_path, 'train'], env=env)
            return

        if args.auto or self.auto:
            temp_topic = args.auto if args.auto else self.auto
            if isinstance(temp_topic, list):
                temp_topic = ' '.join(temp_topic)
            self.topic = temp_topic

            self.agent_file = "test.yaml"
            generator = AutoGenerator(topic=self.topic, framework=self.framework, agent_file=self.agent_file)
            self.agent_file = generator.generate()
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
            self.agent_file = generator.generate()
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
        parser = argparse.ArgumentParser(prog="praisonai", description="praisonAI command-line interface")
        parser.add_argument("--framework", choices=["crewai", "autogen", "praisonai"], help="Specify the framework")
        parser.add_argument("--ui", choices=["chainlit", "gradio"], help="Specify the UI framework (gradio or chainlit).")
        parser.add_argument("--auto", nargs=argparse.REMAINDER, help="Enable auto mode and pass arguments for it")
        parser.add_argument("--init", nargs=argparse.REMAINDER, help="Initialize agents with optional topic")
        parser.add_argument("command", nargs="?", help="Command to run")
        parser.add_argument("--deploy", action="store_true", help="Deploy the application")
        parser.add_argument("--model", type=str, help="Model name")
        parser.add_argument("--hf", type=str, help="Hugging Face model name")
        parser.add_argument("--ollama", type=str, help="Ollama model name")
        parser.add_argument("--dataset", type=str, help="Dataset name for training", default="yahma/alpaca-cleaned")
        parser.add_argument("--realtime", action="store_true", help="Start the realtime voice interaction interface")
        parser.add_argument("--call", action="store_true", help="Start the PraisonAI Call server")
        parser.add_argument("--public", action="store_true", help="Use ngrok to expose the server publicly (only with --call)")
        args, unknown_args = parser.parse_known_args()

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

        # Handle special commands first
        special_commands = ['chat', 'code', 'call', 'realtime', 'train', 'ui']

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
                print("[red]ERROR: Train feature is not installed. Install with:[/red]")
                print("\npip install \"praisonai[train]\"\n")
                sys.exit(1)

            elif args.command == 'ui':
                if not CHAINLIT_AVAILABLE:
                    print("[red]ERROR: UI is not installed. Install with:[/red]")
                    print("\npip install \"praisonai[ui]\"\n")
                    sys.exit(1)
                self.create_chainlit_interface()
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

        return args

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
            chainlit_run([chat_ui_path])
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
            chainlit_run([code_ui_path])
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
            chainlit_run([chainlit_ui_path])
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
            chainlit_run([realtime_ui_path])
        else:
            print("ERROR: Realtime UI is not installed. Please install it with 'pip install \"praisonai[realtime]\"' to use the realtime UI.")

if __name__ == "__main__":
    praison_ai = PraisonAI()
    praison_ai.main()
