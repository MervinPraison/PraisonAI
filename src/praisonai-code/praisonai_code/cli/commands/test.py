"""
PraisonAI Test CLI Command

Provides a unified interface for running tests with tier and provider options.

Usage:
    praisonai test                      # Run main tier (default)
    praisonai test --tier smoke         # Run smoke tests only
    praisonai test --tier extended      # Run extended tests
    praisonai test --provider openai    # Run OpenAI provider tests
    praisonai test --live               # Enable live API tests
    praisonai test --parallel auto      # Run with parallelization
    
    # Interactive mode tests
    praisonai test interactive --csv tests.csv
    praisonai test interactive --suite smoke
    praisonai test interactive --list
    praisonai test interactive --generate-template
"""

import os
import subprocess
from typing import Optional, List

import typer

# Source the default judge/agent model from the single source of truth so the
# test harness never re-declares the terminal fallback literal.
from praisonai_code.llm.env import DEFAULT_FALLBACK_MODEL as _DEFAULT_TEST_MODEL

app = typer.Typer(help="Run PraisonAI test suite with tier and provider options")


def _get_pytest_args(
    tier: str,
    provider: Optional[str],
    live: bool,
    parallel: Optional[str],
    verbose: bool,
    coverage: bool,
) -> List[str]:
    """Build pytest arguments based on options."""
    args = ["python", "-m", "pytest"]
    
    # Base test paths
    if tier == "smoke":
        args.append("tests/unit/")
    elif tier == "main":
        args.extend(["tests/unit/", "tests/integration/"])
    elif tier in ("extended", "nightly"):
        args.append("tests/")
    else:
        args.append("tests/")
    
    # Always ignore fixtures directory
    args.extend(["--ignore=tests/fixtures"])
    
    # Tier-specific markers
    if tier == "smoke":
        args.extend(["-m", "not slow and not network"])
    elif tier == "main":
        # Exclude non-OpenAI providers by default
        args.extend([
            "-m", 
            "not provider_anthropic and not provider_google and not provider_ollama and not provider_grok_xai and not provider_groq and not provider_cohere"
        ])
    
    # Provider-specific filter
    if provider:
        if provider == "all":
            pass  # No filter
        else:
            provider_marker = f"provider_{provider}"
            args.extend(["-m", provider_marker])
    
    # Verbosity
    if verbose:
        args.append("-v")
    else:
        args.append("-q")
    
    args.append("--tb=short")
    
    # Timeout
    if tier == "smoke":
        args.extend(["--timeout=30"])
    elif tier == "main":
        args.extend(["--timeout=60"])
    else:
        args.extend(["--timeout=120"])
    
    # Coverage
    if coverage:
        args.extend([
            "--cov=praisonai",
            "--cov-report=term-missing",
            "--cov-report=xml"
        ])
    
    # Parallelization
    if parallel:
        if parallel == "auto":
            args.extend(["-n", "auto"])
        else:
            args.extend(["-n", parallel])
    
    return args


def _set_environment(tier: str, provider: Optional[str], live: bool):
    """Set environment variables for test run."""
    os.environ["PRAISONAI_TEST_TIER"] = tier
    
    if live:
        os.environ["PRAISONAI_ALLOW_NETWORK"] = "1"
        os.environ["PRAISONAI_LIVE_TESTS"] = "1"
    else:
        os.environ["PRAISONAI_ALLOW_NETWORK"] = "0"
        os.environ["PRAISONAI_LIVE_TESTS"] = "0"
    
    if provider:
        os.environ["PRAISONAI_TEST_PROVIDERS"] = provider


def _print_skip_summary(tier: str, provider: Optional[str], live: bool):
    """Print summary of what will be skipped."""
    typer.echo("\n📋 Test Configuration:")
    typer.echo(f"  Tier: {tier}")
    typer.echo(f"  Provider: {provider or 'all (gated)'}")
    typer.echo(f"  Live tests: {'enabled' if live else 'disabled'}")
    typer.echo("")
    
    if not live:
        typer.echo("⚠️  Network tests will be skipped (use --live to enable)")
    
    if tier == "smoke":
        typer.echo("ℹ️  Running unit tests only (no integration/e2e)")
    elif tier == "main":
        typer.echo("ℹ️  Skipping non-OpenAI provider tests")
    
    typer.echo("")


@app.command()
def run(
    tier: str = typer.Option(
        "main",
        "--tier", "-t",
        help="Test tier: smoke (fast), main (default), extended, nightly"
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider", "-p",
        help="Run tests for specific provider: openai, anthropic, google, ollama, grok_xai, groq, cohere, all"
    ),
    live: bool = typer.Option(
        False,
        "--live", "-l",
        help="Enable live API tests (requires API keys)"
    ),
    allow_network: bool = typer.Option(
        False,
        "--allow-network",
        help="Allow network access in tests"
    ),
    parallel: Optional[str] = typer.Option(
        None,
        "--parallel", "-n",
        help="Run tests in parallel: auto or number of workers"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Verbose output"
    ),
    coverage: bool = typer.Option(
        False,
        "--coverage", "-c",
        help="Generate coverage report"
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast", "-x",
        help="Stop on first failure"
    ),
):
    """
    Run the PraisonAI test suite.
    
    Examples:
        praisonai test                      # Run main tier
        praisonai test --tier smoke         # Fast smoke tests
        praisonai test --tier extended      # Extended tests
        praisonai test --provider openai --live  # OpenAI live tests
        praisonai test --parallel auto      # Parallel execution
    """
    # Validate tier
    valid_tiers = ["smoke", "main", "extended", "nightly"]
    if tier not in valid_tiers:
        typer.echo(f"❌ Invalid tier: {tier}. Must be one of: {', '.join(valid_tiers)}")
        raise typer.Exit(1)
    
    # Validate provider
    valid_providers = ["openai", "anthropic", "google", "ollama", "grok_xai", "groq", "cohere", "all"]
    if provider and provider not in valid_providers:
        typer.echo(f"❌ Invalid provider: {provider}. Must be one of: {', '.join(valid_providers)}")
        raise typer.Exit(1)
    
    # Set environment
    _set_environment(tier, provider, live or allow_network)
    
    # Print summary
    _print_skip_summary(tier, provider, live or allow_network)
    
    # Build pytest args
    args = _get_pytest_args(tier, provider, live or allow_network, parallel, verbose, coverage)
    
    if fail_fast:
        args.append("-x")
    
    # Print command
    typer.echo(f"🧪 Running: {' '.join(args)}")
    typer.echo("")
    
    # Find the tests directory
    # Try current directory first, then src/praisonai
    test_dirs = [
        os.getcwd(),
        os.path.join(os.getcwd(), "src", "praisonai"),
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    ]
    
    cwd = None
    for test_dir in test_dirs:
        if os.path.isdir(os.path.join(test_dir, "tests")):
            cwd = test_dir
            break
    
    if not cwd:
        typer.echo("❌ Could not find tests directory")
        raise typer.Exit(1)
    
    # Run pytest
    try:
        result = subprocess.run(args, cwd=cwd)
        raise typer.Exit(result.returncode)
    except KeyboardInterrupt:
        typer.echo("\n❌ Tests interrupted")
        raise typer.Exit(1)


# Built-in interactive test suites
BUILTIN_SUITES = {
    "smoke": "smoke.csv",
    "tools": "tools.csv",
    "refactor": "refactor.csv",
    "multi_agent": "multi_agent.csv",
}

# Special suites that don't use CSV
SPECIAL_SUITES = {
    "advanced": "Advanced Agent-Centric (5 complex autonomous scenarios)",
}


def _iter_fixtures_dirs():
    """Yield candidate fixtures/interactive directories.

    Resolution is tried in order so that both editable/dev checkouts and
    installed wheels (where fixtures ship as package data) resolve correctly:
      1. Packaged data inside praisonai_code (importlib.resources).
      2. src/praisonai/tests/fixtures/interactive relative to this module.
      3. tests/fixtures/interactive under the current working directory.
    """
    from pathlib import Path

    # 1. Packaged data shipped inside the praisonai_code wheel.
    try:
        from importlib.resources import files as _resource_files

        packaged = _resource_files("praisonai_code") / "data" / "fixtures" / "interactive"
        yield Path(str(packaged))
    except Exception:
        pass

    # 2. Development tree layout: .../src/praisonai/tests/fixtures/interactive.
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if parent.name == "src":
            yield parent / "praisonai" / "tests" / "fixtures" / "interactive"
            break

    # 3. Current working directory (running from a repo checkout).
    cwd = Path.cwd()
    yield cwd / "tests" / "fixtures" / "interactive"
    yield cwd / "src" / "praisonai" / "tests" / "fixtures" / "interactive"


def _get_builtin_suite_path(suite: str):
    """Get path to built-in test suite."""
    if suite not in BUILTIN_SUITES:
        return None

    filename = BUILTIN_SUITES[suite]
    for fixtures_dir in _iter_fixtures_dirs():
        suite_path = fixtures_dir / filename
        if suite_path.exists():
            return suite_path

    return None


@app.command("interactive")
def interactive(
    csv: Optional[str] = typer.Option(
        None, "--csv", "-c",
        help="Path to CSV file with test cases"
    ),
    suite: Optional[str] = typer.Option(
        None, "--suite", "-s",
        help="Built-in test suite: smoke, tools, refactor, multi_agent"
    ),
    model: str = typer.Option(
        _DEFAULT_TEST_MODEL, "--model", "-m",
        help="LLM model for agent"
    ),
    judge_model: str = typer.Option(
        _DEFAULT_TEST_MODEL, "--judge-model",
        help="LLM model for judge"
    ),
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace directory (default: temp)"
    ),
    artifacts_dir: Optional[str] = typer.Option(
        None, "--artifacts-dir",
        help="Directory for test artifacts"
    ),
    fail_fast: bool = typer.Option(
        False, "--fail-fast", "-x",
        help="Stop on first failure"
    ),
    keep_artifacts: bool = typer.Option(
        False, "--keep-artifacts",
        help="Keep test artifacts after run"
    ),
    no_judge: bool = typer.Option(
        False, "--no-judge",
        help="Skip judge evaluation even if rubric present"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Verbose output"
    ),
    list_suites: bool = typer.Option(
        False, "--list",
        help="List available built-in suites"
    ),
    generate_template: bool = typer.Option(
        False, "--generate-template",
        help="Generate CSV template in current directory"
    ),
):
    """
    Run interactive mode tests from CSV.
    
    Tests are executed through the headless interactive core, using the same
    pipeline as the interactive TUI (InteractiveRuntime, get_interactive_tools,
    ActionOrchestrator).
    
    Examples:
        praisonai test interactive --csv tests.csv
        praisonai test interactive --suite smoke
        praisonai test interactive --suite tools --keep-artifacts
        praisonai test interactive --list
        praisonai test interactive --generate-template
    """
    from pathlib import Path
    
    # List suites
    if list_suites:
        typer.echo("📋 Available built-in test suites:")
        typer.echo("")
        typer.echo("CSV-based suites:")
        for name, filename in BUILTIN_SUITES.items():
            suite_path = _get_builtin_suite_path(name)
            status = "✅" if suite_path else "❌ (not found)"
            typer.echo(f"  {name:15} {filename:20} {status}")
        typer.echo("")
        typer.echo("Special suites:")
        for name, description in SPECIAL_SUITES.items():
            typer.echo(f"  {name:15} {description}")
        typer.echo("")
        typer.echo("Usage: praisonai test interactive --suite <name>")
        typer.echo("       PRAISONAI_LIVE_INTERACTIVE=1 praisonai test interactive --suite advanced")
        return
    
    # Generate template
    if generate_template:
        # Lazy import
        from praisonai_code.cli.features.csv_test_runner import generate_csv_template
        
        output_path = Path.cwd() / "interactive_tests_template.csv"
        generate_csv_template(output_path)
        typer.echo(f"✅ Generated CSV template: {output_path}")
        return
    
    # Validate inputs
    if not csv and not suite:
        typer.echo("❌ Either --csv or --suite is required")
        typer.echo("")
        typer.echo("Examples:")
        typer.echo("  praisonai test interactive --csv tests.csv")
        typer.echo("  praisonai test interactive --suite smoke")
        typer.echo("  praisonai test interactive --suite advanced")
        typer.echo("  praisonai test interactive --list")
        raise typer.Exit(1)
    
    # Handle special suites
    if suite and suite in SPECIAL_SUITES:
        if suite == "advanced":
            _run_advanced_suite(
                model=model,
                artifacts_dir=Path(artifacts_dir) if artifacts_dir else None,
                keep_artifacts=keep_artifacts,
                verbose=verbose,
            )
            return
    
    # Get CSV path
    if csv:
        csv_path = Path(csv)
        if not csv_path.exists():
            typer.echo(f"❌ CSV file not found: {csv}")
            raise typer.Exit(1)
    else:
        csv_path = _get_builtin_suite_path(suite)
        if not csv_path:
            typer.echo(f"❌ Built-in suite not found: {suite}")
            typer.echo("Use --list to see available suites")
            raise typer.Exit(1)
    
    # Lazy import runner
    from praisonai_code.cli.features.csv_test_runner import CSVTestRunner
    
    typer.echo(f"🧪 Running interactive tests from: {csv_path}")
    typer.echo(f"   Model: {model} | Judge: {judge_model}")
    typer.echo("")
    
    # Create runner
    runner = CSVTestRunner(
        csv_path=csv_path,
        model=model,
        judge_model=judge_model,
        workspace=Path(workspace) if workspace else None,
        artifacts_dir=Path(artifacts_dir) if artifacts_dir else None,
        fail_fast=fail_fast,
        keep_artifacts=keep_artifacts,
        no_judge=no_judge,
        verbose=verbose,
    )
    
    # Run tests
    summary = runner.run()
    
    # Print summary
    typer.echo("")
    summary.print_summary()
    
    # Save summary if keeping artifacts
    if keep_artifacts and runner.artifacts_dir:
        import json
        summary_path = runner.artifacts_dir / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w") as f:
            json.dump(summary.to_dict(), f, indent=2, default=str)
        typer.echo(f"\n📁 Artifacts saved to: {runner.artifacts_dir}")
    
    # Exit code based on results
    if summary.failed > 0 or summary.errors > 0:
        raise typer.Exit(1)


def _run_advanced_suite(
    model: str = _DEFAULT_TEST_MODEL,
    artifacts_dir = None,
    keep_artifacts: bool = True,
    verbose: bool = True,
):
    """Run the Advanced Agent-Centric test suite."""
    from pathlib import Path
    
    # Check prerequisites
    typer.echo("🔍 Checking Advanced suite prerequisites...")
    
    # Check if live interactive is enabled
    live_enabled = os.environ.get("PRAISONAI_LIVE_INTERACTIVE", "0") == "1"
    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
    
    if not live_enabled:
        typer.echo("\n⚠️  Cannot run Advanced tests: PRAISONAI_LIVE_INTERACTIVE=1 not set")
        typer.echo("")
        typer.echo("Prerequisites:")
        typer.echo("  1. Set PRAISONAI_LIVE_INTERACTIVE=1")
        typer.echo("  2. Set OPENAI_API_KEY")
        typer.echo("")
        typer.echo("Example:")
        typer.echo("  PRAISONAI_LIVE_INTERACTIVE=1 praisonai test interactive --suite advanced")
        raise typer.Exit(1)
    
    if not has_api_key:
        typer.echo("\n⚠️  Cannot run Advanced tests: OPENAI_API_KEY not set")
        raise typer.Exit(1)
    
    typer.echo("✅ Live interactive mode enabled")
    typer.echo("✅ API key configured")
    typer.echo("")
    
    # Lazy import runner and scenarios
    from tests.live.interactive.runner import LiveInteractiveRunner
    from tests.live.interactive.advanced.scenarios import ALL_ADVANCED_SCENARIOS
    
    # Create runner
    runner = LiveInteractiveRunner(
        model=model,
        artifacts_dir=Path(artifacts_dir) if artifacts_dir else None,
        keep_artifacts=keep_artifacts,
        verbose=verbose,
    )
    
    # Run tests
    summary = runner.run_all(ALL_ADVANCED_SCENARIOS)
    
    # Print summary
    typer.echo("")
    summary.print_summary()
    
    # Show artifacts location
    if keep_artifacts:
        typer.echo(f"\n📁 Artifacts saved to: {runner.artifacts_dir}")
    
    # Exit code
    if summary.failed > 0:
        raise typer.Exit(1)


@app.command()
def info():
    """Show test configuration and available options."""
    typer.echo("📊 PraisonAI Test Suite Information")
    typer.echo("=" * 50)
    typer.echo("")
    
    typer.echo("🎯 Test Tiers:")
    typer.echo("  smoke    - Fast unit tests, no network (≤2 min)")
    typer.echo("  main     - Unit + integration, OpenAI only (≤5 min)")
    typer.echo("  extended - All providers, gated by keys (≤15 min)")
    typer.echo("  nightly  - Full matrix + stress tests (≤30 min)")
    typer.echo("")
    
    typer.echo("🔌 Providers:")
    providers = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "ollama": "(local service)",
        "grok_xai": "XAI_API_KEY",
        "groq": "GROQ_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    for provider, env_var in providers.items():
        status = "✅" if os.environ.get(env_var.replace("(local service)", "")) else "❌"
        if env_var == "(local service)":
            status = "🔧"
        typer.echo(f"  {provider:12} {env_var:25} {status}")
    typer.echo("")
    
    typer.echo("🌐 Environment Variables:")
    env_vars = {
        "PRAISONAI_TEST_TIER": os.environ.get("PRAISONAI_TEST_TIER", "main"),
        "PRAISONAI_ALLOW_NETWORK": os.environ.get("PRAISONAI_ALLOW_NETWORK", "0"),
        "PRAISONAI_LIVE_TESTS": os.environ.get("PRAISONAI_LIVE_TESTS", "0"),
        "PRAISONAI_TEST_PROVIDERS": os.environ.get("PRAISONAI_TEST_PROVIDERS", "openai"),
        "PRAISONAI_LOCAL_SERVICES": os.environ.get("PRAISONAI_LOCAL_SERVICES", "0"),
    }
    for var, value in env_vars.items():
        typer.echo(f"  {var}: {value}")


if __name__ == "__main__":
    app()
