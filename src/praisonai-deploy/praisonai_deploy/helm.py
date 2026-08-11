"""
Thin Helm CLI wrapper for repo-infra charts under package infra/ trees.
"""
from __future__ import annotations

import subprocess
from typing import Optional

from ._infra import AGENTS_API_CHART, GATEWAY_CHART, resolve_helm_chart_dir
from .models import DeployResult

CHART_ALIASES = {
    "gateway": GATEWAY_CHART,
    "agents-api": AGENTS_API_CHART,
    GATEWAY_CHART: GATEWAY_CHART,
    AGENTS_API_CHART: AGENTS_API_CHART,
}


def resolve_chart_dir(chart: str, chart_dir: Optional[str] = None):
    """Resolve chart directory from alias or explicit path."""
    chart_name = CHART_ALIASES.get(chart, chart)
    return resolve_helm_chart_dir(chart_name, chart_dir=chart_dir)


def helm_upgrade_install(
    chart: str,
    release: str = "praisonai",
    namespace: str = "default",
    chart_dir: Optional[str] = None,
    install: bool = True,
    extra_set: Optional[list[str]] = None,
) -> DeployResult:
    """Run helm upgrade --install for a repo-infra chart."""
    try:
        path = resolve_chart_dir(chart, chart_dir)
        cmd = [
            "helm", "upgrade", release, str(path),
            "--namespace", namespace,
        ]
        if install:
            cmd.insert(2, "--install")

        chart_name = path.name
        sets = list(extra_set or [])
        if chart_name == GATEWAY_CHART and not any(s.startswith("auth.") for s in sets):
            sets.append("auth.existingSecret=praisonai-gateway-auth")
        if chart_name == AGENTS_API_CHART:
            if not any(s.startswith("auth.") for s in sets):
                sets.append("auth.existingSecret=praisonai-api-auth")
            if not any(s.startswith("postgres.auth.") for s in sets):
                sets.append("postgres.auth.existingSecret=praisonai-postgres-auth")

        for item in sets:
            cmd.extend(["--set", item])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return DeployResult(
                success=False,
                message="helm upgrade failed",
                error=(result.stderr or result.stdout or "").strip(),
            )

        return DeployResult(
            success=True,
            message=f"Helm release '{release}' upgraded in namespace '{namespace}'",
            metadata={
                "chart": chart_name,
                "chart_dir": str(path),
                "release": release,
                "namespace": namespace,
            },
        )
    except FileNotFoundError as e:
        return DeployResult(success=False, message=str(e), error=str(e))
    except Exception as e:
        return DeployResult(success=False, message="Helm deploy failed", error=str(e))
