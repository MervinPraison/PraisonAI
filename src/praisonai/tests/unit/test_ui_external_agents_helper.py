import sys
import types

from praisonai.ui import _external_agents as ext


class _FakeUserSession:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def test_load_external_agent_settings_uses_explicit_loader(monkeypatch):
    fake_chainlit = types.SimpleNamespace(user_session=_FakeUserSession({}))
    monkeypatch.setitem(sys.modules, "chainlit", fake_chainlit)

    values = {
        "claude_code_enabled": "true",
        "claude_enabled": "false",
        "gemini_enabled": "true",
        "codex_enabled": "1",
    }
    settings = ext.load_external_agent_settings_from_chainlit(lambda key: values.get(key))

    assert set(settings.keys()) == set(ext.EXTERNAL_AGENTS.keys())
    assert settings["claude_enabled"] is False
    assert settings["gemini_enabled"] is True
    assert settings["codex_enabled"] is True


def test_load_external_agent_settings_session_overrides_persistent(monkeypatch):
    fake_chainlit = types.SimpleNamespace(
        user_session=_FakeUserSession({"gemini_enabled": True, "claude_code_enabled": False})
    )
    monkeypatch.setitem(sys.modules, "chainlit", fake_chainlit)

    values = {"gemini_enabled": "false"}
    settings = ext.load_external_agent_settings_from_chainlit(lambda key: values.get(key))

    assert settings["gemini_enabled"] is True
