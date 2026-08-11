"""
Regression tests for `praisonai code` workspace rooting and session binding.

Covers:
- The `--workspace` flag actually re-roots the interactive tool loader
  (previously dead: env-name mismatch + unconditional os.getcwd() override).
- `--continue`/`--session` resume re-binds the tools to the directory the
  session was created in (persisted UnifiedSession.workspace), with a graceful
  cwd fallback when that directory no longer exists.
"""

import argparse
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestWorkspaceFlagRootsTools:
    """Bug 1: `--workspace <dir>` must re-root the tool loader."""

    def test_load_interactive_tools_honours_workspace_env(self, tmp_path):
        from praisonai.cli.legacy import interactive_legacy

        captured = {}

        def _fake_get_tools(config=None, disable=None):
            captured["workspace"] = config.workspace
            return []

        target = tmp_path / "ws"
        target.mkdir()
        self_stub = SimpleNamespace(args=argparse.Namespace(no_acp=False, no_lsp=False))

        with patch.dict(os.environ, {"PRAISONAI_WORKSPACE": str(target)}, clear=False):
            os.environ.pop("PRAISON_WORKSPACE", None)
            with patch(
                "praisonai.cli.features.interactive_tools.get_interactive_tools",
                _fake_get_tools,
            ):
                interactive_legacy._load_interactive_tools(self_stub)

        assert captured["workspace"] == str(target)

    def test_load_interactive_tools_defaults_to_cwd(self):
        from praisonai.cli.legacy import interactive_legacy

        captured = {}

        def _fake_get_tools(config=None, disable=None):
            captured["workspace"] = config.workspace
            return []

        self_stub = SimpleNamespace(args=argparse.Namespace(no_acp=False, no_lsp=False))

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRAISONAI_WORKSPACE", None)
            os.environ.pop("PRAISON_WORKSPACE", None)
            with patch(
                "praisonai.cli.features.interactive_tools.get_interactive_tools",
                _fake_get_tools,
            ):
                interactive_legacy._load_interactive_tools(self_stub)

        assert captured["workspace"] == os.getcwd()


class TestSessionResumeRebindsDirectory:
    """Session↔directory binding on --continue/--session resume."""

    def _store_with(self, workspace):
        session = SimpleNamespace(workspace=workspace)
        store = MagicMock()
        store.get_last_session.return_value = session
        store.get_or_create.return_value = session
        return store

    def test_resume_binds_existing_directory(self, tmp_path):
        from praisonai.cli.legacy import interactive_legacy

        ws = tmp_path / "session_dir"
        ws.mkdir()
        store = self._store_with(str(ws))
        args = argparse.Namespace(resume_session="last")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRAISONAI_WORKSPACE", None)
            with patch(
                "praisonai.cli.session.get_session_store",
                return_value=store,
            ):
                interactive_legacy._bind_resume_workspace(args, console=None)
            assert os.environ.get("PRAISONAI_WORKSPACE") == str(ws)

    def test_resume_missing_directory_falls_back_to_cwd(self, tmp_path):
        from praisonai.cli.legacy import interactive_legacy

        missing = tmp_path / "gone"
        store = self._store_with(str(missing))
        args = argparse.Namespace(resume_session="abc123")
        console = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRAISONAI_WORKSPACE", None)
            with patch(
                "praisonai.cli.session.get_session_store",
                return_value=store,
            ):
                interactive_legacy._bind_resume_workspace(args, console=console)
            # Canonical var is pinned to cwd so a stray legacy PRAISON_WORKSPACE
            # cannot override the advertised current-directory fallback.
            assert os.environ.get("PRAISONAI_WORKSPACE") == os.getcwd()
            console.print.assert_called_once()

    def test_resume_missing_directory_pins_cwd_over_legacy_var(self, tmp_path):
        """P1: missing saved dir + legacy PRAISON_WORKSPACE set must still
        resolve to cwd in the tool loader, not the legacy directory."""
        from praisonai.cli.legacy import interactive_legacy

        missing = tmp_path / "gone"
        legacy = tmp_path / "legacy_ws"
        legacy.mkdir()
        store = self._store_with(str(missing))
        args = argparse.Namespace(resume_session="abc123")

        with patch.dict(
            os.environ, {"PRAISON_WORKSPACE": str(legacy)}, clear=False
        ):
            os.environ.pop("PRAISONAI_WORKSPACE", None)
            with patch(
                "praisonai.cli.session.get_session_store",
                return_value=store,
            ):
                interactive_legacy._bind_resume_workspace(args, console=None)
            assert os.environ.get("PRAISONAI_WORKSPACE") == os.getcwd()

    def test_resume_uses_provided_session_without_relookup(self, tmp_path):
        """P1: when the caller passes the already-resolved session, the binder
        must not perform a second store lookup (avoids racing a concurrent CLI)."""
        from praisonai.cli.legacy import interactive_legacy

        ws = tmp_path / "provided"
        ws.mkdir()
        session = SimpleNamespace(workspace=str(ws))
        args = argparse.Namespace(resume_session="last")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRAISONAI_WORKSPACE", None)
            with patch(
                "praisonai.cli.session.get_session_store"
            ) as mock_store_getter:
                interactive_legacy._bind_resume_workspace(
                    args, console=None, session=session
                )
                mock_store_getter.assert_not_called()
            assert os.environ.get("PRAISONAI_WORKSPACE") == str(ws)

    def test_no_resume_is_noop(self):
        from praisonai.cli.legacy import interactive_legacy

        args = argparse.Namespace(resume_session=None)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRAISONAI_WORKSPACE", None)
            interactive_legacy._bind_resume_workspace(args, console=None)
            assert "PRAISONAI_WORKSPACE" not in os.environ


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
