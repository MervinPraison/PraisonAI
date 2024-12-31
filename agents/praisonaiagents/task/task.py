import logging
from typing import List, Optional, Dict, Any, Type, Callable, Union
from pydantic import BaseModel
from ..main import TaskOutput
from ..agent.agent import Agent
import uuid

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
        images: Optional[List[str]] = None,
        next_tasks: Optional[List[str]] = None,
        task_type: str = "task",
        condition: Optional[Dict[str, List[str]]] = None,
        is_start: bool = False,
        loop_state: Optional[Dict[str, Union[str, int]]] = None
    ):
        self.id = str(uuid.uuid4()) if id is None else str(id)
        self.name = name
        self.description = description
        self.expected_output = expected_output
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
        self.images = images if images else []
        self.next_tasks = next_tasks if next_tasks else []
        self.task_type = task_type
        self.condition = condition if condition else {}
        self.is_start = is_start
        self.loop_state = loop_state if loop_state else {}

        if self.output_json and self.output_pydantic:
            raise ValueError("Only one output type can be defined")

        # Track previous tasks based on next_tasks relationships
        self.previous_tasks = []

    def __str__(self):
        return f"Task(name='{self.name if self.name else 'None'}', description='{self.description}', agent='{self.agent.name if self.agent else 'None'}', status='{self.status}')" 