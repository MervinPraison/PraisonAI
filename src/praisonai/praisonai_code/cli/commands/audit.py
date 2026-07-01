"""
CLI command for agent-centric compliance auditing.

Usage:
    praisonai audit agent-centric --scan /path/to/examples
    praisonai audit agent-centric --fix /path/to/examples
    praisonai audit agent-centric --check /path/to/examples
"""

import click
import json
import sys
from pathlib import Path


@click.group()
def audit():
    """Audit commands for compliance checking."""
    pass


@audit.command("agent-centric")
@click.option("--scan", "scan_path", type=click.Path(exists=True), help="Scan path for compliance")
@click.option("--fix", "fix_path", type=click.Path(exists=True), help="Fix non-compliant files")
@click.option("--check", "check_path", type=click.Path(exists=True), help="Check and fail if non-compliant")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--line-limit", default=40, help="Line limit for header scan (default: 40)")
@click.option("--only-examples", is_flag=True, help="Only scan Python examples")
@click.option("--only-docs", is_flag=True, help="Only scan documentation")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def agent_centric(scan_path, fix_path, check_path, output_json, line_limit, only_examples, only_docs, verbose):
    """
    Audit agent-centric compliance for examples and docs.
    
    Examples:
        praisonai audit agent-centric --scan ./examples
        praisonai audit agent-centric --fix ./examples --verbose
        praisonai audit agent-centric --check ./examples  # Fails if non-compliant
    """
    from praisonai.audit.agent_centric import AgentCentricAuditor, ComplianceStatus
    
    path = scan_path or fix_path or check_path
    if not path:
        click.echo("Error: Must specify --scan, --fix, or --check with a path", err=True)
        sys.exit(1)
    
    auditor = AgentCentricAuditor(line_limit=line_limit, verbose=verbose)
    
    if fix_path:
        # Fix mode
        click.echo(f"Fixing non-compliant files in: {fix_path}")
        report = auditor.scan(fix_path)
        
        fixed_count = 0
        for result in report.results:
            if result.status == ComplianceStatus.NON_COMPLIANT:
                success, reason = auditor.fix_file(result.file_path)
                if success:
                    fixed_count += 1
                    if verbose:
                        click.echo(f"  Fixed: {result.file_path} - {reason}")
        
        click.echo(f"\nFixed {fixed_count} files")
        
        # Re-scan to verify
        report = auditor.scan(fix_path)
        click.echo(f"Compliance rate: {report.compliance_rate():.1f}%")
        
    else:
        # Scan or check mode
        report = auditor.scan(path)
        
        if output_json:
            click.echo(auditor.to_json(report))
        else:
            click.echo(f"\n{'='*60}")
            click.echo("AGENT-CENTRIC COMPLIANCE REPORT")
            click.echo(f"{'='*60}")
            click.echo(f"Total files:    {report.total_files}")
            click.echo(f"Compliant:      {report.compliant}")
            click.echo(f"Non-compliant:  {report.non_compliant}")
            click.echo(f"Skipped:        {report.skipped}")
            click.echo(f"Compliance rate: {report.compliance_rate():.1f}%")
            
            if report.by_reason:
                click.echo(f"\nBy Reason:")
                for reason, count in sorted(report.by_reason.items()):
                    click.echo(f"  {reason}: {count}")
            
            if verbose and report.non_compliant > 0:
                click.echo(f"\nNon-compliant files:")
                for r in report.results:
                    if r.status == ComplianceStatus.NON_COMPLIANT:
                        click.echo(f"  {r.file_path}")
                        click.echo(f"    Reason: {r.reason.value if r.reason else 'unknown'}")
        
        # Check mode - fail if non-compliant
        if check_path and report.non_compliant > 0:
            click.echo(f"\n❌ FAILED: {report.non_compliant} non-compliant files found", err=True)
            sys.exit(1)
        elif check_path:
            click.echo(f"\n✓ PASSED: All files are agent-centric compliant")
