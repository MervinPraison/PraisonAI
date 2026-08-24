"""
Docker Sandbox implementation for PraisonAI.

Provides isolated code execution in Docker containers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from praisonaiagents.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxStatus,
    ResourceLimits,
)
from praisonaiagents.sandbox.config import SecurityPolicy

logger = logging.getLogger(__name__)

#: Where the sandbox's directory appears inside the container. Files written
#: with write_file() land here, and commands run here by default, so a write
#: followed by a read sees the same file -- and so does the next command.
SANDBOX_ROOT = "/sandbox"

#: Lowest pids cap a container can run a shell under. Below roughly this,
#: `docker run` dies before the command starts rather than limiting it.
MIN_CONTAINER_PIDS = 128



def _sandbox_relative(path: str) -> str:
    """Accept both spellings of a sandbox path.

    The directory is mounted at SANDBOX_ROOT, so that is the path a user sees
    from inside the container and the one they naturally type. But the file API
    treats "/" as the sandbox root, so "/sandbox/report.txt" was joined onto the
    root again and landed at "/sandbox/sandbox/report.txt" -- write_file
    returned True, and `cat /sandbox/report.txt` could not find it.

    Both spellings now mean the same file. Only the exact prefix is stripped, so
    a genuine subdirectory that happens to be called "sandbox" still works.
    """
    if path == SANDBOX_ROOT:
        return "/"
    prefix = SANDBOX_ROOT + "/"
    if path.startswith(prefix):
        return "/" + path[len(prefix):]
    return path

class DockerSandbox:
    """Docker-based sandbox for safe code execution.
    
    Executes code in isolated Docker containers with resource limits
    and security policies.
    
    Example:
        from praisonai_sandbox import DockerSandbox
        
        sandbox = DockerSandbox(image="python:3.12-slim")
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    
    Requires: Docker installed and running
    """
    
    def __init__(
        self,
        # Kept in step with the compute-side DockerCompute default. The two
        # implementations of "docker" disagreed -- 3.11 here, 3.12 there -- so
        # tools_run_on="docker" and run_in="docker" handed you different
        # Pythons for the same word. Nobody chose that; they drifted.
        image: str = "python:3.12-slim",
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the Docker sandbox.
        
        Args:
            image: Docker image to use
            config: Optional sandbox configuration
        """
        self.config = config or SandboxConfig.docker(image)
        self._image = image
        self._container_id: Optional[str] = None
        self._is_running = False
        self._temp_dir: Optional[str] = None

    def _validate_command_against_policy(
        self,
        cmd: List[str],
        policy: SecurityPolicy,
    ) -> Optional[str]:
        """Return an error message when *cmd* violates *policy*.

        Mirrors SubprocessSandbox: the container bounds *where* code runs, but
        command-level clauses (blocked_commands, allowed_commands, blocked_paths)
        must still be enforced before dispatch. allowed_commands in particular
        has no container analogue -- it is the only way a user can say "this
        sandbox may only run python".
        """
        if not cmd:
            return "Empty command"

        from ._shell import policy_scan_parts, strip_heredoc_bodies

        cmd_str = strip_heredoc_bodies(" ".join(cmd))
        for blocked in policy.blocked_commands:
            if blocked and blocked in cmd_str:
                return f"Blocked command pattern: {blocked}"

        if policy.allowed_commands:
            base_cmd = os.path.basename(cmd[0])
            allowed = {c.split()[0] for c in policy.allowed_commands}
            if base_cmd not in allowed and cmd[0] not in policy.allowed_commands:
                return f"Command not in allowlist: {base_cmd}"

        for part in policy_scan_parts([strip_heredoc_bodies(c) for c in cmd]):
            if not part.startswith(("/", "~", ".")):
                continue
            expanded = os.path.realpath(os.path.expanduser(part))
            for blocked_path in policy.blocked_paths:
                blocked_abs = os.path.realpath(os.path.expanduser(blocked_path))
                if expanded == blocked_abs or expanded.startswith(blocked_abs + os.sep):
                    return f"Access to blocked path: {blocked_path}"
        return None

    def _truncate_output(self, data: bytes) -> bytes:
        """Bound host-side buffered output to the policy's max_output_size.

        communicate() buffers whatever the container prints on the HOST, so an
        unbounded print in sandboxed code exhausts the host process -- the very
        thing the limit exists to contain. Mirrors subprocess.py.
        """
        max_output_size = self.config.security_policy.max_output_size
        if max_output_size and max_output_size > 0 and len(data) > max_output_size:
            return data[:max_output_size] + b"\n[OUTPUT TRUNCATED]"
        return data

    @property
    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @property
    def sandbox_type(self) -> str:
        return "docker"
    
    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        if self._is_running:
            return
        
        if not self.is_available:
            raise RuntimeError("Docker is not available")
        
        self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandbox_")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "pull", self._image,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        except Exception as e:
            logger.warning(f"Failed to pull image: {e}")
        
        self._is_running = True
        logger.info(f"Docker sandbox initialized with image: {self._image}")
    
    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        if not self._is_running:
            return
        
        if self._container_id:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", self._container_id,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            except Exception as e:
                logger.warning(f"Failed to remove container: {e}")
            self._container_id = None
        
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        
        self._is_running = False
        logger.info("Docker sandbox stopped")
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Execute code in the sandbox."""
        if not self._is_running:
            await self.start()
        
        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())
        
        # Drop the script inside the mounted sandbox dir rather than a private
        # /code mount. That way execute() sees files written by write_file() or
        # a prior run_command(), and anything it writes survives for the next
        # call -- the same shared storage every entry point already uses.
        script_name = f"code_{execution_id}.py"
        code_file = os.path.join(self._temp_dir, script_name)
        with open(code_file, "w") as f:
            f.write(code)
        
        container_name = f"praisonai-{execution_id}"
        docker_cmd = self._build_docker_command(
            script_name=script_name,
            language=language,
            limits=limits,
            env=env,
            working_dir=working_dir,
            container_name=container_name,
        )
        
        started_at = time.time()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds,
                )
                
                completed_at = time.time()

                stdout = self._truncate_output(stdout)
                stderr = self._truncate_output(stderr)

                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.COMPLETED,
                    exit_code=proc.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_seconds=completed_at - started_at,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            except asyncio.TimeoutError:
                # Kill the container, not just the client. proc.kill() ends the
                # docker CLI while the container it started keeps running,
                # unnamed and unreachable.
                try:
                    killer = await asyncio.create_subprocess_exec(
                        "docker", "kill", container_name,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await killer.wait()
                except Exception:  # pragma: no cover - best effort teardown
                    logger.warning("Could not kill container %s", container_name)
                proc.kill()
                await proc.wait()

                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.TIMEOUT,
                    error=f"Execution timed out after {limits.timeout_seconds}s",
                    duration_seconds=limits.timeout_seconds,
                    started_at=started_at,
                    completed_at=time.time(),
                )
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
        finally:
            if os.path.exists(code_file):
                os.remove(code_file)
    
    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a file in the sandbox."""
        if not os.path.exists(file_path):
            return SandboxResult(
                status=SandboxStatus.FAILED,
                error=f"File not found: {file_path}",
            )
        
        with open(file_path, "r") as f:
            code = f.read()
        
        return await self.execute(code, limits=limits, env=env)
    
    async def run_command(
        self,
        command: Union[str, List[str]],
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
        shell: bool = False,
    ) -> SandboxResult:
        """Run a command in the sandbox.
        
        Args:
            command: String command or list of arguments
            limits: Resource limits to apply
            env: Environment variables
            working_dir: Working directory
            shell: If True, explicitly use shell. If False (default), execute safely without shell.
        """
        if not self._is_running:
            await self.start()
        
        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())
        
        if isinstance(command, list):
            # Always quote list elements to prevent shell injection
            cmd_parts = list(command)
            cmd_str = " ".join(shlex.quote(arg) for arg in command)
        else:
            if shell:
                # Caller explicitly requested shell evaluation
                cmd_parts = ["sh", "-c", command]
                cmd_str = command
            else:
                # Parse string safely then re-quote each part
                cmd_parts = shlex.split(command)
                cmd_str = " ".join(shlex.quote(part) for part in cmd_parts)

        # Enforce the command-level security policy before dispatch. The
        # container bounds where code runs, but allowlisting, blocked commands
        # and blocked paths have to be checked here -- the same enforcement
        # SubprocessSandbox already applies.
        policy_error = self._validate_command_against_policy(
            cmd_parts, self.config.security_policy
        )
        if policy_error:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=policy_error,
            )

        # Generate container name for timeout cleanup
        container_name = f"praisonai-{execution_id}"
        
        # Mount the sandbox directory. write_file() writes into self._temp_dir
        # on the HOST, and `docker run` never mounted it -- so a write reported
        # success, the file landed outside the container, and reading it back
        # failed. Nothing carried between commands either, because each one got
        # a fresh --rm container with no shared storage.
        docker_cmd = [
            "docker", "run", "--rm", "--name", container_name,
            "-v", f"{self._temp_dir}:{SANDBOX_ROOT}",
            "-w", SANDBOX_ROOT,
            "--memory", f"{limits.memory_mb}m",
            "--cpus", str(limits.cpu_percent / 100),
        ]

        # max_processes was accepted and ignored here while the other execution
        # path applied it, so a fork bomb ran unbounded through the bridged
        # execute_command tool. Docker enforces pids per CONTAINER, so unlike
        # setrlimit's per-user RLIMIT_NPROC it means what it says.
        #
        # The floor matters though. max_processes defaults to 10, a number
        # chosen for the rlimit world, and `--pids-limit 10` kills the
        # container before the shell finishes starting -- `docker run` exits
        # 125 with "No such container". A shell, its pipeline and the command
        # itself need more than that, so the cap is raised to something a
        # container can actually live within. It still bounds a fork bomb,
        # which is the point; it just stops the bound from being the bug.
        if limits.max_processes and limits.max_processes > 0:
            pids = max(limits.max_processes, MIN_CONTAINER_PIDS)
            docker_cmd.extend(["--pids-limit", str(pids)])
        
        if not limits.network_enabled:
            docker_cmd.extend(["--network", "none"])
        
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        if working_dir and working_dir != SANDBOX_ROOT:
            docker_cmd.extend(["-w", working_dir])
        
        docker_cmd.extend([self._image, "sh", "-c", cmd_str])
        
        started_at = time.time()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds,
                )
                
                completed_at = time.time()

                stdout = self._truncate_output(stdout)
                stderr = self._truncate_output(stderr)

                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.COMPLETED,
                    exit_code=proc.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_seconds=completed_at - started_at,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            except asyncio.TimeoutError:
                # Kill the container, not just the client
                try:
                    kill_proc = await asyncio.create_subprocess_exec(
                        "docker", "kill", container_name,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await kill_proc.wait()
                except Exception:
                    pass  # Container may already be gone
                
                proc.kill()
                await proc.wait()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.TIMEOUT,
                    error=f"Command timed out after {limits.timeout_seconds}s",
                    duration_seconds=limits.timeout_seconds,
                    started_at=started_at,
                    completed_at=time.time(),
                )
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
    
    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file to the sandbox.

        Opened through open_in_sandbox rather than by path string: the sandbox
        directory is bind-mounted into the container, so anything that
        validates a name and then re-opens it can be raced by code inside.
        """
        from ._compat import makedirs_in_sandbox, open_in_sandbox

        path = _sandbox_relative(path)

        if not makedirs_in_sandbox(self._temp_dir, path):
            return False

        payload = content if isinstance(content, bytes) else content.encode()
        fd = open_in_sandbox(
            self._temp_dir, path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        )
        if fd is None:
            return False
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            return True
        except OSError as exc:
            logger.warning("Failed to write %s in sandbox: %s", path, exc)
            return False

    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file from the sandbox.

        Symlink-proof for the same reason as write_file: a name validated a
        moment ago can point somewhere else by the time it is opened.
        """
        from ._compat import open_in_sandbox

        fd = open_in_sandbox(self._temp_dir, _sandbox_relative(path), os.O_RDONLY)
        if fd is None:
            return None
        try:
            with os.fdopen(fd, "rb") as handle:
                raw = handle.read()
        except OSError:
            return None
        try:
            return raw.decode()
        except UnicodeDecodeError:
            return raw

    async def list_files(
        self,
        path: str = "/",
    ) -> List[str]:
        """List files in a sandbox directory."""
        from ._compat import safe_sandbox_path

        full_path = safe_sandbox_path(self._temp_dir, _sandbox_relative(path))
        if full_path is None or not os.path.exists(full_path):
            return []
        
        try:
            # Resolve both sides before comparing. On macOS the sandbox dir
            # comes back as /var/folders/... while os.walk reports
            # /private/var/folders/... -- /var being a symlink -- so relpath
            # produced "../../../../../../private/var/..." and leaked the real
            # host path to the caller instead of a sandbox-relative one.
            root_dir = os.path.realpath(self._temp_dir)
            files = []
            for root, dirs, filenames in os.walk(os.path.realpath(full_path)):
                for filename in filenames:
                    rel_path = os.path.relpath(
                        os.path.join(root, filename),
                        root_dir,
                    )
                    if rel_path.startswith(".."):
                        continue          # outside the sandbox; never report it
                    files.append("/" + rel_path)
            return files
        except Exception:
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get sandbox status information."""
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "image": self._image,
            "container_id": self._container_id,
            "temp_dir": self._temp_dir,
        }
    
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandbox_")
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        await self.stop()
        await self.start()
    
    def _build_docker_command(
        self,
        script_name: str,
        language: str,
        limits: ResourceLimits,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
        container_name: str = "",
    ) -> List[str]:
        """Build the Docker run command.

        The script lives in the mounted sandbox dir (SANDBOX_ROOT), so execute()
        shares the same storage as write_file() and run_command().
        """
        # Named so a timeout can kill the container by name rather than just the
        # docker client -- without --name a timed-out run left a container with a
        # random Docker name that nothing could reach. Labelled `praisonai=sandbox-exec`,
        # deliberately NOT `praisonai=managed`: these are ephemeral per-execution
        # `--rm` containers, not managed instances, and `praisonai=managed` is the
        # sole input to DockerCompute.list_instances(). Tagging them managed made
        # `praisonai managed ps` list a `praisonai-<uuid>` name that `managed stop`
        # (which resolves `praisonai_<id>`) could never reclaim.
        docker_cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--label", "praisonai=sandbox-exec",
            "-v", f"{self._temp_dir}:{SANDBOX_ROOT}",
            "--memory", f"{limits.memory_mb}m",
            "--cpus", str(limits.cpu_percent / 100),
        ]

        # Same floor as run_command(): --pids-limit is per CONTAINER, and the
        # default max_processes of 10 was chosen for setrlimit's per-user world.
        # A raw 10 here kills the container before python even starts (exit 125),
        # so raise it to something a container can live within. Still bounds a
        # fork bomb; just stops the bound from being the bug.
        if limits.max_processes and limits.max_processes > 0:
            docker_cmd.extend(
                ["--pids-limit", str(max(limits.max_processes, MIN_CONTAINER_PIDS))]
            )
        
        if not limits.network_enabled:
            docker_cmd.extend(["--network", "none"])
        
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        docker_cmd.extend(["-w", working_dir or SANDBOX_ROOT])
        
        docker_cmd.append(self._image)
        
        script_path = f"{SANDBOX_ROOT}/{script_name}"
        if language == "bash":
            docker_cmd.extend(["bash", script_path])
        else:
            docker_cmd.extend(["python", script_path])
        
        return docker_cmd
