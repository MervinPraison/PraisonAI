"""
Unit tests for WebSocket origin checking functionality.

Tests the check_origin() function that provides CSWSH (Cross-Site WebSocket Hijacking) defense.
"""

import pytest
from praisonai_bot.gateway.origin_check import check_origin, is_loopback


class TestOriginCheck:
    """Test the origin checking functionality."""

    def test_loopback_allows_local_pages_and_non_browser_clients(self):
        """Loopback binds allow no Origin and pages served from this machine.

        A page on another site is refused unless listed: the browser connects
        from 127.0.0.1 too, so the bind address alone proves nothing.
        """
        for host in ("127.0.0.1", "localhost", "::1"):
            assert check_origin(None, [], host) is True
            assert check_origin("http://localhost:3000", [], host) is True
            assert check_origin("http://127.0.0.1:8765", [], host) is True
            assert check_origin("http://foreign.example", [], host) is False
            assert check_origin("https://foreign.example", [], host) is False
            assert check_origin("https://foreign.example", ["https://foreign.example"], host) is True

    def test_external_bind_requires_allowed_origins(self):
        """External binds should require allowed_origins configuration."""
        with pytest.raises(ValueError, match="allowed_origins is required"):
            check_origin("https://example.com", [], "0.0.0.0")
        
        with pytest.raises(ValueError, match="allowed_origins is required"):
            check_origin("https://example.com", [], "192.168.1.100")

    def test_external_bind_with_matching_origin(self):
        """External binds should allow origins in the allowlist."""
        allowed = ["https://ui.example.com", "https://localhost:3000"]
        
        assert check_origin("https://ui.example.com", allowed, "0.0.0.0") is True
        assert check_origin("https://localhost:3000", allowed, "0.0.0.0") is True

    def test_external_bind_with_mismatched_origin(self):
        """External binds should reject origins not in the allowlist."""
        allowed = ["https://ui.example.com", "https://localhost:3000"]
        
        assert check_origin("http://foreign.example", allowed, "0.0.0.0") is False
        assert check_origin("https://foreign.example.com", allowed, "0.0.0.0") is False
        assert check_origin("https://ui.foreign.com", allowed, "0.0.0.0") is False

    def test_wildcard_origin(self):
        """Wildcard in allowed_origins should allow any origin."""
        allowed = ["*"]
        
        assert check_origin("http://foreign.example", allowed, "0.0.0.0") is True
        assert check_origin("https://any.domain.com", allowed, "0.0.0.0") is True
        assert check_origin("file://local", allowed, "0.0.0.0") is True

    def test_no_origin_header(self):
        """Missing origin header should be rejected for external binds."""
        allowed = ["https://ui.example.com"]
        
        assert check_origin(None, allowed, "0.0.0.0") is False
        assert check_origin("", allowed, "0.0.0.0") is False

    def test_mixed_wildcard_and_specific(self):
        """Mixing wildcard with specific origins should work."""
        allowed = ["https://ui.example.com", "*"]
        
        assert check_origin("https://ui.example.com", allowed, "0.0.0.0") is True
        assert check_origin("http://foreign.example", allowed, "0.0.0.0") is True


class TestIsLoopback:
    """Test the is_loopback() helper function."""

    def test_ipv4_loopback(self):
        """Test IPv4 loopback detection."""
        assert is_loopback("127.0.0.1") is True
        assert is_loopback("127.0.0.2") is True  # Any 127.x.x.x is loopback
        assert is_loopback("127.255.255.255") is True

    def test_ipv6_loopback(self):
        """Test IPv6 loopback detection."""
        assert is_loopback("::1") is True
        assert is_loopback("0:0:0:0:0:0:0:1") is True

    def test_localhost_hostname(self):
        """Test localhost hostname detection."""
        assert is_loopback("localhost") is True

    def test_non_loopback_ips(self):
        """Test non-loopback IP detection."""
        assert is_loopback("0.0.0.0") is False
        assert is_loopback("192.168.1.1") is False
        assert is_loopback("10.0.0.1") is False
        assert is_loopback("8.8.8.8") is False

    def test_non_loopback_hostnames(self):
        """Test non-loopback hostname detection."""
        assert is_loopback("example.com") is False
        assert is_loopback("gateway.local") is False
        assert is_loopback("") is False

    def test_invalid_input(self):
        """Test handling of invalid input."""
        assert is_loopback(None) is False


class TestIntegration:
    """Integration tests for the full origin checking workflow."""

    def test_acceptance_criteria_examples(self):
        """Test the specific examples from the acceptance criteria."""
        # Bad origin on external bind
        assert check_origin("http://foreign.example", ["https://ui.example.com"], "0.0.0.0") is False
        
        # Loopback: a page on another site is refused unless listed
        assert check_origin("http://foreign.example", [], "127.0.0.1") is False
        assert check_origin("https://anything.com", ["*"], "127.0.0.1") is True
        
        # External bind without allowed_origins should raise
        with pytest.raises(ValueError):
            check_origin("https://ui.example.com", [], "0.0.0.0")

    def test_real_world_scenarios(self):
        """Test realistic configuration scenarios."""
        # Development setup - localhost allows everything
        assert check_origin("http://localhost:3000", [], "localhost") is True
        assert check_origin("http://127.0.0.1:8080", [], "127.0.0.1") is True
        
        # Production setup - external bind with specific allowlist
        production_origins = [
            "https://app.example.com",
            "https://admin.example.com", 
            "https://localhost:3000"  # For local development
        ]
        
        # Valid origins
        assert check_origin("https://app.example.com", production_origins, "0.0.0.0") is True
        assert check_origin("https://admin.example.com", production_origins, "0.0.0.0") is True
        assert check_origin("https://localhost:3000", production_origins, "0.0.0.0") is True
        
        # Invalid origins
        assert check_origin("https://foreign.com", production_origins, "0.0.0.0") is False
        assert check_origin("http://app.example.com", production_origins, "0.0.0.0") is False  # Wrong protocol
        assert check_origin("https://app.foreign.com", production_origins, "0.0.0.0") is False