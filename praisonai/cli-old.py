# praisonai/cli.py

import sys
from version import __version__
import yaml, os
from rich import print
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
load_dotenv()
import autogen
import gradio as gr
import argparse

config_list = [
    {
        'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-3.5-turbo"),
        'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
    }
]

def generate_crew_and_kickoff(agent_file, framework=None):
    with open(agent_file, 'r') as f:
        config = yaml.safe_load(f)

    topic = config['topic']  
    framework = framework or config.get('framework')

    agents = {}
    tasks = []
    if framework == "autogen":
        # Load the LLM configuration dynamically
        print(config_list)
        llm_config = {"config_list": config_list}
        
        for role, details in config['roles'].items():
            agent_name = details['role'].format(topic=topic).replace("{topic}", topic)
            agent_goal = details['goal'].format(topic=topic)
            # Creating an AssistantAgent for each role dynamically
            agents[role] = autogen.AssistantAgent(
                name=agent_name,
                llm_config=llm_config,
                system_message=details['backstory'].format(topic=topic)+". Reply \"TERMINATE\" in the end when everything is done.",
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

def main(args=None):
    if args is None:
        args = parse_args()

    invocation_cmd = "praisonai"
    version_string = f"praisonAI version {__version__}"
    framework = args.framework  # Default framework
    ui = args.ui  # Default UI flag
    print(args)

    if args.agent_file:
        agent_file = args.agent_file
    else:
        agent_file = "agents.yaml"

    if ui:
        create_gradio_interface()
    else:
        result = generate_crew_and_kickoff(agent_file, framework)
        print(result)

def parse_args():
    parser = argparse.ArgumentParser(prog="praisonai", description="praisonAI command-line interface")
    parser.add_argument("--framework", choices=["crewai", "autogen"], default="crewai", help="Specify the framework")
    parser.add_argument("--ui", action="store_true", help="Enable UI mode")
    parser.add_argument("--auto", action="store_true", help="Enable auto mode")
    parser.add_argument("agent_file", nargs="?", help="Specify the agent file")

    return parser.parse_args()

def create_gradio_interface():
    def generate_crew_and_kickoff_interface(agent_file, framework):
        result = generate_crew_and_kickoff(agent_file, framework)
        return result

    gr.Interface(
        fn=generate_crew_and_kickoff_interface,
        inputs=["textbox", "radio"],
        outputs="textbox",
        title="Generate Crew and Kickoff",
        description="Generate a crew and kickoff the tasks",
        theme="default"
    ).launch()

if __name__ == "__main__":
    main()
