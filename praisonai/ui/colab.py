from praisonaiagents import Agent, Task, PraisonAIAgents
import os
import importlib
import inspect
import yaml
import logging

logger = logging.getLogger(__name__)

with open(agent_file, 'r') as f:
    config = yaml.safe_load(f)

# Get topic from message content
topic = cl.user_session.get("message_history", [{}])[-1].get("content", "")

# Create agents generator with loaded config
agents_generator = AgentsGenerator(
    agent_file=agent_file,
    framework=framework,
    config_list=config_list,
    agent_yaml=yaml.dump(config)  # Pass the loaded config as YAML string
)

def load_tools_from_tools_py():
    """
    Imports and returns all contents from tools.py file.
    Also adds the tools to the global namespace.

    Returns:
        list: A list of callable functions with proper formatting
    """
    tools_list = []
    try:
        # Try to import tools.py from current directory
        spec = importlib.util.spec_from_file_location("tools", "tools.py")
        logger.info(f"Spec: {spec}")
        if spec is None:
            logger.info("tools.py not found in current directory")
            return tools_list

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get all module attributes except private ones and classes
        for name, obj in inspect.getmembers(module):
            if (not name.startswith('_') and 
                callable(obj) and 
                not inspect.isclass(obj)):
                # Add the function to global namespace
                globals()[name] = obj
                # Add to tools list
                tools_list.append(obj)
                logger.info(f"Loaded and globalized tool function: {name}")

        logger.info(f"Loaded {len(tools_list)} tool functions from tools.py")
        logger.info(f"Tools list: {tools_list}")
        
    except Exception as e:
        logger.warning(f"Error loading tools from tools.py: {e}")
        
    return tools_list

def ui_run_praisonai(config, topic, tools_dict):
    """
    Run agents using the PraisonAI framework.
    """
    agents = {}
    tasks = []
    tasks_dict = {}

    # Load tools once at the beginning
    tools_list = load_tools_from_tools_py()

    # Create agents from config
    for role, details in config['roles'].items():
        role_filled = details['role'].format(topic=topic)
        goal_filled = details['goal'].format(topic=topic)
        backstory_filled = details['backstory'].format(topic=topic)
        
        # Pass all loaded tools to the agent
        agent = Agent(
            name=role_filled,
            role=role_filled,
            goal=goal_filled,
            backstory=backstory_filled,
            tools=tools_list,  # Pass the entire tools list to the agent
            allow_delegation=details.get('allow_delegation', False),
            llm=details.get('llm', {}).get("model", os.environ.get("MODEL_NAME", "gpt-4o")),
            function_calling_llm=details.get('function_calling_llm', {}).get("model", os.environ.get("MODEL_NAME", "gpt-4o")),
            max_iter=details.get('max_iter', 15),
            max_rpm=details.get('max_rpm'),
            max_execution_time=details.get('max_execution_time'),
            verbose=details.get('verbose', True),
            cache=details.get('cache', True),
            system_template=details.get('system_template'),
            prompt_template=details.get('prompt_template'),
            response_template=details.get('response_template'),
            reflect_llm=details.get('reflect_llm', {}).get("model", os.environ.get("MODEL_NAME", "gpt-4o")),
            min_reflect=details.get('min_reflect', 1),
            max_reflect=details.get('max_reflect', 3),
        )

        agents[role] = agent

        # Create tasks for the agent
        for task_name, task_details in details.get('tasks', {}).items():
            description_filled = task_details['description'].format(topic=topic)
            expected_output_filled = task_details['expected_output'].format(topic=topic)

            task = Task(
                description=description_filled,
                expected_output=expected_output_filled,
                agent=agent,
                tools=tools_list,  # Pass the same tools list to the task
                async_execution=task_details.get('async_execution', False),
                context=[],
                config=task_details.get('config', {}),
                output_json=task_details.get('output_json'),
                output_pydantic=task_details.get('output_pydantic'),
                output_file=task_details.get('output_file', ""),
                callback=task_details.get('callback'),
                create_directory=task_details.get('create_directory', False)
            )

            tasks.append(task)
            tasks_dict[task_name] = task

    # Set up task contexts
    for role, details in config['roles'].items():
        for task_name, task_details in details.get('tasks', {}).items():
            task = tasks_dict[task_name]
            context_tasks = [tasks_dict[ctx] for ctx in task_details.get('context', []) 
                        if ctx in tasks_dict]
            task.context = context_tasks

    # Create and run the PraisonAI agents
    if config.get('process') == 'hierarchical':
        agents = PraisonAIAgents(
            agents=list(agents.values()),
            tasks=tasks,
            verbose=True,
            process="hierarchical",
            manager_llm=config.get('manager_llm', 'gpt-4o'),
        )
    else:
        agents = PraisonAIAgents(
            agents=list(agents.values()),
            tasks=tasks,
            verbose=2
        )

    logger.debug("Final Configuration:")
    logger.debug(f"Agents: {agents.agents}")
    logger.debug(f"Tasks: {agents.tasks}")

    response = agents.start()
    logger.debug(f"Result: {response}")
    result = ""
        
    return result