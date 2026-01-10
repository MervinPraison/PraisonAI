"""
Main standardisation engine for the FDEP system.

Orchestrates all standardisation operations:
- Discovery
- Validation
- Dedupe detection
- Drift detection
- Report generation
- Fix application
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import StandardiseConfig
from .dedupe import DedupeDetector
from .discovery import FeatureDiscovery
from .drift import DriftDetector
from .models import (
    ArtifactType,
    FeatureSlug,
    IssueType,
    StandardiseIssue,
    StandardiseReport,
)
from .reports import ReportGenerator
from .templates import TemplateGenerator
from .validator import ArtifactValidator


class StandardiseEngine:
    """Main engine for standardisation operations."""
    
    def __init__(self, config: Optional[StandardiseConfig] = None):
        self.config = config or StandardiseConfig()
        self.discovery = FeatureDiscovery(self.config)
        self.validator = ArtifactValidator(self.config, self.discovery)
        self.dedupe = DedupeDetector(self.config, self.discovery)
        self.drift = DriftDetector(self.config, self.discovery)
        self.templates = TemplateGenerator()
        self.reports = ReportGenerator()
    
    def check(self) -> StandardiseReport:
        """Run a full standardisation check and return a report."""
        timestamp = datetime.now().isoformat()
        
        # Discover features
        all_features = self.discovery.get_all_features()
        
        # Count docs and examples
        docs_count = self._count_docs()
        examples_count = self._count_examples()
        
        # Validate artifacts
        validation_results = self.validator.validate_all()
        missing_artifacts = self.validator.get_missing_artifacts()
        
        # Detect duplicates
        duplicates = self.dedupe.detect_all()
        
        # Detect naming inconsistencies
        naming_issues = self.dedupe.get_naming_inconsistencies()
        
        # Detect drift
        drift_reports = self.drift.detect_all()
        
        # Compile issues
        issues = []
        
        # Add naming inconsistency issues
        for path1, path2, message in naming_issues:
            issues.append(StandardiseIssue(
                issue_type=IssueType.NAMING_INCONSISTENCY,
                slug=None,
                path=path1,
                message=message,
                severity="warning",
                auto_fixable=True,
                fix_action=f"rename {path1} or {path2}",
            ))
        
        # Add drift issues
        for drift_report in drift_reports:
            for item in drift_report.sdk_drift:
                issues.append(StandardiseIssue(
                    issue_type=IssueType.DRIFT_SDK_DOCS,
                    slug=drift_report.slug,
                    path=None,
                    message=f"{item.name} in {item.source} but missing in {item.missing_in}",
                    severity="info",
                    auto_fixable=False,
                ))
            for item in drift_report.cli_drift:
                issues.append(StandardiseIssue(
                    issue_type=IssueType.DRIFT_CLI_DOCS,
                    slug=drift_report.slug,
                    path=None,
                    message=f"{item.name} in {item.source} but missing in {item.missing_in}",
                    severity="info",
                    auto_fixable=False,
                ))
        
        return StandardiseReport(
            timestamp=timestamp,
            features_scanned=len(all_features),
            docs_pages=docs_count,
            examples_count=examples_count,
            issues=issues,
            duplicates=duplicates,
            missing_artifacts=missing_artifacts,
            drift_reports=drift_reports,
            validation_results=list(validation_results.values()),
        )
    
    def report(self, format: str = "text") -> str:
        """Generate a report in the specified format."""
        report = self.check()
        return self.reports.generate(report, format)
    
    def fix(self, feature: Optional[str] = None, 
            apply: bool = False) -> Dict[str, List[str]]:
        """
        Fix standardisation issues.
        
        Args:
            feature: Specific feature slug to fix (None = all)
            apply: Actually apply changes (False = dry-run)
        
        Returns:
            Dict with 'planned' and 'applied' actions
        """
        actions = {"planned": [], "applied": []}
        
        # Get current state
        report = self.check()
        
        # Plan fixes for missing artifacts
        for slug_str, missing in report.missing_artifacts.items():
            if feature and slug_str != feature:
                continue
            
            slug = FeatureSlug.from_string(slug_str)
            
            for artifact_type in missing:
                path = self.templates.get_expected_path(
                    slug, artifact_type,
                    docs_root=self.config.docs_root,
                    examples_root=self.config.examples_root,
                )
                
                if path:
                    action = f"CREATE {path}"
                    actions["planned"].append(action)
                    
                    if apply and not self.config.dry_run:
                        self._create_artifact(slug, artifact_type, path)
                        actions["applied"].append(action)
        
        # Plan fixes for naming inconsistencies
        naming_issues = self.dedupe.get_naming_inconsistencies()
        for path1, path2, message in naming_issues:
            if feature:
                slug1 = FeatureSlug.from_path(path1, "docs")
                slug2 = FeatureSlug.from_path(path2, "docs")
                if slug1.normalised != feature and slug2.normalised != feature:
                    continue
            
            # Prefer plural form
            if "singular" in str(path1).lower() or len(path1.stem) < len(path2.stem):
                action = f"RENAME {path1} -> deprecated, keep {path2}"
            else:
                action = f"RENAME {path2} -> deprecated, keep {path1}"
            actions["planned"].append(action)
        
        return actions
    
    def init(self, feature: str) -> Dict[str, str]:
        """
        Initialise a new feature with all required artifacts.
        
        Args:
            feature: Feature slug to initialise
        
        Returns:
            Dict mapping artifact type to created path
        """
        created = {}
        slug = FeatureSlug.from_string(feature)
        
        if not slug.is_valid:
            raise ValueError(f"Invalid feature slug: {slug.validation_error}")
        
        for artifact_type in ArtifactType:
            if artifact_type == ArtifactType.MANIFEST:
                continue
            
            path = self.templates.get_expected_path(
                slug, artifact_type,
                docs_root=self.config.docs_root,
                examples_root=self.config.examples_root,
            )
            
            if path and not path.exists():
                if not self.config.dry_run:
                    self._create_artifact(slug, artifact_type, path)
                created[artifact_type.value] = str(path)
        
        return created
    
    def _create_artifact(self, slug: FeatureSlug, artifact_type: ArtifactType,
                         path: Path) -> None:
        """Create an artifact file."""
        # Backup if exists
        if path.exists() and self.config.backup:
            self._backup_file(path)
        
        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate content
        content = self.templates.generate(slug, artifact_type)
        
        # Write file
        path.write_text(content, encoding="utf-8")
    
    def _backup_file(self, path: Path) -> Path:
        """Create a backup of a file."""
        if not self.config.project_root:
            return path
        
        backup_dir = self.config.project_root / ".praison" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.stem}_{timestamp}{path.suffix}"
        backup_path = backup_dir / backup_name
        
        shutil.copy2(path, backup_path)
        return backup_path
    
    def _count_docs(self) -> int:
        """Count total docs pages."""
        if not self.config.docs_root or not self.config.docs_root.exists():
            return 0
        
        count = 0
        for mdx_file in self.config.docs_root.rglob("*.mdx"):
            if not any(excluded in str(mdx_file) for excluded in self.config.excluded_paths):
                count += 1
        return count
    
    def _count_examples(self) -> int:
        """Count total example files."""
        if not self.config.examples_root or not self.config.examples_root.exists():
            return 0
        
        count = 0
        for py_file in self.config.examples_root.rglob("*.py"):
            if not any(excluded in str(py_file) for excluded in self.config.excluded_paths):
                count += 1
        return count
    
    def get_exit_code(self, report: StandardiseReport) -> int:
        """Get CI exit code based on report."""
        if report.has_issues:
            return 1  # Issues found
        return 0  # No issues
