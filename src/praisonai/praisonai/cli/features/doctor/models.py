"""
Data models for the Doctor CLI module.

Defines the core data structures for check results, reports, and configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class CheckStatus(Enum):
    """Status of a doctor check."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class CheckCategory(Enum):
    """Category of a doctor check."""
    ENVIRONMENT = "environment"
    CONFIG = "config"
    TOOLS = "tools"
    DATABASE = "database"
    MCP = "mcp"
    OBSERVABILITY = "observability"
    SKILLS = "skills"
    MEMORY = "memory"
    PERMISSIONS = "permissions"
    NETWORK = "network"
    PERFORMANCE = "performance"
    SELFTEST = "selftest"


class CheckSeverity(Enum):
    """Severity level of a check."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class CheckResult:
    """Result of a single doctor check."""
    id: str
    title: str
    category: CheckCategory
    status: CheckStatus
    message: str
    details: Optional[str] = None
    remediation: Optional[str] = None
    duration_ms: float = 0.0
    severity: CheckSeverity = CheckSeverity.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category.value,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "remediation": self.remediation,
            "duration_ms": round(self.duration_ms, 2),
            "severity": self.severity.value,
            "metadata": self.metadata,
        }
    
    @property
    def passed(self) -> bool:
        """Check if this result is considered passing."""
        return self.status in (CheckStatus.PASS, CheckStatus.SKIP)
    
    @property
    def is_warning(self) -> bool:
        """Check if this result is a warning."""
        return self.status == CheckStatus.WARN
    
    @property
    def is_failure(self) -> bool:
        """Check if this result is a failure."""
        return self.status in (CheckStatus.FAIL, CheckStatus.ERROR)


@dataclass
class CheckDefinition:
    """Definition of a doctor check."""
    id: str
    title: str
    description: str
    category: CheckCategory
    severity: CheckSeverity = CheckSeverity.MEDIUM
    requires_deep: bool = False
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "severity": self.severity.value,
            "requires_deep": self.requires_deep,
            "dependencies": self.dependencies,
            "tags": self.tags,
        }


@dataclass
class EnvironmentSummary:
    """Summary of the runtime environment."""
    python_version: str = ""
    python_executable: str = ""
    os_name: str = ""
    os_version: str = ""
    architecture: str = ""
    praisonai_version: str = ""
    praisonaiagents_version: str = ""
    working_directory: str = ""
    virtual_env: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "python_version": self.python_version,
            "python_executable": self.python_executable,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "praisonai_version": self.praisonai_version,
            "praisonaiagents_version": self.praisonaiagents_version,
            "working_directory": self.working_directory,
            "virtual_env": self.virtual_env,
        }


@dataclass
class ReportSummary:
    """Summary statistics for a doctor report."""
    total: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total": self.total,
            "passed": self.passed,
            "warnings": self.warnings,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
        }


@dataclass
class DoctorReport:
    """Complete doctor report."""
    version: str = "1.0.0"
    timestamp: str = ""
    duration_ms: float = 0.0
    environment: EnvironmentSummary = field(default_factory=EnvironmentSummary)
    results: List[CheckResult] = field(default_factory=list)
    summary: ReportSummary = field(default_factory=ReportSummary)
    exit_code: int = 0
    mode: str = "fast"
    filters: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            from datetime import datetime, timezone
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def calculate_summary(self) -> None:
        """Calculate summary statistics from results."""
        self.summary = ReportSummary(
            total=len(self.results),
            passed=sum(1 for r in self.results if r.status == CheckStatus.PASS),
            warnings=sum(1 for r in self.results if r.status == CheckStatus.WARN),
            failed=sum(1 for r in self.results if r.status == CheckStatus.FAIL),
            skipped=sum(1 for r in self.results if r.status == CheckStatus.SKIP),
            errors=sum(1 for r in self.results if r.status == CheckStatus.ERROR),
        )
    
    def calculate_exit_code(self, strict: bool = False) -> int:
        """
        Calculate exit code based on results.
        
        Args:
            strict: If True, treat warnings as failures
            
        Returns:
            0: All passed (warnings allowed unless strict)
            1: Failures present
            2: Internal errors
        """
        if self.summary.errors > 0:
            return 2
        if self.summary.failed > 0:
            return 1
        if strict and self.summary.warnings > 0:
            return 1
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "duration_ms": round(self.duration_ms, 2),
            "environment": self.environment.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary.to_dict(),
            "exit_code": self.exit_code,
            "mode": self.mode,
            "filters": self.filters,
        }


@dataclass
class DoctorConfig:
    """Configuration for doctor execution."""
    deep: bool = False
    timeout: float = 10.0
    strict: bool = False
    quiet: bool = False
    no_color: bool = False
    format: str = "text"
    output_path: Optional[str] = None
    only: List[str] = field(default_factory=list)
    skip: List[str] = field(default_factory=list)
    
    # Subcommand-specific options
    show_keys: bool = False
    require_keys: List[str] = field(default_factory=list)
    config_file: Optional[str] = None
    dsn: Optional[str] = None
    provider: Optional[str] = None
    read_only: bool = True
    mock: bool = True
    live: bool = False
    model: Optional[str] = None
    budget_ms: Optional[int] = None
    top_n: int = 10
    fail_fast: bool = False
    list_tools: bool = False
    all_checks: bool = False
    missing_only: bool = False
    name: Optional[str] = None
    category: Optional[str] = None
    path: Optional[str] = None
    save_report: bool = False
