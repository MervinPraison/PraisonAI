"""The sandbox directory is bind-mounted into the container, so code inside it
can race the host's file operations.

`safe_sandbox_path()` validates a path *string*; the caller then opens that
string. Two syscalls, with a gap. That was harmless while only the host could
write to the directory. Once it is mounted, a loop of

    ln -s /etc/passwd notes.txt   /   : > notes.txt

substituted between the check and the open redirects the write. Measured before
the fix: an escape on write attempt 375, and a host secret disclosed on read
attempt 4.

No amount of stricter string checking fixes that -- anything verified before the
open can be invalidated after it. These tests pin the property that does: the
file is never re-opened by name.
"""

import os
import shutil
import subprocess

import pytest

from praisonai_sandbox._compat import (
    makedirs_in_sandbox,
    open_in_sandbox,
    safe_sandbox_path,
)


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return str(root)


def test_a_symlink_in_place_of_a_file_is_refused(sandbox, tmp_path):
    """The core of the escape: the final component becomes a symlink."""
    target = tmp_path / "outside.txt"
    target.write_text("HOST-ONLY")
    os.symlink(target, os.path.join(sandbox, "notes.txt"))

    assert open_in_sandbox(sandbox, "notes.txt", os.O_RDONLY) is None
    assert open_in_sandbox(sandbox, "notes.txt", os.O_WRONLY | os.O_CREAT) is None
    assert target.read_text() == "HOST-ONLY", "the host file was written through"


def test_a_symlinked_directory_component_is_refused(sandbox, tmp_path):
    """O_NOFOLLOW on the last component alone is not enough -- an intermediate
    directory can be swapped just as easily."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f.txt").write_text("HOST-ONLY")
    os.symlink(outside, os.path.join(sandbox, "sub"))

    assert open_in_sandbox(sandbox, "sub/f.txt", os.O_RDONLY) is None


@pytest.mark.parametrize("path", [
    "../escape.txt", "../../etc/passwd", "a/../../../etc/hosts", "/../../etc/shadow",
])
def test_climbing_out_is_refused(sandbox, path):
    assert open_in_sandbox(sandbox, path, os.O_RDONLY) is None


def test_ordinary_files_still_work(sandbox):
    """The guard must not break the thing it protects."""
    assert makedirs_in_sandbox(sandbox, "sub/deep/note.txt")
    fd = open_in_sandbox(sandbox, "sub/deep/note.txt", os.O_WRONLY | os.O_CREAT)
    assert fd is not None
    with os.fdopen(fd, "wb") as handle:
        handle.write(b"kept")

    fd = open_in_sandbox(sandbox, "sub/deep/note.txt", os.O_RDONLY)
    assert fd is not None
    with os.fdopen(fd, "rb") as handle:
        assert handle.read() == b"kept"


def test_the_string_guard_is_no_longer_load_bearing(sandbox, tmp_path):
    """safe_sandbox_path still resolves paths, and still cannot be trusted on
    its own -- it answers about a name, and names can change. This test records
    why the descriptor-based path exists rather than deleting the old helper."""
    target = tmp_path / "outside.txt"
    target.write_text("HOST-ONLY")
    link = os.path.join(sandbox, "swapped.txt")

    # a plain file: the string guard approves it
    open(link, "w").close()
    assert safe_sandbox_path(sandbox, "swapped.txt") is not None

    # ...and the moment it becomes a symlink, the same name is unsafe
    os.unlink(link)
    os.symlink(target, link)
    assert open_in_sandbox(sandbox, "swapped.txt", os.O_RDONLY) is None


# ── the container-side property, where the race actually lives ───────────────
def _docker_running() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                              capture_output=True, timeout=25).returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(not _docker_running(), reason="needs a Docker daemon")
def test_a_racing_container_cannot_reach_a_host_file(tmp_path):
    """The end-to-end version: symlink-swap from inside the container while the
    host writes. This escaped before the fix."""
    import asyncio

    from praisonaiagents.sandbox import SandboxConfig, SandboxManager

    target = tmp_path / "host_target.txt"
    target.write_text("ORIGINAL")

    async def attack():
        sandbox = await SandboxManager(SandboxConfig(sandbox_type="docker"))._create_sandbox()
        racer = (
            "for i in $(seq 1 4); do (while true; do rm -f /sandbox/n.txt; "
            f"ln -s {target} /sandbox/n.txt; rm -f /sandbox/n.txt; "
            ": > /sandbox/n.txt; done) & done; sleep 20"
        )
        task = asyncio.create_task(sandbox.run_command(racer, shell=True))
        try:
            await asyncio.sleep(1)
            for _ in range(1500):
                await sandbox.write_file("n.txt", "PWNED")
        finally:
            task.cancel()
            await sandbox.stop()

    asyncio.run(attack())
    assert target.read_text() == "ORIGINAL", "a racing container overwrote a host file"


# ── teardown must survive interpreter shutdown ───────────────────────────────
def test_offload_falls_back_when_the_executor_is_gone():
    """A sandbox is usually released by a weakref finalizer as the process
    ends. By then concurrent.futures has set its own atexit flag, so
    run_in_executor raises "cannot schedule new futures after interpreter
    shutdown" -- and that failure was swallowed and logged as a successful
    release, leaking a container on every run.

    Blocking inline is correct there: no event loop is left to starve.
    """
    import asyncio

    from praisonai_sandbox.compute._sync_base import SyncComputeProvider

    class Dying(SyncComputeProvider):
        def _shutdown_sync(self, instance_id):
            return f"released {instance_id}"

    provider = Dying()

    async def drive():
        loop = asyncio.get_running_loop()

        def refuse(*_a, **_kw):
            raise RuntimeError("cannot schedule new futures after interpreter shutdown")

        loop.run_in_executor = refuse
        return await provider.shutdown("inst-1")

    assert asyncio.run(drive()) == "released inst-1"


def test_offload_still_raises_unrelated_runtime_errors():
    """The fallback must not swallow a genuine bug."""
    import asyncio

    import pytest as _pytest

    from praisonai_sandbox.compute._sync_base import SyncComputeProvider

    class Broken(SyncComputeProvider):
        def _shutdown_sync(self, instance_id):
            return None

    provider = Broken()

    async def drive():
        loop = asyncio.get_running_loop()

        def explode(*_a, **_kw):
            raise RuntimeError("something else entirely")

        loop.run_in_executor = explode
        return await provider.shutdown("inst-1")

    with _pytest.raises(RuntimeError, match="something else entirely"):
        asyncio.run(drive())
