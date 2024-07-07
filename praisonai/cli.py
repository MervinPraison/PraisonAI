# praisonai/cli.py

import sys
from .version import __version__
import yaml, os
from rich import print
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
load_dotenv()
import autogen
import argparse
from .auto import AutoGenerator
from .agents_generator import AgentsGenerator
from .inbuilt_tools import *
import shutil
import logging
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO'), format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from chainlit.cli import chainlit_run
    CHAINLIT_AVAILABLE = True
except ImportError:
    CHAINLIT_AVAILABLE = False

try:
    import gradio as gr
    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False

class PraisonAI:
    def __init__(self, agent_file="agents.yaml", framework="", auto=False, init=False, agent_yaml=None):
        """
        Initialize the PraisonAI object with default parameters.

        Parameters:
            agent_file (str): The default agent file to use. Defaults to "agents.yaml".
            framework (str): The default framework to use. Defaults to "crewai".
            auto (bool): A flag indicating whether to enable auto mode. Defaults to False.
            init (bool): A flag indicating whether to enable initialization mode. Defaults to False.

        Attributes:
            config_list (list): A list of configuration dictionaries for the OpenAI API.
            agent_file (str): The agent file to use.
            framework (str): The framework to use.
            auto (bool): A flag indicating whether to enable auto mode.
            init (bool): A flag indicating whether to enable initialization mode.
            agent_yaml (str, optional): The content of the YAML file. Defaults to None.
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

    def main(self):
        """
        The main function of the PraisonAI object. It parses the command-line arguments,
        initializes the necessary attributes, and then calls the appropriate methods based on the
        provided arguments.

        Args:
            self (PraisonAI): An instance of the PraisonAI class.
    
        Returns:
            Any: Depending on the arguments provided, the function may return a result from the
            AgentsGenerator, a deployment result from the CloudDeployer, or a message indicating
            the successful creation of a file.
        """
        args = self.parse_args()
        if args is None:
            agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list)
            result = agents_generator.generate_crew_and_kickoff()
            return result
        if args.deploy:
            from .deploy import CloudDeployer
            deployer = CloudDeployer()
            deployer.run_commands()
            return
        
        if getattr(args, 'chat', False):
            self.create_chainlit_chat_interface()
            return
        
        invocation_cmd = "praisonai"
        version_string = f"PraisonAI version {__version__}"
        
        self.framework = args.framework or self.framework 
        
        if args.agent_file:
            if args.agent_file.startswith("tests.test"): # Argument used for testing purposes. eg: python -m unittest tests.test 
                print("test")
            else:
                self.agent_file = args.agent_file
        
        
        if args.auto or args.init:
            temp_topic = ' '.join(args.auto) if args.auto else ' '.join(args.init)
            self.topic = temp_topic
        elif self.auto or self.init:  # Use the auto attribute if args.auto is not provided
            self.topic = self.auto
            
        if args.auto or self.auto:
            self.agent_file = "test.yaml"
            generator = AutoGenerator(topic=self.topic , framework=self.framework, agent_file=self.agent_file)
            self.agent_file = generator.generate()
            agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list)
            result = agents_generator.generate_crew_and_kickoff()
            return result
        elif args.init or self.init:
            self.agent_file = "agents.yaml"
            generator = AutoGenerator(topic=self.topic , framework=self.framework, agent_file=self.agent_file)
            self.agent_file = generator.generate()
            print("File {} created successfully".format(self.agent_file))
            return "File {} created successfully".format(self.agent_file)
        
        if args.ui:
            if args.ui == "gradio":
                self.create_gradio_interface()
            elif args.ui == "chainlit":
                self.create_chainlit_interface()
            else:
                # Modify below code to allow default ui
                agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list, agent_yaml=self.agent_yaml)
                result = agents_generator.generate_crew_and_kickoff()
                return result
        else:
            agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list, agent_yaml=self.agent_yaml)
            result = agents_generator.generate_crew_and_kickoff()
            return result
            
    def parse_args(self):
        """
        Parse the command-line arguments for the PraisonAI CLI.

        Args:
            self (PraisonAI): An instance of the PraisonAI class.

        Returns:
            argparse.Namespace: An object containing the parsed command-line arguments.

        Raises:
            argparse.ArgumentError: If the arguments provided are invalid.

        Example:
            >>> args = praison_ai.parse_args()
            >>> print(args.agent_file)  # Output: 'agents.yaml'
        """
        parser = argparse.ArgumentParser(prog="praisonai", description="praisonAI command-line interface")
        parser.add_argument("--framework", choices=["crewai", "autogen"], help="Specify the framework")
        parser.add_argument("--ui", choices=["chainlit", "gradio"], help="Specify the UI framework (gradio or chainlit).")
        parser.add_argument("--auto", nargs=argparse.REMAINDER, help="Enable auto mode and pass arguments for it")
        parser.add_argument("--init", nargs=argparse.REMAINDER, help="Enable auto mode and pass arguments for it")
        parser.add_argument("agent_file", nargs="?", help="Specify the agent file")
        parser.add_argument("--deploy", action="store_true", help="Deploy the application")  # New argument
        args, unknown_args = parser.parse_known_args()

        if unknown_args and unknown_args[0] == '-b' and unknown_args[1] == 'api:app':
            args.agent_file = 'agents.yaml'
        if args.agent_file == 'api:app' or args.agent_file == '/app/api:app':
            args.agent_file = 'agents.yaml'
        if args.agent_file == 'ui':
            args.ui = 'chainlit'
        if args.agent_file == 'chat':
            args.ui = 'chainlit'
            args.chat = True

        return args
    
    def create_chainlit_chat_interface(self):
        """
        Create a Chainlit interface for the chat application.

        This function sets up a Chainlit application that listens for messages.
        When a message is received, it runs PraisonAI with the provided message as the topic.
        The generated agents are then used to perform tasks.

        Returns:
            None: This function does not return any value. It starts the Chainlit application.
        """
        if CHAINLIT_AVAILABLE:
            import praisonai
            os.environ["CHAINLIT_PORT"] = "8084"
            chat_ui_path = os.path.join(os.path.dirname(praisonai.__file__), 'ui', 'chat.py')
            chainlit_run([chat_ui_path])
        else:
            print("ERROR: Chat UI is not installed. Please install it with 'pip install \"praisonai\[chat]\"' to use the chat UI.")

    def create_gradio_interface(self):
        """
        Create a Gradio interface for generating agents and performing tasks.

        Args:
            self (PraisonAI): An instance of the PraisonAI class.

        Returns:
            None: This method does not return any value. It launches the Gradio interface.

        Raises:
            None: This method does not raise any exceptions.

        Example:
            >>> praison_ai.create_gradio_interface()
        """
        if GRADIO_AVAILABLE:
            def generate_crew_and_kickoff_interface(auto_args, framework):
                """
                Generate a crew and kick off tasks based on the provided auto arguments and framework.

                Args:
                    auto_args (list): Topic.
                    framework (str): The framework to use for generating agents.

                Returns:
                    str: A string representing the result of generating the crew and kicking off tasks.

                Raises:
                    None: This method does not raise any exceptions.

                Example:
                    >>> result = generate_crew_and_kickoff_interface("Create a movie about Cat in Mars", "crewai")
                    >>> print(result)
                """
                self.framework = framework
                self.agent_file = "test.yaml"
                generator = AutoGenerator(topic=auto_args , framework=self.framework)
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

        This function sets up a Chainlit application that listens for messages.
        When a message is received, it runs PraisonAI with the provided message as the topic.
        The generated agents are then used to perform tasks.

        Returns:
            None: This function does not return any value. It starts the Chainlit application.
        """
        if CHAINLIT_AVAILABLE:
            import praisonai
            os.environ["CHAINLIT_PORT"] = "8082"
            # Get the path to the 'public' folder within the package
            public_folder = os.path.join(os.path.dirname(praisonai.__file__), 'public')
            if not os.path.exists("public"):  # Check if the folder exists in the current directory
                if os.path.exists(public_folder):
                    shutil.copytree(public_folder, 'public', dirs_exist_ok=True)
                    logging.info("Public folder copied successfully!")
                else:
                    logging.info("Public folder not found in the package.")
            else:
                logging.info("Public folder already exists.")
            chainlit_ui_path = os.path.join(os.path.dirname(praisonai.__file__), 'chainlit_ui.py')
            chainlit_run([chainlit_ui_path])
        else:
            print("ERROR: Chainlit is not installed. Please install it with 'pip install \"praisonai\[ui]\"' to use the UI.")        

if __name__ == "__main__":
    praison_ai = PraisonAI()
    praison_ai.main()