"""
Template Security

Security primitives for template validation and safe extraction.
Includes checksum verification, allowlists, and safe path handling.
"""

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field


@dataclass
class SecurityConfig:
    """Security configuration for template operations."""
    
    # Allowed template sources
    allowed_sources: Set[str] = field(default_factory=lambda: {
        "github:MervinPraison/agent-recipes",
        "package:agent_recipes",
    })
    
    # Allow all local paths by default
    allow_local: bool = True
    
    # Allow all GitHub sources (not just allowlisted)
    allow_any_github: bool = True
    
    # Allow HTTP sources
    allow_http: bool = False
    
    # Require checksum verification for remote templates
    require_checksum: bool = False
    
    # Maximum template size in bytes (10MB default)
    max_template_size: int = 10 * 1024 * 1024
    
    # Blocked file patterns (security risk)
    blocked_patterns: List[str] = field(default_factory=lambda: [
        r"\.\.\/",  # Path traversal
        r"^\/",     # Absolute paths in archives
        r"\.exe$",  # Executables
        r"\.dll$",
        r"\.so$",
        r"\.dylib$",
        r"\.sh$",   # Shell scripts (unless explicitly allowed)
        r"\.bat$",
        r"\.cmd$",
        r"\.ps1$",
    ])
    
    # Allowed file extensions
    allowed_extensions: Set[str] = field(default_factory=lambda: {
        ".yaml", ".yml", ".json", ".md", ".txt", ".py",
        ".toml", ".cfg", ".ini", ".env.example", ".bak"
    })


class TemplateSecurity:
    """
    Security handler for template operations.
    
    Provides:
    - Source allowlist validation
    - Checksum verification
    - Safe path extraction
    - File type validation
    """
    
    CONFIG_FILE = ".praison/security.yaml"
    
    def __init__(self, config: Optional[SecurityConfig] = None):
        """
        Initialize security handler.
        
        Args:
            config: Security configuration (loads from file if not provided)
        """
        self.config = config or self._load_config()
    
    def _load_config(self) -> SecurityConfig:
        """Load security config from file or use defaults."""
        config_path = Path.home() / self.CONFIG_FILE
        
        if config_path.exists():
            try:
                import yaml
                with open(config_path) as f:
                    data = yaml.safe_load(f)
                return SecurityConfig(
                    allowed_sources=set(data.get("allowed_sources", [])),
                    allow_local=data.get("allow_local", True),
                    allow_any_github=data.get("allow_any_github", True),
                    allow_http=data.get("allow_http", False),
                    require_checksum=data.get("require_checksum", False),
                    max_template_size=data.get("max_template_size", 10 * 1024 * 1024),
                )
            except Exception:
                pass
        
        return SecurityConfig()
    
    def is_source_allowed(self, uri: str) -> bool:
        """
        Check if a template source is allowed.
        
        Args:
            uri: Template URI
            
        Returns:
            True if source is allowed
        """
        # Local paths
        if uri.startswith(("./", "../", "~/", "/")) or os.path.exists(uri):
            return self.config.allow_local
        
        # Package references
        if uri.startswith("package:"):
            package = uri.split(":")[1].split("/")[0]
            return (
                f"package:{package}" in self.config.allowed_sources or
                uri in self.config.allowed_sources
            )
        
        # GitHub references
        if uri.startswith("github:"):
            if self.config.allow_any_github:
                return True
            # Check specific repo allowlist
            parts = uri.replace("github:", "").split("/")
            if len(parts) >= 2:
                repo_ref = f"github:{parts[0]}/{parts[1]}"
                return repo_ref in self.config.allowed_sources
            return False
        
        # HTTP references
        if uri.startswith(("http://", "https://")):
            return self.config.allow_http
        
        # Simple template name (assumes default repo)
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', uri):
            return True
        
        return False
    
    def verify_checksum(
        self,
        directory: Path,
        expected_checksum: str,
        algorithm: str = "sha256"
    ) -> bool:
        """
        Verify checksum of template directory.
        
        Args:
            directory: Template directory
            expected_checksum: Expected checksum value
            algorithm: Hash algorithm (sha256, sha512, md5)
            
        Returns:
            True if checksum matches
        """
        actual = self.calculate_checksum(directory, algorithm)
        return actual == expected_checksum
    
    def calculate_checksum(
        self,
        directory: Path,
        algorithm: str = "sha256"
    ) -> str:
        """
        Calculate checksum of template directory.
        
        Args:
            directory: Template directory
            algorithm: Hash algorithm
            
        Returns:
            Hex digest of checksum
        """
        if algorithm == "sha256":
            hasher = hashlib.sha256()
        elif algorithm == "sha512":
            hasher = hashlib.sha512()
        elif algorithm == "md5":
            hasher = hashlib.md5()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        for file_path in sorted(directory.rglob("*")):
            if file_path.is_file() and not file_path.name.startswith("."):
                hasher.update(file_path.name.encode())
                hasher.update(file_path.read_bytes())
        
        return hasher.hexdigest()
    
    def validate_path(self, path: str) -> bool:
        """
        Validate a path for security issues.
        
        Args:
            path: Path to validate
            
        Returns:
            True if path is safe
        """
        for pattern in self.config.blocked_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                return False
        return True
    
    def validate_file(self, file_path: Path) -> bool:
        """
        Validate a file for security.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file is safe
        """
        # Check extension
        if file_path.suffix.lower() not in self.config.allowed_extensions:
            # Allow files without extension (like README)
            if file_path.suffix:
                return False
            # Files without extension are allowed (like README, LICENSE)
            return True
        
        # Check size
        if file_path.exists() and file_path.stat().st_size > self.config.max_template_size:
            return False
        
        # Check path (only validate the filename, not the full path)
        return self.validate_path(file_path.name)
    
    def validate_template_directory(self, directory: Path) -> List[str]:
        """
        Validate all files in a template directory.
        
        Args:
            directory: Template directory
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        total_size = 0
        
        # Directories to skip during validation
        SKIP_DIRS = {"__pycache__", ".git", ".svn", ".hg", "node_modules", ".venv", "venv"}
        
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                # Skip files in excluded directories
                if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                    continue
                
                # Check path safety
                if not self.validate_path(str(file_path.relative_to(directory))):
                    errors.append(f"Unsafe path: {file_path.relative_to(directory)}")
                    continue
                
                # Check extension
                if file_path.suffix.lower() not in self.config.allowed_extensions:
                    if file_path.suffix:  # Has extension but not allowed
                        errors.append(f"Blocked file type: {file_path.name}")
                
                # Track size
                total_size += file_path.stat().st_size
        
        if total_size > self.config.max_template_size:
            errors.append(
                f"Template too large: {total_size} bytes "
                f"(max: {self.config.max_template_size})"
            )
        
        return errors
    
    def sanitize_template_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize template configuration.
        
        Removes potentially dangerous fields and validates structure.
        
        Args:
            config: Raw template configuration
            
        Returns:
            Sanitized configuration
        """
        # Fields that are safe to keep
        safe_fields = {
            "name", "description", "version", "author", "license",
            "tags", "requires", "config", "workflow", "agents",
            "skills", "cli", "metadata"
        }
        
        sanitized = {}
        for key, value in config.items():
            if key in safe_fields:
                sanitized[key] = value
        
        return sanitized
    
    def add_allowed_source(self, source: str) -> None:
        """Add a source to the allowlist."""
        self.config.allowed_sources.add(source)
    
    def remove_allowed_source(self, source: str) -> None:
        """Remove a source from the allowlist."""
        self.config.allowed_sources.discard(source)
    
    def save_config(self) -> None:
        """Save current config to file."""
        import yaml
        
        config_path = Path.home() / self.CONFIG_FILE
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "allowed_sources": list(self.config.allowed_sources),
            "allow_local": self.config.allow_local,
            "allow_any_github": self.config.allow_any_github,
            "allow_http": self.config.allow_http,
            "require_checksum": self.config.require_checksum,
            "max_template_size": self.config.max_template_size,
        }
        
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
