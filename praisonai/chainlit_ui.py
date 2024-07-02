# praisonai/chainlit_ui.py
from praisonai.agents_generator import AgentsGenerator 
from praisonai.auto import AutoGenerator 
import chainlit as cl
import os
from chainlit.types import ThreadDict
from chainlit.input_widget import Select, TextInput
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
from contextlib import redirect_stdout
from io import StringIO
import logging
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO').upper(), format='%(asctime)s - %(levelname)s - %(message)s')

framework = "crewai"
config_list = [
            {
                'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
                'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
                'api_key': os.environ.get("OPENAI_API_KEY", "")
            }
        ]
agent_file = "test.yaml"

actions=[
    cl.Action(name="run", value="run", label="✅ Run"),
    cl.Action(name="modify", value="modify", label="🔧 Modify"),
]

@cl.action_callback("run")
async def on_run(action):
    await main(cl.Message(content=""))

@cl.action_callback("modify")
async def on_modify(action):
    await cl.Message(content="Modify the agents and tools from below settings").send()
    

@cl.set_chat_profiles
async def set_profiles(current_user: cl.User):
    return [
        cl.ChatProfile(
            name="Auto",
            markdown_description="Automatically generate agents and tasks based on your input.",
            starters=[
                cl.Starter(
                    label="Create a movie script",
                    message="Create a movie script about a futuristic society where AI and humans coexist, focusing on the conflict and resolution between them. Start with an intriguing opening scene.",
                    icon="/public/movie.svg",
                ),
                cl.Starter(
                    label="Design a fantasy world",
                    message="Design a detailed fantasy world with unique geography, cultures, and magical systems. Start by describing the main continent and its inhabitants.",
                    icon="/public/fantasy.svg",
                ),
                cl.Starter(
                    label="Write a futuristic political thriller",
                    message="Write a futuristic political thriller involving a conspiracy within a global government. Start with a high-stakes meeting that sets the plot in motion.",
                    icon="/public/thriller.svg",
                ),
                cl.Starter(
                    label="Develop a new board game",
                    message="Develop a new, innovative board game. Describe the game's objective, rules, and unique mechanics. Create a scenario to illustrate gameplay.",
                    icon="/public/game.svg",
                ),
            ]
        ),
        cl.ChatProfile(
            name="Manual",
            markdown_description="Manually define your agents and tasks using a YAML file.",
        ),
    ]


@cl.on_chat_start
async def start_chat():
    cl.user_session.set(
        "message_history",
        [{"role": "system", "content": "You are a helpful assistant."}],
    )
    
    # Create tools.py if it doesn't exist
    if not os.path.exists("tools.py"):
        with open("tools.py", "w") as f:
            f.write("# Add your custom tools here\n")
    
    settings = await cl.ChatSettings(
        [
            TextInput(id="Model", label="OpenAI - Model", initial=config_list[0]['model']),
            TextInput(id="BaseUrl", label="OpenAI - Base URL", initial=config_list[0]['base_url']),
            TextInput(id="ApiKey", label="OpenAI - API Key", initial=config_list[0]['api_key']), 
            Select(
                id="Framework",
                label="Framework",
                values=["crewai", "autogen"],
                initial_index=0,
            ),
        ]
    ).send()
    cl.user_session.set("settings", settings)
    chat_profile = cl.user_session.get("chat_profile")
    if chat_profile=="Manual":
        
        agent_file = "agents.yaml"
        full_agent_file_path = os.path.abspath(agent_file)  # Get full path
        if os.path.exists(full_agent_file_path):
            with open(full_agent_file_path, 'r') as f:
                yaml_content = f.read()
            msg = cl.Message(content=yaml_content, language="yaml")
            await msg.send()
            
                
        full_tools_file_path = os.path.abspath("tools.py")  # Get full path
        if os.path.exists(full_tools_file_path):
            with open(full_tools_file_path, 'r') as f:
                tools_content = f.read()
            msg = cl.Message(content=tools_content, language="python")
            await msg.send()

        settings = await cl.ChatSettings(
            [
                TextInput(id="Model", label="OpenAI - Model", initial=config_list[0]['model']),
                TextInput(id="BaseUrl", label="OpenAI - Base URL", initial=config_list[0]['base_url']),
                TextInput(id="ApiKey", label="OpenAI - API Key", initial=config_list[0]['api_key']), 
                Select(
                    id="Framework",
                    label="Framework",
                    values=["crewai", "autogen"],
                    initial_index=0,
                ),
                TextInput(id="agents", label="agents.yaml", initial=yaml_content, multiline=True),
                TextInput(id="tools", label="tools.py", initial=tools_content, multiline=True),
            ]
        ).send()
        cl.user_session.set("settings", settings)
        
        res = await cl.AskActionMessage(
            content="Pick an action!",
            actions=actions,
        ).send()
        if res and res.get("value") == "modify":
            await cl.Message(content="Modify the agents and tools from below settings", actions=actions).send()
        elif res and res.get("value") == "run":
            await main(cl.Message(content="", actions=actions))

    await on_settings_update(settings)
    
@cl.on_settings_update
async def on_settings_update(settings):
    """Handle updates to the ChatSettings form."""
    global config_list, framework
    config_list[0]['model'] = settings["Model"]
    config_list[0]['base_url'] = settings["BaseUrl"]
    config_list[0]['api_key'] = settings["ApiKey"]
    os.environ["OPENAI_API_KEY"] = config_list[0]['api_key']
    os.environ["OPENAI_MODEL_NAME"] = config_list[0]['model']
    os.environ["OPENAI_API_BASE"] = config_list[0]['base_url']
    framework = settings["Framework"]
    
    if "agents" in settings:
        with open("agents.yaml", "w") as f:
            f.write(settings["agents"])
    if "tools" in settings:
        with open("tools.py", "w") as f:
            f.write(settings["tools"])
    
    print("Settings updated")

@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    message_history = cl.user_session.get("message_history", [])
    root_messages = [m for m in thread["steps"] if m["parentId"] is None]
    for message in root_messages:
        if message["type"] == "user_message":
            message_history.append({"role": "user", "content": message["output"]})
        elif message["type"] == "ai_message":
            message_history.append({"role": "assistant", "content": message["content"]})
    cl.user_session.set("message_history", message_history)

# @cl.step(type="tool")
# async def tool(data: Optional[str] = None, language: Optional[str] = None):
#     return cl.Message(content=data, language=language)

@cl.step(type="tool", show_input=False)
async def run_agents(agent_file: str, framework: str):
    """Runs the agents and returns the result."""
    agents_generator = AgentsGenerator(agent_file, framework, config_list)
    current_step = cl.context.current_step
    print("Current Step:", current_step)

    stdout_buffer = StringIO()
    with redirect_stdout(stdout_buffer):
        result = agents_generator.generate_crew_and_kickoff()
        
    complete_output = stdout_buffer.getvalue()

    async with cl.Step(name="gpt4", type="llm", show_input=True) as step:
        step.input = ""
        
        for line in stdout_buffer.getvalue().splitlines():
            print(line)
            await step.stream_token(line)
            
        tool_res = await output(complete_output)

    yield result

@cl.step(type="tool", show_input=False, language="yaml")
async def output(output):
    return output

@cl.step(type="tool", show_input=False, language="yaml")
def agent(output):
    return(f"""
        Agent Step Completed!
        Output: {output}
    """)

@cl.step(type="tool", show_input=False, language="yaml")
def task(output):
    return(f"""
        Task Completed!
        Task: {output.description}
        Output: {output.raw_output}
        {output}
    """)

@cl.on_message
async def main(message: cl.Message):
    """Run PraisonAI with the provided message as the topic."""
    message_history = cl.user_session.get("message_history")
    if message_history is None:
        message_history = []
        cl.user_session.set("message_history", message_history)
    message_history.append({"role": "user", "content": message.content})
    topic = message.content
    chat_profile = cl.user_session.get("chat_profile")

    if chat_profile == "Auto":
        agent_file = "agents.yaml"
        generator = AutoGenerator(topic=topic, agent_file=agent_file, framework=framework, config_list=config_list)
        await cl.sleep(2)
        agent_file = generator.generate()
        agents_generator = AgentsGenerator(
            agent_file, 
            framework, 
            config_list, 
            # agent_callback=agent,
            # task_callback=task
        )
        # Capture stdout
        stdout_buffer = StringIO()
        with redirect_stdout(stdout_buffer):
            result = agents_generator.generate_crew_and_kickoff()
            
        complete_output = stdout_buffer.getvalue()
        tool_res = await output(complete_output)
        msg = cl.Message(content=result)
        await msg.send()
        message_history.append({"role": "assistant", "content": message.content})
    else:  # chat_profile == "Manual"
        agent_file = "agents.yaml"
        full_agent_file_path = os.path.abspath(agent_file)  # Get full path
        full_tools_file_path = os.path.abspath("tools.py")  
        if os.path.exists(full_agent_file_path):
            with open(full_agent_file_path, 'r') as f:
                yaml_content = f.read()
            # tool_res = await tool()
            msg_agents = cl.Message(content=yaml_content, language="yaml")
            await msg_agents.send()
            if os.path.exists(full_tools_file_path):
                with open(full_tools_file_path, 'r') as f:
                    tools_content = f.read()
                msg_tools = cl.Message(content=tools_content, language="python")
                await msg_tools.send()
        else:
            # If the file doesn't exist, follow the same process as "Auto"
            generator = AutoGenerator(topic=topic, agent_file=agent_file, framework=framework, config_list=config_list)
            agent_file = generator.generate()

        agents_generator = AgentsGenerator(agent_file, framework, config_list)
        result = agents_generator.generate_crew_and_kickoff()
        msg = cl.Message(content=result, actions=actions)
        await msg.send()
        message_history.append({"role": "assistant", "content": message.content})

# Load environment variables from .env file
load_dotenv()

# Get username and password from environment variables
username = os.getenv("CHAINLIT_USERNAME", "admin")  # Default to "admin" if not found
password = os.getenv("CHAINLIT_PASSWORD", "admin")  # Default to "admin" if not found

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # Fetch the user matching username from your database
    # and compare the hashed password with the value stored in the database
    if (username, password) == (username, password):
        return cl.User(
            identifier=username, metadata={"role": "ADMIN", "provider": "credentials"}
        )
    else:
        return None
