"""PraisonAI Code - Optimized Chainlit Application

This is the optimized code assistant application with:
- Lazy imports for fast startup
- Agent reuse between messages (persistent agent per session)
- Default ACP/LSP tools with trust mode
- Context gathering optimization (cached per session)
- Profiling hooks (optional via PRAISON_CODE_PROFILE=1)
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
PROFILING_ENABLED = os.getenv("PRAISON_CODE_PROFILE", "").lower() in ("1", "true", "yes")
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

def _get_subprocess():
    if 'subprocess' not in _cached_modules:
        import subprocess
        _cached_modules['subprocess'] = subprocess
    return _cached_modules['subprocess']

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

def _get_context_gatherer():
    if 'ContextGatherer' not in _cached_modules:
        try:
            _profile_start("import_context_gatherer")
            from context import ContextGatherer
            _cached_modules['ContextGatherer'] = ContextGatherer
            _profile_end("import_context_gatherer")
        except ImportError:
            _cached_modules['ContextGatherer'] = None
    return _cached_modules['ContextGatherer']

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
            config.workspace = os.environ.get("PRAISONAI_CODE_REPO_PATH", os.getcwd())
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

# Cached context (expensive to gather on every message)
_cached_context = {}

def _get_cached_context(repo_path: str, force_refresh: bool = False):
    """Get cached context or gather new context."""
    cache_key = repo_path
    
    if not force_refresh and cache_key in _cached_context:
        cached = _cached_context[cache_key]
        # Check if cache is still valid (5 minutes)
        import time
        if time.time() - cached.get('timestamp', 0) < 300:
            return cached['context'], cached['token_count'], cached['context_tree']
    
    ContextGatherer = _get_context_gatherer()
    if ContextGatherer is None:
        return "", 0, ""
    
    _profile_start("gather_context")
    gatherer = ContextGatherer(directory=repo_path)
    context, token_count, context_tree = gatherer.run()
    _profile_end("gather_context")
    
    import time
    _cached_context[cache_key] = {
        'context': context,
        'token_count': token_count,
        'context_tree': context_tree,
        'timestamp': time.time()
    }
    
    return context, token_count, context_tree

# Claude Code Tool Function (lazy subprocess)
async def claude_code_tool(query: str) -> str:
    """Execute Claude Code CLI commands for file modifications and coding tasks."""
    subprocess = _get_subprocess()
    datetime = _get_datetime()
    
    try:
        repo_path = os.environ.get("PRAISONAI_CODE_REPO_PATH", ".")
        
        git_available = False
        try:
            subprocess.run(["git", "status"], cwd=repo_path, capture_output=True, check=True)
            git_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_available = False
        
        claude_cmd = ["claude", "--dangerously-skip-permissions", "-p", query]
        
        user_session_context = cl.user_session.get("claude_code_context", False)
        if user_session_context:
            claude_cmd.insert(1, "--continue")
        
        result = subprocess.run(
            claude_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        cl.user_session.set("claude_code_context", True)
        
        output = result.stdout
        if result.stderr:
            output += f"\n\nErrors:\n{result.stderr}"
        
        if git_available and result.returncode == 0:
            try:
                git_status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                if git_status.stdout.strip():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    branch_name = f"claude-code-{timestamp}"
                    
                    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_path, check=True)
                    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
                    commit_message = f"Claude Code changes: {query[:50]}..."
                    subprocess.run(
                        ["git", "commit", "-m", commit_message],
                        cwd=repo_path,
                        check=True
                    )
                    
                    try:
                        subprocess.run(
                            ["git", "push", "-u", "origin", branch_name],
                            cwd=repo_path,
                            check=True
                        )
                        
                        remote_url = subprocess.run(
                            ["git", "config", "--get", "remote.origin.url"],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if remote_url.returncode == 0:
                            repo_url = remote_url.stdout.strip()
                            if repo_url.endswith(".git"):
                                repo_url = repo_url[:-4]
                            if "github.com" in repo_url:
                                pr_url = f"{repo_url}/compare/main...{branch_name}?quick_pull=1"
                                output += f"\n\n📋 **Pull Request Created:**\n{pr_url}"
                                
                    except subprocess.CalledProcessError:
                        output += f"\n\n🌲 **Branch created:** {branch_name} (push manually if needed)"
                        
            except subprocess.CalledProcessError as e:
                output += f"\n\nGit operations failed: {e}"
        
        return output
        
    except subprocess.TimeoutExpired:
        return "Claude Code execution timed out after 5 minutes."
    except subprocess.CalledProcessError as e:
        return f"Claude Code execution failed: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}"
    except Exception as e:
        return f"Error executing Claude Code: {str(e)}"

# Deferred tool loading
_tavily_client = None

def _get_tavily():
    global _tavily_client
    if _tavily_client is None:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if tavily_api_key:
            TavilyClient = _get_tavily_client()
            if TavilyClient:
                _tavily_client = TavilyClient(api_key=tavily_api_key)
    return _tavily_client

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
def auth_callback(input_username: str, input_password: str):
    if (input_username, input_password) == (expected_username, expected_password):
        return cl.User(
            identifier=input_username, metadata={"role": "ADMIN", "provider": "credentials"}
        )
    else:
        return None

def _get_or_create_agent(model_name: str, tools_enabled: bool = True, claude_code_enabled: bool = False):
    """Get or create a reusable agent for the session."""
    Agent = _get_praisonai_agent()
    if Agent is None:
        return None
    
    # Get cached agent from session
    cached_agent = cl.user_session.get("_cached_agent")
    cached_model = cl.user_session.get("_cached_agent_model")
    cached_claude = cl.user_session.get("_cached_agent_claude")
    
    # Reuse if model and claude setting match
    if cached_agent is not None and cached_model == model_name and cached_claude == claude_code_enabled:
        return cached_agent
    
    # Create new agent with interactive tools
    _profile_start("create_agent")
    tools = []
    if tools_enabled:
        tools = list(_get_interactive_tools())  # Copy to avoid mutation
        # Add Tavily if available
        if os.getenv("TAVILY_API_KEY"):
            tools.append(tavily_web_search)
        # Add Claude Code if enabled
        if claude_code_enabled:
            tools.append(claude_code_tool)
    
    agent = Agent(
        name="PraisonAI Code Assistant",
        instructions="""You are a powerful AI code assistant with access to comprehensive development tools.

Available capabilities:
- **File Operations**: Read, write, create, edit, delete files using ACP tools
- **Code Intelligence**: Find symbols, definitions, references using LSP tools
- **Command Execution**: Run shell commands safely
- **Web Search**: Search the web for documentation and solutions (if Tavily API key is set)
- **Claude Code**: Execute complex coding tasks with Claude Code CLI (if enabled)

When helping with code:
1. Use ACP tools for safe, reviewable file modifications
2. Use LSP tools to understand code structure before making changes
3. Always explain what you're doing and why
4. Test changes when possible

Trust mode is enabled - tool executions are auto-approved for efficiency.""",
        llm=model_name,
        tools=tools if tools else None,
        output="minimal",
    )
    
    # Cache the agent
    cl.user_session.set("_cached_agent", agent)
    cl.user_session.set("_cached_agent_model", model_name)
    cl.user_session.set("_cached_agent_claude", claude_code_enabled)
    _profile_end("create_agent")
    
    return agent

@cl.on_chat_start
async def start():
    _profile_start("on_chat_start")
    _ensure_env_loaded()
    
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    claude_code_enabled = os.getenv("PRAISONAI_CLAUDECODE_ENABLED", "false").lower() == "true"
    if not claude_code_enabled:
        claude_code_enabled = (load_setting("claude_code_enabled") or "false").lower() == "true"
    tools_enabled = (load_setting("tools_enabled") or "true").lower() == "true"
    
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("claude_code_enabled", claude_code_enabled)
    cl.user_session.set("tools_enabled", tools_enabled)
    logger.debug(f"Model name: {model_name}, Claude Code: {claude_code_enabled}, Tools: {tools_enabled}")
    
    # Pre-create agent for faster first response
    _get_or_create_agent(model_name, tools_enabled, claude_code_enabled)
    
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
            ),
            Switch(
                id="claude_code_enabled",
                label="Enable Claude Code (file modifications & coding)",
                initial=claude_code_enabled
            )
        ]
    )
    cl.user_session.set("settings", settings)
    await settings.send()
    
    # Get context info (cached)
    repo_path = os.environ.get("PRAISONAI_CODE_REPO_PATH", ".")
    context, token_count, context_tree = _get_cached_context(repo_path)
    
    # Show loaded tools info
    tools = _get_interactive_tools()
    tool_names = [t.__name__ for t in tools[:5]]
    if len(tools) > 5:
        tool_names.append(f"... and {len(tools) - 5} more")
    
    await cl.Message(
        content=f"🚀 **PraisonAI Code Assistant Ready**\n\n"
                f"**Model:** {model_name}\n"
                f"**Tools:** {len(tools)} loaded ({', '.join(tool_names)})\n"
                f"**Claude Code:** {'Enabled' if claude_code_enabled else 'Disabled'}\n"
                f"**Trust Mode:** Enabled (auto-approve tool executions)\n"
                f"**Context:** {token_count} tokens from workspace\n\n"
                f"**Files in workspace:**\n```\n{context_tree[:500]}{'...' if len(context_tree) > 500 else ''}\n```"
    ).send()
    
    _profile_end("on_chat_start")

@cl.on_settings_update
async def setup_agent(settings):
    json = _get_json()
    logger.debug(settings)
    cl.user_session.set("settings", settings)
    
    model_name = settings["model_name"]
    claude_code_enabled = settings.get("claude_code_enabled", False)
    tools_enabled = settings.get("tools_enabled", True)
    
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("claude_code_enabled", claude_code_enabled)
    cl.user_session.set("tools_enabled", tools_enabled)
    
    # Invalidate cached agent if settings changed
    cached_model = cl.user_session.get("_cached_agent_model")
    cached_claude = cl.user_session.get("_cached_agent_claude")
    if cached_model != model_name or cached_claude != claude_code_enabled:
        cl.user_session.set("_cached_agent", None)
        cl.user_session.set("_cached_agent_model", None)
        cl.user_session.set("_cached_agent_claude", None)

    save_setting("model_name", model_name)
    save_setting("claude_code_enabled", str(claude_code_enabled).lower())
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
            metadata["claude_code_enabled"] = claude_code_enabled
            metadata["tools_enabled"] = tools_enabled
            await cl_data.update_thread(thread_id, metadata=metadata)
            cl.user_session.set("metadata", metadata)

@cl.on_message
async def main(message: cl.Message):
    _profile_start("on_message_total")
    json = _get_json()
    datetime = _get_datetime()
    
    model_name = cl.user_session.get("model_name") or load_setting("model_name") or os.getenv("MODEL_NAME", "gpt-4o-mini")
    claude_code_enabled = cl.user_session.get("claude_code_enabled", False)
    tools_enabled = cl.user_session.get("tools_enabled", True)
    message_history = cl.user_session.get("message_history", [])
    
    repo_path = os.environ.get("PRAISONAI_CODE_REPO_PATH", ".")
    context, token_count, context_tree = _get_cached_context(repo_path)
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

{message.content}

Current Date and Time: {now}

Context:
{context[:8000] if len(context) > 8000 else context}
"""

    if image:
        user_message = f"Image uploaded. {user_message}"

    message_history.append({"role": "user", "content": user_message})
    msg = cl.Message(content="")

    # Try PraisonAI Agent first (faster, with tool reuse)
    agent = _get_or_create_agent(model_name, tools_enabled, claude_code_enabled) if tools_enabled else None
    
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
    io = _get_io()
    base64 = _get_base64()
    acompletion = _get_acompletion()
    
    _profile_start("litellm_response")
    
    # Build tools list
    tools = []
    if os.getenv("TAVILY_API_KEY"):
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
        completion_params["model"] = "gpt-4-vision-preview"

    if tools:
        completion_params["tools"] = tools
        completion_params["tool_choice"] = "auto"

    response = await acompletion(**completion_params)

    full_response = ""
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

    if not msg_sent:
        await msg.send()

    message_history.append({"role": "assistant", "content": full_response})
    cl.user_session.set("message_history", message_history)
    
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
    claude_code_enabled = os.getenv("PRAISONAI_CLAUDECODE_ENABLED", "false").lower() == "true"
    if not claude_code_enabled:
        claude_code_enabled = (load_setting("claude_code_enabled") or "false").lower() == "true"
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
            ),
            Switch(
                id="claude_code_enabled",
                label="Enable Claude Code (file modifications & coding)",
                initial=claude_code_enabled
            )
        ]
    )
    await settings.send()
    
    cl.user_session.set("thread_id", thread["id"])
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("claude_code_enabled", claude_code_enabled)
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
    _get_or_create_agent(model_name, tools_enabled, claude_code_enabled)

    image_data = metadata.get("image")
    if image_data:
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))
        cl.user_session.set("image", image)
        await cl.Message(content="Previous image loaded. You can continue asking questions about it, upload a new image, or just chat.").send()
