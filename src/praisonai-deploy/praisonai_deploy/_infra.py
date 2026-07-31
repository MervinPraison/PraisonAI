"""
Resolve checkout-only deployment infra paths (Helm, Compose, starters).

Infra lives outside the PyPI wheel under package-adjacent ``infra/`` trees.
Gateway charts are owned by praisonai-bot; compose/starters/agents-api by C14.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

GATEWAY_CHART = "praisonai-gateway"
AGENTS_API_CHART = "praisonai-agents-api"
DEFAULT_STACK_NAME = "agents-stack"
STARTERS_INDEX = "templates.yaml"


def deploy_infra_root() -> Path:
    """C14 infra root: src/praisonai-deploy/infra."""
    return Path(__file__).resolve().parents[1] / "infra"


def bot_infra_root() -> Path:
    """C9 infra root: src/praisonai-bot/infra (sibling package in monorepo)."""
    deploy_pkg = Path(__file__).resolve().parents[1]
    monorepo_src = deploy_pkg.parent
    return monorepo_src / "praisonai-bot" / "infra"


def _walk_legacy_deploy_root(start: Path) -> Optional[Path]:
    """Legacy monorepo root ``deploy/`` (one-release fallback)."""
    for parent in [start, *start.parents]:
        deploy_dir = parent / "deploy"
        if (
            (deploy_dir / "helm").is_dir()
            or (deploy_dir / "compose").is_dir()
            or (deploy_dir / "starters").is_dir()
        ):
            return parent
    return None


def resolve_deploy_infra_root(
    *,
    explicit: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """Resolve C14 infra root with optional overrides."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Infra directory not found: {path}")
        return path

    infra_env = os.environ.get("PRAISONAI_INFRA_ROOT")
    if infra_env:
        path = Path(infra_env).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"PRAISONAI_INFRA_ROOT is not a directory: {path}")
        return path

    package_root = deploy_infra_root()
    if package_root.is_dir():
        return package_root

    legacy = _walk_legacy_deploy_root(cwd or Path.cwd())
    if legacy is not None:
        return legacy / "deploy"

    raise FileNotFoundError(
        "Could not find praisonai-deploy infra. Run from a monorepo checkout, "
        "set PRAISONAI_INFRA_ROOT, or pass an explicit path."
    )


def _compose_stack_from_infra(infra_root: Path) -> Optional[Path]:
    candidate = infra_root / "compose" / DEFAULT_STACK_NAME
    if (candidate / "docker-compose.yml").is_file():
        return candidate
    return None


def resolve_compose_stack_dir(
    *,
    stack_dir: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """Resolve compose stack directory (contains docker-compose.yml)."""
    if stack_dir:
        path = Path(stack_dir).expanduser().resolve()
        if not (path / "docker-compose.yml").is_file():
            raise FileNotFoundError(f"Compose stack not found: {path / 'docker-compose.yml'}")
        return path

    env_path = os.environ.get("PRAISONAI_COMPOSE_STACK")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if not (path / "docker-compose.yml").is_file():
            raise FileNotFoundError(f"Compose stack not found: {path / 'docker-compose.yml'}")
        return path

    if os.environ.get("PRAISONAI_INFRA_ROOT"):
        infra_root = resolve_deploy_infra_root(cwd=cwd)
        candidate = _compose_stack_from_infra(infra_root)
        if candidate is not None:
            return candidate
        raise FileNotFoundError(
            f"Compose stack not found under PRAISONAI_INFRA_ROOT: "
            f"{infra_root / 'compose' / DEFAULT_STACK_NAME / 'docker-compose.yml'}"
        )

    candidate = _compose_stack_from_infra(deploy_infra_root())
    if candidate is not None:
        return candidate

    legacy = _walk_legacy_deploy_root(cwd or Path.cwd())
    if legacy is not None:
        candidate = legacy / "deploy" / "compose" / DEFAULT_STACK_NAME
        if (candidate / "docker-compose.yml").is_file():
            return candidate

    raise FileNotFoundError(
        "Could not find compose stack. Set PRAISONAI_COMPOSE_STACK or PRAISONAI_INFRA_ROOT, "
        "run from a monorepo checkout, or pass --stack-dir."
    )


def _helm_search_roots(cwd: Optional[Path] = None) -> list[Path]:
    roots: list[Path] = []
    env_root = os.environ.get("PRAISONAI_HELM_ROOT")
    if env_root:
        path = Path(env_root).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"PRAISONAI_HELM_ROOT is not a directory: {path}")
        roots.append(path)

    if os.environ.get("PRAISONAI_INFRA_ROOT"):
        infra_root = resolve_deploy_infra_root(cwd=cwd)
        roots.append(infra_root / "helm")

    bot_helm = bot_infra_root() / "helm"
    if bot_helm.is_dir():
        roots.append(bot_helm)

    deploy_helm = deploy_infra_root() / "helm"
    if deploy_helm.is_dir():
        roots.append(deploy_helm)

    legacy = _walk_legacy_deploy_root(cwd or Path.cwd())
    if legacy is not None:
        roots.append(legacy / "deploy" / "helm")

    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _helm_not_found_message(chart_name: str) -> str:
    if chart_name == GATEWAY_CHART:
        return (
            f"Helm chart '{chart_name}' not found. Gateway charts live under "
            "src/praisonai-bot/infra/helm/ in a full checkout. Set PRAISONAI_HELM_ROOT, "
            "pass --chart-dir, or ensure praisonai-bot infra is present."
        )
    return (
        f"Helm chart '{chart_name}' not found. Set PRAISONAI_HELM_ROOT or PRAISONAI_INFRA_ROOT, "
        "run from a monorepo checkout, or pass --chart-dir."
    )


def resolve_helm_chart_dir(
    chart_name: str,
    chart_dir: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """Resolve a Helm chart directory by chart folder name."""
    if chart_dir:
        path = Path(chart_dir).expanduser().resolve()
        if not (path / "Chart.yaml").is_file():
            raise FileNotFoundError(f"Helm chart not found: {path / 'Chart.yaml'}")
        return path

    for root in _helm_search_roots(cwd=cwd):
        if not root.is_dir():
            continue
        candidate = root / chart_name
        if (candidate / "Chart.yaml").is_file():
            return candidate

    raise FileNotFoundError(_helm_not_found_message(chart_name))


def resolve_starters_root(starters_root: Optional[str] = None, cwd: Optional[Path] = None) -> Path:
    """Resolve starters template index directory."""
    if starters_root:
        path = Path(starters_root).expanduser().resolve()
        if not (path / STARTERS_INDEX).is_file():
            raise FileNotFoundError(f"Starters index not found: {path / STARTERS_INDEX}")
        return path

    env_path = os.environ.get("PRAISONAI_STARTERS_ROOT")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if not (path / STARTERS_INDEX).is_file():
            raise FileNotFoundError(f"Starters index not found: {path / STARTERS_INDEX}")
        return path

    if os.environ.get("PRAISONAI_INFRA_ROOT"):
        infra_root = resolve_deploy_infra_root(cwd=cwd)
        candidate = infra_root / "starters"
        if (candidate / STARTERS_INDEX).is_file():
            return candidate
        raise FileNotFoundError(
            f"Starters index not found under PRAISONAI_INFRA_ROOT: {candidate / STARTERS_INDEX}"
        )

    candidate = deploy_infra_root() / "starters"
    if (candidate / STARTERS_INDEX).is_file():
        return candidate

    legacy = _walk_legacy_deploy_root(cwd or Path.cwd())
    if legacy is not None:
        candidate = legacy / "deploy" / "starters"
        if (candidate / STARTERS_INDEX).is_file():
            return candidate

    raise FileNotFoundError(
        "Could not find deploy starters. Set PRAISONAI_STARTERS_ROOT or PRAISONAI_INFRA_ROOT, "
        "run from a monorepo checkout, or pass --starters-root."
    )


def iter_helm_chart_dirs() -> list[Path]:
    """All chart directories discovered under known helm roots (for CI/scripts)."""
    charts: list[Path] = []
    seen: set[Path] = set()
    for root in _helm_search_roots():
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "Chart.yaml").is_file():
                resolved = child.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    charts.append(resolved)
    return charts
