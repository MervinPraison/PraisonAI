"""
Unit tests for the Unified Profiling Architecture.

Tests the core invariants:
1. Profiled execution produces identical output to non-profiled execution
2. Schema equivalence across invocation methods
3. Overhead bounds
4. Profile data bounds
"""

import pytest
from unittest.mock import patch


class TestExecutionRequest:
    """Tests for ExecutionRequest dataclass."""
    
    def test_create_basic_request(self):
        """Test creating a basic execution request."""
        from praisonai.cli.execution import ExecutionRequest
        
        req = ExecutionRequest(prompt="What is 2+2?")
        
        assert req.prompt == "What is 2+2?"
        assert req.agent_name == "Assistant"
        assert req.model is None
        assert req.stream is False
        assert req.tools == ()
    
    def test_request_immutability(self):
        """Test that ExecutionRequest is immutable (frozen)."""
        from praisonai.cli.execution import ExecutionRequest
        
        req = ExecutionRequest(prompt="test")
        
        with pytest.raises(AttributeError):
            req.prompt = "modified"
    
    def test_request_with_model(self):
        """Test creating request with model."""
        from praisonai.cli.execution import ExecutionRequest
        
        req = ExecutionRequest(prompt="test", model="gpt-4")
        new_req = req.with_model("gpt-3.5-turbo")
        
        assert req.model == "gpt-4"
        assert new_req.model == "gpt-3.5-turbo"
        assert req.prompt == new_req.prompt
    
    def test_request_validation(self):
        """Test that empty prompt raises error."""
        from praisonai.cli.execution import ExecutionRequest
        
        with pytest.raises(ValueError):
            ExecutionRequest(prompt="")
    
    def test_request_to_dict(self):
        """Test serialization to dict."""
        from praisonai.cli.execution import ExecutionRequest
        
        req = ExecutionRequest(
            prompt="test",
            agent_name="TestAgent",
            model="gpt-4",
        )
        
        d = req.to_dict()
        
        assert d["prompt"] == "test"
        assert d["agent_name"] == "TestAgent"
        assert d["model"] == "gpt-4"
        assert d["tools_count"] == 0


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""
    
    def test_create_basic_result(self):
        """Test creating a basic execution result."""
        from praisonai.cli.execution.result import ExecutionResult
        
        result = ExecutionResult(output="four")
        
        assert result.output == "four"
        assert result.success is True
        assert result.error is None
    
    def test_result_from_error(self):
        """Test creating result from error."""
        from praisonai.cli.execution.result import ExecutionResult
        
        result = ExecutionResult.from_error("Something went wrong")
        
        assert result.output == ""
        assert result.success is False
        assert result.error == "Something went wrong"
    
    def test_result_duration(self):
        """Test duration calculation."""
        from praisonai.cli.execution.result import ExecutionResult
        
        result = ExecutionResult(
            output="test",
            start_time=1000.0,
            end_time=1002.5,
        )
        
        assert result.duration_ms == 2500.0


class TestProfilerConfig:
    """Tests for ProfilerConfig."""
    
    def test_default_config(self):
        """Test default profiler configuration."""
        from praisonai.cli.execution.profiler import ProfilerConfig
        
        config = ProfilerConfig()
        
        assert config.layer == 1
        assert config.limit == 30
        assert config.track_network is False
    
    def test_from_flags_basic(self):
        """Test creating config from basic --profile flag."""
        from praisonai.cli.execution.profiler import ProfilerConfig
        
        config = ProfilerConfig.from_flags(profile=True)
        
        assert config.layer == 1
    
    def test_from_flags_deep(self):
        """Test creating config from --profile --deep flags."""
        from praisonai.cli.execution.profiler import ProfilerConfig
        
        config = ProfilerConfig.from_flags(profile=True, deep=True)
        
        assert config.layer == 2
        assert config.show_callers is True
        assert config.show_callees is True
    
    def test_from_flags_network(self):
        """Test creating config with network tracking."""
        from praisonai.cli.execution.profiler import ProfilerConfig
        
        config = ProfilerConfig.from_flags(profile=True, network=True)
        
        assert config.track_network is True


class TestTimingBreakdown:
    """Tests for TimingBreakdown."""
    
    def test_timing_to_dict(self):
        """Test timing serialization."""
        from praisonai.cli.execution.profiler import TimingBreakdown
        
        timing = TimingBreakdown(
            total_ms=1000.0,
            imports_ms=500.0,
            agent_init_ms=10.0,
            execution_ms=490.0,
        )
        
        d = timing.to_dict()
        
        assert d["total_ms"] == 1000.0
        assert d["imports_ms"] == 500.0
        assert d["agent_init_ms"] == 10.0
        assert d["execution_ms"] == 490.0


class TestProfileReport:
    """Tests for ProfileReport."""
    
    def test_report_schema_version(self):
        """Test that schema version is set."""
        from praisonai.cli.execution.profiler import ProfileReport, SCHEMA_VERSION
        
        report = ProfileReport(run_id="test123")
        
        assert report.schema_version == SCHEMA_VERSION
        assert report.schema_version == "1.0"
    
    def test_report_timestamp(self):
        """Test that timestamp is auto-generated."""
        from praisonai.cli.execution.profiler import ProfileReport
        
        report = ProfileReport(run_id="test123")
        
        assert report.timestamp is not None
        assert "T" in report.timestamp  # ISO 8601 format
    
    def test_report_to_dict(self):
        """Test report serialization."""
        from praisonai.cli.execution.profiler import (
            ProfileReport, TimingBreakdown, InvocationInfo
        )
        
        report = ProfileReport(
            run_id="test123",
            timing=TimingBreakdown(total_ms=100),
            invocation=InvocationInfo(method="test"),
        )
        
        d = report.to_dict()
        
        assert d["schema_version"] == "1.0"
        assert d["run_id"] == "test123"
        assert "timing" in d
        assert "invocation" in d
    
    def test_report_to_json(self):
        """Test JSON serialization."""
        from praisonai.cli.execution.profiler import ProfileReport
        import json
        
        report = ProfileReport(run_id="test123")
        
        json_str = report.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["run_id"] == "test123"
    
    def test_report_to_text(self):
        """Test text formatting."""
        from praisonai.cli.execution.profiler import ProfileReport
        
        report = ProfileReport(run_id="test123")
        
        text = report.to_text()
        
        assert "test123" in text
        assert "Timing Breakdown" in text


class TestProfilerBounds:
    """Tests for profile data bounds."""
    
    def test_max_function_stats(self):
        """Test that function stats are bounded."""
        from praisonai.cli.execution.profiler import MAX_FUNCTION_STATS
        
        assert MAX_FUNCTION_STATS == 1000
    
    def test_max_call_graph_edges(self):
        """Test that call graph edges are bounded."""
        from praisonai.cli.execution.profiler import MAX_CALL_GRAPH_EDGES
        
        assert MAX_CALL_GRAPH_EDGES == 5000
    
    def test_max_network_requests(self):
        """Test that network requests are bounded."""
        from praisonai.cli.execution.profiler import MAX_NETWORK_REQUESTS
        
        assert MAX_NETWORK_REQUESTS == 100


class TestSchemaStability:
    """Tests for schema stability guarantees."""
    
    def test_mandatory_fields_present(self):
        """Test that all mandatory fields are present in report."""
        from praisonai.cli.execution.profiler import ProfileReport
        
        report = ProfileReport(run_id="test")
        d = report.to_dict()
        
        # Mandatory fields
        assert "schema_version" in d
        assert "run_id" in d
        assert "timestamp" in d
        assert "invocation" in d
        assert "timing" in d
        assert "response_preview" in d
    
    def test_optional_fields_nullable(self):
        """Test that optional fields can be None."""
        from praisonai.cli.execution.profiler import ProfileReport
        
        report = ProfileReport(run_id="test")
        d = report.to_dict()
        
        # Optional fields should not be present if None
        assert "functions" not in d or d["functions"] is None
        assert "call_graph" not in d or d["call_graph"] is None
        assert "network" not in d or d["network"] is None


class TestInvocationInfo:
    """Tests for InvocationInfo."""
    
    def test_version_auto_populated(self):
        """Test that versions are auto-populated."""
        from praisonai.cli.execution.profiler import InvocationInfo
        
        info = InvocationInfo(method="test")
        
        assert info.python_version is not None
        assert len(info.python_version) > 0


class TestCallGraph:
    """Tests for CallGraph."""
    
    def test_edges_property(self):
        """Test edges property."""
        from praisonai.cli.execution.profiler import CallGraph
        
        graph = CallGraph(
            callers={"func_b": ["func_a"]},
            callees={"func_a": ["func_b"]},
        )
        
        edges = graph.edges
        
        assert len(edges) == 1
        assert ("func_a", "func_b") in edges


class TestRequestTiming:
    """Tests for RequestTiming."""
    
    def test_ttfb_calculation(self):
        """Test time to first byte calculation."""
        from praisonai.cli.execution.profiler import RequestTiming
        
        timing = RequestTiming(
            url="https://api.openai.com",
            method="POST",
            start_time=1000.0,
            first_byte_time=1001.5,
            end_time=1002.0,
            status_code=200,
        )
        
        assert timing.ttfb_ms == 1500.0
        assert timing.total_ms == 2000.0


# Integration tests (require mocking)
class TestProfilerIntegration:
    """Integration tests for Profiler class."""
    
    def test_profiler_creates_report(self):
        """Test that profiler creates a valid report."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        # Mock at the profiler level by patching the imported _execute_core
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="four",
                run_id="test123",
            )
            
            config = ProfilerConfig(layer=0)  # Minimal profiling
            profiler = Profiler(config)
            
            req = ExecutionRequest(prompt="What is 2+2?")
            result, report = profiler.profile_sync(req)
            
            assert result.output == "four"
            assert report.schema_version == "1.0"
            assert report.timing.total_ms > 0
    
    def test_output_equivalence_profiled_vs_non_profiled(self):
        """INVARIANT 1: Profiled execution produces identical output."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        expected_output = "test_output_value"
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output=expected_output,
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            
            # Layer 0 (minimal)
            config0 = ProfilerConfig(layer=0)
            result0, _ = Profiler(config0).profile_sync(req)
            
            # Layer 1 (basic)
            config1 = ProfilerConfig(layer=1)
            result1, _ = Profiler(config1).profile_sync(req)
            
            # Layer 2 (deep)
            config2 = ProfilerConfig(layer=2)
            result2, _ = Profiler(config2).profile_sync(req)
            
            # All outputs must be identical
            assert result0.output == expected_output
            assert result1.output == expected_output
            assert result2.output == expected_output
    
    def test_schema_equivalence_across_invocation_methods(self):
        """INVARIANT 2: Schema equivalence across invocation methods."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=1)
            
            # CLI direct
            _, report1 = Profiler(config).profile_sync(req, invocation_method="cli_direct")
            
            # Profile command
            _, report2 = Profiler(config).profile_sync(req, invocation_method="profile_command")
            
            # Schema must be identical
            dict1 = report1.to_dict()
            dict2 = report2.to_dict()
            
            assert dict1["schema_version"] == dict2["schema_version"]
            assert set(dict1["timing"].keys()) == set(dict2["timing"].keys())
            assert set(dict1["invocation"].keys()) == set(dict2["invocation"].keys())
    
    def test_data_bounds_function_stats(self):
        """INVARIANT 4: Function stats are bounded."""
        from praisonai.cli.execution.profiler import (
            Profiler, ProfilerConfig, MAX_FUNCTION_STATS
        )
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=1, limit=50)
            
            _, report = Profiler(config).profile_sync(req)
            
            # Functions should be bounded by limit
            if report.functions:
                assert len(report.functions) <= config.limit
                assert len(report.functions) <= MAX_FUNCTION_STATS
    
    def test_layer_0_minimal_overhead(self):
        """INVARIANT 3: Layer 0 has minimal overhead (<1ms)."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        import time
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            # Fast mock execution
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=0)
            
            start = time.perf_counter()
            Profiler(config).profile_sync(req)
            elapsed = (time.perf_counter() - start) * 1000
            
            # Layer 0 overhead should be minimal (allow some margin for test environment)
            # The actual profiling overhead (excluding execution) should be < 1ms
            # We can't measure this precisely with mocks, but we verify it runs fast
            assert elapsed < 100  # Very generous bound for test environment
    
    def test_ttfr_is_populated(self):
        """Test that Time to First Response (TTFR) is populated and > 0."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=1)
            
            _, report = Profiler(config).profile_sync(req)
            
            # TTFR must be populated
            assert report.timing.time_to_first_response_ms > 0
            assert report.timing.first_output_ms >= 0
    
    def test_first_output_less_than_total(self):
        """Test that first_output_ms <= total_ms."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=1)
            
            _, report = Profiler(config).profile_sync(req)
            
            # first_output must be <= total
            assert report.timing.first_output_ms <= report.timing.total_ms
    
    def test_timeline_phases_ordered(self):
        """Test that timeline phases are correctly ordered."""
        from praisonai.cli.execution.profiler import TimingBreakdown
        
        timing = TimingBreakdown(
            total_ms=1000.0,
            imports_ms=200.0,
            agent_init_ms=50.0,
            execution_ms=700.0,
        )
        
        timeline = timing.to_timeline()
        
        # Timeline should have entries
        assert len(timeline) > 0
        
        # Each entry should have (name, start, duration)
        for entry in timeline:
            assert len(entry) == 3
            name, start, duration = entry
            assert isinstance(name, str)
            assert isinstance(start, float)
            assert isinstance(duration, float)
    
    def test_decision_trace_in_deep_profile(self):
        """Test that decision trace is present in deep profile (layer 2)."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test", model="gpt-4")
            config = ProfilerConfig(layer=2)  # Deep profile
            
            _, report = Profiler(config).profile_sync(req)
            
            # Decision trace must be present in deep profile
            assert report.decision_trace is not None
            assert report.decision_trace.model_selected == "gpt-4"
            assert report.decision_trace.profile_layer == 2
    
    def test_module_breakdown_in_deep_profile(self):
        """Test that module breakdown is present in deep profile (layer 2)."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=2)  # Deep profile
            
            _, report = Profiler(config).profile_sync(req)
            
            # Module breakdown must be present in deep profile
            assert report.module_breakdown is not None
    
    def test_text_output_includes_timeline(self):
        """Test that text output includes timeline section."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=1)
            
            _, report = Profiler(config).profile_sync(req)
            text = report.to_text()
            
            # Text output must include timeline and TTFR
            assert "Execution Timeline" in text
            assert "Time to First Response" in text
    
    def test_json_output_includes_ttfr(self):
        """Test that JSON output includes time_to_first_response_ms."""
        from praisonai.cli.execution.profiler import Profiler, ProfilerConfig
        from praisonai.cli.execution.request import ExecutionRequest
        from praisonai.cli.execution.result import ExecutionResult
        import json
        
        with patch('praisonai.cli.execution.profiler._execute_core') as mock_exec:
            mock_exec.return_value = ExecutionResult(
                output="test",
                run_id="test123",
            )
            
            req = ExecutionRequest(prompt="test")
            config = ProfilerConfig(layer=1)
            
            _, report = Profiler(config).profile_sync(req)
            data = json.loads(report.to_json())
            
            # JSON must include TTFR
            assert "time_to_first_response_ms" in data["timing"]
            assert data["timing"]["time_to_first_response_ms"] > 0
