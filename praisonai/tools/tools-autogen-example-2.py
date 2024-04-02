from typing import Any, Optional
import os
from autogen import ConversableAgent
from scrape_website_tool.scrape_website_tool import ScrapeWebsiteTool

def scrape_website_tool(website_url: str) -> Any:
    scrape_tool = ScrapeWebsiteTool(website_url=website_url)
    return scrape_tool.run()

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

from autogen import register_function
# Register the ScrapeWebsiteTool function to the agent and user proxy to add a website scraping tool.
register_function(
    scrape_website_tool,
    caller=assistant,  # The assistant agent can suggest calls to the scrape website tool.
    executor=user_proxy,  # The user proxy agent can execute the scrape website tool calls.
    name="scrape_website_tool",  # By default, the function name is used as the tool name.
    description="A tool for scraping specific websites",  # A description of the tool.
)

chat_result = user_proxy.initiate_chat(assistant, message="Scrape the official Python website.")