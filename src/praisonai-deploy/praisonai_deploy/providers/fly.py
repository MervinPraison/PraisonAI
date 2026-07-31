"""
Fly.io deployment provider (optional — prefer infra/starters/fly for full scaffold).
"""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from ..doctor import DoctorCheckResult, DoctorReport
from ..models import DeployResult, DeployStatus, DestroyResult, ServiceState
from .base import BaseProvider


def _check_cli(name: str, version_args: list[str]) -> DoctorCheckResult:
    try:
        result = subprocess.run(
            [name, *version_args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = (result.stdout or result.stderr or "").strip().splitlines()[0]
            return DoctorCheckResult(name=f"{name} CLI", passed=True, message=version)
        return DoctorCheckResult(
            name=f"{name} CLI",
            passed=False,
            message=f"{name} not available",
            fix_suggestion=f"Install {name} and ensure it is on PATH",
        )
    except FileNotFoundError:
        return DoctorCheckResult(
            name=f"{name} CLI",
            passed=False,
            message=f"{name} not found",
            fix_suggestion=f"Install {name} (https://fly.io/docs/flyctl/install/)",
        )
    except Exception as e:
        return DoctorCheckResult(name=f"{name} CLI", passed=False, message=str(e))


class FlyProvider(BaseProvider):
    """Deploy to Fly.io via flyctl."""

    def doctor(self) -> DoctorReport:
        checks = [_check_cli("flyctl", ["version"])]
        token = __import__("os").environ.get("FLY_API_TOKEN")
        checks.append(DoctorCheckResult(
            name="FLY_API_TOKEN",
            passed=bool(token),
            message="Set" if token else "Not set",
            fix_suggestion="export FLY_API_TOKEN=... or fly auth login",
        ))
        return DoctorReport(checks=checks)

    def plan(self) -> Dict[str, Any]:
        return {
            "provider": "fly",
            "service_name": self.config.service_name,
            "region": self.config.region,
            "notes": "Use praisonai deploy create --template fly for starter scaffold",
        }

    def deploy(self) -> DeployResult:
        app = self.config.service_name
        try:
            result = subprocess.run(
                ["flyctl", "deploy", "--app", app, "--remote-only"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                return DeployResult(
                    success=False,
                    message="Fly deploy failed",
                    error=(result.stderr or result.stdout or "").strip(),
                )
            url = f"https://{app}.fly.dev"
            return DeployResult(success=True, message=f"Deployed to Fly app {app}", url=url)
        except FileNotFoundError:
            return DeployResult(
                success=False,
                message="flyctl not found",
                error="Install flyctl or run: praisonai deploy create --template fly",
            )
        except Exception as e:
            return DeployResult(success=False, message="Fly deploy failed", error=str(e))

    def status(self) -> DeployStatus:
        app = self.config.service_name
        try:
            result = subprocess.run(
                ["flyctl", "status", "--app", app, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            running = result.returncode == 0
            return DeployStatus(
                state=ServiceState.RUNNING if running else ServiceState.UNKNOWN,
                url=f"https://{app}.fly.dev",
                message="Fly app status retrieved" if running else "Could not retrieve status",
                service_name=app,
                provider="fly",
                healthy=running,
            )
        except Exception as e:
            return DeployStatus(
                state=ServiceState.UNKNOWN,
                message=str(e),
                service_name=app,
                provider="fly",
            )

    def destroy(self, force: bool = False) -> DestroyResult:
        app = self.config.service_name
        try:
            cmd = ["flyctl", "apps", "destroy", app]
            if force:
                cmd.append("--yes")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return DestroyResult(
                    success=False,
                    message="Fly destroy failed",
                    error=(result.stderr or result.stdout or "").strip(),
                )
            return DestroyResult(success=True, message=f"Destroyed Fly app {app}", resources_deleted=[app])
        except Exception as e:
            return DestroyResult(success=False, message="Fly destroy failed", error=str(e))
