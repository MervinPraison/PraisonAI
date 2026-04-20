"""Agent Skills activation protocol for progressive disclosure."""

from typing import Protocol, Optional


class SkillActivationProtocol(Protocol):
    """Protocol for progressive disclosure skill activation.
    
    This protocol defines the interface for activating skills on demand,
    supporting Claude Code-style progressive disclosure where only skill
    descriptions are shown in the system prompt initially, with full
    bodies loaded when needed.
    """

    def activate(self, name: str, arguments: str = "", session_id: Optional[str] = None) -> str:
        """Activate a skill and return its rendered body.
        
        Args:
            name: Name of the skill to activate
            arguments: Arguments to substitute in the skill body
            session_id: Optional session identifier for context
            
        Returns:
            Rendered skill body with arguments substituted
            
        Raises:
            ValueError: If skill is not found or not user-invocable
        """
        ...