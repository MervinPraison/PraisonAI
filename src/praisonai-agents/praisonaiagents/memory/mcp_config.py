"""
MCP Config Manager for PraisonAI Agents.

Provides JSON-based MCP server configuration support similar to:
- Cursor .cursor/mcp/*.mcpjson
- Windsurf MCP configuration

Features:
- Auto-discovery of MCP configs from .praison/mcp/
- JSON config files for MCP servers
- Environment variable support
- Easy server management

Storage Structure:
    .praison/mcp/
    ├── filesystem.json      # Filesystem MCP server
    ├── brave-search.json    # Brave search MCP server
    └── postgres.json        # PostgreSQL MCP server

Config File Format (JSON):
    {
        "name": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "env": {
            "SOME_VAR": "value"
        },
        "enabled": true,
        "description": "Filesystem access for the agent"
    }
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MCPConfig:
    """A single MCP server configuration."""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""
    file_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "enabled": self.enabled,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], file_path: Optional[str] = None) -> 'MCPConfig':
        return cls(
            name=data.get("name", ""),
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            file_path=file_path
        )
    
    def to_mcp_instance(self):
        """
        Convert this config to an MCP instance.
        
        Returns:
            MCP instance ready for use with agents
        """
        try:
            from praisonaiagents.tools.mcp import MCP
            
            # Resolve environment variables
            resolved_env = {}
            for key, value in self.env.items():
                if value.startswith("$"):
                    # Environment variable reference
                    env_var = value[1:]
                    resolved_env[key] = os.environ.get(env_var, value)
                else:
                    resolved_env[key] = value
            
            return MCP(
                command=self.command,
                args=self.args,
                env=resolved_env if resolved_env else None
            )
        except ImportError:
            logger.warning("MCP tools not available")
            return None


class MCPConfigManager:
    """
    Manages MCP server configurations for AI agents.
    
    Provides:
    - Auto-discovery of MCP configs from .praison/mcp/
    - Global configs from ~/.praison/mcp/
    - Easy server management
    """
    
    MCP_DIR_NAME = ".praison/mcp"
    SUPPORTED_EXTENSIONS = [".json", ".mcpjson"]
    
    def __init__(
        self,
        workspace_path: Optional[str] = None,
        global_mcp_path: Optional[str] = None,
        verbose: int = 0
    ):
        """
        Initialize MCPConfigManager.
        
        Args:
            workspace_path: Path to workspace/project root
            global_mcp_path: Path to global MCP configs (default: ~/.praison/mcp)
            verbose: Verbosity level
        """
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        self.global_mcp_path = Path(global_mcp_path) if global_mcp_path else Path.home() / ".praison" / "mcp"
        self.verbose = verbose
        
        self._configs: Dict[str, MCPConfig] = {}
        self._load_all_configs()
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message if verbose."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _load_config_file(self, file_path: Path, scope: str = "workspace") -> Optional[MCPConfig]:
        """Load a single MCP config file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            
            # Use filename as name if not specified
            if not data.get("name"):
                data["name"] = file_path.stem
            
            config = MCPConfig.from_dict(data, str(file_path))
            return config
        except json.JSONDecodeError as e:
            self._log(f"Invalid JSON in {file_path}: {e}", logging.WARNING)
            return None
        except Exception as e:
            self._log(f"Failed to load MCP config {file_path}: {e}", logging.WARNING)
            return None
    
    def _load_configs_from_dir(self, mcp_dir: Path, scope: str = "workspace"):
        """Load all MCP configs from a directory."""
        if not mcp_dir.exists():
            return
        
        for ext in self.SUPPORTED_EXTENSIONS:
            for file_path in mcp_dir.glob(f"*{ext}"):
                if file_path.is_file():
                    config = self._load_config_file(file_path, scope)
                    if config:
                        key = f"{scope}:{config.name}"
                        self._configs[key] = config
                        self._log(f"Loaded MCP config: {key}")
    
    def _load_all_configs(self):
        """Load all MCP configs from global and workspace directories."""
        self._configs.clear()
        
        # 1. Load global configs
        if self.global_mcp_path.exists():
            self._load_configs_from_dir(self.global_mcp_path, "global")
        
        # 2. Load workspace configs (override global)
        workspace_mcp_dir = self.workspace_path / self.MCP_DIR_NAME.replace("/", os.sep)
        if workspace_mcp_dir.exists():
            self._load_configs_from_dir(workspace_mcp_dir, "workspace")
        
        self._log(f"Loaded {len(self._configs)} MCP configs total")
    
    def reload(self):
        """Reload all configs from disk."""
        self._load_all_configs()
    
    def get_all_configs(self) -> List[MCPConfig]:
        """Get all loaded MCP configs."""
        return list(self._configs.values())
    
    def get_enabled_configs(self) -> List[MCPConfig]:
        """Get all enabled MCP configs."""
        return [c for c in self._configs.values() if c.enabled]
    
    def get_config(self, name: str) -> Optional[MCPConfig]:
        """Get a specific MCP config by name."""
        # Try workspace first, then global
        for scope in ["workspace", "global"]:
            key = f"{scope}:{name}"
            if key in self._configs:
                return self._configs[key]
        return None
    
    def get_mcp_tools(self, names: Optional[List[str]] = None) -> List:
        """
        Get MCP instances for use with agents.
        
        Args:
            names: Specific config names to load (None = all enabled)
            
        Returns:
            List of MCP instances
        """
        tools = []
        
        if names:
            configs = [self.get_config(name) for name in names]
            configs = [c for c in configs if c and c.enabled]
        else:
            configs = self.get_enabled_configs()
        
        for config in configs:
            mcp = config.to_mcp_instance()
            if mcp:
                tools.append(mcp)
        
        return tools
    
    def create_config(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        enabled: bool = True,
        description: str = "",
        scope: str = "workspace"
    ) -> MCPConfig:
        """
        Create a new MCP config file.
        
        Args:
            name: Config name (used as filename)
            command: Command to run (e.g., "npx")
            args: Command arguments
            env: Environment variables
            enabled: Whether the config is enabled
            description: Description of the MCP server
            scope: Where to save (global or workspace)
            
        Returns:
            Created MCPConfig object
        """
        # Determine save path
        if scope == "global":
            mcp_dir = self.global_mcp_path
        else:
            mcp_dir = self.workspace_path / self.MCP_DIR_NAME.replace("/", os.sep)
        
        mcp_dir.mkdir(parents=True, exist_ok=True)
        file_path = mcp_dir / f"{name}.json"
        
        # Build config
        config = MCPConfig(
            name=name,
            command=command,
            args=args or [],
            env=env or {},
            enabled=enabled,
            description=description,
            file_path=str(file_path)
        )
        
        # Write file
        file_path.write_text(
            json.dumps(config.to_dict(), indent=2),
            encoding="utf-8"
        )
        
        self._configs[f"{scope}:{name}"] = config
        self._log(f"Created MCP config '{name}' at {file_path}")
        
        return config
    
    def delete_config(self, name: str, scope: Optional[str] = None) -> bool:
        """
        Delete an MCP config file.
        
        Args:
            name: Config name to delete
            scope: Scope to delete from (None = try both)
            
        Returns:
            True if deleted, False if not found
        """
        scopes = [scope] if scope else ["workspace", "global"]
        
        for s in scopes:
            key = f"{s}:{name}"
            if key in self._configs:
                config = self._configs[key]
                if config.file_path:
                    try:
                        Path(config.file_path).unlink()
                        del self._configs[key]
                        self._log(f"Deleted MCP config '{name}' from {s}")
                        return True
                    except Exception as e:
                        self._log(f"Failed to delete config file: {e}", logging.ERROR)
        
        return False
    
    def enable_config(self, name: str) -> bool:
        """Enable an MCP config."""
        config = self.get_config(name)
        if config:
            config.enabled = True
            self._save_config(config)
            return True
        return False
    
    def disable_config(self, name: str) -> bool:
        """Disable an MCP config."""
        config = self.get_config(name)
        if config:
            config.enabled = False
            self._save_config(config)
            return True
        return False
    
    def _save_config(self, config: MCPConfig):
        """Save a config back to its file."""
        if config.file_path:
            Path(config.file_path).write_text(
                json.dumps(config.to_dict(), indent=2),
                encoding="utf-8"
            )
    
    def list_configs(self) -> List[Dict[str, Any]]:
        """
        List all MCP configs with metadata.
        
        Returns:
            List of config info dicts
        """
        configs = []
        for key, config in self._configs.items():
            scope = key.split(":")[0]
            configs.append({
                "name": config.name,
                "scope": scope,
                "command": config.command,
                "args": config.args,
                "enabled": config.enabled,
                "description": config.description,
                "file_path": config.file_path
            })
        
        return configs
