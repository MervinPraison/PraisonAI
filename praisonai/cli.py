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

    def generate_crew_and_kickoff(self):
        if self.agent_file == '/app/api:app' or self.agent_file == 'api:app':
            self.agent_file = 'agents.yaml'
        try:
            with open(self.agent_file, 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"File not found: {self.agent_file}")
            return

        topic = config['topic']  
        framework = self.framework or config.get('framework')

        agents = {}
        tasks = []
        if framework == "autogen":
            # Load the LLM configuration dynamically
            # print(self.config_list)
            llm_config = {"config_list": self.config_list}
            
            for role, details in config['roles'].items():
                agent_name = details['role'].format(topic=topic).replace("{topic}", topic)
                agent_goal = details['goal'].format(topic=topic)
                # Creating an AssistantAgent for each role dynamically
                agents[role] = autogen.AssistantAgent(
                    name=agent_name,
                    llm_config=llm_config,
                    system_message=details['backstory'].format(topic=topic)+". Must Reply \"TERMINATE\" in the end when everything is done.",
                )

                # Preparing tasks for initiate_chats
                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = task_details['description'].format(topic=topic)
                    expected_output_filled = task_details['expected_output'].format(topic=topic)
                    
                    chat_task = {
                        "recipient": agents[role],
                        "message": description_filled,
                        "summary_method": "last_msg", 
                        # Additional fields like carryover can be added based on dependencies
                    }
                    tasks.append(chat_task)

            # Assuming the user proxy agent is set up as per your requirements
            user = autogen.UserProxyAgent(
                name="User",
                human_input_mode="NEVER",
                is_termination_msg=lambda x: (x.get("content") or "").rstrip().rstrip(".").lower().endswith("terminate") or "TERMINATE" in (x.get("content") or ""),
                code_execution_config={
                    "work_dir": "coding",
                    "use_docker": False,
                },
                # additional setup for the user proxy agent
            )
            response = user.initiate_chats(tasks)
            result = "### Output ###\n"+response[-1].summary if hasattr(response[-1], 'summary') else ""
        else:
            for role, details in config['roles'].items():
                role_filled = details['role'].format(topic=topic)
                goal_filled = details['goal'].format(topic=topic)
                backstory_filled = details['backstory'].format(topic=topic)
                
                # Assume tools are loaded and handled here as per your requirements
                agent = Agent(role=role_filled, goal=goal_filled, backstory=backstory_filled, allow_delegation=False)
                agents[role] = agent

                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = task_details['description'].format(topic=topic)
                    expected_output_filled = task_details['expected_output'].format(topic=topic)

                    task = Task(description=description_filled, expected_output=expected_output_filled, agent=agent)
                    tasks.append(task)

            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=2
            )

            response = crew.kickoff()
            result = f"### Output ###\n{response}"
        return result

    def main(self):
        args = self.parse_args()
        if args is None:
            result = self.generate_crew_and_kickoff()
            return result
        if args.deploy:
            from .deploy import CloudDeployer
            deployer = CloudDeployer()
            deployer.run_commands()
            return
        invocation_cmd = "praisonai"
        version_string = f"praisonAI version {__version__}"
        
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
            self.filename = full_path
        
        if args.auto or args.init:
            temp_topic = ' '.join(args.auto) if args.auto else ' '.join(args.init)
            self.topic = temp_topic
        elif self.auto or self.init:  # Use the auto attribute if args.auto is not provided
            self.topic = self.auto
            
        if args.auto or self.auto:
            self.filename = "test.yaml"
            generator = AutoGenerator(topic=self.topic , framework=self.framework)
            self.agent_file = generator.generate()
            result = self.generate_crew_and_kickoff()
            return result
        elif args.init or self.init:
            self.filename = "agents.yaml"
            generator = AutoGenerator(topic=self.topic , framework=self.framework, filename=self.filename)
            self.agent_file = generator.generate()
            print("File {} created successfully".format(self.agent_file))
            return "File {} created successfully".format(self.agent_file)
        
        if ui:
            self.create_gradio_interface()
        else:
            result = self.generate_crew_and_kickoff()
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
            result = self.generate_crew_and_kickoff()
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