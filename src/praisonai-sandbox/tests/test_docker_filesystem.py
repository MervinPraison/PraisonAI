"""`run_in="docker"` had no filesystem.

write_file() wrote into a host temp directory that `docker run` never mounted,
so a write reported success, the file landed outside the container, and reading
it back failed. list_files() then reported the real host path, prefixed with
enough "../" to escape the sandbox entirely.

Both are user-visible: the first loses data silently, the second leaks where the
host keeps it.
"""

import asyncio
import shutil
import subprocess

import pytest

from praisonaiagents.sandbox import SandboxConfig, SandboxManager


def _docker_running() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, timeout=25,
        ).returncode == 0
    except Exception:
        return False


needs_docker = pytest.mark.skipif(not _docker_running(), reason="needs a Docker daemon")


def _run(coro):
    return asyncio.run(coro)


async def _with_sandbox(fn):
    sandbox = await SandboxManager(SandboxConfig(sandbox_type="docker"))._create_sandbox()
    try:
        return await fn(sandbox)
    finally:
        await sandbox.stop()


@needs_docker
def test_a_written_file_can_be_read_back():
    async def check(sandbox):
        await sandbox.write_file("data.txt", "persisted")
        return await sandbox.run_command("cat data.txt")

    result = _run(_with_sandbox(check))
    assert result.exit_code == 0, "the file was written outside the container"
    assert (result.stdout or "").strip() == "persisted"


@needs_docker
def test_a_file_survives_between_commands():
    """Each command gets a fresh --rm container, so persistence comes entirely
    from the mounted directory."""

    async def check(sandbox):
        await sandbox.run_command("echo between > p.txt", shell=True)
        return await sandbox.run_command("cat p.txt", shell=True)

    result = _run(_with_sandbox(check))
    assert (result.stdout or "").strip() == "between"


@needs_docker
def test_listing_files_does_not_reveal_the_host_path():
    """On macOS the sandbox dir is /var/folders/... while os.walk reports
    /private/var/folders/... -- /var is a symlink -- so the relative path
    computation escaped upward and returned the real host location."""

    async def check(sandbox):
        await sandbox.write_file("a.txt", "x")
        await sandbox.write_file("sub/b.txt", "y")
        return await sandbox.list_files("/")

    listed = _run(_with_sandbox(check))
    assert sorted(listed) == ["/a.txt", "/sub/b.txt"]
    for entry in listed:
        assert ".." not in entry, f"{entry} escapes the sandbox root"
        assert "private/var" not in entry, f"{entry} leaks the host path"


@needs_docker
def test_the_container_is_still_isolated_from_the_host():
    """Mounting one directory must not turn into mounting the host."""

    async def check(sandbox):
        return await sandbox.run_command("ls /Users", shell=True)

    result = _run(_with_sandbox(check))
    assert result.exit_code != 0, "the host filesystem is visible inside the container"
