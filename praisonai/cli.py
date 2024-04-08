# praisonai/cli.py

import sys
from .version import __version__
import yaml, os
from rich import print
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
load_dotenv()
import autogen
import gradio as gr
import argparse
from .auto import AutoGenerator
from .agents_generator import AgentsGenerator
from crewai_tools import *
from .main_tools import *

class PraisonAI:
    def __init__(self, agent_file="agents.yaml", framework="crewai", auto=False, init=False):
        self.config_list = [
            {
                'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-4-turbo-preview"),
                'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
            }
        ]
        self.agent_file = agent_file
        self.framework = framework
        self.auto = auto
        self.init = init

    def main(self):
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
        invocation_cmd = "praisonai"
        version_string = f"PraisonAI version {__version__}"
        
        if args.framework:
            self.framework = args.framework
        
        ui = args.ui

        if args.agent_file:
            if args.agent_file == "tests.test": # Argument used for testing purposes
                full_path = os.path.abspath("agents.yaml")
            else:
                full_path = os.path.abspath(args.agent_file)
            self.agent_file = full_path
        else:
            full_path = os.path.abspath(self.agent_file)
            self.agent_file = full_path
        
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
        
        if ui:
            self.create_gradio_interface()
        else:
            agents_generator = AgentsGenerator(self.agent_file, self.framework, self.config_list)
            result = agents_generator.generate_crew_and_kickoff()
            return result
            
    def parse_args(self):
        parser = argparse.ArgumentParser(prog="praisonai", description="praisonAI command-line interface")
        parser.add_argument("--framework", choices=["crewai", "autogen"], default="crewai", help="Specify the framework")
        parser.add_argument("--ui", action="store_true", help="Enable UI mode")
        parser.add_argument("--auto", nargs=argparse.REMAINDER, help="Enable auto mode and pass arguments for it")
        parser.add_argument("--init", nargs=argparse.REMAINDER, help="Enable auto mode and pass arguments for it")
        parser.add_argument("agent_file", nargs="?", help="Specify the agent file")
        parser.add_argument("--deploy", action="store_true", help="Deploy the application")  # New argument

        args, unknown_args = parser.parse_known_args()

        if unknown_args and unknown_args[0] == '-b' and unknown_args[1] == 'api:app':
            args.agent_file = 'agents.yaml'
        if args.agent_file == 'api:app' or args.agent_file == '/app/api:app':
            args.agent_file = 'agents.yaml'

        return args

    def create_gradio_interface(self):
        def generate_crew_and_kickoff_interface(auto_args, framework):
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

if __name__ == "__main__":
    praison_ai = PraisonAI()
    praison_ai.main()



## agents.yaml
# framework: autogen
# topic: create movie script about cat in mars
# roles:
#   concept_developer:
#     backstory: Experienced in creating captivating and original story concepts.
#     goal: Generate a unique concept for a movie script about a cat in Mars
#     role: Concept Developer
#     tools:
#     - search_tool
#     tasks:
#       concept_generation:
#         description: Develop a unique and engaging concept for a movie script about
#           a cat in Mars.
#         expected_output: A detailed concept document for the movie script.
#   scriptwriter:
#     backstory: Expert in dialogue and script structure, translating concepts into
#       scripts.
#     goal: Write a script based on the movie concept
#     role: Scriptwriter
#     tasks:
#       scriptwriting_task:
#         description: Turn the movie concept into a script, including dialogue and
#           scenes.
#         expected_output: A production-ready script for the movie about a cat in Mars.
#   director:
#     backstory: Experienced in visualizing scripts and creating compelling storyboards.
#     goal: Create a storyboard and visualize the script
#     role: Director
#     tasks:
#       storyboard_creation:
#         description: Create a storyboard for the movie script about a cat in Mars.
#         expected_output: A detailed storyboard for the movie about a cat in Mars.
# dependencies: []

