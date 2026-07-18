"""Unit tests for canonical tool name resolution."""

from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.tools.resolver import (
    ToolResolutionError,
    resolve_tool_name,
    resolve_tool_names,
)


class TestResolveToolName:
    def test_registry_takes_precedence(self):
        mock_tool = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        with patch("praisonaiagents.tools.registry.get_registry", return_value=mock_registry):
            assert resolve_tool_name("my_tool") is mock_tool

    def test_falls_back_to_tool_mappings(self):
        sentinel = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with patch("praisonaiagents.tools.registry.get_registry", return_value=mock_registry):
            with patch("praisonaiagents.tools.TOOL_MAPPINGS", {"schedule_add": (".schedule_tools", None)}):
                with patch("praisonaiagents.tools.__getattr__", return_value=sentinel):
                    assert resolve_tool_name("schedule_add") is sentinel

    def test_returns_none_when_unresolved(self):
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with patch("praisonaiagents.tools.registry.get_registry", return_value=mock_registry):
            with patch("praisonaiagents.tools.TOOL_MAPPINGS", {}):
                with patch("praisonaiagents.tools.resolver._praisonai_tools_available", False):
                    assert resolve_tool_name("nonexistent_tool_xyz") is None


class TestResolveToolNames:
    def test_resolve_tool_names_skips_missing(self):
        with patch(
            "praisonaiagents.tools.resolver.resolve_tool_name",
            side_effect=[MagicMock(), None, MagicMock()],
        ):
            resolved = resolve_tool_names(["a", "b", "c"])
        assert len(resolved) == 2

    def test_strict_raises_on_unknown(self):
        with patch(
            "praisonaiagents.tools.resolver.resolve_tool_name",
            return_value=None,
        ):
            with pytest.raises(ToolResolutionError) as exc_info:
                resolve_tool_names(["web_serch"], strict=True)
        assert exc_info.value.unknown == ["web_serch"]
        assert "web_serch" in exc_info.value.suggestions

    def test_strict_from_env(self, monkeypatch):
        monkeypatch.setenv("PRAISONAI_STRICT_TOOLS", "true")
        with patch(
            "praisonaiagents.tools.resolver.resolve_tool_name",
            return_value=None,
        ):
            with pytest.raises(ToolResolutionError):
                resolve_tool_names(["nope_xyz"])

    def test_non_strict_invokes_on_unknown_callback(self):
        seen = {}

        def _cb(unknown, suggestions):
            seen["unknown"] = unknown
            seen["suggestions"] = suggestions

        with patch(
            "praisonaiagents.tools.resolver.resolve_tool_name",
            return_value=None,
        ):
            resolved = resolve_tool_names(["nope_xyz"], strict=False, on_unknown=_cb)
        assert resolved == []
        assert seen["unknown"] == ["nope_xyz"]

    def test_suggestion_for_typo(self):
        with patch(
            "praisonaiagents.tools.resolver._available_tool_names",
            return_value=["internet_search", "duckduckgo"],
        ):
            from praisonaiagents.tools.resolver import _closest_names

            assert "internet_search" in _closest_names("internet_serch")
