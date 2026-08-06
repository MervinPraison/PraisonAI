"""OpenAI-compatible schema for hierarchical manager delegation."""

from pydantic import BaseModel, ConfigDict, Field


class ManagerInstructions(BaseModel):
    """Instructions emitted by the hierarchical manager each delegation turn.

    ``extra="forbid"`` makes Pydantic emit ``additionalProperties: false`` in the
    generated JSON schema, which OpenAI's strict structured-output API requires.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(
        ...,
        description=(
            "Exact task_id integer of the task to run next, chosen from the "
            "task_id values shown in the tasks list (these ids are 0-based). "
            "Never select manager_task and never invent an id."
        ),
    )
    agent_name: str = Field(..., description="Name of the agent assigned to the task")
    action: str = Field(..., description="'execute' to run the task or 'stop' to end the workflow")
