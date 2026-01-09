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
"""

import os
import subprocess
from typing import Optional, List

import typer

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
