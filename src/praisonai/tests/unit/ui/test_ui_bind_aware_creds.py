"""
Unit tests for UI bind-aware credential enforcement.

Tests that UI refuses default admin/admin credentials on external interfaces.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

pytest.importorskip("chainlit", reason="chainlit is an optional [ui] extra")

from praisonai.ui._auth import register_password_auth, UIStartupError


class TestUIAuthValidation:
    """Test UI authentication validation logic."""
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "admin",
        "CHAINLIT_PASSWORD": "admin",
        "PRAISONAI_ALLOW_DEFAULT_CREDS": ""
    })
    def test_default_creds_on_loopback_warns_only(self):
        """Test default credentials on loopback show warning but allow start."""
        mock_app = MagicMock()
        
        # Should not raise exception on loopback
        register_password_auth(mock_app, bind_host="127.0.0.1")
        register_password_auth(mock_app, bind_host="localhost")
        register_password_auth(mock_app, bind_host="::1")
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "admin", 
        "CHAINLIT_PASSWORD": "admin",
        "PRAISONAI_ALLOW_DEFAULT_CREDS": ""
    })
    def test_default_creds_on_external_blocks_start(self):
        """Test default credentials on external interface block start."""
        mock_app = MagicMock()
        
        with pytest.raises(UIStartupError) as exc_info:
            register_password_auth(mock_app, bind_host="0.0.0.0")
        
        assert "Cannot bind to 0.0.0.0 with default admin/admin credentials" in str(exc_info.value)
        assert "CHAINLIT_USERNAME" in str(exc_info.value)
        assert "CHAINLIT_PASSWORD" in str(exc_info.value)
        
        # Test other external interfaces
        external_hosts = ["192.168.1.1", "10.0.0.1", "8.8.8.8"]
        for host in external_hosts:
            with pytest.raises(UIStartupError):
                register_password_auth(mock_app, bind_host=host)
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "admin",
        "CHAINLIT_PASSWORD": "admin", 
        "PRAISONAI_ALLOW_DEFAULT_CREDS": "1"
    })
    def test_escape_hatch_allows_default_creds(self):
        """Test escape hatch allows default credentials on external interface."""
        mock_app = MagicMock()
        
        # Should not raise with escape hatch
        register_password_auth(mock_app, bind_host="0.0.0.0")
        register_password_auth(mock_app, bind_host="192.168.1.1")
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "myuser",
        "CHAINLIT_PASSWORD": "mypass"
    })
    def test_custom_creds_always_allowed(self):
        """Test custom credentials are always allowed."""
        mock_app = MagicMock()
        
        # Should not raise on any interface with custom creds
        register_password_auth(mock_app, bind_host="127.0.0.1")
        register_password_auth(mock_app, bind_host="0.0.0.0")
        register_password_auth(mock_app, bind_host="192.168.1.1")
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "admin",
        "CHAINLIT_PASSWORD": "different"
    })
    def test_non_default_admin_allowed(self):
        """Test non-default admin credentials are allowed."""
        mock_app = MagicMock()
        
        # Should not raise - only username is default
        register_password_auth(mock_app, bind_host="0.0.0.0")
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "different", 
        "CHAINLIT_PASSWORD": "admin"
    })
    def test_non_default_password_allowed(self):
        """Test non-default password with admin username is allowed."""
        mock_app = MagicMock()
        
        # Should not raise - only password is default  
        register_password_auth(mock_app, bind_host="0.0.0.0")


class TestChainlitAuthCallback:
    """Test the actual Chainlit auth callback behavior."""
    
    def test_auth_callback_registration(self):
        """Test that auth callback gets registered with Chainlit."""
        mock_app = MagicMock()
        
        with patch('chainlit.password_auth_callback') as mock_decorator:
            mock_decorator.return_value = lambda f: f  # Mock decorator
            
            register_password_auth(mock_app, bind_host="127.0.0.1")
            
            # Verify decorator was called
            mock_decorator.assert_called_once()


class TestUISecurityScenarios:
    """Test real-world UI security scenarios."""
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "admin",
        "CHAINLIT_PASSWORD": "admin"
    })
    def test_local_development_scenario(self):
        """Test local development scenario (default creds, loopback)."""
        mock_app = MagicMock()
        
        # Should warn but allow (typical development scenario)
        register_password_auth(mock_app, bind_host="127.0.0.1")
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "admin",
        "CHAINLIT_PASSWORD": "admin",
        "PRAISONAI_ALLOW_DEFAULT_CREDS": ""
    })
    def test_accidental_production_deploy_blocked(self):
        """Test accidental production deploy with default creds is blocked."""
        mock_app = MagicMock()
        
        # Should block (prevents shipping with admin/admin to LAN/internet)
        with pytest.raises(UIStartupError):
            register_password_auth(mock_app, bind_host="0.0.0.0")
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "prod-user",
        "CHAINLIT_PASSWORD": "secure-pass-123"
    })
    def test_secure_production_deploy_allowed(self):
        """Test secure production deploy with custom creds is allowed."""
        mock_app = MagicMock()
        
        # Should allow (secure production deployment)
        register_password_auth(mock_app, bind_host="0.0.0.0")
    
    @patch.dict(os.environ, {
        "CHAINLIT_USERNAME": "admin",
        "CHAINLIT_PASSWORD": "admin",
        "PRAISONAI_ALLOW_DEFAULT_CREDS": "1" 
    })
    def test_lab_demo_escape_hatch(self):
        """Test lab/demo escape hatch scenario."""
        mock_app = MagicMock()
        
        # Should allow with warning (demo/lab scenario)
        register_password_auth(mock_app, bind_host="0.0.0.0")