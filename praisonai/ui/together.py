# colab_combined.py
"""
Combined and refactored code from colab.py, colab_chainlit.py, and callbacks.py
All features preserved. Simplified logging and unified callback usage.
"""

import os
import sys
import yaml
import logging
import inspect
import asyncio
import importlib.util
from datetime import datetime
from queue import Queue
from dotenv import load_dotenv
import chainlit as cl
from chainlit.types import ThreadDict

# External imports from your local packages (adjust if needed)
from praisonaiagents import Agent, Task, PraisonAIAgents

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
# Callback Manager
# -----------------------------------------------------------------------------

class CallbackManager:
    """Manages callbacks for the PraisonAI UI."""
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
# Tools Loader
# -----------------------------------------------------------------------------

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
                # Format the tool as an OpenAI function
                tool = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": obj.__doc__ or f"Function to {name.replace('_', ' ')}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to look up information about"
                                }
                            },
                            "required": ["query"]
                        }
                    }
                }
                # Add formatted tool to tools list
                tools_list.append(tool)
                logger.info(f"Loaded and globalized tool function: {name}")

        logger.info(f"Loaded {len(tools_list)} tool functions from tools.py")
        logger.info(f"Tools list: {tools_list}")
        
    except Exception as e:
        logger.warning(f"Error loading tools from tools.py: {e}")
        
    return tools_list

# -----------------------------------------------------------------------------
# Async Queue Processor
# -----------------------------------------------------------------------------

async def process_message_queue():
    """Continuously checks the message queue and sends messages to Chainlit."""
    while True:
        try:
            if not message_queue.empty():
                msg_data = message_queue.get()
                await cl.Message(**msg_data).send()
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error processing message queue: {e}")

# -----------------------------------------------------------------------------
# Step & Task Callbacks (Async & Sync)
# -----------------------------------------------------------------------------

async def step_callback(step_details):
    """Default asynchronous callback for each agent step."""
    logger.info(f"[CALLBACK DEBUG] step_callback: {step_details}")
    agent_name = step_details.get("agent_name", "Agent")
    try:
        # Queue agent response
        if step_details.get("response"):
            message_queue.put({
                "content": f"Agent Response: {step_details['response']}",
                "author": agent_name
            })
        # Queue tool usage
        if step_details.get("tool_name"):
            message_queue.put({
                "content": f"🛠️ Using tool: {step_details['tool_name']}",
                "author": "System"
            })
    except Exception as e:
        logger.error(f"Error in step_callback: {e}", exc_info=True)

async def task_callback(task_output):
    """Default asynchronous callback for task completion."""
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
    """Wraps step_callback logic for direct Chainlit usage."""
    logger.info(f"[CALLBACK DEBUG] step_callback_wrapper: {step_details}")
    agent_name = step_details.get("agent_name", "Agent")
    try:
        if not cl.context.context_var.get():
            logger.warning("[CALLBACK DEBUG] No Chainlit context in wrapper.")
            return
        # Agent response
        if step_details.get("response"):
            await cl.Message(
                content=f"{agent_name}: {step_details['response']}",
                author=agent_name,
            ).send()
        # Tool usage
        if step_details.get("tool_name"):
            await cl.Message(
                content=f"🛠️ {agent_name} is using tool: {step_details['tool_name']}",
                author="System",
            ).send()
        # Thought
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
    """Wraps task_callback logic for direct Chainlit usage."""
    logger.info("[CALLBACK DEBUG] task_callback_wrapper triggered")
    try:
        if not cl.context.context_var.get():
            logger.warning("[CALLBACK DEBUG] No Chainlit context in task wrapper.")
            return

        # Determine content to display
        if hasattr(task_output, 'raw'):
            content = task_output.raw
        elif hasattr(task_output, 'content'):
            content = task_output.content
        else:
            content = str(task_output)

        # Display task completion
        await cl.Message(
            content=f"✅ Agent completed task:\n{content}",
            author="Agent",
        ).send()

        # Display additional details if any
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
    """Sync wrapper for task callback, allows thread-safe usage."""
    logger.info("[CALLBACK DEBUG] sync_task_callback_wrapper")
    try:
        loop = None
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
    """Sync wrapper for step callback, allows thread-safe usage."""
    logger.info("[CALLBACK DEBUG] sync_step_callback_wrapper")
    try:
        loop = None
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
    """Run PraisonAI agents with the given config, topic, and tools."""
    logger.info("Starting ui_run_praisonai")
    agents = {}
    tasks = []
    tasks_dict = {}

    try:
        # Start background task to process the message queue
        queue_processor = asyncio.create_task(process_message_queue())

        # Create agents
        for role, details in config['roles'].items():
            role_name = details.get('name', role).format(topic=topic)
            role_filled = details.get('role', role).format(topic=topic)
            goal_filled = details['goal'].format(topic=topic)
            backstory_filled = details['backstory'].format(topic=topic)

            await cl.Message(content=f"[DEBUG] Creating agent: {role_name}", author="System").send()

            def step_callback_sync(step_details):
                # Insert agent name for reference
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
                step_callback=step_callback_sync
            )
            agents[role] = agent

        # Create tasks
        for role, details in config['roles'].items():
            agent = agents[role]
            role_name = agent.name
            # Build tool list for this role
            role_tools = []
            for tool_name in details.get('tools', []):
                if tool_name in tools_dict:
                    role_tools.append(tools_dict[tool_name])

            # Build tasks for this agent
            for tname, tdetails in details.get('tasks', {}).items():
                description_filled = tdetails['description'].format(topic=topic)
                expected_output_filled = tdetails['expected_output'].format(topic=topic)

                await cl.Message(content=f"[DEBUG] Created task: {tname} for {role_name}", author="System").send()

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
                    tools=role_tools,
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

        # Choose hierarchical or standard process
        if config.get('process') == 'hierarchical':
            agents = PraisonAIAgents(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True,
                process="hierarchical",
                manager_llm=config.get('manager_llm', 'gpt-4o')
            )
        else:
            agents = PraisonAIAgents(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=2
            )

        # Store agents in user session
        cl.user_session.set("agents", agents)

        # Run the agents in a separate thread
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, agents.start)

        # Process final response
        if hasattr(response, 'raw'):
            result = response.raw
        elif hasattr(response, 'content'):
            result = response.content
        else:
            result = str(response)

        await cl.Message(content="PraisonAI agents execution completed.", author="System").send()
        await asyncio.sleep(1)  # Give time for final messages
        queue_processor.cancel()
        return result

    except Exception as e:
        error_msg = f"Error in ui_run_praisonai: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(content=error_msg, author="System").send()
        raise

# -----------------------------------------------------------------------------
# Chainlit Handlers
# -----------------------------------------------------------------------------

tools_dict = load_tools_from_tools_py()

# Load agent config
with open(agent_file, 'r') as f:
    config = yaml.safe_load(f)

@cl.on_message
async def main(message: cl.Message):
    """Main Chainlit message handler."""
    try:
        logger.info(f"User message: {message.content}")
        await cl.Message(content=f"🔄 Processing your request: {message.content}...", author="System").send()
        await cl.Message(content="Using Running PraisonAI Agents...", author="System").send()
        result = await ui_run_praisonai(config, message.content, tools_dict)
        # await cl.Message(content="", author="System").send()
    except Exception as e:
        error_msg = f"Error running PraisonAI agents: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(content=error_msg, author="System").send()

@cl.on_chat_start
async def start():
    """Handler for chat start."""
    await cl.Message(content="👋 Welcome! I'm your AI assistant. What would you like to work on?", author="System").send()

# Optional password auth
if os.getenv("CHAINLIT_AUTH_SECRET"):
    @cl.password_auth_callback
    def auth_callback(username: str, password: str) -> cl.User:
        if username == os.getenv("CHAINLIT_USERNAME", "admin") and password == os.getenv("CHAINLIT_PASSWORD", "admin"):
            return cl.User(identifier=username, metadata={"role": "user"})
        return None
