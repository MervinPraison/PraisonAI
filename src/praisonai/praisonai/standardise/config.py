"""
Configuration for the FDEP standardisation system.

Supports configuration via:
1. CLI flags (highest priority)
2. Config file (.praison/standardise.yaml)
3. Environment variables
4. Defaults (lowest priority)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class StandardiseConfig:
    """Configuration for the standardiser engine."""
    
    # Root paths (auto-detected if not specified)
    project_root: Optional[Path] = None
    docs_root: Optional[Path] = None
    examples_root: Optional[Path] = None
    sdk_root: Optional[Path] = None
    cli_root: Optional[Path] = None
    
    # Mintlify config
    mintlify_config: Optional[Path] = None
    
    # Manifest storage
    manifest_dir: Optional[Path] = None
    
    # Safety settings
    dry_run: bool = True
    backup: bool = True
    force: bool = False
    
    # Scope settings
    scope: str = "all"  # all, docs, examples, sdk, cli
    feature_filter: Optional[str] = None  # Specific feature slug to check
    
    # Dedupe settings
    dedupe_mode: str = "prompt"  # prompt, auto, skip
    similarity_threshold: float = 0.8
    
    # Report settings
    report_format: str = "text"  # text, json, markdown
    
    # CI settings
    ci_mode: bool = False
    
    # Excluded paths (relative to project root)
    excluded_paths: List[str] = field(default_factory=lambda: [
        "node_modules",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "dist",
        "build",
    ])
    
    # Required artifact types per feature
    required_artifacts: List[str] = field(default_factory=lambda: [
        "docs_concept",
        "docs_feature", 
        "docs_cli",
        "docs_sdk",
        "example_basic",
        "example_advanced",
    ])
    
    def __post_init__(self):
        """Auto-detect paths if not specified."""
        # Convert string paths to Path objects
        if isinstance(self.project_root, str):
            self.project_root = Path(self.project_root)
        if isinstance(self.docs_root, str):
            self.docs_root = Path(self.docs_root)
        if isinstance(self.examples_root, str):
            self.examples_root = Path(self.examples_root)
        if isinstance(self.sdk_root, str):
            self.sdk_root = Path(self.sdk_root)
        if isinstance(self.cli_root, str):
            self.cli_root = Path(self.cli_root)
        if isinstance(self.mintlify_config, str):
            self.mintlify_config = Path(self.mintlify_config)
        if isinstance(self.manifest_dir, str):
            self.manifest_dir = Path(self.manifest_dir)
        
        if self.project_root is None:
            self.project_root = self._detect_project_root()
        
        if self.project_root:
            self._auto_detect_paths()
    
    def _detect_project_root(self) -> Optional[Path]:
        """Detect project root by looking for common markers."""
        cwd = Path.cwd()
        
        # Look for .praison directory or pyproject.toml
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".praison").exists():
                return parent
            if (parent / "pyproject.toml").exists():
                return parent
            if (parent / "mint.json").exists():
                return parent
        
        return cwd
    
    def _auto_detect_paths(self):
        """Auto-detect paths based on project root."""
        if not self.project_root:
            return
        
        root = self.project_root
        
        # Docs root detection - default: ~/PraisonAIDocs/docs
        if self.docs_root is None:
            # First check home directory for PraisonAIDocs
            home_docs = Path.home() / "PraisonAIDocs" / "docs"
            if home_docs.exists():
                self.docs_root = home_docs
            else:
                # Fallback to project-relative paths
                for candidate in ["docs", "PraisonAIDocs/docs"]:
                    path = root / candidate
                    if path.exists():
                        self.docs_root = path
                        break
                # Check parent for PraisonAIDocs
                parent_docs = root.parent / "PraisonAIDocs"
                if parent_docs.exists() and self.docs_root is None:
                    self.docs_root = parent_docs / "docs"
        
        # Examples root detection - default: ~/praisonai-package/examples
        if self.examples_root is None:
            # First check home directory for praisonai-package/examples
            home_examples = Path.home() / "praisonai-package" / "examples"
            if home_examples.exists():
                self.examples_root = home_examples
            else:
                # Fallback to project-relative paths
                for candidate in ["examples/python", "examples"]:
                    path = root / candidate
                    if path.exists():
                        self.examples_root = path
                        break
        
        # SDK root detection
        if self.sdk_root is None:
            for candidate in [
                "src/praisonai-agents/praisonaiagents",
                "praisonaiagents",
            ]:
                path = root / candidate
                if path.exists():
                    self.sdk_root = path
                    break
        
        # CLI root detection
        if self.cli_root is None:
            for candidate in [
                "src/praisonai/praisonai/cli",
                "praisonai/cli",
            ]:
                path = root / candidate
                if path.exists():
                    self.cli_root = path
                    break
        
        # Mintlify config detection
        if self.mintlify_config is None:
            # Check docs root parent for mint.json
            if self.docs_root:
                mint_path = self.docs_root.parent / "mint.json"
                if mint_path.exists():
                    self.mintlify_config = mint_path
            # Check project root
            if self.mintlify_config is None:
                for name in ["mint.json", "mintlify.json", "docs.json"]:
                    path = root / name
                    if path.exists():
                        self.mintlify_config = path
                        break
        
        # Manifest directory
        if self.manifest_dir is None:
            self.manifest_dir = root / ".praison" / "features"
    
    @classmethod
    def from_file(cls, path: Path) -> "StandardiseConfig":
        """Load configuration from a YAML file."""
        try:
            import yaml
        except ImportError:
            # Fallback to basic parsing if PyYAML not available
            return cls()
        
        if not path.exists():
            return cls()
        
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        
        return cls(
            project_root=Path(data["project_root"]) if data.get("project_root") else None,
            docs_root=Path(data["docs_root"]) if data.get("docs_root") else None,
            examples_root=Path(data["examples_root"]) if data.get("examples_root") else None,
            sdk_root=Path(data["sdk_root"]) if data.get("sdk_root") else None,
            cli_root=Path(data["cli_root"]) if data.get("cli_root") else None,
            mintlify_config=Path(data["mintlify_config"]) if data.get("mintlify_config") else None,
            manifest_dir=Path(data["manifest_dir"]) if data.get("manifest_dir") else None,
            dry_run=data.get("dry_run", True),
            backup=data.get("backup", True),
            force=data.get("force", False),
            scope=data.get("scope", "all"),
            feature_filter=data.get("feature_filter"),
            dedupe_mode=data.get("dedupe_mode", "prompt"),
            similarity_threshold=data.get("similarity_threshold", 0.8),
            report_format=data.get("report_format", "text"),
            ci_mode=data.get("ci_mode", False),
            excluded_paths=data.get("excluded_paths", cls.__dataclass_fields__["excluded_paths"].default_factory()),
            required_artifacts=data.get("required_artifacts", cls.__dataclass_fields__["required_artifacts"].default_factory()),
        )
    
    @classmethod
    def from_env(cls) -> "StandardiseConfig":
        """Load configuration from environment variables."""
        return cls(
            project_root=Path(os.environ["PRAISON_PROJECT_ROOT"]) if os.environ.get("PRAISON_PROJECT_ROOT") else None,
            docs_root=Path(os.environ["PRAISON_DOCS_ROOT"]) if os.environ.get("PRAISON_DOCS_ROOT") else None,
            dry_run=os.environ.get("PRAISON_DRY_RUN", "true").lower() == "true",
            ci_mode=os.environ.get("CI", "false").lower() == "true",
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialisation."""
        return {
            "project_root": str(self.project_root) if self.project_root else None,
            "docs_root": str(self.docs_root) if self.docs_root else None,
            "examples_root": str(self.examples_root) if self.examples_root else None,
            "sdk_root": str(self.sdk_root) if self.sdk_root else None,
            "cli_root": str(self.cli_root) if self.cli_root else None,
            "mintlify_config": str(self.mintlify_config) if self.mintlify_config else None,
            "manifest_dir": str(self.manifest_dir) if self.manifest_dir else None,
            "dry_run": self.dry_run,
            "backup": self.backup,
            "force": self.force,
            "scope": self.scope,
            "feature_filter": self.feature_filter,
            "dedupe_mode": self.dedupe_mode,
            "similarity_threshold": self.similarity_threshold,
            "report_format": self.report_format,
            "ci_mode": self.ci_mode,
            "excluded_paths": self.excluded_paths,
            "required_artifacts": self.required_artifacts,
        }
