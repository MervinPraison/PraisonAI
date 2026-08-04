"""OpenAI-compatible schema for hierarchical manager delegation."""

from pydantic import BaseModel, ConfigDict, Field


class ManagerInstructions(BaseModel):
    """Instructions emitted by the hierarchical manager each delegation turn.

    ``extra="forbid"`` makes Pydantic emit ``additionalProperties: false`` in the
    generated JSON schema, which OpenAI's strict structured-output API requires.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(..., description="1-based index of the task to run next")
    agent_name: str = Field(..., description="Name of the agent assigned to the task")
    action: str = Field(..., description="'execute' to run the task or 'stop' to end the workflow")
