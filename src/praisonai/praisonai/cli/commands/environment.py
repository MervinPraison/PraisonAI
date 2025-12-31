"""
Environment command group for PraisonAI CLI.

Provides environment management and diagnostics:
- env view: Show environment variables
- env check: Validate API keys
- env doctor: Run diagnostics (alias for doctor command)
"""

import os
from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Environment and diagnostics")


# Known API key patterns
API_KEY_PATTERNS = {
    "OPENAI_API_KEY": {"prefix": "sk-", "min_length": 20},
    "ANTHROPIC_API_KEY": {"prefix": "sk-ant-", "min_length": 20},
    "GOOGLE_API_KEY": {"prefix": "AI", "min_length": 20},
    "GEMINI_API_KEY": {"prefix": "AI", "min_length": 20},
    "TAVILY_API_KEY": {"prefix": "tvly-", "min_length": 20},
    "GROQ_API_KEY": {"prefix": "gsk_", "min_length": 20},
}


def _redact_key(value: str, show_chars: int = 4) -> str:
    """Redact an API key for display."""
    if len(value) <= show_chars * 2:
        return "*" * len(value)
    return value[:show_chars] + "*" * (len(value) - show_chars * 2) + value[-show_chars:]


def _validate_key(name: str, value: str) -> tuple[bool, str]:
    """Validate an API key format."""
    if name not in API_KEY_PATTERNS:
        return True, "Unknown key type"
    
    pattern = API_KEY_PATTERNS[name]
    
    if len(value) < pattern["min_length"]:
        return False, f"Too short (expected >= {pattern['min_length']} chars)"
    
    if pattern.get("prefix") and not value.startswith(pattern["prefix"]):
        return False, f"Invalid prefix (expected {pattern['prefix']}...)"
    
    return True, "Valid format"


@app.command("view")
def env_view(
    show_values: bool = typer.Option(
        False,
        "--show-values",
        help="Show actual values (redacted by default)",
    ),
    filter_prefix: Optional[str] = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter by prefix (e.g., OPENAI, PRAISONAI)",
    ),
):
    """Show relevant environment variables."""
    output = get_output_controller()
    
    # Relevant prefixes
    prefixes = ["OPENAI", "ANTHROPIC", "GOOGLE", "GEMINI", "TAVILY", "GROQ", 
                "PRAISONAI", "MODEL", "LLM", "OLLAMA", "AZURE"]
    
    if filter_prefix:
        prefixes = [filter_prefix.upper()]
    
    env_vars = {}
    for key, value in os.environ.items():
        for prefix in prefixes:
            if key.upper().startswith(prefix):
                if show_values:
                    if "KEY" in key.upper() or "SECRET" in key.upper() or "TOKEN" in key.upper():
                        env_vars[key] = _redact_key(value)
                    else:
                        env_vars[key] = value
                else:
                    env_vars[key] = "***" if value else "(empty)"
                break
    
    if output.is_json_mode:
        output.print_json({"environment": env_vars})
        return
    
    if not env_vars:
        output.print_info("No relevant environment variables found")
        return
    
    headers = ["Variable", "Value"]
    rows = [[k, v] for k, v in sorted(env_vars.items())]
    output.print_table(headers, rows, title="Environment Variables")


@app.command("check")
def env_check():
    """Validate API keys and configuration."""
    output = get_output_controller()
    
    results = []
    all_valid = True
    
    for key_name, pattern in API_KEY_PATTERNS.items():
        value = os.environ.get(key_name)
        
        if value:
            valid, message = _validate_key(key_name, value)
            results.append({
                "key": key_name,
                "present": True,
                "valid": valid,
                "message": message,
            })
            if not valid:
                all_valid = False
        else:
            results.append({
                "key": key_name,
                "present": False,
                "valid": False,
                "message": "Not set",
            })
    
    if output.is_json_mode:
        output.print_json({"checks": results, "all_valid": all_valid})
        return
    
    headers = ["Key", "Status", "Message"]
    rows = []
    for r in results:
        if r["present"]:
            status = "✅" if r["valid"] else "⚠️"
        else:
            status = "❌"
        rows.append([r["key"], status, r["message"]])
    
    output.print_table(headers, rows, title="API Key Validation")
    
    if not all_valid:
        output.print_warning("Some API keys are missing or invalid")
        raise typer.Exit(3)  # Exit code 3 = missing config/env


@app.command("doctor")
def env_doctor(
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Run deep checks (network, DB connections)",
    ),
):
    """Run environment diagnostics (alias for 'praisonai doctor env')."""
    output = get_output_controller()
    
    # Delegate to doctor command
    try:
        from ..features.doctor.handler import DoctorHandler
        handler = DoctorHandler()
        
        # Run env checks
        if output.is_json_mode:
            # Run and get JSON output
            result = handler.handle(["env", "--json"] if not deep else ["env", "--json", "--deep"])
        else:
            result = handler.handle(["env"] if not deep else ["env", "--deep"])
        
        raise typer.Exit(result)
    except ImportError:
        # Fallback to basic env check
        env_check()
