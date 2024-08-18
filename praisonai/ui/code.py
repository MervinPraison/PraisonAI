import chainlit as cl
from chainlit.input_widget import TextInput
from chainlit.types import ThreadDict
from litellm import acompletion
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()
import chainlit.data as cl_data
from chainlit.step import StepDict
from literalai.helper import utc_now
import logging
import json
from sql_alchemy import SQLAlchemyDataLayer
from context import ContextGatherer

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

CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

if not CHAINLIT_AUTH_SECRET:
    os.environ["CHAINLIT_AUTH_SECRET"] = "p8BPhQChpg@J>jBz$wGxqLX2V>yTVgP*7Ky9H$aV:axW~ANNX-7_T:o@lnyCBu^U"
    CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

now = utc_now()

create_step_counter = 0

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
    """Saves a setting to the database.

    Args:
        key: The setting key.
        value: The setting value.
    """
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
    """Loads a setting from the database.

    Args:
        key: The setting key.

    Returns:
        The setting value, or None if the key is not found.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


# Initialize the database
initialize_db()

deleted_thread_ids = []  # type: List[str]

cl_data._data_layer = SQLAlchemyDataLayer(conninfo=f"sqlite+aiosqlite:///{DB_PATH}")

@cl.on_chat_start
async def start():
    initialize_db()
    model_name = load_setting("model_name") 

    if model_name:
        cl.user_session.set("model_name", model_name)
    else:
        # If no setting found, use default or environment variable
        model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")
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
    gatherer = ContextGatherer()
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
    
    # Save in settings table
    save_setting("model_name", model_name)
    
    # Save in thread metadata
    thread_id = cl.user_session.get("thread_id")
    if thread_id:
        thread = await cl_data.get_thread(thread_id)
        if thread:
            metadata = thread.get("metadata", {})
            metadata["model_name"] = model_name
            
            # Always store metadata as a JSON string
            await cl_data.update_thread(thread_id, metadata=json.dumps(metadata))
            
            # Update the user session with the new metadata
            cl.user_session.set("metadata", metadata)

@cl.on_message
async def main(message: cl.Message):
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-4o-mini"
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})
    gatherer = ContextGatherer()
    context, token_count, context_tree = gatherer.run()
    prompt_history = message_history
    prompt_history.append({"role": "user", "content": """
                           Answer the question:\n{question}.\n\n
                           Below is the Context:\n{context}\n\n"""
                           .format(context=context, question=message.content)})

    msg = cl.Message(content="")
    await msg.send()

    response = await acompletion(
        model=model_name,
        messages=prompt_history,
        stream=True,
        # temperature=0.7,
        # max_tokens=500,
        # top_p=1
    )

    full_response = ""
    async for part in response:
        if token := part['choices'][0]['delta']['content']:
            await msg.stream_token(token)
            full_response += token
    logger.debug(f"Full response: {full_response}")
    message_history.append({"role": "assistant", "content": full_response})
    logger.debug(f"Message history: {message_history}")
    cl.user_session.set("message_history", message_history)
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
async def on_chat_resume(thread: cl_data.ThreadDict):
    logger.info(f"Resuming chat: {thread['id']}")
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-4o-mini"
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
    cl.user_session.set("thread_id", thread["id"])
    
    # The metadata should now already be a dictionary
    metadata = thread.get("metadata", {})
    cl.user_session.set("metadata", metadata)
    
    message_history = cl.user_session.get("message_history", [])
    steps = thread["steps"]

    for message in steps:
        msg_type = message.get("type")
        if msg_type == "user_message":
            message_history.append({"role": "user", "content": message.get("output", "")})
        elif msg_type == "assistant_message":
            message_history.append({"role": "assistant", "content": message.get("output", "")})
        else:
            logger.warning(f"Message without type: {message}")

    cl.user_session.set("message_history", message_history)
