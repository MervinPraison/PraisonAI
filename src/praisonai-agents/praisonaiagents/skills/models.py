"""Data models for Agent Skills."""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


class ParseError(Exception):
    """Raised when SKILL.md parsing fails."""
    pass


class ValidationError(Exception):
    """Raised when skill validation fails."""
    pass


@dataclass
class SkillProperties:
    """Properties parsed from a skill's SKILL.md frontmatter.

    Attributes:
        name: Skill name in kebab-case (required)
        description: What the skill does and when the model should use it (required)
        license: License for the skill (optional)
        compatibility: Compatibility information for the skill (optional)
        allowed_tools: Tool patterns the skill requires (optional, experimental)
        metadata: Key-value pairs for client-specific properties (defaults to
            empty dict; omitted from to_dict() output when empty)
        path: Path to the skill directory (optional, added for PraisonAI)
    """

    name: str
    description: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    path: Optional[Path] = None

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values and empty metadata."""
        result = {"name": self.name, "description": self.description}
        if self.license is not None:
            result["license"] = self.license
        if self.compatibility is not None:
            result["compatibility"] = self.compatibility
        if self.allowed_tools is not None:
            result["allowed-tools"] = self.allowed_tools
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class SkillMetadata:
    """Lightweight skill metadata for system prompt injection.
    
    This is the minimal information needed to include a skill in the
    system prompt's <available_skills> block (~50-100 tokens per skill).

    Attributes:
        name: Skill name
        description: What the skill does and when to use it
        location: Absolute path to the SKILL.md file
    """

    name: str
    description: str
    location: str

    @classmethod
    def from_properties(cls, props: SkillProperties) -> "SkillMetadata":
        """Create SkillMetadata from SkillProperties.
        
        Args:
            props: SkillProperties instance with path set
            
        Returns:
            SkillMetadata with location pointing to SKILL.md
        """
        if props.path:
            # Look for SKILL.md or skill.md
            skill_md = props.path / "SKILL.md"
            if not skill_md.exists():
                skill_md = props.path / "skill.md"
            location = str(skill_md)
        else:
            location = ""
        
        return cls(
            name=props.name,
            description=props.description,
            location=location
        )
