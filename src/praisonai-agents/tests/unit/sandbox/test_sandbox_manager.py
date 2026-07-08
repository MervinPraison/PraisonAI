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
        """Test initialization with default config."""
        manager = SandboxManager()
        assert manager.config is not None
        assert manager.config.sandbox_type == "subprocess"

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = SandboxConfig.docker("python:3.11")
        manager = SandboxManager(config)
        assert manager.config == config

    @patch('praisonaiagents.sandbox.manager.SandboxManager._create_sandbox')
    async def test_context_manager(self, mock_create_sandbox):
        """Test SandboxManager as async context manager."""
        mock_sandbox = AsyncMock()
        mock_create_sandbox.return_value = mock_sandbox
        
        manager = SandboxManager()
        
        async with manager as sandbox:
            assert sandbox == mock_sandbox
            mock_create_sandbox.assert_called_once()
        
        # Cleanup should be called
        mock_sandbox.stop.assert_called_once()
        mock_sandbox.cleanup.assert_called_once()

    @patch('praisonaiagents.sandbox.manager.SandboxManager._create_sandbox')
    async def test_context_manager_cleanup_error(self, mock_create_sandbox):
        """Test context manager cleanup with error."""
        mock_sandbox = AsyncMock()
        mock_sandbox.stop.side_effect = Exception("Stop failed")
        mock_create_sandbox.return_value = mock_sandbox
        
        manager = SandboxManager()
        
        # Should not raise exception, just log warning
        async with manager as sandbox:
            assert sandbox == mock_sandbox
        
        mock_sandbox.stop.assert_called_once()
        mock_sandbox.cleanup.assert_called_once()

    @patch('praisonaiagents.sandbox.manager.SandboxManager._create_sandbox')
    async def test_run_code_convenience_method(self, mock_create_sandbox):
        """Test run_code convenience method."""
        mock_sandbox = AsyncMock()
        mock_result = SandboxResult(status=SandboxStatus.COMPLETED, stdout="output")
        mock_sandbox.execute.return_value = mock_result
        mock_create_sandbox.return_value = mock_sandbox
        
        manager = SandboxManager()
        
        result = await manager.run_code("print('hello')", language="python")
        
        assert result == mock_result
        mock_sandbox.execute.assert_called_once_with("print('hello')", language="python")

    async def test_create_sandbox_subprocess(self):
        """Test creating subprocess sandbox."""
        config = SandboxConfig.subprocess()
        manager = SandboxManager(config)
        
        with patch('praisonai.sandbox.subprocess.SubprocessSandbox') as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance
            mock_instance.is_available = True
            
            sandbox = await manager._create_sandbox()
            
            mock_class.assert_called_once_with(config)
            assert sandbox == mock_instance

    async def test_create_sandbox_docker(self):
        """Test creating Docker sandbox."""
        config = SandboxConfig.docker("python:3.11")
        manager = SandboxManager(config)
        
        with patch('praisonai.sandbox.docker.DockerSandbox') as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance
            mock_instance.is_available = True
            
            sandbox = await manager._create_sandbox()
            
            mock_class.assert_called_once_with(config)
            assert sandbox == mock_instance

    async def test_create_sandbox_e2b(self):
        """Test creating E2B sandbox."""
        config = SandboxConfig.e2b()
        manager = SandboxManager(config)
        
        with patch('praisonai.sandbox.e2b.E2BSandbox') as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance
            mock_instance.is_available = True
            
            sandbox = await manager._create_sandbox()
            
            mock_class.assert_called_once_with(config)
            assert sandbox == mock_instance

    async def test_create_sandbox_unknown_type(self):
        """Test creating sandbox with unknown type fails via registry."""
        config = SandboxConfig(sandbox_type="totally_unknown_backend")
        manager = SandboxManager(config)

        mock_registry = Mock()
        mock_registry.resolve.side_effect = ValueError(
            "Unknown praisonai.sandbox plugin: 'totally_unknown_backend'"
        )
        mock_registry.list_names.return_value = ["docker", "subprocess"]

        with patch("praisonai.sandbox._registry.SandboxRegistry.default", return_value=mock_registry):
            with pytest.raises(ValueError, match="Unknown sandbox type"):
                await manager._create_sandbox()

    async def test_create_sandbox_registry_plugin(self):
        """Test plugin sandbox types resolve via praisonai.sandbox registry."""
        config = SandboxConfig.capsule()
        manager = SandboxManager(config)

        mock_instance = AsyncMock()
        mock_instance.is_available = True
        mock_cls = Mock(return_value=mock_instance)

        mock_registry = Mock()
        mock_registry.resolve.return_value = mock_cls

        with patch("praisonai.sandbox._registry.SandboxRegistry.default", return_value=mock_registry):
            sandbox = await manager._create_sandbox()

        mock_registry.resolve.assert_called_once_with("capsule")
        mock_cls.assert_called_once_with(config=config)
        mock_instance.start.assert_called_once()
        assert sandbox is mock_instance

    async def test_create_sandbox_unavailable(self):
        """Test creating sandbox when not available."""
        config = SandboxConfig.docker("python:3.11")
        manager = SandboxManager(config)
        
        with patch('praisonai.sandbox.docker.DockerSandbox') as mock_class:
            mock_instance = Mock()
            mock_instance.is_available = False
            mock_class.return_value = mock_instance
            
            with pytest.raises(RuntimeError, match="not available"):
                await manager._create_sandbox()

    async def test_create_sandbox_import_error(self):
        """Test creating sandbox with import error."""
        config = SandboxConfig.e2b()
        manager = SandboxManager(config)
        
        with patch('importlib.import_module', side_effect=ImportError("Module not found")):
            with pytest.raises(ImportError, match="Module not found"):
                await manager._create_sandbox()

    def test_get_available_types(self):
        """Test getting available sandbox types."""
        manager = SandboxManager()
        
        with patch('praisonaiagents.sandbox.manager.SandboxManager._check_availability') as mock_check:
            mock_check.side_effect = lambda t: t in ["subprocess", "docker"]
            
            available = manager.get_available_types()
            
            assert "subprocess" in available
            assert available["subprocess"] is True
            assert "docker" in available
            assert available["docker"] is True
            assert "e2b" in available
            assert available["e2b"] is False

    def test_check_availability_subprocess(self):
        """Test checking subprocess availability."""
        manager = SandboxManager()
        
        # Subprocess should always be available
        available = manager._check_availability("subprocess")
        assert available is True

    def test_check_availability_docker(self):
        """Test checking Docker availability."""
        manager = SandboxManager()
        
        with patch('importlib.import_module') as mock_import:
            with patch.object(mock_import.return_value, 'DockerSandbox') as mock_class:
                mock_instance = Mock()
                mock_instance.is_available = True
                mock_class.return_value = mock_instance
                
                available = manager._check_availability("docker")
                assert available is True

    def test_check_availability_not_available(self):
        """Test checking availability when not available."""
        manager = SandboxManager()
        
        with patch('importlib.import_module', side_effect=ImportError()):
            available = manager._check_availability("docker")
            assert available is False

    def test_check_availability_unknown(self):
        """Test checking availability for unknown type."""
        manager = SandboxManager()
        
        available = manager._check_availability("unknown")
        assert available is False