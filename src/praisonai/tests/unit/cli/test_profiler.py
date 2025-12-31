"""
Unit tests for CLI profiler module.
"""


class TestProfilerConfig:
    """Tests for ProfilerConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        from praisonai.cli.features.profiler import ProfilerConfig
        
        config = ProfilerConfig()
        assert config.deep is False
        assert config.limit == 30
        assert config.sort_by == "cumulative"
        assert config.show_files is False
        assert config.show_callers is False
        assert config.show_callees is False
        assert config.importtime is False
        assert config.first_token is False
        assert config.save_path is None
        assert config.output_format == "text"
        assert config.stream is False
    
    def test_custom_config(self):
        """Test custom configuration."""
        from praisonai.cli.features.profiler import ProfilerConfig
        
        config = ProfilerConfig(
            deep=True,
            limit=50,
            sort_by="tottime",
            show_files=True,
        )
        assert config.deep is True
        assert config.limit == 50
        assert config.sort_by == "tottime"
        assert config.show_files is True


class TestTimingBreakdown:
    """Tests for TimingBreakdown dataclass."""
    
    def test_default_timing(self):
        """Test default timing values."""
        from praisonai.cli.features.profiler.core import TimingBreakdown
        
        timing = TimingBreakdown()
        assert timing.cli_parse_ms == 0.0
        assert timing.imports_ms == 0.0
        assert timing.agent_construction_ms == 0.0
        assert timing.model_init_ms == 0.0
        assert timing.first_token_ms == 0.0
        assert timing.total_run_ms == 0.0


class TestFunctionStats:
    """Tests for FunctionStats dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from praisonai.cli.features.profiler.core import FunctionStats
        
        stats = FunctionStats(
            name="test_func",
            filename="/path/to/file.py",
            lineno=42,
            calls=10,
            tottime=0.5,
            cumtime=1.0,
        )
        
        result = stats.to_dict()
        assert result["name"] == "test_func"
        assert result["filename"] == "/path/to/file.py"
        assert result["lineno"] == 42
        assert result["calls"] == 10
        assert result["tottime_ms"] == 500.0
        assert result["cumtime_ms"] == 1000.0


class TestFileStats:
    """Tests for FileStats dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from praisonai.cli.features.profiler.core import FileStats, FunctionStats
        
        func_stats = FunctionStats(
            name="func1",
            filename="/path/to/file.py",
            lineno=10,
            calls=5,
            tottime=0.1,
            cumtime=0.2,
        )
        
        file_stats = FileStats(
            filename="/path/to/file.py",
            total_time=0.5,
            functions=[func_stats],
        )
        
        result = file_stats.to_dict()
        assert result["filename"] == "/path/to/file.py"
        assert result["total_time_ms"] == 500.0
        assert result["function_count"] == 1


class TestProfilerResult:
    """Tests for ProfilerResult dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from praisonai.cli.features.profiler.core import (
            ProfilerResult,
            TimingBreakdown,
            FunctionStats,
            FileStats,
        )
        
        timing = TimingBreakdown(
            cli_parse_ms=1.0,
            imports_ms=100.0,
            total_run_ms=500.0,
        )
        
        func_stats = [FunctionStats(
            name="test",
            filename="test.py",
            lineno=1,
            calls=1,
            tottime=0.1,
            cumtime=0.2,
        )]
        
        file_stats = [FileStats(
            filename="test.py",
            total_time=0.2,
        )]
        
        result = ProfilerResult(
            prompt="test prompt",
            response="test response",
            timing=timing,
            function_stats=func_stats,
            file_stats=file_stats,
            metadata={"model": "test"},
        )
        
        data = result.to_dict()
        assert "timestamp" in data
        assert data["prompt"] == "test prompt"
        assert data["response_preview"] == "test response"
        assert data["timing"]["cli_parse_ms"] == 1.0
        assert data["timing"]["imports_ms"] == 100.0
        assert len(data["top_functions"]) == 1
        assert len(data["top_files"]) == 1


class TestQueryProfiler:
    """Tests for QueryProfiler class."""
    
    def test_init_default_config(self):
        """Test initialization with default config."""
        from praisonai.cli.features.profiler import QueryProfiler, ProfilerConfig
        
        profiler = QueryProfiler()
        assert profiler.config is not None
        assert isinstance(profiler.config, ProfilerConfig)
    
    def test_init_custom_config(self):
        """Test initialization with custom config."""
        from praisonai.cli.features.profiler import QueryProfiler, ProfilerConfig
        
        config = ProfilerConfig(deep=True, limit=50)
        profiler = QueryProfiler(config)
        assert profiler.config.deep is True
        assert profiler.config.limit == 50
    
    def test_collect_metadata(self):
        """Test metadata collection."""
        from praisonai.cli.features.profiler import QueryProfiler
        
        profiler = QueryProfiler()
        metadata = profiler._collect_metadata("gpt-4")
        
        assert "python_version" in metadata
        assert "platform" in metadata
        assert "praisonai_version" in metadata
        assert metadata["model"] == "gpt-4"
        assert "timestamp" in metadata


class TestFormatProfileReport:
    """Tests for format_profile_report function."""
    
    def test_basic_report(self):
        """Test basic report formatting."""
        from praisonai.cli.features.profiler import (
            format_profile_report,
            ProfilerConfig,
        )
        from praisonai.cli.features.profiler.core import (
            ProfilerResult,
            TimingBreakdown,
            FunctionStats,
            FileStats,
        )
        
        timing = TimingBreakdown(
            cli_parse_ms=1.0,
            imports_ms=100.0,
            total_run_ms=500.0,
        )
        
        func_stats = [FunctionStats(
            name="test_func",
            filename="test.py",
            lineno=1,
            calls=10,
            tottime=0.1,
            cumtime=0.2,
        )]
        
        file_stats = [FileStats(
            filename="test.py",
            total_time=0.2,
        )]
        
        result = ProfilerResult(
            prompt="test",
            response="response",
            timing=timing,
            function_stats=func_stats,
            file_stats=file_stats,
            metadata={"python_version": "3.12", "platform": "test", "praisonai_version": "1.0", "model": "test"},
        )
        
        report = format_profile_report(result)
        
        assert "PraisonAI Profile Report" in report
        assert "System Information" in report
        assert "Timing Breakdown" in report
        assert "Per-Function Timing" in report
        assert "test_func" in report
    
    def test_report_with_files(self):
        """Test report with file grouping."""
        from praisonai.cli.features.profiler import (
            format_profile_report,
            ProfilerConfig,
        )
        from praisonai.cli.features.profiler.core import (
            ProfilerResult,
            TimingBreakdown,
            FunctionStats,
            FileStats,
        )
        
        config = ProfilerConfig(show_files=True)
        
        timing = TimingBreakdown()
        func_stats = []
        file_stats = [FileStats(filename="test.py", total_time=0.5)]
        
        result = ProfilerResult(
            prompt="test",
            response="response",
            timing=timing,
            function_stats=func_stats,
            file_stats=file_stats,
            metadata={},
        )
        
        report = format_profile_report(result, config)
        assert "Per-File Timing" in report


class TestRedactSecrets:
    """Tests for secret redaction."""
    
    def test_redact_openai_key(self):
        """Test redacting OpenAI API keys."""
        from praisonai.cli.features.profiler.core import redact_secrets
        
        text = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "sk-1234567890" not in result
        assert "[REDACTED]" in result
    
    def test_redact_anthropic_key(self):
        """Test redacting Anthropic API keys."""
        from praisonai.cli.features.profiler.core import redact_secrets
        
        text = "Key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "sk-ant-api03" not in result
        assert "[REDACTED]" in result
    
    def test_preserve_normal_text(self):
        """Test that normal text is preserved."""
        from praisonai.cli.features.profiler.core import redact_secrets
        
        text = "This is normal text without secrets"
        result = redact_secrets(text)
        assert result == text


class TestCLIImports:
    """Tests for CLI import functionality."""
    
    def test_cli_app_imports(self):
        """Test that CLI app imports without errors."""
        # This tests the fix for ModuleNotFoundError
        from praisonai.cli.app import app
        assert app is not None
    
    def test_output_module_imports(self):
        """Test that output module imports correctly."""
        from praisonai.cli.output import OutputController, OutputMode
        assert OutputController is not None
        assert OutputMode is not None
    
    def test_profiler_module_imports(self):
        """Test that profiler module imports correctly."""
        from praisonai.cli.features.profiler import (
            ProfilerConfig,
            ProfilerResult,
            QueryProfiler,
            run_profiled_query,
            format_profile_report,
        )
        assert ProfilerConfig is not None
        assert ProfilerResult is not None
        assert QueryProfiler is not None
        assert run_profiled_query is not None
        assert format_profile_report is not None


class TestOutputController:
    """Tests for OutputController."""
    
    def test_default_mode(self):
        """Test default output mode."""
        from praisonai.cli.output import OutputController, OutputMode
        
        controller = OutputController()
        assert controller.mode == OutputMode.TEXT
        assert controller.is_json_mode is False
        assert controller.is_quiet is False
    
    def test_json_mode(self):
        """Test JSON output mode."""
        from praisonai.cli.output import OutputController, OutputMode
        
        controller = OutputController(mode=OutputMode.JSON)
        assert controller.is_json_mode is True
    
    def test_quiet_mode(self):
        """Test quiet output mode."""
        from praisonai.cli.output import OutputController, OutputMode
        
        controller = OutputController(mode=OutputMode.QUIET)
        assert controller.is_quiet is True
