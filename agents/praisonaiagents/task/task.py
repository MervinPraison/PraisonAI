import logging
from typing import List, Optional, Dict, Any, Type
from pydantic import BaseModel
from ..main import TaskOutput
from ..agent.agent import Agent

class Task:
    def __init__(
        self,
        description: str,
        expected_output: str,
        agent: Optional[Agent] = None,
        name: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        context: Optional[List["Task"]] = None,
        async_execution: Optional[bool] = False,
        config: Optional[Dict[str, Any]] = None,
        output_file: Optional[str] = None,
        output_json: Optional[Type[BaseModel]] = None,
        output_pydantic: Optional[Type[BaseModel]] = None,
        callback: Optional[Any] = None,
        status: str = "not started",
        result: Optional[TaskOutput] = None,
        create_directory: Optional[bool] = False,
        id: Optional[int] = None,
        images: Optional[List[str]] = None
    ):
        self.description = description
        self.expected_output = expected_output
        self.name = name
        self.agent = agent
        self.tools = tools if tools else []
        self.context = context if context else []
        self.async_execution = async_execution
        self.config = config if config else {}
        self.output_file = output_file
        self.output_json = output_json
        self.output_pydantic = output_pydantic
        self.callback = callback
        self.status = status
        self.result = result
        self.create_directory = create_directory
        self.id = id
        self.images = images if images else []

        if self.output_json and self.output_pydantic:
            raise ValueError("Only one output type can be defined")

    def __str__(self):
        return f"Task(name='{self.name if self.name else 'None'}', description='{self.description}', agent='{self.agent.name if self.agent else 'None'}', status='{self.status}')" 