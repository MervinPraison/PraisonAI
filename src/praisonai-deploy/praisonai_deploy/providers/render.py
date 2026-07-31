"""
Render deployment provider (optional — prefer infra/starters/render).
"""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from ..doctor import DoctorCheckResult, DoctorReport
from ..models import DeployResult, DeployStatus, DestroyResult, ServiceState
from .base import BaseProvider
from .fly import _check_cli


class RenderProvider(BaseProvider):
    """Deploy to Render via render CLI (when available)."""

    def doctor(self) -> DoctorReport:
        checks = [_check_cli("render", ["--version"])]
        return DoctorReport(checks=checks)

    def plan(self) -> Dict[str, Any]:
        return {
            "provider": "render",
            "service_name": self.config.service_name,
            "notes": "Use praisonai deploy create --template render for starter scaffold",
        }

    def deploy(self) -> DeployResult:
        try:
            result = subprocess.run(
                ["render", "deploys", "create", self.config.service_name, "--confirm"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                return DeployResult(
                    success=False,
                    message="Render deploy failed",
                    error=(result.stderr or result.stdout or "").strip(),
                )
            return DeployResult(
                success=True,
                message=f"Render deploy triggered for {self.config.service_name}",
            )
        except FileNotFoundError:
            return DeployResult(
                success=False,
                message="render CLI not found",
                error="Install Render CLI or run: praisonai deploy create --template render",
            )
        except Exception as e:
            return DeployResult(success=False, message="Render deploy failed", error=str(e))

    def status(self) -> DeployStatus:
        return DeployStatus(
            state=ServiceState.UNKNOWN,
            message="Use Render dashboard for service status",
            service_name=self.config.service_name,
            provider="render",
        )

    def destroy(self, force: bool = False) -> DestroyResult:
        return DestroyResult(
            success=False,
            message="Render destroy not automated",
            error="Delete the service in the Render dashboard",
        )
