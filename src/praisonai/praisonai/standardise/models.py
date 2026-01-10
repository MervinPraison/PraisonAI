"""
Data models for the FDEP standardisation system.

All models use dataclasses for lightweight, stdlib-only implementation.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class ArtifactType(Enum):
    """Types of required artifacts per feature."""
    DOCS_CONCEPT = "docs_concept"
    DOCS_FEATURE = "docs_feature"
    DOCS_CLI = "docs_cli"
    DOCS_SDK = "docs_sdk"
    EXAMPLE_BASIC = "example_basic"
    EXAMPLE_ADVANCED = "example_advanced"
    MANIFEST = "manifest"


class ArtifactStatus(Enum):
    """Status of an artifact."""
    PRESENT = "present"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    OUTDATED = "outdated"


class IssueType(Enum):
    """Types of standardisation issues."""
    MISSING_ARTIFACT = "missing_artifact"
    DUPLICATE_CONTENT = "duplicate_content"
    NAMING_INCONSISTENCY = "naming_inconsistency"
    DRIFT_SDK_DOCS = "drift_sdk_docs"
    DRIFT_CLI_DOCS = "drift_cli_docs"
    INVALID_FRONTMATTER = "invalid_frontmatter"


# Slug validation regex: lowercase alphanumeric + hyphens, 2-64 chars
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$|^[a-z]$")

# Singular to plural mappings for normalisation
SINGULAR_PLURAL_MAP = {
    "agent": "agents",
    "task": "tasks",
    "tool": "tools",
    "guardrail": "guardrails",
    "handoff": "handoffs",
    "workflow": "workflows",
    "checkpoint": "checkpoints",
    "hook": "hooks",
    "skill": "skills",
    "plugin": "plugins",
    "session": "sessions",
    "process": "processes",
}

# Legacy alias mappings
LEGACY_ALIASES = {
    "rag": "knowledge",
    "retrieval": "knowledge",
    "llm": "models",
    "model": "models",
    "db": "databases",
    "database": "databases",
}


@dataclass
class FeatureSlug:
    """
    Represents a normalised feature slug.
    
    Slug rules:
    - Lowercase alphanumeric + hyphens only
    - 1-64 characters
    - Stable normalisation (singular/plural, legacy aliases)
    """
    raw: str
    normalised: str
    is_valid: bool
    validation_error: Optional[str] = None
    
    @classmethod
    def from_string(cls, value: str) -> "FeatureSlug":
        """Create a FeatureSlug from a raw string."""
        raw = value.strip().lower()
        
        # Replace underscores with hyphens
        normalised = raw.replace("_", "-")
        
        # Remove .py, .mdx extensions if present
        for ext in (".py", ".mdx", ".md"):
            if normalised.endswith(ext):
                normalised = normalised[:-len(ext)]
        
        # Apply legacy alias mapping
        if normalised in LEGACY_ALIASES:
            normalised = LEGACY_ALIASES[normalised]
        
        # Apply singular to plural normalisation (prefer plural for collections)
        if normalised in SINGULAR_PLURAL_MAP:
            normalised = SINGULAR_PLURAL_MAP[normalised]
        
        # Validate
        is_valid = bool(SLUG_PATTERN.match(normalised))
        validation_error = None
        
        if not is_valid:
            if not normalised:
                validation_error = "Slug cannot be empty"
            elif not normalised[0].isalpha():
                validation_error = "Slug must start with a letter"
            elif len(normalised) > 64:
                validation_error = "Slug must be 64 characters or less"
            else:
                validation_error = "Slug must contain only lowercase letters, numbers, and hyphens"
        
        return cls(raw=raw, normalised=normalised, is_valid=is_valid, 
                   validation_error=validation_error)
    
    @classmethod
    def from_path(cls, path: Path, base_type: str = "unknown") -> "FeatureSlug":
        """
        Derive a slug from a file or directory path.
        
        Args:
            path: Path to derive slug from
            base_type: Type hint (sdk, cli, docs, examples)
        """
        # Use the stem (filename without extension) or directory name
        name = path.stem if path.is_file() else path.name
        return cls.from_string(name)
    
    def __str__(self) -> str:
        return self.normalised
    
    def __hash__(self) -> int:
        return hash(self.normalised)
    
    def __eq__(self, other) -> bool:
        if isinstance(other, FeatureSlug):
            return self.normalised == other.normalised
        if isinstance(other, str):
            return self.normalised == other.lower()
        return False


@dataclass
class ArtifactPath:
    """Represents a path to a required artifact."""
    artifact_type: ArtifactType
    expected_path: Path
    actual_path: Optional[Path] = None
    status: ArtifactStatus = ArtifactStatus.MISSING
    
    @property
    def exists(self) -> bool:
        return self.actual_path is not None and self.actual_path.exists()


@dataclass
class FeatureManifest:
    """
    Manifest entry for a single feature.
    
    This is the source of truth for what artifacts a feature should have.
    """
    slug: FeatureSlug
    name: str
    description: str
    status: str = "stable"  # stable, beta, experimental, deprecated
    min_version: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    related_features: List[str] = field(default_factory=list)
    sdk_module: Optional[str] = None
    cli_commands: List[str] = field(default_factory=list)
    api_classes: List[str] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialisation."""
        return {
            "slug": self.slug.normalised,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "min_version": self.min_version,
            "tags": self.tags,
            "related_features": self.related_features,
            "sdk_module": self.sdk_module,
            "cli_commands": self.cli_commands,
            "api_classes": self.api_classes,
            "artifacts": self.artifacts,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FeatureManifest":
        """Create from dictionary."""
        slug = FeatureSlug.from_string(data.get("slug", ""))
        return cls(
            slug=slug,
            name=data.get("name", slug.normalised.replace("-", " ").title()),
            description=data.get("description", ""),
            status=data.get("status", "stable"),
            min_version=data.get("min_version"),
            tags=data.get("tags", []),
            related_features=data.get("related_features", []),
            sdk_module=data.get("sdk_module"),
            cli_commands=data.get("cli_commands", []),
            api_classes=data.get("api_classes", []),
            artifacts=data.get("artifacts", {}),
        )


@dataclass
class ValidationResult:
    """Result of validating a feature's artifacts."""
    slug: FeatureSlug
    is_valid: bool
    missing_artifacts: List[ArtifactType] = field(default_factory=list)
    present_artifacts: List[ArtifactPath] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    
    @property
    def missing_count(self) -> int:
        return len(self.missing_artifacts)
    
    @property
    def present_count(self) -> int:
        return len(self.present_artifacts)


@dataclass
class DuplicateCluster:
    """A cluster of duplicate or near-duplicate content."""
    slug: FeatureSlug
    pages: List[Path]
    similarity_score: float  # 0.0 to 1.0
    issue_type: str  # "same_slug", "title_similarity", "content_overlap"
    recommendation: str  # "merge", "keep_both", "review"
    primary_page: Optional[Path] = None  # Recommended canonical page
    
    def __str__(self) -> str:
        return f"DuplicateCluster({self.slug}, {len(self.pages)} pages, {self.issue_type})"


@dataclass
class DriftItem:
    """A single drift item (SDK export or CLI flag not in docs, or vice versa)."""
    name: str
    source: str  # "sdk", "cli", "docs"
    missing_in: str  # Where it's missing
    item_type: str  # "class", "function", "flag", "command"


@dataclass
class DriftReport:
    """Report of drift between code and documentation."""
    slug: FeatureSlug
    sdk_drift: List[DriftItem] = field(default_factory=list)
    cli_drift: List[DriftItem] = field(default_factory=list)
    
    @property
    def has_drift(self) -> bool:
        return bool(self.sdk_drift or self.cli_drift)
    
    @property
    def total_drift_items(self) -> int:
        return len(self.sdk_drift) + len(self.cli_drift)


@dataclass
class StandardiseIssue:
    """A single standardisation issue."""
    issue_type: IssueType
    slug: Optional[FeatureSlug]
    path: Optional[Path]
    message: str
    severity: str = "warning"  # error, warning, info
    auto_fixable: bool = False
    fix_action: Optional[str] = None


@dataclass
class StandardiseReport:
    """Complete standardisation report."""
    timestamp: str
    features_scanned: int
    docs_pages: int
    examples_count: int
    issues: List[StandardiseIssue] = field(default_factory=list)
    duplicates: List[DuplicateCluster] = field(default_factory=list)
    missing_artifacts: Dict[str, List[ArtifactType]] = field(default_factory=dict)
    drift_reports: List[DriftReport] = field(default_factory=list)
    validation_results: List[ValidationResult] = field(default_factory=list)
    
    @property
    def total_issues(self) -> int:
        return len(self.issues)
    
    @property
    def total_missing(self) -> int:
        return sum(len(v) for v in self.missing_artifacts.values())
    
    @property
    def total_duplicates(self) -> int:
        return len(self.duplicates)
    
    @property
    def has_issues(self) -> bool:
        return self.total_issues > 0 or self.total_missing > 0 or self.total_duplicates > 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialisation."""
        return {
            "timestamp": self.timestamp,
            "summary": {
                "features_scanned": self.features_scanned,
                "docs_pages": self.docs_pages,
                "examples_count": self.examples_count,
                "total_issues": self.total_issues,
                "total_missing": self.total_missing,
                "total_duplicates": self.total_duplicates,
            },
            "issues": [
                {
                    "type": i.issue_type.value,
                    "slug": str(i.slug) if i.slug else None,
                    "path": str(i.path) if i.path else None,
                    "message": i.message,
                    "severity": i.severity,
                    "auto_fixable": i.auto_fixable,
                }
                for i in self.issues
            ],
            "duplicates": [
                {
                    "slug": str(d.slug),
                    "pages": [str(p) for p in d.pages],
                    "similarity": d.similarity_score,
                    "type": d.issue_type,
                    "recommendation": d.recommendation,
                }
                for d in self.duplicates
            ],
            "missing_artifacts": {
                slug: [a.value for a in artifacts]
                for slug, artifacts in self.missing_artifacts.items()
            },
        }
