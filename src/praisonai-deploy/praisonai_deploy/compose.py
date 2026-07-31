"""
Docker Compose stack orchestration for production-like agent deployments.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ._infra import DEFAULT_STACK_NAME, resolve_compose_stack_dir
from .api import generate_api_server_code
from .docker import collect_runtime_env_vars
from .models import APIConfig, DeployResult
from .schema import validate_agents_yaml

COMPOSE_PROJECT_DIR = ".praisonai-compose"


def resolve_stack_dir(
    stack_dir: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """Resolve the compose stack template directory."""
    return resolve_compose_stack_dir(stack_dir=stack_dir, cwd=cwd)


def prepare_compose_project(
    agents_file: str,
    project_dir: Optional[Path] = None,
    api_config: Optional[APIConfig] = None,
    stack_dir: Optional[str] = None,
) -> Path:
    """
    Prepare a project directory for docker compose: validate YAML, write api_server.py.
    """
    agents_path = Path(agents_file).expanduser().resolve()
    if not agents_path.is_file():
        raise FileNotFoundError(f"agents file not found: {agents_path}")

    yaml_config = validate_agents_yaml(str(agents_path))
    config = api_config or (yaml_config.api if yaml_config and yaml_config.api else APIConfig())
    config = config.model_copy(update={"host": "0.0.0.0"})

    workdir = (project_dir or Path.cwd()).resolve()
    compose_dir = workdir / COMPOSE_PROJECT_DIR
    compose_dir.mkdir(parents=True, exist_ok=True)

    agents_dest = compose_dir / agents_path.name
    if agents_dest.resolve() != agents_path.resolve():
        shutil.copy2(agents_path, agents_dest)

    server_code = generate_api_server_code(str(agents_dest), config)
    server_file = compose_dir / "api_server.py"
    server_file.write_text(server_code, encoding="utf-8")

    env_example = resolve_stack_dir(stack_dir=stack_dir) / ".env.example"
    if not env_example.is_file():
        env_example = None

    env_file = compose_dir / ".env"
    if not env_file.exists() and env_example is not None:
        shutil.copy2(env_example, env_file)

    return compose_dir


def compose_up(
    agents_file: str = "agents.yaml",
    stack_dir: Optional[str] = None,
    detach: bool = True,
    api_config: Optional[APIConfig] = None,
) -> DeployResult:
    """Start the agents compose stack."""
    try:
        stack_path = resolve_stack_dir(stack_dir)
        project_dir = prepare_compose_project(agents_file, api_config=api_config, stack_dir=stack_dir)
        compose_file = stack_path / "docker-compose.yml"

        env = os.environ.copy()
        env.update(collect_runtime_env_vars())
        env["AGENTS_FILE"] = str((project_dir / Path(agents_file).name).resolve())

        cmd = [
            "docker", "compose",
            "-f", str(compose_file),
            "--project-directory", str(project_dir),
            "up",
        ]
        if detach:
            cmd.append("-d")

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            return DeployResult(
                success=False,
                message="docker compose up failed",
                error=(result.stderr or result.stdout or "").strip(),
            )

        port = os.environ.get("API_PORT", "8005")
        url = f"http://127.0.0.1:{port}"
        return DeployResult(
            success=True,
            message="Compose stack started",
            url=url,
            metadata={
                "stack_dir": str(stack_path),
                "project_dir": str(project_dir),
                "compose_file": str(compose_file),
            },
        )
    except FileNotFoundError as e:
        return DeployResult(success=False, message=str(e), error=str(e))
    except Exception as e:
        return DeployResult(success=False, message="Compose up failed", error=str(e))


def compose_down(
    agents_file: str = "agents.yaml",
    stack_dir: Optional[str] = None,
    volumes: bool = False,
) -> DeployResult:
    """Stop the agents compose stack."""
    try:
        stack_path = resolve_stack_dir(stack_dir)
        project_dir = Path.cwd().resolve() / COMPOSE_PROJECT_DIR
        compose_file = stack_path / "docker-compose.yml"

        cmd = [
            "docker", "compose",
            "-f", str(compose_file),
            "--project-directory", str(project_dir),
            "down",
        ]
        if volumes:
            cmd.append("-v")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return DeployResult(
                success=False,
                message="docker compose down failed",
                error=(result.stderr or result.stdout or "").strip(),
            )

        return DeployResult(
            success=True,
            message="Compose stack stopped",
            metadata={"project_dir": str(project_dir)},
        )
    except FileNotFoundError as e:
        return DeployResult(success=False, message=str(e), error=str(e))
    except Exception as e:
        return DeployResult(success=False, message="Compose down failed", error=str(e))
