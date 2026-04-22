"""
Tests for bind-aware UI authentication.

This module tests that UI components refuse default admin/admin credentials
on external interfaces unless the escape hatch is explicitly enabled.
"""

import pytest
import os
from unittest.mock import patch, MagicMock

from praisonai.ui._auth import (
    UIAuthEnforcer,
    UIStartupError,
    register_password_auth,
)


class TestUIAuthEnforcer:
    """Test the UIAuthEnforcer implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.enforcer = UIAuthEnforcer()
    
    def test_default_creds_on_loopback_with_warning(self):
        """Test that default credentials on loopback are allowed with warning."""
        # Should not raise (warning only)
        self.enforcer.validate_credentials_config(
            bind_host="127.0.0.1",
            username="admin",
            password="admin",
            allow_defaults=False
        )
    
    def test_default_creds_on_external_raises_error(self):
        """Test that default credentials on external interface raise error."""
        with pytest.raises(UIStartupError) as excinfo:
            self.enforcer.validate_credentials_config(
                bind_host="0.0.0.0",
                username="admin",
                password="admin",
                allow_defaults=False
            )
        
        assert "Cannot use default admin/admin credentials on external interface" in str(excinfo.value)
        assert "Set CHAINLIT_USERNAME and CHAINLIT_PASSWORD" in str(excinfo.value)
        assert "PRAISONAI_ALLOW_DEFAULT_CREDS=1" in str(excinfo.value)
    
    def test_default_creds_on_external_with_escape_hatch(self):
        """Test that default credentials on external interface work with escape hatch."""
        # Should not raise with escape hatch
        self.enforcer.validate_credentials_config(
            bind_host="0.0.0.0",
            username="admin",
            password="admin",
            allow_defaults=True
        )
    
    def test_custom_creds_on_external_is_valid(self):
        """Test that custom credentials on external interface are valid."""
        # Should not raise
        self.enforcer.validate_credentials_config(
            bind_host="0.0.0.0",
            username="myuser",
            password="mypassword",
            allow_defaults=False
        )
    
    def test_custom_creds_on_loopback_is_valid(self):
        """Test that custom credentials on loopback are valid."""
        # Should not raise
        self.enforcer.validate_credentials_config(
            bind_host="127.0.0.1",
            username="myuser",
            password="mypassword",
            allow_defaults=False
        )
    
    def test_check_auth_callback_with_correct_credentials(self):
        """Test auth callback with correct credentials."""
        assert self.enforcer.check_auth_callback(
            bind_host="127.0.0.1",
            provided_username="admin",
            provided_password="admin",
            expected_username="admin",
            expected_password="admin"
        ) is True
        
        assert self.enforcer.check_auth_callback(
            bind_host="0.0.0.0",
            provided_username="myuser",
            provided_password="mypass",
            expected_username="myuser",
            expected_password="mypass"
        ) is True
    
    def test_check_auth_callback_with_incorrect_credentials(self):
        """Test auth callback with incorrect credentials."""
        assert self.enforcer.check_auth_callback(
            bind_host="127.0.0.1",
            provided_username="admin",
            provided_password="wrong",
            expected_username="admin",
            expected_password="admin"
        ) is False
        
        assert self.enforcer.check_auth_callback(
            bind_host="0.0.0.0",
            provided_username="wrong",
            provided_password="admin",
            expected_username="admin",
            expected_password="admin"
        ) is False


class TestRegisterPasswordAuth:
    """Test the register_password_auth function."""
    
    @patch('praisonai.ui._auth.cl')
    @patch.dict(os.environ, {}, clear=True)
    def test_default_credentials_on_loopback(self, mock_cl):
        """Test registration with default credentials on loopback."""
        # Should not raise
        register_password_auth(None, bind_host="127.0.0.1")
        
        # Should have registered a callback
        mock_cl.password_auth_callback.assert_called_once()
    
    @patch('praisonai.ui._auth.cl')
    @patch.dict(os.environ, {}, clear=True)
    def test_default_credentials_on_external_raises_error(self, mock_cl):
        """Test registration with default credentials on external interface raises error."""
        with pytest.raises(RuntimeError) as excinfo:
            register_password_auth(None, bind_host="0.0.0.0")
        
        assert "Cannot use default admin/admin credentials on external interface" in str(excinfo.value)
    
    @patch('praisonai.ui._auth.cl')
    @patch.dict(os.environ, {"PRAISONAI_ALLOW_DEFAULT_CREDS": "1"}, clear=True)
    def test_default_credentials_on_external_with_escape_hatch(self, mock_cl):
        """Test registration with default credentials on external interface with escape hatch."""
        # Should not raise with escape hatch
        register_password_auth(None, bind_host="0.0.0.0")
        
        # Should have registered a callback
        mock_cl.password_auth_callback.assert_called_once()
    
    @patch('praisonai.ui._auth.cl')
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "myuser",
        "CHAINLIT_PASSWORD": "mypassword"
    }, clear=True)
    def test_custom_credentials_on_external(self, mock_cl):
        """Test registration with custom credentials on external interface."""
        # Should not raise
        register_password_auth(None, bind_host="0.0.0.0")
        
        # Should have registered a callback
        mock_cl.password_auth_callback.assert_called_once()
    
    @patch('praisonai.ui._auth.cl')
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "myuser",
        "CHAINLIT_PASSWORD": "mypassword"
    }, clear=True)
    def test_auth_callback_functionality(self, mock_cl):
        """Test that the registered auth callback works correctly."""
        register_password_auth(None, bind_host="127.0.0.1")
        
        # Get the registered callback function
        callback = mock_cl.password_auth_callback.call_args[0][0]
        
        # Mock User class
        mock_user = MagicMock()
        mock_cl.User.return_value = mock_user
        
        # Test correct credentials
        result = callback("myuser", "mypassword")
        assert result == mock_user
        mock_cl.User.assert_called_with(
            identifier="myuser",
            metadata={"role": "admin", "provider": "credentials"}
        )
        
        # Test incorrect credentials
        result = callback("wrong", "credentials")
        assert result is None


class TestEnvironmentVariables:
    """Test handling of environment variables."""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_default_environment(self):
        """Test behavior with default environment (no vars set)."""
        enforcer = UIAuthEnforcer()
        
        # Should allow default creds on loopback
        enforcer.validate_credentials_config(
            bind_host="127.0.0.1",
            username="admin",
            password="admin",
            allow_defaults=False
        )
        
        # Should reject default creds on external
        with pytest.raises(UIStartupError):
            enforcer.validate_credentials_config(
                bind_host="0.0.0.0",
                username="admin",
                password="admin",
                allow_defaults=False
            )
    
    @patch.dict(os.environ, {"PRAISONAI_ALLOW_DEFAULT_CREDS": "true"}, clear=True)
    def test_escape_hatch_true_values(self):
        """Test various true values for the escape hatch."""
        enforcer = UIAuthEnforcer()
        
        # Should allow default creds on external with escape hatch
        enforcer.validate_credentials_config(
            bind_host="0.0.0.0",
            username="admin",
            password="admin",
            allow_defaults=True  # This would be set based on env var parsing
        )
    
    @patch.dict(os.environ, {"PRAISONAI_ALLOW_DEFAULT_CREDS": "false"}, clear=True)
    def test_escape_hatch_false_values(self):
        """Test false values for the escape hatch."""
        enforcer = UIAuthEnforcer()
        
        # Should reject default creds on external even with env var set to false
        with pytest.raises(UIStartupError):
            enforcer.validate_credentials_config(
                bind_host="0.0.0.0",
                username="admin",
                password="admin",
                allow_defaults=False  # This would be set based on env var parsing
            )


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_credentials(self):
        """Test behavior with empty credentials."""
        enforcer = UIAuthEnforcer()
        
        # Empty credentials should not be treated as default
        enforcer.validate_credentials_config(
            bind_host="0.0.0.0",
            username="",
            password="",
            allow_defaults=False
        )
    
    def test_none_credentials(self):
        """Test behavior with None credentials."""
        enforcer = UIAuthEnforcer()
        
        # None credentials should not be treated as default
        enforcer.validate_credentials_config(
            bind_host="0.0.0.0",
            username=None,
            password=None,
            allow_defaults=False
        )
    
    def test_case_sensitive_default_detection(self):
        """Test that default credential detection is case-sensitive."""
        enforcer = UIAuthEnforcer()
        
        # "Admin" != "admin" - should not trigger default credential error
        enforcer.validate_credentials_config(
            bind_host="0.0.0.0",
            username="Admin",
            password="admin",
            allow_defaults=False
        )
        
        enforcer.validate_credentials_config(
            bind_host="0.0.0.0",
            username="admin",
            password="Admin",
            allow_defaults=False
        )


if __name__ == "__main__":
    pytest.main([__file__])