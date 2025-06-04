#!/usr/bin/env python3

from typing import Tuple, Any
from praisonaiagents import Agent, Task, TaskOutput


def validate_content(task_output: TaskOutput) -> Tuple[bool, Any]:
    if len(task_output.raw) < 50:
        return False, "Content too short"
    return True, task_output


def main():
    agent = Agent(
        name="Writer",
        guardrail=validate_content
    )
    
    result = agent.start("Write a welcome message with 4 words")
    print(result)


if __name__ == "__main__":
    main()
