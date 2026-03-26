"""
Example of AG2 tool registration for use with PraisonAI's --framework ag2.

AG2 (community fork of AutoGen, PyPI package: ag2) installs under the
'autogen' namespace but is a distinct package from pyautogen/pyautogen2.

Usage with PraisonAI:
    pip install "praisonai[ag2]"
    praisonai --framework ag2 agents.yaml

Standalone run:
    python tests/source/ag2_function_tools.py
"""
from typing import Annotated, Literal
import os

# ag2 installs under the 'autogen' namespace
from autogen import (
    AssistantAgent,
    UserProxyAgent,
    GroupChat,
    GroupChatManager,
    LLMConfig,
)

Operator = Literal["+", "-", "*", "/"]


def calculator(
    a: Annotated[int, "First operand"],
    b: Annotated[int, "Second operand"],
    operator: Annotated[Operator, "Arithmetic operator: +, -, *, /"],
) -> int:
    """Perform basic arithmetic operations."""
    if operator == "+":
        return a + b
    elif operator == "-":
        return a - b
    elif operator == "*":
        return a * b
    elif operator == "/":
        if b == 0:
            raise ValueError("Division by zero")
        return int(a / b)
    else:
        raise ValueError(f"Invalid operator: {operator}")


# Build LLMConfig — AG2 uses a context manager pattern so agents
# created inside the 'with' block automatically inherit the config.
llm_config = LLMConfig(
    api_type="openai",
    model=os.environ.get("MODEL_NAME", "gpt-4o-mini"),
    api_key=os.environ.get("OPENAI_API_KEY"),
)

# Create AssistantAgent inside llm_config context
with llm_config:
    assistant = AssistantAgent(
        name="Calculator_Assistant",
        system_message=(
            "You are a helpful AI assistant that can perform arithmetic calculations. "
            "Use the calculator tool when math operations are needed. "
            "Return 'TERMINATE' when the task is done."
        ),
    )

# UserProxyAgent does not use LLM — created outside context
user_proxy = UserProxyAgent(
    name="User",
    human_input_mode="NEVER",
    is_termination_msg=lambda msg: (
        msg.get("content") is not None and "TERMINATE" in msg["content"]
    ),
    code_execution_config=False,
)

# AG2 tool registration pattern:
#   @agent.register_for_llm(description="...")  — exposes tool schema to the LLM
#   @user_proxy.register_for_execution()        — tells user_proxy to execute it


@assistant.register_for_llm(description="A simple calculator for arithmetic operations.")
@user_proxy.register_for_execution()
def calculator_tool(
    a: Annotated[int, "First operand"],
    b: Annotated[int, "Second operand"],
    operator: Annotated[Operator, "Arithmetic operator"],
) -> int:
    return calculator(a, b, operator)


if __name__ == "__main__":
    chat_result = user_proxy.initiate_chat(
        assistant,
        message="What is (44232 + 13312 / (232 - 32)) * 5?",
    )
    print(f"\nResult: {chat_result.summary}")
