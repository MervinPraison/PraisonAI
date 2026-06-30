"""Data models for Agent Skills."""

from dataclasses import dataclass, field
from typing import Optional, List, Union
from pathlib import Path
from enum import Enum


class ParseError(Exception):
    """Raised when SKILL.md parsing fails."""
    pass


class ValidationError(Exception):
    """Raised when skill validation fails."""
    pass


class SkillState(Enum):
    """Skill activation state based on requirement validation."""
    ACTIVE = "active"          # All requirements satisfied
    DEGRADED = "degraded"      # Some requirements missing (soft warn)
    UNAVAILABLE = "unavailable" # Critical requirements missing (hard fail)
    UNKNOWN = "unknown"        # Requirements not yet validated


@dataclass
class SkillRequirements:
    """Capability requirements for a skill.
    
    This represents the parsed and normalized requirements from skill frontmatter.
    Supports both Hermes/OpenClaw conventions and PraisonAI-specific extensions.
    
    Attributes:
        servers: Required MCP servers or service endpoints
        tools: Required tool names (from tool registry)
        env_vars: Required environment variables (use sparingly)
        openclaw_hints: OpenClaw-specific metadata (passthrough)
        fallback_for_tools: Tools this skill is a graceful fallback for. The
            skill is offered only when *none* of these tools are present,
            keeping capable agents free of redundant fallback guidance.
        fallback_for_servers: MCP servers this skill is a graceful fallback
            for. The skill is offered only when *none* of these servers are
            present.
    """
    servers: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list) 
    env_vars: List[str] = field(default_factory=list)
    openclaw_hints: dict = field(default_factory=dict)
    fallback_for_tools: List[str] = field(default_factory=list)
    fallback_for_servers: List[str] = field(default_factory=list)
    
    @classmethod
    def from_frontmatter(cls, metadata: dict) -> "SkillRequirements":
        """Parse requirements from skill frontmatter.
        
        Normalizes various naming conventions:
        - requires_servers, requires_tools (Hermes/OpenClaw style)
        - allowed-tools (existing PraisonAI convention) 
        - openclaw (OpenClaw-specific hints)
        
        Args:
            metadata: Raw frontmatter dict
            
        Returns:
            SkillRequirements instance
        """
        servers = []
        tools = []
        env_vars = []
        openclaw_hints = {}
        fallback_for_tools = []
        fallback_for_servers = []
        
        # Parse servers
        if "requires_servers" in metadata:
            servers = cls._normalize_list(metadata["requires_servers"])
        elif "requires-servers" in metadata:
            servers = cls._normalize_list(metadata["requires-servers"])
        
        # Parse tools (multiple naming conventions)
        if "requires_tools" in metadata:
            tools.extend(cls._normalize_list(metadata["requires_tools"]))
        elif "requires-tools" in metadata:
            tools.extend(cls._normalize_list(metadata["requires-tools"]))
            
        # Support existing allowed-tools convention for backward compatibility
        if "allowed-tools" in metadata:
            tools.extend(cls._normalize_list(metadata["allowed-tools"]))
            
        # Parse environment variables
        if "requires_env" in metadata:
            env_vars = cls._normalize_list(metadata["requires_env"])
        elif "requires-env" in metadata:
            env_vars = cls._normalize_list(metadata["requires-env"])
            
        # OpenClaw hints (passthrough)
        if "openclaw" in metadata:
            openclaw_hints = metadata["openclaw"] if isinstance(metadata["openclaw"], dict) else {}

        # Parse graceful-degradation fallback declarations. A fallback skill is
        # surfaced only when its target capability is ABSENT (inverse of requires).
        if "fallback_for_tools" in metadata:
            fallback_for_tools = cls._normalize_list(metadata["fallback_for_tools"])
        elif "fallback-for-tools" in metadata:
            fallback_for_tools = cls._normalize_list(metadata["fallback-for-tools"])

        if "fallback_for_servers" in metadata:
            fallback_for_servers = cls._normalize_list(metadata["fallback_for_servers"])
        elif "fallback-for-servers" in metadata:
            fallback_for_servers = cls._normalize_list(metadata["fallback-for-servers"])

        return cls(
            servers=servers,
            tools=tools,
            env_vars=env_vars, 
            openclaw_hints=openclaw_hints,
            fallback_for_tools=fallback_for_tools,
            fallback_for_servers=fallback_for_servers
        )
    
    @staticmethod
    def _normalize_list(value: Union[str, List[str]]) -> List[str]:
        """Normalize string or list to list of strings."""
        if isinstance(value, str):
            # Support both comma-separated and space-separated strings
            return [item.strip() for item in value.replace(',', ' ').split() if item.strip()]
        elif isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        else:
            return []
    
    def is_empty(self) -> bool:
        """Check if no requirements are specified."""
        return not any([
            self.servers, self.tools, self.env_vars, self.openclaw_hints,
            self.fallback_for_tools, self.fallback_for_servers,
        ])
    
    def __bool__(self) -> bool:
        """Truth value: True if any requirements are specified."""
        return not self.is_empty()


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
    allowed_tools: Optional[object] = None  # str | list[str]
    metadata: dict = field(default_factory=dict)
    path: Optional[Path] = None
    # Claude Code extended frontmatter (optional)
    when_to_use: Optional[str] = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    argument_hint: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    context: Optional[str] = None  # "fork" or None
    agent: Optional[str] = None
    hooks: Optional[dict] = None
    paths: Optional[object] = None  # list[str] glob patterns
    shell: Optional[str] = None  # "bash" | "powershell"
    # Capability requirements (new)
    requirements: Optional[SkillRequirements] = None
    # Provenance + usage telemetry (read by lifecycle/curator plugins).
    # These are protocol-only data fields; retention policy lives in plugins.
    agent_created: bool = False
    created_at: Optional[str] = None  # ISO 8601 timestamp
    use_count: int = 0
    last_used: Optional[str] = None  # ISO 8601 timestamp
    patch_count: int = 0

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
        if self.when_to_use is not None:
            result["when_to_use"] = self.when_to_use
        if self.disable_model_invocation:
            result["disable-model-invocation"] = True
        if not self.user_invocable:
            result["user-invocable"] = False
        if self.argument_hint is not None:
            result["argument-hint"] = self.argument_hint
        if self.model is not None:
            result["model"] = self.model
        if self.effort is not None:
            result["effort"] = self.effort
        if self.context is not None:
            result["context"] = self.context
        if self.agent is not None:
            result["agent"] = self.agent
        if self.hooks is not None:
            result["hooks"] = self.hooks
        if self.paths is not None:
            result["paths"] = self.paths
        if self.shell is not None:
            result["shell"] = self.shell
        if self.agent_created:
            result["agent-created"] = True
        if self.created_at is not None:
            result["created-at"] = self.created_at
        if self.use_count:
            result["use-count"] = self.use_count
        if self.last_used is not None:
            result["last-used"] = self.last_used
        if self.patch_count:
            result["patch-count"] = self.patch_count
        return result

    @property
    def idle_days(self) -> Optional[float]:
        """Days since the skill was last used (or created if never used).

        Returns None when no timestamp is available. Used by lifecycle
        curator plugins to decide active -> stale -> archived transitions.
        """
        from datetime import datetime, timezone

        ref = self.last_used or self.created_at
        if not ref:
            return None
        try:
            ts = datetime.fromisoformat(ref)
        except ValueError:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        return delta.total_seconds() / 86400.0


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
