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
except ImportError as e:
    pytest.skip(f"Could not import framework_adapters: {e}", allow_module_level=True)


class TestAssertFrameworkAvailableRaises:
    """Tests that ImportError is raised for unavailable frameworks."""

    def test_raises_import_error_for_missing_framework(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError):
                assert_framework_available("crewai")

    def test_error_message_contains_framework_name(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError, match="crewai"):
                assert_framework_available("crewai")

    def test_error_message_contains_install_hint(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_registry.create.return_value.install_hint = 'pip install "praisonai[crewai]"'
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError, match="pip install"):
                assert_framework_available("crewai")

    def test_crewai_hint_mentions_praisonai_extra(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            # No adapter-declared hint -> fall back to the frameworks extra. The
            # validator now threads its (injected) registry into get_install_hint,
            # so the registry the validator consults is the one that produces the
            # hint — keeping DI intact end to end.
            mock_registry.create.return_value.install_hint = None
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError) as exc_info:
                assert_framework_available("crewai")
            error_msg = str(exc_info.value)
            assert "praisonai-frameworks[crewai]" in error_msg or "pip install crewai" in error_msg

    def test_autogen_hint_mentions_pyautogen(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_registry.create.return_value.install_hint = None
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError) as exc_info:
                assert_framework_available("autogen")
            assert "autogen" in str(exc_info.value).lower()

    def test_unknown_framework_generic_hint(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = False
            mock_registry.create.return_value.install_hint = None
            mock_get.return_value = mock_registry

            with pytest.raises(ImportError) as exc_info:
                assert_framework_available("some_unknown_framework_xyz")
            assert "some_unknown_framework_xyz" in str(exc_info.value)
            assert "praisonai-frameworks[some_unknown_framework_xyz]" in str(exc_info.value)


class TestAssertFrameworkAvailableHonoursInjectedRegistry:
    """The injected registry (DI seam) must drive validation, not the default."""

    def test_injected_registry_is_consulted(self):
        # An injected registry that reports availability must pass even if the
        # process-default would reject the framework. This is the multi-tenant /
        # scoped-adapter case the process-global default silently broke.
        injected = MagicMock()
        injected.is_available.return_value = True

        with patch(
            "praisonai.framework_adapters.validators.get_default_registry"
        ) as mock_default:
            mock_default.return_value = MagicMock(is_available=lambda name: False)
            # Should NOT raise: the injected registry reports available.
            assert_framework_available("tenant_scoped_fw", registry=injected)

        injected.is_available.assert_called_once_with("tenant_scoped_fw")
        # The process-default must not be consulted when a registry is injected.
        mock_default.assert_not_called()

    def test_injected_registry_drives_install_hint(self):
        # When the injected registry rejects the framework, the hint must be
        # derived from that same registry (DI end to end), not the default.
        injected = MagicMock()
        injected.is_available.return_value = False
        injected.create.return_value.install_hint = "pip install my-tenant-shim"

        with pytest.raises(ImportError) as exc_info:
            assert_framework_available("tenant_scoped_fw", registry=injected)

        assert "pip install my-tenant-shim" in str(exc_info.value)

    def test_resolved_builtin_name_falls_back_to_default(self):
        # A router/alias can resolve to a concrete built-in (e.g. autogen ->
        # autogen_v2) whose key lives on the process default, not on a scoped
        # injected registry. Validation must NOT reject it: it should fall back
        # to the default registry which knows the resolved name.
        injected = MagicMock()
        injected.is_available.return_value = False  # scoped registry lacks it

        default = MagicMock()
        default.is_available.return_value = True  # default knows the resolved name

        with patch(
            "praisonai.framework_adapters.validators.get_default_registry",
            return_value=default,
        ):
            # Must NOT raise thanks to the default-registry fallback.
            assert_framework_available("autogen_v2", registry=injected)

        injected.is_available.assert_called_once_with("autogen_v2")
        default.is_available.assert_called_once_with("autogen_v2")

    def test_no_fallback_when_default_also_missing(self):
        # If neither the injected registry nor the default knows the name, the
        # ImportError must still surface (fallback must not mask real absence).
        injected = MagicMock()
        injected.is_available.return_value = False
        injected.create.return_value.install_hint = "pip install my-tenant-shim"

        default = MagicMock()
        default.is_available.return_value = False

        with patch(
            "praisonai.framework_adapters.validators.get_default_registry",
            return_value=default,
        ):
            with pytest.raises(ImportError):
                assert_framework_available("totally_unknown_fw", registry=injected)


class TestRegistryImportErrorIsContained:
    """Registry must not leak raw ImportError from adapter construction."""

    def test_is_available_swallows_constructor_import_error(self):
        from praisonai.framework_adapters.registry import get_default_registry

        registry = get_default_registry()
        with patch.object(registry, "create", side_effect=ImportError("missing dep")):
            assert registry.is_available("crewai") is False

    def test_assert_framework_available_gives_friendly_hint_on_import_error(self):
        from praisonai.framework_adapters.registry import get_default_registry

        registry = get_default_registry()
        with patch(
            "praisonai.framework_adapters.validators.get_default_registry",
            return_value=registry,
        ), patch.object(registry, "create", side_effect=ImportError("missing dep")):
            with pytest.raises(ImportError, match="was requested but is not installed"):
                assert_framework_available("crewai")


class TestAssertFrameworkAvailableSucceeds:
    """Tests that no exception is raised for available frameworks."""

    def test_no_error_when_framework_available(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = True
            mock_get.return_value = mock_registry

            # Should not raise
            assert_framework_available("crewai")

    def test_returns_none_for_available_framework(self):
        with patch("praisonai.framework_adapters.validators.get_default_registry") as mock_get:
            mock_registry = MagicMock()
            mock_registry.is_available.return_value = True
            mock_get.return_value = mock_registry

            result = assert_framework_available("praisonai")
            assert result is None
