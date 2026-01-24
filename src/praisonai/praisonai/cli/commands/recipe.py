"""
Recipe command group for PraisonAI CLI.

Provides recipe management commands.
"""

import typer

app = typer.Typer(help="Recipe management")


@app.command("list")
def recipe_list():
    """List available recipes."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'list']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("run")
def recipe_run(
    name: str = typer.Argument(..., help="Recipe name"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model to use"),
    var: list[str] = typer.Option(None, "--var", help="Variable override (key=value), can be used multiple times"),
    save: bool = typer.Option(False, "--save", "-s", help="Save replay trace for debugging"),
    trace_name: str = typer.Option(None, "--name", "-n", help="Custom trace name (e.g., run-abc123). Overwrites if exists."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    output: str = typer.Option(None, "--output", "-o", help="Output mode: silent, status, trace, verbose, debug"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
    profile: bool = typer.Option(False, "--profile", help="Enable profiling"),
    deep_profile: bool = typer.Option(False, "--deep-profile", help="Enable deep profiling"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without executing"),
    force: bool = typer.Option(False, "--force", help="Force execution even with missing deps"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
):
    """Run a recipe with optional variable overrides.
    
    Examples:
        praisonai recipe run ai-url-blog-generator --var url="https://example.com/article"
        praisonai recipe run ai-dynamic-blog-generator --var topic="LangGraph 0.3" --var style="coding"
        praisonai recipe run ai-wordpress-post-generator --save --verbose
        praisonai recipe run ai-topic-gatherer --save --name my-test-run --var topic="AI"
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'run', name]
    if model:
        argv.extend(['--model', model])
    
    # Pass --var directly to the recipe handler (features/recipe.py)
    # Don't convert to --workflow-var as that gets consumed by main.py's parser
    if var:
        for v in var:
            argv.extend(['--var', v])
    
    # Forward all flags to the recipe handler
    if save:
        argv.append('--save')
    if trace_name:
        argv.extend(['--name', trace_name])
    if verbose:
        argv.append('--verbose')
    if output:
        argv.extend(['--output', output])
    if debug:
        argv.append('--debug')
    if profile:
        argv.append('--profile')
    if deep_profile:
        argv.append('--deep-profile')
    if dry_run:
        argv.append('--dry-run')
    if force:
        argv.append('--force')
    if json_output:
        argv.append('--json')
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv




@app.command("install")
def recipe_install(
    source: str = typer.Argument(..., help="Recipe source (path or URL)"),
):
    """Install a recipe."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'install', source]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("judge")
def recipe_judge(
    trace_id: str = typer.Argument(..., help="Trace ID to judge (e.g., run-abc123)"),
    yaml_file: str = typer.Option(None, "--yaml", "-y", help="YAML file path for fix recommendations"),
    output: str = typer.Option(None, "--output", "-o", help="Output plan file (default: judge_plan.yaml)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without saving"),
):
    """Judge a recipe execution trace and generate fix recommendations.
    
    Similar to 'terraform plan' - analyzes the trace and generates a plan of fixes.
    
    Examples:
        praisonai recipe judge run-abc123
        praisonai recipe judge run-abc123 --yaml agents.yaml --output plan.yaml
        praisonai recipe judge run-abc123 --dry-run
    """
    from praisonai.replay import (
        ContextTraceReader,
        ContextEffectivenessJudge,
        generate_plan_from_report,
        format_judge_report,
    )
    
    print(f"🔍 Judging trace: {trace_id}")
    
    try:
        reader = ContextTraceReader(trace_id)
        events = reader.get_all()
        
        if not events:
            print(f"❌ No events found for trace: {trace_id}")
            raise typer.Exit(1)
        
        print(f"  📊 Found {len(events)} events")
        
        # Run judge with YAML-aware evaluation if yaml_file provided
        judge = ContextEffectivenessJudge()
        report = judge.judge_trace(events, session_id=trace_id, yaml_file=yaml_file)
        
        # Display report
        print(format_judge_report(report))
        
        # Generate plan if yaml_file provided
        if yaml_file:
            plan = generate_plan_from_report(report, yaml_file=yaml_file)
            print(plan.format_summary())
            
            if not dry_run:
                output_file = output or "judge_plan.yaml"
                plan.save(output_file)
                print(f"\n✅ Plan saved to: {output_file}")
                print(f"   Run 'praisonai recipe apply {output_file}' to apply fixes")
        else:
            print("\n💡 Tip: Add --yaml <file> to generate actionable fix recommendations")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        raise typer.Exit(1)


@app.command("apply")
def recipe_apply(
    plan_file: str = typer.Argument(..., help="Plan file to apply (from 'recipe judge')"),
    confirm: bool = typer.Option(False, "--confirm", "-c", help="Apply without confirmation"),
    fix_ids: str = typer.Option(None, "--fix-ids", help="Comma-separated fix IDs to apply"),
    no_backup: bool = typer.Option(False, "--no-backup", help="Skip creating backup"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
):
    """Apply fixes from a judge plan to YAML files.
    
    Similar to 'terraform apply' - applies the planned fixes.
    
    Examples:
        praisonai recipe apply judge_plan.yaml
        praisonai recipe apply judge_plan.yaml --confirm
        praisonai recipe apply judge_plan.yaml --fix-ids fix_001,fix_002
        praisonai recipe apply judge_plan.yaml --dry-run
    """
    from praisonai.replay import JudgePlan, PlanApplier
    from pathlib import Path
    
    print(f"📋 Loading plan: {plan_file}")
    
    try:
        if not Path(plan_file).exists():
            print(f"❌ Plan file not found: {plan_file}")
            raise typer.Exit(1)
        
        plan = JudgePlan.load(plan_file)
        applier = PlanApplier(plan)
        
        # Show preview
        print(applier.preview())
        
        if dry_run:
            print("\n🔍 Dry run - no changes applied")
            return
        
        # Confirm before applying
        if not confirm:
            response = typer.prompt("Apply these fixes? [y/N]", default="n")
            if response.lower() != "y":
                print("❌ Aborted")
                raise typer.Exit(0)
        
        # Parse fix IDs if provided
        fix_id_list = None
        if fix_ids:
            fix_id_list = [f.strip() for f in fix_ids.split(",")]
        
        # Apply fixes
        result = applier.apply(backup=not no_backup, fix_ids=fix_id_list)
        
        # Validate
        if applier.validate():
            print("✅ YAML validation passed")
        else:
            print("⚠️  YAML validation failed - consider rolling back")
            if result.get("backup_path"):
                print(f"   Backup available at: {result['backup_path']}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        raise typer.Exit(1)
