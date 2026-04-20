"""Agent Skills observability events for telemetry and monitoring."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class SkillDiscoveredEvent:
    """Event emitted when a skill is discovered during skill directory scanning.
    
    This event provides visibility into which skills are found and from
    what sources during the discovery phase.
    """
    agent: str
    skill_name: str
    source: str  # Directory path or source identifier
    description_chars: int  # Length of skill description


@dataclass 
class SkillActivatedEvent:
    """Event emitted when a skill is activated (full body loaded/rendered).
    
    This event tracks skill usage patterns and performance metrics
    for skill invocation.
    """
    agent: str
    skill_name: str
    trigger: Literal["slash", "activate_tool", "auto"]
    arguments: str
    rendered_chars: int
    session_id: str | None = None
    activation_time_ms: float | None = None