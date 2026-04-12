"""
Local Compute Provider — subprocess-based compute for managed agents.

No container runtime required. Executes commands directly in subprocess.
Auto-shutdown is handled by process exit.
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)


class LocalCompute:
    """Local subprocess-based compute provider.

    Satisfies ``ComputeProviderProtocol`` (Core SDK).
    No external dependencies — runs commands in local subprocesses.
    """

    def __init__(self) -> None:
        self._instances: Dict[str, Dict[str, Any]] = {}

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def is_available(self) -> bool:
        return True

    async def provision(self, config) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        instance_id = f"local_{uuid.uuid4().hex[:12]}"
        working_dir = config.working_dir if config.working_dir != "/workspace" else os.getcwd()

        self._instances[instance_id] = {
            "config": config,
            "status": "running",
            "working_dir": working_dir,
            "created_at": time.time(),
        }

        # Install packages if specified
        if config.packages:
            await self._install_packages(instance_id, config.packages)

        info = InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"local://{working_dir}",
            provider="local",
            created_at=time.time(),
        )
        logger.info("[local_compute] provisioned: %s at %s", instance_id, working_dir)
        return info

    async def shutdown(self, instance_id: str) -> None:
        if instance_id in self._instances:
            self._instances[instance_id]["status"] = "stopped"
            logger.info("[local_compute] shutdown: %s", instance_id)

    async def get_status(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        inst = self._instances.get(instance_id)
        if not inst:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="local",
            )
        status_map = {
            "running": InstanceStatus.RUNNING,
            "stopped": InstanceStatus.STOPPED,
        }
        return InstanceInfo(
            instance_id=instance_id,
            status=status_map.get(inst["status"], InstanceStatus.ERROR),
            endpoint=f"local://{inst['working_dir']}",
            provider="local",
            created_at=inst.get("created_at", 0),
        )

    async def execute(
        self,
        instance_id: str,
        command: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        inst = self._instances.get(instance_id)
        if not inst or inst["status"] != "running":
            return {"stdout": "", "stderr": "Instance not running", "exit_code": -1}

        cwd = inst["working_dir"]
        env = {**os.environ, **inst["config"].env}

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"stdout": "", "stderr": "Timeout", "exit_code": -1}

        return {
            "stdout": stdout.decode(errors="replace") if stdout else "",
            "stderr": stderr.decode(errors="replace") if stderr else "",
            "exit_code": proc.returncode or 0,
        }

    async def upload_file(
        self, instance_id: str, local_path: str, remote_path: str,
    ) -> bool:
        import shutil
        try:
            shutil.copy2(local_path, remote_path)
            return True
        except Exception as e:
            logger.error("[local_compute] upload failed: %s", e)
            return False

    async def download_file(
        self, instance_id: str, remote_path: str, local_path: str,
    ) -> bool:
        import shutil
        try:
            shutil.copy2(remote_path, local_path)
            return True
        except Exception as e:
            logger.error("[local_compute] download failed: %s", e)
            return False

    async def list_instances(self) -> list:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = []
        for iid, inst in self._instances.items():
            if inst["status"] == "running":
                result.append(InstanceInfo(
                    instance_id=iid,
                    status=InstanceStatus.RUNNING,
                    endpoint=f"local://{inst['working_dir']}",
                    provider="local",
                    created_at=inst.get("created_at", 0),
                ))
        return result

    async def _install_packages(self, instance_id: str, packages: Dict[str, list]) -> None:
        import sys

        pip_pkgs = packages.get("pip", [])
        if pip_pkgs:
            cmd = f"{sys.executable} -m pip install -q {' '.join(pip_pkgs)}"
            result = await self.execute(instance_id, cmd, timeout=120)
            if result["exit_code"] != 0:
                logger.warning("[local_compute] pip install failed: %s", result["stderr"])
