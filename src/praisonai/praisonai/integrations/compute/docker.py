"""
Docker Compute Provider — container-based compute for managed agents.

Uses the Docker Python SDK to provision isolated containers for agent
sandbox execution. Supports auto-shutdown after idle timeout.

Requires: ``pip install docker``
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)


class DockerCompute:
    """Docker container-based compute provider.

    Satisfies ``ComputeProviderProtocol`` (Core SDK).
    Requires Docker daemon running and ``docker`` Python package installed.

    Example::

        from praisonaiagents.managed import ComputeConfig
        from praisonai.integrations.compute import DockerCompute

        compute = DockerCompute()
        config = ComputeConfig(
            image="python:3.12-slim",
            packages={"pip": ["pandas"]},
            auto_shutdown=True,
        )
        info = await compute.provision(config)
        result = await compute.execute(info.instance_id, "python -c 'import pandas; print(pandas.__version__)'")
        await compute.shutdown(info.instance_id)
    """

    def __init__(self) -> None:
        self._client = None
        self._containers: Dict[str, Dict[str, Any]] = {}

    def _get_client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except ImportError:
                raise ImportError(
                    "Docker Python SDK required. Install with: pip install docker"
                )
            except Exception as e:
                raise RuntimeError(f"Cannot connect to Docker daemon: {e}")
        return self._client

    @property
    def provider_name(self) -> str:
        return "docker"

    @property
    def is_available(self) -> bool:
        try:
            client = self._get_client()
            client.ping()
            return True
        except Exception:
            return False

    async def provision(self, config) -> Any:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, self._provision_sync, config)
        return info

    def _provision_sync(self, config) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        client = self._get_client()
        instance_id = f"docker_{uuid.uuid4().hex[:12]}"

        # Build environment
        env = dict(config.env)

        # Resource limits
        mem_limit = f"{config.memory_mb}m"
        cpu_count = config.cpu

        # Pull image if needed
        try:
            client.images.get(config.image)
        except Exception:
            logger.info("[docker_compute] pulling image: %s", config.image)
            client.images.pull(config.image)

        # Create and start container
        container = client.containers.run(
            config.image,
            command="sleep infinity",
            detach=True,
            name=f"praisonai_{instance_id}",
            environment=env,
            working_dir=config.working_dir,
            mem_limit=mem_limit,
            nano_cpus=int(cpu_count * 1e9),
            remove=False,
            labels={"praisonai": "managed", "instance_id": instance_id},
        )

        self._containers[instance_id] = {
            "container": container,
            "config": config,
            "created_at": time.time(),
        }

        # Install packages
        if config.packages:
            self._install_packages_sync(container, config.packages)

        logger.info("[docker_compute] provisioned: %s image=%s", instance_id, config.image)

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"docker://{container.id[:12]}",
            provider="docker",
            created_at=time.time(),
        )

    async def shutdown(self, instance_id: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._shutdown_sync, instance_id)

    def _shutdown_sync(self, instance_id: str) -> None:
        info = self._containers.pop(instance_id, None)
        if info:
            container = info["container"]
            try:
                container.stop(timeout=10)
                if info["config"].auto_shutdown:
                    container.remove(force=True)
            except Exception as e:
                logger.warning("[docker_compute] shutdown error: %s", e)
            logger.info("[docker_compute] shutdown: %s", instance_id)

    async def get_status(self, instance_id: str) -> Any:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        info = self._containers.get(instance_id)
        if not info:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.STOPPED,
                provider="docker",
            )

        try:
            info["container"].reload()
            docker_status = info["container"].status
            status_map = {
                "running": InstanceStatus.RUNNING,
                "created": InstanceStatus.PROVISIONING,
                "exited": InstanceStatus.STOPPED,
                "dead": InstanceStatus.ERROR,
            }
            return InstanceInfo(
                instance_id=instance_id,
                status=status_map.get(docker_status, InstanceStatus.ERROR),
                endpoint=f"docker://{info['container'].id[:12]}",
                provider="docker",
                created_at=info.get("created_at", 0),
            )
        except Exception:
            return InstanceInfo(
                instance_id=instance_id,
                status=InstanceStatus.ERROR,
                provider="docker",
            )

    async def execute(
        self,
        instance_id: str,
        command: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._execute_sync, instance_id, command, timeout,
        )

    def _execute_sync(
        self, instance_id: str, command: str, timeout: int,
    ) -> Dict[str, Any]:
        info = self._containers.get(instance_id)
        if not info:
            return {"stdout": "", "stderr": "Instance not found", "exit_code": -1}

        container = info["container"]
        try:
            exit_code, output = container.exec_run(
                ["sh", "-c", command],
                workdir=info["config"].working_dir,
                demux=True,
            )
            stdout = output[0].decode(errors="replace") if output and output[0] else ""
            stderr = output[1].decode(errors="replace") if output and output[1] else ""
            return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "exit_code": -1}

    async def upload_file(
        self, instance_id: str, local_path: str, remote_path: str,
    ) -> bool:
        import tarfile
        import io
        import os

        info = self._containers.get(instance_id)
        if not info:
            return False

        try:
            with open(local_path, "rb") as f:
                data = f.read()

            tar_stream = io.BytesIO()
            tar_info = tarfile.TarInfo(name=os.path.basename(remote_path))
            tar_info.size = len(data)
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                tar.addfile(tar_info, io.BytesIO(data))
            tar_stream.seek(0)

            dest_dir = os.path.dirname(remote_path) or "/"
            info["container"].put_archive(dest_dir, tar_stream)
            return True
        except Exception as e:
            logger.error("[docker_compute] upload failed: %s", e)
            return False

    async def download_file(
        self, instance_id: str, remote_path: str, local_path: str,
    ) -> bool:
        import tarfile
        import io

        info = self._containers.get(instance_id)
        if not info:
            return False

        try:
            bits, _ = info["container"].get_archive(remote_path)
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)

            with tarfile.open(fileobj=tar_stream) as tar:
                for member in tar.getmembers():
                    f = tar.extractfile(member)
                    if f:
                        with open(local_path, "wb") as out:
                            out.write(f.read())
                        return True
            return False
        except Exception as e:
            logger.error("[docker_compute] download failed: %s", e)
            return False

    async def list_instances(self) -> list:
        from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

        result = []
        for iid, info in self._containers.items():
            try:
                info["container"].reload()
                if info["container"].status == "running":
                    result.append(InstanceInfo(
                        instance_id=iid,
                        status=InstanceStatus.RUNNING,
                        endpoint=f"docker://{info['container'].id[:12]}",
                        provider="docker",
                        created_at=info.get("created_at", 0),
                    ))
            except Exception:
                pass
        return result

    def _install_packages_sync(self, container, packages: Dict[str, list]) -> None:
        pip_pkgs = packages.get("pip", [])
        if pip_pkgs:
            cmd = f"pip install -q {' '.join(pip_pkgs)}"
            logger.info("[docker_compute] installing pip packages: %s", pip_pkgs)
            exit_code, output = container.exec_run(["sh", "-c", cmd])
            if exit_code != 0:
                logger.warning("[docker_compute] pip install failed: %s", output)

        apt_pkgs = packages.get("apt", [])
        if apt_pkgs:
            cmd = f"apt-get update -qq && apt-get install -y -qq {' '.join(apt_pkgs)}"
            logger.info("[docker_compute] installing apt packages: %s", apt_pkgs)
            exit_code, output = container.exec_run(["sh", "-c", cmd])
            if exit_code != 0:
                logger.warning("[docker_compute] apt install failed: %s", output)

        npm_pkgs = packages.get("npm", [])
        if npm_pkgs:
            cmd = f"npm install -g {' '.join(npm_pkgs)}"
            logger.info("[docker_compute] installing npm packages: %s", npm_pkgs)
            exit_code, output = container.exec_run(["sh", "-c", cmd])
            if exit_code != 0:
                logger.warning("[docker_compute] npm install failed: %s", output)
