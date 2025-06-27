# Standard library imports
import os
from datetime import datetime
from typing import Dict, Optional
import logging
import json
import asyncio
import io
import base64
import importlib.util
import inspect

# Third-party imports
from dotenv import load_dotenv
from PIL import Image
from tavily import TavilyClient
from crawl4ai import AsyncWebCrawler

# Local application/library imports
import chainlit as cl
from chainlit.input_widget import TextInput
from chainlit.types import ThreadDict
import chainlit.data as cl_data
from litellm import acompletion
from literalai.helper import utc_now
from db import DatabaseManager

# Load environment variables
load_dotenv()

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

CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")
if not CHAINLIT_AUTH_SECRET:
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"
    CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

now = utc_now()
create_step_counter = 0

# Initialize database
db_manager = DatabaseManager()
db_manager.initialize()

def save_setting(key: str, value: str):
    """Save a setting to the database"""
    asyncio.run(db_manager.save_setting(key, value))

def load_setting(key: str) -> str:
    """Load a setting from the database"""
    return asyncio.run(db_manager.load_setting(key))

cl_data._data_layer = db_manager

def load_custom_tools():
    """Load custom tools from tools.py if it exists"""
    custom_tools = {}
    try:
        spec = importlib.util.spec_from_file_location("tools", "tools.py")
        if spec is None:
            logger.debug("tools.py not found in current directory")
            return custom_tools
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Load all functions from tools.py
        for name, obj in inspect.getmembers(module):
            if not name.startswith('_') and callable(obj) and not inspect.isclass(obj):
                # Store function in globals for access
                globals()[name] = obj
                
                # Get function signature to build parameters
                sig = inspect.signature(obj)
                params_properties = {}
                required_params = []
                
                for param_name, param in sig.parameters.items():
                    if param_name != 'self':  # Skip self parameter
                        # Get type annotation if available
                        param_type = "string"  # Default type
                        if param.annotation != inspect.Parameter.empty:
                            if param.annotation == int:
                                param_type = "integer"
                            elif param.annotation == float:
                                param_type = "number"
                            elif param.annotation == bool:
                                param_type = "boolean"
                        
                        params_properties[param_name] = {
                            "type": param_type,
                            "description": f"Parameter {param_name}"
                        }
                        
                        # Add to required if no default value
                        if param.default == inspect.Parameter.empty:
                            required_params.append(param_name)
                
                # Build tool definition
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": obj.__doc__ or f"Function {name.replace('_', ' ')}",
                        "parameters": {
                            "type": "object",
                            "properties": params_properties,
                            "required": required_params
                        }
                    }
                }
                
                custom_tools[name] = tool_def
                logger.info(f"Loaded custom tool: {name}")
        
        logger.info(f"Loaded {len(custom_tools)} custom tools from tools.py")
    except Exception as e:
        logger.warning(f"Error loading custom tools: {e}")
    
    return custom_tools

# Load custom tools
custom_tools_dict = load_custom_tools()

tavily_api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=tavily_api_key) if tavily_api_key else None

async def tavily_web_search(query):
    if not tavily_client:
        return json.dumps({
            "query": query,
            "error": "Tavily API key is not set. Web search is unavailable."
        })

    response = tavily_client.search(query)
    logger.debug(f"Tavily search response: {response}")

    async with AsyncWebCrawler() as crawler:
        results = []
        for result in response.get('results', []):
            url = result.get('url')
            if url:
                try:
                    crawl_result = await crawler.arun(url=url)
                    results.append({
                        "content": result.get('content'),
                        "url": url,
                        "full_content": crawl_result.markdown
                    })
                except Exception as e:
                    logger.error(f"Error crawling {url}: {str(e)}")
                    results.append({
                        "content": result.get('content'),
                        "url": url,
                        "full_content": "Error: Unable to crawl this URL"
                    })

    return json.dumps({
        "query": query,
        "results": results
    })

# Build tools list with Tavily and custom tools
tools = []

# Add Tavily tool if API key is available
if tavily_api_key:
    tools.append({
        "type": "function",
        "function": {
            "name": "tavily_web_search",
            "description": "Search the web using Tavily API and crawl the resulting URLs",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    })

# Add custom tools from tools.py
tools.extend(list(custom_tools_dict.values()))

# Authentication configuration
AUTH_PASSWORD_ENABLED = os.getenv("AUTH_PASSWORD_ENABLED", "true").lower() == "true"  # Password authentication enabled by default
AUTH_OAUTH_ENABLED = os.getenv("AUTH_OAUTH_ENABLED", "false").lower() == "true"    # OAuth authentication disabled by default

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

async def send_count():
    await cl.Message(
        f"Create step counter: {create_step_counter}", disable_feedback=True
    ).send()

@cl.on_chat_start
async def start():
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    cl.user_session.set("model_name", model_name)
    logger.debug(f"Model name: {model_name}")
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini",
                initial=model_name
            )
        ]
    )
    cl.user_session.set("settings", settings)
    await settings.send()

@cl.on_settings_update
async def setup_agent(settings):
    logger.debug(settings)
    cl.user_session.set("settings", settings)
    model_name = settings["model_name"]
    cl.user_session.set("model_name", model_name)

    save_setting("model_name", model_name)

    thread_id = cl.user_session.get("thread_id")
    if thread_id:
        thread = await cl_data.get_thread(thread_id)
        if thread:
            metadata = thread.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = {}
            metadata["model_name"] = model_name
            await cl_data.update_thread(thread_id, metadata=metadata)
            cl.user_session.set("metadata", metadata)

@cl.on_message
async def main(message: cl.Message):
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    message_history = cl.user_session.get("message_history", [])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    image = None
    if message.elements and isinstance(message.elements[0], cl.Image):
        image_element = message.elements[0]
        try:
            image = Image.open(image_element.path)
            image.load()
            cl.user_session.set("image", image)
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            await cl.Message(content="Error processing the image. Please try again.").send()
            return

    user_message = f"""
Answer the question and use tools if needed:

Current Date and Time: {now}

User Question: {message.content}
"""

    if image:
        user_message = f"Image uploaded. {user_message}"

    message_history.append({"role": "user", "content": user_message})
    msg = cl.Message(content="")
    await msg.send()

    completion_params = {
        "model": model_name,
        "messages": message_history,
        "stream": True,
    }

    if image:
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        completion_params["messages"][-1] = {
            "role": "user",
            "content": [
                {"type": "text", "text": user_message},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_str}"}}
            ]
        }

    # Pass tools if we have any (Tavily or custom)
    if tools:
        completion_params["tools"] = tools
        completion_params["tool_choice"] = "auto"

    response = await acompletion(**completion_params)

    full_response = ""
    tool_calls = []
    current_tool_call = None

    async for part in response:
        if 'choices' in part and len(part['choices']) > 0:
            delta = part['choices'][0].get('delta', {})

            if 'content' in delta and delta['content'] is not None:
                token = delta['content']
                await msg.stream_token(token)
                full_response += token

            if tools and 'tool_calls' in delta and delta['tool_calls'] is not None:
                for tool_call in delta['tool_calls']:
                    if current_tool_call is None or tool_call.index != current_tool_call['index']:
                        if current_tool_call:
                            tool_calls.append(current_tool_call)
                        current_tool_call = {
                            'id': tool_call.id,
                            'type': tool_call.type,
                            'index': tool_call.index,
                            'function': {
                                'name': tool_call.function.name if tool_call.function else None,
                                'arguments': ''
                            }
                        }
                    if tool_call.function:
                        if tool_call.function.name:
                            current_tool_call['function']['name'] = tool_call.function.name
                        if tool_call.function.arguments:
                            current_tool_call['function']['arguments'] += tool_call.function.arguments

    if current_tool_call:
        tool_calls.append(current_tool_call)

    logger.debug(f"Full response: {full_response}")
    logger.debug(f"Tool calls: {tool_calls}")
    message_history.append({"role": "assistant", "content": full_response})
    logger.debug(f"Message history: {message_history}")
    cl.user_session.set("message_history", message_history)
    await msg.update()

    if tool_calls and tools:  # Check if we have any tools and tool calls
        available_functions = {}
        
        # Add Tavily function if available
        if tavily_api_key:
            available_functions["tavily_web_search"] = tavily_web_search
        
        # Add all custom tool functions from globals
        for tool_name in custom_tools_dict:
            if tool_name in globals():
                available_functions[tool_name] = globals()[tool_name]
        messages = message_history + [{"role": "assistant", "content": None, "function_call": {
            "name": tool_calls[0]['function']['name'],
            "arguments": tool_calls[0]['function']['arguments']
        }}]

        for tool_call in tool_calls:
            function_name = tool_call['function']['name']
            if function_name in available_functions:
                function_to_call = available_functions[function_name]
                function_args = tool_call['function']['arguments']
                if function_args:
                    try:
                        function_args = json.loads(function_args)
                        
                        # Call function based on whether it's async or sync
                        if asyncio.iscoroutinefunction(function_to_call):
                            # For async functions like tavily_web_search
                            if function_name == "tavily_web_search":
                                function_response = await function_to_call(
                                    query=function_args.get("query"),
                                )
                            else:
                                # For custom async functions, pass all arguments
                                function_response = await function_to_call(**function_args)
                        else:
                            # For sync functions (most custom tools)
                            function_response = function_to_call(**function_args)
                        
                        # Convert response to string if needed
                        if not isinstance(function_response, str):
                            function_response = json.dumps(function_response)
                        
                        messages.append(
                            {
                                "role": "function",
                                "name": function_name,
                                "content": function_response,
                            }
                        )
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse function arguments: {function_args}")
                    except Exception as e:
                        logger.error(f"Error calling function {function_name}: {str(e)}")
                        messages.append(
                            {
                                "role": "function",
                                "name": function_name,
                                "content": f"Error: {str(e)}",
                            }
                        )

        second_response = await acompletion(
            model=model_name,
            stream=True,
            messages=messages,
        )
        logger.debug(f"Second LLM response: {second_response}")

        full_response = ""
        async for part in second_response:
            if 'choices' in part and len(part['choices']) > 0:
                delta = part['choices'][0].get('delta', {})
                if 'content' in delta and delta['content'] is not None:
                    token = delta['content']
                    await msg.stream_token(token)
                    full_response += token

        msg.content = full_response
        await msg.update()
    else:
        msg.content = full_response
        await msg.update()

@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    logger.info(f"Resuming chat: {thread['id']}")
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    logger.debug(f"Model name: {model_name}")
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini",
                initial=model_name
            )
        ]
    )
    await settings.send()
    thread_id = thread["id"]
    cl.user_session.set("thread_id", thread_id)

    metadata = thread.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    cl.user_session.set("metadata", metadata)

    message_history = cl.user_session.get("message_history", [])
    steps = thread["steps"]

    for m in steps:
        msg_type = m.get("type")
        if msg_type == "user_message":
            message_history.append({"role": "user", "content": m.get("output", "")})
        elif msg_type == "assistant_message":
            message_history.append({"role": "assistant", "content": m.get("output", "")})
        elif msg_type == "run":
            if m.get("isError"):
                message_history.append({"role": "system", "content": f"Error: {m.get('output', '')}"})
        else:
            logger.warning(f"Message without recognized type: {m}")

    cl.user_session.set("message_history", message_history)

    image_data = metadata.get("image")
    if image_data:
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))
        cl.user_session.set("image", image)
        await cl.Message(content="Previous image loaded.").send()
