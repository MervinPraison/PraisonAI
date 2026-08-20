"""Tests for the zero-code custom channel path (Issue #4104).

Covers the YAML ``adapter:`` dotted import-string resolution in
``GatewayConfigSchema.normalize_and_validate`` and the filesystem drop-in
discovery in ``BotPlatformRegistry``.
"""

import sys
import textwrap
import types

import pytest

from praisonai_bot.bots import _registry as R
from praisonai_bot.bots._config_schema import GatewayConfigSchema


@pytest.fixture(autouse=True)
def _reset_default_registry():
    """Isolate the process ``_default_registry`` singleton around each test."""
    saved = R._default_registry
    R._default_registry = None
    R._bot_registry = None
    try:
        yield
    finally:
        R._default_registry = saved
        R._bot_registry = saved


def _make_adapter_module(mod_name: str, class_name: str = "IntranetBot"):
    """Create an importable module exposing a BasePlatformAdapter subclass."""
    from praisonaiagents.bots import BasePlatformAdapter

    class _Adapter(BasePlatformAdapter):
        async def connect(self, *, is_reconnect: bool = False) -> bool:
            return True

        async def disconnect(self) -> None:
            return None

        async def send_message(self, *args, **kwargs):
            return None

        async def listen(self, *args, **kwargs):
            return None

    _Adapter.__name__ = class_name
    module = types.ModuleType(mod_name)
    setattr(module, class_name, _Adapter)
    sys.modules[mod_name] = module
    return _Adapter


def test_yaml_adapter_ref_registers_custom_channel():
    """A channel with an ``adapter:`` import string resolves and validates."""
    adapter_cls = _make_adapter_module("fake_intranet_mod")
    try:
        cfg = GatewayConfigSchema(
            channels={
                "my_intranet_chat": {
                    "adapter": "fake_intranet_mod:IntranetBot",
                    "token": "tok",
                }
            }
        )
    finally:
        pass

    assert cfg.channels["my_intranet_chat"].platform == "my_intranet_chat"
    assert R.resolve_adapter("my_intranet_chat") is adapter_cls
    sys.modules.pop("fake_intranet_mod", None)


def test_yaml_adapter_ref_rejects_non_adapter():
    """A non-BasePlatformAdapter class is rejected with a clear error."""
    module = types.ModuleType("fake_bad_mod")

    class NotAnAdapter:
        pass

    module.NotAnAdapter = NotAnAdapter
    sys.modules["fake_bad_mod"] = module
    try:
        with pytest.raises(Exception) as exc:
            GatewayConfigSchema(
                channels={
                    "bad": {"adapter": "fake_bad_mod:NotAnAdapter", "token": "t"}
                }
            )
        assert "BasePlatformAdapter" in str(exc.value)
    finally:
        sys.modules.pop("fake_bad_mod", None)


def test_yaml_adapter_ref_bad_module():
    """An unimportable module surfaces a friendly ValueError."""
    with pytest.raises(Exception) as exc:
        GatewayConfigSchema(
            channels={"x": {"adapter": "no_such_mod_xyz:Foo", "token": "t"}}
        )
    assert "no_such_mod_xyz" in str(exc.value)


def test_import_adapter_ref_malformed():
    """A ref without ``module:Class`` form is rejected."""
    with pytest.raises(Exception) as exc:
        GatewayConfigSchema(
            channels={"x": {"adapter": "no_colon_here", "token": "t"}}
        )
    assert "module.path:ClassName" in str(exc.value)


def test_builtin_platform_still_works_without_adapter():
    """Backward compatible: no ``adapter`` key resolves as before."""
    cfg = GatewayConfigSchema(
        channels={"telegram": {"platform": "telegram", "token": "t"}}
    )
    assert cfg.channels["telegram"].platform == "telegram"


def test_drop_in_channel_file_discovered(tmp_path, monkeypatch):
    """A single-file adapter in the user channels dir is auto-registered."""
    user_home = tmp_path / "userhome"
    channels_dir = user_home / "channels"
    channels_dir.mkdir(parents=True)
    (channels_dir / "mydrop.py").write_text(
        textwrap.dedent(
            '''
            from praisonaiagents.bots import BasePlatformAdapter

            class DropInBot(BasePlatformAdapter):
                platform_name = "dropin_chat"

                async def connect(self, *, is_reconnect=False):
                    return True

                async def disconnect(self):
                    return None

                async def send_message(self, *a, **k):
                    return None

                async def listen(self, *a, **k):
                    return None
            '''
        )
    )

    import praisonaiagents.paths as paths

    monkeypatch.setattr(paths, "get_plugins_dir", lambda: user_home / "plugins")
    monkeypatch.setattr(
        paths, "get_project_data_dir", lambda *a, **k: tmp_path / "noproject"
    )

    reg = R.BotPlatformRegistry()
    assert "dropin_chat" in reg.list_names()
    for mod in list(sys.modules):
        if mod.startswith("praison_channel_mydrop_"):
            sys.modules.pop(mod, None)
