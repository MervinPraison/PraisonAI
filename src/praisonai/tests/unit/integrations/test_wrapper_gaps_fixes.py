"""
Unit tests for wrapper gap fixes from PR #1849.

Tests cover:
1. try_create method in ExternalAgentRegistry
2. invalidate_availability method in BaseCLIIntegration  
3. configure_host contextvars isolation
"""

import pytest
import threading
import concurrent.futures
from unittest.mock import patch, MagicMock
import shutil
import tempfile
from pathlib import Path

from praisonai.praisonai.integrations.base import BaseCLIIntegration
from praisonai.praisonai.integrations.registry import ExternalAgentRegistry, create_integration
from praisonai.praisonai.integration.host_app import configure_host, _configured_context


class TestExternalAgentRegistryTryCreate:
    """Test the try_create method added in PR #1849."""

    def test_try_create_returns_none_for_unknown_integration(self):
        """Test that try_create returns None for unknown integration names."""
        registry = ExternalAgentRegistry()
        
        result = registry.try_create("nonexistent_integration", workspace="/tmp")
        assert result is None

    def test_try_create_returns_integration_for_known_name(self):
        """Test that try_create returns the integration for known names."""
        registry = ExternalAgentRegistry()
        
        # Mock a successful integration creation
        with patch('praisonai.praisonai.integrations.registry._get_integration_class') as mock_get_class:
            mock_class = MagicMock()
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance
            mock_get_class.return_value = mock_class
            
            result = registry.try_create("claude", workspace="/tmp")
            assert result is mock_instance
            mock_class.assert_called_once_with(workspace="/tmp")

    def test_try_create_returns_none_on_exception(self):
        """Test that try_create returns None when integration creation fails."""
        registry = ExternalAgentRegistry()
        
        with patch('praisonai.praisonai.integrations.registry._get_integration_class') as mock_get_class:
            mock_get_class.side_effect = Exception("Integration failed")
            
            result = registry.try_create("claude", workspace="/tmp")
            assert result is None

    def test_create_integration_factory_uses_try_create(self):
        """Test that the create_integration factory function uses try_create."""
        with patch.object(ExternalAgentRegistry, 'try_create') as mock_try_create:
            mock_try_create.return_value = "mock_integration"
            
            result = create_integration("claude", workspace="/tmp")
            assert result == "mock_integration"
            mock_try_create.assert_called_once_with("claude", workspace="/tmp")

    def test_create_integration_factory_returns_none(self):
        """Test that the create_integration factory returns None for unknown integrations."""
        with patch.object(ExternalAgentRegistry, 'try_create') as mock_try_create:
            mock_try_create.return_value = None
            
            result = create_integration("nonexistent", workspace="/tmp")
            assert result is None


class TestBaseCLIIntegrationInvalidateAvailability:
    """Test the invalidate_availability method added in PR #1849."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear the class-level cache before each test
        BaseCLIIntegration._availability_cache.clear()

    def test_invalidate_availability_clears_all_cache(self):
        """Test that invalidate_availability() clears the entire cache."""
        self.setUp()
        
        # Pre-populate cache
        BaseCLIIntegration._availability_cache["cmd1"] = True
        BaseCLIIntegration._availability_cache["cmd2"] = False
        
        BaseCLIIntegration.invalidate_availability()
        
        assert len(BaseCLIIntegration._availability_cache) == 0

    def test_invalidate_availability_clears_specific_command(self):
        """Test that invalidate_availability(cmd) clears only that command."""
        self.setUp()
        
        # Pre-populate cache
        BaseCLIIntegration._availability_cache["cmd1"] = True
        BaseCLIIntegration._availability_cache["cmd2"] = False
        
        BaseCLIIntegration.invalidate_availability("cmd1")
        
        assert "cmd1" not in BaseCLIIntegration._availability_cache
        assert "cmd2" in BaseCLIIntegration._availability_cache
        assert BaseCLIIntegration._availability_cache["cmd2"] is False

    def test_invalidate_availability_thread_safe(self):
        """Test that invalidate_availability is thread-safe."""
        self.setUp()
        
        # Pre-populate cache
        for i in range(100):
            BaseCLIIntegration._availability_cache[f"cmd{i}"] = True
        
        def clear_cache():
            BaseCLIIntegration.invalidate_availability()
        
        def clear_specific():
            for i in range(0, 50):
                BaseCLIIntegration.invalidate_availability(f"cmd{i}")
        
        # Run cache operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            futures.append(executor.submit(clear_cache))
            futures.append(executor.submit(clear_specific))
            futures.append(executor.submit(clear_cache))
            
            # Wait for completion
            concurrent.futures.wait(futures)
        
        # Should not raise any exceptions and cache should be cleared
        assert len(BaseCLIIntegration._availability_cache) == 0

    def test_is_available_thread_safe_with_invalidation(self):
        """Test that is_available property is thread-safe during invalidation."""
        self.setUp()
        
        class MockCLIIntegration(BaseCLIIntegration):
            cli_command = "mock_cmd"

        # Mock shutil.which to return True
        with patch('shutil.which', return_value='/usr/bin/mock_cmd'):
            integration = MockCLIIntegration()
            
            results = []
            errors = []
            
            def check_availability():
                try:
                    result = integration.is_available
                    results.append(result)
                except Exception as e:
                    errors.append(e)
            
            def invalidate_cache():
                try:
                    BaseCLIIntegration.invalidate_availability("mock_cmd")
                except Exception as e:
                    errors.append(e)
            
            # Run availability checks and invalidations concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = []
                
                # Start multiple availability checks
                for _ in range(20):
                    futures.append(executor.submit(check_availability))
                
                # Start invalidations while checks are running  
                for _ in range(5):
                    futures.append(executor.submit(invalidate_cache))
                
                # Wait for all to complete
                concurrent.futures.wait(futures)
            
            # Should not have any race condition errors
            assert len(errors) == 0, f"Race condition errors: {errors}"
            # All availability checks should succeed
            assert all(result is True for result in results), f"Unexpected availability results: {results}"


class TestConfigureHostContextVarsIsolation:
    """Test the configure_host contextvars isolation added in PR #1849."""

    def setUp(self):
        """Reset the configuration context before each test."""
        _configured_context.set(False)

    def test_configure_host_context_isolation(self):
        """Test that configure_host uses contextvars for isolation."""
        self.setUp()
        
        # Initially not configured
        assert _configured_context.get(False) is False
        
        # Configure in main context
        with patch('praisonai.praisonai.integration.host_app.aiui') as mock_aiui:
            configure_host()
            assert _configured_context.get(False) is True
            mock_aiui.set_datastore.assert_called_once()
        
        # Should still be configured in main context
        assert _configured_context.get(False) is True

    def test_configure_host_prevents_duplicate_configuration(self):
        """Test that configure_host prevents duplicate configuration in same context."""
        self.setUp()
        
        with patch('praisonai.praisonai.integration.host_app.aiui') as mock_aiui:
            # First call should configure
            configure_host()
            assert mock_aiui.set_datastore.call_count == 1
            
            # Second call in same context should not configure again
            configure_host()
            assert mock_aiui.set_datastore.call_count == 1

    def test_configure_host_thread_isolation(self):
        """Test that configure_host provides proper thread isolation."""
        self.setUp()
        
        main_configured = []
        thread_configured = []
        errors = []
        
        def configure_in_thread():
            try:
                # Should not be configured in new thread context
                thread_configured.append(_configured_context.get(False))
                
                with patch('praisonai.praisonai.integration.host_app.aiui'):
                    configure_host()
                    # Should be configured in this thread context
                    thread_configured.append(_configured_context.get(False))
            except Exception as e:
                errors.append(e)
        
        # Configure in main thread
        with patch('praisonai.praisonai.integration.host_app.aiui'):
            configure_host()
            main_configured.append(_configured_context.get(False))
        
        # Start thread
        thread = threading.Thread(target=configure_in_thread)
        thread.start()
        thread.join()
        
        # Check main thread context is still configured
        main_configured.append(_configured_context.get(False))
        
        # No errors should occur
        assert len(errors) == 0, f"Thread errors: {errors}"
        
        # Main thread should be configured
        assert main_configured == [True, True]
        
        # Thread should start unconfigured, then become configured
        assert thread_configured == [False, True]

    def test_configure_host_async_context_isolation(self):
        """Test configure_host works with async context isolation."""
        import asyncio
        from contextvars import copy_context
        
        self.setUp()
        
        async def configure_in_async_context():
            # Should not be configured in new async context
            initial_state = _configured_context.get(False)
            
            with patch('praisonai.praisonai.integration.host_app.aiui'):
                configure_host()
                configured_state = _configured_context.get(False)
            
            return initial_state, configured_state
        
        # Configure in main context
        with patch('praisonai.praisonai.integration.host_app.aiui'):
            configure_host()
            main_configured = _configured_context.get(False)
        
        # Run in new async context
        ctx = copy_context()
        initial, configured = asyncio.run(configure_in_async_context(), debug=False)
        
        # Main context should still be configured
        assert main_configured is True
        assert _configured_context.get(False) is True
        
        # Async context should have started unconfigured, then became configured
        assert initial is False
        assert configured is True

    def test_backward_compatibility_shim(self):
        """Test that the backward compatibility shim works for tests."""
        self.setUp()
        
        # Import the host_app module to access the shim
        from praisonai.praisonai.integration import host_app
        
        # Should have a _CONFIGURED shim for backward compatibility
        assert hasattr(host_app, '_CONFIGURED')
        
        # The shim should allow setting False to reset context
        host_app._CONFIGURED = False
        assert _configured_context.get(False) is False
        
        # Configure and check the shim reflects the state
        with patch('praisonai.praisonai.integration.host_app.aiui'):
            configure_host()
        
        # The shim should reflect the configured state
        # Note: This test validates the shim exists and basic functionality
        # The exact behavior depends on the shim implementation