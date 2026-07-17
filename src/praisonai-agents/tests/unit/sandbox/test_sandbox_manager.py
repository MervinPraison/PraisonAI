"""
Unit tests for SandboxManager.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from praisonaiagents.sandbox.manager import SandboxManager
from praisonaiagents.sandbox.config import SandboxConfig
from praisonaiagents.sandbox.protocols import SandboxResult, SandboxStatus


class TestSandboxManager:
    """Test SandboxManager functionality."""

    def test_init_default_config(self):
        manager = SandboxManager()
        assert manager.config is not None
        assert manager.config.sandbox_type == "subprocess"

    def test_init_with_config(self):
        config = SandboxConfig.docker("python:3.11")
        manager = SandboxManager(config)
        assert manager.config == config

    @patch('praisonaiagents.sandbox.manager.SandboxManager._create_sandbox')
    async def test_context_manager(self, mock_create_sandbox):
        mock_sandbox = AsyncMock()
        mock_create_sandbox.return_value = mock_sandbox

        manager = SandboxManager()

        async with manager as sandbox:
            assert sandbox == mock_sandbox
            mock_create_sandbox.assert_called_once()

        mock_sandbox.stop.assert_called_once()
        mock_sandbox.cleanup.assert_called_once()

    @patch('praisonaiagents.sandbox.manager.SandboxManager._create_sandbox')
    async def test_context_manager_cleanup_error(self, mock_create_sandbox):
        mock_sandbox = AsyncMock()
        mock_sandbox.stop.side_effect = Exception("Stop failed")
        mock_create_sandbox.return_value = mock_sandbox

        manager = SandboxManager()

        async with manager as sandbox:
            assert sandbox == mock_sandbox

        mock_sandbox.stop.assert_called_once()
        mock_sandbox.cleanup.assert_not_called()

    @patch('praisonaiagents.sandbox.manager.SandboxManager._create_sandbox')
    async def test_run_code_convenience_method(self, mock_create_sandbox):
        mock_sandbox = AsyncMock()
        mock_result = SandboxResult(status=SandboxStatus.COMPLETED, stdout="output")
        mock_sandbox.execute.return_value = mock_result
        mock_create_sandbox.return_value = mock_sandbox

        manager = SandboxManager()
        result = await manager.run_code("print('hello')", language="python")

        assert result == mock_result
        mock_sandbox.execute.assert_called_once_with("print('hello')", language="python")

    async def test_create_sandbox_subprocess(self):
        config = SandboxConfig.subprocess()
        manager = SandboxManager(config)

        mock_instance = AsyncMock()
        mock_instance.start = AsyncMock()
        mock_cls = Mock(return_value=mock_instance)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            return_value=mock_cls,
        ):
            sandbox = await manager._create_sandbox()

        mock_cls.assert_called_once_with(config=config)
        mock_instance.start.assert_called_once()
        assert sandbox is mock_instance

    async def test_create_sandbox_docker(self):
        config = SandboxConfig.docker("python:3.11")
        manager = SandboxManager(config)

        mock_instance = AsyncMock()
        mock_instance.start = AsyncMock()
        mock_cls = Mock(return_value=mock_instance)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            return_value=mock_cls,
        ):
            sandbox = await manager._create_sandbox()

        mock_cls.assert_called_once_with(config=config, image="python:3.11")
        assert sandbox is mock_instance

    async def test_create_sandbox_e2b(self):
        config = SandboxConfig.e2b()
        manager = SandboxManager(config)

        mock_instance = AsyncMock()
        mock_instance.start = AsyncMock()
        mock_cls = Mock(return_value=mock_instance)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            return_value=mock_cls,
        ):
            sandbox = await manager._create_sandbox()

        mock_cls.assert_called_once_with(config=config)
        assert sandbox is mock_instance

    async def test_create_sandbox_unknown_type(self):
        config = SandboxConfig(sandbox_type="totally_unknown_backend")
        manager = SandboxManager(config)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            side_effect=ValueError("Unknown plugin"),
        ):
            with pytest.raises(ValueError, match="Unknown sandbox type"):
                await manager._create_sandbox()

    async def test_create_sandbox_registry_plugin(self):
        config = SandboxConfig.capsule()
        manager = SandboxManager(config)

        mock_instance = AsyncMock()
        mock_instance.start = AsyncMock()
        mock_cls = Mock(return_value=mock_instance)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            return_value=mock_cls,
        ) as mock_resolve:
            sandbox = await manager._create_sandbox()

        mock_resolve.assert_called_once_with("capsule")
        mock_cls.assert_called_once_with(config=config)
        mock_instance.start.assert_called_once()
        assert sandbox is mock_instance

    async def test_create_sandbox_registry_import_error(self):
        config = SandboxConfig(sandbox_type="totally_unknown_backend")
        manager = SandboxManager(config)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            side_effect=ImportError("No module named 'praisonai_sandbox'"),
        ):
            with pytest.raises(ImportError):
                await manager._create_sandbox()

    def test_config_capsule_factory(self):
        config = SandboxConfig.capsule()
        assert config.sandbox_type == "capsule"
        assert config.security_policy.allow_network is False

    async def test_create_sandbox_unavailable(self):
        config = SandboxConfig.docker("python:3.11")
        manager = SandboxManager(config)

        mock_instance = Mock()
        mock_instance.is_available = False
        mock_cls = Mock(return_value=mock_instance)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            return_value=mock_cls,
        ):
            with pytest.raises(RuntimeError, match="not available"):
                await manager._create_sandbox()

    async def test_create_sandbox_import_error(self):
        config = SandboxConfig.e2b()
        manager = SandboxManager(config)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            side_effect=ImportError("Module not found"),
        ):
            with pytest.raises(ImportError, match="praisonai-sandbox"):
                await manager._create_sandbox()

    def test_get_available_types(self):
        manager = SandboxManager()

        mock_registry = Mock()
        mock_registry.list_names.return_value = ["subprocess", "docker"]

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.get_sandbox_registry',
        ) as mock_get_registry:
            mock_get_registry.return_value.default.return_value = mock_registry
            available = manager.get_available_types()

        assert "subprocess" in available
        assert "docker" in available
        assert isinstance(available["subprocess"], dict)

    async def test_create_sandbox_native_alias(self):
        config = SandboxConfig(sandbox_type="native")
        manager = SandboxManager(config)

        mock_instance = AsyncMock()
        mock_instance.start = AsyncMock()
        mock_cls = Mock(return_value=mock_instance)

        with patch(
            'praisonaiagents.sandbox._sandbox_bridge.resolve_sandbox_class',
            return_value=mock_cls,
        ) as mock_resolve:
            await manager._create_sandbox()

        mock_resolve.assert_called_once_with("sandlock")
