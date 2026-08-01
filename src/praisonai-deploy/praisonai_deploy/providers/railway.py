"""
Railway deployment provider (optional — prefer infra/starters/railway).
"""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from ..doctor import DoctorCheckResult, DoctorReport
from ..models import DeployResult, DeployStatus, DestroyResult, ServiceState
from .base import BaseProvider
from .fly import _check_cli


class RailwayProvider(BaseProvider):
    """Deploy to Railway via railway CLI."""

    def doctor(self) -> DoctorReport:
        return DoctorReport(checks=[_check_cli("railway", ["--version"])])

    def plan(self) -> Dict[str, Any]:
        return {
            "provider": "railway",
            "service_name": self.config.service_name,
            "notes": "Use praisonai deploy create --template railway for starter scaffold",
        }

    def deploy(self) -> DeployResult:
        try:
            result = subprocess.run(
                ["railway", "up", "--detach"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                return DeployResult(
                    success=False,
                    message="Railway deploy failed",
                    error=(result.stderr or result.stdout or "").strip(),
                )
            return DeployResult(
                success=True,
                message="Railway deploy initiated",
                metadata={"stdout": (result.stdout or "").strip()},
            )
        except FileNotFoundError:
            return DeployResult(
                success=False,
                message="railway CLI not found",
                error="Install Railway CLI or run: praisonai deploy create --template railway",
            )
        except Exception as e:
            return DeployResult(success=False, message="Railway deploy failed", error=str(e))

    def status(self) -> DeployStatus:
        try:
            result = subprocess.run(
                ["railway", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            ok = result.returncode == 0
            return DeployStatus(
                state=ServiceState.RUNNING if ok else ServiceState.UNKNOWN,
                message=(result.stdout or result.stderr or "").strip(),
                service_name=self.config.service_name,
                provider="railway",
                healthy=ok,
            )
        except Exception as e:
            return DeployStatus(state=ServiceState.UNKNOWN, message=str(e), provider="railway")

    def destroy(self, force: bool = False) -> DestroyResult:
        return DestroyResult(
            success=False,
            message="Railway destroy not automated",
            error="Remove the service in the Railway dashboard or use railway down manually",
        )
