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
def test_execute_shares_storage_with_write_file():
    """run_in="docker" goes through execute(), which used to mount only its own
    script under /code -- so it could not see files write_file() produced, and
    anything it wrote vanished with the container."""

    async def check(sandbox):
        await sandbox.write_file("seed.txt", "seen")
        wrote = await sandbox.execute(
            "open('/sandbox/made.txt', 'w').write(open('/sandbox/seed.txt').read())"
        )
        read_back = await sandbox.run_command("cat made.txt")
        return wrote, read_back

    wrote, read_back = _run(_with_sandbox(check))
    assert wrote.exit_code == 0, "execute() could not read the written file"
    assert (read_back.stdout or "").strip() == "seen", "execute() output did not persist"


@needs_docker
def test_the_container_is_still_isolated_from_the_host():
    """Mounting one directory must not turn into mounting the host."""

    async def check(sandbox):
        return await sandbox.run_command("ls /Users", shell=True)

    result = _run(_with_sandbox(check))
    assert result.exit_code != 0, "the host filesystem is visible inside the container"


@needs_docker
def test_both_spellings_of_a_sandbox_path_mean_the_same_file():
    """The directory is mounted at /sandbox, so that is what a user sees from
    inside the container and the one they naturally type. But the file API
    treats "/" as the sandbox root, so "/sandbox/report.txt" was joined onto
    the root again and landed at "/sandbox/sandbox/report.txt" -- write_file
    returned True and `cat /sandbox/report.txt` could not find it.
    """

    async def check(sandbox):
        await sandbox.write_file("/sandbox/report.txt", "written via the container path")
        found = await sandbox.run_command("cat /sandbox/report.txt", shell=True)

        await sandbox.run_command("echo REMOTE > /sandbox/out.txt", shell=True)
        bare = await sandbox.read_file("out.txt")
        prefixed = await sandbox.read_file("/sandbox/out.txt")
        listed = await sandbox.list_files("/sandbox")
        return found, bare, prefixed, listed

    found, bare, prefixed, listed = _run(_with_sandbox(check))
    assert found.exit_code == 0, "a file written through the container path was not there"
    assert bare == prefixed, "the two spellings disagree about the same file"
    assert sorted(listed) == ["/out.txt", "/report.txt"]


@needs_docker
def test_a_directory_genuinely_called_sandbox_still_works():
    """Only the exact mount prefix is stripped, so a real subdirectory of that
    name is not swallowed."""

    async def check(sandbox):
        await sandbox.write_file("sandbox/nested.txt", "kept")
        return await sandbox.read_file("sandbox/nested.txt"), await sandbox.list_files("/")

    content, listed = _run(_with_sandbox(check))
    assert content == "kept"
    assert "/sandbox/nested.txt" in listed


@needs_docker
def test_a_timed_out_execution_does_not_leave_a_container():
    """`proc.kill()` ends the docker CLI while the container it started keeps
    running. It had no --name either, so it got a random Docker name that
    neither the timeout handler nor `praisonai managed ps` could find."""
    import asyncio

    from praisonaiagents.sandbox import SandboxConfig

    before = subprocess.run(["docker", "ps", "-q"], capture_output=True,
                            text=True, timeout=60).stdout.split()

    config = SandboxConfig(sandbox_type="docker")
    config.resource_limits.timeout_seconds = 5

    async def run():
        sandbox = await SandboxManager(config)._create_sandbox()
        try:
            return await sandbox.execute("import time; time.sleep(300)")
        finally:
            await sandbox.stop()

    result = asyncio.run(run())
    assert result.status.name == "TIMEOUT"

    import time as _time
    _time.sleep(3)
    after = subprocess.run(["docker", "ps", "-q"], capture_output=True,
                           text=True, timeout=60).stdout.split()
    assert len(after) <= len(before), "the timed-out container is still running"
