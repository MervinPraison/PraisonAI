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




@app.command("info")
def recipe_info(
    name: str = typer.Argument(..., help="Recipe name"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full YAML content"),
):
    """Show detailed information about a recipe.
    
    Displays recipe metadata, agents, steps, and tools.
    
    Examples:
        praisonai recipe info image-to-blog-generator
        praisonai recipe info url-to-blog-generator --verbose
    """
    from pathlib import Path
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    import yaml
    
    console = Console()
    
    # Find recipe path
    recipe_path = None
    
    # Check template search paths
    try:
        from praisonai.recipe.core import get_template_search_paths
        for search_path in get_template_search_paths():
            candidate = search_path / name
            if candidate.exists() and (candidate / "agents.yaml").exists():
                recipe_path = candidate
                break
    except ImportError:
        pass
    
    # Also check agent_recipes package
    if not recipe_path:
        try:
            import agent_recipes
            if hasattr(agent_recipes, 'get_template_path'):
                template_base = Path(agent_recipes.get_template_path(""))
                candidate = template_base / name
                if candidate.exists() and (candidate / "agents.yaml").exists():
                    recipe_path = candidate
        except ImportError:
            pass
    
    # Check current directory
    if not recipe_path:
        candidate = Path(name)
        if candidate.exists() and (candidate / "agents.yaml").exists():
            recipe_path = candidate
    
    if not recipe_path:
        console.print(f"[red]❌ Recipe not found: {name}[/red]")
        console.print("[dim]Hint: Run 'praisonai recipe list' to see available recipes[/dim]")
        raise typer.Exit(1)
    
    # Load agents.yaml
    yaml_path = recipe_path / "agents.yaml"
    try:
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]❌ Error loading recipe: {e}[/red]")
        raise typer.Exit(1)
    
    # Display recipe info
    console.print()
    console.print(Panel(f"[bold cyan]{name}[/bold cyan]", title="Recipe Info"))
    
    # Metadata
    metadata = config.get("metadata", {})
    if metadata:
        console.print("\n[bold]Metadata:[/bold]")
        meta_table = Table(show_header=False, box=None)
        meta_table.add_column("Key", style="dim")
        meta_table.add_column("Value")
        for key, value in metadata.items():
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            elif isinstance(value, dict):
                value = str(value)
            meta_table.add_row(key, str(value))
        console.print(meta_table)
    
    # Topic
    topic = config.get("topic", "Not specified")
    console.print(f"\n[bold]Topic:[/bold] {topic}")
    
    # Agents
    agents = config.get("agents", {})
    if agents:
        console.print(f"\n[bold]Agents ({len(agents)}):[/bold]")
        agent_table = Table(show_header=True, header_style="bold")
        agent_table.add_column("Name", style="green")
        agent_table.add_column("Role")
        agent_table.add_column("Tools", style="cyan")
        agent_table.add_column("LLM", style="dim")
        
        for agent_name, agent_config in agents.items():
            tools = agent_config.get("tools", [])
            tools_str = ", ".join(tools) if tools else "-"
            llm = agent_config.get("llm", "default")
            agent_table.add_row(
                agent_name,
                agent_config.get("role", "-"),
                tools_str,
                str(llm)
            )
        console.print(agent_table)
    
    # Steps
    steps = config.get("steps", [])
    if steps:
        console.print(f"\n[bold]Steps ({len(steps)}):[/bold]")
        step_table = Table(show_header=True, header_style="bold")
        step_table.add_column("#", style="dim")
        step_table.add_column("Name", style="green")
        step_table.add_column("Agent", style="cyan")
        step_table.add_column("Action (truncated)")
        
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"step_{i}")
            agent = step.get("agent", "-")
            action = step.get("action", "")
            # Truncate action for display
            action_preview = action[:60].replace("\n", " ") + "..." if len(action) > 60 else action.replace("\n", " ")
            step_table.add_row(str(i), step_name, agent, action_preview)
        console.print(step_table)
    
    # Tools.py
    tools_path = recipe_path / "tools.py"
    if tools_path.exists():
        console.print("\n[bold]Custom Tools:[/bold] [green]✓ tools.py present[/green]")
    else:
        console.print("\n[bold]Custom Tools:[/bold] [dim]No tools.py[/dim]")
    
    # Full YAML if verbose
    if verbose:
        console.print("\n[bold]Full YAML:[/bold]")
        with open(yaml_path) as f:
            yaml_content = f.read()
        syntax = Syntax(yaml_content, "yaml", theme="monokai", line_numbers=True)
        console.print(syntax)
    
    # Path
    console.print(f"\n[dim]Path: {recipe_path}[/dim]")


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
    chunked: bool = typer.Option(False, "--chunked", help="Use chunked evaluation for large outputs (preserves all content)"),
    no_auto_chunk: bool = typer.Option(False, "--no-auto-chunk", help="Disable automatic chunking (auto-chunk is enabled by default)"),
    chunk_size: int = typer.Option(8000, "--chunk-size", help="Max characters per chunk (default: 8000)"),
    max_chunks: int = typer.Option(5, "--max-chunks", help="Max chunks per agent (default: 5)"),
    aggregation: str = typer.Option("weighted_average", "--aggregation", help="Score aggregation: weighted_average, average, min, max"),
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
    # auto_chunk is True by default unless --no-auto-chunk is specified
    auto_chunk = not no_auto_chunk
    chunked_indicator = " [chunked]" if chunked else (" [auto-chunk]" if auto_chunk else "")
    print(f"{mode_emoji.get(mode, '🔍')} Judging trace: {trace_id} (mode: {mode}){chunked_indicator}")
    
    try:
        reader = ContextTraceReader(trace_id)
        events = reader.get_all()
        
        if not events:
            print(f"❌ No events found for trace: {trace_id}")
            raise typer.Exit(1)
        
        print(f"  📊 Found {len(events)} events")
        if chunked:
            print(f"  📦 Chunked evaluation: {chunk_size} chars/chunk, max {max_chunks} chunks, {aggregation} aggregation")
        elif auto_chunk:
            print("  🔄 Auto-chunk: will chunk if content exceeds model context window")
        
        # Run judge with mode-specific evaluation
        judge = ContextEffectivenessJudge(
            mode=mode,
            chunked=chunked,
            auto_chunk=auto_chunk,
            chunk_size=chunk_size,
            max_chunks=max_chunks,
            aggregation_strategy=aggregation,
        )
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
    criteria: str = typer.Option(None, "--criteria", "-c", help="Custom evaluation criteria (for domain-agnostic optimization)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Optimize a recipe using AI judge feedback.
    
    Iteratively runs the recipe, judges output, and applies improvements.
    
    Supports custom criteria for domain-agnostic optimization (e.g., water flow, data pipelines).
    
    Examples:
        praisonai recipe optimize my-recipe
        praisonai recipe optimize my-recipe "improve error handling"
        praisonai recipe optimize my-recipe --iterations 5 --threshold 9.0
        praisonai recipe optimize my-recipe --input '{"query": "test"}'
        praisonai recipe optimize my-recipe --criteria "Water flow is optimal: no leaks, pressure within range"
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
        
        # Create custom judge if criteria provided
        custom_judge = None
        if criteria:
            try:
                from praisonaiagents.eval import Judge
                custom_judge = Judge(criteria=criteria)
                print(f"   Custom criteria: {criteria[:50]}{'...' if len(criteria) > 50 else ''}")
            except ImportError:
                print("   ⚠️ Custom criteria requires praisonaiagents. Using default judge.")
        
        optimizer = RecipeOptimizer(
            max_iterations=iterations,
            score_threshold=threshold,
            judge=custom_judge,
            criteria=criteria,
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
    
    DEPRECATED: Use `praisonai serve recipe` instead.
    
    Serves recipes as REST API endpoints.
    
    Examples:
        praisonai recipe serve
        praisonai recipe serve my-recipe --port 8080
        praisonai recipe serve --host 0.0.0.0 --port 8000
        praisonai recipe serve --config serve.yaml
        praisonai recipe serve --api-key my-secret-key
        praisonai recipe serve --workers 4
    """
    import sys
    
    # Print deprecation warning
    print("\n\033[93m⚠ DEPRECATION WARNING:\033[0m", file=sys.stderr)
    print("\033[93m'praisonai recipe serve' is deprecated and will be removed in a future version.\033[0m", file=sys.stderr)
    print("\033[93mPlease use 'praisonai serve recipe' instead.\033[0m\n", file=sys.stderr)
    
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
