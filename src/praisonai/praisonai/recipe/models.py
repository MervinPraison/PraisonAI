"""
Recipe Data Models

Defines the core data structures for recipe execution.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional


class ExitCode(IntEnum):
    """Stable exit codes for CLI operations."""
    SUCCESS = 0
    GENERAL_ERROR = 1
    VALIDATION_ERROR = 2
    RUNTIME_ERROR = 3
    POLICY_DENIED = 4
    TIMEOUT = 5
    MISSING_DEPS = 6
    NOT_FOUND = 7


class RecipeStatus:
    """Recipe execution status constants."""
    SUCCESS = "success"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    POLICY_DENIED = "policy_denied"
    TIMEOUT = "timeout"
    MISSING_DEPS = "missing_deps"
    VALIDATION_ERROR = "validation_error"


@dataclass
class RecipeResult:
    """
    Result of a recipe execution.
    
    Attributes:
        run_id: Unique identifier for this execution
        recipe: Recipe name
        version: Recipe version
        status: Execution status (success, failed, dry_run, policy_denied, etc.)
        output: Recipe-specific output data
        metrics: Execution metrics (duration, tokens, etc.)
        error: Error message if failed
        trace: Tracing identifiers (run_id, trace_id, session_id, agent_id)
    """
    run_id: str
    recipe: str
    version: str
    status: str
    output: Any = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    trace: Dict[str, str] = field(default_factory=dict)
    
    @property
    def ok(self) -> bool:
        """Check if execution was successful."""
        return self.status in (RecipeStatus.SUCCESS, RecipeStatus.DRY_RUN)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ok": self.ok,
            "run_id": self.run_id,
            "recipe": self.recipe,
            "version": self.version,
            "status": self.status,
            "output": self.output,
            "metrics": self.metrics,
            "error": self.error,
            "trace": self.trace,
        }
    
    def to_exit_code(self) -> int:
        """Convert status to CLI exit code."""
        status_to_code = {
            RecipeStatus.SUCCESS: ExitCode.SUCCESS,
            RecipeStatus.DRY_RUN: ExitCode.SUCCESS,
            RecipeStatus.FAILED: ExitCode.RUNTIME_ERROR,
            RecipeStatus.POLICY_DENIED: ExitCode.POLICY_DENIED,
            RecipeStatus.TIMEOUT: ExitCode.TIMEOUT,
            RecipeStatus.MISSING_DEPS: ExitCode.MISSING_DEPS,
            RecipeStatus.VALIDATION_ERROR: ExitCode.VALIDATION_ERROR,
        }
        return status_to_code.get(self.status, ExitCode.GENERAL_ERROR)


@dataclass
class RecipeEvent:
    """
    Streaming event from recipe execution.
    
    Attributes:
        event_type: Type of event (started, progress, log, output, completed, error)
        data: Event-specific data
        timestamp: ISO format timestamp
    """
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/SSE serialization."""
        return {
            "event": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }
    
    def to_sse(self) -> str:
        """Convert to Server-Sent Events format."""
        import json
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"


@dataclass
class RecipeConfig:
    """
    Recipe configuration and metadata.
    
    Attributes:
        name: Recipe name (kebab-case)
        version: SemVer version string
        description: Recipe description
        author: Author name or identifier
        license: License identifier (e.g., Apache-2.0)
        tags: Discovery tags
        requires: Dependencies (packages, env, tools, external)
        tools: Tool permissions (allow, deny)
        config_schema: JSON Schema for input configuration
        defaults: Default configuration values
        outputs: Expected output definitions
        governance: Governance settings (approval, cost limits, audit)
        data_policy: Data handling policy (PII, retention)
        path: Source path of the recipe
    """
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: Optional[str] = None
    license: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    # Dependencies
    requires: Dict[str, Any] = field(default_factory=dict)
    
    # Tool permissions
    tools: Dict[str, List[str]] = field(default_factory=dict)
    
    # Configuration
    config_schema: Dict[str, Any] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    
    # Outputs
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    
    # Governance
    governance: Dict[str, Any] = field(default_factory=dict)
    
    # Data policy
    data_policy: Dict[str, Any] = field(default_factory=dict)
    
    # Source path
    path: Optional[str] = None
    
    # Raw config dict
    raw: Dict[str, Any] = field(default_factory=dict)
    
    def get_allowed_tools(self) -> List[str]:
        """Get list of explicitly allowed tools."""
        return self.tools.get("allow", [])
    
    def get_denied_tools(self) -> List[str]:
        """Get list of explicitly denied tools."""
        return self.tools.get("deny", [])
    
    def get_required_packages(self) -> List[str]:
        """Get list of required Python packages."""
        packages = self.requires.get("packages", [])
        return [packages] if isinstance(packages, str) else packages
    
    def get_required_env(self) -> List[str]:
        """Get list of required environment variables."""
        env = self.requires.get("env", [])
        return [env] if isinstance(env, str) else env
    
    def get_required_tools(self) -> List[str]:
        """Get list of required tools."""
        tools = self.requires.get("tools", [])
        return [tools] if isinstance(tools, str) else tools
    
    def get_external_deps(self) -> List[Dict[str, Any]]:
        """Get list of external dependencies (ffmpeg, etc.)."""
        return self.requires.get("external", [])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "tags": self.tags,
            "requires": self.requires,
            "tools": self.tools,
            "config_schema": self.config_schema,
            "defaults": self.defaults,
            "outputs": self.outputs,
            "governance": self.governance,
            "data_policy": self.data_policy,
            "path": self.path,
        }


@dataclass
class ValidationResult:
    """Result of recipe validation."""
    valid: bool
    recipe: str
    version: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dependencies: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "recipe": self.recipe,
            "version": self.version,
            "errors": self.errors,
            "warnings": self.warnings,
            "dependencies": self.dependencies,
        }


@dataclass
class RecipeInfo:
    """Recipe information for listing/discovery."""
    name: str
    version: str
    description: str
    tags: List[str]
    path: str
    source: str  # local, package, github
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tags": self.tags,
            "path": self.path,
            "source": self.source,
        }
