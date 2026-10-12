"""Gateway ``access_groups`` expansion at config load (Issue #5775)."""

import pytest

from praisonai_bot.gateway.server import WebSocketGateway

_BASE = """
agents:
  a: {instructions: hi}
access_groups:
  admins: ["111", "222"]
  team: ["group:admins", "333"]
channels:
  telegram:
    token: t
    allowed_users: ["group:team"]
  discord:
    token: d
    allowed_users: ["group:admins"]
    blocklist: ["999"]
"""


def test_channels_share_one_group_definition(tmp_path):
    cfg_path = tmp_path / "gateway.yaml"
    cfg_path.write_text(_BASE)
    cfg = WebSocketGateway.load_gateway_config(str(cfg_path))
    assert cfg["channels"]["telegram"]["allowed_users"] == ["111", "222", "333"]
    assert cfg["channels"]["discord"]["allowed_users"] == ["111", "222"]
    assert cfg["channels"]["discord"]["blocklist"] == ["999"]


def test_unknown_group_fails_closed(tmp_path):
    cfg_path = tmp_path / "gateway.yaml"
    cfg_path.write_text(_BASE.replace('["group:admins"]', '["group:nope"]'))
    with pytest.raises(ValueError, match="Unknown access group"):
        WebSocketGateway.load_gateway_config(str(cfg_path))
