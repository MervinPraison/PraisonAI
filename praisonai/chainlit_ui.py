from praisonai.agents_generator import AgentsGenerator 
from praisonai.auto import AutoGenerator 
import chainlit as cl
import os
from chainlit.types import ThreadDict
from typing import Optional
from dotenv import load_dotenv

framework = "crewai"
config_list = [
            {
                'model': os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
                'base_url': os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
            }
        ]
agent_file = "test.yaml"

@cl.on_chat_start
async def start_chat():
    cl.user_session.set(
        "message_history",
        [{"role": "system", "content": "You are a helpful assistant."}],
    )
    
@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    message_history = cl.user_session.get("message_history", [])
    root_messages = [m for m in thread["steps"] if m["parentId"] is None]
    for message in root_messages:
        if message["type"] == "user_message":
            message_history.append({"role": "user", "content": message["output"]})
        elif message["type"] == "ai_message":
            message_history.append({"role": "assistant", "content": message["content"]})
    cl.user_session.set("message_history", message_history)

@cl.on_message
async def main(message: cl.Message):
    """Run PraisonAI with the provided message as the topic."""
    message_history = cl.user_session.get("message_history")
    message_history.append({"role": "user", "content": message.content})
    topic = message.content
    agent_file = "test.yaml"
    generator = AutoGenerator(topic=topic, framework=framework)
    agent_file = generator.generate()
    agents_generator = AgentsGenerator(agent_file, framework, config_list)
    result = agents_generator.generate_crew_and_kickoff()
    msg = cl.Message(content=result)
    await msg.send()
    message_history.append({"role": "assistant", "content": message.content})

# Load environment variables from .env file
load_dotenv()

# Get username and password from environment variables
username = os.getenv("CHAINLIT_USERNAME", "admin")  # Default to "admin" if not found
password = os.getenv("CHAINLIT_PASSWORD", "admin")  # Default to "admin" if not found

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # Fetch the user matching username from your database
    # and compare the hashed password with the value stored in the database
    if (username, password) == ("admin", "admin"):
        return cl.User(
            identifier="admin", metadata={"role": "admin", "provider": "credentials"}
        )
    else:
        return None