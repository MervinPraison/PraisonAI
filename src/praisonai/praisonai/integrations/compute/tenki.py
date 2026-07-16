"""
Tenki Compute Provider — cloud sandbox-based compute for managed agents.

Uses the Tenki Cloud SDK to run tools in disposable Linux microVMs.

Requires: ``pip install tenki-sandbox``
Environment: ``TENKI_API_KEY`` (optionally ``TENKI_WORKSPACE_ID``, ``TENKI_PROJECT_ID``)
"""

import base64
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
            image="python:3.12-slim",
            packages={"pip": ["pandas"]},
        )
        info = await compute.provision(config)
        result = await compute.execute(info.instance_id, "python -c 'print(1+1)'")
        await compute.shutdown(info.instance_id)
    """

    def __init__(
        self,
        api_key: str = "",
        workspace_id: str = "",
        project_id: str = "",
    ) -> None:
        self._api_key = api_key or os.environ.get("TENKI_API_KEY", "")
        self._workspace_id = workspace_id or os.environ.get("TENKI_WORKSPACE_ID", "")
        self._project_id = project_id or os.environ.get("TENKI_PROJECT_ID", "")
        self._client = None
        self._sandboxes: Dict[str, Dict[str, Any]] = {}

    def _get_client(self):
        if self._client is None:
            try:
                from tenki_sandbox import Client
            except ImportError:
                raise ImportError(
                    "Tenki SDK required. Install with: pip install tenki-sandbox"
                )
            # Falls back to TENKI_API_KEY / TENKI_AUTH_TOKEN in the environment.
            self._client = Client(auth_token=self._api_key) if self._api_key else Client()
        return self._client

    def _resolve_ids(self, client) -> tuple:
        """Resolve the workspace/project to create sandboxes under.

        The SDK has no "current project" default like the CLI, so fall back to
        the first workspace/project on the account.
        """
        if self._workspace_id and self._project_id:
            return self._workspace_id, self._project_id
        identity = client.who_am_i()
        workspaces = identity.workspaces
        if not workspaces:
            raise RuntimeError("No Tenki workspaces available for this API key")
        ws = next((w for w in workspaces if w.id == self._workspace_id), workspaces[0]) if self._workspace_id else workspaces[0]
        if not ws.projects:
            raise RuntimeError(f"No Tenki projects available in workspace {ws.id}")
        proj = next((p for p in ws.projects if p.id == self._project_id), ws.projects[0]) if self._project_id else ws.projects[0]
        self._workspace_id, self._project_id = ws.id, proj.id
        return ws.id, proj.id

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
        workspace_id, project_id = self._resolve_ids(client)
        instance_id = f"tenki_{uuid.uuid4().hex[:12]}"

        create_kwargs: Dict[str, Any] = {
            "name": instance_id,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "cpu_cores": config.cpu,
            "memory_mb": config.memory_mb,
            "env": config.env or None,
            # Tools generally need outbound network for package installs / APIs.
            "allow_outbound": True,
        }
        # Custom images map to a Tenki registry image / template; default stock
        # image otherwise (keeps the provider on stable features).
        image = (config.metadata or {}).get("tenki_image")
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
            self._install_packages_sync(sandbox, config.packages)

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
        info = self._sandboxes.pop(instance_id, None)
        if info:
            try:
                info["sandbox"].terminate()
            except Exception as e:
                logger.warning("[tenki_compute] shutdown error: %s", e)
            logger.info("[tenki_compute] shutdown: %s", instance_id)

    async def get_status(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        info = self._sandboxes.get(instance_id)
        if not info:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="tenki",
            )
        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
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
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = []
        for iid, info in self._sandboxes.items():
            result.append(InstanceInfo(
                instance_id=iid,
                status=InstanceStatus.RUNNING,
                endpoint=f"tenki://{info['sandbox_id']}",
                provider="tenki",
                created_at=info.get("created_at", 0),
            ))
        return result

    def _install_packages_sync(self, sandbox, packages: Dict[str, list]) -> None:
        pip_pkgs = packages.get("pip", [])
        if pip_pkgs:
            # The default Tenki image ships python3 but not pip; bootstrap it.
            cmd = (
                "if ! command -v pip3 >/dev/null 2>&1; then "
                "sudo apt-get update -y && sudo apt-get install -y python3-pip; fi && "
                f"pip3 install -q --break-system-packages {' '.join(pip_pkgs)}"
            )
            logger.info("[tenki_compute] installing pip: %s", pip_pkgs)
            try:
                result = sandbox.exec("bash", "-lc", cmd, timeout=300)
                if result.exit_code != 0:
                    logger.warning(
                        "[tenki_compute] pip install failed: %s",
                        (result.stderr or b"").decode(errors="replace"),
                    )
            except Exception as e:
                logger.warning("[tenki_compute] pip install error: %s", e)

        npm_pkgs = packages.get("npm", [])
        if npm_pkgs:
            cmd = (
                "if ! command -v npm >/dev/null 2>&1; then "
                "sudo apt-get update -y && sudo apt-get install -y npm; fi && "
                f"npm install -g {' '.join(npm_pkgs)}"
            )
            logger.info("[tenki_compute] installing npm: %s", npm_pkgs)
            try:
                sandbox.exec("bash", "-lc", cmd, timeout=300)
            except Exception as e:
                logger.warning("[tenki_compute] npm install error: %s", e)
