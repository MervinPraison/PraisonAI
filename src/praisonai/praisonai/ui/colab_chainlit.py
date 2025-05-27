import os
import logging
from dotenv import load_dotenv
import chainlit as cl
from chainlit.types import ThreadDict
import yaml
import sys
import os
from datetime import datetime

# Add the parent directory to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from praisonai.ui.colab import ui_run_praisonai, load_tools_from_tools_py
from praisonai.ui.callbacks import callback, trigger_callback

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger.setLevel(log_level)

# Load agent configuration
agent_file = "agents.yaml"
with open(agent_file, 'r') as f:
    config = yaml.safe_load(f)

# Load tools
tools_dict = load_tools_from_tools_py()

@cl.on_message
async def main(message: cl.Message):
    """Main message handler for Chainlit"""
    try:
        logger.info(f"Processing message: {message.content}")
        await cl.Message(
            content=f"🔄 Processing your request about: {message.content}...",
            author="System"
        ).send()

        await cl.Message(
            content="Using Running PraisonAI Agents...",
            author="System"
        ).send()

        # Run PraisonAI with the message content as the topic
        result = await ui_run_praisonai(config, message.content, tools_dict)
        
        # Send the final result
        await cl.Message(
            content=result,
            author="System"
        ).send()

    except Exception as e:
        error_msg = f"Error running PraisonAI agents: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(
            content=error_msg,
            author="System"
        ).send()

@cl.on_chat_start
async def start():
    """Handler for chat start"""
    await cl.Message(
        content="👋 Welcome! I'm your AI assistant. What would you like to work on?",
        author="System"
    ).send()

# Authentication setup (optional)
if os.getenv("CHAINLIT_AUTH_SECRET"):
    @cl.password_auth_callback
    def auth_callback(username: str, password: str) -> cl.User:
        # Replace with your authentication logic
        if username == os.getenv("CHAINLIT_USERNAME", "admin") and \
           password == os.getenv("CHAINLIT_PASSWORD", "admin"):
            return cl.User(identifier=username, metadata={"role": "user"})
        return None 