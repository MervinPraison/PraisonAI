"""
Unit tests for PraisonAI Advanced Profiler features.

TDD: Tests written first for new profiling capabilities:
- API/HTTP call profiling (wall-clock time)
- Streaming profiling (TTFT, total time)
- Line-level profiling
- Memory profiling
- Flamegraph generation
- cProfile integration
- Statistics (p50, p95, p99)
"""

import time
import asyncio
import pytest


# ============================================================================
# API Call Profiling Tests
# ============================================================================

class TestAPICallProfiler:
    """Test API/HTTP call profiling with wall-clock time."""
    
    def test_api_call_record(self):
        """Should record API call timing."""
        from praisonai.profiler import Profiler, APICallRecord
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_api_call(
            endpoint="https://api.openai.com/v1/chat/completions",
            method="POST",
            duration_ms=1500.0,
            status_code=200,
            request_size=1024,
            response_size=2048
        )
        
        calls = Profiler.get_api_calls()
        assert len(calls) >= 1
        assert calls[-1].endpoint == "https://api.openai.com/v1/chat/completions"
        assert calls[-1].duration_ms == 1500.0
        assert calls[-1].status_code == 200
        
        Profiler.disable()
        Profiler.clear()
    
    def test_api_call_context_manager(self):
        """Should profile API call with context manager."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.api_call("https://api.example.com/test", method="GET") as call:
            time.sleep(0.01)  # Simulate API latency
        
        calls = Profiler.get_api_calls()
        assert len(calls) >= 1
        assert calls[-1].duration_ms >= 10
        
        Profiler.disable()
        Profiler.clear()
    
    def test_api_call_decorator(self):
        """Should profile function as API call."""
        from praisonai.profiler import Profiler, profile_api
        
        Profiler.enable()
        Profiler.clear()
        
        @profile_api(endpoint="test_endpoint")
        def mock_api_call():
            time.sleep(0.01)
            return {"status": "ok"}
        
        result = mock_api_call()
        assert result == {"status": "ok"}
        
        calls = Profiler.get_api_calls()
        assert len(calls) >= 1
        
        Profiler.disable()
        Profiler.clear()


# ============================================================================
# Streaming Profiling Tests
# ============================================================================

class TestStreamingProfiler:
    """Test streaming profiling (TTFT, chunk times, total time)."""
    
    def test_streaming_record(self):
        """Should record streaming metrics."""
        from praisonai.profiler import Profiler, StreamingRecord
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_streaming(
            name="chat_completion",
            ttft_ms=150.0,  # Time to first token
            total_ms=2000.0,
            chunk_count=50,
            total_tokens=500
        )
        
        streams = Profiler.get_streaming_records()
        assert len(streams) >= 1
        assert streams[-1].ttft_ms == 150.0
        assert streams[-1].total_ms == 2000.0
        assert streams[-1].chunk_count == 50
        
        Profiler.disable()
        Profiler.clear()
    
    def test_streaming_tracker(self):
        """Should track streaming with context manager."""
        from praisonai.profiler import Profiler, StreamingTracker
        
        Profiler.enable()
        Profiler.clear()
        
        tracker = StreamingTracker("test_stream")
        tracker.start()
        time.sleep(0.01)
        tracker.first_token()  # Mark TTFT
        time.sleep(0.02)
        tracker.chunk()  # Record chunk
        tracker.chunk()
        tracker.end(total_tokens=100)
        
        streams = Profiler.get_streaming_records()
        assert len(streams) >= 1
        assert streams[-1].ttft_ms >= 10
        assert streams[-1].chunk_count == 2
        
        Profiler.disable()
        Profiler.clear()
    
    def test_streaming_context_manager(self):
        """Should profile streaming with context manager."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.streaming("test_stream") as tracker:
            time.sleep(0.01)
            tracker.first_token()
            for _ in range(3):
                tracker.chunk()
                time.sleep(0.005)
        
        streams = Profiler.get_streaming_records()
        assert len(streams) >= 1
        assert streams[-1].chunk_count == 3
        
        Profiler.disable()
        Profiler.clear()


# ============================================================================
# Memory Profiling Tests
# ============================================================================

class TestMemoryProfiler:
    """Test memory profiling capabilities."""
    
    def test_memory_record(self):
        """Should record memory usage."""
        from praisonai.profiler import Profiler, MemoryRecord
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_memory(
            name="agent_init",
            current_kb=1024.0,
            peak_kb=2048.0
        )
        
        memories = Profiler.get_memory_records()
        assert len(memories) >= 1
        assert memories[-1].current_kb == 1024.0
        assert memories[-1].peak_kb == 2048.0
        
        Profiler.disable()
        Profiler.clear()
    
    def test_memory_context_manager(self):
        """Should profile memory with context manager."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.memory("test_operation"):
            # Allocate some memory
            data = [i for i in range(10000)]
        
        memories = Profiler.get_memory_records()
        assert len(memories) >= 1
        assert memories[-1].peak_kb > 0
        
        Profiler.disable()
        Profiler.clear()
    
    def test_memory_snapshot(self):
        """Should take memory snapshot."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        
        snapshot = Profiler.memory_snapshot()
        assert 'current_kb' in snapshot
        assert 'peak_kb' in snapshot
        
        Profiler.disable()


# ============================================================================
# Statistics Tests
# ============================================================================

class TestProfilerStatistics:
    """Test statistical analysis of profiling data."""
    
    def test_percentiles(self):
        """Should calculate percentiles (p50, p95, p99)."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        # Add multiple timing records
        for i in range(100):
            Profiler.record_timing(f"op_{i}", float(i), "test")
        
        stats = Profiler.get_statistics(category="test")
        
        assert 'p50' in stats
        assert 'p95' in stats
        assert 'p99' in stats
        assert 'mean' in stats
        assert 'std_dev' in stats
        assert 'min' in stats
        assert 'max' in stats
        
        Profiler.disable()
        Profiler.clear()
    
    def test_statistics_by_category(self):
        """Should calculate statistics per category."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        for i in range(10):
            Profiler.record_timing(f"api_{i}", float(i * 100), "api")
            Profiler.record_timing(f"func_{i}", float(i * 10), "function")
        
        api_stats = Profiler.get_statistics(category="api")
        func_stats = Profiler.get_statistics(category="function")
        
        assert api_stats['mean'] > func_stats['mean']
        
        Profiler.disable()
        Profiler.clear()


# ============================================================================
# cProfile Integration Tests
# ============================================================================

class TestCProfileIntegration:
    """Test cProfile integration for detailed function profiling."""
    
    def test_cprofile_context_manager(self):
        """Should profile with cProfile."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        
        with Profiler.cprofile("test_operation") as stats:
            # Do some work
            result = sum(i * i for i in range(1000))
        
        assert stats is not None
        assert hasattr(stats, 'total_calls') or hasattr(stats, 'stats')
        
        Profiler.disable()
    
    def test_cprofile_decorator(self):
        """Should profile function with cProfile decorator."""
        from praisonai.profiler import profile_detailed
        
        @profile_detailed
        def compute_heavy():
            return sum(i * i for i in range(10000))
        
        result = compute_heavy()
        assert result > 0


# ============================================================================
# Flamegraph Tests
# ============================================================================

class TestFlamegraph:
    """Test flamegraph generation."""
    
    def test_flamegraph_data_generation(self):
        """Should generate flamegraph-compatible data."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        # Record some nested operations
        with Profiler.block("outer"):
            time.sleep(0.01)
            with Profiler.block("inner"):
                time.sleep(0.01)
        
        flamegraph_data = Profiler.get_flamegraph_data()
        
        assert flamegraph_data is not None
        assert isinstance(flamegraph_data, (str, list, dict))
        
        Profiler.disable()
        Profiler.clear()
    
    def test_flamegraph_export(self):
        """Should export flamegraph to file."""
        import tempfile
        import os
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.block("test_op"):
            time.sleep(0.01)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False) as f:
            filepath = f.name
        
        try:
            Profiler.export_flamegraph(filepath)
            assert os.path.exists(filepath)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
        
        Profiler.disable()
        Profiler.clear()


# ============================================================================
# Line-Level Profiling Tests
# ============================================================================

class TestLineProfiler:
    """Test line-level profiling integration."""
    
    def test_line_profile_decorator(self):
        """Should profile function line by line."""
        from praisonai.profiler import profile_lines, Profiler
        
        Profiler.enable()
        
        @profile_lines
        def sample_function():
            a = 1
            b = 2
            c = a + b
            return c
        
        result = sample_function()
        assert result == 3
        
        # Line profiling data should be available
        line_data = Profiler.get_line_profile_data()
        # May be empty if line_profiler not installed, but shouldn't error
        assert line_data is not None
        
        Profiler.disable()


# ============================================================================
# Report Export Tests
# ============================================================================

class TestReportExport:
    """Test report export in various formats."""
    
    def test_json_export(self):
        """Should export report as JSON."""
        import json
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("test_op", 100.0, "test")
        
        json_report = Profiler.export_json()
        data = json.loads(json_report)
        
        assert 'timings' in data or 'summary' in data
        
        Profiler.disable()
        Profiler.clear()
    
    def test_html_export(self):
        """Should export report as HTML."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("test_op", 100.0, "test")
        
        html_report = Profiler.export_html()
        
        assert '<html>' in html_report or '<!DOCTYPE' in html_report.lower()
        
        Profiler.disable()
        Profiler.clear()
    
    def test_file_export(self):
        """Should export report to file."""
        import tempfile
        import os
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("test_op", 100.0, "test")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            Profiler.export_to_file(filepath, format="json")
            assert os.path.exists(filepath)
            with open(filepath) as f:
                content = f.read()
            assert len(content) > 0
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
        
        Profiler.disable()
        Profiler.clear()


# ============================================================================
# Zero Performance Impact Tests
# ============================================================================

class TestZeroPerformanceImpact:
    """Test that profiling has zero impact when disabled."""
    
    def test_disabled_no_overhead(self):
        """Should have minimal overhead when disabled."""
        from praisonai.profiler import Profiler, profile
        
        Profiler.disable()
        
        @profile
        def fast_function():
            return 1 + 1
        
        # Measure overhead
        iterations = 10000
        start = time.perf_counter()
        for _ in range(iterations):
            fast_function()
        duration = time.perf_counter() - start
        
        # Should complete very fast (< 1ms per call on average)
        avg_us = (duration / iterations) * 1_000_000
        assert avg_us < 100  # Less than 100 microseconds per call
    
    def test_no_data_when_disabled(self):
        """Should not record data when disabled."""
        from praisonai.profiler import Profiler
        
        Profiler.disable()
        Profiler.clear()
        
        Profiler.record_timing("test", 100.0, "test")
        Profiler.record_api_call("endpoint", "GET", 100.0)
        
        assert len(Profiler.get_timings()) == 0
        assert len(Profiler.get_api_calls()) == 0


# ============================================================================
# Async Profiling Tests
# ============================================================================

class TestAsyncProfiling:
    """Test async function profiling."""
    
    @pytest.mark.asyncio
    async def test_async_api_call(self):
        """Should profile async API calls."""
        from praisonai.profiler import Profiler, profile_api_async
        
        Profiler.enable()
        Profiler.clear()
        
        @profile_api_async(endpoint="async_test")
        async def async_api_call():
            await asyncio.sleep(0.01)
            return {"status": "ok"}
        
        result = await async_api_call()
        assert result == {"status": "ok"}
        
        calls = Profiler.get_api_calls()
        assert len(calls) >= 1
        
        Profiler.disable()
        Profiler.clear()
    
    @pytest.mark.asyncio
    async def test_async_streaming(self):
        """Should profile async streaming."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        async with Profiler.streaming_async("async_stream") as tracker:
            await asyncio.sleep(0.01)
            tracker.first_token()
            for _ in range(3):
                tracker.chunk()
                await asyncio.sleep(0.005)
        
        streams = Profiler.get_streaming_records()
        assert len(streams) >= 1
        
        Profiler.disable()
        Profiler.clear()
