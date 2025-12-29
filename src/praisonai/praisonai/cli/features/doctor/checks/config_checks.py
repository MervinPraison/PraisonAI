"""
Configuration checks for the Doctor CLI module.

Validates YAML configuration files like agents.yaml and workflow.yaml.
"""

import os
from pathlib import Path

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


def _find_config_file(config: DoctorConfig, default_names: list) -> str:
    """Find a configuration file."""
    if config.config_file:
        return config.config_file
    
    cwd = Path.cwd()
    for name in default_names:
        path = cwd / name
        if path.exists():
            return str(path)
    
    return ""


def _validate_yaml_syntax(file_path: str) -> tuple:
    """Validate YAML syntax and return (valid, data, error)."""
    try:
        import yaml
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        return True, data, None
    except ImportError:
        return False, None, "PyYAML not installed"
    except yaml.YAMLError as e:
        return False, None, f"YAML syntax error: {e}"
    except Exception as e:
        return False, None, str(e)


@register_check(
    id="agents_yaml_exists",
    title="agents.yaml Exists",
    description="Check if agents.yaml configuration file exists",
    category=CheckCategory.CONFIG,
    severity=CheckSeverity.MEDIUM,
)
def check_agents_yaml_exists(config: DoctorConfig) -> CheckResult:
    """Check if agents.yaml exists."""
    file_path = _find_config_file(config, ["agents.yaml", "agents.yml"])
    
    if file_path and os.path.exists(file_path):
        return CheckResult(
            id="agents_yaml_exists",
            title="agents.yaml Exists",
            category=CheckCategory.CONFIG,
            status=CheckStatus.PASS,
            message=f"Found: {file_path}",
            metadata={"path": file_path},
        )
    else:
        return CheckResult(
            id="agents_yaml_exists",
            title="agents.yaml Exists",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="No agents.yaml found in current directory (optional)",
            details="agents.yaml is only required when running YAML-based workflows",
        )


@register_check(
    id="agents_yaml_syntax",
    title="agents.yaml Syntax",
    description="Validate agents.yaml YAML syntax",
    category=CheckCategory.CONFIG,
    severity=CheckSeverity.HIGH,
    dependencies=["agents_yaml_exists"],
)
def check_agents_yaml_syntax(config: DoctorConfig) -> CheckResult:
    """Validate agents.yaml YAML syntax."""
    file_path = _find_config_file(config, ["agents.yaml", "agents.yml"])
    
    if not file_path or not os.path.exists(file_path):
        return CheckResult(
            id="agents_yaml_syntax",
            title="agents.yaml Syntax",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="No agents.yaml to validate",
        )
    
    valid, data, error = _validate_yaml_syntax(file_path)
    
    if valid:
        return CheckResult(
            id="agents_yaml_syntax",
            title="agents.yaml Syntax",
            category=CheckCategory.CONFIG,
            status=CheckStatus.PASS,
            message="YAML syntax is valid",
            metadata={"path": file_path},
        )
    else:
        return CheckResult(
            id="agents_yaml_syntax",
            title="agents.yaml Syntax",
            category=CheckCategory.CONFIG,
            status=CheckStatus.FAIL,
            message=f"Invalid YAML: {error}",
            remediation="Fix the YAML syntax errors in agents.yaml",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="agents_yaml_schema",
    title="agents.yaml Schema",
    description="Validate agents.yaml schema structure",
    category=CheckCategory.CONFIG,
    severity=CheckSeverity.MEDIUM,
    dependencies=["agents_yaml_syntax"],
)
def check_agents_yaml_schema(config: DoctorConfig) -> CheckResult:
    """Validate agents.yaml schema structure."""
    file_path = _find_config_file(config, ["agents.yaml", "agents.yml"])
    
    if not file_path or not os.path.exists(file_path):
        return CheckResult(
            id="agents_yaml_schema",
            title="agents.yaml Schema",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="No agents.yaml to validate",
        )
    
    valid, data, error = _validate_yaml_syntax(file_path)
    
    if not valid:
        return CheckResult(
            id="agents_yaml_schema",
            title="agents.yaml Schema",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="Skipped due to syntax errors",
        )
    
    if not isinstance(data, dict):
        return CheckResult(
            id="agents_yaml_schema",
            title="agents.yaml Schema",
            category=CheckCategory.CONFIG,
            status=CheckStatus.FAIL,
            message="agents.yaml must be a YAML mapping (dictionary)",
            remediation="Ensure agents.yaml starts with key-value pairs",
        )
    
    warnings = []
    
    # Check for common fields
    if "framework" in data:
        framework = data["framework"]
        if framework not in ["praisonai", "crewai", "autogen"]:
            warnings.append(f"Unknown framework: {framework}")
    
    # Check for agents section
    agents = data.get("agents") or data.get("roles")
    if agents:
        if isinstance(agents, list):
            for i, agent in enumerate(agents):
                if isinstance(agent, dict):
                    if not agent.get("name") and not agent.get("role"):
                        warnings.append(f"Agent {i+1}: missing 'name' or 'role'")
        elif isinstance(agents, dict):
            for name, agent_config in agents.items():
                if isinstance(agent_config, dict):
                    if not agent_config.get("role") and not agent_config.get("goal"):
                        warnings.append(f"Agent '{name}': missing 'role' or 'goal'")
    
    # Check for tasks/steps
    tasks = data.get("tasks") or data.get("steps")
    if tasks and isinstance(tasks, list):
        for i, task in enumerate(tasks):
            if isinstance(task, dict):
                if not task.get("description") and not task.get("action"):
                    warnings.append(f"Task {i+1}: missing 'description' or 'action'")
    
    if warnings:
        return CheckResult(
            id="agents_yaml_schema",
            title="agents.yaml Schema",
            category=CheckCategory.CONFIG,
            status=CheckStatus.WARN,
            message=f"Schema valid with {len(warnings)} warning(s)",
            details="; ".join(warnings[:3]) + ("..." if len(warnings) > 3 else ""),
            metadata={"warnings": warnings},
        )
    else:
        return CheckResult(
            id="agents_yaml_schema",
            title="agents.yaml Schema",
            category=CheckCategory.CONFIG,
            status=CheckStatus.PASS,
            message="Schema structure is valid",
        )


@register_check(
    id="workflow_yaml_exists",
    title="workflow.yaml Exists",
    description="Check if workflow.yaml configuration file exists",
    category=CheckCategory.CONFIG,
    severity=CheckSeverity.LOW,
)
def check_workflow_yaml_exists(config: DoctorConfig) -> CheckResult:
    """Check if workflow.yaml exists."""
    file_path = _find_config_file(config, ["workflow.yaml", "workflow.yml"])
    
    if file_path and os.path.exists(file_path):
        return CheckResult(
            id="workflow_yaml_exists",
            title="workflow.yaml Exists",
            category=CheckCategory.CONFIG,
            status=CheckStatus.PASS,
            message=f"Found: {file_path}",
            metadata={"path": file_path},
        )
    else:
        return CheckResult(
            id="workflow_yaml_exists",
            title="workflow.yaml Exists",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="No workflow.yaml found (optional)",
        )


@register_check(
    id="workflow_yaml_syntax",
    title="workflow.yaml Syntax",
    description="Validate workflow.yaml YAML syntax",
    category=CheckCategory.CONFIG,
    severity=CheckSeverity.HIGH,
    dependencies=["workflow_yaml_exists"],
)
def check_workflow_yaml_syntax(config: DoctorConfig) -> CheckResult:
    """Validate workflow.yaml YAML syntax."""
    file_path = _find_config_file(config, ["workflow.yaml", "workflow.yml"])
    
    if not file_path or not os.path.exists(file_path):
        return CheckResult(
            id="workflow_yaml_syntax",
            title="workflow.yaml Syntax",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="No workflow.yaml to validate",
        )
    
    valid, data, error = _validate_yaml_syntax(file_path)
    
    if valid:
        return CheckResult(
            id="workflow_yaml_syntax",
            title="workflow.yaml Syntax",
            category=CheckCategory.CONFIG,
            status=CheckStatus.PASS,
            message="YAML syntax is valid",
        )
    else:
        return CheckResult(
            id="workflow_yaml_syntax",
            title="workflow.yaml Syntax",
            category=CheckCategory.CONFIG,
            status=CheckStatus.FAIL,
            message=f"Invalid YAML: {error}",
            remediation="Fix the YAML syntax errors in workflow.yaml",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="praison_config_dir",
    title=".praison Config Directory",
    description="Check .praison configuration directory",
    category=CheckCategory.CONFIG,
    severity=CheckSeverity.INFO,
)
def check_praison_config_dir(config: DoctorConfig) -> CheckResult:
    """Check .praison configuration directory."""
    home_dir = Path.home()
    cwd = Path.cwd()
    
    locations = [
        cwd / ".praison",
        home_dir / ".praison",
        home_dir / ".config" / "praison",
    ]
    
    found = []
    for loc in locations:
        if loc.exists():
            found.append(str(loc))
    
    if found:
        return CheckResult(
            id="praison_config_dir",
            title=".praison Config Directory",
            category=CheckCategory.CONFIG,
            status=CheckStatus.PASS,
            message=f"Found {len(found)} config location(s)",
            details=", ".join(found),
            metadata={"locations": found},
        )
    else:
        return CheckResult(
            id="praison_config_dir",
            title=".praison Config Directory",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="No .praison config directory found (will be created on first use)",
        )


@register_check(
    id="env_file",
    title=".env File",
    description="Check for .env file",
    category=CheckCategory.CONFIG,
    severity=CheckSeverity.INFO,
)
def check_env_file(config: DoctorConfig) -> CheckResult:
    """Check for .env file."""
    cwd = Path.cwd()
    env_files = [".env", ".env.local", ".env.development"]
    
    found = []
    for name in env_files:
        path = cwd / name
        if path.exists():
            found.append(name)
    
    if found:
        return CheckResult(
            id="env_file",
            title=".env File",
            category=CheckCategory.CONFIG,
            status=CheckStatus.PASS,
            message=f"Found: {', '.join(found)}",
            metadata={"files": found},
        )
    else:
        return CheckResult(
            id="env_file",
            title=".env File",
            category=CheckCategory.CONFIG,
            status=CheckStatus.SKIP,
            message="No .env file found (environment variables can be set directly)",
        )
