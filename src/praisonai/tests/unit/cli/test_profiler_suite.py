"""
Unit tests for CLI profiler suite module.
"""


class TestScenarioConfig:
    """Tests for ScenarioConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        from praisonai.cli.features.profiler import ScenarioConfig
        
        config = ScenarioConfig(name="test", prompt="hi")
        assert config.name == "test"
        assert config.prompt == "hi"
        assert config.model is None
        assert config.stream is False
        assert config.iterations == 3
        assert config.warmup == 1
        assert config.show_files is True
        assert config.limit == 20
    
    def test_custom_config(self):
        """Test custom configuration."""
        from praisonai.cli.features.profiler import ScenarioConfig
        
        config = ScenarioConfig(
            name="custom",
            prompt="test prompt",
            model="gpt-4o",
            stream=True,
            iterations=5,
        )
        assert config.name == "custom"
        assert config.model == "gpt-4o"
        assert config.stream is True
        assert config.iterations == 5


class TestScenarioResult:
    """Tests for ScenarioResult dataclass."""
    
    def test_empty_result(self):
        """Test empty result."""
        from praisonai.cli.features.profiler import ScenarioConfig, ScenarioResult
        
        config = ScenarioConfig(name="test", prompt="hi")
        result = ScenarioResult(name="test", config=config)
        
        assert result.name == "test"
        assert len(result.results) == 0
        assert result.import_times == []
        assert result.total_times == []
    
    def test_get_stats_empty(self):
        """Test stats with empty values."""
        from praisonai.cli.features.profiler import ScenarioConfig, ScenarioResult
        
        config = ScenarioConfig(name="test", prompt="hi")
        result = ScenarioResult(name="test", config=config)
        
        stats = result.get_stats([])
        assert stats["mean"] == 0
        assert stats["min"] == 0
        assert stats["max"] == 0
    
    def test_get_stats_single_value(self):
        """Test stats with single value."""
        from praisonai.cli.features.profiler import ScenarioConfig, ScenarioResult
        
        config = ScenarioConfig(name="test", prompt="hi")
        result = ScenarioResult(name="test", config=config)
        
        stats = result.get_stats([100.0])
        assert stats["mean"] == 100.0
        assert stats["min"] == 100.0
        assert stats["max"] == 100.0
        assert stats["stdev"] == 0
    
    def test_get_stats_multiple_values(self):
        """Test stats with multiple values."""
        from praisonai.cli.features.profiler import ScenarioConfig, ScenarioResult
        
        config = ScenarioConfig(name="test", prompt="hi")
        result = ScenarioResult(name="test", config=config)
        
        stats = result.get_stats([100.0, 200.0, 300.0])
        assert stats["mean"] == 200.0
        assert stats["min"] == 100.0
        assert stats["max"] == 300.0
        assert stats["median"] == 200.0
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from praisonai.cli.features.profiler import ScenarioConfig, ScenarioResult
        
        config = ScenarioConfig(name="test", prompt="hi", iterations=2)
        result = ScenarioResult(name="test", config=config)
        
        data = result.to_dict()
        assert data["name"] == "test"
        assert "config" in data
        assert data["config"]["prompt"] == "hi"
        assert "import_time_stats" in data
        assert "total_time_stats" in data


class TestSuiteResult:
    """Tests for SuiteResult dataclass."""
    
    def test_default_result(self):
        """Test default result."""
        from praisonai.cli.features.profiler import SuiteResult
        
        result = SuiteResult()
        assert len(result.scenarios) == 0
        assert result.startup_cold_ms == 0.0
        assert result.startup_warm_ms == 0.0
        assert len(result.import_analysis) == 0
        assert result.timestamp.endswith("Z")  # ISO format with Z suffix
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from praisonai.cli.features.profiler import SuiteResult
        
        result = SuiteResult(
            startup_cold_ms=100.0,
            startup_warm_ms=50.0,
        )
        
        data = result.to_dict()
        assert "timestamp" in data
        assert "metadata" in data
        assert data["startup"]["cold_ms"] == 100.0
        assert data["startup"]["warm_ms"] == 50.0


class TestProfileSuiteRunner:
    """Tests for ProfileSuiteRunner class."""
    
    def test_init_default(self):
        """Test initialization with defaults."""
        from praisonai.cli.features.profiler import ProfileSuiteRunner
        
        runner = ProfileSuiteRunner()
        assert len(runner.scenarios) == 4  # DEFAULT_SCENARIOS
        assert runner.verbose is False
    
    def test_init_custom_scenarios(self):
        """Test initialization with custom scenarios."""
        from praisonai.cli.features.profiler import ProfileSuiteRunner, ScenarioConfig
        
        scenarios = [
            ScenarioConfig(name="custom1", prompt="test1"),
            ScenarioConfig(name="custom2", prompt="test2"),
        ]
        
        runner = ProfileSuiteRunner(scenarios=scenarios)
        assert len(runner.scenarios) == 2
        assert runner.scenarios[0].name == "custom1"
    
    def test_collect_metadata(self):
        """Test metadata collection."""
        from praisonai.cli.features.profiler import ProfileSuiteRunner
        
        runner = ProfileSuiteRunner()
        metadata = runner._collect_metadata()
        
        assert "python_version" in metadata
        assert "platform" in metadata
        assert "praisonai_version" in metadata
        assert "timestamp" in metadata
    
    def test_measure_startup(self):
        """Test startup measurement."""
        from praisonai.cli.features.profiler import ProfileSuiteRunner
        
        runner = ProfileSuiteRunner()
        cold, warm = runner._measure_startup()
        
        # Both should be positive numbers
        assert cold > 0
        assert warm > 0
    
    def test_analyze_imports(self):
        """Test import analysis."""
        from praisonai.cli.features.profiler import ProfileSuiteRunner
        
        runner = ProfileSuiteRunner()
        imports = runner._analyze_imports()
        
        # Should return a list (may be empty if subprocess fails)
        assert isinstance(imports, list)
        
        # If we got results, check structure
        if imports:
            assert "module" in imports[0]
            assert "cumulative_ms" in imports[0]


class TestProfilerModuleImports:
    """Tests for profiler module imports."""
    
    def test_all_exports_available(self):
        """Test that all exports are available."""
        from praisonai.cli.features.profiler import (
            ProfilerConfig,
            ProfilerResult,
            QueryProfiler,
            run_profiled_query,
            format_profile_report,
            ScenarioConfig,
            ScenarioResult,
            SuiteResult,
            ProfileSuiteRunner,
            run_profile_suite,
        )
        
        assert ProfilerConfig is not None
        assert ProfilerResult is not None
        assert QueryProfiler is not None
        assert run_profiled_query is not None
        assert format_profile_report is not None
        assert ScenarioConfig is not None
        assert ScenarioResult is not None
        assert SuiteResult is not None
        assert ProfileSuiteRunner is not None
        assert run_profile_suite is not None
