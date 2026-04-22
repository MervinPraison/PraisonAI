"""Workspace management for PraisonAI agents.

This module provides workspace isolation and security for agent operations,
particularly for bots and gateways that need to scope file operations to
specific directories.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional
import os

WorkspaceAccess = Literal["rw", "ro", "none"]
WorkspaceScope = Literal["shared", "session", "user", "agent"]


@dataclass(frozen=True)
class Workspace:
    """Workspace configuration for agent operations.
    
    Provides path containment and access control for file operations,
    ensuring agents can only access files within their designated workspace.
    
    Attributes:
        root: Absolute path to workspace directory (must exist, refuses "/")
        access: Access mode ("rw" = read-write, "ro" = read-only, "none" = copy-on-write sandbox)
        scope: Workspace scope level ("shared", "session", "user", "agent")
        session_key: Optional session identifier for scope resolution
    """
    
    root: Path
    access: WorkspaceAccess = "rw"
    scope: WorkspaceScope = "session"
    session_key: Optional[str] = None
    
    def __post_init__(self):
        """Validate workspace configuration after initialization."""
        # Always resolve symlinks so containment checks below are consistent
        # This fixes macOS issues where /tmp -> /private/tmp symlinks break containment
        object.__setattr__(self, 'root', self.root.resolve())
        
        # Security: refuse root filesystem access
        if str(self.root) in ('/', '\\', 'C:\\'):
            raise ValueError(f"Workspace root cannot be filesystem root: {self.root}")
        
        # Ensure workspace directory exists
        if not self.root.exists():
            try:
                self.root.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e:
                raise ValueError(f"Cannot create workspace directory {self.root}: {e}")
    
    def contains(self, path: str | Path) -> bool:
        """Check if a path is contained within this workspace.
        
        Args:
            path: Path to check (string or Path object)
            
        Returns:
            True if path is within workspace boundaries
        """
        try:
            resolved_path = self.resolve(path)
            return True
        except ValueError:
            return False
    
    def resolve(self, path: str | Path) -> Path:
        """Resolve a path against the workspace root with security checks.
        
        Args:
            path: Relative or absolute path to resolve
            
        Returns:
            Absolute path within workspace
            
        Raises:
            ValueError: If path escapes workspace or contains traversal attempts
        """
        if isinstance(path, str):
            path = Path(path)
        
        # Reject traversal components (proper part-wise check; substring search
        # would reject legitimate names like "v1..2.md").
        if has_traversal_component(str(path)):
            raise ValueError(f"Path traversal detected: {path}")
        
        # If path is absolute, check if it's within workspace
        if path.is_absolute():
            resolved = path.resolve()
        else:
            # Resolve relative to workspace root
            resolved = (self.root / path).resolve()
        
        # Security check: ensure resolved path is within workspace
        try:
            resolved.relative_to(self.root)
        except ValueError as e:
            raise ValueError(
                f"Path escapes workspace: {path} -> {resolved} (workspace: {self.root})"
            ) from e
        
        return resolved
    
    @classmethod
    def from_config(cls, config: Optional[object], *, session_key: str) -> "Workspace":
        """Create workspace from bot configuration.
        
        Args:
            config: BotConfig or similar configuration object
            session_key: Session identifier for workspace resolution
            
        Returns:
            Configured Workspace instance
        """
        # Extract workspace configuration from config object
        workspace_dir = None
        workspace_access = "rw"
        workspace_scope = "session"
        
        if config is not None:
            workspace_dir = getattr(config, 'workspace_dir', None)
            workspace_access = getattr(config, 'workspace_access', "rw")
            workspace_scope = getattr(config, 'workspace_scope', "session")
        
        # Default workspace directory resolution
        if not workspace_dir:
            # Default: ~/.praisonai/workspaces/<scope>/<session_key>
            home = Path.home()
            workspace_dir = home / ".praisonai" / "workspaces" / workspace_scope / session_key
        else:
            workspace_dir = Path(workspace_dir).expanduser()
        
        return cls(
            root=workspace_dir,
            access=workspace_access,
            scope=workspace_scope,
            session_key=session_key
        )
    
    def is_read_only(self) -> bool:
        """Check if workspace is in read-only mode."""
        return self.access == "ro"
    
    def is_sandbox_mode(self) -> bool:
        """Check if workspace is in copy-on-write sandbox mode."""
        return self.access == "none"
    
    def __str__(self) -> str:
        return f"Workspace(root={self.root}, access={self.access}, scope={self.scope})"


def validate_within_dir(path: Path, allowed_root: Path) -> bool:
    """Validate that a path is contained within an allowed root directory.
    
    Args:
        path: Path to validate
        allowed_root: Root directory that must contain the path
        
    Returns:
        True if path is within allowed_root, False otherwise
    """
    try:
        path.resolve().relative_to(allowed_root.resolve())
        return True
    except ValueError:
        return False


def has_traversal_component(path: str) -> bool:
    """Check if a path contains directory traversal components.
    
    Args:
        path: Path string to check
        
    Returns:
        True if path contains '..' or other suspicious patterns
    """
    # Split path and check each component
    parts = Path(path).parts
    for part in parts:
        if part == '..' or part.startswith('..'):
            return True
    
    # Also check for encoded traversal attempts
    suspicious_patterns = ['%2e%2e', '..%2f', '..%5c', '%252e%252e']
    path_lower = path.lower()
    return any(pattern in path_lower for pattern in suspicious_patterns)