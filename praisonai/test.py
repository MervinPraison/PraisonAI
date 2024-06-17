import yaml
import os
from rich import print
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
load_dotenv()
import autogen
config_list = [
    {
        'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-3.5-turbo"),
        'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
        'api_key': os.environ.get("OPENAI_API_KEY")
    }
]

def generate_crew_and_kickoff(agent_file):
    """
    This function generates a crew of agents and kicks off tasks based on the configuration provided in a YAML file.

    Parameters:
    agent_file (str): The path to the YAML file containing the configuration for the agents and tasks.

    Returns:
    str: The result of the last task executed by the crew.
    """

    with open(agent_file, 'r') as f:
        config = yaml.safe_load(f)

    topic = config['topic']  
    framework = config['framework']

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
                    "summary_method": "last_msg",  # Customize as needed
                    # Additional fields like carryover can be added based on dependencies
                }
                tasks.append(chat_task)

        # Assuming the user proxy agent is set up as per your requirements
        user = autogen.UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: (x.get("content") or "").rstrip().endswith("TERMINATE"),
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
            agent = Agent(role=role_filled, goal=goal_filled, backstory=backstory_filled)
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

        result = crew.kickoff()
    return result

if __name__ == "__main__":
    agent_file = "agents.yaml"
    result = generate_crew_and_kickoff(agent_file)
    print(result)