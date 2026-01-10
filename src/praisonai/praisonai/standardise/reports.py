"""
Report generators for the FDEP standardisation system.

Generates reports in:
- Text (terminal-friendly)
- JSON (machine-readable)
- Markdown (documentation-friendly)
"""

import json
from pathlib import Path

from .models import StandardiseReport


class ReportGenerator:
    """Generates standardisation reports in various formats."""
    
    def generate(self, report: StandardiseReport, format: str = "text") -> str:
        """Generate a report in the specified format."""
        if format == "text":
            return self._generate_text(report)
        elif format == "json":
            return self._generate_json(report)
        elif format == "markdown":
            return self._generate_markdown(report)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def _generate_text(self, report: StandardiseReport) -> str:
        """Generate a text report for terminal output."""
        lines = []
        
        # Header
        lines.append("")
        lines.append("🔍 PraisonAI Standardisation Check")
        lines.append("══════════════════════════════════")
        lines.append("")
        
        # Summary
        lines.append("📊 Summary")
        lines.append("──────────")
        lines.append(f"Features scanned:     {report.features_scanned}")
        lines.append(f"Docs pages:          {report.docs_pages}")
        lines.append(f"Examples:              {report.examples_count}")
        lines.append("")
        
        if not report.has_issues:
            lines.append("✅ No issues found!")
            return "\n".join(lines)
        
        lines.append(f"⚠️  Issues Found: {report.total_issues + report.total_missing + report.total_duplicates}")
        lines.append("──────────────────────")
        lines.append("")
        
        # Duplicates
        if report.duplicates:
            lines.append(f"🔴 DUPLICATES ({len(report.duplicates)} clusters)")
            for cluster in report.duplicates:
                pages_str = ", ".join(self._short_path(p) for p in cluster.pages[:3])
                if len(cluster.pages) > 3:
                    pages_str += f" (+{len(cluster.pages) - 3} more)"
                lines.append(f"  • {cluster.slug}: {len(cluster.pages)} pages ({cluster.issue_type})")
            lines.append("")
        
        # Missing artifacts
        if report.missing_artifacts:
            lines.append(f"🟡 MISSING ARTIFACTS ({len(report.missing_artifacts)} features)")
            for slug, artifacts in list(report.missing_artifacts.items())[:10]:
                artifact_names = [a.value.replace("_", " ") for a in artifacts]
                lines.append(f"  • {slug}: missing {', '.join(artifact_names[:3])}")
                if len(artifact_names) > 3:
                    lines.append(f"    (+{len(artifact_names) - 3} more)")
            if len(report.missing_artifacts) > 10:
                lines.append(f"  ... and {len(report.missing_artifacts) - 10} more features")
            lines.append("")
        
        # Other issues
        if report.issues:
            naming_issues = [i for i in report.issues if "naming" in i.message.lower()]
            if naming_issues:
                lines.append(f"🟢 NAMING ISSUES ({len(naming_issues)})")
                for issue in naming_issues[:5]:
                    lines.append(f"  • {issue.message}")
                lines.append("")
        
        # Next actions
        lines.append("📋 Next Actions")
        lines.append("───────────────")
        lines.append("1. Run `praisonai standardise report --format markdown` for details")
        if report.duplicates:
            lines.append("2. Run `praisonai standardise fix --feature <slug>` to consolidate")
        if report.missing_artifacts:
            lines.append("3. Run `praisonai standardise init --feature <slug>` to create missing")
        lines.append("")
        
        return "\n".join(lines)
    
    def _generate_json(self, report: StandardiseReport) -> str:
        """Generate a JSON report."""
        return json.dumps(report.to_dict(), indent=2)
    
    def _generate_markdown(self, report: StandardiseReport) -> str:
        """Generate a Markdown report."""
        lines = []
        
        # Header
        lines.append("# PraisonAI Standardisation Report")
        lines.append("")
        lines.append(f"Generated: {report.timestamp}")
        lines.append("")
        
        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Features scanned | {report.features_scanned} |")
        lines.append(f"| Docs pages | {report.docs_pages} |")
        lines.append(f"| Examples | {report.examples_count} |")
        lines.append(f"| Total issues | {report.total_issues} |")
        lines.append(f"| Missing artifacts | {report.total_missing} |")
        lines.append(f"| Duplicate clusters | {report.total_duplicates} |")
        lines.append("")
        
        # Duplicates section
        if report.duplicates:
            lines.append("## Duplicate Clusters")
            lines.append("")
            for cluster in report.duplicates:
                lines.append(f"### {cluster.slug}")
                lines.append("")
                lines.append(f"- **Type**: {cluster.issue_type}")
                lines.append(f"- **Similarity**: {cluster.similarity_score:.0%}")
                lines.append(f"- **Recommendation**: {cluster.recommendation}")
                lines.append("")
                lines.append("**Pages:**")
                for page in cluster.pages:
                    lines.append(f"- `{page}`")
                lines.append("")
        
        # Missing artifacts section
        if report.missing_artifacts:
            lines.append("## Missing Artifacts")
            lines.append("")
            lines.append("| Feature | Missing |")
            lines.append("|---------|---------|")
            for slug, artifacts in report.missing_artifacts.items():
                artifact_names = ", ".join(a.value for a in artifacts)
                lines.append(f"| {slug} | {artifact_names} |")
            lines.append("")
        
        # Issues section
        if report.issues:
            lines.append("## Other Issues")
            lines.append("")
            for issue in report.issues:
                severity_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "⚪")
                lines.append(f"- {severity_icon} **{issue.issue_type.value}**: {issue.message}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _short_path(self, path: Path) -> str:
        """Get a shortened path for display."""
        parts = path.parts
        if len(parts) > 3:
            return "/".join(parts[-3:])
        return str(path)
    
    def save(self, report: StandardiseReport, output_path: Path, 
             format: str = "text") -> None:
        """Save a report to a file."""
        content = self.generate(report, format)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
