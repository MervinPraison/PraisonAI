"""Outbound attachments stay inside the agent's workspace.

``send_message("origin", "... MEDIA:<path>")`` is model-controlled. A file
outside the workspace (another app's token file, a database, shell history)
must not be uploaded, whatever its name; the credential denylist is only a
second layer.
"""
import asyncio

import pytest

from praisonai_bot.bots._outbound_media import (
    MediaDeliveryError,
    OutboundMediaPolicy,
    validate_media_delivery_path,
)
from praisonai_bot.bots._outbound_messenger import BotOutboundMessenger


@pytest.fixture
def layout(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "home" / ".config" / "gh"
    outside.mkdir(parents=True)
    (outside / "hosts.yml").write_text("oauth_token: x")
    (tmp_path / "app.sqlite").write_text("rows")
    (workspace / "report.pdf").write_bytes(b"%PDF")
    monkeypatch.chdir(workspace)
    return tmp_path, workspace


def test_file_outside_workspace_is_refused(layout):
    tmp_path, _ = layout
    for path in (tmp_path / "home/.config/gh/hosts.yml", tmp_path / "app.sqlite",
                 "../app.sqlite"):
        with pytest.raises(MediaDeliveryError, match="outside the workspace"):
            validate_media_delivery_path(str(path))


def test_file_inside_workspace_is_sent(layout):
    _, workspace = layout
    assert validate_media_delivery_path("report.pdf") == str((workspace / "report.pdf").resolve())


def test_symlink_out_of_workspace_is_refused(layout):
    tmp_path, workspace = layout
    (workspace / "innocent.pdf").symlink_to(tmp_path / "app.sqlite")
    with pytest.raises(MediaDeliveryError, match="outside the workspace"):
        validate_media_delivery_path("innocent.pdf")


def test_recent_file_outside_roots_is_refused_in_strict_mode(layout):
    tmp_path, workspace = layout
    policy = OutboundMediaPolicy(strict=True, allow_roots=[str(workspace)])
    with pytest.raises(MediaDeliveryError):
        validate_media_delivery_path(str(tmp_path / "app.sqlite"), policy=policy)


def test_configured_root_is_the_boundary(layout):
    tmp_path, _ = layout
    policy = OutboundMediaPolicy(allow_roots=[str(tmp_path)])
    assert validate_media_delivery_path(str(tmp_path / "app.sqlite"), policy=policy)


def test_messenger_does_not_upload_outside_workspace(layout):
    tmp_path, _ = layout
    uploads = []

    class Router:
        async def send_media(self, target, path, caption=None, origin=None):
            uploads.append(path)
            return True

    messenger = BotOutboundMessenger(Router())
    sent, skipped, _ = asyncio.run(messenger._deliver_media(
        "telegram:1", [str(tmp_path / "home/.config/gh/hosts.yml"), "report.pdf"],
        caption=None,
    ))
    assert (sent, skipped) == (1, 1)
    assert [p.endswith("report.pdf") for p in uploads] == [True]
