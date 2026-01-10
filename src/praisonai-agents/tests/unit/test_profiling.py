"""
Unit tests for the core SDK profiling module.

Tests cover:
- Profiler enable/disable
- Timing recording
- Streaming tracking
- Phase tracking
- Report generation
- Zero overhead when disabled
"""

import pytest
import time
from unittest.mock import patch


class TestProfilerBasics:
    """Test basic Profiler functionality."""
    
    def test_profiler_disabled_by_default(self):
        """Profiler should be disabled by default."""
        from praisonaiagents.profiling import Profiler
        Profiler.disable()  # Ensure clean state
        assert not Profiler.is_enabled()
    
    def test_profiler_enable_disable(self):
        """Test enable/disable functionality."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.disable()
        assert not Profiler.is_enabled()
        
        Profiler.enable()
        assert Profiler.is_enabled()
        
        Profiler.disable()
        assert not Profiler.is_enabled()
    
    def test_profiler_env_var_enable(self):
        """Test enabling via environment variable."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.disable()
        
        with patch.dict('os.environ', {'PRAISONAI_PROFILE': '1'}):
            assert Profiler.is_enabled()
        
        with patch.dict('os.environ', {'PRAISONAI_PROFILE': 'true'}):
            assert Profiler.is_enabled()
        
        with patch.dict('os.environ', {'PRAISONAI_PROFILE': 'yes'}):
            assert Profiler.is_enabled()
    
    def test_profiler_clear(self):
        """Test clearing profiling data."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.enable()
        Profiler.record_timing("test", 100.0)
        assert len(Profiler.get_timings()) > 0
        
        Profiler.clear()
        assert len(Profiler.get_timings()) == 0
        Profiler.disable()


class TestTimingRecording:
    """Test timing recording functionality."""
    
    def test_record_timing_when_enabled(self):
        """Timing should be recorded when profiler is enabled."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("test_op", 123.45, category="test")
        
        timings = Profiler.get_timings()
        assert len(timings) == 1
        assert timings[0].name == "test_op"
        assert timings[0].duration_ms == 123.45
        assert timings[0].category == "test"
        
        Profiler.disable()
    
    def test_record_timing_when_disabled(self):
        """Timing should NOT be recorded when profiler is disabled."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.disable()
        Profiler.clear()
        
        Profiler.record_timing("test_op", 123.45)
        
        timings = Profiler.get_timings()
        assert len(timings) == 0
    
    def test_record_timing_with_metadata(self):
        """Timing should include metadata."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("test_op", 100.0, metadata={"key": "value"})
        
        timings = Profiler.get_timings()
        assert timings[0].metadata == {"key": "value"}
        
        Profiler.disable()


class TestPhaseTracking:
    """Test phase tracking functionality."""
    
    def test_phase_context_manager(self):
        """Phase context manager should record timing."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.phase("test_phase"):
            time.sleep(0.01)  # 10ms
        
        timings = Profiler.get_timings(category="phase")
        assert len(timings) == 1
        assert timings[0].name == "test_phase"
        assert timings[0].duration_ms >= 10  # At least 10ms
        
        Profiler.disable()
    
    def test_nested_phases(self):
        """Nested phases should track parent."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.phase("outer"):
            with Profiler.phase("inner"):
                time.sleep(0.005)
        
        timings = Profiler.get_timings(category="phase")
        assert len(timings) == 2
        
        inner = next(t for t in timings if t.name == "inner")
        assert inner.parent == "outer"
        
        Profiler.disable()


class TestStreamingTracker:
    """Test streaming tracker functionality."""
    
    def test_streaming_ttft(self):
        """Streaming tracker should measure TTFT."""
        from praisonaiagents.profiling import Profiler, StreamingTracker
        
        Profiler.enable()
        Profiler.clear()
        
        tracker = StreamingTracker("test_stream")
        tracker.start()
        time.sleep(0.01)  # 10ms to first token
        tracker.first_token()
        time.sleep(0.02)  # 20ms more
        tracker.end()
        
        assert tracker.ttft_ms >= 10
        assert tracker.elapsed_ms >= 30
        
        records = Profiler.get_streaming_records()
        assert len(records) == 1
        assert records[0].name == "test_stream"
        assert records[0].ttft_ms >= 10
        
        Profiler.disable()
    
    def test_streaming_context_manager(self):
        """Streaming context manager should work."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.streaming("test_stream") as tracker:
            time.sleep(0.01)
            tracker.first_token()
            tracker.chunk()
            tracker.chunk()
        
        records = Profiler.get_streaming_records()
        assert len(records) == 1
        assert records[0].chunk_count == 2
        
        Profiler.disable()


class TestProfileDecorators:
    """Test profiling decorators."""
    
    def test_profile_func_decorator(self):
        """profile_func decorator should record function timing."""
        from praisonaiagents.profiling import Profiler, profile_func
        
        Profiler.enable()
        Profiler.clear()
        
        @profile_func
        def slow_function():
            time.sleep(0.01)
            return "done"
        
        result = slow_function()
        assert result == "done"
        
        timings = Profiler.get_timings(category="function")
        assert len(timings) == 1
        assert timings[0].name == "slow_function"
        assert timings[0].duration_ms >= 10
        
        Profiler.disable()
    
    def test_profile_func_disabled(self):
        """profile_func should have zero overhead when disabled."""
        from praisonaiagents.profiling import Profiler, profile_func
        
        Profiler.disable()
        Profiler.clear()
        
        @profile_func
        def fast_function():
            return "done"
        
        result = fast_function()
        assert result == "done"
        
        timings = Profiler.get_timings()
        assert len(timings) == 0


class TestProfileBlock:
    """Test profile_block context manager."""
    
    def test_profile_block(self):
        """profile_block should record block timing."""
        from praisonaiagents.profiling import Profiler, profile_block
        
        Profiler.enable()
        Profiler.clear()
        
        with profile_block("my_block", category="custom"):
            time.sleep(0.01)
        
        timings = Profiler.get_timings(category="custom")
        assert len(timings) == 1
        assert timings[0].name == "my_block"
        
        Profiler.disable()
    
    def test_profile_block_disabled(self):
        """profile_block should have zero overhead when disabled."""
        from praisonaiagents.profiling import Profiler, profile_block
        
        Profiler.disable()
        Profiler.clear()
        
        with profile_block("my_block"):
            pass
        
        timings = Profiler.get_timings()
        assert len(timings) == 0


class TestReporting:
    """Test report generation."""
    
    def test_get_summary(self):
        """get_summary should return structured data."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("op1", 100.0, category="cat1")
        Profiler.record_timing("op2", 200.0, category="cat2")
        
        summary = Profiler.get_summary()
        
        assert summary['total_time_ms'] == 300.0
        assert summary['timing_count'] == 2
        assert 'cat1' in summary['by_category']
        assert 'cat2' in summary['by_category']
        assert len(summary['slowest_operations']) == 2
        
        Profiler.disable()
    
    def test_export_json(self):
        """export_json should return valid JSON."""
        from praisonaiagents.profiling import Profiler
        import json
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("test", 100.0)
        
        json_str = Profiler.export_json()
        data = json.loads(json_str)
        
        assert 'summary' in data
        assert 'timings' in data
        assert len(data['timings']) == 1
        
        Profiler.disable()


class TestWarmup:
    """Test warmup function."""
    
    def test_warmup_returns_timings(self):
        """warmup should return timing information."""
        from praisonaiagents import warmup
        
        result = warmup(include_litellm=False, include_openai=False)
        assert isinstance(result, dict)
    
    def test_warmup_with_litellm(self):
        """warmup with litellm should return litellm timing."""
        from praisonaiagents import warmup
        
        result = warmup(include_litellm=True, include_openai=False)
        assert 'litellm' in result
        # Should be positive (imported) or -1 (not available)
        assert result['litellm'] > 0 or result['litellm'] == -1


class TestZeroOverhead:
    """Test that profiling has zero overhead when disabled."""
    
    def test_record_timing_overhead(self):
        """record_timing should be fast when disabled."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.disable()
        
        start = time.perf_counter()
        for _ in range(10000):
            Profiler.record_timing("test", 100.0)
        elapsed = (time.perf_counter() - start) * 1000
        
        # Should complete 10k calls in under 10ms when disabled
        assert elapsed < 10, f"record_timing took {elapsed}ms for 10k calls"
    
    def test_phase_context_overhead(self):
        """phase context manager should be fast when disabled."""
        from praisonaiagents.profiling import Profiler
        
        Profiler.disable()
        
        start = time.perf_counter()
        for _ in range(1000):
            with Profiler.phase("test"):
                pass
        elapsed = (time.perf_counter() - start) * 1000
        
        # Should complete 1k calls in under 10ms when disabled
        assert elapsed < 10, f"phase took {elapsed}ms for 1k calls"
