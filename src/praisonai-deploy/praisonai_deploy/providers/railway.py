"""
Railway deployment provider (optional — prefer infra/starters/railway).
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
            metadata = {"stdout": (result.stdout or "").strip()}
            if unapplied:
                metadata["unapplied"] = unapplied
            return DeployResult(
                success=True,
                message="Railway deploy initiated",
                metadata=metadata,
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
