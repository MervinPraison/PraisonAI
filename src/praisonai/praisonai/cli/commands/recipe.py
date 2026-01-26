"""
Recipe command group for PraisonAI CLI.

Provides recipe management commands.
"""

import typer

app = typer.Typer(help="Recipe management")


@app.command("create")
def recipe_create(
    goal: str = typer.Argument(..., help="Natural language goal for the recipe"),
    output: str = typer.Option(".", "--output", "-o", help="Output directory"),
    no_optimize: bool = typer.Option(False, "--no-optimize", help="Skip optimization loop"),
    iterations: int = typer.Option(3, "--iterations", help="Max optimization iterations"),
    threshold: float = typer.Option(8.0, "--threshold", help="Score threshold to stop"),
    agents: str = typer.Option(None, "--agents", help="Custom agents (format: name:role=X,goal=Y;name2:...)"),
    tools: str = typer.Option(None, "--tools", help="Custom tools per agent (format: agent:tool1,tool2;...)"),
    agent_types: str = typer.Option(None, "--agent-types", help="Agent types (format: agent:image;agent2:audio;...)"),
):
    """Create a new recipe from a natural language goal.
    
    Examples:
        praisonai recipe create "Build a web scraper for news"
        praisonai recipe create "Research AI trends" --no-optimize
        praisonai recipe create "Research AI" --agents "researcher:role=AI Researcher,goal=Find papers"
        praisonai recipe create "Research AI" --tools "researcher:internet_search,arxiv"
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'create', goal]
    if output != ".":
        argv.extend(['--output', output])
    if no_optimize:
        argv.append('--no-optimize')
    if iterations != 3:
        argv.extend(['--iterations', str(iterations)])
    if threshold != 8.0:
        argv.extend(['--threshold', str(threshold)])
    if agents:
        argv.extend(['--agents', agents])
    if tools:
        argv.extend(['--tools', tools])
    if agent_types:
        argv.extend(['--agent-types', agent_types])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


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
    context: bool = typer.Option(False, "--context", help="Evaluate context flow between agents (default mode)"),
    memory: bool = typer.Option(False, "--memory", help="Evaluate memory utilization (store/search effectiveness)"),
    knowledge: bool = typer.Option(False, "--knowledge", help="Evaluate knowledge retrieval effectiveness"),
    goal: str = typer.Option(None, "--goal", "-g", help="Override recipe goal for evaluation (extracted from YAML if not provided)"),
):
    """Judge a recipe execution trace and generate fix recommendations.
    
    Similar to 'terraform plan' - analyzes the trace and generates a plan of fixes.
    
    The judge now includes:
    - Dynamic failure detection (LLM determines if task failed)
    - Previous step quality context (each agent sees how prior agents performed)
    - Recipe goal evaluation (evaluates against overall workflow objective)
    - Input validation status (detects unresolved template variables)
    
    Evaluation Modes:
    - --context: Evaluate context flow between agents (default)
    - --memory: Evaluate memory utilization (store/search effectiveness)
    - --knowledge: Evaluate knowledge retrieval effectiveness
    
    Examples:
        praisonai recipe judge run-abc123
        praisonai recipe judge run-abc123 --goal "Analyze image and create blog post"
        praisonai recipe judge run-abc123 --memory
        praisonai recipe judge run-abc123 --knowledge
        praisonai recipe judge run-abc123 --yaml agents.yaml --output plan.yaml
        praisonai recipe judge run-abc123 --dry-run
    """
    from praisonai.replay import (
        ContextTraceReader,
        ContextEffectivenessJudge,
        generate_plan_from_report,
        format_judge_report,
    )
    
    # Determine evaluation mode (default to context)
    mode = "context"
    if memory:
        mode = "memory"
    elif knowledge:
        mode = "knowledge"
    
    mode_emoji = {"context": "🔄", "memory": "🧠", "knowledge": "📚"}
    print(f"{mode_emoji.get(mode, '🔍')} Judging trace: {trace_id} (mode: {mode})")
    
    try:
        reader = ContextTraceReader(trace_id)
        events = reader.get_all()
        
        if not events:
            print(f"❌ No events found for trace: {trace_id}")
            raise typer.Exit(1)
        
        print(f"  📊 Found {len(events)} events")
        
        # Run judge with mode-specific evaluation
        judge = ContextEffectivenessJudge(mode=mode)
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


@app.command("optimize")
def recipe_optimize(
    recipe_path: str = typer.Argument(..., help="Path to recipe folder"),
    target: str = typer.Argument(None, help="Optional optimization target (e.g., 'improve error handling')"),
    iterations: int = typer.Option(3, "--iterations", "-i", help="Maximum optimization iterations"),
    threshold: float = typer.Option(8.0, "--threshold", "-t", help="Score threshold to stop (1-10)"),
    input_data: str = typer.Option("", "--input", help="Input data for recipe runs"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Optimize a recipe using AI judge feedback.
    
    Iteratively runs the recipe, judges output, and applies improvements.
    
    Examples:
        praisonai recipe optimize my-recipe
        praisonai recipe optimize my-recipe "improve error handling"
        praisonai recipe optimize my-recipe --iterations 5 --threshold 9.0
        praisonai recipe optimize my-recipe --input '{"query": "test"}'
    """
    from pathlib import Path
    import logging
    
    if verbose:
        logging.basicConfig(level=logging.INFO)
    
    recipe_path_obj = Path(recipe_path)
    if not recipe_path_obj.exists():
        print(f"❌ Recipe not found: {recipe_path}")
        raise typer.Exit(1)
    
    print(f"🔄 Optimizing recipe: {recipe_path}")
    print(f"   Max iterations: {iterations}")
    print(f"   Score threshold: {threshold}")
    if target:
        print(f"   Target: {target}")
    
    try:
        from praisonai.cli.features.recipe_optimizer import RecipeOptimizer
        
        optimizer = RecipeOptimizer(
            max_iterations=iterations,
            score_threshold=threshold,
        )
        
        final_report = optimizer.optimize(
            recipe_path=recipe_path_obj,
            input_data=input_data,
            optimization_target=target,
        )
        
        if final_report:
            score = getattr(final_report, 'overall_score', 0)
            print(f"\n{'✅' if score >= threshold else '📊'} Final score: {score}/10")
            
            if score >= threshold:
                print("   Recipe optimization complete!")
            else:
                print("   Threshold not reached. Consider running more iterations.")
        else:
            print("❌ Optimization failed - no report generated")
            raise typer.Exit(1)
            
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Install with: pip install litellm")
        raise typer.Exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise typer.Exit(1)


@app.command("serve")
def recipe_serve(
    recipe: str = typer.Argument(None, help="Recipe name or path to serve (optional, serves all if not specified)"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    port: int = typer.Option(8765, "--port", "-p", help="Server port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable hot reload"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
    config: str = typer.Option(None, "--config", "-c", help="Path to serve.yaml config file"),
    api_key: str = typer.Option(None, "--api-key", help="API key for authentication"),
    cors: str = typer.Option("*", "--cors", help="CORS origins (comma-separated or *)"),
    metrics: bool = typer.Option(False, "--metrics", help="Enable /metrics endpoint"),
    admin: bool = typer.Option(False, "--admin", help="Enable /admin endpoints"),
):
    """Start HTTP server for recipe execution.
    
    Serves recipes as REST API endpoints.
    
    Examples:
        praisonai recipe serve
        praisonai recipe serve my-recipe --port 8080
        praisonai recipe serve --host 0.0.0.0 --port 8000
        praisonai recipe serve --config serve.yaml
        praisonai recipe serve --api-key my-secret-key
        praisonai recipe serve --workers 4
    """
    print(f"🚀 Starting recipe server...")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    if recipe:
        print(f"   Recipe: {recipe}")
    if config:
        print(f"   Config: {config}")
    if api_key:
        print(f"   Auth: API Key enabled")
    if workers > 1:
        print(f"   Workers: {workers}")
    
    try:
        from praisonai.recipe.serve import serve, load_config
        
        # Load config from file if provided
        serve_config = {}
        if config:
            serve_config = load_config(config)
        
        # Override with CLI options
        if api_key:
            serve_config["api_key"] = api_key
            serve_config["auth"] = "api-key"
        if cors:
            serve_config["cors_origins"] = cors
        if metrics:
            serve_config["enable_metrics"] = True
        if admin:
            serve_config["enable_admin"] = True
        if recipe:
            serve_config["recipes"] = [recipe]
        
        print(f"\n📡 Server running at http://{host}:{port}")
        print(f"   Health: http://{host}:{port}/health")
        print(f"   Recipes: http://{host}:{port}/v1/recipes")
        print(f"   OpenAPI: http://{host}:{port}/openapi.json")
        if metrics:
            print(f"   Metrics: http://{host}:{port}/metrics")
        print(f"\n   Press Ctrl+C to stop\n")
        
        serve(
            host=host,
            port=port,
            reload=reload,
            config=serve_config,
            workers=workers,
        )
        
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Install with: pip install praisonai[serve]")
        raise typer.Exit(1)
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
