"""
Daytona Compute Provider — cloud sandbox-based compute for managed agents.

Uses Daytona SDK for 90ms sandbox creation with full process isolation.

Requires: ``pip install daytona-sdk``
Environment: ``DAYTONA_API_KEY``, ``DAYTONA_API_URL``, ``DAYTONA_TARGET``
"""

import logging
import os
import time
import uuid
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DaytonaCompute:
    """Daytona cloud sandbox compute provider.

    Satisfies ``ComputeProviderProtocol`` (Core SDK).
    Uses Daytona SDK for secure, isolated sandbox environments.

    Example::

        from praisonaiagents.managed import ComputeConfig
        from praisonai.integrations.compute.daytona import DaytonaCompute

        compute = DaytonaCompute()
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
        api_url: str = "",
        target: str = "",
    ) -> None:
        self._api_key = api_key or os.environ.get("DAYTONA_API_KEY", "")
        self._api_url = api_url or os.environ.get("DAYTONA_API_URL", "https://app.daytona.io/api")
        self._target = target or os.environ.get("DAYTONA_TARGET", "us")
        self._client = None
        self._sandboxes: Dict[str, Any] = {}

    def _get_client(self):
        if self._client is None:
            try:
                from daytona_sdk import Daytona, DaytonaConfig
            except ImportError:
                raise ImportError(
                    "Daytona SDK required. Install with: pip install daytona-sdk"
                )
            self._client = Daytona(DaytonaConfig(
                api_key=self._api_key,
                api_url=self._api_url,
                target=self._target,
            ))
        return self._client

    @property
    def provider_name(self) -> str:
        return "daytona"

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
        instance_id = f"daytona_{uuid.uuid4().hex[:12]}"

        try:
            from daytona_sdk import CreateSandboxFromImageParams, Resources
        except ImportError:
            raise ImportError("Daytona SDK required. Install with: pip install daytona-sdk")

        resources = Resources(cpu=config.cpu, memory=config.memory_mb)

        params = CreateSandboxFromImageParams(
            image=config.image,
            resources=resources,
            env_vars=config.env or None,
            auto_stop_interval=max(config.idle_timeout_s // 60, 1) if config.auto_shutdown else 0,
        )

        sandbox = client.create(params, timeout=120)
        sandbox_id = sandbox.id if hasattr(sandbox, 'id') else str(sandbox)

        self._sandboxes[instance_id] = {
            "sandbox": sandbox,
            "sandbox_id": sandbox_id,
            "config": config,
            "created_at": time.time(),
        }

        # Install packages
        if config.packages:
            self._install_packages_sync(sandbox, config.packages)

        logger.info("[daytona_compute] provisioned: %s sandbox=%s", instance_id, sandbox_id)

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"daytona://{sandbox_id}",
            provider="daytona",
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
                info["sandbox"].delete()
            except Exception as e:
                logger.warning("[daytona_compute] shutdown error: %s", e)
            logger.info("[daytona_compute] shutdown: %s", instance_id)

    async def get_status(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        info = self._sandboxes.get(instance_id)
        if not info:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="daytona",
            )
        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"daytona://{info['sandbox_id']}",
            provider="daytona",
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
            response = sandbox.process.exec(command, timeout=timeout)
            return {
                "stdout": response.result or "",
                "stderr": "",
                "exit_code": response.exit_code,
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
                content = f.read()
            info["sandbox"].fs.upload_file(remote_path, content)
            return True
        except Exception as e:
            logger.error("[daytona_compute] upload failed: %s", e)
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
            content = info["sandbox"].fs.download_file(remote_path)
            with open(local_path, "wb") as f:
                f.write(content if isinstance(content, bytes) else content.encode())
            return True
        except Exception as e:
            logger.error("[daytona_compute] download failed: %s", e)
            return False

    async def list_instances(self) -> List[Any]:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = []
        for iid, info in self._sandboxes.items():
            result.append(InstanceInfo(
                instance_id=iid,
                status=InstanceStatus.RUNNING,
                endpoint=f"daytona://{info['sandbox_id']}",
                provider="daytona",
                created_at=info.get("created_at", 0),
            ))
        return result

    def _install_packages_sync(self, sandbox, packages: Dict[str, list]) -> None:
        pip_pkgs = packages.get("pip", [])
        if pip_pkgs:
            cmd = f"pip install -q {' '.join(pip_pkgs)}"
            logger.info("[daytona_compute] installing pip: %s", pip_pkgs)
            try:
                response = sandbox.process.exec(cmd, timeout=120)
                if response.exit_code != 0:
                    logger.warning("[daytona_compute] pip install failed: %s", response.result)
            except Exception as e:
                logger.warning("[daytona_compute] pip install error: %s", e)

        npm_pkgs = packages.get("npm", [])
        if npm_pkgs:
            cmd = f"npm install -g {' '.join(npm_pkgs)}"
            logger.info("[daytona_compute] installing npm: %s", npm_pkgs)
            try:
                sandbox.process.exec(cmd, timeout=120)
            except Exception as e:
                logger.warning("[daytona_compute] npm install error: %s", e)
