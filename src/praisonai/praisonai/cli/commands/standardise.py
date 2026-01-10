"""
CLI commands for the FDEP standardisation system.

Commands:
- praisonai standardise check   - Check for standardisation issues
- praisonai standardise report  - Generate detailed report
- praisonai standardise fix     - Fix issues (with --apply)
- praisonai standardise init    - Initialise a new feature
"""

import sys
from pathlib import Path


def _lazy_import_engine():
    """Lazy import to avoid heavy imports at CLI startup."""
    from praisonai.standardise import StandardiseEngine, StandardiseConfig
    return StandardiseEngine, StandardiseConfig


def standardise_command(args=None):
    """Main entry point for standardise command."""
    import argparse
    
    parser = argparse.ArgumentParser(
        prog="praisonai standardise",
        description="Standardise documentation and examples (FDEP)",
    )
    
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
    
    # check subcommand
    check_parser = subparsers.add_parser(
        "check",
        help="Check for standardisation issues (default)",
    )
    _add_common_args(check_parser)
    
    # report subcommand
    report_parser = subparsers.add_parser(
        "report",
        help="Generate detailed report",
    )
    _add_common_args(report_parser)
    report_parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "markdown"],
        default="text",
        help="Report format (default: text)",
    )
    report_parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file path (default: stdout)",
    )
    
    # fix subcommand
    fix_parser = subparsers.add_parser(
        "fix",
        help="Fix standardisation issues",
    )
    _add_common_args(fix_parser)
    fix_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes (default: dry-run)",
    )
    fix_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create backups before changes",
    )
    
    # init subcommand
    init_parser = subparsers.add_parser(
        "init",
        help="Initialise a new feature with all required artifacts",
    )
    init_parser.add_argument(
        "feature",
        type=str,
        help="Feature slug to initialise",
    )
    _add_common_args(init_parser)
    init_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create files (default: dry-run)",
    )
    
    # Parse args
    parsed = parser.parse_args(args)
    
    # Default to check if no subcommand
    if not parsed.subcommand:
        parsed.subcommand = "check"
        parsed = parser.parse_args(["check"] + (args or []))
    
    # Execute subcommand
    if parsed.subcommand == "check":
        return _run_check(parsed)
    elif parsed.subcommand == "report":
        return _run_report(parsed)
    elif parsed.subcommand == "fix":
        return _run_fix(parsed)
    elif parsed.subcommand == "init":
        return _run_init(parsed)
    
    return 0


def _add_common_args(parser):
    """Add common arguments to a parser."""
    parser.add_argument(
        "--path", "-p",
        type=str,
        default=".",
        help="Project root path (default: current directory)",
    )
    parser.add_argument(
        "--feature",
        type=str,
        help="Specific feature slug to check",
    )
    parser.add_argument(
        "--scope",
        choices=["all", "docs", "examples", "sdk", "cli"],
        default="all",
        help="Scope of check (default: all)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode (no prompts, machine-readable output)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Don't make changes (default: true)",
    )


def _create_config(parsed):
    """Create config from parsed arguments."""
    _, StandardiseConfig = _lazy_import_engine()
    
    config = StandardiseConfig(
        project_root=Path(parsed.path).resolve() if hasattr(parsed, "path") else None,
        dry_run=getattr(parsed, "dry_run", True) and not getattr(parsed, "apply", False),
        backup=not getattr(parsed, "no_backup", False),
        scope=getattr(parsed, "scope", "all"),
        feature_filter=getattr(parsed, "feature", None),
        ci_mode=getattr(parsed, "ci", False),
        report_format=getattr(parsed, "format", "text"),
    )
    
    return config


def _run_check(parsed) -> int:
    """Run the check subcommand."""
    StandardiseEngine, StandardiseConfig = _lazy_import_engine()
    
    config = _create_config(parsed)
    engine = StandardiseEngine(config)
    
    report = engine.check()
    
    # Print report
    output = engine.reports.generate(report, "text")
    print(output)
    
    # Return exit code
    if config.ci_mode:
        return engine.get_exit_code(report)
    
    return 0


def _run_report(parsed) -> int:
    """Run the report subcommand."""
    StandardiseEngine, StandardiseConfig = _lazy_import_engine()
    
    config = _create_config(parsed)
    engine = StandardiseEngine(config)
    
    report = engine.check()
    output = engine.reports.generate(report, parsed.format)
    
    if parsed.output:
        Path(parsed.output).write_text(output, encoding="utf-8")
        print(f"Report saved to {parsed.output}")
    else:
        print(output)
    
    if config.ci_mode:
        return engine.get_exit_code(report)
    
    return 0


def _run_fix(parsed) -> int:
    """Run the fix subcommand."""
    StandardiseEngine, StandardiseConfig = _lazy_import_engine()
    
    config = _create_config(parsed)
    engine = StandardiseEngine(config)
    
    actions = engine.fix(
        feature=parsed.feature,
        apply=parsed.apply,
    )
    
    if not actions["planned"]:
        print("No fixes needed.")
        return 0
    
    print(f"Planned actions ({len(actions['planned'])}):")
    for action in actions["planned"]:
        print(f"  • {action}")
    
    if parsed.apply:
        print(f"\nApplied actions ({len(actions['applied'])}):")
        for action in actions["applied"]:
            print(f"  ✓ {action}")
    else:
        print("\nRun with --apply to execute these changes.")
    
    return 0


def _run_init(parsed) -> int:
    """Run the init subcommand."""
    StandardiseEngine, StandardiseConfig = _lazy_import_engine()
    
    config = _create_config(parsed)
    engine = StandardiseEngine(config)
    
    try:
        created = engine.init(parsed.feature)
    except ValueError as e:
        print(f"Error: {e}")
        return 2
    
    if not created:
        print(f"Feature '{parsed.feature}' already has all required artifacts.")
        return 0
    
    print(f"{'Would create' if config.dry_run else 'Created'} artifacts for '{parsed.feature}':")
    for artifact_type, path in created.items():
        status = "📝" if config.dry_run else "✓"
        print(f"  {status} {artifact_type}: {path}")
    
    if config.dry_run:
        print("\nRun with --apply to create these files.")
    
    return 0


# Click-based alternative for integration with main CLI
def register_click_commands(app):
    """Register click commands with the main CLI app."""
    try:
        import click
    except ImportError:
        return
    
    @app.group(name="standardise")
    def standardise_group():
        """Standardise documentation and examples (FDEP)."""
        pass
    
    @standardise_group.command(name="check")
    @click.option("--path", "-p", default=".", help="Project root path")
    @click.option("--feature", help="Specific feature slug to check")
    @click.option("--scope", type=click.Choice(["all", "docs", "examples", "sdk", "cli"]), default="all")
    @click.option("--ci", is_flag=True, help="CI mode")
    def check_cmd(path, feature, scope, ci):
        """Check for standardisation issues."""
        StandardiseEngine, StandardiseConfig = _lazy_import_engine()
        
        config = StandardiseConfig(
            project_root=Path(path).resolve(),
            feature_filter=feature,
            scope=scope,
            ci_mode=ci,
        )
        engine = StandardiseEngine(config)
        report = engine.check()
        
        output = engine.reports.generate(report, "text")
        click.echo(output)
        
        if ci:
            sys.exit(engine.get_exit_code(report))
    
    @standardise_group.command(name="report")
    @click.option("--path", "-p", default=".", help="Project root path")
    @click.option("--format", "-f", type=click.Choice(["text", "json", "markdown"]), default="text")
    @click.option("--output", "-o", help="Output file path")
    @click.option("--ci", is_flag=True, help="CI mode")
    def report_cmd(path, format, output, ci):
        """Generate detailed report."""
        StandardiseEngine, StandardiseConfig = _lazy_import_engine()
        
        config = StandardiseConfig(
            project_root=Path(path).resolve(),
            ci_mode=ci,
        )
        engine = StandardiseEngine(config)
        report = engine.check()
        
        content = engine.reports.generate(report, format)
        
        if output:
            Path(output).write_text(content, encoding="utf-8")
            click.echo(f"Report saved to {output}")
        else:
            click.echo(content)
    
    @standardise_group.command(name="fix")
    @click.option("--path", "-p", default=".", help="Project root path")
    @click.option("--feature", help="Specific feature slug to fix")
    @click.option("--apply", is_flag=True, help="Actually apply changes")
    @click.option("--no-backup", is_flag=True, help="Don't create backups")
    def fix_cmd(path, feature, apply, no_backup):
        """Fix standardisation issues."""
        StandardiseEngine, StandardiseConfig = _lazy_import_engine()
        
        config = StandardiseConfig(
            project_root=Path(path).resolve(),
            feature_filter=feature,
            dry_run=not apply,
            backup=not no_backup,
        )
        engine = StandardiseEngine(config)
        
        actions = engine.fix(feature=feature, apply=apply)
        
        if not actions["planned"]:
            click.echo("No fixes needed.")
            return
        
        click.echo(f"Planned actions ({len(actions['planned'])}):")
        for action in actions["planned"]:
            click.echo(f"  • {action}")
        
        if apply:
            click.echo(f"\nApplied actions ({len(actions['applied'])}):")
            for action in actions["applied"]:
                click.echo(f"  ✓ {action}")
        else:
            click.echo("\nRun with --apply to execute these changes.")
    
    @standardise_group.command(name="init")
    @click.argument("feature")
    @click.option("--path", "-p", default=".", help="Project root path")
    @click.option("--apply", is_flag=True, help="Actually create files")
    def init_cmd(feature, path, apply):
        """Initialise a new feature with all required artifacts."""
        StandardiseEngine, StandardiseConfig = _lazy_import_engine()
        
        config = StandardiseConfig(
            project_root=Path(path).resolve(),
            dry_run=not apply,
        )
        engine = StandardiseEngine(config)
        
        try:
            created = engine.init(feature)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(2)
        
        if not created:
            click.echo(f"Feature '{feature}' already has all required artifacts.")
            return
        
        action_word = "Would create" if config.dry_run else "Created"
        click.echo(f"{action_word} artifacts for '{feature}':")
        for artifact_type, artifact_path in created.items():
            status = "📝" if config.dry_run else "✓"
            click.echo(f"  {status} {artifact_type}: {artifact_path}")
        
        if config.dry_run:
            click.echo("\nRun with --apply to create these files.")
    
    return standardise_group


if __name__ == "__main__":
    sys.exit(standardise_command())
