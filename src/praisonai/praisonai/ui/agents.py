from chainlit.input_widget import Select, TextInput
import os
import sys
import yaml
import logging
import inspect
import chainlit as cl
from praisonaiagents import Agent, Task, PraisonAIAgents, register_display_callback

framework = "praisonai"
config_list = [
    {
        'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
        'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
        'api_key': os.environ.get("OPENAI_API_KEY", "")
    }
]

actions = [
    cl.Action(name="run", payload="run", label="✅ Run"),
    cl.Action(name="modify", payload="modify", label="🔧 Modify"),
]

@cl.action_callback("run")
async def on_run(action):
    await main(cl.Message(content=""))

@cl.action_callback("modify")
async def on_modify(action):
    await cl.Message(content="Modify the agents and tools from below settings").send()

import os
import sys
import yaml
import logging
import inspect
import asyncio
import importlib.util
import sqlite3
from queue import Queue
from datetime import datetime
from dotenv import load_dotenv

# Chainlit imports
import chainlit as cl
from chainlit.types import ThreadDict
import chainlit.data as cl_data

# -----------------------------------------------------------------------------
# Global Setup
# -----------------------------------------------------------------------------

load_dotenv()
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

message_queue = Queue()  # Queue to handle messages sent to Chainlit UI
agent_file = "agents.yaml"

# -----------------------------------------------------------------------------
# Database and Settings Logic
# -----------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

from db import DatabaseManager

async def init_database_with_retry():
    db = DatabaseManager()
    for attempt in range(MAX_RETRIES):
        try:
            db.initialize()
            return db
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            raise

db_manager = asyncio.run(init_database_with_retry())
cl_data._data_layer = db_manager

async def save_setting_with_retry(key: str, value: str):
    for attempt in range(MAX_RETRIES):
        try:
            await db_manager.save_setting(key, value)
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            raise

async def load_setting_with_retry(key: str) -> str:
    for attempt in range(MAX_RETRIES):
        try:
            return await db_manager.load_setting(key)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            raise
    return ""

def save_setting(key: str, value: str):
    asyncio.run(save_setting_with_retry(key, value))

def load_setting(key: str) -> str:
    return asyncio.run(load_setting_with_retry(key))

async def update_thread_metadata(thread_id: str, metadata: dict):
    for attempt in range(MAX_RETRIES):
        try:
            await cl_data.update_thread(thread_id, metadata=metadata)
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            raise

# -----------------------------------------------------------------------------
# Callback Manager
# -----------------------------------------------------------------------------

class CallbackManager:
    def __init__(self):
        self._callbacks = {}

    def register(self, name: str, callback, is_async: bool = False) -> None:
        self._callbacks[name] = {'func': callback, 'is_async': is_async}

    async def call(self, name: str, **kwargs) -> None:
        if name not in self._callbacks:
            logger.warning(f"No callback registered for {name}")
            return
        callback_info = self._callbacks[name]
        func = callback_info['func']
        is_async = callback_info['is_async']
        try:
            if is_async:
                await func(**kwargs)
            else:
                if asyncio.iscoroutinefunction(func):
                    await func(**kwargs)
                else:
                    await asyncio.get_event_loop().run_in_executor(None, lambda: func(**kwargs))
        except Exception as e:
            logger.error(f"Error in callback {name}: {str(e)}")

callback_manager = CallbackManager()

def register_callback(name: str, callback, is_async: bool = False) -> None:
    callback_manager.register(name, callback, is_async)

async def trigger_callback(name: str, **kwargs) -> None:
    await callback_manager.call(name, **kwargs)

def callback(name: str, is_async: bool = False):
    def decorator(func):
        register_callback(name, func, is_async)
        return func
    return decorator

# -----------------------------------------------------------------------------
# ADDITIONAL CALLBACKS
# -----------------------------------------------------------------------------
def interaction_callback(message=None, response=None, **kwargs):
    logger.debug(f"[CALLBACK: interaction] Message: {message} | Response: {response}")
    message_queue.put({
        "content": f"[CALLBACK: interaction] Message: {message} | Response: {response}",
        "author": "Callback"
    })

def error_callback(message=None, **kwargs):
    logger.error(f"[CALLBACK: error] Message: {message}")
    message_queue.put({
        "content": f"[CALLBACK: error] Message: {message}",
        "author": "Callback"
    })

def tool_call_callback(message=None, **kwargs):
    logger.debug(f"[CALLBACK: tool_call] Tool used: {message}")
    message_queue.put({
        "content": f"[CALLBACK: tool_call] Tool used: {message}",
        "author": "Callback"
    })

def instruction_callback(message=None, **kwargs):
    logger.debug(f"[CALLBACK: instruction] Instruction: {message}")
    message_queue.put({
        "content": f"[CALLBACK: instruction] Instruction: {message}",
        "author": "Callback"
    })

def self_reflection_callback(message=None, **kwargs):
    logger.debug(f"[CALLBACK: self_reflection] Reflection: {message}")
    message_queue.put({
        "content": f"[CALLBACK: self_reflection] Reflection: {message}",
        "author": "Callback"
    })

register_display_callback('error', error_callback)
register_display_callback('tool_call', tool_call_callback)
register_display_callback('instruction', instruction_callback)
register_display_callback('self_reflection', self_reflection_callback)

# -----------------------------------------------------------------------------
# Tools Loader
# -----------------------------------------------------------------------------

def load_tools_from_tools_py():
    """
    Imports and returns all contents from tools.py file.
    Also adds the tools to the global namespace.
    """
    tools_dict = {}
    try:
        spec = importlib.util.spec_from_file_location("tools", "tools.py")
        if spec is None:
            logger.info("tools.py not found in current directory")
            return tools_dict

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for name, obj in inspect.getmembers(module):
            if not name.startswith('_') and callable(obj) and not inspect.isclass(obj):
                # Store the function in globals
                globals()[name] = obj

                # Build the function definition
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": obj.__doc__ or f"Function to {name.replace('_', ' ')}",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    # Keep the actual callable as well
                    "callable": obj,
                }

                tools_dict[name] = tool_def
                logger.info(f"Loaded and globalized tool function: {name}")

        logger.info(f"Loaded {len(tools_dict)} tool functions from tools.py")
    except Exception as e:
        logger.warning(f"Error loading tools from tools.py: {e}")
    return tools_dict

# -----------------------------------------------------------------------------
# Async Queue Processor
# -----------------------------------------------------------------------------

async def process_message_queue():
    while True:
        try:
            if not message_queue.empty():
                msg_data = message_queue.get()
                await cl.Message(**msg_data).send()
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error processing message queue: {e}")

# -----------------------------------------------------------------------------
# Step & Task Callbacks
# -----------------------------------------------------------------------------

async def step_callback(step_details):
    logger.info(f"[CALLBACK DEBUG] step_callback: {step_details}")
    agent_name = step_details.get("agent_name", "Agent")
    try:
        if step_details.get("response"):
            message_queue.put({
                "content": f"Agent Response: {step_details['response']}",
                "author": agent_name
            })
        if step_details.get("tool_name"):
            message_queue.put({
                "content": f"🛠️ Using tool: {step_details['tool_name']}",
                "author": "System"
            })
    except Exception as e:
        logger.error(f"Error in step_callback: {e}", exc_info=True)

async def task_callback(task_output):
    logger.info(f"[CALLBACK DEBUG] task_callback: type={type(task_output)}")
    try:
        if hasattr(task_output, 'raw'):
            content = task_output.raw
        elif hasattr(task_output, 'content'):
            content = task_output.content
        else:
            content = str(task_output)
        message_queue.put({
            "content": f"Task Output: {content}",
            "author": "Task"
        })
    except Exception as e:
        logger.error(f"Error in task_callback: {e}", exc_info=True)

async def step_callback_wrapper(step_details):
    logger.info(f"[CALLBACK DEBUG] step_callback_wrapper: {step_details}")
    agent_name = step_details.get("agent_name", "Agent")
    try:
        if not cl.context.context_var.get():
            logger.warning("[CALLBACK DEBUG] No Chainlit context in wrapper.")
            return
        if step_details.get("response"):
            await cl.Message(
                content=f"{agent_name}: {step_details['response']}",
                author=agent_name,
            ).send()
        if step_details.get("tool_name"):
            await cl.Message(
                content=f"🛠️ {agent_name} is using tool: {step_details['tool_name']}",
                author="System",
            ).send()
        if step_details.get("thought"):
            await cl.Message(
                content=f"💭 {agent_name}'s thought: {step_details['thought']}",
                author=agent_name,
            ).send()
    except Exception as e:
        logger.error(f"Error in step_callback_wrapper: {e}", exc_info=True)
        try:
            await cl.Message(content=f"Error in step callback: {e}", author="System").send()
        except Exception as send_error:
            logger.error(f"Error sending error message: {send_error}")

async def task_callback_wrapper(task_output):
    logger.info("[CALLBACK DEBUG] task_callback_wrapper triggered")
    try:
        if not cl.context.context_var.get():
            logger.warning("[CALLBACK DEBUG] No Chainlit context in task wrapper.")
            return
        if hasattr(task_output, 'raw'):
            content = task_output.raw
        elif hasattr(task_output, 'content'):
            content = task_output.content
        else:
            content = str(task_output)

        await cl.Message(
            content=f"✅ Agent completed task:\n{content}",
            author="Agent",
        ).send()

        if hasattr(task_output, 'details'):
            await cl.Message(
                content=f"📝 Additional details:\n{task_output.details}",
                author="Agent",
            ).send()
    except Exception as e:
        logger.error(f"Error in task_callback_wrapper: {e}", exc_info=True)
        try:
            await cl.Message(content=f"Error in task callback: {e}", author="System").send()
        except Exception as send_error:
            logger.error(f"Error sending error message: {send_error}")

def sync_task_callback_wrapper(task_output):
    logger.info("[CALLBACK DEBUG] sync_task_callback_wrapper")
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.run_coroutine_threadsafe(task_callback_wrapper(task_output), loop)
        else:
            loop.run_until_complete(task_callback_wrapper(task_output))
    except Exception as e:
        logger.error(f"Error in sync_task_callback_wrapper: {e}", exc_info=True)

def sync_step_callback_wrapper(step_details):
    logger.info("[CALLBACK DEBUG] sync_step_callback_wrapper")
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.run_coroutine_threadsafe(step_callback_wrapper(step_details), loop)
        else:
            loop.run_until_complete(step_callback_wrapper(step_details))
    except Exception as e:
        logger.error(f"Error in sync_step_callback_wrapper: {e}", exc_info=True)

# -----------------------------------------------------------------------------
# Main PraisonAI Runner
# -----------------------------------------------------------------------------
async def ui_run_praisonai(config, topic, tools_dict):
    logger.info("Starting ui_run_praisonai")
    agents_map = {}
    tasks = []
    tasks_dict = {}

    try:
        queue_processor = asyncio.create_task(process_message_queue())

        # Create agents
        for role, details in config['roles'].items():
            role_name = details.get('name', role).format(topic=topic)
            role_filled = details.get('role', role).format(topic=topic)
            goal_filled = details['goal'].format(topic=topic)
            backstory_filled = details['backstory'].format(topic=topic)

            def step_callback_sync(step_details):
                step_details["agent_name"] = role_name
                try:
                    loop_ = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop_)
                    loop_.run_until_complete(step_callback(step_details))
                    loop_.close()
                except Exception as e:
                    logger.error(f"Error in step_callback_sync: {e}", exc_info=True)

            agent = Agent(
                name=role_name,
                role=role_filled,
                goal=goal_filled,
                backstory=backstory_filled,
                llm=details.get('llm', 'gpt-4o'),
                verbose=True,
                allow_delegation=details.get('allow_delegation', False),
                max_iter=details.get('max_iter', 15),
                max_rpm=details.get('max_rpm'),
                max_execution_time=details.get('max_execution_time'),
                cache=details.get('cache', True),
                step_callback=step_callback_sync,
                self_reflect=details.get('self_reflect', False)
            )
            agents_map[role] = agent

        # Create tasks
        for role, details in config['roles'].items():
            agent = agents_map[role]
            role_name = agent.name

            # -------------------------------------------------------------
            # FIX: Skip empty or invalid tool names to avoid null tool objects
            # -------------------------------------------------------------
            role_tools = []
            task_tools = []  # Initialize task_tools outside the loop
            
            for tool_name in details.get('tools', []):
                if not tool_name or not tool_name.strip():
                    logger.warning("Skipping empty tool name.")
                    continue
                if tool_name in tools_dict:
                    # Create a copy of the tool definition
                    tool_def = tools_dict[tool_name].copy()
                    # Store the callable separately and remove from definition
                    callable_func = tool_def.pop("callable")
                    # Add callable to role_tools for task execution
                    role_tools.append(callable_func)
                    # Add API tool definition to task's tools
                    task_tools.append(tool_def)
                    # Also set the agent's tools to include both
                    agent.tools = role_tools
                else:
                    logger.warning(f"Tool '{tool_name}' not found. Skipping.")

            for tname, tdetails in details.get('tasks', {}).items():
                description_filled = tdetails['description'].format(topic=topic)
                expected_output_filled = tdetails['expected_output'].format(topic=topic)

                def task_callback_sync(task_output):
                    try:
                        loop_ = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop_)
                        loop_.run_until_complete(task_callback(task_output))
                        loop_.close()
                    except Exception as e:
                        logger.error(f"Error in task_callback_sync: {e}", exc_info=True)

                task = Task(
                    description=description_filled,
                    expected_output=expected_output_filled,
                    agent=agent,
                    tools=task_tools,  # Pass API tool definitions
                    async_execution=True,
                    context=[],
                    config=tdetails.get('config', {}),
                    output_json=tdetails.get('output_json'),
                    output_pydantic=tdetails.get('output_pydantic'),
                    output_file=tdetails.get('output_file', ""),
                    callback=task_callback_sync,
                    create_directory=tdetails.get('create_directory', False)
                )
                tasks.append(task)
                tasks_dict[tname] = task

        # Build context links
        for role, details in config['roles'].items():
            for tname, tdetails in details.get('tasks', {}).items():
                if tname not in tasks_dict:
                    continue
                task = tasks_dict[tname]
                context_tasks = [
                    tasks_dict[ctx]
                    for ctx in tdetails.get('context', [])
                    if ctx in tasks_dict
                ]
                task.context = context_tasks

        await cl.Message(content="Starting PraisonAI agents execution...", author="System").send()

        # Decide how to process tasks
        if config.get('process') == 'hierarchical':
            prai_agents = PraisonAIAgents(
                agents=list(agents_map.values()),
                tasks=tasks,
                verbose=True,
                process="hierarchical",
                manager_llm=config.get('manager_llm', 'gpt-4o')
            )
        else:
            prai_agents = PraisonAIAgents(
                agents=list(agents_map.values()),
                tasks=tasks,
                verbose=2
            )

        cl.user_session.set("agents", prai_agents)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, prai_agents.start)

        if hasattr(response, 'raw'):
            result = response.raw
        elif hasattr(response, 'content'):
            result = response.content
        else:
            result = str(response)

        await cl.Message(content="PraisonAI agents execution completed.", author="System").send()
        await asyncio.sleep(1)
        queue_processor.cancel()
        return result

    except Exception as e:
        error_msg = f"Error in ui_run_praisonai: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(content=error_msg, author="System").send()
        raise

# -----------------------------------------------------------------------------
# Chainlit Handlers + logic
# -----------------------------------------------------------------------------

tools_dict = load_tools_from_tools_py()
print(f"[DEBUG] tools_dict: {tools_dict}")

# Load agent config (default) from 'agents.yaml'
with open(agent_file, 'r') as f:
    config = yaml.safe_load(f)

AUTH_PASSWORD_ENABLED = os.getenv("AUTH_PASSWORD_ENABLED", "true").lower() == "true"
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")
if not CHAINLIT_AUTH_SECRET:
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"

username_env = os.getenv("CHAINLIT_USERNAME", "admin")
password_env = os.getenv("CHAINLIT_PASSWORD", "admin")

def simple_auth_callback(u: str, p: str):
    if (u, p) == (username_env, password_env):
        return cl.User(identifier=u, metadata={"role": "ADMIN", "provider": "credentials"})
    return None

if AUTH_PASSWORD_ENABLED:
    auth_callback = cl.password_auth_callback(simple_auth_callback)

@cl.set_chat_profiles
async def set_profiles(current_user: cl.User):
    return [
        cl.ChatProfile(
            name="Auto",
            markdown_description=(
                "Automatically generate agents and tasks based on your input."
            ),
            starters=[
                cl.Starter(
                    label="Create a movie script",
                    message=(
                        "Create a movie script about a futuristic society where AI "
                        "and humans coexist, focusing on the conflict and resolution "
                        "between them. Start with an intriguing opening scene."
                    ),
                    icon="/public/movie.svg",
                ),
                cl.Starter(
                    label="Design a fantasy world",
                    message=(
                        "Design a detailed fantasy world with unique geography, "
                        "cultures, and magical systems. Start by describing the main "
                        "continent and its inhabitants."
                    ),
                    icon="/public/fantasy.svg",
                ),
                cl.Starter(
                    label="Write a futuristic political thriller",
                    message=(
                        "Write a futuristic political thriller involving a conspiracy "
                        "within a global government. Start with a high-stakes meeting "
                        "that sets the plot in motion."
                    ),
                    icon="/public/thriller.svg",
                ),
                cl.Starter(
                    label="Develop a new board game",
                    message=(
                        "Develop a new, innovative board game. Describe the game's "
                        "objective, rules, and unique mechanics. Create a scenario to "
                        "illustrate gameplay."
                    ),
                    icon="/public/game.svg",
                ),
            ],
        ),
        cl.ChatProfile(
            name="Manual",
            markdown_description="Manually define your agents and tasks using a YAML file.",
        ),
    ]

@cl.on_chat_start
async def start_chat():
    try:
        model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
        cl.user_session.set("model_name", model_name)
        logger.debug(f"Model name: {model_name}")

        cl.user_session.set(
            "message_history",
            [{"role": "system", "content": "You are a helpful assistant."}],
        )
        
        if not os.path.exists("tools.py"):
            with open("tools.py", "w") as f:
                f.write("# Add your custom tools here\n")
        
        if not os.path.exists("agents.yaml"):
            with open("agents.yaml", "w") as f:
                f.write("# Add your custom agents here\n")
        
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

        if chat_profile == "Manual":
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

@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    try:
        message_history = cl.user_session.get("message_history", [])
        root_messages = [m for m in thread["steps"] if m["parentId"] is None]
        for message in root_messages:
            if message["type"] == "user_message":
                message_history.append({"role": "user", "content": message["output"]})
            elif message["type"] == "ai_message":
                message_history.append({"role": "assistant", "content": message["content"]})
        cl.user_session.set("message_history", message_history)
    except Exception as e:
        logger.error(f"Error in on_chat_resume: {str(e)}")

@cl.on_message
async def main(message: cl.Message):
    try:
        logger.info(f"User message: {message.content}")
        msg = cl.Message(content="")
        await msg.stream_token(f"🔄 Processing your request: {message.content}...")
        
        # Run PraisonAI
        result = await ui_run_praisonai(config, message.content, tools_dict)

        message_history = cl.user_session.get("message_history", [])
        message_history.append({"role": "user", "content": message.content})
        message_history.append({"role": "assistant", "content": str(result)})
        cl.user_session.set("message_history", message_history)
        await msg.send()
    except Exception as e:
        error_msg = f"Error running PraisonAI agents: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(content=error_msg, author="System").send()

@cl.on_settings_update
async def on_settings_update(settings):
    try:
        global config_list, framework
        config_list[0]['model'] = settings["Model"]
        config_list[0]['base_url'] = settings["BaseUrl"]
        config_list[0]['api_key'] = settings["ApiKey"]
        
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
        
        thread_id = cl.user_session.get("thread_id")
        if thread_id:
            for attempt in range(MAX_RETRIES):
                try:
                    thread = await cl_data.get_thread(thread_id)
                    if thread:
                        metadata = thread.get("metadata", {})
                        if isinstance(metadata, str):
                            try:
                                import json
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
        try:
            await asyncio.sleep(RETRY_DELAY * 2)
            await on_settings_update(settings)
        except Exception as e:
            logger.error(f"Final retry failed: {str(e)}")
            await cl.Message(content=f"Failed to update settings after retries: {str(e)}").send()