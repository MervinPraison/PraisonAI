"""
Render deployment provider (optional — prefer infra/starters/render).
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any, Dict

from ..doctor import DoctorCheckResult, DoctorReport
from ..models import DeployResult, DeployStatus, DestroyResult, ServiceState
from .base import BaseProvider
from .fly import _check_cli


logger = logging.getLogger(__name__)


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

    def _unapplied_settings(self) -> list:
        """CloudConfig values this provider does not send to its CLI.

        CloudConfig declares env_vars, cpu, memory, image, region and instance
        counts, validates them (extra="forbid") and echoes them from
        `deploy validate --json`. This provider sends none of them, so a config
        naming env_vars={"OPENAI_API_KEY": ...} deployed an app without its key
        and reported success.

        Wiring them needs flags verified against the real CLI, which was not
        installed when this was written -- guessing at flag names would turn a
        silent omission into a broken deploy. Naming them is the honest half,
        and costs nothing.
        """
        cfg = self.config
        pending = []
        if cfg.env_vars:
            pending.append(f"env_vars ({', '.join(sorted(cfg.env_vars))})")
        if cfg.image:
            pending.append("image")
        if cfg.cpu not in (None, "256"):
            pending.append("cpu")
        if cfg.memory not in (None, "512"):
            pending.append("memory")
        if cfg.region:
            pending.append("region")
        if cfg.min_instances not in (None, 1) or cfg.max_instances not in (None, 10):
            pending.append("min_instances/max_instances")
        return pending

    def deploy(self) -> DeployResult:
        unapplied = self._unapplied_settings()
        if unapplied:
            logger.warning(
                "%s deploy does not apply: %s",
                type(self).__name__, "; ".join(unapplied),
            )
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
                metadata={"unapplied": unapplied} if unapplied else {},
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
