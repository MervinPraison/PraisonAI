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

import json

DB_PATH = "threads.db"

def initialize_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY,
            name TEXT,
            createdAt TEXT,
            userId TEXT,
            userIdentifier TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS steps (
            id TEXT PRIMARY KEY,
            threadId TEXT,
            name TEXT,
            createdAt TEXT,
            type TEXT,
            output TEXT,
            FOREIGN KEY (threadId) REFERENCES threads (id)
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

def save_thread_to_db(thread):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO threads (id, name, createdAt, userId, userIdentifier)
        VALUES (?, ?, ?, ?, ?)
    ''', (thread['id'], thread['name'], thread['createdAt'], thread['userId'], thread['userIdentifier']))
    
    # No steps to save as steps are empty in the provided thread data
    conn.commit()
    conn.close()
    logger.debug("Thread saved to DB")

def update_thread_in_db(thread):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Insert or update the thread
    cursor.execute('''
        INSERT OR REPLACE INTO threads (id, name, createdAt, userId, userIdentifier)
        VALUES (?, ?, ?, ?, ?)
    ''', (thread['id'], thread['name'], thread['createdAt'], thread['userId'], thread['userIdentifier']))

    # Fetch message_history from metadata
    message_history = cl.user_session.get("message_history", [])

    # Ensure user messages come first followed by assistant messages
    user_messages = [msg for msg in message_history if msg['role'] == 'user']
    assistant_messages = [msg for msg in message_history if msg['role'] == 'assistant']
    ordered_steps = [val for pair in zip(user_messages, assistant_messages) for val in pair]

    # Generate steps from ordered message_history
    steps = []
    for idx, message in enumerate(ordered_steps):
        step_id = f"{thread['id']}-step-{idx}"
        step_type = 'user_message' if message['role'] == 'user' else 'assistant_message'
        step_name = 'user' if message['role'] == 'user' else 'assistant'
        created_at = message.get('createdAt', thread['createdAt'])  # Use thread's createdAt if no timestamp in message
        steps.append({
            'id': step_id,
            'threadId': thread['id'],
            'name': step_name,
            'createdAt': created_at,
            'type': step_type,
            'output': message['content']
        })

    # Insert all steps into the database
    for step in steps:
        cursor.execute('''
            INSERT OR REPLACE INTO steps (id, threadId, name, createdAt, type, output)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (step['id'], step['threadId'], step['name'], step['createdAt'], step['type'], step['output']))
    
    conn.commit()
    conn.close()
    logger.debug("Thread updated in DB")

def delete_thread_from_db(thread_id: str):
    """Deletes a thread and its steps from the database.

    Args:
        thread_id: The ID of the thread to delete.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM threads WHERE id = ?', (thread_id,))
    cursor.execute('DELETE FROM steps WHERE threadId = ?', (thread_id,))
    conn.commit()
    conn.close()

def load_threads_from_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM threads ORDER BY createdAt ASC')
    thread_rows = cursor.fetchall()
    threads = []
    for thread_row in thread_rows:
        cursor.execute('SELECT * FROM steps WHERE threadId = ? ORDER BY createdAt ASC', (thread_row[0],))
        step_rows = cursor.fetchall()
        steps = []
        for step_row in step_rows:
            steps.append({
                "id": step_row[0],
                "threadId": step_row[1],
                "name": step_row[2],
                "createdAt": step_row[3],
                "type": step_row[4],
                "output": step_row[5]
            })
        threads.append({
            "id": thread_row[0],
            "name": thread_row[1],
            "createdAt": thread_row[2],
            "userId": thread_row[3],
            "userIdentifier": thread_row[4],
            "steps": steps
        })
    conn.close()
    logger.debug("Threads loaded from DB")
    return threads

# Initialize the database
initialize_db()
thread_history = load_threads_from_db()

deleted_thread_ids = []  # type: List[str]

class TestDataLayer(cl_data.BaseDataLayer):
    async def get_user(self, identifier: str):
        logger.debug(f"Getting user: {identifier}")
        return cl.PersistedUser(id="test", createdAt=now, identifier=identifier)

    async def create_user(self, user: cl.User):
        logger.debug(f"Creating user: {user.identifier}")
        return cl.PersistedUser(id="test", createdAt=now, identifier=user.identifier)

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        logger.debug(f"Updating thread: {thread_id}")
        thread = next((t for t in thread_history if t["id"] == thread_id), None)
        if thread:
            if name:
                thread["name"] = name
            if metadata:
                thread["metadata"] = metadata
            if tags:
                thread["tags"] = tags
            
            logger.debug(f"Thread: {thread}")
            cl.user_session.set("message_history", thread['metadata']['message_history'])
            cl.user_session.set("thread_id", thread["id"])
            update_thread_in_db(thread)
            logger.debug(f"Thread updated: {thread_id}")
            
        else:
            thread_history.append(
                {
                    "id": thread_id,
                    "name": name,
                    "metadata": metadata,
                    "tags": tags,
                    "createdAt": utc_now(),
                    "userId": user_id,
                    "userIdentifier": "admin",
                    "steps": [],
                }
            )
            thread = {
                "id": thread_id,
                "name": name,
                "metadata": metadata,
                "tags": tags,
                "createdAt": utc_now(),
                "userId": user_id,
                "userIdentifier": "admin",
                "steps": [],
            }
            save_thread_to_db(thread)
            logger.debug(f"Thread created: {thread_id}")

    @cl_data.queue_until_user_message()
    async def create_step(self, step_dict: StepDict):
        global create_step_counter
        create_step_counter += 1

        thread = next(
            (t for t in thread_history if t["id"] == step_dict.get("threadId")), None
        )
        if thread:
            thread["steps"].append(step_dict)

    async def get_thread_author(self, thread_id: str):
        logger.debug(f"Getting thread author: {thread_id}")
        return "admin"

    async def list_threads(
        self, pagination: cl_data.Pagination, filters: cl_data.ThreadFilter
    ) -> cl_data.PaginatedResponse[cl_data.ThreadDict]:
        logger.debug(f"Listing threads")
        return cl_data.PaginatedResponse(
            data=[t for t in thread_history if t["id"] not in deleted_thread_ids][::-1],
            pageInfo=cl_data.PageInfo(
                hasNextPage=False, startCursor=None, endCursor=None
            ),
        )

    async def get_thread(self, thread_id: str):
        logger.debug(f"Getting thread: {thread_id}")
        thread_history = load_threads_from_db()
        return next((t for t in thread_history if t["id"] == thread_id), None)

    async def delete_thread(self, thread_id: str):
        deleted_thread_ids.append(thread_id)
        delete_thread_from_db(thread_id)
        logger.debug(f"Deleted thread: {thread_id}")

cl_data._data_layer = TestDataLayer()

@cl.on_chat_start
async def start():
    initialize_db()
    model_name = load_setting("model_name") 

    if model_name:
        cl.user_session.set("model_name", model_name)
    else:
        # If no setting found, use default or environment variable
        model_name = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
        cl.user_session.set("model_name", model_name)
    logger.debug(f"Model name: {model_name}")
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-3.5-turbo",
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
    
    # Save in settings table
    save_setting("model_name", model_name)
    
    # Save in thread metadata
    thread_id = cl.user_session.get("thread_id")
    if thread_id:
        thread = await cl_data.get_thread(thread_id)
        if thread:
            metadata = thread.get("metadata", {})
            metadata["model_name"] = model_name
            await cl_data.update_thread(thread_id, metadata=metadata)

@cl.on_message
async def main(message: cl.Message):
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-3.5-turbo"
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    msg = cl.Message(content="")
    await msg.send()

    response = await acompletion(
        model=model_name,
        messages=message_history,
        stream=True,
        temperature=0.7,
        max_tokens=500,
        top_p=1
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
    model_name = load_setting("model_name") or os.getenv("MODEL_NAME") or "gpt-3.5-turbo"
    logger.debug(f"Model name: {model_name}")
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-3.5-turbo",
                initial=model_name
            )
        ]
    )
    await settings.send()
    thread_id = thread["id"]
    cl.user_session.set("thread_id", thread["id"])
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
