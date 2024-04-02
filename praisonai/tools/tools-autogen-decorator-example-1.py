from typing import Any, Optional
import os
from autogen import ConversableAgent
from scrape_website_tool.scrape_website_tool import ScrapeWebsiteTool

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
from typing import Any

def register_tool(tool_class, tool_name, tool_description):
    def tool_func(website_url: str) -> Any:
        tool_instance = tool_class(website_url=website_url)
        return tool_instance.run()

    register_function(
        tool_func,
        caller=assistant,  # The assistant agent can suggest calls to the tool.
        executor=user_proxy,  # The user proxy agent can execute the tool calls.
        name=tool_name,  # By default, the function name is used as the tool name.
        description=tool_description,  # A description of the tool.
    )
register_tool(ScrapeWebsiteTool, "scrape_website_tool", "A tool for scraping specific websites")

chat_result = user_proxy.initiate_chat(assistant, message="Scrape the official Nodejs website.")