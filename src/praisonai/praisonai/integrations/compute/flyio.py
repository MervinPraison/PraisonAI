"""
Fly.io Compute Provider — Machines-based compute for managed agents.

Uses Fly.io Machines API to provision containers with fast start/stop
and per-second billing. Ideal for auto-shutdown after work completes.

Requires: ``FLY_API_TOKEN`` environment variable.

Fly.io Machines API:
- Start in <3s, stop instantly
- Pay only while running (per-second billing)
- GPU support available
- Built-in regions worldwide
"""

import logging
import os
import time
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)

FLY_API_BASE = "https://api.machines.dev/v1"


class FlyioCompute:
    """Fly.io Machines-based compute provider.

    Satisfies ``ComputeProviderProtocol`` (Core SDK).
    Uses the Fly.io Machines REST API for container management.

    Environment variables:
    - ``FLY_API_TOKEN`` — Fly.io API token (required)
    - ``FLY_APP_NAME`` — Fly.io app name (optional, defaults to auto-create)

    Example::

        from praisonaiagents.managed import ComputeConfig
        from praisonai.integrations.compute.flyio import FlyioCompute

        compute = FlyioCompute()
        config = ComputeConfig(
            image="python:3.12-slim",
            cpu=2,
            memory_mb=2048,
            packages={"pip": ["pandas"]},
            auto_shutdown=True,
            idle_timeout_s=300,
        )
        info = await compute.provision(config)
        result = await compute.execute(info.instance_id, "python -c 'print(1+1)'")
        await compute.shutdown(info.instance_id)
    """

    def __init__(
        self,
        api_token: str = "",
        app_name: str = "",
        region: str = "iad",
    ) -> None:
        self._api_token = api_token or os.environ.get("FLY_API_TOKEN", "")
        self._app_name = app_name or os.environ.get("FLY_APP_NAME", "")
        self._region = region
        self._machines: Dict[str, Dict[str, Any]] = {}

    @property
    def provider_name(self) -> str:
        return "flyio"

    @property
    def is_available(self) -> bool:
        return bool(self._api_token)

    async def _api_request(
        self, method: str, path: str, json_data: Any = None,
    ) -> Dict[str, Any]:
        """Make an authenticated request to the Fly.io Machines API."""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp required for Fly.io compute. Install with: pip install aiohttp")

        url = f"{FLY_API_BASE}/apps/{self._app_name}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, json=json_data, headers=headers) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.error("[flyio_compute] API error %d: %s", resp.status, body)
                    return {"error": body, "status": resp.status}
                return await resp.json()

    async def provision(self, config) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        if not self._api_token:
            raise RuntimeError("FLY_API_TOKEN not set. Get one at https://fly.io/docs/flyctl/auth-token/")

        instance_id = f"flyio_{uuid.uuid4().hex[:12]}"

        # Build machine config
        machine_config = {
            "image": config.image,
            "env": config.env,
            "guest": {
                "cpus": config.cpu,
                "memory_mb": config.memory_mb,
                "cpu_kind": "shared",
            },
            "auto_destroy": config.auto_shutdown,
            "restart": {"policy": "no"},
        }

        if config.gpu:
            machine_config["guest"]["gpus"] = [{"kind": config.gpu}]

        # Create machine
        result = await self._api_request("POST", "/machines", {
            "name": f"praisonai-{instance_id}",
            "region": self._region,
            "config": machine_config,
        })

        if "error" in result:
            raise RuntimeError(f"Fly.io provision failed: {result['error']}")

        machine_id = result.get("id", instance_id)

        self._machines[instance_id] = {
            "machine_id": machine_id,
            "config": config,
            "created_at": time.time(),
        }

        # Install packages after provisioning
        if config.packages:
            pip_pkgs = config.packages.get("pip", [])
            if pip_pkgs:
                await self.execute(instance_id, f"pip install -q {' '.join(pip_pkgs)}")

        logger.info("[flyio_compute] provisioned: %s machine=%s region=%s",
                    instance_id, machine_id, self._region)

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"flyio://{machine_id}",
            provider="flyio",
            region=self._region,
            created_at=time.time(),
        )

    async def shutdown(self, instance_id: str) -> None:
        info = self._machines.pop(instance_id, None)
        if info:
            machine_id = info["machine_id"]
            await self._api_request("POST", f"/machines/{machine_id}/stop")
            if info["config"].auto_shutdown:
                await self._api_request("DELETE", f"/machines/{machine_id}")
            logger.info("[flyio_compute] shutdown: %s", instance_id)

    async def get_status(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        info = self._machines.get(instance_id)
        if not info:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="flyio",
            )

        machine_id = info["machine_id"]
        result = await self._api_request("GET", f"/machines/{machine_id}")

        fly_status = result.get("state", "unknown")
        status_map = {
            "started": InstanceStatus.RUNNING,
            "starting": InstanceStatus.PROVISIONING,
            "stopped": InstanceStatus.STOPPED,
            "stopping": InstanceStatus.STOPPING,
            "destroyed": InstanceStatus.STOPPED,
        }

        return InstanceInfo(
            instance_id=instance_id,
            status=status_map.get(fly_status, InstanceStatus.ERROR),
            endpoint=f"flyio://{machine_id}",
            provider="flyio",
            region=self._region,
            created_at=info.get("created_at", 0),
        )

    async def execute(
        self,
        instance_id: str,
        command: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        info = self._machines.get(instance_id)
        if not info:
            return {"stdout": "", "stderr": "Instance not found", "exit_code": -1}

        machine_id = info["machine_id"]
        result = await self._api_request("POST", f"/machines/{machine_id}/exec", {
            "cmd": ["sh", "-c", command],
            "timeout": timeout,
        })

        if "error" in result:
            return {"stdout": "", "stderr": result["error"], "exit_code": -1}

        return {
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code", 0),
        }

    async def upload_file(
        self, instance_id: str, local_path: str, remote_path: str,
    ) -> bool:
        # Fly.io file upload via exec + base64
        import base64
        try:
            with open(local_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            cmd = f"echo '{data}' | base64 -d > {remote_path}"
            result = await self.execute(instance_id, cmd)
            return result["exit_code"] == 0
        except Exception as e:
            logger.error("[flyio_compute] upload failed: %s", e)
            return False

    async def download_file(
        self, instance_id: str, remote_path: str, local_path: str,
    ) -> bool:
        import base64
        try:
            result = await self.execute(instance_id, f"base64 {remote_path}")
            if result["exit_code"] != 0:
                return False
            data = base64.b64decode(result["stdout"])
            with open(local_path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            logger.error("[flyio_compute] download failed: %s", e)
            return False

    async def list_instances(self) -> list:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = await self._api_request("GET", "/machines")
        if isinstance(result, dict) and "error" in result:
            return []

        instances = []
        for machine in result if isinstance(result, list) else []:
            if machine.get("state") == "started":
                # Match against our tracked machines
                mid = machine.get("id", "")
                for iid, info in self._machines.items():
                    if info["machine_id"] == mid:
                        instances.append(InstanceInfo(
                            instance_id=iid,
                            status=InstanceStatus.RUNNING,
                            endpoint=f"flyio://{mid}",
                            provider="flyio",
                            region=machine.get("region", ""),
                            created_at=info.get("created_at", 0),
                        ))
                        break
        return instances
