"""Daemon CLI background spawn uses code-tier runtime module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer


def test_daemon_start_background_spawns_code_runtime_module():
    """Background daemon must spawn praisonai_code.runtime, not praisonai.runtime."""
    from praisonai_code.cli.commands import daemon as daemon_cmd

    ready = MagicMock(base_url="http://127.0.0.1:9999", pid=12345)

    with patch(
        "praisonai_code.runtime.get_runtime_descriptor",
        side_effect=[None, ready],
    ), patch("subprocess.Popen") as popen, patch("time.sleep"):
        popen.return_value = MagicMock()
        with pytest.raises(typer.Exit) as exc:
            daemon_cmd.daemon_start(
                host="127.0.0.1",
                port=0,
                model=None,
                idle_timeout=1800.0,
                background=True,
            )
        assert exc.value.exit_code == 0
        cmd = popen.call_args[0][0]
        assert "-m" in cmd
        assert cmd[cmd.index("-m") + 1] == "praisonai_code.runtime"
