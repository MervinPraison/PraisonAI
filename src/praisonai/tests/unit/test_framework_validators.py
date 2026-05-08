"""
Unit tests for praisonai.framework_adapters.validators.assert_framework_available().

Tests cover:
- Raises ImportError for unavailable frameworks with actionable install hint
- Does not raise for available frameworks
- Install hint format and content
- Unknown framework names fall back to generic pip install hint
"""

import pytest
from unittest.mock import patch, MagicMock

try:
    from praisonai.framework_adapters.validators import assert_framework_available
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry
except ImportError as e:
    pytest.skip(f"Could not import framework_adapters: {e}", allow_module_level=True)


class TestAssertFrameworkAvailableRaises:
    """Tests that ImportError is raised for unavailable frameworks."""

    def test_raises_import_error_for_missing_framework(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError):
                assert_framework_available("crewai")

    def test_error_message_contains_framework_name(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError, match="crewai"):
                assert_framework_available("crewai")

    def test_error_message_contains_install_hint(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError, match="pip install"):
                assert_framework_available("crewai")

    def test_crewai_hint_mentions_praisonai_extra(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError) as exc_info:
                assert_framework_available("crewai")
            error_msg = str(exc_info.value)
            assert "praisonai[crewai]" in error_msg or "pip install crewai" in error_msg

    def test_autogen_hint_mentions_pyautogen(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError) as exc_info:
                assert_framework_available("autogen")
            assert "autogen" in str(exc_info.value).lower()

    def test_unknown_framework_generic_hint(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError) as exc_info:
                assert_framework_available("some_unknown_framework_xyz")
            assert "some_unknown_framework_xyz" in str(exc_info.value)


class TestAssertFrameworkAvailableSucceeds:
    """Tests that no exception is raised for available frameworks."""

    def test_no_error_when_framework_available(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = True
            mock_get.return_value = mock_registry

            # Should not raise
            assert_framework_available("crewai")

    def test_returns_none_for_available_framework(self):
        with patch.object(FrameworkAdapterRegistry, "get_instance") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = True
            mock_get.return_value = mock_registry

            result = assert_framework_available("praisonai")
            assert result is None
