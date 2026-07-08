"""Unit tests for Computer Use tools (Issue #516).

Verifies:
- Tools are importable from praisonaiagents.tools (lazy registration).
- Read-only tools (screenshot / screen_size) never require approval.
- Control tools (click/type/key/scroll/move) are denied without approval and
  allowed once an approval callback is registered.
- Missing optional backend (pyautogui) degrades gracefully (no import error).
"""

import pytest


def _reset_approval():
    from praisonaiagents.tools import set_computer_approval
    set_computer_approval(None)


class TestComputerToolsImport:
    def test_tools_importable(self):
        from praisonaiagents.tools import (
            computer_screenshot, computer_screen_size, computer_move,
            computer_click, computer_type, computer_key, computer_scroll,
            set_computer_approval,
        )
        for fn in (
            computer_screenshot, computer_screen_size, computer_move,
            computer_click, computer_type, computer_key, computer_scroll,
            set_computer_approval,
        ):
            assert callable(fn)

    def test_module_importable(self):
        from praisonaiagents.tools import computer_tools
        assert hasattr(computer_tools, "computer_click")


class TestApprovalGate:
    def setup_method(self):
        _reset_approval()

    def teardown_method(self):
        _reset_approval()

    def test_control_denied_without_approval(self):
        from praisonaiagents.tools import computer_click
        result = computer_click(10, 20)
        assert "denied" in result.lower()

    def test_control_allowed_with_approval(self, monkeypatch):
        from praisonaiagents.tools import (
            computer_click, set_computer_approval, computer_tools,
        )
        # Force the backend to be "missing" so we test the gate, not the OS.
        monkeypatch.setattr(computer_tools, "_get_backend", lambda: None)
        set_computer_approval(lambda action: True)
        result = computer_click(10, 20)
        assert "denied" not in result.lower()

    def test_approval_receives_action_description(self):
        from praisonaiagents.tools import computer_key, set_computer_approval
        seen = {}
        set_computer_approval(lambda action: seen.setdefault("action", action) and False or False)
        computer_key("ctrl+c")
        assert "ctrl+c" in seen.get("action", "")


class TestReadOnlyTools:
    def setup_method(self):
        _reset_approval()

    def test_screenshot_no_approval_needed(self, monkeypatch):
        from praisonaiagents.tools import computer_screenshot, computer_tools
        monkeypatch.setattr(computer_tools, "_get_backend", lambda: None)
        # Even with no approval callback, read-only tools do not report "denied".
        result = computer_screenshot()
        assert "denied" not in result.lower()

    def test_screen_size_no_approval_needed(self, monkeypatch):
        from praisonaiagents.tools import computer_screen_size, computer_tools
        monkeypatch.setattr(computer_tools, "_get_backend", lambda: None)
        result = computer_screen_size()
        assert "denied" not in result.lower()


class TestMissingBackend:
    def setup_method(self):
        _reset_approval()

    def test_graceful_message_when_backend_missing(self, monkeypatch):
        from praisonaiagents.tools import (
            computer_screenshot, computer_tools, set_computer_approval,
        )
        monkeypatch.setattr(computer_tools, "_get_backend", lambda: None)
        set_computer_approval(lambda action: True)
        result = computer_screenshot()
        assert "pyautogui" in result.lower()


class TestControlBackendInvoked:
    """When approved and backend present, the backend receives the call."""

    def setup_method(self):
        _reset_approval()

    def teardown_method(self):
        _reset_approval()

    def test_click_invokes_backend(self, monkeypatch):
        from unittest.mock import MagicMock
        from praisonaiagents.tools import (
            computer_click, computer_tools, set_computer_approval,
        )
        fake = MagicMock()
        monkeypatch.setattr(computer_tools, "_get_backend", lambda: fake)
        set_computer_approval(lambda action: True)
        result = computer_click(5, 6, button="right")
        fake.click.assert_called_once_with(x=5, y=6, button="right")
        assert "denied" not in result.lower()

    def test_key_hotkey_split(self, monkeypatch):
        from unittest.mock import MagicMock
        from praisonaiagents.tools import (
            computer_key, computer_tools, set_computer_approval,
        )
        fake = MagicMock()
        monkeypatch.setattr(computer_tools, "_get_backend", lambda: fake)
        set_computer_approval(lambda action: True)
        computer_key("ctrl+c")
        fake.hotkey.assert_called_once_with("ctrl", "c")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
