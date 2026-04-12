"""
Modal Compute Provider — serverless sandbox-based compute for managed agents.

Uses Modal SDK for auto-scaling sandboxes with sub-second cold starts.
Supports GPU, per-second billing, and 10,000+ concurrent sandboxes.

Requires: ``pip install modal``
Authentication: ``modal token set`` or ``MODAL_TOKEN_ID`` + ``MODAL_TOKEN_SECRET``
"""

import logging
import os
import time
import uuid
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ModalCompute:
    """Modal serverless sandbox compute provider.

    Satisfies ``ComputeProviderProtocol`` (Core SDK).
    Uses Modal SDK for secure, auto-scaling sandbox environments.

    Example::

        from praisonaiagents.managed import ComputeConfig
        from praisonai.integrations.compute.modal_compute import ModalCompute

        compute = ModalCompute()
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
        app_name: str = "praisonai-compute",
    ) -> None:
        self._app_name = app_name
        self._app = None
        self._sandboxes: Dict[str, Dict[str, Any]] = {}

    def _get_app(self):
        if self._app is None:
            try:
                import modal
            except ImportError:
                raise ImportError(
                    "Modal SDK required. Install with: pip install modal"
                )
            self._app = modal.App.lookup(self._app_name, create_if_missing=True)
        return self._app

    @property
    def provider_name(self) -> str:
        return "modal"

    @property
    def is_available(self) -> bool:
        try:
            import importlib.util
            if importlib.util.find_spec("modal") is None:
                return False
            # Check if modal is configured (token exists)
            config_path = os.path.expanduser("~/.modal.toml")
            has_config = os.path.exists(config_path)
            has_env = bool(os.environ.get("MODAL_TOKEN_ID"))
            return has_config or has_env
        except Exception:
            return False

    async def provision(self, config) -> Any:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._provision_sync, config)

    def _provision_sync(self, config) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        try:
            import modal
        except ImportError:
            raise ImportError("Modal SDK required. Install with: pip install modal")

        instance_id = f"modal_{uuid.uuid4().hex[:12]}"
        app = self._get_app()

        # Build Modal Image from config
        image = modal.Image.debian_slim(python_version="3.12")

        # Install pip packages into the image
        pip_pkgs = config.packages.get("pip", []) if config.packages else []
        if pip_pkgs:
            image = image.pip_install(*pip_pkgs)

        # Install apt packages
        apt_pkgs = config.packages.get("apt", []) if config.packages else []
        if apt_pkgs:
            image = image.apt_install(*apt_pkgs)

        # Create sandbox with sleep infinity to keep it alive
        sandbox = modal.Sandbox.create(
            "sleep", "infinity",
            app=app,
            image=image,
            timeout=config.idle_timeout_s,
            secrets=[modal.Secret.from_dict(config.env)] if config.env else [],
        )

        sandbox_id = sandbox.object_id

        self._sandboxes[instance_id] = {
            "sandbox": sandbox,
            "sandbox_id": sandbox_id,
            "config": config,
            "created_at": time.time(),
        }

        logger.info("[modal_compute] provisioned: %s sandbox=%s", instance_id, sandbox_id)

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"modal://{sandbox_id}",
            provider="modal",
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
                logger.warning("[modal_compute] shutdown error: %s", e)
            logger.info("[modal_compute] shutdown: %s", instance_id)

    async def get_status(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        info = self._sandboxes.get(instance_id)
        if not info:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="modal",
            )

        try:
            rc = info["sandbox"].returncode
            # If returncode is not None, sandbox has exited
            status = InstanceStatus.STOPPED if rc is not None else InstanceStatus.RUNNING
        except Exception:
            status = InstanceStatus.RUNNING

        return InstanceInfo(
            instance_id=instance_id,
            status=status,
            endpoint=f"modal://{info['sandbox_id']}",
            provider="modal",
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
            proc = sandbox.exec("sh", "-c", command)
            stdout = proc.stdout.read()
            stderr = proc.stderr.read()
            proc.wait()
            return {
                "stdout": stdout or "",
                "stderr": stderr or "",
                "exit_code": proc.returncode or 0,
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
            import base64
            with open(local_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            proc = info["sandbox"].exec(
                "sh", "-c", f"echo '{data}' | base64 -d > {remote_path}"
            )
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            logger.error("[modal_compute] upload failed: %s", e)
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
            import base64
            proc = info["sandbox"].exec("base64", remote_path)
            stdout = proc.stdout.read()
            proc.wait()
            if proc.returncode != 0:
                return False
            data = base64.b64decode(stdout)
            with open(local_path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            logger.error("[modal_compute] download failed: %s", e)
            return False

    async def list_instances(self) -> List[Any]:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = []
        for iid, info in self._sandboxes.items():
            try:
                rc = info["sandbox"].returncode
                if rc is None:  # Still running
                    result.append(InstanceInfo(
                        instance_id=iid,
                        status=InstanceStatus.RUNNING,
                        endpoint=f"modal://{info['sandbox_id']}",
                        provider="modal",
                        created_at=info.get("created_at", 0),
                    ))
            except Exception:
                pass
        return result
