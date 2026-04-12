"""
E2B Compute Provider — cloud sandbox-based compute for managed agents.

Uses E2B SDK for secure, isolated sandbox environments with <1s boot.

Requires: ``pip install e2b``
Environment: ``E2B_API_KEY``
"""

import logging
import os
import time
import uuid
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class E2BCompute:
    """E2B cloud sandbox compute provider.

    Satisfies ``ComputeProviderProtocol`` (Core SDK).
    Uses E2B SDK for secure, isolated sandbox environments.

    Example::

        from praisonaiagents.managed import ComputeConfig
        from praisonai.integrations.compute.e2b import E2BCompute

        compute = E2BCompute()
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
    ) -> None:
        self._api_key = api_key or os.environ.get("E2B_API_KEY", "")
        self._sandboxes: Dict[str, Dict[str, Any]] = {}

    @property
    def provider_name(self) -> str:
        return "e2b"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    async def provision(self, config) -> Any:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._provision_sync, config)

    def _provision_sync(self, config) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        try:
            from e2b import Sandbox
        except ImportError:
            raise ImportError("E2B SDK required. Install with: pip install e2b")

        instance_id = f"e2b_{uuid.uuid4().hex[:12]}"

        # E2B uses templates, not images — use 'base' for default
        template = config.metadata.get("e2b_template") if config.metadata else None

        sandbox = Sandbox.create(
            template=template,
            timeout=max(config.idle_timeout_s, 60),
            envs=config.env or None,
            api_key=self._api_key,
        )

        self._sandboxes[instance_id] = {
            "sandbox": sandbox,
            "sandbox_id": sandbox.sandbox_id,
            "config": config,
            "created_at": time.time(),
        }

        # Install packages
        if config.packages:
            self._install_packages_sync(sandbox, config.packages)

        logger.info("[e2b_compute] provisioned: %s sandbox=%s", instance_id, sandbox.sandbox_id)

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"e2b://{sandbox.sandbox_id}",
            provider="e2b",
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
                info["sandbox"].kill()
            except Exception as e:
                logger.warning("[e2b_compute] shutdown error: %s", e)
            logger.info("[e2b_compute] shutdown: %s", instance_id)

    async def get_status(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        info = self._sandboxes.get(instance_id)
        if not info:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="e2b",
            )
        try:
            running = info["sandbox"].is_running()
        except Exception:
            running = False

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING if running else InstanceStatus.STOPPED,
            endpoint=f"e2b://{info['sandbox_id']}",
            provider="e2b",
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
            result = sandbox.commands.run(command, timeout=timeout)
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
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
                content = f.read()
            info["sandbox"].files.write(remote_path, content)
            return True
        except Exception as e:
            logger.error("[e2b_compute] upload failed: %s", e)
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
            content = info["sandbox"].files.read(remote_path)
            with open(local_path, "w") as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error("[e2b_compute] download failed: %s", e)
            return False

    async def list_instances(self) -> List[Any]:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = []
        for iid, info in self._sandboxes.items():
            try:
                running = info["sandbox"].is_running()
            except Exception:
                running = False
            if running:
                result.append(InstanceInfo(
                    instance_id=iid,
                    status=InstanceStatus.RUNNING,
                    endpoint=f"e2b://{info['sandbox_id']}",
                    provider="e2b",
                    created_at=info.get("created_at", 0),
                ))
        return result

    def _install_packages_sync(self, sandbox, packages: Dict[str, list]) -> None:
        pip_pkgs = packages.get("pip", [])
        if pip_pkgs:
            cmd = f"pip install -q {' '.join(pip_pkgs)}"
            logger.info("[e2b_compute] installing pip: %s", pip_pkgs)
            try:
                result = sandbox.commands.run(cmd, timeout=120)
                if result.exit_code != 0:
                    logger.warning("[e2b_compute] pip install failed: %s", result.stderr)
            except Exception as e:
                logger.warning("[e2b_compute] pip install error: %s", e)

        npm_pkgs = packages.get("npm", [])
        if npm_pkgs:
            cmd = f"npm install -g {' '.join(npm_pkgs)}"
            logger.info("[e2b_compute] installing npm: %s", npm_pkgs)
            try:
                sandbox.commands.run(cmd, timeout=120)
            except Exception as e:
                logger.warning("[e2b_compute] npm install error: %s", e)
