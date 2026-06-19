"""
Unified configuration resolver for PraisonAI CLI.

Implements a single, project-aware configuration hierarchy with proper precedence:
1. Built-in defaults
2. Global user config (~/.praisonai/config.yaml)
3. Project config (discovered by walking up from cwd)
4. Environment variables
5. Explicit CLI flags

Supports deep-merge semantics and backward compatibility with legacy paths.
"""

import os
import json
import toml
import yaml
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from functools import lru_cache

from ..utils.project import get_git_root


@dataclass
class AgentDefaults:
    """Agent configuration defaults."""
    model: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # Note: Only stored for env var reference, not in file
    tools: List[str] = field(default_factory=list)
    toolset: Optional[str] = None
    default_agent: Optional[str] = None
    memory: Optional[Union[bool, Dict[str, Any]]] = None
    stream: bool = True
    temperature: float = 0.7
    max_tokens: int = 16000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values and api_key."""
        result = {}
        for key, value in asdict(self).items():
            if key == 'api_key':
                continue  # Never serialize API key
            if value is not None:
                if isinstance(value, list) and not value:
                    continue  # Skip empty lists
                result[key] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentDefaults":
        """Create from dictionary."""
        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class RAGConfig:
    """RAG/Knowledge configuration."""
    collection: str = "default"
    top_k: int = 5
    hybrid: bool = False
    rerank: bool = False
    min_score: float = 0.0
    include_citations: bool = True
    max_context_tokens: int = 4000
    vector_store: str = "chroma"
    vector_store_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGConfig":
        """Create from dictionary."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class ResolvedConfig:
    """
    Complete resolved configuration with provenance tracking.
    
    Combines all configuration sources into a single, validated structure.
    """
    # Core agent defaults
    agent: AgentDefaults = field(default_factory=AgentDefaults)
    
    # RAG configuration
    rag: RAGConfig = field(default_factory=RAGConfig)
    
    # Output settings (from existing schema)
    output_format: str = "text"
    color: bool = True
    verbose: bool = False
    quiet: bool = False
    
    # Telemetry
    telemetry: bool = True
    
    # Provenance tracking
    sources: List[str] = field(default_factory=list)
    
    # Extra settings for extensibility
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent": self.agent.to_dict(),
            "rag": self.rag.to_dict(),
            "output": {
                "format": self.output_format,
                "color": self.color,
                "verbose": self.verbose,
                "quiet": self.quiet,
            },
            "telemetry": self.telemetry,
            **self.extra
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResolvedConfig":
        """Create from dictionary."""
        agent_data = data.get("agent", {})
        rag_data = data.get("rag", {})
        output_data = data.get("output", {})
        
        # Extract known top-level fields
        known_keys = {"agent", "rag", "output", "telemetry", "sources"}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        
        return cls(
            agent=AgentDefaults.from_dict(agent_data),
            rag=RAGConfig.from_dict(rag_data),
            output_format=output_data.get("format", "text"),
            color=output_data.get("color", True),
            verbose=output_data.get("verbose", False),
            quiet=output_data.get("quiet", False),
            telemetry=data.get("telemetry", True),
            sources=data.get("sources", []),
            extra=extra,
        )


class ConfigResolver:
    """
    Unified configuration resolver with project-aware hierarchy.
    
    Implements walk-up discovery and deep-merge semantics.
    """
    
    # Config file names to search for (in order of preference)
    PROJECT_CONFIG_NAMES = [
        ".praisonai/config.yaml",
        ".praisonai/config.yml",
        "praison.yaml",
        "praison.yml",
        ".praison/config.toml",  # Legacy, backward compat
    ]
    
    def __init__(self, cwd: Optional[Path] = None):
        """
        Initialize the resolver.
        
        Args:
            cwd: Current working directory to start discovery from
        """
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self._cache: Optional[ResolvedConfig] = None
    
    def resolve(
        self,
        cli_args: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> ResolvedConfig:
        """
        Resolve configuration from all sources.
        
        Args:
            cli_args: CLI arguments (highest precedence)
            force_refresh: Force re-resolution, ignoring cache
            
        Returns:
            Fully resolved configuration with provenance
        """
        if self._cache and not force_refresh and not cli_args:
            return self._cache
        
        # Start with defaults
        config = ResolvedConfig()
        config.sources.append("defaults")
        
        # Layer 2: Global user config
        global_config = self._load_global_config()
        if global_config:
            config = self._merge_configs(config, global_config)
            config.sources.append(f"global:{global_config['_source']}")
        
        # Layer 3: Project config (with walk-up discovery)
        project_config = self._load_project_config()
        if project_config:
            config = self._merge_configs(config, project_config)
            config.sources.append(f"project:{project_config['_source']}")
        
        # Layer 4: Environment variables
        env_config = self._load_env_config()
        if env_config:
            config = self._merge_configs(config, env_config)
            config.sources.append("environment")
        
        # Layer 5: CLI arguments (if provided)
        if cli_args:
            cli_config = self._process_cli_args(cli_args)
            config = self._merge_configs(config, cli_config)
            config.sources.append("cli")
        
        # Cache if no CLI args (CLI args are transient)
        if not cli_args:
            self._cache = config
        
        return config
    
    def _load_global_config(self) -> Optional[Dict[str, Any]]:
        """Load global user configuration."""
        configs = []
        
        # Check ~/.praisonai/config.yaml (preferred)
        praisonai_home = Path.home() / ".praisonai"
        for name in ["config.yaml", "config.yml"]:
            config_path = praisonai_home / name
            if config_path.exists():
                data = self._read_config_file(config_path)
                if data:
                    data["_source"] = str(config_path)
                    configs.append(data)
                    break
        
        # Check legacy ~/.praison/config.toml for backward compat
        legacy_path = Path.home() / ".praison" / "config.toml"
        if legacy_path.exists() and not configs:
            data = self._read_config_file(legacy_path)
            if data:
                data["_source"] = str(legacy_path)
                # Map legacy RAG-centric config to new schema
                data = self._migrate_legacy_config(data)
                configs.append(data)
        
        # Check legacy ~/.praisonai/.env for model/provider
        env_path = praisonai_home / ".env"
        if env_path.exists():
            env_data = self._read_env_file(env_path)
            if env_data and not configs:
                configs.append(env_data)
            elif env_data and configs:
                # Merge env data into existing config
                configs[0] = self._deep_merge(configs[0], env_data)
        
        return configs[0] if configs else None
    
    def _load_project_config(self) -> Optional[Dict[str, Any]]:
        """Load project configuration with walk-up discovery."""
        # Try git root first
        git_root = get_git_root(str(self.cwd))
        search_paths = []
        
        if git_root:
            search_paths.append(git_root)
        
        # Walk up from cwd to root (or git root if found)
        current = self.cwd.resolve()
        stop_at = git_root if git_root else Path("/")
        
        while current != current.parent and current != stop_at:
            if current not in search_paths:
                search_paths.append(current)
            current = current.parent
        
        # Search for config files
        for search_dir in search_paths:
            for config_name in self.PROJECT_CONFIG_NAMES:
                config_path = search_dir / config_name
                if config_path.exists():
                    data = self._read_config_file(config_path)
                    if data:
                        data["_source"] = str(config_path)
                        # Migrate legacy format if needed
                        if config_name.endswith(".toml"):
                            data = self._migrate_legacy_config(data)
                        return data
        
        return None
    
    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}
        
        # Model/provider settings
        model_env_vars = [
            ("MODEL_NAME", ["agent", "model"]),
            ("OPENAI_MODEL_NAME", ["agent", "model"]),
            ("PRAISONAI_MODEL", ["agent", "model"]),
            ("PRAISONAI_PROVIDER", ["agent", "provider"]),
            ("OPENAI_BASE_URL", ["agent", "base_url"]),
            ("OPENAI_API_BASE", ["agent", "base_url"]),
            ("PRAISONAI_BASE_URL", ["agent", "base_url"]),
        ]
        
        for env_var, path in model_env_vars:
            value = os.environ.get(env_var)
            if value:
                self._set_nested(config, path, value)
        
        # Output settings
        output_env_vars = [
            ("PRAISONAI_OUTPUT_FORMAT", ["output", "format"]),
            ("PRAISONAI_COLOR", ["output", "color"]),
            ("PRAISONAI_VERBOSE", ["output", "verbose"]),
            ("PRAISONAI_QUIET", ["output", "quiet"]),
        ]
        
        for env_var, path in output_env_vars:
            value = os.environ.get(env_var)
            if value:
                # Convert string bools
                if env_var.endswith(("COLOR", "VERBOSE", "QUIET")):
                    value = value.lower() in ("true", "1", "yes")
                self._set_nested(config, path, value)
        
        # Telemetry
        telemetry = os.environ.get("PRAISONAI_TELEMETRY")
        if telemetry:
            config["telemetry"] = telemetry.lower() in ("true", "1", "yes")
        
        return config if config else {}
    
    def _process_cli_args(self, cli_args: Dict[str, Any]) -> Dict[str, Any]:
        """Process CLI arguments into config structure."""
        config = {}
        
        # Map common CLI args to config paths
        arg_mapping = {
            "model": ["agent", "model"],
            "provider": ["agent", "provider"],
            "base_url": ["agent", "base_url"],
            "temperature": ["agent", "temperature"],
            "max_tokens": ["agent", "max_tokens"],
            "verbose": ["output", "verbose"],
            "quiet": ["output", "quiet"],
            "no_color": ["output", "color"],
            "output_format": ["output", "format"],
        }
        
        for arg, path in arg_mapping.items():
            if arg in cli_args and cli_args[arg] is not None:
                value = cli_args[arg]
                # Handle no_color flag
                if arg == "no_color":
                    value = not value
                self._set_nested(config, path, value)
        
        # Handle tools/toolset
        if "tools" in cli_args and cli_args["tools"]:
            config.setdefault("agent", {})["tools"] = cli_args["tools"]
        if "toolset" in cli_args and cli_args["toolset"]:
            config.setdefault("agent", {})["toolset"] = cli_args["toolset"]
        
        return config
    
    def _read_config_file(self, path: Path) -> Optional[Dict[str, Any]]:
        """Read a configuration file (YAML or TOML)."""
        try:
            content = path.read_text()
            
            if path.suffix in (".yaml", ".yml"):
                return yaml.safe_load(content) or {}
            elif path.suffix == ".toml":
                return toml.loads(content)
            elif path.suffix == ".json":
                return json.loads(content)
            else:
                # Try to detect format
                try:
                    return yaml.safe_load(content) or {}
                except:
                    try:
                        return toml.loads(content)
                    except:
                        return None
        except Exception:
            return None
    
    def _read_env_file(self, path: Path) -> Dict[str, Any]:
        """Read a .env file and convert to config structure."""
        config = {}
        
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    
                    # Map known .env keys to config structure
                    if key == "model":
                        self._set_nested(config, ["agent", "model"], value)
                    elif key == "provider":
                        self._set_nested(config, ["agent", "provider"], value)
        except Exception:
            pass
        
        return config
    
    def _migrate_legacy_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate legacy config format to new schema."""
        migrated = {}
        
        # Handle old RAGCliConfig format
        if "collection" in data or "vector_store_provider" in data:
            migrated["rag"] = {}
            rag_keys = [
                "collection", "top_k", "hybrid", "rerank", "min_score",
                "include_citations", "max_context_tokens", "vector_store_path"
            ]
            for key in rag_keys:
                if key in data:
                    if key == "vector_store_provider":
                        migrated["rag"]["vector_store"] = data[key]
                    else:
                        migrated["rag"][key] = data[key]
        
        # Handle model in legacy format
        if "model" in data and "agent" not in migrated:
            migrated.setdefault("agent", {})["model"] = data["model"]
        
        # Preserve other keys
        for key, value in data.items():
            if key not in ["collection", "top_k", "hybrid", "rerank", "min_score",
                           "include_citations", "max_context_tokens", "vector_store_path",
                           "vector_store_provider", "model", "_source"]:
                migrated[key] = value
        
        # Preserve source
        if "_source" in data:
            migrated["_source"] = data["_source"]
        
        return migrated
    
    def _merge_configs(self, base: ResolvedConfig, overlay: Dict[str, Any]) -> ResolvedConfig:
        """Merge overlay config into base config."""
        # Convert base to dict for merging
        base_dict = base.to_dict()
        base_dict["sources"] = base.sources
        
        # Deep merge
        merged_dict = self._deep_merge(base_dict, overlay)
        
        # Convert back to ResolvedConfig
        result = ResolvedConfig.from_dict(merged_dict)
        result.sources = base.sources  # Preserve sources list
        
        return result
    
    def _deep_merge(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge overlay into base dictionary."""
        result = base.copy()
        
        for key, value in overlay.items():
            if key == "_source":
                continue  # Skip internal metadata
                
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    # Recursive merge for nested dicts
                    result[key] = self._deep_merge(result[key], value)
                elif isinstance(result[key], list) and isinstance(value, list):
                    # Concatenate lists (could be configurable)
                    result[key] = result[key] + value
                else:
                    # Scalar override
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    def _set_nested(self, d: Dict[str, Any], path: List[str], value: Any) -> None:
        """Set a nested value in a dictionary."""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value


# Singleton instance for convenient access
_default_resolver: Optional[ConfigResolver] = None


def get_resolver(cwd: Optional[Path] = None, reset: bool = False) -> ConfigResolver:
    """
    Get the default configuration resolver.
    
    Args:
        cwd: Working directory for project discovery
        reset: Force create a new resolver
        
    Returns:
        ConfigResolver instance
    """
    global _default_resolver
    
    if reset or _default_resolver is None or (cwd and _default_resolver.cwd != cwd):
        _default_resolver = ConfigResolver(cwd)
    
    return _default_resolver


def resolve_config(
    cwd: Optional[Path] = None,
    cli_args: Optional[Dict[str, Any]] = None
) -> ResolvedConfig:
    """
    Convenience function to resolve configuration.
    
    Args:
        cwd: Working directory for project discovery
        cli_args: CLI arguments to overlay
        
    Returns:
        Resolved configuration
    """
    resolver = get_resolver(cwd)
    return resolver.resolve(cli_args)