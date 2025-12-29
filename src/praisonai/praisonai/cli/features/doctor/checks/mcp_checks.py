"""
MCP (Model Context Protocol) checks for the Doctor CLI module.

Validates MCP server configurations and connectivity.
"""

import os
import shutil
from pathlib import Path

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


def _find_mcp_config() -> dict:
    """Find MCP configuration files."""
    locations = [
        Path.cwd() / ".praison" / "mcp.json",
        Path.cwd() / ".praison" / "mcp" / "config.json",
        Path.home() / ".praison" / "mcp.json",
        Path.home() / ".config" / "praison" / "mcp.json",
    ]
    
    for loc in locations:
        if loc.exists():
            try:
                import json
                with open(loc) as f:
                    return {"path": str(loc), "config": json.load(f)}
            except Exception:
                pass
    
    return {}


@register_check(
    id="mcp_config",
    title="MCP Configuration",
    description="Check MCP configuration file",
    category=CheckCategory.MCP,
    severity=CheckSeverity.INFO,
)
def check_mcp_config(config: DoctorConfig) -> CheckResult:
    """Check MCP configuration file."""
    mcp_config = _find_mcp_config()
    
    if mcp_config:
        servers = mcp_config.get("config", {}).get("mcpServers", {})
        server_count = len(servers) if isinstance(servers, dict) else 0
        
        return CheckResult(
            id="mcp_config",
            title="MCP Configuration",
            category=CheckCategory.MCP,
            status=CheckStatus.PASS,
            message=f"MCP config found with {server_count} server(s)",
            details=f"Path: {mcp_config['path']}",
            metadata={"path": mcp_config["path"], "server_count": server_count},
        )
    else:
        return CheckResult(
            id="mcp_config",
            title="MCP Configuration",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message="No MCP configuration found (optional)",
            details="Create .praison/mcp.json to configure MCP servers",
        )


@register_check(
    id="mcp_npx",
    title="npx for MCP",
    description="Check npx availability for MCP servers",
    category=CheckCategory.MCP,
    severity=CheckSeverity.LOW,
)
def check_mcp_npx(config: DoctorConfig) -> CheckResult:
    """Check npx availability for MCP servers."""
    npx_path = shutil.which("npx")
    
    if npx_path:
        return CheckResult(
            id="mcp_npx",
            title="npx for MCP",
            category=CheckCategory.MCP,
            status=CheckStatus.PASS,
            message=f"npx available at {npx_path}",
        )
    else:
        return CheckResult(
            id="mcp_npx",
            title="npx for MCP",
            category=CheckCategory.MCP,
            status=CheckStatus.WARN,
            message="npx not found (required for most MCP servers)",
            remediation="Install Node.js to use MCP servers",
        )


@register_check(
    id="mcp_python",
    title="Python MCP Support",
    description="Check Python MCP package availability",
    category=CheckCategory.MCP,
    severity=CheckSeverity.LOW,
)
def check_mcp_python(config: DoctorConfig) -> CheckResult:
    """Check Python MCP package availability."""
    try:
        import mcp
        version = getattr(mcp, "__version__", "unknown")
        return CheckResult(
            id="mcp_python",
            title="Python MCP Support",
            category=CheckCategory.MCP,
            status=CheckStatus.PASS,
            message=f"mcp package {version} available",
        )
    except ImportError:
        return CheckResult(
            id="mcp_python",
            title="Python MCP Support",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message="mcp package not installed (optional)",
            remediation="Install with: pip install mcp",
        )


@register_check(
    id="mcp_servers_valid",
    title="MCP Server Configs Valid",
    description="Validate MCP server configurations",
    category=CheckCategory.MCP,
    severity=CheckSeverity.MEDIUM,
    dependencies=["mcp_config"],
)
def check_mcp_servers_valid(config: DoctorConfig) -> CheckResult:
    """Validate MCP server configurations."""
    mcp_config = _find_mcp_config()
    
    if not mcp_config:
        return CheckResult(
            id="mcp_servers_valid",
            title="MCP Server Configs Valid",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message="No MCP configuration to validate",
        )
    
    servers = mcp_config.get("config", {}).get("mcpServers", {})
    if not servers:
        return CheckResult(
            id="mcp_servers_valid",
            title="MCP Server Configs Valid",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message="No MCP servers configured",
        )
    
    valid = []
    invalid = []
    
    for name, server_config in servers.items():
        if not isinstance(server_config, dict):
            invalid.append(f"{name}: invalid config format")
            continue
        
        command = server_config.get("command")
        if not command:
            invalid.append(f"{name}: missing 'command'")
            continue
        
        # Check if command executable exists
        cmd_parts = command.split() if isinstance(command, str) else [command]
        cmd_exe = cmd_parts[0] if cmd_parts else ""
        
        if cmd_exe and shutil.which(cmd_exe):
            valid.append(name)
        else:
            invalid.append(f"{name}: command '{cmd_exe}' not found")
    
    if invalid:
        return CheckResult(
            id="mcp_servers_valid",
            title="MCP Server Configs Valid",
            category=CheckCategory.MCP,
            status=CheckStatus.WARN,
            message=f"{len(valid)} valid, {len(invalid)} invalid server(s)",
            details="; ".join(invalid[:3]) + ("..." if len(invalid) > 3 else ""),
            metadata={"valid": valid, "invalid": invalid},
        )
    else:
        return CheckResult(
            id="mcp_servers_valid",
            title="MCP Server Configs Valid",
            category=CheckCategory.MCP,
            status=CheckStatus.PASS,
            message=f"All {len(valid)} MCP server config(s) valid",
            metadata={"valid": valid},
        )


@register_check(
    id="mcp_server_spawn",
    title="MCP Server Spawn Test",
    description="Test spawning MCP servers",
    category=CheckCategory.MCP,
    severity=CheckSeverity.LOW,
    requires_deep=True,
)
def check_mcp_server_spawn(config: DoctorConfig) -> CheckResult:
    """Test spawning MCP servers (deep mode only)."""
    mcp_config = _find_mcp_config()
    
    if not mcp_config:
        return CheckResult(
            id="mcp_server_spawn",
            title="MCP Server Spawn Test",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message="No MCP configuration to test",
        )
    
    servers = mcp_config.get("config", {}).get("mcpServers", {})
    if not servers:
        return CheckResult(
            id="mcp_server_spawn",
            title="MCP Server Spawn Test",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message="No MCP servers to test",
        )
    
    # Only test first server to avoid long delays
    test_server = config.name if config.name else list(servers.keys())[0]
    server_config = servers.get(test_server)
    
    if not server_config:
        return CheckResult(
            id="mcp_server_spawn",
            title="MCP Server Spawn Test",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message=f"Server '{test_server}' not found",
        )
    
    try:
        import subprocess
        
        command = server_config.get("command", "")
        args = server_config.get("args", [])
        
        if isinstance(command, str):
            cmd = command.split() + args
        else:
            cmd = [command] + args
        
        # Try to start the server with a short timeout
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **server_config.get("env", {})},
        )
        
        # Wait briefly to see if it starts
        import time
        time.sleep(1)
        
        if proc.poll() is None:
            # Process is still running - success
            proc.terminate()
            proc.wait(timeout=2)
            return CheckResult(
                id="mcp_server_spawn",
                title="MCP Server Spawn Test",
                category=CheckCategory.MCP,
                status=CheckStatus.PASS,
                message=f"Server '{test_server}' started successfully",
            )
        else:
            # Process exited
            stderr = proc.stderr.read().decode()[:200] if proc.stderr else ""
            return CheckResult(
                id="mcp_server_spawn",
                title="MCP Server Spawn Test",
                category=CheckCategory.MCP,
                status=CheckStatus.WARN,
                message=f"Server '{test_server}' exited immediately",
                details=stderr if stderr else "No error output",
            )
    
    except FileNotFoundError as e:
        return CheckResult(
            id="mcp_server_spawn",
            title="MCP Server Spawn Test",
            category=CheckCategory.MCP,
            status=CheckStatus.FAIL,
            message=f"Command not found for '{test_server}'",
            details=str(e),
            remediation="Install the required MCP server package",
        )
    except Exception as e:
        return CheckResult(
            id="mcp_server_spawn",
            title="MCP Server Spawn Test",
            category=CheckCategory.MCP,
            status=CheckStatus.WARN,
            message=f"Could not test server '{test_server}'",
            details=str(e)[:200],
        )


@register_check(
    id="mcp_praisonai_integration",
    title="PraisonAI MCP Integration",
    description="Check PraisonAI MCP integration",
    category=CheckCategory.MCP,
    severity=CheckSeverity.LOW,
)
def check_mcp_praisonai_integration(config: DoctorConfig) -> CheckResult:
    """Check PraisonAI MCP integration."""
    try:
        from praisonaiagents.mcp import MCP
        return CheckResult(
            id="mcp_praisonai_integration",
            title="PraisonAI MCP Integration",
            category=CheckCategory.MCP,
            status=CheckStatus.PASS,
            message="PraisonAI MCP integration available",
        )
    except ImportError as e:
        return CheckResult(
            id="mcp_praisonai_integration",
            title="PraisonAI MCP Integration",
            category=CheckCategory.MCP,
            status=CheckStatus.SKIP,
            message="MCP integration not available",
            details=str(e),
            remediation="Install with: pip install praisonaiagents[mcp]",
        )
