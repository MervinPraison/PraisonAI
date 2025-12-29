"""
Recipe Policy Module

Provides policy management for recipes:
- Policy packs (reusable org-wide policies)
- Tool allow/deny enforcement
- Network/file restrictions
- PII defaults
- Mode enforcement (dev/prod)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import yaml


class PolicyError(Exception):
    """Base exception for policy operations."""
    pass


class PolicyDeniedError(PolicyError):
    """Action denied by policy."""
    pass


# Default denied tools (dangerous by default)
DEFAULT_DENIED_TOOLS: Set[str] = {
    "shell.exec",
    "shell.run",
    "shell_tool",
    "execute_command",
    "file.write",
    "file.delete",
    "fs.write",
    "fs.delete",
    "network.unrestricted",
    "db.write",
    "db.delete",
    "db.drop",
}

# Default allowed tools (safe by default)
DEFAULT_ALLOWED_TOOLS: Set[str] = {
    "web.search",
    "web_search",
    "tavily_search",
    "file.read",
    "fs.read",
    "db.query",
    "db.read",
}


class PolicyPack:
    """
    Reusable policy pack for org-wide policy management.
    
    Policy pack YAML format:
    ```yaml
    name: my-org-policy
    version: "1.0"
    description: Organization-wide security policy
    
    tools:
      allow:
        - web.search
        - db.query
      deny:
        - shell.exec
        - file.write
    
    network:
      allow_domains:
        - api.openai.com
        - api.anthropic.com
      deny_domains:
        - localhost
        - 127.0.0.1
    
    files:
      allow_paths:
        - /tmp
        - ./outputs
      deny_paths:
        - /etc
        - /var
    
    pii:
      mode: redact  # allow, deny, redact
      fields:
        - email
        - phone
        - ssn
    
    data:
      retention_days: 30
      export_allowed: true
    
    modes:
      dev:
        allow_interactive_prompts: true
        strict_tool_enforcement: false
      prod:
        allow_interactive_prompts: false
        strict_tool_enforcement: true
        require_auth: true
    ```
    """
    
    def __init__(
        self,
        name: str = "default",
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize policy pack."""
        self.name = name
        self.config = config or {}
        
        # Tool policies
        self.allowed_tools: Set[str] = set(self.config.get("tools", {}).get("allow", []))
        self.denied_tools: Set[str] = set(self.config.get("tools", {}).get("deny", []))
        
        # Add defaults
        self.denied_tools.update(DEFAULT_DENIED_TOOLS)
        
        # Network policies
        self.allowed_domains: Set[str] = set(self.config.get("network", {}).get("allow_domains", []))
        self.denied_domains: Set[str] = set(self.config.get("network", {}).get("deny_domains", []))
        
        # File policies
        self.allowed_paths: List[str] = self.config.get("files", {}).get("allow_paths", [])
        self.denied_paths: List[str] = self.config.get("files", {}).get("deny_paths", [])
        
        # PII policy
        self.pii_mode: str = self.config.get("pii", {}).get("mode", "allow")
        self.pii_fields: List[str] = self.config.get("pii", {}).get("fields", [])
        
        # Data policy
        self.retention_days: Optional[int] = self.config.get("data", {}).get("retention_days")
        self.export_allowed: bool = self.config.get("data", {}).get("export_allowed", True)
        
        # Mode-specific settings
        self.modes: Dict[str, Dict[str, Any]] = self.config.get("modes", {})
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "PolicyPack":
        """Load policy pack from file."""
        path = Path(path)
        if not path.exists():
            raise PolicyError(f"Policy file not found: {path}")
        
        with open(path) as f:
            if path.suffix in (".yaml", ".yml"):
                config = yaml.safe_load(f)
            else:
                config = json.load(f)
        
        name = config.get("name", path.stem)
        return cls(name=name, config=config)
    
    def save(self, path: Union[str, Path]):
        """Save policy pack to file."""
        path = Path(path)
        
        data = {
            "name": self.name,
            "version": self.config.get("version", "1.0"),
            "description": self.config.get("description", ""),
            "tools": {
                "allow": list(self.allowed_tools),
                "deny": list(self.denied_tools),
            },
            "network": {
                "allow_domains": list(self.allowed_domains),
                "deny_domains": list(self.denied_domains),
            },
            "files": {
                "allow_paths": self.allowed_paths,
                "deny_paths": self.denied_paths,
            },
            "pii": {
                "mode": self.pii_mode,
                "fields": self.pii_fields,
            },
            "data": {
                "retention_days": self.retention_days,
                "export_allowed": self.export_allowed,
            },
            "modes": self.modes,
        }
        
        with open(path, "w") as f:
            if path.suffix in (".yaml", ".yml"):
                yaml.dump(data, f, default_flow_style=False)
            else:
                json.dump(data, f, indent=2)
    
    def check_tool(self, tool_id: str, mode: str = "dev") -> bool:
        """
        Check if a tool is allowed.
        
        Args:
            tool_id: Tool identifier
            mode: Execution mode (dev/prod)
            
        Returns:
            True if allowed
            
        Raises:
            PolicyDeniedError: If tool is denied
        """
        # Explicit deny always wins
        if tool_id in self.denied_tools:
            raise PolicyDeniedError(f"Tool denied by policy: {tool_id}")
        
        # Check mode-specific settings
        mode_config = self.modes.get(mode, {})
        strict = mode_config.get("strict_tool_enforcement", mode == "prod")
        
        if strict:
            # In strict mode, tool must be explicitly allowed
            if tool_id not in self.allowed_tools and tool_id not in DEFAULT_ALLOWED_TOOLS:
                raise PolicyDeniedError(f"Tool not in allowlist (strict mode): {tool_id}")
        
        return True
    
    def check_domain(self, domain: str) -> bool:
        """Check if a network domain is allowed."""
        if domain in self.denied_domains:
            raise PolicyDeniedError(f"Domain denied by policy: {domain}")
        
        if self.allowed_domains and domain not in self.allowed_domains:
            raise PolicyDeniedError(f"Domain not in allowlist: {domain}")
        
        return True
    
    def check_path(self, path: str) -> bool:
        """Check if a file path is allowed."""
        path_obj = Path(path).resolve()
        
        for denied in self.denied_paths:
            if str(path_obj).startswith(str(Path(denied).resolve())):
                raise PolicyDeniedError(f"Path denied by policy: {path}")
        
        if self.allowed_paths:
            allowed = False
            for allow in self.allowed_paths:
                if str(path_obj).startswith(str(Path(allow).resolve())):
                    allowed = True
                    break
            if not allowed:
                raise PolicyDeniedError(f"Path not in allowlist: {path}")
        
        return True
    
    def get_data_policy(self) -> Dict[str, Any]:
        """Get data policy configuration."""
        return {
            "pii": {
                "mode": self.pii_mode,
                "fields": self.pii_fields,
            },
            "retention_days": self.retention_days,
            "export_allowed": self.export_allowed,
        }
    
    def get_mode_config(self, mode: str) -> Dict[str, Any]:
        """Get mode-specific configuration."""
        return self.modes.get(mode, {})
    
    def merge(self, other: "PolicyPack") -> "PolicyPack":
        """
        Merge another policy pack (other takes precedence).
        
        Args:
            other: Policy pack to merge
            
        Returns:
            New merged policy pack
        """
        merged_config = {
            "name": f"{self.name}+{other.name}",
            "tools": {
                "allow": list(self.allowed_tools | other.allowed_tools),
                "deny": list(self.denied_tools | other.denied_tools),
            },
            "network": {
                "allow_domains": list(self.allowed_domains | other.allowed_domains),
                "deny_domains": list(self.denied_domains | other.denied_domains),
            },
            "files": {
                "allow_paths": self.allowed_paths + other.allowed_paths,
                "deny_paths": self.denied_paths + other.denied_paths,
            },
            "pii": {
                "mode": other.pii_mode or self.pii_mode,
                "fields": list(set(self.pii_fields + other.pii_fields)),
            },
            "data": {
                "retention_days": other.retention_days or self.retention_days,
                "export_allowed": other.export_allowed and self.export_allowed,
            },
            "modes": {**self.modes, **other.modes},
        }
        
        return PolicyPack(name=merged_config["name"], config=merged_config)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "tools": {
                "allow": list(self.allowed_tools),
                "deny": list(self.denied_tools),
            },
            "network": {
                "allow_domains": list(self.allowed_domains),
                "deny_domains": list(self.denied_domains),
            },
            "files": {
                "allow_paths": self.allowed_paths,
                "deny_paths": self.denied_paths,
            },
            "pii": {
                "mode": self.pii_mode,
                "fields": self.pii_fields,
            },
            "data": {
                "retention_days": self.retention_days,
                "export_allowed": self.export_allowed,
            },
            "modes": self.modes,
        }


# Default policy packs
DEFAULT_DEV_POLICY = PolicyPack(
    name="default-dev",
    config={
        "tools": {
            "allow": list(DEFAULT_ALLOWED_TOOLS),
            "deny": list(DEFAULT_DENIED_TOOLS),
        },
        "pii": {"mode": "allow"},
        "modes": {
            "dev": {
                "allow_interactive_prompts": True,
                "strict_tool_enforcement": False,
            },
        },
    },
)

DEFAULT_PROD_POLICY = PolicyPack(
    name="default-prod",
    config={
        "tools": {
            "allow": list(DEFAULT_ALLOWED_TOOLS),
            "deny": list(DEFAULT_DENIED_TOOLS),
        },
        "pii": {"mode": "redact", "fields": ["email", "phone", "ssn"]},
        "modes": {
            "prod": {
                "allow_interactive_prompts": False,
                "strict_tool_enforcement": True,
                "require_auth": True,
            },
        },
    },
)


def get_default_policy(mode: str = "dev") -> PolicyPack:
    """Get default policy for a mode."""
    if mode == "prod":
        return DEFAULT_PROD_POLICY
    return DEFAULT_DEV_POLICY


def load_policy(
    policy_path: Optional[Union[str, Path]] = None,
    mode: str = "dev",
) -> PolicyPack:
    """
    Load policy from file or return default.
    
    Args:
        policy_path: Path to policy file (optional)
        mode: Execution mode
        
    Returns:
        PolicyPack instance
    """
    if policy_path:
        return PolicyPack.load(policy_path)
    return get_default_policy(mode)


def check_tool_policy(
    tool_id: str,
    policy: Optional[PolicyPack] = None,
    mode: str = "dev",
) -> bool:
    """
    Check if a tool is allowed by policy.
    
    Args:
        tool_id: Tool identifier
        policy: Policy pack (optional, uses default)
        mode: Execution mode
        
    Returns:
        True if allowed
        
    Raises:
        PolicyDeniedError: If tool is denied
    """
    policy = policy or get_default_policy(mode)
    return policy.check_tool(tool_id, mode)
