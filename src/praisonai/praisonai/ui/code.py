# Standard library imports
import os
from datetime import datetime
import logging
import json
import io
import base64
import asyncio
import subprocess
import tempfile
import re
import shutil

# Third-party imports
from dotenv import load_dotenv
from PIL import Image
from context import ContextGatherer
from tavily import TavilyClient
from crawl4ai import AsyncWebCrawler

# Local application/library imports
import chainlit as cl
from chainlit.input_widget import TextInput
from chainlit.types import ThreadDict
import chainlit.data as cl_data
from litellm import acompletion
import litellm
from db import DatabaseManager

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

# Configure litellm same as in llm.py
litellm.set_verbose = False
litellm.success_callback = []
litellm._async_success_callback = []
litellm.callbacks = []
litellm.drop_params = True
litellm.modify_params = True
litellm.suppress_debug_messages = True

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
        model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")
        cl.user_session.set("model_name", model_name)
    logger.debug(f"Model name: {model_name}")
    
    # Load Claude Code setting
    claude_code_enabled = load_setting("claude_code_enabled")
    if claude_code_enabled is None:
        claude_code_enabled = str(CLAUDE_CODE_ENABLED).lower()
    else:
        claude_code_enabled = claude_code_enabled.lower()
    
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini",
                initial=model_name
            ),
            cl.input_widget.Switch(
                id="claude_code_enabled",
                label="Enable Claude Code (file modifications & git operations)",
                initial=claude_code_enabled == "true"
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
    cl.user_session.set("model_name", model_name)
    
    # Handle Claude Code setting
    claude_code_enabled = settings.get("claude_code_enabled", False)
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
            
            # Always store metadata as a dictionary
            await cl_data._data_layer.update_thread(thread_id, metadata=metadata)
            
            # Update the user session with the new metadata
            cl.user_session.set("metadata", metadata)

# Set Tavily API key
tavily_api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=tavily_api_key) if tavily_api_key else None

# Claude Code configuration
CLAUDE_CODE_ENABLED = os.getenv("CLAUDE_CODE_ENABLED", "true").lower() == "true"
CLAUDE_EXECUTABLE = shutil.which("claude") or "claude"

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

def should_use_claude_code(message_content: str) -> bool:
    """
    Determine if the message requires Claude Code for file modifications or git operations.
    """
    # Check user session setting first, fall back to environment variable
    user_claude_enabled = cl.user_session.get("claude_code_enabled")
    if user_claude_enabled is None:
        claude_enabled = CLAUDE_CODE_ENABLED
    else:
        claude_enabled = user_claude_enabled
        
    if not claude_enabled:
        return False
    
    # Keywords that indicate file modification intent
    modification_keywords = [
        "create", "modify", "update", "edit", "change", "fix", "implement", 
        "add", "remove", "delete", "refactor", "write", "generate",
        "build", "install", "setup", "configure", "deploy"
    ]
    
    # Keywords that indicate git operations
    git_keywords = [
        "commit", "branch", "git", "pull request", "pr", "merge", "push"
    ]
    
    # File operation keywords
    file_keywords = [
        "file", "files", "code", "script", "function", "class", "module",
        "package", "library", "component", "feature"
    ]
    
    message_lower = message_content.lower()
    
    # Check for explicit requests
    explicit_requests = [
        "modify the", "create a", "update the", "fix the", "implement",
        "add a", "remove the", "delete the", "write a", "generate a"
    ]
    
    for request in explicit_requests:
        if request in message_lower:
            return True
    
    # Check for combination of modification + file keywords
    has_modification = any(keyword in message_lower for keyword in modification_keywords)
    has_file_ref = any(keyword in message_lower for keyword in file_keywords)
    has_git = any(keyword in message_lower for keyword in git_keywords)
    
    return (has_modification and has_file_ref) or has_git

async def execute_claude_code(message_content: str, repo_path: str, continue_conversation: bool = False) -> str:
    """
    Execute Claude Code CLI with appropriate flags and return the output.
    """
    try:
        # Check if git repo exists, create branch if needed
        git_available = await check_and_setup_git(repo_path)
        
        # Build Claude Code command
        cmd = [CLAUDE_EXECUTABLE]
        
        # Add flags
        cmd.extend(["--dangerously-skip-permissions"])
        
        if continue_conversation:
            cmd.extend(["--continue"])
        
        # Add the message
        cmd.extend(["-p", message_content])
        
        logger.info(f"Executing Claude Code: {' '.join(cmd)}")
        
        # Execute Claude Code
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            text=True
        )
        
        output = ""
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line_text = line.decode() if isinstance(line, bytes) else line
            output += line_text
            
        await process.wait()
        
        # If git is available and changes were made, create PR
        if git_available and process.returncode == 0:
            pr_url = await create_pull_request(repo_path, message_content)
            if pr_url:
                output += f"\n\n🔗 Pull Request created: {pr_url}"
        
        return output
        
    except Exception as e:
        logger.error(f"Error executing Claude Code: {str(e)}")
        return f"Error executing Claude Code: {str(e)}"

async def check_and_setup_git(repo_path: str) -> bool:
    """
    Check if git repo exists and setup branch if needed.
    """
    try:
        # Check if git repo exists
        git_check = await asyncio.create_subprocess_exec(
            "git", "status",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await git_check.wait()
        
        if git_check.returncode != 0:
            logger.info("No git repository found, continuing without git operations")
            return False
        
        # Create a new branch for the changes
        branch_name = f"claude-code-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Check if we're already on a branch that's not main
        current_branch = await asyncio.create_subprocess_exec(
            "git", "branch", "--show-current",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await current_branch.wait()
        
        if current_branch.returncode == 0:
            current = current_branch.stdout.read().decode().strip()
            if current and current != "main" and current != "master":
                logger.info(f"Already on branch: {current}")
                return True
        
        # Create and switch to new branch
        branch_create = await asyncio.create_subprocess_exec(
            "git", "checkout", "-b", branch_name,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await branch_create.wait()
        
        if branch_create.returncode == 0:
            logger.info(f"Created and switched to branch: {branch_name}")
            return True
        else:
            logger.warning("Failed to create git branch")
            return False
            
    except Exception as e:
        logger.error(f"Git setup error: {str(e)}")
        return False

async def create_pull_request(repo_path: str, original_message: str) -> str:
    """
    Create a pull request with the changes made by Claude Code.
    """
    try:
        # Check if there are any changes
        status_check = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await status_check.wait()
        
        if status_check.returncode != 0:
            return None
            
        changes = status_check.stdout.read().decode().strip()
        if not changes:
            logger.info("No changes detected, skipping PR creation")
            return None
        
        # Get current branch name
        branch_cmd = await asyncio.create_subprocess_exec(
            "git", "branch", "--show-current",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await branch_cmd.wait()
        
        if branch_cmd.returncode != 0:
            return None
            
        branch_name = branch_cmd.stdout.read().decode().strip()
        
        # Get repository info
        remote_url = await get_remote_url(repo_path)
        if not remote_url:
            return None
            
        # Extract owner and repo from URL
        repo_match = re.search(r'github\.com[:/]([^/]+)/([^/\.]+)', remote_url)
        if not repo_match:
            return None
            
        owner, repo = repo_match.groups()
        
        # Create PR URL
        pr_title = f"Claude Code: {original_message[:50]}{'...' if len(original_message) > 50 else ''}"
        pr_body = f"""Changes made by Claude Code based on request:

> {original_message}

**Modified files:**
{changes}

Generated with [Claude Code](https://claude.ai/code)"""
        
        # URL encode the parameters
        import urllib.parse
        title_encoded = urllib.parse.quote(pr_title)
        body_encoded = urllib.parse.quote(pr_body)
        
        pr_url = f"https://github.com/{owner}/{repo}/compare/main...{branch_name}?quick_pull=1&title={title_encoded}&body={body_encoded}"
        
        return pr_url
        
    except Exception as e:
        logger.error(f"Error creating PR: {str(e)}")
        return None

async def get_remote_url(repo_path: str) -> str:
    """
    Get the remote URL of the git repository.
    """
    try:
        remote_cmd = await asyncio.create_subprocess_exec(
            "git", "remote", "get-url", "origin",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await remote_cmd.wait()
        
        if remote_cmd.returncode == 0:
            return remote_cmd.stdout.read().decode().strip()
        return None
        
    except Exception:
        return None

@cl.on_message
async def main(message: cl.Message):
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-4o-mini"
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

    # Check if we should use Claude Code for this request
    use_claude_code = should_use_claude_code(message.content)
    continue_conversation = cl.user_session.get("continue_conversation", False)
    
    if use_claude_code:
        logger.info("Using Claude Code for file modifications/git operations")
        await msg.stream_token("🔧 **Using Claude Code for file modifications...**\n\n")
        
        # Execute Claude Code
        claude_output = await execute_claude_code(
            message.content, 
            repo_path_to_use, 
            continue_conversation=continue_conversation
        )
        
        # Stream the Claude Code output
        await msg.stream_token(claude_output)
        
        # Set flag for next message to potentially continue conversation
        cl.user_session.set("continue_conversation", True)
        
        # Update message history with Claude Code response
        message_history.append({"role": "assistant", "content": f"🔧 Used Claude Code:\n\n{claude_output}"})
        cl.user_session.set("message_history", message_history)
        
        msg.content = f"🔧 **Used Claude Code for file modifications**\n\n{claude_output}"
        await msg.update()
        return

    # Reset continue conversation flag if not using Claude Code
    cl.user_session.set("continue_conversation", False)

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
        completion_params["model"] = "gpt-4-vision-preview"  # Adjust this to your actual vision-capable model

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
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-4o-mini"
    logger.debug(f"Model name: {model_name}")
    
    # Load Claude Code setting
    claude_code_enabled = load_setting("claude_code_enabled")
    if claude_code_enabled is None:
        claude_code_enabled = str(CLAUDE_CODE_ENABLED).lower()
    else:
        claude_code_enabled = claude_code_enabled.lower()
    
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini",
                initial=model_name
            ),
            cl.input_widget.Switch(
                id="claude_code_enabled",
                label="Enable Claude Code (file modifications & git operations)",
                initial=claude_code_enabled == "true"
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