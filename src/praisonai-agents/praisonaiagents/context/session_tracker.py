"""
Session Context Tracker for PraisonAI Agents.

Tracks session state (summary, goal, plan, progress) across conversation turns.
Inspired by Agno's SessionContextStore pattern.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """
    Session state tracking data.
    
    Tracks:
    - summary: What's happened in the conversation
    - goal: User's objective for this session
    - plan: Steps to achieve the goal
    - progress: Completed steps
    """
    session_id: str = ""
    summary: str = ""
    goal: str = ""
    plan: List[str] = field(default_factory=list)
    progress: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    turn_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Create from dictionary."""
        return cls(
            session_id=data.get("session_id", ""),
            summary=data.get("summary", ""),
            goal=data.get("goal", ""),
            plan=data.get("plan", []),
            progress=data.get("progress", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            turn_count=data.get("turn_count", 0),
        )


class SessionContextTracker:
    """
    Tracks session context (summary/goal/plan/progress) across turns.
    
    Implements the Agno SessionContextStore pattern for PraisonAI.
    Builds upon previous context rather than starting fresh each turn.
    
    Example:
        tracker = SessionContextTracker(session_id="abc123")
        
        # After each turn, update state
        tracker.update_from_turn(messages, llm_client)
        
        # Get context string for system prompt
        context_str = tracker.to_context_string()
    """
    
    def __init__(
        self,
        session_id: str = "",
        track_summary: bool = True,
        track_goal: bool = True,
        track_plan: bool = True,
        track_progress: bool = True,
    ):
        """
        Initialize session context tracker.
        
        Args:
            session_id: Session identifier
            track_summary: Whether to track conversation summary
            track_goal: Whether to track user's objective
            track_plan: Whether to track steps to goal
            track_progress: Whether to track completed steps
        """
        self.session_id = session_id or self._generate_session_id()
        self.track_summary = track_summary
        self.track_goal = track_goal
        self.track_plan = track_plan
        self.track_progress = track_progress
        
        self._state = SessionState(
            session_id=self.session_id,
            created_at=datetime.utcnow().isoformat() + "Z",
            updated_at=datetime.utcnow().isoformat() + "Z",
        )
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    @property
    def state(self) -> SessionState:
        """Get current session state."""
        return self._state
    
    @property
    def summary(self) -> str:
        """Get current summary."""
        return self._state.summary
    
    @property
    def goal(self) -> str:
        """Get current goal."""
        return self._state.goal
    
    @property
    def plan(self) -> List[str]:
        """Get current plan."""
        return self._state.plan
    
    @property
    def progress(self) -> List[str]:
        """Get completed steps."""
        return self._state.progress
    
    def update_summary(self, summary: str) -> None:
        """Update conversation summary."""
        if self.track_summary:
            self._state.summary = summary
            self._mark_updated()
    
    def update_goal(self, goal: str) -> None:
        """Update user's objective."""
        if self.track_goal:
            self._state.goal = goal
            self._mark_updated()
    
    def update_plan(self, plan: List[str]) -> None:
        """Update plan steps."""
        if self.track_plan:
            self._state.plan = plan
            self._mark_updated()
    
    def add_progress(self, step: str) -> None:
        """Add a completed step to progress."""
        if self.track_progress:
            self._state.progress.append(step)
            self._mark_updated()
    
    def mark_plan_step_complete(self, step_index: int) -> None:
        """Mark a plan step as complete and add to progress."""
        if 0 <= step_index < len(self._state.plan):
            step = self._state.plan[step_index]
            self.add_progress(step)
    
    def _mark_updated(self) -> None:
        """Update the updated_at timestamp."""
        self._state.updated_at = datetime.utcnow().isoformat() + "Z"
        self._state.turn_count += 1
    
    def to_context_string(self) -> str:
        """
        Format session context for injection into system prompt.
        
        Returns string formatted for the agent to use as context.
        """
        parts = []
        
        if self._state.summary:
            parts.append(f"**Conversation Summary**: {self._state.summary}")
        
        if self._state.goal:
            parts.append(f"**User's Goal**: {self._state.goal}")
        
        if self._state.plan:
            plan_str = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(self._state.plan))
            parts.append(f"**Plan**:\n{plan_str}")
        
        if self._state.progress:
            progress_str = "\n".join(f"  ✓ {step}" for step in self._state.progress)
            parts.append(f"**Progress**:\n{progress_str}")
        
        if not parts:
            return ""
        
        return "\n\n".join(parts)
    
    def to_system_prompt_section(self) -> str:
        """
        Generate a system prompt section with session context.
        
        Follows Agno's pattern of including guidelines for using the context.
        """
        context = self.to_context_string()
        
        if not context:
            return ""
        
        return f"""<session_context>
This is a continuation of an ongoing session. Here's where things stand:

{context}

<session_context_guidelines>
Use this context to maintain continuity:
- Reference earlier decisions and conclusions naturally
- Don't re-ask questions that have already been answered
- Build on established understanding rather than starting fresh
- If the user references something from "earlier," this context has the details

Current messages take precedence if there's any conflict with this summary.
</session_context_guidelines>
</session_context>"""
    
    def update_from_messages(
        self,
        messages: List[Dict[str, Any]],
        extract_goal: bool = True,
    ) -> None:
        """
        Update session state from conversation messages.
        
        This is a simple heuristic-based extraction. For more accurate
        extraction, use update_from_turn with an LLM.
        
        Args:
            messages: List of conversation messages
            extract_goal: Whether to try extracting goal from first user message
        """
        if not messages:
            return
        
        # Extract goal from first user message if not set
        if extract_goal and not self._state.goal:
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str) and len(content) < 500:
                        self._state.goal = content[:200]
                    break
        
        # Update turn count
        user_turns = sum(1 for m in messages if m.get("role") == "user")
        self._state.turn_count = user_turns
        self._mark_updated()
    
    def clear(self) -> None:
        """Clear session state."""
        self._state = SessionState(
            session_id=self.session_id,
            created_at=self._state.created_at,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "track_summary": self.track_summary,
            "track_goal": self.track_goal,
            "track_plan": self.track_plan,
            "track_progress": self.track_progress,
            "state": self._state.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContextTracker":
        """Create from dictionary."""
        tracker = cls(
            session_id=data.get("session_id", ""),
            track_summary=data.get("track_summary", True),
            track_goal=data.get("track_goal", True),
            track_plan=data.get("track_plan", True),
            track_progress=data.get("track_progress", True),
        )
        if "state" in data:
            tracker._state = SessionState.from_dict(data["state"])
        return tracker
