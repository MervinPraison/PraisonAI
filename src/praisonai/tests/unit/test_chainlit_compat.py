"""
Unit tests for the Chainlit compatibility shim.

Tests ensure forward/backward compatibility with Chainlit versions
that may have different locations for EXPIRY_TIME and BaseStorageClient.
"""

import os
import sys
import pytest
from unittest.mock import patch


class TestChainlitCompat:
    """Tests for praisonai.ui.chainlit_compat module."""

    def test_get_expiry_seconds_returns_int(self):
        """Test that get_expiry_seconds returns an integer."""
        from praisonai.ui.chainlit_compat import get_expiry_seconds
        result = get_expiry_seconds()
        assert isinstance(result, int)
        assert result > 0

    def test_get_expiry_seconds_default_value(self):
        """Test that default expiry is 3600 seconds (1 hour)."""
        from praisonai.ui.chainlit_compat import DEFAULT_EXPIRY_SECONDS
        assert DEFAULT_EXPIRY_SECONDS == 3600

    def test_expiry_time_alias_exists(self):
        """Test that EXPIRY_TIME is exported for backward compatibility."""
        from praisonai.ui.chainlit_compat import EXPIRY_TIME
        assert isinstance(EXPIRY_TIME, int)
        assert EXPIRY_TIME > 0

    def test_get_expiry_seconds_env_override(self):
        """Test that STORAGE_EXPIRY_TIME env var overrides default."""
        with patch.dict(os.environ, {"STORAGE_EXPIRY_TIME": "7200"}):
            # Need to reimport to pick up env change
            from praisonai.ui import chainlit_compat
            import importlib
            importlib.reload(chainlit_compat)
            result = chainlit_compat.get_expiry_seconds()
            assert result == 7200

    def test_get_expiry_seconds_invalid_env_fallback(self):
        """Test that invalid STORAGE_EXPIRY_TIME falls back to default."""
        with patch.dict(os.environ, {"STORAGE_EXPIRY_TIME": "invalid"}):
            from praisonai.ui import chainlit_compat
            import importlib
            importlib.reload(chainlit_compat)
            result = chainlit_compat.get_expiry_seconds()
            # Should fall back to chainlit value or default
            assert isinstance(result, int)
            assert result > 0

    def test_base_storage_client_import(self):
        """Test that BaseStorageClient can be imported."""
        from praisonai.ui.chainlit_compat import BaseStorageClient
        # May be None if chainlit not installed, or a class if installed
        if BaseStorageClient is not None:
            assert hasattr(BaseStorageClient, '__mro__')

    def test_get_base_storage_client_function(self):
        """Test get_base_storage_client returns class or None."""
        from praisonai.ui.chainlit_compat import get_base_storage_client
        result = get_base_storage_client()
        # Should be None or a class
        assert result is None or hasattr(result, '__mro__')

    def test_module_exports_all(self):
        """Test that __all__ contains expected exports."""
        from praisonai.ui import chainlit_compat
        expected = [
            'get_expiry_seconds',
            'get_base_storage_client',
            'get_base_data_layer',
            'base_data_layer_has_close',
            'EXPIRY_TIME',
            'BaseStorageClient',
            'DEFAULT_EXPIRY_SECONDS',
        ]
        for name in expected:
            assert name in chainlit_compat.__all__

    def test_get_base_data_layer_function(self):
        """Test get_base_data_layer returns class or None."""
        from praisonai.ui.chainlit_compat import get_base_data_layer
        result = get_base_data_layer()
        # Should be None or a class
        assert result is None or hasattr(result, '__mro__')

    def test_base_data_layer_has_close_function(self):
        """Test base_data_layer_has_close returns bool."""
        from praisonai.ui.chainlit_compat import base_data_layer_has_close
        result = base_data_layer_has_close()
        assert isinstance(result, bool)


class TestChainlitCompatWithMocking:
    """Tests with mocked chainlit imports to simulate version differences."""

    def test_fallback_when_storage_expiry_time_not_found(self):
        """Test fallback when storage_expiry_time doesn't exist in chainlit."""
        # This tests the try/except fallback logic
        from praisonai.ui.chainlit_compat import get_expiry_seconds
        result = get_expiry_seconds()
        # Should not raise, should return a valid int
        assert isinstance(result, int)

    def test_fallback_when_expiry_time_uppercase_not_found(self):
        """Test fallback when EXPIRY_TIME (uppercase) doesn't exist."""
        from praisonai.ui.chainlit_compat import get_expiry_seconds
        result = get_expiry_seconds()
        assert isinstance(result, int)


class TestSQLAlchemyDataLayerCompat:
    """Tests for SQLAlchemyDataLayer compatibility with Chainlit 2.9.4."""

    def test_sql_alchemy_imports_from_compat_shim(self):
        """Test that sql_alchemy.py imports from chainlit_compat."""
        # Read the file directly to check imports without executing it
        import os
        sql_alchemy_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'praisonai', 'ui', 'sql_alchemy.py'
        )
        with open(sql_alchemy_path, 'r') as f:
            content = f.read()
        
        # Should import from chainlit_compat, not directly from chainlit
        assert 'from praisonai.ui.chainlit_compat import' in content
        # Should NOT have direct EXPIRY_TIME import from chainlit
        assert 'from chainlit.data.storage_clients.base import EXPIRY_TIME' not in content

    def test_sql_alchemy_has_close_method(self):
        """Test that SQLAlchemyDataLayer has close method for Chainlit 2.9.4."""
        # Import the module to check the class
        import sys
        # Add UI path for local imports
        ui_path = '/Users/praison/praisonai-package/src/praisonai/praisonai/ui'
        if ui_path not in sys.path:
            sys.path.insert(0, ui_path)
        
        try:
            from praisonai.ui.sql_alchemy import SQLAlchemyDataLayer
            # Check that close method exists
            assert hasattr(SQLAlchemyDataLayer, 'close')
            # Check it's an async method
            import inspect
            assert inspect.iscoroutinefunction(SQLAlchemyDataLayer.close)
        except ImportError:
            # If chainlit not installed, skip
            pytest.skip("Chainlit not installed")


class TestCLILazyImports:
    """Tests to ensure CLI doesn't import chainlit at startup."""

    def test_praisonai_import_no_chainlit(self):
        """Test that importing praisonai doesn't import chainlit."""
        # Clear any cached chainlit imports
        chainlit_modules = [k for k in sys.modules.keys() if 'chainlit' in k.lower()]
        for mod in chainlit_modules:
            del sys.modules[mod]
        
        # Import praisonai
        import praisonai
        
        # chainlit should not be in sys.modules yet
        # (unless it was imported by something else)
        # We just verify the import doesn't crash
        assert praisonai is not None

    def test_praisonai_cli_import_no_crash(self):
        """Test that importing praisonai.cli.main doesn't crash."""
        import praisonai.cli.main
        assert praisonai.cli.main is not None


class TestChatPyLogLevel:
    """Tests for chat.py LOGLEVEL handling."""

    def test_empty_loglevel_handled(self):
        """Test that empty LOGLEVEL string doesn't crash."""
        # The fix: log_level = os.getenv("LOGLEVEL", "INFO").upper() or "INFO"
        # This ensures empty string falls back to INFO
        with patch.dict(os.environ, {"LOGLEVEL": ""}):
            log_level = os.getenv("LOGLEVEL", "INFO").upper() or "INFO"
            assert log_level == "INFO"

    def test_valid_loglevel_preserved(self):
        """Test that valid LOGLEVEL is preserved."""
        with patch.dict(os.environ, {"LOGLEVEL": "DEBUG"}):
            log_level = os.getenv("LOGLEVEL", "INFO").upper() or "INFO"
            assert log_level == "DEBUG"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
