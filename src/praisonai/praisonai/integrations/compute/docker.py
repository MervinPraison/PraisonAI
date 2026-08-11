"""
Docker Compute Provider — container-based compute for managed agents.

Uses the Docker Python SDK to provision isolated containers for agent
sandbox execution. Supports auto-shutdown after idle timeout.

Requires: ``pip install docker``
"""

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Local image namespace for post-setup captures (``docker commit``).
_CAPTURE_IMAGE = "praisonai-env"

# Registry bookkeeping: {definition_hash: {backend, ref, created_at, last_used}}
_REGISTRY_DIR = os.path.join(
    os.path.expanduser("~"), ".praisonai", "environments"
)
_REGISTRY_PATH = os.path.join(_REGISTRY_DIR, "registry.json")

# Age-based GC default: entries unused for this long are prunable.
_DEFAULT_MAX_AGE_S = 14 * 24 * 3600


def _load_registry() -> Dict[str, Dict[str, Any]]:
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_registry(registry: Dict[str, Dict[str, Any]]) -> None:
    try:
        os.makedirs(_REGISTRY_DIR, exist_ok=True)
        tmp = f"{_REGISTRY_PATH}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, sort_keys=True)
        os.replace(tmp, _REGISTRY_PATH)
    except OSError as e:
        logger.warning("[docker_compute] could not write env registry: %s", e)


@contextlib.contextmanager
def _registry_lock() -> Iterator[None]:
    """Best-effort cross-process advisory lock around the registry file.

    Serialises the load→mutate→save cycle so concurrent provisions don't drop
    each other's entries (lost update). Uses ``fcntl`` where available (POSIX)
    and silently degrades to a no-op elsewhere (e.g. Windows) — captures still
    work, just without the guarantee under heavy concurrency.
    """
    try:
        import fcntl  # POSIX only
    except ImportError:
        yield
        return

    try:
        os.makedirs(_REGISTRY_DIR, exist_ok=True)
    except OSError:
        yield
        return

    lock_path = f"{_REGISTRY_PATH}.lock"
    fh = None
    try:
        fh = open(lock_path, "w", encoding="utf-8")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    except OSError as e:
        logger.debug("[docker_compute] registry lock unavailable: %s", e)
        yield
    finally:
        if fh is not None:
            with contextlib.suppress(Exception):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


def _update_registry(
    mutate: Callable[[Dict[str, Dict[str, Any]]], None],
) -> None:
    """Atomically read-modify-write the registry under the file lock.

    ``mutate`` receives the freshest registry dict and edits it in place, so an
    entry written by a concurrent provision is preserved rather than clobbered.
    """
    with _registry_lock():
        registry = _load_registry()
        mutate(registry)
        _save_registry(registry)


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
        from praisonaiagents.managed.protocols import (
            InstanceInfo,
            InstanceStatus,
            capture_key,
            definition_hash,
        )

        client = self._get_client()
        instance_id = f"docker_{uuid.uuid4().hex[:12]}"

        # Build environment
        env = dict(config.env)

        # Resource limits
        mem_limit = f"{config.memory_mb}m"
        cpu_count = config.cpu

        # Capture reuse: if a prior provision of this exact definition was
        # committed to a local image, start from it and skip pull+install+setup.
        # A hit is only worthwhile when there is setup to amortise; a change to
        # the definition yields a new key → miss → fresh build + new capture.
        #
        # The reuse key is ``capture_key`` (binds env *values*), NOT the
        # value-free ``definition_hash``: ``setup:`` runs with env values
        # injected and may bake secret-derived state into the filesystem, so a
        # capture must not be shared across differing secrets. ``definition_hash``
        # is kept only as a non-sensitive display label in the registry.
        cap_key = capture_key(config)
        defn_hash = definition_hash(config)
        capture_ref = self._capture_tag(cap_key)
        from_capture = bool(config.setup or config.packages) and self.has_capture(
            capture_ref
        )
        base_image = capture_ref if from_capture else config.image

        # Pull base image if needed (captures are always local — never pulled).
        if not from_capture:
            try:
                client.images.get(base_image)
            except Exception:
                logger.info("[docker_compute] pulling image: %s", base_image)
                client.images.pull(base_image)

        # Create and start container
        container = client.containers.run(
            base_image,
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

        # Install packages / run setup. If either fails, tear down the
        # just-started container so we don't leak an unreachable
        # ``sleep infinity`` container + registry entry (the caller never
        # receives an instance_id on failure).
        try:
            if from_capture:
                # Capture already has packages+setup baked in. Run only the
                # cheap incremental ``refresh:`` step (e.g. ``pip install -e .``)
                # to pick up code changes, if declared.
                refresh = getattr(config, "metadata", {}).get("refresh") or []
                if isinstance(refresh, str):
                    refresh = [refresh]
                if refresh:
                    self._run_setup_sync(container, refresh)
                self._touch_capture(cap_key)
            else:
                if config.packages:
                    self._install_packages_sync(container, config.packages)

                # Run setup commands once, after provision, before agent work
                setup = getattr(config, "setup", None)
                if setup:
                    self._run_setup_sync(container, setup)
        except Exception:
            self._containers.pop(instance_id, None)
            try:
                container.remove(force=True)
            except Exception as cleanup_err:
                logger.warning(
                    "[docker_compute] cleanup after failed provision: %s",
                    cleanup_err,
                )
            raise

        # Capture-after-setup: commit the fully-prepared container to a local
        # image keyed by the definition hash, so the next provision reuses it.
        # A failed commit degrades to today's ephemeral behaviour with a log
        # line — it never blocks the run.
        if not from_capture and (config.setup or config.packages):
            self.capture(instance_id, capture_ref, definition=defn_hash)

        logger.info("[docker_compute] provisioned: %s image=%s", instance_id, base_image)

        return InstanceInfo(
            instance_id=instance_id,
            status=InstanceStatus.RUNNING,
            endpoint=f"docker://{container.id[:12]}",
            provider="docker",
            created_at=time.time(),
        )

    # ------------------------------------------------------------------
    # SupportsCapture — docker commit / reuse
    # ------------------------------------------------------------------
    @staticmethod
    def _capture_tag(defn_hash: str) -> str:
        """Local image tag a definition hash captures to."""
        return f"{_CAPTURE_IMAGE}:{defn_hash[:12]}"

    def has_capture(self, ref: str) -> bool:
        """Whether a reusable local capture image ``ref`` exists."""
        try:
            client = self._get_client()
            client.images.get(ref)
            return True
        except Exception:
            return False

    def capture(
        self, instance_id: str, ref: str, definition: Optional[str] = None,
    ) -> Optional[str]:
        """``docker commit`` ``instance_id`` to local image ``ref``.

        Records the capture in the registry. Returns the ref on success or
        ``None`` on failure (never raises) so the caller degrades to ephemeral.

        Args:
            instance_id: Container to commit.
            ref: Local image ref to commit to (``praisonai-env:{key}``); the
                ``{key}`` is a secret-aware :func:`capture_key`.
            definition: Optional non-sensitive :func:`definition_hash` recorded
                for display so ``list_captures`` can be shown without leaking the
                secret-bearing key.
        """
        info = self._containers.get(instance_id)
        if not info:
            logger.warning("[docker_compute] capture: unknown instance %s", instance_id)
            return None
        try:
            repository, _, tag = ref.partition(":")
            info["container"].commit(repository=repository, tag=tag or "latest")
        except Exception as e:
            logger.warning(
                "[docker_compute] capture failed for %s (ephemeral fallback): %s",
                instance_id, e,
            )
            return None

        cap_key = tag or "latest"
        now = time.time()

        def _mutate(registry: Dict[str, Dict[str, Any]]) -> None:
            existing = registry.get(cap_key, {})
            registry[cap_key] = {
                "backend": "docker",
                "ref": ref,
                "definition": definition or existing.get("definition"),
                "created_at": existing.get("created_at", now),
                "last_used": now,
            }

        _update_registry(_mutate)
        logger.info("[docker_compute] captured %s -> %s", instance_id, ref)
        return ref

    def _touch_capture(self, cap_key: str) -> None:
        """Update ``last_used`` for a capture that was just reused."""
        def _mutate(registry: Dict[str, Dict[str, Any]]) -> None:
            entry = registry.get(cap_key[:12])
            if entry:
                entry["last_used"] = time.time()

        _update_registry(_mutate)

    def list_captures(self) -> List[Dict[str, Any]]:
        """Return recorded captures ``[{hash, backend, ref, created_at, last_used}]``."""
        return [
            {"hash": h, **meta} for h, meta in sorted(_load_registry().items())
        ]

    def prune_captures(self, max_age_s: int = _DEFAULT_MAX_AGE_S) -> List[str]:
        """Remove captures unused for longer than ``max_age_s``.

        Deletes the local docker image and drops the registry entry. Returns the
        list of pruned definition hashes.
        """
        now = time.time()
        pruned: List[str] = []
        refs: List[str] = []

        # Select + drop stale entries atomically under the lock so a concurrent
        # capture writer is preserved. Image deletion (slow, external) happens
        # afterwards, outside the lock.
        def _mutate(registry: Dict[str, Dict[str, Any]]) -> None:
            for defn_hash, meta in list(registry.items()):
                if now - meta.get("last_used", 0) < max_age_s:
                    continue
                ref = meta.get("ref")
                if ref:
                    refs.append(ref)
                registry.pop(defn_hash, None)
                pruned.append(defn_hash)

        _update_registry(_mutate)

        for ref in refs:
            try:
                self._get_client().images.remove(ref, force=True)
            except Exception as e:
                logger.debug("[docker_compute] prune image %s: %s", ref, e)

        if pruned:
            logger.info("[docker_compute] pruned %d capture(s)", len(pruned))
        return pruned

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

    def _run_setup_sync(self, container, setup: list) -> None:
        """Run environment ``setup`` commands once, streaming output to logs.

        A failing command is reported (not silently swallowed) and halts the
        remaining setup so the failure surfaces to the caller.
        """
        for cmd in setup:
            logger.info("[docker_compute] setup: %s", cmd)
            exit_code, output = container.exec_run(["sh", "-c", cmd])
            if output:
                logger.info(
                    "[docker_compute] setup output:\n%s",
                    output.decode("utf-8", "replace")
                    if isinstance(output, bytes) else output,
                )
            if exit_code != 0:
                raise RuntimeError(
                    f"[docker_compute] setup command failed (exit {exit_code}): {cmd}"
                )
