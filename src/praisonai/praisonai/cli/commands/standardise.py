"""
CLI commands for the FDEP standardisation system.

Commands:
- praisonai standardise check      - Check for standardisation issues
- praisonai standardise report     - Generate detailed report
- praisonai standardise fix        - Fix issues (with --apply)
- praisonai standardise init       - Initialise a new feature
- praisonai standardise ai         - AI-powered generation
- praisonai standardise checkpoint - Create undo checkpoint
- praisonai standardise undo       - Undo to previous checkpoint
- praisonai standardise redo       - Redo after undo
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
    
    # ai subcommand
    ai_parser = subparsers.add_parser(
        "ai",
        help="AI-powered generation of docs/examples",
    )
    ai_parser.add_argument(
        "feature",
        type=str,
        help="Feature slug to generate content for",
    )
    ai_parser.add_argument(
        "--type", "-t",
        choices=["docs", "examples", "all"],
        default="all",
        help="Type of content to generate",
    )
    ai_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create files (default: dry-run preview)",
    )
    ai_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify generated content with AI",
    )
    ai_parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model to use (default: gpt-4o-mini)",
    )
    _add_common_args(ai_parser)
    
    # checkpoint subcommand
    checkpoint_parser = subparsers.add_parser(
        "checkpoint",
        help="Create an undo checkpoint",
    )
    checkpoint_parser.add_argument(
        "--message", "-m",
        type=str,
        help="Checkpoint message",
    )
    checkpoint_parser.add_argument(
        "--path", "-p",
        type=str,
        default=".",
        help="Repository path",
    )
    
    # undo subcommand
    undo_parser = subparsers.add_parser(
        "undo",
        help="Undo to a previous checkpoint",
    )
    undo_parser.add_argument(
        "--checkpoint",
        type=str,
        help="Specific checkpoint ID to restore",
    )
    undo_parser.add_argument(
        "--list",
        action="store_true",
        help="List available checkpoints",
    )
    undo_parser.add_argument(
        "--path", "-p",
        type=str,
        default=".",
        help="Repository path",
    )
    
    # redo subcommand
    redo_parser = subparsers.add_parser(
        "redo",
        help="Redo after an undo",
    )
    redo_parser.add_argument(
        "--path", "-p",
        type=str,
        default=".",
        help="Repository path",
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
    elif parsed.subcommand == "ai":
        return _run_ai(parsed)
    elif parsed.subcommand == "checkpoint":
        return _run_checkpoint(parsed)
    elif parsed.subcommand == "undo":
        return _run_undo(parsed)
    elif parsed.subcommand == "redo":
        return _run_redo(parsed)
    
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


def _run_ai(parsed) -> int:
    """Run the AI generation subcommand with ACP/LSP runtime support."""
    import asyncio
    from praisonai.standardise.ai_generator import AIGenerator
    from praisonai.standardise.models import ArtifactType, FeatureSlug
    
    config = _create_config(parsed)
    
    slug = FeatureSlug.from_string(parsed.feature)
    if not slug.is_valid:
        print(f"Error: Invalid feature slug: {slug.validation_error}")
        return 2
    
    # Start ACP/LSP runtime for context gathering
    runtime = None
    try:
        from praisonai.cli.features.interactive_runtime import create_runtime
        runtime = create_runtime(
            workspace=str(config.sdk_root or config.project_root or "."),
            lsp=True,
            acp=False  # ACP not needed for generation
        )
        # Start runtime in background
        asyncio.get_event_loop().run_until_complete(runtime.start())
        if runtime.lsp_ready:
            print("🔧 LSP server ready for code intelligence")
    except Exception:
        # Runtime is optional, continue without it
        pass
    
    generator = AIGenerator(
        model=parsed.model,
        sdk_root=config.sdk_root,
        docs_root=config.docs_root,
        examples_root=config.examples_root,
        use_fast_context=True,
    )
    
    # Determine which artifacts to generate
    artifact_types = []
    gen_type = getattr(parsed, "type", "all")
    
    if gen_type in ["docs", "all"]:
        artifact_types.extend([
            ArtifactType.DOCS_CONCEPT,
            ArtifactType.DOCS_FEATURE,
            ArtifactType.DOCS_CLI,
            ArtifactType.DOCS_SDK,
        ])
    
    if gen_type in ["examples", "all"]:
        artifact_types.extend([
            ArtifactType.EXAMPLE_BASIC,
            ArtifactType.EXAMPLE_ADVANCED,
        ])
    
    print(f"🤖 AI Generation for '{slug.normalised}'")
    print("=" * 50)
    
    results = []
    for artifact_type in artifact_types:
        print(f"\n📝 Generating {artifact_type.value}...")
        
        try:
            # Generate with execution verification for examples
            content, output_path, verification_info = generator.generate(
                slug, artifact_type,
                dry_run=not parsed.apply,
                verify_execution=True,
            )
            
            # Show verification results for examples
            if verification_info:
                if verification_info.get("execution_passed"):
                    print("  ✅ Code verified: runs successfully")
                elif verification_info.get("requires_external"):
                    libs = ", ".join(verification_info.get("missing_libraries", []))
                    print(f"  ⚠️  Requires external libraries: {libs}")
                elif not verification_info.get("syntax_valid"):
                    print(f"  ❌ Syntax error: {verification_info.get('error', 'Unknown')[:100]}")
                else:
                    print(f"  ❌ Execution failed after {verification_info.get('attempt', 1)} attempts")
                    if verification_info.get("error"):
                        print(f"     Error: {verification_info['error'][:150]}")
            
            # AI content verification (optional)
            if parsed.verify:
                print("  🔍 AI content review...")
                is_valid, summary, issues = generator.verify(content, artifact_type, slug)
                if is_valid:
                    print(f"  ✅ {summary}")
                else:
                    print(f"  ⚠️  {summary}")
                    for issue in issues[:3]:
                        print(f"     - {issue}")
            
            # Check if we should write
            can_write = True
            if verification_info and not verification_info.get("success"):
                if not verification_info.get("requires_external"):
                    can_write = False
                    print("  ⛔ Not writing: code doesn't run")
            
            if parsed.apply and output_path and can_write:
                print(f"  ✓ Created: {output_path}")
                results.append((artifact_type.value, True, output_path))
            elif not parsed.apply:
                print(f"  📋 Preview ({len(content)} chars)")
                # Show first few lines
                preview_lines = content.split("\n")[:10]
                for line in preview_lines:
                    print(f"     {line[:60]}")
                if len(content.split("\n")) > 10:
                    print("     ...")
                results.append((artifact_type.value, True, None))
            else:
                results.append((artifact_type.value, False, "Verification failed"))
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append((artifact_type.value, False, str(e)))
    
    print("\n" + "=" * 50)
    print("Summary:")
    success_count = sum(1 for _, success, _ in results if success)
    print(f"  Generated: {success_count}/{len(results)}")
    
    if not parsed.apply:
        print("\nRun with --apply to create these files.")
    
    # Cleanup runtime
    if runtime:
        try:
            asyncio.get_event_loop().run_until_complete(runtime.stop())
        except Exception:
            pass
    
    return 0


def _run_checkpoint(parsed) -> int:
    """Run the checkpoint subcommand."""
    from praisonai.standardise.undo_redo import UndoRedoManager
    
    manager = UndoRedoManager(Path(parsed.path).resolve())
    
    success, result = manager.create_checkpoint(parsed.message)
    
    if success:
        print(f"✓ Checkpoint created: {result}")
    else:
        print(f"❌ Failed: {result}")
        return 1
    
    return 0


def _run_undo(parsed) -> int:
    """Run the undo subcommand."""
    from praisonai.standardise.undo_redo import UndoRedoManager
    
    manager = UndoRedoManager(Path(parsed.path).resolve())
    
    # List checkpoints if requested
    if getattr(parsed, "list", False):
        checkpoints = manager.list_checkpoints()
        if not checkpoints:
            print("No checkpoints found.")
            return 0
        
        print("Available checkpoints:")
        for cp_id, date, message in checkpoints:
            print(f"  • {cp_id} ({date}): {message[:50]}")
        return 0
    
    # Undo to checkpoint
    success, result = manager.undo(parsed.checkpoint)
    
    if success:
        print(f"✓ {result}")
    else:
        print(f"❌ {result}")
        return 1
    
    return 0


def _run_redo(parsed) -> int:
    """Run the redo subcommand."""
    from praisonai.standardise.undo_redo import UndoRedoManager
    
    manager = UndoRedoManager(Path(parsed.path).resolve())
    
    success, result = manager.redo()
    
    if success:
        print(f"✓ {result}")
    else:
        print(f"❌ {result}")
        return 1
    
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
