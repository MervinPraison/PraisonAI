"""Host-side file helpers must not follow a symlink the sandboxed code swaps in.

SubprocessSandbox and SandlockSandbox checked the path string (realpath inside
the sandbox root) and then opened it by name. Code running in the sandbox shares
that directory, so it can replace the file with a symlink between the check and
the open, and the host then writes or reads outside the root. DockerSandbox
already opened through a descriptor; now all three share one helper.
"""
import inspect
import os
import sys
from unittest.mock import Mock, patch

import pytest

from praisonaiagents.sandbox.config import SandboxConfig, SecurityPolicy


def _subprocess_sandbox():
    from praisonai_sandbox.subprocess import SubprocessSandbox

    return SubprocessSandbox(SandboxConfig(security_policy=SecurityPolicy(allow_network=True)))


def _sandlock_sandbox():
    fake = Mock()
    fake.landlock_abi_version.return_value = 6
    fake.min_landlock_abi.return_value = 6
    sys.modules.pop("praisonai_sandbox.sandlock", None)
    with patch.dict("sys.modules", {"sandlock": fake}):
        from praisonai_sandbox.sandlock import SandlockSandbox
        return SandlockSandbox()


BACKENDS = {"subprocess": _subprocess_sandbox, "sandlock": _sandlock_sandbox}


@pytest.fixture(params=sorted(BACKENDS))
def started(request, tmp_path):
    import asyncio

    sandbox = BACKENDS[request.param]()
    asyncio.run(sandbox.start())
    outside = tmp_path / "outside.txt"
    outside.write_text("HOST")
    yield sandbox, outside
    asyncio.run(sandbox.stop())


def _swap_after_check(sandbox, name, target):
    """Make the old check-then-open path lose the race: swap in a symlink right after the check."""
    from praisonai_sandbox import _compat

    real = _compat.safe_sandbox_path

    def checked_then_swapped(root, path):
        result = real(root, path)
        link = os.path.join(sandbox._temp_dir, name)
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(target, link)
        return result

    stack = [patch.object(_compat, "safe_sandbox_path", checked_then_swapped)]
    if hasattr(sandbox, "_safe_sandbox_path"):
        stack.append(patch.object(sandbox, "_safe_sandbox_path",
                                  lambda path: checked_then_swapped(sandbox._temp_dir, path)))
    return stack


def test_a_symlink_swapped_in_after_the_check_is_not_written_through(started):
    import asyncio
    from contextlib import ExitStack

    sandbox, outside = started
    with ExitStack() as stack:
        for p in _swap_after_check(sandbox, "notes.txt", str(outside)):
            stack.enter_context(p)
        asyncio.run(sandbox.write_file("notes.txt", "PWNED"))
    assert outside.read_text() == "HOST"


def test_a_symlink_swapped_in_after_the_check_is_not_read_through(started):
    import asyncio
    from contextlib import ExitStack

    sandbox, outside = started
    with open(os.path.join(sandbox._temp_dir, "notes.txt"), "w") as f:
        f.write("inside")
    with ExitStack() as stack:
        for p in _swap_after_check(sandbox, "notes.txt", str(outside)):
            stack.enter_context(p)
        assert asyncio.run(sandbox.read_file("notes.txt")) != "HOST"


def test_a_symlinked_directory_component_is_refused(started, tmp_path):
    import asyncio

    sandbox, _ = started
    os.symlink(tmp_path, os.path.join(sandbox._temp_dir, "d"))
    assert asyncio.run(sandbox.write_file("d/escaped.txt", "x")) is False
    assert not (tmp_path / "escaped.txt").exists()


def test_ordinary_files_round_trip(started):
    import asyncio

    sandbox, _ = started
    assert asyncio.run(sandbox.write_file("sub/a.txt", "hello")) is True
    assert asyncio.run(sandbox.read_file("/sub/a.txt")) == "hello"
    assert asyncio.run(sandbox.write_file("b.bin", b"\xff\x00")) is True
    assert asyncio.run(sandbox.read_file("b.bin")) == b"\xff\x00"


@pytest.mark.parametrize("module, cls", [
    ("praisonai_sandbox.subprocess", "SubprocessSandbox"),
    ("praisonai_sandbox.sandlock", "SandlockSandbox"),
    ("praisonai_sandbox.docker", "DockerSandbox"),
])
def test_every_local_backend_uses_the_descriptor_helpers(module, cls):
    """Guard: a host-side file helper over a shared directory goes through _compat."""
    import importlib

    with patch.dict("sys.modules", {"sandlock": sys.modules.get("sandlock") or Mock()}):
        klass = getattr(importlib.import_module(module), cls)
    assert "write_in_sandbox" in inspect.getsource(klass.write_file)
    assert "read_in_sandbox" in inspect.getsource(klass.read_file)


def test_a_symlink_already_in_place_is_not_followed(started):
    import asyncio

    sandbox, outside = started
    os.symlink(outside, os.path.join(sandbox._temp_dir, "link.txt"))
    assert asyncio.run(sandbox.write_file("link.txt", "PWNED")) is False
    assert asyncio.run(sandbox.read_file("link.txt")) is None
    assert outside.read_text() == "HOST"
