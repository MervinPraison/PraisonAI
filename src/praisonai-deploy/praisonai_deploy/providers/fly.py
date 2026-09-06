"""
Fly.io deployment provider (optional — prefer infra/starters/fly for full scaffold).
"""
from __future__ import annotations

import logging
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


logger = logging.getLogger(__name__)


class FlyProvider(BaseProvider):
    """Deploy to Fly.io via flyctl."""

    def doctor(self) -> DoctorReport:
        import os

        checks = [_check_cli("flyctl", ["version"])]
        token = os.environ.get("FLY_API_TOKEN") or os.environ.get("FLY_ACCESS_TOKEN")
        authed = bool(token)
        # A `fly auth login` session stores the token in the flyctl config
        # rather than the environment, so fall back to `fly auth whoami`.
        if not authed:
            try:
                result = subprocess.run(
                    ["flyctl", "auth", "whoami"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                authed = result.returncode == 0
            except Exception:
                authed = False
        checks.append(DoctorCheckResult(
            name="Fly authentication",
            passed=authed,
            message="Authenticated" if authed else "Not authenticated",
            fix_suggestion="export FLY_API_TOKEN=... or run: fly auth login",
        ))
        return DoctorReport(checks=checks)

    def plan(self) -> Dict[str, Any]:
        return {
            "provider": "fly",
            "service_name": self.config.service_name,
            "region": self.config.region,
            "notes": "Use praisonai deploy create --template fly for starter scaffold",
        }

    def _unsupported_settings(self) -> list:
        """CloudConfig values `flyctl deploy` has no flag for.

        Returned so the caller can say so rather than discard them silently.
        Region is set in fly.toml, not on the deploy command; instance counts
        are a scaling concern (`flyctl scale count`).
        """
        unsupported = []
        cfg = self.config
        if cfg.region:
            unsupported.append("region (set it in fly.toml)")
        if cfg.min_instances not in (None, 1) or cfg.max_instances not in (None, 10):
            unsupported.append("min_instances/max_instances (use `flyctl scale count`)")
        return unsupported

    def _deploy_command(self, app: str) -> list:
        """Build the flyctl invocation, carrying the settings it accepts.

        CloudConfig declares env_vars, cpu, memory, image, region and instance
        counts, validates them, and echoes them from `deploy validate --json`.
        This command used to send none of them: a config naming
        env_vars={"OPENAI_API_KEY": ...} deployed an app without its key and
        reported success.

        Flags verified against flyctl v0.4.14: -e/--env, --vm-cpus,
        --vm-memory and --image exist; --region does not.

        `cpu`/`memory` are only forwarded when set away from the CloudConfig
        defaults ("256"/"512"). Those defaults are ECS CPU-unit conventions
        consumed by the AWS provider, not Fly VM core counts -- passing
        `--vm-cpus 256` would request an unavailable machine size and fail a
        previously valid deploy. Fly's own default VM is used when the caller
        does not override it.

        Secrets are NOT placed here: env values can carry credentials, and the
        argument vector is visible to other processes on the host. They go
        through `fly secrets set` in `deploy()` instead.
        """
        cmd = ["flyctl", "deploy", "--app", app, "--remote-only"]
        cfg = self.config
        if cfg.image:
            cmd += ["--image", str(cfg.image)]
        if cfg.cpu not in (None, "256"):
            cmd += ["--vm-cpus", str(cfg.cpu)]
        if cfg.memory not in (None, "512"):
            cmd += ["--vm-memory", str(cfg.memory)]
        return cmd

    def _set_secrets(self, app: str) -> None:
        """Push env_vars through `fly secrets set` rather than the argv.

        Placing `KEY=value` in the deploy argument vector would expose secret
        values (e.g. OPENAI_API_KEY) to anyone able to inspect processes on the
        host. `fly secrets set` is the path the starter already documents.
        `--stage` records the secrets without triggering a second deploy; the
        subsequent `flyctl deploy` applies them.
        """
        env_vars = self.config.env_vars or {}
        if not env_vars:
            return
        pairs = [f"{key}={value}" for key, value in env_vars.items()]
        subprocess.run(
            ["flyctl", "secrets", "set", "--app", app, "--stage", *pairs],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def deploy(self) -> DeployResult:
        app = self.config.service_name
        ignored = self._unsupported_settings()
        if ignored:
            logger.warning(
                "flyctl deploy cannot apply: %s", "; ".join(ignored)
            )
        try:
            self._set_secrets(app)
            result = subprocess.run(
                self._deploy_command(app),
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                return DeployResult(
                    success=False,
                    message="Fly deploy failed",
                    error=(result.stderr or result.stdout or "").strip(),
                    metadata={"unapplied": ignored} if ignored else {},
                )
            url = f"https://{app}.fly.dev"
            return DeployResult(
                success=True,
                message=f"Deployed to Fly app {app}",
                url=url,
                metadata={"unapplied": ignored} if ignored else {},
            )
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
