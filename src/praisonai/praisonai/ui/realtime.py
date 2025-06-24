import os
import asyncio
import sqlite3
from datetime import datetime
from uuid import uuid4

from openai import AsyncOpenAI
import chainlit as cl
from chainlit.input_widget import TextInput
from chainlit.types import ThreadDict

from realtimeclient import RealtimeClient
from realtimeclient.tools import tools
from sql_alchemy import SQLAlchemyDataLayer
import chainlit.data as cl_data
from literalai.helper import utc_now
import json
import logging
import importlib.util
from importlib import import_module
from pathlib import Path

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

# Set up CHAINLIT_AUTH_SECRET
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

if not CHAINLIT_AUTH_SECRET:
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"
    CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

# Database path
DB_PATH = os.path.expanduser("~/.praison/database.sqlite")

def initialize_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            identifier TEXT NOT NULL UNIQUE,
            metadata JSONB NOT NULL,
            createdAt TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS threads (
            id UUID PRIMARY KEY,
            createdAt TEXT,
            name TEXT,
            userId UUID,
            userIdentifier TEXT,
            tags TEXT[],
            metadata JSONB NOT NULL DEFAULT '{}',
            FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS steps (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            threadId UUID NOT NULL,
            parentId UUID,
            disableFeedback BOOLEAN NOT NULL DEFAULT 0,
            streaming BOOLEAN NOT NULL DEFAULT 0,
            waitForAnswer BOOLEAN DEFAULT 0,
            isError BOOLEAN NOT NULL DEFAULT 0,
            metadata JSONB DEFAULT '{}',
            tags TEXT[],
            input TEXT,
            output TEXT,
            createdAt TEXT,
            start TEXT,
            end TEXT,
            generation JSONB,
            showInput TEXT,
            language TEXT,
            indent INT,
            FOREIGN KEY (threadId) REFERENCES threads (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS elements (
            id UUID PRIMARY KEY,
            threadId UUID,
            type TEXT,
            url TEXT,
            chainlitKey TEXT,
            name TEXT NOT NULL,
            display TEXT,
            objectKey TEXT,
            size TEXT,
            page INT,
            language TEXT,
            forId UUID,
            mime TEXT,
            FOREIGN KEY (threadId) REFERENCES threads (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedbacks (
            id UUID PRIMARY KEY,
            forId UUID NOT NULL,
            value INT NOT NULL,
            threadId UUID,
            comment TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_setting(key: str, value: str):
    """Saves a setting to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO settings (id, key, value)
        VALUES ((SELECT id FROM settings WHERE key = ?), ?, ?)
    """,
        (key, key, value),
    )
    conn.commit()
    conn.close()

def load_setting(key: str) -> str:
    """Loads a setting from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# Initialize the database
initialize_db()

# Set up SQLAlchemy data layer
cl_data._data_layer = SQLAlchemyDataLayer(conninfo=f"sqlite+aiosqlite:///{DB_PATH}")

client = AsyncOpenAI()

# Try to import tools from the root directory
tools_path = os.path.join(os.getcwd(), 'tools.py')
logger.info(f"Tools path: {tools_path}")

def import_tools_from_file(file_path):
    spec = importlib.util.spec_from_file_location("custom_tools", file_path)
    custom_tools_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(custom_tools_module)
    logger.debug(f"Imported tools from {file_path}")
    logger.debug(f"Tools: {custom_tools_module}")
    return custom_tools_module

try:
    if os.path.exists(tools_path):
        # tools.py exists in the root directory, import from file
        custom_tools_module = import_tools_from_file(tools_path)
        logger.info("Successfully imported custom tools from root tools.py")
    else:
        logger.info("No custom tools.py file found in the root directory")
        custom_tools_module = None

    if custom_tools_module:
        # Update the tools list with custom tools
        if hasattr(custom_tools_module, 'tools') and isinstance(custom_tools_module.tools, list):
            # Only add tools that have proper function definitions
            for tool in custom_tools_module.tools:
                if isinstance(tool, tuple) and len(tool) == 2:
                    tool_def, handler = tool
                    if isinstance(tool_def, dict) and "type" in tool_def and tool_def["type"] == "function":
                        # Convert class/function to proper tool definition
                        if "function" in tool_def:
                            func = tool_def["function"]
                            if hasattr(func, "__name__"):
                                tool_def = {
                                    "name": func.__name__,
                                    "description": func.__doc__ or f"Execute {func.__name__}",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {},
                                        "required": []
                                    }
                                }
                                tools.append((tool_def, handler))
                    else:
                        # Tool definition is already properly formatted
                        tools.append(tool)
        else:
            # Process individual functions/classes
            for name, obj in custom_tools_module.__dict__.items():
                if callable(obj) and not name.startswith("__"):
                    tool_def = {
                        "name": name,
                        "description": obj.__doc__ or f"Execute {name}",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                    tools.append((tool_def, obj))

except Exception as e:
    logger.warning(f"Error importing custom tools: {str(e)}. Continuing without custom tools.")

@cl.on_chat_start
async def start():
    initialize_db()
    model_name = os.getenv("OPENAI_MODEL_NAME") or os.getenv("MODEL_NAME", "gpt-4o-mini-realtime-preview-2024-12-17")
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("message_history", [])  # Initialize message history
    logger.debug(f"Model name: {model_name}")
    # settings = cl.ChatSettings(
    #     [
    #         TextInput(
    #             id="model_name",
    #             label="Enter the Model Name",
    #             placeholder="e.g., gpt-4o-mini-realtime-preview-2024-12-17",
    #             initial=model_name
    #         )
    #     ]
    # )
    # cl.user_session.set("settings", settings)
    # await settings.send()
    await cl.Message(
        content="Welcome to the PraisonAI realtime. Press `P` to talk!"
    ).send()
    await setup_openai_realtime()

@cl.on_message
async def on_message(message: cl.Message):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    message_history = cl.user_session.get("message_history", [])
    
    if openai_realtime and openai_realtime.is_connected():
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = f"Current time Just for reference: {current_date}\n\n{message.content}"
        
        # Add user message to history
        message_history.append({"role": "user", "content": prompt})
        cl.user_session.set("message_history", message_history)
        
        await openai_realtime.send_user_message_content([{ "type": 'input_text', "text": message.content }])
    else:
        await cl.Message(content="Please activate voice mode before sending messages!").send()

async def setup_openai_realtime():
    """Instantiate and configure the OpenAI Realtime Client"""
    openai_realtime = RealtimeClient(api_key=os.getenv("OPENAI_API_KEY"))
    cl.user_session.set("track_id", str(uuid4()))

    async def handle_conversation_updated(event):
        item = event.get("item")
        delta = event.get("delta")
        """Currently used to stream audio back to the client."""
        if delta:
            if 'audio' in delta:
                audio = delta['audio']  # Int16Array, audio added
                await cl.context.emitter.send_audio_chunk(cl.OutputAudioChunk(mimeType="pcm16", data=audio, track=cl.user_session.get("track_id")))
            if 'transcript' in delta:
                transcript = delta['transcript']  # string, transcript added
                logger.debug(f"Transcript delta: {transcript}")
            if 'text' in delta:
                text = delta['text']  # string, text added
                logger.debug(f"Text delta: {text}")
            if 'arguments' in delta:
                arguments = delta['arguments']  # string, function arguments added
                logger.debug(f"Function arguments delta: {arguments}")

    async def handle_item_completed(event):
        """Used to populate the chat context with transcription once an item is completed."""
        try:
            item = event.get("item")
            logger.debug(f"Item completed: {json.dumps(item, indent=2, default=str)}")
            await openai_realtime._send_chainlit_message(item)
            
            # Add assistant message to history
            message_history = cl.user_session.get("message_history", [])
            content = item.get("formatted", {}).get("text", "") or item.get("formatted", {}).get("transcript", "")
            if content:
                message_history.append({"role": "assistant", "content": content})
                cl.user_session.set("message_history", message_history)
        except Exception as e:
            error_message = f"Error in handle_item_completed: {str(e)}"
            logger.error(error_message)
            debug_item = json.dumps(item, indent=2, default=str)
            logger.error(f"Item causing error: {debug_item}")

    async def handle_conversation_interrupt(event):
        """Used to cancel the client previous audio playback."""
        cl.user_session.set("track_id", str(uuid4()))
        await cl.context.emitter.send_audio_interrupt()

    async def handle_error(event):
        logger.error(event)
        await cl.Message(content=f"Error: {event}", author="System").send()

    # Register event handlers
    openai_realtime.on('conversation.updated', handle_conversation_updated)
    openai_realtime.on('conversation.item.completed', handle_item_completed)
    openai_realtime.on('conversation.interrupted', handle_conversation_interrupt)
    openai_realtime.on('error', handle_error)

    cl.user_session.set("openai_realtime", openai_realtime)
    
    # Filter out invalid tools and add valid ones
    valid_tools = []
    for tool_def, tool_handler in tools:
        try:
            if isinstance(tool_def, dict) and "name" in tool_def:
                valid_tools.append((tool_def, tool_handler))
            else:
                logger.warning(f"Skipping invalid tool definition: {tool_def}")
        except Exception as e:
            logger.warning(f"Error processing tool: {e}")
    
    if valid_tools:
        coros = [openai_realtime.add_tool(tool_def, tool_handler) for tool_def, tool_handler in valid_tools]
        await asyncio.gather(*coros)
    else:
        logger.warning("No valid tools found to add")

@cl.on_settings_update
async def setup_agent(settings):
    logger.debug(settings)
    cl.user_session.set("settings", settings)
    model_name = settings["model_name"]
    cl.user_session.set("model_name", model_name)
    
    # Save in settings table
    save_setting("model_name", model_name)
    
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

@cl.on_audio_start
async def on_audio_start():
    try:
        openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
        if not openai_realtime:
            await setup_openai_realtime()
            openai_realtime = cl.user_session.get("openai_realtime")
        
        if not openai_realtime.is_connected():
            model_name = cl.user_session.get("model_name") or os.getenv("OPENAI_MODEL_NAME") or os.getenv("MODEL_NAME", "gpt-4o-mini-realtime-preview-2024-12-17")
            await openai_realtime.connect(model_name)
            
        logger.info("Connected to OpenAI realtime")
        return True
    except Exception as e:
        error_msg = f"Failed to connect to OpenAI realtime: {str(e)}"
        logger.error(error_msg)
        await cl.ErrorMessage(content=error_msg).send()
        return False

@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    
    if not openai_realtime:
        logger.debug("No realtime client available")
        return
        
    if openai_realtime.is_connected():
        try:
            success = await openai_realtime.append_input_audio(chunk.data)
            if not success:
                logger.debug("Failed to append audio data - connection may be lost")
        except Exception as e:
            logger.debug(f"Error processing audio chunk: {e}")
            # Optionally try to reconnect here if needed
    else:
        logger.debug("RealtimeClient is not connected - audio chunk ignored")

@cl.on_audio_end
@cl.on_chat_end
@cl.on_stop
async def on_end():
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        await openai_realtime.disconnect()

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # You can customize this function to use your own authentication logic
    expected_username = os.getenv("CHAINLIT_USERNAME", "admin")
    expected_password = os.getenv("CHAINLIT_PASSWORD", "admin")
    if (username, password) == (expected_username, expected_password):
        return cl.User(
            identifier=username, metadata={"role": "ADMIN", "provider": "credentials"}
        )
    else:
        return None

@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    logger.info(f"Resuming chat: {thread['id']}")
    model_name = os.getenv("OPENAI_MODEL_NAME") or os.getenv("MODEL_NAME") or "gpt-4o-mini-realtime-preview-2024-12-17"
    logger.debug(f"Model name: {model_name}")
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini-realtime-preview-2024-12-17",
                initial=model_name
            )
        ]
    )
    await settings.send()
    thread_id = thread["id"]
    cl.user_session.set("thread_id", thread["id"])
    
    # Ensure metadata is a dictionary
    metadata = thread.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    
    cl.user_session.set("metadata", metadata)
    
    message_history = []
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

    # Reconnect to OpenAI realtime
    await setup_openai_realtime()

    