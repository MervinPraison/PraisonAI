"""Regression tests for the Windows cp1252 CLI crash (issue #3605).

On default Windows consoles stdout uses cp1252, which cannot encode the emoji
prefixes (🏥 🔍 📋 🚀 ❌) emitted by the deploy CLI banners. These tests assert
that the UTF-8 stdio safeguard prevents ``UnicodeEncodeError`` from bubbling up.
"""
import io
import sys
from unittest.mock import Mock, patch


def _make_cp1252_stream():
    """A text stream backed by a cp1252 buffer, mimicking a legacy Windows console."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def test_configure_stdio_reconfigures_to_utf8():
    """_configure_stdio must switch a cp1252 stream to utf-8 with replace errors."""
    from praisonai_deploy.cli.features.deploy import _configure_stdio

    stream = _make_cp1252_stream()
    assert stream.encoding == "cp1252"

    with patch.object(sys, "stdout", stream), patch.object(sys, "stderr", stream):
        _configure_stdio()

    assert stream.encoding == "utf-8"
    stream.write("🏥 health check ❌")
    stream.flush()


def test_configure_stdio_survives_streams_without_reconfigure():
    """Streams lacking reconfigure (e.g. some captured stdio) must not raise."""
    from praisonai_deploy.cli.features.deploy import _configure_stdio

    plain = io.StringIO()
    assert not hasattr(plain, "reconfigure")

    with patch.object(sys, "stdout", plain), patch.object(sys, "stderr", plain):
        _configure_stdio()  # should be a no-op, no exception


def test_handle_deploy_command_configures_stdio_before_dispatch():
    """The `praisonai deploy` bridge entry must reconfigure stdio before printing."""
    from praisonai_deploy.cli.features import deploy as deploy_mod

    with patch.object(deploy_mod, "_configure_stdio") as mock_cfg, patch.object(
        deploy_mod.DeployHandler, "handle_validate"
    ):
        code = deploy_mod.handle_deploy_command(["validate", "agents.yaml"])

    assert code == 0
    mock_cfg.assert_called_once()


def test_doctor_banner_does_not_crash_on_cp1252_stdout():
    """doctor emoji banner must not raise UnicodeEncodeError once stdio is UTF-8."""
    from praisonai_deploy.cli.features import deploy as deploy_mod
    from praisonai_deploy.doctor import DoctorReport, DoctorCheckResult

    stream = _make_cp1252_stream()

    with patch.object(sys, "stdout", stream), patch.object(sys, "stderr", stream):
        deploy_mod._configure_stdio()
        # Rebind the module-level Rich console to the reconfigured stream.
        from rich.console import Console

        with patch.object(deploy_mod, "console", Console(file=sys.stdout)):
            with patch("praisonai_deploy.doctor.run_all_checks") as mock_all:
                mock_all.return_value = DoctorReport(
                    [DoctorCheckResult("Check 1", True, "OK")]
                )
                args = Mock(all=True, provider=None, file=None, verbose=False, json=False)
                deploy_mod.DeployHandler().handle_doctor(args)

    stream.flush()
