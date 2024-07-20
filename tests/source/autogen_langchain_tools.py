import math
import os
from typing import Optional, Type

# Starndard Langchain example
from langchain.agents import create_spark_sql_agent
from langchain.agents.agent_toolkits import SparkSQLToolkit
from langchain.chat_models import ChatOpenAI

# Import things that are needed generically
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import BaseTool
from langchain.tools.file_management.read import ReadFileTool
from langchain.utilities.spark_sql import SparkSQL

import autogen

class CircumferenceToolInput(BaseModel):
    radius: float = Field()


class CircumferenceTool(BaseTool):
    name = "circumference_calculator"
    description = "Use this tool when you need to calculate a circumference using the radius of a circle"
    args_schema: Type[BaseModel] = CircumferenceToolInput

    def _run(self, radius: float):
        return float(radius) * 2.0 * math.pi


def get_file_path_of_example():
    current_dir = os.path.dirname(__file__)
    file_path = os.path.join(current_dir, "radius.txt")
    return file_path

# Define a function to generate llm_config from a LangChain tool
def generate_llm_config(tool):
    # Define the function schema based on the tool's args_schema
    function_schema = {
        "name": tool.name.lower().replace(" ", "_"),
        "description": tool.description,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }

    if tool.args is not None:
        function_schema["parameters"]["properties"] = tool.args

    return function_schema


# Instantiate the ReadFileTool
read_file_tool = ReadFileTool()
custom_tool = CircumferenceTool()

# Construct the llm_config
llm_config = {
    # Generate functions config for the Tool
    "functions": [
        generate_llm_config(custom_tool),
        generate_llm_config(read_file_tool),
    ],
    "config_list": [{"model": "gpt-4o-mini", "api_key": os.environ["OPENAI_API_KEY"]}],
    "timeout": 120,
}

user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    is_termination_msg=lambda x: x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE"),
    human_input_mode="NEVER",
    max_consecutive_auto_reply=10,
    code_execution_config={
        "work_dir": "coding",
        "use_docker": False,
    },  # Please set use_docker=True if docker is available to run the generated code. Using docker is safer than running the generated code directly.
)

# Register the tool and start the conversation
user_proxy.register_function(
    function_map={
        custom_tool.name: custom_tool._run,
        read_file_tool.name: read_file_tool._run,
    }
)

chatbot = autogen.AssistantAgent(
    name="chatbot",
    system_message="For coding tasks, only use the functions you have been provided with. Reply TERMINATE when the task is done.",
    llm_config=llm_config,
)

user_proxy.initiate_chat(
    chatbot,
    message=f"Read the file with the path {get_file_path_of_example()}, then calculate the circumference of a circle that has a radius of that files contents.",  # 7.81mm in the file
    llm_config=llm_config,
)
