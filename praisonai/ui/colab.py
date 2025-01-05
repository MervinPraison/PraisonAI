from praisonaiagents import Agent, Task, PraisonAIAgents
import os
import importlib
import inspect
import yaml
import logging
from .callbacks import trigger_callback
import asyncio
import chainlit as cl
from queue import Queue

logger = logging.getLogger(__name__)
agent_file = "agents.yaml"

with open(agent_file, 'r') as f:
    config = yaml.safe_load(f)

topic = "get from the message content from the chainlit user message"

# Create a message queue
message_queue = Queue()

async def process_message_queue():
    """Process messages in the queue and send them to Chainlit"""
    while True:
        try:
            if not message_queue.empty():
                msg_data = message_queue.get()
                await cl.Message(**msg_data).send()
            await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
        except Exception as e:
            logger.error(f"Error processing message queue: {e}")

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

async def step_callback(step_details):
    """Callback for agent steps"""
    logger.info(f"[CALLBACK DEBUG] Step callback triggered with details: {step_details}")
    try:
        # Queue message for agent response
        if step_details.get("response"):
            message_queue.put({
                "content": f"Agent Response: {step_details.get('response')}",
                "author": step_details.get("agent_name", "Agent")
            })
            logger.info("[CALLBACK DEBUG] Queued agent response message")
        
        # Queue message for tool usage
        if step_details.get("tool_name"):
            message_queue.put({
                "content": f"🛠️ Using tool: {step_details.get('tool_name')}",
                "author": "System"
            })
            logger.info("[CALLBACK DEBUG] Queued tool usage message")
            
    except Exception as e:
        logger.error(f"[CALLBACK DEBUG] Error in step callback: {str(e)}", exc_info=True)

async def task_callback(task_output):
    """Callback for task completion"""
    logger.info(f"[CALLBACK DEBUG] Task callback triggered with output: {task_output}")
    try:
        # Create message content
        if hasattr(task_output, 'raw'):
            content = task_output.raw
        elif hasattr(task_output, 'content'):
            content = task_output.content
        else:
            content = str(task_output)
            
        # Queue the message
        message_queue.put({
            "content": f"Task Output: {content}",
            "author": "Task"
        })
        logger.info("[CALLBACK DEBUG] Queued task completion message")
        
    except Exception as e:
        logger.error(f"[CALLBACK DEBUG] Error in task callback: {str(e)}", exc_info=True)

async def step_callback_wrapper(step_details):
    logger.info(f"[CALLBACK DEBUG] Step callback wrapper triggered with details: {step_details}")
    try:
        # Check if we have a Chainlit context
        if not cl.context.context_var.get():
            logger.warning("[CALLBACK DEBUG] No Chainlit context available in wrapper")
            return
        logger.info("[CALLBACK DEBUG] Chainlit context found in wrapper")

        # Create a message for the agent's response
        if step_details.get("response"):
            logger.info(f"[CALLBACK DEBUG] Sending agent response from wrapper: {step_details.get('response')}")
            try:
                await cl.Message(
                    content=f"{role_name}: {step_details.get('response')}",
                    author=role_name,
                ).send()
                logger.info("[CALLBACK DEBUG] Successfully sent agent response message from wrapper")
            except Exception as e:
                logger.error(f"[CALLBACK DEBUG] Error sending agent response message from wrapper: {str(e)}")

        # Create a message for any tool usage
        if step_details.get("tool_name"):
            logger.info(f"[CALLBACK DEBUG] Sending tool usage from wrapper: {step_details.get('tool_name')}")
            try:
                await cl.Message(
                    content=f"🛠️ {role_name} is using tool: {step_details.get('tool_name')}",
                    author="System",
                ).send()
                logger.info("[CALLBACK DEBUG] Successfully sent tool usage message from wrapper")
            except Exception as e:
                logger.error(f"[CALLBACK DEBUG] Error sending tool usage message from wrapper: {str(e)}")

        # Create a message for any thoughts or reasoning
        if step_details.get("thought"):
            logger.info(f"[CALLBACK DEBUG] Sending thought from wrapper: {step_details.get('thought')}")
            try:
                await cl.Message(
                    content=f"💭 {role_name}'s thought: {step_details.get('thought')}",
                    author=role_name,
                ).send()
                logger.info("[CALLBACK DEBUG] Successfully sent thought message from wrapper")
            except Exception as e:
                logger.error(f"[CALLBACK DEBUG] Error sending thought message from wrapper: {str(e)}")

    except Exception as e:
        logger.error(f"[CALLBACK DEBUG] Error in step callback wrapper: {str(e)}", exc_info=True)
        try:
            await cl.Message(
                content=f"Error in step callback: {str(e)}",
                author="System",
            ).send()
        except Exception as send_error:
            logger.error(f"[CALLBACK DEBUG] Error sending error message: {str(send_error)}")

async def task_callback_wrapper(task_output):
    logger.info(f"[CALLBACK DEBUG] Task callback wrapper triggered with output type: {type(task_output)}")
    try:
        # Check if we have a Chainlit context
        if not cl.context.context_var.get():
            logger.warning("[CALLBACK DEBUG] No Chainlit context available in task wrapper")
            return
        logger.info("[CALLBACK DEBUG] Chainlit context found in task wrapper")

        # Create a message for task completion
        if hasattr(task_output, 'raw'):
            content = task_output.raw
            logger.info("[CALLBACK DEBUG] Using raw output")
        elif hasattr(task_output, 'content'):
            content = task_output.content
            logger.info("[CALLBACK DEBUG] Using content output")
        else:
            content = str(task_output)
            logger.info("[CALLBACK DEBUG] Using string representation of output")
            
        logger.info(f"[CALLBACK DEBUG] Sending task completion message from wrapper: {content[:100]}...")
        try:
            await cl.Message(
                content=f"✅ {role_name} completed task:\n{content}",
                author=role_name,
            ).send()
            logger.info("[CALLBACK DEBUG] Successfully sent task completion message from wrapper")
        except Exception as e:
            logger.error(f"[CALLBACK DEBUG] Error sending task completion message from wrapper: {str(e)}")

        # If there are any additional task details
        if hasattr(task_output, 'details'):
            logger.info("[CALLBACK DEBUG] Task has additional details")
            try:
                await cl.Message(
                    content=f"📝 Additional details:\n{task_output.details}",
                    author=role_name,
                ).send()
                logger.info("[CALLBACK DEBUG] Successfully sent additional details message")
            except Exception as e:
                logger.error(f"[CALLBACK DEBUG] Error sending additional details message: {str(e)}")

    except Exception as e:
        logger.error(f"[CALLBACK DEBUG] Error in task callback wrapper: {str(e)}", exc_info=True)
        try:
            await cl.Message(
                content=f"Error in task callback: {str(e)}",
                author="System",
            ).send()
        except Exception as send_error:
            logger.error(f"[CALLBACK DEBUG] Error sending error message: {str(send_error)}")

def sync_task_callback_wrapper(task_output):
    logger.info("[CALLBACK DEBUG] Sync task callback wrapper triggered")
    try:
        # Create a new event loop for this thread if there isn't one
        try:
            loop = asyncio.get_event_loop()
            logger.info("[CALLBACK DEBUG] Got existing event loop")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("[CALLBACK DEBUG] Created new event loop")
        
        if loop.is_running():
            # If loop is running, schedule the callback
            logger.info("[CALLBACK DEBUG] Loop is running, scheduling callback")
            asyncio.run_coroutine_threadsafe(
                task_callback_wrapper(task_output),
                loop
            )
        else:
            # If loop is not running, run it directly
            logger.info("[CALLBACK DEBUG] Loop is not running, running callback directly")
            loop.run_until_complete(task_callback_wrapper(task_output))
            
    except Exception as e:
        logger.error(f"[CALLBACK DEBUG] Error in sync task callback: {str(e)}", exc_info=True)

def sync_step_callback_wrapper(step_details):
    logger.info("[CALLBACK DEBUG] Sync step callback wrapper triggered")
    try:
        # Create a new event loop for this thread if there isn't one
        try:
            loop = asyncio.get_event_loop()
            logger.info("[CALLBACK DEBUG] Got existing event loop")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("[CALLBACK DEBUG] Created new event loop")
        
        if loop.is_running():
            # If loop is running, schedule the callback
            logger.info("[CALLBACK DEBUG] Loop is running, scheduling callback")
            asyncio.run_coroutine_threadsafe(
                step_callback_wrapper(step_details),
                loop
            )
        else:
            # If loop is not running, run it directly
            logger.info("[CALLBACK DEBUG] Loop is not running, running callback directly")
            loop.run_until_complete(step_callback_wrapper(step_details))
            
    except Exception as e:
        logger.error(f"[CALLBACK DEBUG] Error in sync step callback: {str(e)}", exc_info=True)

async def ui_run_praisonai(config, topic, tools_dict):
    """Run PraisonAI with the given configuration and topic."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    agents = {}
    tasks = []
    tasks_dict = {}

    try:
        # Start message queue processor
        queue_processor = asyncio.create_task(process_message_queue())
        
        # Create agents for each role
        for role, details in config['roles'].items():
            # Format the role name and other details
            role_name = details.get('name', role).format(topic=topic)
            role_filled = details.get('role', role).format(topic=topic)
            goal_filled = details['goal'].format(topic=topic)
            backstory_filled = details['backstory'].format(topic=topic)

            # Test message to verify Chainlit is working
            await cl.Message(
                content=f"[DEBUG] Creating agent: {role_name}",
                author="System"
            ).send()

            # Create a sync wrapper for the step callback
            def step_callback_sync(step_details):
                try:
                    # Create a new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Add agent name to step details
                    step_details["agent_name"] = role_name
                    
                    # Run the callback
                    loop.run_until_complete(step_callback(step_details))
                    loop.close()
                except Exception as e:
                    logger.error(f"[CALLBACK DEBUG] Error in step callback: {str(e)}", exc_info=True)

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

        # Create tasks for each role
        for role, details in config['roles'].items():
            agent = agents[role]
            tools_list = []
            
            # Get tools for this role
            for tool_name in details.get('tools', []):
                if tool_name in tools_dict:
                    tool_func = tools_dict[tool_name]
                    tools_list.append(tool_func)

            # Create tasks for the agent
            for task_name, task_details in details.get('tasks', {}).items():
                description_filled = task_details['description'].format(topic=topic)
                expected_output_filled = task_details['expected_output'].format(topic=topic)

                # Test message to verify task creation
                await cl.Message(
                    content=f"[DEBUG] Created task: {task_name} for agent {role_name}",
                    author="System"
                ).send()

                # Create a sync wrapper for the task callback
                def task_callback_sync(task_output):
                    try:
                        # Create a new event loop for this thread
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        # Run the callback
                        loop.run_until_complete(task_callback(task_output))
                        loop.close()
                    except Exception as e:
                        logger.error(f"[CALLBACK DEBUG] Error in task callback: {str(e)}", exc_info=True)

                task = Task(
                    description=description_filled,
                    expected_output=expected_output_filled,
                    agent=agent,
                    tools=tools_list,
                    async_execution=True,
                    context=[],
                    config=task_details.get('config', {}),
                    output_json=task_details.get('output_json'),
                    output_pydantic=task_details.get('output_pydantic'),
                    output_file=task_details.get('output_file', ""),
                    callback=task_callback_sync,
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

        # Send the start message
        await cl.Message(
            content="Starting PraisonAI agents execution...",
            author="System"
        ).send()

        # Create and run the PraisonAI agents
        if config.get('process') == 'hierarchical':
            crew = PraisonAIAgents(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True,
                process="hierarchical",
                manager_llm=config.get('manager_llm', 'gpt-4o')
            )
        else:
            crew = PraisonAIAgents(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=2
            )

        # Store the crew in the user session
        cl.user_session.set("crew", crew)

        # Run the agents in a separate thread
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, crew.start)
        
        logger.debug(f"[CALLBACK DEBUG] Result: {response}")
        
        # Convert response to string if it's not already
        if hasattr(response, 'raw'):
            result = response.raw
        elif hasattr(response, 'content'):
            result = response.content
        else:
            result = str(response)
        
        # Send the completion message
        await cl.Message(
            content="PraisonAI agents execution completed.",
            author="System"
        ).send()
        
        # After getting the response, wait a bit for remaining messages
        await asyncio.sleep(1)  # Give time for final messages to be processed
        queue_processor.cancel()  # Stop the queue processor
        
        return result
        
    except Exception as e:
        error_msg = f"Error in ui_run_praisonai: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(
            content=error_msg,
            author="System"
        ).send()
        raise