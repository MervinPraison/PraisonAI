"""PraisonAI Chat - Optimized Chainlit Application

This is the optimized chat application with:
- Lazy imports for fast startup
- Agent reuse between messages (persistent agent per session)
- Default ACP/LSP tools with trust mode
- Session management
- Profiling hooks (optional via PRAISON_CHAT_PROFILE=1)

Performance improvements over original chat.py:
- Deferred database initialization
- Lazy loading of PIL, Tavily, crawl4ai, litellm
- Agent reuse (no re-creation per message)
- Interactive tools loaded once per session
"""

# Standard library imports (minimal at top level)
import os
import logging

# Set up minimal logging first
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper() or "INFO"
logger.handlers = []
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)
logger.setLevel(log_level)

# Chainlit must be imported early (required by decorators)
import chainlit as cl
from chainlit.input_widget import TextInput, Switch
from chainlit.types import ThreadDict
import chainlit.data as cl_data

# Profiling support (optional)
PROFILING_ENABLED = os.getenv("PRAISON_CHAT_PROFILE", "").lower() in ("1", "true", "yes")
_profile_data = {}

def _profile_start(name: str):
    """Start profiling a section."""
    if PROFILING_ENABLED:
        import time
        _profile_data[name] = {"start": time.perf_counter()}

def _profile_end(name: str):
    """End profiling a section and log."""
    if PROFILING_ENABLED and name in _profile_data:
        import time
        elapsed = time.perf_counter() - _profile_data[name]["start"]
        _profile_data[name]["elapsed"] = elapsed
        logger.info(f"[PROFILE] {name}: {elapsed*1000:.2f}ms")

# Lazy import cache
_cached_modules = {}

def _get_json():
    if 'json' not in _cached_modules:
        import json
        _cached_modules['json'] = json
    return _cached_modules['json']

def _get_asyncio():
    if 'asyncio' not in _cached_modules:
        import asyncio
        _cached_modules['asyncio'] = asyncio
    return _cached_modules['asyncio']

def _get_datetime():
    if 'datetime' not in _cached_modules:
        from datetime import datetime
        _cached_modules['datetime'] = datetime
    return _cached_modules['datetime']

def _get_io():
    if 'io' not in _cached_modules:
        import io
        _cached_modules['io'] = io
    return _cached_modules['io']

def _get_base64():
    if 'base64' not in _cached_modules:
        import base64
        _cached_modules['base64'] = base64
    return _cached_modules['base64']

def _get_importlib():
    if 'importlib' not in _cached_modules:
        import importlib.util
        _cached_modules['importlib'] = importlib
    return _cached_modules['importlib']

def _get_inspect():
    if 'inspect' not in _cached_modules:
        import inspect
        _cached_modules['inspect'] = inspect
    return _cached_modules['inspect']

def _get_pil_image():
    if 'PIL.Image' not in _cached_modules:
        _profile_start("import_pil")
        from PIL import Image
        _cached_modules['PIL.Image'] = Image
        _profile_end("import_pil")
    return _cached_modules['PIL.Image']

def _get_acompletion():
    if 'acompletion' not in _cached_modules:
        _profile_start("import_litellm")
        from litellm import acompletion
        _cached_modules['acompletion'] = acompletion
        _profile_end("import_litellm")
    return _cached_modules['acompletion']

def _get_tavily_client():
    if 'TavilyClient' not in _cached_modules:
        try:
            _profile_start("import_tavily")
            from tavily import TavilyClient
            _cached_modules['TavilyClient'] = TavilyClient
            _profile_end("import_tavily")
        except ImportError:
            _cached_modules['TavilyClient'] = None
    return _cached_modules['TavilyClient']

def _get_async_web_crawler():
    if 'AsyncWebCrawler' not in _cached_modules:
        try:
            _profile_start("import_crawl4ai")
            from crawl4ai import AsyncWebCrawler
            _cached_modules['AsyncWebCrawler'] = AsyncWebCrawler
            _profile_end("import_crawl4ai")
        except ImportError:
            _cached_modules['AsyncWebCrawler'] = None
    return _cached_modules['AsyncWebCrawler']

def _get_praisonai_agent():
    """Lazy load PraisonAI Agent for reuse."""
    if 'Agent' not in _cached_modules:
        try:
            _profile_start("import_praisonai_agent")
            from praisonaiagents import Agent
            _cached_modules['Agent'] = Agent
            _profile_end("import_praisonai_agent")
        except ImportError:
            _cached_modules['Agent'] = None
    return _cached_modules['Agent']

def _get_interactive_tools():
    """Lazy load interactive tools (ACP, LSP, basic) with trust mode."""
    if 'interactive_tools' not in _cached_modules:
        try:
            _profile_start("load_interactive_tools")
            from praisonai.cli.features.interactive_tools import get_interactive_tools, ToolConfig
            config = ToolConfig.from_env()
            config.workspace = os.getcwd()
            config.approval_mode = "auto"  # Trust mode - auto-approve all tool executions
            tools = get_interactive_tools(config=config)
            _cached_modules['interactive_tools'] = tools
            _profile_end("load_interactive_tools")
            logger.info(f"Loaded {len(tools)} interactive tools (ACP, LSP, basic) with trust mode")
        except ImportError as e:
            logger.debug(f"Interactive tools not available: {e}")
            _cached_modules['interactive_tools'] = []
    return _cached_modules['interactive_tools']

# Deferred database initialization
_db_manager = None

def _get_db_manager():
    """Lazy initialize database manager."""
    global _db_manager
    if _db_manager is None:
        _profile_start("init_database")
        # Import from the same directory as this module
        import sys
        ui_dir = os.path.dirname(os.path.abspath(__file__))
        if ui_dir not in sys.path:
            sys.path.insert(0, ui_dir)
        from db import DatabaseManager
        _db_manager = DatabaseManager()
        _db_manager.initialize()
        cl_data._data_layer = _db_manager
        _profile_end("init_database")
    return _db_manager

# Load environment variables lazily
def _ensure_env_loaded():
    if 'env_loaded' not in _cached_modules:
        from dotenv import load_dotenv
        load_dotenv()
        _cached_modules['env_loaded'] = True

# Auth secret setup (required early)
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")
if not CHAINLIT_AUTH_SECRET:
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"
    CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

def save_setting(key: str, value: str):
    """Save a setting to the database"""
    asyncio = _get_asyncio()
    db_manager = _get_db_manager()
    asyncio.run(db_manager.save_setting(key, value))

def load_setting(key: str) -> str:
    """Load a setting from the database"""
    asyncio = _get_asyncio()
    db_manager = _get_db_manager()
    return asyncio.run(db_manager.load_setting(key))

def load_custom_tools():
    """Load custom tools from tools.py if it exists."""
    custom_tools = {}
    importlib = _get_importlib()
    inspect = _get_inspect()
    
    tools_path = os.getenv("PRAISONAI_TOOLS_PATH")
    if tools_path:
        if not os.path.exists(tools_path):
            logger.warning(f"PRAISONAI_TOOLS_PATH set but path does not exist: {tools_path}")
            return custom_tools
    else:
        cwd_tools = os.path.join(os.getcwd(), "tools.py")
        if os.path.exists(cwd_tools):
            tools_path = cwd_tools
        else:
            logger.debug("No tools.py found in current directory (this is normal)")
            return custom_tools
    
    try:
        spec = importlib.util.spec_from_file_location("tools", tools_path)
        if spec is None or spec.loader is None:
            logger.debug(f"Could not load tools from {tools_path}")
            return custom_tools
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        for name, obj in inspect.getmembers(module):
            if not name.startswith('_') and callable(obj) and not inspect.isclass(obj):
                globals()[name] = obj
                
                sig = inspect.signature(obj)
                params_properties = {}
                required_params = []
                
                for param_name, param in sig.parameters.items():
                    if param_name != 'self':
                        param_type = "string"
                        if param.annotation is not inspect.Parameter.empty:
                            if param.annotation is int:
                                param_type = "integer"
                            elif param.annotation is float:
                                param_type = "number"
                            elif param.annotation is bool:
                                param_type = "boolean"
                        
                        params_properties[param_name] = {
                            "type": param_type,
                            "description": f"Parameter {param_name}"
                        }
                        
                        if param.default is inspect.Parameter.empty:
                            required_params.append(param_name)
                
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
        
        if custom_tools:
            logger.info(f"Loaded {len(custom_tools)} custom tools from {tools_path}")
    except FileNotFoundError:
        logger.debug(f"Tools file not found: {tools_path}")
    except Exception as e:
        logger.warning(f"Error loading custom tools from {tools_path}: {e}")
    
    return custom_tools

# Deferred tool loading
_custom_tools_dict = None
_tavily_client = None
_tools_list = None

def _get_custom_tools():
    global _custom_tools_dict
    if _custom_tools_dict is None:
        _custom_tools_dict = load_custom_tools()
    return _custom_tools_dict

def _get_tavily():
    global _tavily_client
    if _tavily_client is None:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if tavily_api_key:
            TavilyClient = _get_tavily_client()
            if TavilyClient:
                _tavily_client = TavilyClient(api_key=tavily_api_key)
    return _tavily_client

def _get_tools_list():
    """Get the combined tools list (Tavily + custom tools)."""
    global _tools_list
    if _tools_list is None:
        _tools_list = []
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if tavily_api_key:
            _tools_list.append({
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
        custom_tools = _get_custom_tools()
        _tools_list.extend(list(custom_tools.values()))
    return _tools_list

async def tavily_web_search(query):
    """Search the web using Tavily API."""
    json = _get_json()
    tavily_client = _get_tavily()
    
    if not tavily_client:
        return json.dumps({
            "query": query,
            "error": "Tavily API key is not set. Web search is unavailable."
        })

    response = tavily_client.search(query)
    logger.debug(f"Tavily search response: {response}")

    AsyncWebCrawler = _get_async_web_crawler()
    if AsyncWebCrawler:
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
    else:
        results = [{"content": r.get('content'), "url": r.get('url')} for r in response.get('results', [])]

    return json.dumps({
        "query": query,
        "results": results
    })

# Authentication configuration
expected_username = os.getenv("CHAINLIT_USERNAME", "admin")
expected_password = os.getenv("CHAINLIT_PASSWORD", "admin")

if expected_username == "admin" and expected_password == "admin":
    logger.warning("⚠️  Using default admin credentials. Set CHAINLIT_USERNAME and CHAINLIT_PASSWORD environment variables for production.")

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    logger.debug(f"Auth attempt: username='{username}', expected='{expected_username}'")
    if (username, password) == (expected_username, expected_password):
        logger.info(f"Login successful for user: {username}")
        return cl.User(identifier=username, metadata={"role": "admin", "provider": "credentials"})
    else:
        logger.warning(f"Login failed for user: {username}")
        return None

def _get_or_create_agent(model_name: str, tools_enabled: bool = True):
    """Get or create a reusable agent for the session."""
    Agent = _get_praisonai_agent()
    if Agent is None:
        return None
    
    # Get cached agent from session
    cached_agent = cl.user_session.get("_cached_agent")
    cached_model = cl.user_session.get("_cached_agent_model")
    
    # Reuse if model matches
    if cached_agent is not None and cached_model == model_name:
        return cached_agent
    
    # Create new agent with interactive tools
    _profile_start("create_agent")
    tools = []
    if tools_enabled:
        tools = _get_interactive_tools()
        # Add Tavily if available
        if os.getenv("TAVILY_API_KEY"):
            tools.append(tavily_web_search)
    
    agent = Agent(
        name="PraisonAI Assistant",
        instructions="""You are a helpful AI assistant with access to powerful tools.

Available capabilities:
- File operations (read, write, create, edit, delete files)
- Code intelligence (find symbols, definitions, references)
- Command execution (run shell commands)
- Web search (if Tavily API key is set)

Use tools when needed to help the user. For file modifications, use the ACP tools which provide safe, reviewable changes.
Always be helpful, accurate, and concise.""",
        llm=model_name,
        tools=tools if tools else None,
        output="minimal",
    )
    
    # Cache the agent
    cl.user_session.set("_cached_agent", agent)
    cl.user_session.set("_cached_agent_model", model_name)
    _profile_end("create_agent")
    
    return agent

@cl.on_chat_start
async def start():
    _profile_start("on_chat_start")
    _ensure_env_loaded()
    
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    tools_enabled = (load_setting("tools_enabled") or "true").lower() == "true"
    
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("tools_enabled", tools_enabled)
    logger.debug(f"Model name: {model_name}, Tools enabled: {tools_enabled}")
    
    # Pre-create agent for faster first response
    _get_or_create_agent(model_name, tools_enabled)
    
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini",
                initial=model_name
            ),
            Switch(
                id="tools_enabled",
                label="Enable Tools (ACP, LSP, Web Search)",
                initial=tools_enabled
            )
        ]
    )
    cl.user_session.set("settings", settings)
    await settings.send()
    
    # Show loaded tools info
    tools = _get_interactive_tools()
    tool_names = [t.__name__ for t in tools[:5]]
    if len(tools) > 5:
        tool_names.append(f"... and {len(tools) - 5} more")
    
    await cl.Message(
        content=f"🚀 **PraisonAI Chat Ready**\n\n"
                f"**Model:** {model_name}\n"
                f"**Tools:** {len(tools)} loaded ({', '.join(tool_names)})\n"
                f"**Trust Mode:** Enabled (auto-approve tool executions)\n\n"
                f"Type your message to get started!"
    ).send()
    
    _profile_end("on_chat_start")

@cl.on_settings_update
async def setup_agent(settings):
    json = _get_json()
    logger.debug(settings)
    cl.user_session.set("settings", settings)
    
    model_name = settings["model_name"]
    tools_enabled = settings.get("tools_enabled", True)
    
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("tools_enabled", tools_enabled)
    
    # Invalidate cached agent if model changed
    cached_model = cl.user_session.get("_cached_agent_model")
    if cached_model != model_name:
        cl.user_session.set("_cached_agent", None)
        cl.user_session.set("_cached_agent_model", None)

    save_setting("model_name", model_name)
    save_setting("tools_enabled", str(tools_enabled).lower())

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
            metadata["tools_enabled"] = tools_enabled
            await cl_data.update_thread(thread_id, metadata=metadata)
            cl.user_session.set("metadata", metadata)

@cl.on_message
async def main(message: cl.Message):
    _profile_start("on_message_total")
    json = _get_json()
    asyncio = _get_asyncio()
    datetime = _get_datetime()
    
    model_name = cl.user_session.get("model_name") or load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    tools_enabled = cl.user_session.get("tools_enabled", True)
    message_history = cl.user_session.get("message_history", [])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Handle image uploads
    image = None
    if message.elements and isinstance(message.elements[0], cl.Image):
        Image = _get_pil_image()
        image_element = message.elements[0]
        try:
            image = Image.open(image_element.path)
            image.load()
            cl.user_session.set("image", image)
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            await cl.Message(content="Error processing the image. Please try again.").send()
            return

    user_message = f"""Answer the question and use tools if needed:

Current Date and Time: {now}

User Question: {message.content}
"""

    if image:
        user_message = f"Image uploaded. {user_message}"

    message_history.append({"role": "user", "content": user_message})
    msg = cl.Message(content="")

    # Try PraisonAI Agent first (faster, with tool reuse)
    agent = _get_or_create_agent(model_name, tools_enabled) if tools_enabled else None
    
    if agent is not None:
        _profile_start("agent_response")
        await msg.send()
        
        try:
            # Use async chat for streaming
            result = await agent.achat(message.content)
            
            # Get response text
            if hasattr(result, 'raw'):
                response_text = result.raw
            else:
                response_text = str(result)
            
            # Stream in word chunks for better UX
            words = response_text.split(' ')
            for i, word in enumerate(words):
                token = word + (' ' if i < len(words) - 1 else '')
                await msg.stream_token(token)
            
            msg.content = response_text
            await msg.update()
            
            message_history.append({"role": "assistant", "content": response_text})
            cl.user_session.set("message_history", message_history)
            
        except Exception as e:
            logger.error(f"Agent error: {e}")
            # Fallback to litellm
            await _handle_with_litellm(message, user_message, model_name, message_history, msg, image)
        
        _profile_end("agent_response")
    else:
        # Fallback to litellm
        await _handle_with_litellm(message, user_message, model_name, message_history, msg, image)
    
    _profile_end("on_message_total")

async def _handle_with_litellm(message, user_message, model_name, message_history, msg, image):
    """Fallback handler using litellm for backward compatibility."""
    json = _get_json()
    asyncio = _get_asyncio()
    io = _get_io()
    base64 = _get_base64()
    acompletion = _get_acompletion()
    tools = _get_tools_list()
    
    _profile_start("litellm_response")
    
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

    if tools:
        completion_params["tools"] = tools
        completion_params["tool_choice"] = "auto"

    response = await acompletion(**completion_params)

    full_response = ""
    tool_calls = []
    current_tool_call = None
    msg_sent = False

    async for part in response:
        if 'choices' in part and len(part['choices']) > 0:
            delta = part['choices'][0].get('delta', {})

            if 'content' in delta and delta['content'] is not None:
                token = delta['content']
                if not msg_sent:
                    await msg.send()
                    msg_sent = True
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

    if not msg_sent:
        await msg.send()

    message_history.append({"role": "assistant", "content": full_response})
    cl.user_session.set("message_history", message_history)
    await msg.update()

    # Handle tool calls
    if tool_calls and tools:
        custom_tools = _get_custom_tools()
        available_functions = {}
        
        if os.getenv("TAVILY_API_KEY"):
            available_functions["tavily_web_search"] = tavily_web_search
        
        for tool_name in custom_tools:
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
                        
                        if asyncio.iscoroutinefunction(function_to_call):
                            if function_name == "tavily_web_search":
                                function_response = await function_to_call(query=function_args.get("query"))
                            else:
                                function_response = await function_to_call(**function_args)
                        else:
                            function_response = function_to_call(**function_args)
                        
                        if not isinstance(function_response, str):
                            function_response = json.dumps(function_response)
                        
                        messages.append({
                            "role": "function",
                            "name": function_name,
                            "content": function_response,
                        })
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse function arguments: {function_args}")
                    except Exception as e:
                        logger.error(f"Error calling function {function_name}: {str(e)}")
                        messages.append({
                            "role": "function",
                            "name": function_name,
                            "content": f"Error: {str(e)}",
                        })

        second_response = await acompletion(
            model=model_name,
            stream=True,
            messages=messages,
        )

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
    
    _profile_end("litellm_response")

@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    json = _get_json()
    io = _get_io()
    base64 = _get_base64()
    Image = _get_pil_image()
    
    logger.info(f"Resuming chat: {thread['id']}")
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    tools_enabled = (load_setting("tools_enabled") or "true").lower() == "true"
    
    logger.debug(f"Model name: {model_name}")
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini",
                initial=model_name
            ),
            Switch(
                id="tools_enabled",
                label="Enable Tools (ACP, LSP, Web Search)",
                initial=tools_enabled
            )
        ]
    )
    await settings.send()
    
    cl.user_session.set("thread_id", thread["id"])
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("tools_enabled", tools_enabled)

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
    
    # Pre-create agent for faster first response
    _get_or_create_agent(model_name, tools_enabled)

    image_data = metadata.get("image")
    if image_data:
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))
        cl.user_session.set("image", image)
        await cl.Message(content="Previous image loaded.").send()
