"""
ACP configuration management.

Handles configuration precedence:
1. CLI flags (highest)
2. Environment variables
3. Config file (~/.praison/config.yaml)
4. Defaults (lowest)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ACPConfig:
    """Configuration for ACP server."""
    
    # Workspace settings
    workspace: Path = field(default_factory=Path.cwd)
    
    # Agent settings
    agent: str = "default"
    agents_config: Optional[Path] = None
    router_enabled: bool = False
    model: Optional[str] = None
    
    # Session settings
    resume_session: Optional[str] = None
    resume_last: bool = False
    
    # Permission settings
    read_only: bool = True
    allow_write: bool = False
    allow_shell: bool = False
    allow_network: bool = False
    approval_mode: str = "manual"  # manual, auto, scoped
    
    # Workspace boundaries
    allowed_paths: List[Path] = field(default_factory=list)
    
    # Debug settings
    debug: bool = False
    
    # Profile
    profile: Optional[str] = None
    
    def __post_init__(self):
        """Validate and normalize configuration."""
        if isinstance(self.workspace, str):
            self.workspace = Path(self.workspace).resolve()
        
        if self.agents_config and isinstance(self.agents_config, str):
            self.agents_config = Path(self.agents_config)
        
        # Set up default allowed paths
        if not self.allowed_paths:
            self.allowed_paths = [
                self.workspace,
                Path.home() / ".praison",
            ]
        
        # Normalize allowed paths
        self.allowed_paths = [
            Path(p).resolve() if isinstance(p, str) else p.resolve()
            for p in self.allowed_paths
        ]
    
    @classmethod
    def from_env(cls) -> "ACPConfig":
        """Create config from environment variables."""
        return cls(
            workspace=Path(os.environ.get("PRAISONAI_WORKSPACE", ".")).resolve(),
            agent=os.environ.get("PRAISONAI_AGENT", "default"),
            model=os.environ.get("PRAISONAI_MODEL") or os.environ.get("OPENAI_MODEL"),
            debug=os.environ.get("PRAISONAI_DEBUG", "").lower() in ("1", "true", "yes"),
            read_only=os.environ.get("PRAISONAI_READ_ONLY", "true").lower() in ("1", "true", "yes"),
            approval_mode=os.environ.get("PRAISONAI_APPROVAL_MODE", "manual"),
        )
    
    @classmethod
    def from_file(cls, path: Optional[Path] = None) -> "ACPConfig":
        """Load config from YAML file."""
        if path is None:
            path = Path.home() / ".praison" / "config.yaml"
        
        if not path.exists():
            return cls()
        
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            
            acp_config = data.get("acp", {})
            return cls(
                workspace=Path(acp_config.get("workspace", ".")).resolve(),
                agent=acp_config.get("agent", "default"),
                model=acp_config.get("model"),
                debug=acp_config.get("debug", False),
                read_only=acp_config.get("read_only", True),
                approval_mode=acp_config.get("approval_mode", "manual"),
            )
        except Exception:
            return cls()
    
    @classmethod
    def merge(cls, *configs: "ACPConfig") -> "ACPConfig":
        """Merge multiple configs, later configs override earlier ones."""
        result = cls()
        for config in configs:
            for field_name in [
                "workspace", "agent", "agents_config", "router_enabled",
                "model", "resume_session", "resume_last", "read_only",
                "allow_write", "allow_shell", "allow_network", "approval_mode",
                "debug", "profile"
            ]:
                value = getattr(config, field_name)
                # Only override if value is not default/None
                if value is not None and value != getattr(cls(), field_name, None):
                    setattr(result, field_name, value)
        return result
    
    def is_path_allowed(self, path: Path) -> bool:
        """Check if a path is within allowed boundaries."""
        path = Path(path).resolve()
        return any(
            path == allowed or allowed in path.parents
            for allowed in self.allowed_paths
        )
    
    def can_write(self) -> bool:
        """Check if write operations are allowed."""
        return not self.read_only or self.allow_write
    
    def can_execute_shell(self) -> bool:
        """Check if shell commands are allowed."""
        return self.allow_shell
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "workspace": str(self.workspace),
            "agent": self.agent,
            "agents_config": str(self.agents_config) if self.agents_config else None,
            "router_enabled": self.router_enabled,
            "model": self.model,
            "resume_session": self.resume_session,
            "resume_last": self.resume_last,
            "read_only": self.read_only,
            "allow_write": self.allow_write,
            "allow_shell": self.allow_shell,
            "allow_network": self.allow_network,
            "approval_mode": self.approval_mode,
            "debug": self.debug,
            "profile": self.profile,
        }
