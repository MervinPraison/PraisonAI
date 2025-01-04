# praisonai/chainlit_ui.py
from praisonai.agents_generator import AgentsGenerator 
from praisonai.auto import AutoGenerator 
import chainlit as cl
import os
from chainlit.types import ThreadDict
from chainlit.input_widget import Select, TextInput
from typing import Optional, Dict, Any, AsyncGenerator, List, Callable
from dotenv import load_dotenv
from datetime import datetime
import json
import asyncio
import logging
import chainlit.data as cl_data
from literalai.helper import utc_now
from io import StringIO
from contextlib import redirect_stdout, asynccontextmanager
from db import DatabaseManager
import time
import sqlite3
from openai import AsyncOpenAI
from functools import partial
import yaml

# Load environment variables
load_dotenv()

# Initialize database with retry logic
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

async def init_database_with_retry():
    for attempt in range(MAX_RETRIES):
        try:
            db_manager = DatabaseManager()
            db_manager.initialize()
            return db_manager
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            raise
        except Exception as e:
            raise

# Initialize database
db_manager = asyncio.run(init_database_with_retry())

# Logging configuration
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger.handlers = []
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)
logger.setLevel(log_level)

# Authentication secret setup
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")
if not CHAINLIT_AUTH_SECRET:
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"
    CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

async def save_setting_with_retry(key: str, value: str):
    """Save a setting to the database with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            await db_manager.save_setting(key, value)
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            raise
        except Exception as e:
            raise

async def load_setting_with_retry(key: str) -> str:
    """Load a setting from the database with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            return await db_manager.load_setting(key)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            raise
        except Exception as e:
            raise

def save_setting(key: str, value: str):
    """Save a setting to the database"""
    asyncio.run(save_setting_with_retry(key, value))

def load_setting(key: str) -> str:
    """Load a setting from the database"""
    return asyncio.run(load_setting_with_retry(key))

cl_data._data_layer = db_manager

# Authentication configuration
AUTH_PASSWORD_ENABLED = os.getenv("AUTH_PASSWORD_ENABLED", "true").lower() == "true"
AUTH_OAUTH_ENABLED = os.getenv("AUTH_OAUTH_ENABLED", "false").lower() == "true"

username = os.getenv("CHAINLIT_USERNAME", "admin")
password = os.getenv("CHAINLIT_PASSWORD", "admin")

def auth_callback(u: str, p: str):
    if (u, p) == (username, password):
        return cl.User(identifier=username, metadata={"role": "ADMIN", "provider": "credentials"})
    return None

def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: Dict[str, str],
    default_user: cl.User,
) -> Optional[cl.User]:
    return default_user

if AUTH_PASSWORD_ENABLED:
    auth_callback = cl.password_auth_callback(auth_callback)

if AUTH_OAUTH_ENABLED:
    oauth_callback = cl.oauth_callback(oauth_callback)

framework = "praisonai"
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
    try:
        # Load model name from database
        model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
        cl.user_session.set("model_name", model_name)
        logger.debug(f"Model name: {model_name}")

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
                TextInput(id="Model", label="OpenAI - Model", initial=model_name),
                TextInput(id="BaseUrl", label="OpenAI - Base URL", initial=config_list[0]['base_url']),
                TextInput(id="ApiKey", label="OpenAI - API Key", initial=config_list[0]['api_key']), 
                Select(
                    id="Framework",
                    label="Framework",
                    values=["praisonai", "crewai", "autogen"],
                    initial_index=0,
                ),
            ]
        ).send()
        cl.user_session.set("settings", settings)
        chat_profile = cl.user_session.get("chat_profile")

        if chat_profile=="Manual":
            agent_file = "agents.yaml"
            full_agent_file_path = os.path.abspath(agent_file)
            if os.path.exists(full_agent_file_path):
                with open(full_agent_file_path, 'r') as f:
                    yaml_content = f.read()
                msg = cl.Message(content=yaml_content, language="yaml")
                await msg.send()
                
            full_tools_file_path = os.path.abspath("tools.py")
            if os.path.exists(full_tools_file_path):
                with open(full_tools_file_path, 'r') as f:
                    tools_content = f.read()
                msg = cl.Message(content=tools_content, language="python")
                await msg.send()

            settings = await cl.ChatSettings(
                [
                    TextInput(id="Model", label="OpenAI - Model", initial=model_name),
                    TextInput(id="BaseUrl", label="OpenAI - Base URL", initial=config_list[0]['base_url']),
                    TextInput(id="ApiKey", label="OpenAI - API Key", initial=config_list[0]['api_key']), 
                    Select(
                        id="Framework",
                        label="Framework",
                        values=["praisonai", "crewai", "autogen"],
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
    except Exception as e:
        logger.error(f"Error in start_chat: {str(e)}")
        await cl.Message(content=f"An error occurred while starting the chat: {str(e)}").send()

@cl.on_settings_update
async def on_settings_update(settings):
    """Handle updates to the ChatSettings form."""
    try:
        global config_list, framework
        config_list[0]['model'] = settings["Model"]
        config_list[0]['base_url'] = settings["BaseUrl"]
        config_list[0]['api_key'] = settings["ApiKey"]
        
        # Save settings to database with retry
        for attempt in range(MAX_RETRIES):
            try:
                await save_setting_with_retry("model_name", config_list[0]['model'])
                await save_setting_with_retry("base_url", config_list[0]['base_url'])
                await save_setting_with_retry("api_key", config_list[0]['api_key'])
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise
        
        # Save to environment variables for compatibility
        os.environ["OPENAI_API_KEY"] = config_list[0]['api_key']
        os.environ["OPENAI_MODEL_NAME"] = config_list[0]['model']
        os.environ["OPENAI_API_BASE"] = config_list[0]['base_url']
        os.environ["MODEL_NAME"] = config_list[0]['model']
        framework = settings["Framework"]
        os.environ["FRAMEWORK"] = framework
        
        if "agents" in settings:
            with open("agents.yaml", "w") as f:
                f.write(settings["agents"])
        if "tools" in settings:
            with open("tools.py", "w") as f:
                f.write(settings["tools"])
        
        # Update thread metadata if exists with retry
        thread_id = cl.user_session.get("thread_id")
        if thread_id:
            for attempt in range(MAX_RETRIES):
                try:
                    thread = await cl_data.get_thread(thread_id)
                    if thread:
                        metadata = thread.get("metadata", {})
                        if isinstance(metadata, str):
                            try:
                                metadata = json.loads(metadata)
                            except json.JSONDecodeError:
                                metadata = {}
                        metadata["model_name"] = config_list[0]['model']
                        await cl_data.update_thread(thread_id, metadata=metadata)
                        cl.user_session.set("metadata", metadata)
                    break
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    raise
        
        logger.info("Settings updated successfully")
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        await cl.Message(content=f"An error occurred while updating settings: {str(e)}. Retrying...").send()
        # One final retry after a longer delay
        try:
            await asyncio.sleep(RETRY_DELAY * 2)
            await on_settings_update(settings)
        except Exception as e:
            logger.error(f"Final retry failed: {str(e)}")
            await cl.Message(content=f"Failed to update settings after retries: {str(e)}").send()

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

# Add callback handler class
class ChainlitCallbackHandler:
    """Callback handler for streaming agent execution to Chainlit"""
    
    def __init__(self, parent_step: Optional[cl.Step] = None):
        self.parent_step = parent_step
        self.current_step = None
        self._steps = {}
    
    async def on_agent_start(self, agent_name: str):
        """Called when an agent starts execution"""
        self.current_step = cl.Step(
            name=f"Agent: {agent_name}",
            type="agent",
            show_input=True,
            parent_id=self.parent_step.id if self.parent_step else None
        )
        await self.current_step.start()
        await self.current_step.stream_token(f"🤖 Agent {agent_name} started\n")
        self._steps[agent_name] = self.current_step

    async def on_agent_action(self, agent_name: str, action: str):
        """Called when an agent performs an action"""
        step = self._steps.get(agent_name, self.current_step)
        if step:
            await step.stream_token(f"⚡ {action}\n")

    async def on_agent_finish(self, agent_name: str, output: Any):
        """Called when an agent finishes execution"""
        step = self._steps.get(agent_name)
        if step:
            await step.stream_token(f"\n✅ Agent {agent_name} finished\n")
            step.output = str(output)
            await step.end()
            self._steps.pop(agent_name, None)

    async def on_task_start(self, task_id: str, task_name: str):
        """Called when a task starts execution"""
        self.current_step = cl.Step(
            name=f"Task: {task_name}",
            type="task",
            show_input=True,
            parent_id=self.parent_step.id if self.parent_step else None
        )
        await self.current_step.start()
        await self.current_step.stream_token(f"📋 Starting task: {task_name}\n")
        self._steps[task_id] = self.current_step

    async def on_task_finish(self, task_id: str, output: Any):
        """Called when a task finishes execution"""
        step = self._steps.get(task_id, self.current_step)
        if step:
            await step.stream_token(f"\n✅ Task completed\n")
            step.output = str(output)
            await step.end()
            self._steps.pop(task_id, None)

    async def on_error(self, error: str):
        """Called when an error occurs"""
        if self.current_step:
            await self.current_step.stream_token(f"\n❌ Error: {error}\n")
            await self.current_step.end()

@cl.step(type="tool", show_input=False)
async def run_agents(agent_file: str, framework: str):
    """Runs the agents and returns the result."""
    try:
        logger.debug(f"Running agents with file: {agent_file}, framework: {framework}")
        
        # Create main execution step
        async with cl.Step(name="Agents Execution", type="agents") as agents_step:
            agents_step.input = f"Running agents from {agent_file}"
            
            # Initialize callback handler
            callback_handler = ChainlitCallbackHandler(parent_step=agents_step)
            
            try:
                # Load YAML config first
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
                
                # Execute based on framework
                if framework == "crewai":
                    result = agents_generator._run_crewai(config, topic, [])
                elif framework == "autogen":
                    result = agents_generator._run_autogen(config, topic, [])
                elif framework == "praisonai":
                    result = agents_generator._run_praisonai(config, topic, [])
                else:
                    raise ValueError(f"Unsupported framework: {framework}")
                
                # Process the result if it has tasks
                if hasattr(result, 'tasks') and result.tasks:
                    for task in result.tasks:
                        task_id = getattr(task, 'id', str(id(task)))
                        task_desc = getattr(task, 'description', 'Executing task...')
                        
                        # Signal task start
                        await callback_handler.on_task_start(
                            task_id,
                            task_desc[:50] + "..." if len(task_desc) > 50 else task_desc
                        )
                        
                        try:
                            # Handle agent actions if present
                            agent = getattr(task, 'agent', None)
                            if agent:
                                agent_name = getattr(agent, 'name', 'Unknown Agent')
                                await callback_handler.on_agent_start(agent_name)
                                await callback_handler.on_agent_action(
                                    agent_name,
                                    f"Working on task: {task_desc[:50]}..."
                                )
                            
                            # Get task output
                            task_output = getattr(task, 'output', str(task))
                            
                            # Signal agent completion if exists
                            if agent:
                                await callback_handler.on_agent_finish(agent_name, task_output)
                            
                            # Signal task completion
                            await callback_handler.on_task_finish(task_id, task_output)
                            
                        except Exception as e:
                            await callback_handler.on_error(f"Error in task {task_id}: {str(e)}")
                            raise
                
                # Return the final result
                agents_step.output = "Agents execution completed"
                return result if isinstance(result, str) else str(result)
                
            except Exception as e:
                await callback_handler.on_error(str(e))
                raise

    except Exception as e:
        error_msg = f"Error running agents: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

async def stream_agents_execution(agents) -> AsyncGenerator[tuple[str, str, str], None]:
    """
    Generator to stream agents execution status and messages.
    Yields tuples of (task_id, status, message)
    """
    try:
        for task_id in agents.tasks:
            task = agents.tasks[task_id]
            
            # Signal task start
            yield task_id, "start", ""
            
            if task.async_execution:
                # Execute async task
                result = await agents.aexecute_task(task_id)
            else:
                # Execute sync task in thread pool
                result = await cl.make_async(agents.execute_task)(task_id)
            
            if result:
                # Stream agent messages
                if isinstance(result, str):
                    yield task_id, "agent_message", result
                else:
                    yield task_id, "agent_message", result.raw
                
                # Signal completion
                yield task_id, "complete", ""
            else:
                yield task_id, "error", "Task execution failed"
                
    except Exception as e:
        logger.error(f"Error in stream_agents_execution: {e}")
        yield task_id, "error", str(e)

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

# Add retry decorator for database operations
def with_retries(max_retries=3, delay=1):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        await asyncio.sleep(delay)
                        continue
                    raise
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@with_retries(max_retries=3, delay=1)
async def update_thread_metadata(thread_id: str, metadata: dict):
    """Update thread metadata with retry logic"""
    await cl_data.update_thread(thread_id, metadata=metadata)

@cl.on_message
async def main(message: cl.Message):
    try:
        # Get settings and chat profile
        settings = cl.user_session.get("settings")
        chat_profile = cl.user_session.get("chat_profile")
        
        # Get message history or initialize if not exists
        message_history = cl.user_session.get("message_history", [])
        
        # Format user message with context
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_message = f"""
        Answer the question and use tools if needed:

        Current Date and Time: {now}

        User Question: {message.content}
        """
        
        # Add to message history
        message_history.append({"role": "user", "content": user_message})
        
        # Get configuration
        framework = settings["Framework"]
        topic = message.content

        if chat_profile == "Auto":
            agent_file = "agents.yaml"
            logger.info(f"Generating agents for topic: {topic}")
            generator = AutoGenerator(topic=topic, agent_file=agent_file, framework=framework, config_list=config_list)
            
            await cl.sleep(2)
            agent_file = generator.generate()
            
            # Run agents with streaming while preserving context
            result = await run_agents(agent_file, framework)
            await cl.Message(content=result).send()
            
        else:  # Manual mode
            agent_file = "agents.yaml"
            full_agent_file_path = os.path.abspath(agent_file)
            full_tools_file_path = os.path.abspath("tools.py")
            
            if os.path.exists(full_agent_file_path):
                with open(full_agent_file_path, 'r') as f:
                    yaml_content = f.read()
                msg_agents = cl.Message(content=yaml_content, language="yaml")
                await msg_agents.send()
                
                if os.path.exists(full_tools_file_path):
                    with open(full_tools_file_path, 'r') as f:
                        tools_content = f.read()
                    msg_tools = cl.Message(content=tools_content, language="python")
                    await msg_tools.send()
            
            # Run agents with streaming while preserving context
            result = await run_agents(agent_file, framework)
            await cl.Message(content=result, actions=actions).send()

        # Update message history
        message_history.append({"role": "assistant", "content": result})
        cl.user_session.set("message_history", message_history)
        
        # Update thread metadata with retry logic
        thread_id = cl.user_session.get("thread_id")
        if thread_id:
            metadata = {
                "last_response": result,
                "timestamp": now,
                "mode": chat_profile.lower()
            }
            await update_thread_metadata(thread_id, metadata)

    except Exception as e:
        error_msg = f"Error processing message: {str(e)}"
        logger.error(error_msg)
        await cl.Message(content=error_msg).send()

# Load environment variables from .env file
load_dotenv()

# Get username and password from environment variables
username = os.getenv("CHAINLIT_USERNAME", "admin")  # Default to "admin" if not found
password = os.getenv("CHAINLIT_PASSWORD", "admin")  # Default to "admin" if not found

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # Compare the username and password with environment variables
    if (username, password) == (username, password):
        return cl.User(
            identifier=username, metadata={"role": "ADMIN", "provider": "credentials"}
        )
    else:
        return None
