"""ModalSandbox.write_file() must not claim a write it did not perform.

The whole body was:

    logger.warning("Modal sandbox write_file is limited - files are not persistent...")
    return True

SandboxProtocol documents the return as "True if successful", so every caller
was told the write had happened. Callers that branch on the result
(`if not await sandbox.write_file(...)`) were handed the wrong answer, so the
false True was the difference between a handled failure and a silent one.

The knock-on: execute_file() is built on read_file(), which always returns
None, so it then failed with "File not found: <path>" for a file the caller
had just been told was written successfully. Two contradictory answers about
the same file.

Persisting here needs Modal Volumes. Until that exists, False is the truthful
answer, and callers already handle it.
"""
import asyncio
import inspect

import pytest

from praisonai_sandbox.modal import ModalSandbox


def _bare():
    """A ModalSandbox without the network-touching __init__."""
    return ModalSandbox.__new__(ModalSandbox)


class TestWriteFileTellsTheTruth:

    def test_it_returns_false(self):
        assert asyncio.run(
            ModalSandbox.write_file(_bare(), "/tmp/x.py", "print(1)")) is False

    def test_it_returns_false_for_bytes_too(self):
        assert asyncio.run(
            ModalSandbox.write_file(_bare(), "/tmp/x.bin", b"\x00\x01")) is False

    def test_the_source_no_longer_returns_true(self):
        """Parse it: the docstring quotes the old `return True` on purpose."""
        import ast
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(ModalSandbox.write_file)))
        returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
        assert returns, "write_file no longer returns anything"
        for node in returns:
            assert not (isinstance(node.value, ast.Constant)
                        and node.value.value is True), "still returns True"

    def test_the_message_names_a_way_forward(self):
        """A refusal that does not say what to do instead is half a bug report.

        Assert on the warning users actually receive, not the method source --
        the docstring quotes "execute()" too, so a source search would keep
        passing even if the recommendation vanished from the log message.
        """
        from unittest.mock import patch

        with patch("praisonai_sandbox.modal.logger.warning") as warn:
            asyncio.run(ModalSandbox.write_file(_bare(), "/tmp/x.py", "print(1)"))
        assert warn.call_count == 1
        emitted = " ".join(str(a) for a in warn.call_args.args)
        assert "execute()" in emitted


class TestReadAndExecuteAgreeWithIt:

    def test_read_file_still_returns_none(self):
        assert asyncio.run(ModalSandbox.read_file(_bare(), "/tmp/x.py")) is None

    def test_execute_file_explains_the_real_reason(self):
        """It used to say "File not found", which sends the user hunting a path."""
        src = inspect.getsource(ModalSandbox.execute_file)
        assert "File not found" not in src
        assert "no file storage" in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
