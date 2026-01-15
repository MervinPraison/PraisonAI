"""Browser Protocol — Lightweight type definitions for browser automation.

This module provides protocol-driven type definitions for browser automation.
It is intentionally minimal to keep the core SDK lightweight.

All heavy implementations live in the praisonai wrapper package.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal, Protocol, runtime_checkable
from enum import Enum


class BrowserActionType(str, Enum):
    """Types of browser actions the agent can perform."""
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    EVALUATE = "evaluate"
    DONE = "done"


@dataclass
class ActionableElement:
    """An element on the page that can be interacted with."""
    selector: str
    tag: str = ""
    text: str = ""
    role: str = ""
    name: str = ""
    description: str = ""
    bounds: Optional[Dict[str, float]] = None
    interactable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "selector": self.selector,
            "tag": self.tag,
            "text": self.text,
            "role": self.role,
            "name": self.name,
            "description": self.description,
            "bounds": self.bounds,
            "interactable": self.interactable,
        }


@dataclass
class BrowserObservation:
    """Observation from the browser sent to the agent.
    
    Contains the current state of the browser tab for agent decision-making.
    """
    session_id: str
    task: str
    url: str
    title: str
    screenshot: str = ""  # base64 encoded
    elements: List[ActionableElement] = field(default_factory=list)
    console_logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    step_number: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "task": self.task,
            "url": self.url,
            "title": self.title,
            "screenshot": self.screenshot,
            "elements": [e.to_dict() for e in self.elements],
            "console_logs": self.console_logs,
            "error": self.error,
            "step_number": self.step_number,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrowserObservation":
        """Create from dictionary."""
        elements = [
            ActionableElement(**e) if isinstance(e, dict) else e
            for e in data.get("elements", [])
        ]
        return cls(
            session_id=data.get("session_id", ""),
            task=data.get("task", ""),
            url=data.get("url", ""),
            title=data.get("title", ""),
            screenshot=data.get("screenshot", ""),
            elements=elements,
            console_logs=data.get("console_logs", []),
            error=data.get("error"),
            step_number=data.get("step_number", 0),
        )


@dataclass
class BrowserAction:
    """Action for the browser to execute.
    
    Returned by the agent to instruct the browser extension.
    """
    action: BrowserActionType
    selector: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    direction: Optional[Literal["up", "down"]] = None
    expression: Optional[str] = None
    thought: str = ""
    done: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "action": self.action.value if isinstance(self.action, BrowserActionType) else self.action,
            "selector": self.selector,
            "text": self.text,
            "url": self.url,
            "direction": self.direction,
            "expression": self.expression,
            "thought": self.thought,
            "done": self.done,
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrowserAction":
        """Create from dictionary."""
        action = data.get("action", "done")
        if isinstance(action, str):
            action = BrowserActionType(action)
        return cls(
            action=action,
            selector=data.get("selector"),
            text=data.get("text"),
            url=data.get("url"),
            direction=data.get("direction"),
            expression=data.get("expression"),
            thought=data.get("thought", ""),
            done=data.get("done", False),
            error=data.get("error"),
        )


@dataclass
class BrowserSession:
    """Represents a browser automation session."""
    session_id: str
    goal: str
    status: Literal["running", "completed", "failed", "paused"] = "running"
    steps: List[Dict[str, Any]] = field(default_factory=list)
    current_url: str = ""
    started_at: float = 0.0
    ended_at: Optional[float] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "steps": self.steps,
            "current_url": self.current_url,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
        }


@runtime_checkable
class BrowserAgentProtocol(Protocol):
    """Protocol for browser agent implementations.
    
    This is a typing protocol — implementations live in the wrapper.
    """
    
    def process_observation(self, observation: BrowserObservation) -> BrowserAction:
        """Process an observation and return the next action."""
        ...
    
    async def aprocess_observation(self, observation: BrowserObservation) -> BrowserAction:
        """Async version of process_observation."""
        ...


@runtime_checkable
class BrowserSessionManagerProtocol(Protocol):
    """Protocol for session management implementations."""
    
    def create_session(self, goal: str) -> BrowserSession:
        """Create a new browser session."""
        ...
    
    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """Get a session by ID."""
        ...
    
    def update_session(self, session: BrowserSession) -> None:
        """Update a session."""
        ...
    
    def list_sessions(self) -> List[BrowserSession]:
        """List all sessions."""
        ...


# Convenience exports
__all__ = [
    "BrowserActionType",
    "ActionableElement",
    "BrowserObservation",
    "BrowserAction",
    "BrowserSession",
    "BrowserAgentProtocol",
    "BrowserSessionManagerProtocol",
]
