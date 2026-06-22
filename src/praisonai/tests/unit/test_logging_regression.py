"""
Regression tests for logging configuration violations.

Tests cover:
- inc/models.py should NOT call logging.basicConfig() at import time
- Root logger should not be mutated by module imports
- Logging configuration should be deferred to application entry points
"""

import logging
import importlib
import sys
import pytest
from unittest.mock import patch, MagicMock


class TestLoggingRegressions:
    """Regression tests for improper logging configuration at import time."""

    def test_inc_models_no_logging_basicconfig_at_import(self):
        """
        Regression test: inc/models.py should NOT call logging.basicConfig() during import.
        
        This was a critical architectural violation where inc/models.py mutated the root
        logger configuration at module load time, hijacking embedders' logging setup.
        """
        # Mock logging.basicConfig to detect if it's called
        with patch('logging.basicConfig') as mock_basicconfig:
            # Force reimport of inc.models to test import-time behavior
            module_name = 'praisonai.inc.models'
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            try:
                # Import the module - this should NOT call logging.basicConfig()
                import praisonai.inc.models
                
                # Verify logging.basicConfig() was not called during import
                mock_basicconfig.assert_not_called()
                
            except ImportError as e:
                pytest.skip(f"Could not import praisonai.inc.models: {e}")

    def test_root_logger_unchanged_after_import(self):
        """Verify that importing inc.models does not modify root logger configuration."""
        # Capture initial root logger state
        root_logger = logging.getLogger()
        initial_level = root_logger.level
        initial_handlers_count = len(root_logger.handlers)
        initial_handlers = root_logger.handlers.copy()
        
        # Force reimport to test import-time side effects
        module_name = 'praisonai.inc.models'
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        try:
            # Import should not change root logger
            import praisonai.inc.models
            
            # Verify root logger state is unchanged
            assert root_logger.level == initial_level, "Root logger level was modified"
            assert len(root_logger.handlers) == initial_handlers_count, "Root logger handlers were modified"
            assert root_logger.handlers == initial_handlers, "Root logger handlers list was modified"
            
        except ImportError as e:
            pytest.skip(f"Could not import praisonai.inc.models: {e}")

    def test_logging_module_import_order_independence(self):
        """
        Test that inc.models import doesn't interfere with logging setup regardless of import order.
        
        This tests the scenario where a user application has already configured logging
        before importing PraisonAI modules.
        """
        # Set up a custom logging configuration before import
        custom_logger = logging.getLogger("test_app")
        custom_handler = logging.StreamHandler()
        custom_handler.setLevel(logging.DEBUG)
        custom_logger.addHandler(custom_handler)
        custom_logger.setLevel(logging.DEBUG)
        
        # Force reimport after setting up custom logging
        module_name = 'praisonai.inc.models'
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        try:
            # Import should not interfere with existing logging setup
            import praisonai.inc.models
            
            # Custom logger should remain unchanged
            assert custom_logger.level == logging.DEBUG
            assert len(custom_logger.handlers) == 1
            assert custom_logger.handlers[0] is custom_handler
            
        except ImportError as e:
            pytest.skip(f"Could not import praisonai.inc.models: {e}")
        finally:
            # Cleanup
            custom_logger.removeHandler(custom_handler)

    def test_no_side_effects_on_repeated_imports(self):
        """Verify that repeated imports of inc.models don't accumulate side effects."""
        # Capture initial state
        root_logger = logging.getLogger()
        initial_handlers_count = len(root_logger.handlers)
        
        try:
            # Import multiple times
            import praisonai.inc.models
            importlib.reload(praisonai.inc.models)
            importlib.reload(praisonai.inc.models)
            
            # Should not accumulate handlers or other side effects
            assert len(root_logger.handlers) == initial_handlers_count
            
        except ImportError as e:
            pytest.skip(f"Could not import praisonai.inc.models: {e}")

    def test_module_level_logging_pattern_compliance(self):
        """
        Test that inc.models follows the correct logging pattern:
        - Get logger at module level: logger = logging.getLogger(__name__)
        - Do NOT configure logging at module level
        """
        try:
            import praisonai.inc.models as models_module
            
            # Module should have a logger instance
            assert hasattr(models_module, 'logger'), "Module should have a 'logger' attribute"
            
            # Logger should be correctly named for the module
            expected_name = 'praisonai.inc.models'
            assert models_module.logger.name == expected_name, f"Logger name should be {expected_name}"
            
            # Logger should be a proper Logger instance, not configured at module level
            assert isinstance(models_module.logger, logging.Logger)
            
        except ImportError as e:
            pytest.skip(f"Could not import praisonai.inc.models: {e}")

    def test_architectural_compliance_no_import_time_config(self):
        """
        Architectural compliance test: No PraisonAI module should configure logging at import.
        
        This is a broader architectural test to ensure the logging policy is followed
        across the codebase.
        """
        # List of modules that should not configure logging at import time
        modules_to_test = [
            'praisonai.inc.models',
            # Add other modules here as needed for broader coverage
        ]
        
        for module_name in modules_to_test:
            with patch('logging.basicConfig') as mock_basicconfig:
                # Force clean import
                if module_name in sys.modules:
                    del sys.modules[module_name]
                
                try:
                    importlib.import_module(module_name)
                    mock_basicconfig.assert_not_called()
                except ImportError:
                    # Skip modules that aren't available in test environment
                    continue


class TestLoggingPolicyDocumentation:
    """Tests that document and verify the correct logging policy."""

    def test_logging_policy_documentation(self):
        """
        Document the correct logging policy for PraisonAI modules:
        
        1. Modules should get loggers: logger = logging.getLogger(__name__)
        2. Modules should NOT configure logging at import time
        3. CLI entry points should configure logging via _logging.py
        4. Library users control their own logging configuration
        """
        # This test serves as documentation and verification
        
        # Correct pattern for modules:
        correct_logger_pattern = "logger = logging.getLogger(__name__)"
        
        # Incorrect pattern (what was fixed):
        incorrect_pattern = "logging.basicConfig()"
        
        # Verify the correct pattern works
        test_logger = logging.getLogger("test.module.name")
        assert isinstance(test_logger, logging.Logger)
        assert test_logger.name == "test.module.name"
        
        # Document that basicConfig should only be called by applications, not libraries
        with patch('logging.basicConfig') as mock_basicconfig:
            # This would be appropriate for an application entry point:
            # logging.basicConfig(level=logging.INFO)
            
            # But should NOT be called by library modules during import
            pass  # Library modules should not call this at all