"""C9.6b — approval channel backend split boundary tests."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[4]
BOT_PKG = REPO / "src" / "praisonai-bot"
CODE_PKG = REPO / "src" / "praisonai-code"


@pytest.fixture(autouse=True)
def _paths():
    for p in (str(REPO / "src" / "praisonai-agents"), str(BOT_PKG), str(CODE_PKG)):
        if p not in sys.path:
            sys.path.insert(0, p)
    yield


def test_channel_backends_module_in_bot_package():
    from praisonai_bot.cli import approval_backends

    src = inspect.getsourcefile(approval_backends.resolve_channel_approval_backend)
    assert src is not None
    assert "approval_backends.py" in src.replace("\\", "/")


def test_approval_bridge_uses_approval_backends_not_features_approval():
    from praisonai_code.cli.features import _approval_bridge

    source = inspect.getsource(_approval_bridge.resolve_approval_backend)
    assert "approval_backends" in source
    assert "cli.features.approval" not in source


def test_slack_backend_resolves_via_channel_module():
    with mock.patch(
        "praisonai_bot.bots.SlackApproval",
        create=True,
    ) as slack_cls:
        slack_cls.return_value = object()
        from praisonai_bot.cli.approval_backends import resolve_channel_approval_backend

        backend = resolve_channel_approval_backend("slack")
        assert backend is slack_cls.return_value


def test_code_bridge_delegates_slack_to_bot_backends():
    with mock.patch(
        "praisonai_code._bot_bridge.import_bot_module",
    ) as import_mod:
        fake = mock.MagicMock()
        fake.resolve_channel_approval_backend.return_value = "slack-backend"
        import_mod.return_value = fake

        from praisonai_code.cli.features._approval_bridge import resolve_approval_backend

        result = resolve_approval_backend("slack")
        import_mod.assert_called_once_with("praisonai_bot.cli.approval_backends")
        fake.resolve_channel_approval_backend.assert_called_once_with("slack")
        assert result == "slack-backend"
