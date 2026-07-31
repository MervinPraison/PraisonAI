"""
Docker Compose stack orchestration for production-like agent deployments.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ._infra import resolve_compose_stack_dir
from .api import generate_api_server_code
from .docker import collect_runtime_env_vars
from .models import APIConfig, DeployResult
from .schema import validate_agents_yaml

COMPOSE_PROJECT_DIR = ".praisonai-compose"
DEFAULT_API_PORT = "8005"
# Generous timeout to accommodate first-run image pulls while still preventing
# an unresponsive Docker daemon from hanging the CLI indefinitely.
COMPOSE_TIMEOUT_SECONDS = 600


def _resolve_api_port(env: dict, project_dir: Optional[Path] = None) -> str:
    """Resolve the effective host API port used by the compose stack.

    Precedence: the runtime ``env`` passed to docker compose, then the project
    ``.env``, then ``DEFAULT_API_PORT`` — so the reported URL matches the port
    the stack actually publishes.
    """
    value = env.get("API_PORT")
    if value:
        return str(value)
    if project_dir is not None:
        env_file = Path(project_dir) / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("API_PORT="):
                    candidate = stripped.split("=", 1)[1].split("#", 1)[0].strip().strip('"').strip("'")
                    if candidate:
                        return candidate
    return DEFAULT_API_PORT


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

    _ensure_postgres_password(env_file)
    _restrict_env_permissions(env_file)

    return compose_dir


def _restrict_env_permissions(env_file: Path) -> None:
    """Restrict a secret-bearing .env to owner read/write (0600) on POSIX."""
    if os.name != "posix" or not env_file.exists():
        return
    try:
        env_file.chmod(0o600)
    except OSError:
        pass


def _env_password_value(raw: str) -> str:
    """Return the effective POSTGRES_PASSWORD value from a raw dotenv RHS.

    Strips inline comments (for unquoted values), surrounding quotes, and
    whitespace so a ``POSTGRES_PASSWORD= # comment`` or ``POSTGRES_PASSWORD=""``
    line is correctly treated as empty.
    """
    value = raw.strip()
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        return value[1:end] if end != -1 else value[1:]
    # Unquoted: an unescaped '#' starts an inline comment.
    if "#" in value:
        value = value.split("#", 1)[0]
    return value.strip()


def _ensure_postgres_password(env_file: Path) -> None:
    """
    Guarantee a strong POSTGRES_PASSWORD in the project .env.

    The shipped .env.example intentionally has no default password (so the DB is
    never brought up with a repo-known credential). To keep the CLI usable, we
    generate a strong random value on first run when it is missing or empty.

    The *effective* value is the last non-empty ``POSTGRES_PASSWORD`` assignment
    (matching how docker compose resolves duplicate keys), so a later empty
    override does not leave the DB with an empty password.
    """
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    pattern = re.compile(r"^\s*POSTGRES_PASSWORD\s*=(.*)$")

    effective = ""
    for line in lines:
        match = pattern.match(line)
        if match:
            effective = _env_password_value(match.group(1))
    if effective:
        return  # already set to a non-empty effective value

    generated = f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}"
    # Drop every existing POSTGRES_PASSWORD assignment and append a single
    # generated one so there is exactly one, non-empty effective value.
    new_lines = [line for line in lines if not pattern.match(line)]
    new_lines.append(generated)

    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


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

        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env,
            timeout=COMPOSE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return DeployResult(
                success=False,
                message="docker compose up failed",
                error=(result.stderr or result.stdout or "").strip(),
            )

        port = _resolve_api_port(env, project_dir)
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

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=COMPOSE_TIMEOUT_SECONDS,
        )
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
