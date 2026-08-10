"""
Tenki Compute Provider — cloud sandbox-based compute for managed agents.

Uses the Tenki Cloud SDK to run tools in disposable Linux microVMs.

Requires: ``pip install tenki``
Environment: ``TENKI_API_KEY`` or ``TENKI_AUTH_TOKEN`` (optionally ``TENKI_WORKSPACE_ID``)
"""

import base64
import dataclasses
import logging
import os
import shlex
import time
import uuid
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class TenkiCompute:
    """Tenki Cloud microVM compute provider.

    Satisfies ``ComputeProviderProtocol`` (Core SDK). Uses only stable Tenki
    features (ephemeral exec + file I/O over base64) so it works on the default
    image without volumes, snapshots or templates.

    Example::

        from praisonaiagents.managed import ComputeConfig
        from praisonai.integrations.compute.tenki import TenkiCompute

        compute = TenkiCompute()
        config = ComputeConfig(
            packages={"pip": ["pandas"]},  # installed on Tenki's stock image
        )
        info = await compute.provision(config)
        result = await compute.execute(info.instance_id, "python -c 'print(1+1)'")
        await compute.shutdown(info.instance_id)
    """

    def __init__(
        self,
        api_key: str = "",
        workspace_id: str = "",
    ) -> None:
        # Match the SDK's own precedence: explicit key, then TENKI_AUTH_TOKEN,
        # then TENKI_API_KEY — so is_available agrees with what Client() resolves.
        self._api_key = (
            api_key
            or os.environ.get("TENKI_AUTH_TOKEN", "")
            or os.environ.get("TENKI_API_KEY", "")
        )
        self._workspace_id = workspace_id or os.environ.get("TENKI_WORKSPACE_ID", "")
        self._client = None
        self._sandboxes: Dict[str, Dict[str, Any]] = {}

    def _get_client(self):
        if self._client is None:
            try:
                from tenki import Client
            except ImportError as e:
                raise ImportError(
                    "Tenki SDK required. Install with: pip install tenki"
                ) from e
            # Falls back to TENKI_API_KEY / TENKI_AUTH_TOKEN in the environment.
            self._client = Client(auth_token=self._api_key) if self._api_key else Client()
        return self._client

    def _resolve_workspace(self, client) -> str:
        """Resolve the workspace to create sandboxes under.

        The SDK has no "current workspace" default like the CLI. An explicitly
        configured TENKI_WORKSPACE_ID is trusted (Tenki validates it at
        create()); otherwise fall back to the first workspace on the account.
        """
        if self._workspace_id:
            return self._workspace_id
        identity = client.who_am_i()
        workspaces = identity.workspaces
        if not workspaces:
            raise RuntimeError("No Tenki workspaces available for this API key")
        self._workspace_id = workspaces[0].id
        return self._workspace_id

    @staticmethod
    def _sandbox_id(sandbox) -> str:
        value = getattr(sandbox, "id", None)
        return value() if callable(value) else (value or "")

    @property
    def provider_name(self) -> str:
        return "tenki"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    async def provision(self, config) -> Any:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._provision_sync, config)

    def _provision_sync(self, config) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        client = self._get_client()
        workspace_id = self._resolve_workspace(client)
        instance_id = f"tenki_{uuid.uuid4().hex[:12]}"

        create_kwargs: Dict[str, Any] = {
            "name": instance_id,
            "workspace_id": workspace_id,
            "cpu_cores": config.cpu,
            "memory_mb": config.memory_mb,
            "env": config.env or None,
            # Tenki's outbound control is a single boolean and can't express
            # "limited" per-host allowlists, so only "unrestricted" gets full
            # outbound; any restrictive policy ("limited", which the managed CLI
            # also uses for --no-networking) disables it.
            "allow_outbound": (config.networking or {}).get("type", "unrestricted") == "unrestricted",
        }
        # metadata["tenki_image"] wins; otherwise honour an explicit
        # ComputeConfig.image. Its default is a Docker-style ref, but Tenki's
        # registry is a snapshot store (no Docker pull-through), so an unchanged
        # default means "use Tenki's stock image." Read that default off the
        # dataclass field rather than hardcoding it, so this can't silently
        # drift if ComputeConfig's default ever changes.
        image = (config.metadata or {}).get("tenki_image")
        if not image:
            configured = getattr(config, "image", None)
            default_image = next(
                (f.default for f in dataclasses.fields(config) if f.name == "image"),
                None,
            ) if dataclasses.is_dataclass(config) else None
            if configured and configured != default_image:
                image = configured
        if image:
            create_kwargs["image"] = image
        if config.auto_shutdown:
            create_kwargs["idle_timeout_minutes"] = max(config.idle_timeout_s // 60, 1)
        create_kwargs = {k: v for k, v in create_kwargs.items() if v is not None}

        sandbox = client.create(**create_kwargs)
        sandbox_id = self._sandbox_id(sandbox)

        self._sandboxes[instance_id] = {
            "sandbox": sandbox,
            "sandbox_id": sandbox_id,
            "config": config,
            "created_at": time.time(),
        }

        if config.packages:
            try:
                self._install_packages_sync(sandbox, config.packages)
            except Exception:
                # A half-provisioned sandbox is useless and still bills — tear it
                # down and surface the failure instead of returning RUNNING.
                # Terminate BEFORE dropping the handle so a failed terminate keeps
                # it tracked (for list_instances / retry) rather than leaking it.
                try:
                    sandbox.terminate()
                    self._sandboxes.pop(instance_id, None)
                except Exception as cleanup_err:
                    logger.warning("[tenki_compute] cleanup after failed install: %s", cleanup_err)
                raise

        logger.info("[tenki_compute] provisioned: %s sandbox=%s", instance_id, sandbox_id)

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"tenki://{sandbox_id}",
            provider="tenki",
            created_at=time.time(),
        )

    async def shutdown(self, instance_id: str) -> None:
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._shutdown_sync, instance_id)

    def _shutdown_sync(self, instance_id: str) -> None:
        info = self._sandboxes.get(instance_id)
        if not info:
            return
        # Terminate BEFORE dropping the handle: if this raises (transient network /
        # service error), the sandbox stays tracked so get_status still reports it
        # and a later shutdown can retry, rather than silently leaking the microVM.
        info["sandbox"].terminate()
        self._sandboxes.pop(instance_id, None)
        logger.info("[tenki_compute] shutdown: %s", instance_id)

    @staticmethod
    def _is_running(info: Dict[str, Any]) -> bool:
        """Reconcile against live Tenki state instead of trusting the local map.

        Tenki can terminate a sandbox server-side (e.g. the configured idle
        timeout); without a refresh, get_status/list_instances would keep
        reporting RUNNING for a dead sandbox while execute() hits it and fails.

        A *successful* refresh returning a non-RUNNING state means it really is
        gone. A refresh *exception* (transient outage / rate limit / auth blip)
        is "unknown", not "terminated" — assume still running so we don't hide a
        sandbox that may be alive and still billing.
        """
        try:
            info["sandbox"].refresh()
        except Exception:
            return True
        return info["sandbox"].state == "RUNNING"

    async def get_status(self, instance_id: str) -> Any:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_status_sync, instance_id)

    def _get_status_sync(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        info = self._sandboxes.get(instance_id)
        if not info:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="tenki",
            )
        running = self._is_running(info)
        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING if running else InstanceStatus.STOPPED,
            endpoint=f"tenki://{info['sandbox_id']}",
            provider="tenki",
            created_at=info.get("created_at", 0),
        )

    async def execute(
        self,
        instance_id: str,
        command: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._execute_sync, instance_id, command, timeout,
        )

    def _execute_sync(
        self, instance_id: str, command: str, timeout: int,
    ) -> Dict[str, Any]:
        info = self._sandboxes.get(instance_id)
        if not info:
            return {"stdout": "", "stderr": "Instance not found", "exit_code": -1}

        sandbox = info["sandbox"]
        try:
            result = sandbox.exec("bash", "-lc", command, timeout=timeout)
            return {
                "stdout": (result.stdout or b"").decode(errors="replace"),
                "stderr": (result.stderr or b"").decode(errors="replace"),
                "exit_code": result.exit_code,
            }
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "exit_code": -1}

    async def upload_file(
        self, instance_id: str, local_path: str, remote_path: str,
    ) -> bool:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._upload_sync, instance_id, local_path, remote_path,
        )

    def _upload_sync(self, instance_id: str, local_path: str, remote_path: str) -> bool:
        info = self._sandboxes.get(instance_id)
        if not info:
            return False
        try:
            with open(local_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            path = shlex.quote(remote_path)
            result = info["sandbox"].exec(
                "bash", "-lc", f"mkdir -p \"$(dirname {path})\" && base64 -d > {path}", input=b64, timeout=120,
            )
            return result.exit_code == 0
        except Exception as e:
            logger.error("[tenki_compute] upload failed: %s", e)
            return False

    async def download_file(
        self, instance_id: str, remote_path: str, local_path: str,
    ) -> bool:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._download_sync, instance_id, remote_path, local_path,
        )

    def _download_sync(self, instance_id: str, remote_path: str, local_path: str) -> bool:
        info = self._sandboxes.get(instance_id)
        if not info:
            return False
        try:
            path = shlex.quote(remote_path)
            result = info["sandbox"].exec("bash", "-lc", f"base64 -w0 {path}", timeout=120)
            if result.exit_code != 0:
                logger.error("[tenki_compute] download failed: %s", (result.stderr or b"").decode(errors="replace"))
                return False
            data = base64.b64decode((result.stdout or b"").strip())
            with open(local_path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            logger.error("[tenki_compute] download failed: %s", e)
            return False

    async def list_instances(self) -> List[Any]:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_instances_sync)

    def _list_instances_sync(self) -> List[Any]:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = []
        for iid, info in self._sandboxes.items():
            # Only surface sandboxes that are actually alive remotely, matching
            # the E2B provider (a server-side idle timeout can kill one without
            # our local map knowing).
            if not self._is_running(info):
                continue
            result.append(InstanceInfo(
                instance_id=iid,
                status=InstanceStatus.RUNNING,
                endpoint=f"tenki://{info['sandbox_id']}",
                provider="tenki",
                created_at=info.get("created_at", 0),
            ))
        return result

    def _install_packages_sync(self, sandbox, packages: Dict[str, list]) -> None:
        # Package specs are shlex-quoted before hitting `bash -lc` — a spec must
        # never be able to inject shell commands into the sandbox. Failures raise
        # so provision() can tear the sandbox down rather than report it ready.
        pip_pkgs = packages.get("pip", [])
        if pip_pkgs:
            specs = " ".join(shlex.quote(p) for p in pip_pkgs)
            # The default Tenki image ships python3 but not pip; bootstrap it.
            cmd = (
                "if ! command -v pip3 >/dev/null 2>&1; then "
                "sudo apt-get update -y && sudo apt-get install -y python3-pip; fi && "
                f"pip3 install -q --break-system-packages {specs}"
            )
            # Log only the count — pip specs can carry private-index URLs/tokens.
            logger.info("[tenki_compute] installing %d pip package(s)", len(pip_pkgs))
            result = sandbox.exec("bash", "-lc", cmd, timeout=300)
            if result.exit_code != 0:
                raise RuntimeError(
                    f"pip install failed: {(result.stderr or b'').decode(errors='replace')}"
                )

        npm_pkgs = packages.get("npm", [])
        if npm_pkgs:
            specs = " ".join(shlex.quote(p) for p in npm_pkgs)
            cmd = (
                "if ! command -v npm >/dev/null 2>&1; then "
                "sudo apt-get update -y && sudo apt-get install -y npm; fi && "
                f"npm install -g {specs}"
            )
            logger.info("[tenki_compute] installing %d npm package(s)", len(npm_pkgs))
            result = sandbox.exec("bash", "-lc", cmd, timeout=300)
            if result.exit_code != 0:
                raise RuntimeError(
                    f"npm install failed: {(result.stderr or b'').decode(errors='replace')}"
                )
