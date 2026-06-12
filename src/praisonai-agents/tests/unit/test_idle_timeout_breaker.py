"""
Unit tests for IdleTimeoutBreaker circuit breaker functionality.

Tests the circuit breaker behavior for preventing runaway API costs
from repeated provider stalls.
"""

import pytest
from praisonaiagents.errors import IdleTimeoutBreaker


class TestIdleTimeoutBreaker:
    """Test the IdleTimeoutBreaker circuit breaker."""
    
    def test_initialization_defaults(self):
        """Test that IdleTimeoutBreaker initializes with correct defaults."""
        breaker = IdleTimeoutBreaker()
        
        assert breaker.max_consecutive == 3
        assert breaker._count == 0
    
    def test_initialization_custom_max(self):
        """Test initialization with custom max_consecutive value."""
        breaker = IdleTimeoutBreaker(max_consecutive=5)
        
        assert breaker.max_consecutive == 5
        assert breaker._count == 0
    
    def test_record_idle_timeout_increments_count(self):
        """Test that record_idle_timeout increments the count."""
        breaker = IdleTimeoutBreaker()
        
        # First timeout
        result1 = breaker.record_idle_timeout()
        assert breaker._count == 1
        assert result1 is False  # Not yet at max
        
        # Second timeout
        result2 = breaker.record_idle_timeout()
        assert breaker._count == 2
        assert result2 is False  # Still not at max
    
    def test_circuit_breaker_trips_at_max(self):
        """Test that circuit breaker trips when max_consecutive is reached."""
        breaker = IdleTimeoutBreaker(max_consecutive=3)
        
        # Record timeouts up to the limit
        result1 = breaker.record_idle_timeout()  # count=1
        result2 = breaker.record_idle_timeout()  # count=2
        result3 = breaker.record_idle_timeout()  # count=3
        
        assert result1 is False
        assert result2 is False
        assert result3 is True  # Circuit trips at max
        assert breaker._count == 3
    
    def test_circuit_breaker_stays_tripped(self):
        """Test that circuit breaker stays tripped after reaching max."""
        breaker = IdleTimeoutBreaker(max_consecutive=2)
        
        # Trip the breaker
        breaker.record_idle_timeout()  # count=1
        breaker.record_idle_timeout()  # count=2, trips
        
        # Additional timeouts should still return True
        result3 = breaker.record_idle_timeout()  # count=3
        result4 = breaker.record_idle_timeout()  # count=4
        
        assert result3 is True
        assert result4 is True
        assert breaker._count == 4
    
    def test_reset_clears_count(self):
        """Test that reset() clears the count."""
        breaker = IdleTimeoutBreaker(max_consecutive=3)
        
        # Build up some count
        breaker.record_idle_timeout()
        breaker.record_idle_timeout()
        assert breaker._count == 2
        
        # Reset should clear the count
        breaker.reset()
        assert breaker._count == 0
        
        # Should be able to record timeouts again
        result = breaker.record_idle_timeout()
        assert result is False  # Back to normal operation
        assert breaker._count == 1
    
    def test_reset_after_circuit_trip(self):
        """Test that reset works even after circuit has tripped."""
        breaker = IdleTimeoutBreaker(max_consecutive=2)
        
        # Trip the circuit
        breaker.record_idle_timeout()
        result = breaker.record_idle_timeout()
        assert result is True  # Circuit tripped
        assert breaker._count == 2
        
        # Reset should restore normal operation
        breaker.reset()
        assert breaker._count == 0
        
        # Should work normally again
        result1 = breaker.record_idle_timeout()
        result2 = breaker.record_idle_timeout()
        
        assert result1 is False
        assert result2 is True  # Trips again at max
    
    def test_single_timeout_max(self):
        """Test behavior with max_consecutive=1."""
        breaker = IdleTimeoutBreaker(max_consecutive=1)
        
        # Should trip immediately on first timeout
        result = breaker.record_idle_timeout()
        assert result is True
        assert breaker._count == 1
    
    def test_zero_max_edge_case(self):
        """Test edge case with max_consecutive=0."""
        breaker = IdleTimeoutBreaker(max_consecutive=0)
        
        # Should trip immediately (count >= max)
        result = breaker.record_idle_timeout()
        assert result is True
        assert breaker._count == 1
    
    def test_dataclass_immutability(self):
        """Test that _count field is not included in __init__."""
        # This should work (only max_consecutive in init)
        breaker = IdleTimeoutBreaker(max_consecutive=5)
        
        # This should fail - _count is not in __init__
        with pytest.raises(TypeError):
            IdleTimeoutBreaker(max_consecutive=5, _count=10)
    
    def test_repr_excludes_count(self):
        """Test that repr() excludes the _count field."""
        breaker = IdleTimeoutBreaker(max_consecutive=3)
        breaker.record_idle_timeout()  # Increment count
        
        repr_str = repr(breaker)
        assert "_count" not in repr_str
        assert "max_consecutive=3" in repr_str
    
    def test_circuit_breaker_workflow(self):
        """Test a complete workflow scenario."""
        breaker = IdleTimeoutBreaker(max_consecutive=3)
        
        # Simulate a series of successful requests with occasional timeouts
        
        # First timeout
        assert breaker.record_idle_timeout() is False
        
        # Success (reset)
        breaker.reset()
        
        # Two timeouts
        assert breaker.record_idle_timeout() is False
        assert breaker.record_idle_timeout() is False
        
        # Success (reset)
        breaker.reset()
        
        # Three consecutive timeouts - should trip
        assert breaker.record_idle_timeout() is False  # 1
        assert breaker.record_idle_timeout() is False  # 2  
        assert breaker.record_idle_timeout() is True   # 3 - trips!
        
        # Subsequent timeouts while tripped
        assert breaker.record_idle_timeout() is True
        
        # Recovery
        breaker.reset()
        assert breaker.record_idle_timeout() is False  # Back to normal


if __name__ == "__main__":
    pytest.main([__file__, "-v"])