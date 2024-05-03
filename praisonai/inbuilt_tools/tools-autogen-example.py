from typing import Any, Optional
import os
from autogen import ConversableAgent
from autogen_tools import autogen_ScrapeWebsiteTool

assistant = ConversableAgent(
    name="Assistant",
    system_message="You are a helpful AI assistant. "
    "You can help with website scraping. "
    "Return 'TERMINATE' when the task is done.",
    llm_config={"config_list": [{"model": "gpt-3.5-turbo", "api_key": os.environ["OPENAI_API_KEY"]}]},
)

user_proxy = ConversableAgent(
    name="User",
    llm_config=False,
    is_termination_msg=lambda msg: msg.get("content") is not None and "TERMINATE" in msg["content"],
    human_input_mode="NEVER",
)

autogen_ScrapeWebsiteTool(assistant, user_proxy)

chat_result = user_proxy.initiate_chat(assistant, message="Scrape the official Nodejs website.")