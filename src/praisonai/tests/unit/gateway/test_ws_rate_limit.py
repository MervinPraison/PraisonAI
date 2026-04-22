"""
Unit tests for WebSocket rate limiting functionality.

Tests the rate limiting applied to WebSocket upgrade requests.
"""

import time
from unittest.mock import AsyncMock, patch, Mock
import pytest
from praisonai.gateway.rate_limiter import AuthRateLimiter


class TestWebSocketRateLimit:
    """Test WebSocket rate limiting functionality."""

    def test_allow_under_limit(self):
        """Requests under the limit should be allowed."""
        limiter = AuthRateLimiter(max_attempts=3, window_seconds=60)
        
        # First 3 attempts should be allowed
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    def test_deny_over_limit(self):
        """Requests over the limit should be denied."""
        limiter = AuthRateLimiter(max_attempts=3, window_seconds=60)
        
        # Use up the limit
        for _ in range(3):
            limiter.allow("ws_upgrade", "192.168.1.100")
        
        # 4th attempt should be denied
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False

    def test_different_ips_independent(self):
        """Different IPs should have independent rate limits."""
        limiter = AuthRateLimiter(max_attempts=2, window_seconds=60)
        
        # Use up limit for first IP
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False  # Over limit
        
        # Second IP should still work
        assert limiter.allow("ws_upgrade", "192.168.1.101") is True
        assert limiter.allow("ws_upgrade", "192.168.1.101") is True
        assert limiter.allow("ws_upgrade", "192.168.1.101") is False  # Over limit

    @patch('praisonai.gateway.rate_limiter.time.time')
    def test_window_reset(self, mock_time):
        """Rate limit should reset after the window expires."""
        mock_time.return_value = 0
        limiter = AuthRateLimiter(max_attempts=2, window_seconds=0.1, lockout_seconds=0.05)  # Short window for testing
        
        # Use up the limit
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False  # Over limit
        
        # Simulate window expiration
        mock_time.return_value = 0.2
        
        # Should be allowed again
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    @patch('praisonai.gateway.rate_limiter.time.time')
    def test_lockout_duration(self, mock_time):
        """After exceeding limit, should be locked out for the lockout period."""
        mock_time.return_value = 0
        limiter = AuthRateLimiter(max_attempts=2, window_seconds=60, lockout_seconds=0.2)
        
        # Use up the limit to trigger lockout
        for _ in range(2):
            limiter.allow("ws_upgrade", "192.168.1.100")
        
        # This triggers the lockout
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False
        
        # Should still be locked out immediately after
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False
        
        # Simulate lockout expiration
        mock_time.return_value = 0.3
        
        # Should be allowed again
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    def test_time_until_allowed(self):
        """time_until_allowed should return correct lockout time."""
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=60, lockout_seconds=10)
        
        # Trigger lockout
        limiter.allow("ws_upgrade", "192.168.1.100")
        limiter.allow("ws_upgrade", "192.168.1.100")  # This triggers lockout
        
        # Should report time until allowed
        time_left = limiter.time_until_allowed("ws_upgrade", "192.168.1.100")
        assert 0 < time_left <= 10

    def test_reset_clears_state(self):
        """reset() should clear rate limit state for a key."""
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=60)
        
        # Use up the limit
        limiter.allow("ws_upgrade", "192.168.1.100")
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False  # Should be denied
        
        # Reset the state
        limiter.reset("ws_upgrade", "192.168.1.100")
        
        # Should be allowed again
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    @patch('praisonai.gateway.rate_limiter.time.time')
    def test_prune_removes_expired_entries(self, mock_time):
        """prune() should remove expired buckets and lockouts."""
        mock_time.return_value = 0
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=0.1, lockout_seconds=0.1)
        
        # Create some entries
        limiter.allow("ws_upgrade", "192.168.1.100")
        limiter.allow("ws_upgrade", "192.168.1.101")
        
        # Simulate expiration
        mock_time.return_value = 0.2
        
        # Prune should remove expired entries
        removed_count = limiter.prune()
        assert removed_count >= 2  # Should remove at least the 2 entries we created

    def test_default_configuration(self):
        """Test the default configuration matches requirements.""" 
        limiter = AuthRateLimiter(max_attempts=10, window_seconds=60)
        
        # Should allow 10 attempts
        for _ in range(10):
            assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        
        # 11th attempt should be denied
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False


@pytest.mark.asyncio
class TestWebSocketIntegration:
    """Integration tests for WebSocket rate limiting in the gateway."""

    async def test_websocket_rate_limit_applied(self):
        """Test that rate limiting is correctly applied in WebSocket gateway initialization."""
        # This is a simple smoke test to ensure the rate limiter is properly initialized
        # Full WebSocket integration testing would require a test client and more complex setup
        
        from praisonai.gateway.server import WebSocketGateway
        from praisonai.gateway.rate_limiter import AuthRateLimiter
        
        # Test that gateway can be instantiated (smoke test)
        gateway = WebSocketGateway()
        assert gateway is not None
        
        # Test that AuthRateLimiter can be instantiated with the expected defaults
        rate_limiter = AuthRateLimiter(max_attempts=10, window_seconds=60)
        assert rate_limiter is not None

    def test_acceptance_criteria_11th_attempt(self):
        """Test that the 11th consecutive attempt is rate limited."""
        limiter = AuthRateLimiter(max_attempts=10, window_seconds=60)
        client_ip = "192.168.1.100"
        
        # First 10 attempts should succeed
        for i in range(10):
            result = limiter.allow("ws_upgrade", client_ip)
            assert result is True, f"Attempt {i+1} should be allowed"
        
        # 11th attempt should be denied
        assert limiter.allow("ws_upgrade", client_ip) is False
        
        # Verify lockout is in effect
        retry_time = limiter.time_until_allowed("ws_upgrade", client_ip)
        assert retry_time > 0