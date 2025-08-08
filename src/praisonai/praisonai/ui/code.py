# Standard library imports
import os
from datetime import datetime
import logging
import json
import io
import base64
import asyncio

# Third-party imports
from dotenv import load_dotenv
from PIL import Image
from context import ContextGatherer
from tavily import TavilyClient
from crawl4ai import AsyncWebCrawler
import subprocess

# Local application/library imports
import chainlit as cl
from chainlit.input_widget import TextInput, Switch
from chainlit.types import ThreadDict
import chainlit.data as cl_data
from db import DatabaseManager

# PraisonAI Agents imports
try:
    from praisonaiagents import Agent
    PRAISONAI_AGENTS_AVAILABLE = True
except ImportError:
    PRAISONAI_AGENTS_AVAILABLE = False
    # Fallback to litellm for backward compatibility
    from litellm import acompletion
    import litellm

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger.handlers = []

# Set up logging to console
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Set the logging level for the logger
logger.setLevel(log_level)

# Configure litellm for backward compatibility (only if praisonaiagents not available)
if not PRAISONAI_AGENTS_AVAILABLE:
    import litellm
    litellm.set_verbose = False
    litellm.success_callback = []
    litellm._async_success_callback = []
    litellm.callbacks = []
    litellm.drop_params = True
    litellm.modify_params = True
    litellm.suppress_debug_messages = True

# Claude Code Tool Function
async def claude_code_tool(query: str) -> str:
    """
    Execute Claude Code CLI commands for file modifications and coding tasks.
    
    Args:
        query: The user's request that requires file modifications or coding assistance
        
    Returns:
        The output from Claude Code execution
    """
    try:
        # Check if the current working directory is a git repository
        repo_path = os.environ.get("PRAISONAI_CODE_REPO_PATH", ".")
        
        # Try to detect if git is available and if we're in a git repo
        git_available = False
        try:
            subprocess.run(["git", "status"], cwd=repo_path, capture_output=True, check=True)
            git_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_available = False
        
        # Build Claude Code command
        claude_cmd = ["claude", "--dangerously-skip-permissions", "-p", query]
        
        # Check if it's a continuation (simple heuristic)
        user_session_context = cl.user_session.get("claude_code_context", False)
        if user_session_context:
            claude_cmd.insert(1, "--continue")
        
        # Execute Claude Code command
        result = subprocess.run(
            claude_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        # Set context for future requests
        cl.user_session.set("claude_code_context", True)
        
        output = result.stdout
        if result.stderr:
            output += f"\n\nErrors:\n{result.stderr}"
        
        # If git is available and changes were made, try to create a branch and PR
        if git_available and result.returncode == 0:
            try:
                # Check for changes
                git_status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                if git_status.stdout.strip():
                    # Create a branch for the changes
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    branch_name = f"claude-code-{timestamp}"
                    
                    # Create and switch to new branch
                    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_path, check=True)
                    
                    # Add and commit changes
                    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
                    commit_message = f"Claude Code changes: {query[:50]}..."
                    subprocess.run(
                        ["git", "commit", "-m", commit_message],
                        cwd=repo_path,
                        check=True
                    )
                    
                    # Push to remote (if configured)
                    try:
                        subprocess.run(
                            ["git", "push", "-u", "origin", branch_name],
                            cwd=repo_path,
                            check=True
                        )
                        
                        # Generate PR URL (assuming GitHub)
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

CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

if not CHAINLIT_AUTH_SECRET:
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"
    CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

now = datetime.now()
create_step_counter = 0

# Initialize database
db_manager = DatabaseManager()
db_manager.initialize()

deleted_thread_ids = []  # type: List[str]

def _build_completion_params(model_name, **override_params):
    """Build parameters for litellm completion calls with proper model handling"""
    params = {
        "model": model_name,
    }
    
    # Override with any provided parameters
    params.update(override_params)
    
    return params

def save_setting(key: str, value: str):
    """Saves a setting to the database.
    
    Args:
        key: The setting key.
        value: The setting value.
    """
    asyncio.run(db_manager.save_setting(key, value))

def load_setting(key: str) -> str:
    """Loads a setting from the database.
    
    Args:
        key: The setting key.
    
    Returns:
        The setting value, or None if the key is not found.
    """
    return asyncio.run(db_manager.load_setting(key))

cl_data._data_layer = db_manager

@cl.on_chat_start
async def start():
    model_name = load_setting("model_name") 

    if (model_name):
        cl.user_session.set("model_name", model_name)
    else:
        # If no setting found, use default or environment variable
        model_name = os.getenv("MODEL_NAME", "gpt-5-nano")
        cl.user_session.set("model_name", model_name)
    logger.debug(f"Model name: {model_name}")
    
    # Load Claude Code setting (check CLI flag first, then database setting)
    claude_code_enabled = os.getenv("PRAISONAI_CLAUDECODE_ENABLED", "false").lower() == "true"
    if not claude_code_enabled:
        claude_code_enabled = (load_setting("claude_code_enabled") or "false").lower() == "true"
    
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-5-nano",
                initial=model_name
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
    repo_path_to_use = os.environ.get("PRAISONAI_CODE_REPO_PATH", ".")
    gatherer = ContextGatherer(directory=repo_path_to_use)
    context, token_count, context_tree = gatherer.run()
    msg = cl.Message(content="""Token Count: {token_count},
                                 Files include: \n```bash\n{context_tree}\n"""
                                 .format(token_count=token_count, context_tree=context_tree))
    await msg.send()

@cl.on_settings_update
async def setup_agent(settings):
    logger.debug(settings)
    cl.user_session.set("settings", settings)
    model_name = settings["model_name"]
    claude_code_enabled = settings.get("claude_code_enabled", False)
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("claude_code_enabled", claude_code_enabled)
    
    # Save in settings table
    save_setting("model_name", model_name)
    save_setting("claude_code_enabled", str(claude_code_enabled).lower())
    
    # Save in thread metadata
    thread_id = cl.user_session.get("thread_id")
    if thread_id:
        thread = await cl_data._data_layer.get_thread(thread_id)
        if thread:
            metadata = thread.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = {}
            
            metadata["model_name"] = model_name
            metadata["claude_code_enabled"] = claude_code_enabled
            
            # Always store metadata as a dictionary
            await cl_data._data_layer.update_thread(thread_id, metadata=metadata)
            
            # Update the user session with the new metadata
            cl.user_session.set("metadata", metadata)

# Set Tavily API key
tavily_api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=tavily_api_key) if tavily_api_key else None

# Function to call Tavily Search API and crawl the results
async def tavily_web_search(query):
    if not tavily_client:
        return json.dumps({
            "query": query,
            "error": "Tavily API key is not set. Web search is unavailable."
        })
    
    response = tavily_client.search(query)
    logger.debug(f"Tavily search response: {response}")

    # Create an instance of AsyncAsyncWebCrawler
    async with AsyncAsyncWebCrawler() as crawler:
        # Prepare the results
        results = []
        for result in response.get('results', []):
            url = result.get('url')
            if url:
                try:
                    # Run the crawler asynchronously on each URL
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

# Define the tool for function calling
tools = [{
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
}] if tavily_api_key else []

@cl.on_message
async def main(message: cl.Message):
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-5-nano"
    claude_code_enabled = cl.user_session.get("claude_code_enabled", False)
    message_history = cl.user_session.get("message_history", [])
    repo_path_to_use = os.environ.get("PRAISONAI_CODE_REPO_PATH", ".")
    gatherer = ContextGatherer(directory=repo_path_to_use)
    context, token_count, context_tree = gatherer.run()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Check if an image was uploaded with this message
    image = None
    if message.elements and isinstance(message.elements[0], cl.Image):
        image_element = message.elements[0]
        try:
            # Open the image and keep it in memory
            image = Image.open(image_element.path)
            image.load()  # This ensures the file is fully loaded into memory
            cl.user_session.set("image", image)
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            await cl.Message(content="There was an error processing the uploaded image. Please try again.").send()
            return

    # Prepare user message
    user_message = f"""
Answer the question and use tools if needed:\n{message.content}.\n\n
Current Date and Time: {now}

Context:
{context}
"""

    if image:
        user_message = f"Image uploaded. {user_message}"

    message_history.append({"role": "user", "content": user_message})

    msg = cl.Message(content="")
    await msg.send()

    # Use PraisonAI Agents if available, otherwise fallback to litellm
    if PRAISONAI_AGENTS_AVAILABLE:
        await handle_with_praisonai_agents(message, user_message, model_name, claude_code_enabled, msg, image)
    else:
        await handle_with_litellm(user_message, model_name, message_history, msg, image)

async def handle_with_praisonai_agents(message, user_message, model_name, claude_code_enabled, msg, image):
    """Handle message using PraisonAI Agents framework with optional Claude Code tool"""
    try:
        # Prepare tools list
        available_tools = []
        
        # Add Tavily search tool if API key available
        if tavily_api_key:
            available_tools.append(tavily_web_search)
        
        # Add Claude Code tool if enabled
        if claude_code_enabled:
            available_tools.append(claude_code_tool)
        
        # Create agent instructions
        instructions = """You are a helpful AI assistant. Use the available tools when needed to provide comprehensive responses.
        
If Claude Code tool is available and the user's request involves:
- File modifications, code changes, or implementation tasks
- Creating, editing, or debugging code
- Project setup or development tasks
- Git operations or version control

Then use the Claude Code tool to handle those requests.

For informational questions, explanations, or general conversations, respond normally without using Claude Code."""

        # Create agent
        agent = Agent(
            name="PraisonAI Assistant",
            instructions=instructions,
            llm=model_name,
            tools=available_tools if available_tools else None
        )
        
        # Execute agent with streaming
        full_response = ""
        
        # Use agent's streaming capabilities if available
        try:
            # For now, use synchronous execution and stream the result
            # TODO: Implement proper streaming when PraisonAI agents support it
            result = agent.start(user_message)
            
            # Stream the response character by character for better UX
            if hasattr(result, 'raw'):
                response_text = result.raw
            else:
                response_text = str(result)
            
            for char in response_text:
                await msg.stream_token(char)
                full_response += char
                # Small delay to make streaming visible
                await asyncio.sleep(0.01)
            
        except Exception as e:
            error_response = f"Error executing agent: {str(e)}"
            for char in error_response:
                await msg.stream_token(char)
                full_response += char
                await asyncio.sleep(0.01)
        
        msg.content = full_response
        await msg.update()
        
    except Exception as e:
        error_msg = f"Failed to use PraisonAI Agents: {str(e)}"
        logger.error(error_msg)
        await msg.stream_token(error_msg)
        msg.content = error_msg
        await msg.update()

async def handle_with_litellm(user_message, model_name, message_history, msg, image):
    """Fallback handler using litellm for backward compatibility"""
    # Prepare the completion parameters using the helper function
    completion_params = _build_completion_params(
        model_name,
        messages=message_history,
        stream=True,
    )

    # If an image is uploaded, include it in the message
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
        # Use a vision-capable model when an image is present
        completion_params["model"] = "gpt-4-vision-preview"

    # Only add tools and tool_choice if Tavily API key is available and no image is uploaded
    if tavily_api_key:
        completion_params["tools"] = tools
        completion_params["tool_choice"] = "auto"

    response = await acompletion(**completion_params)
    logger.debug(f"LLM response: {response}")

    full_response = ""
    tool_calls = []
    current_tool_call = None

    async for part in response:
        logger.debug(f"LLM part: {part}")
        if 'choices' in part and len(part['choices']) > 0:
            delta = part['choices'][0].get('delta', {})
            
            if 'content' in delta and delta['content'] is not None:
                token = delta['content']
                await msg.stream_token(token)
                full_response += token
            
            if tavily_api_key and 'tool_calls' in delta and delta['tool_calls'] is not None:
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

    if tavily_api_key and tool_calls:
        available_functions = {
            "tavily_web_search": tavily_web_search,
        }
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
                        # Call the function asynchronously
                        function_response = await function_to_call(
                            query=function_args.get("query"),
                        )
                        messages.append(
                            {
                                "role": "function",
                                "name": function_name,
                                "content": function_response,
                            }
                        )
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse function arguments: {function_args}")

        second_response = await acompletion(
            **_build_completion_params(
                model_name,
                stream=True,
                messages=messages,
            )
        )
        logger.debug(f"Second LLM response: {second_response}")

        # Handle the streaming response
        full_response = ""
        async for part in second_response:
            if 'choices' in part and len(part['choices']) > 0:
                delta = part['choices'][0].get('delta', {})
                if 'content' in delta and delta['content'] is not None:
                    token = delta['content']
                    await msg.stream_token(token)
                    full_response += token

        # Update the message content
        msg.content = full_response
        await msg.update()
    else:
        # If no tool calls or Tavily API key is not set, the full_response is already set
        msg.content = full_response
        await msg.update()

username = os.getenv("CHAINLIT_USERNAME", "admin")  # Default to "admin" if not found
password = os.getenv("CHAINLIT_PASSWORD", "admin")  # Default to "admin" if not found

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    if (username, password) == (username, password):
        return cl.User(
            identifier=username, metadata={"role": "ADMIN", "provider": "credentials"}
        )
    else:
        return None

async def send_count():
    await cl.Message(
        f"Create step counter: {create_step_counter}", disable_feedback=True
    ).send()

@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    logger.info(f"Resuming chat: {thread['id']}")
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-5-nano"
    # Load Claude Code setting (check CLI flag first, then database setting)
    claude_code_enabled = os.getenv("PRAISONAI_CLAUDECODE_ENABLED", "false").lower() == "true"
    if not claude_code_enabled:
        claude_code_enabled = (load_setting("claude_code_enabled") or "false").lower() == "true"
    logger.debug(f"Model name: {model_name}")
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-5-nano",
                initial=model_name
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
    
    # Ensure metadata is a dictionary
    metadata = thread.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    
    cl.user_session.set("metadata", metadata)
    
    message_history = cl.user_session.get("message_history", [])
    steps = thread["steps"]

    for message in steps:
        msg_type = message.get("type")
        if msg_type == "user_message":
            message_history.append({"role": "user", "content": message.get("output", "")})
        elif msg_type == "assistant_message":
            message_history.append({"role": "assistant", "content": message.get("output", "")})
        elif msg_type == "run":
            # Handle 'run' type messages
            if message.get("isError"):
                message_history.append({"role": "system", "content": f"Error: {message.get('output', '')}"})
            else:
                # You might want to handle non-error 'run' messages differently
                pass
        else:
            logger.warning(f"Message without recognized type: {message}")

    cl.user_session.set("message_history", message_history)

    # Check if there's an image in the thread metadata
    image_data = metadata.get("image")
    if image_data:
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))
        cl.user_session.set("image", image)
        await cl.Message(content="Previous image loaded. You can continue asking questions about it, upload a new image, or just chat.").send()