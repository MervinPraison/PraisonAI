"""
Unit tests for CLI compare feature.

Tests cover:
- CompareHandler initialization
- Mode configuration
- Comparison execution
- Result formatting
- Output saving
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestCompareHandler:
    """Tests for CompareHandler class."""
    
    def test_init_default_values(self):
        """Test default initialization values."""
        from praisonai.cli.features.compare import CompareHandler
        
        handler = CompareHandler()
        assert handler.verbose is False
        assert handler.results == []
    
    def test_init_with_verbose(self):
        """Test initialization with verbose flag."""
        from praisonai.cli.features.compare import CompareHandler
        
        handler = CompareHandler(verbose=True)
        assert handler.verbose is True


class TestCompareModes:
    """Tests for comparison mode definitions."""
    
    def test_get_mode_config_basic(self):
        """Test getting basic mode configuration."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("basic")
        assert config == {}
    
    def test_get_mode_config_tools(self):
        """Test getting tools mode configuration."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("tools")
        assert "tools" in config
    
    def test_get_mode_config_research(self):
        """Test getting research mode configuration."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("research")
        assert config.get("research") is True
    
    def test_get_mode_config_planning(self):
        """Test getting planning mode configuration."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("planning")
        assert config.get("planning") is True
    
    def test_get_mode_config_memory(self):
        """Test getting memory mode configuration."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("memory")
        assert config.get("memory") is True
    
    def test_get_mode_config_router(self):
        """Test getting router mode configuration."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("router")
        assert config.get("router") is True
    
    def test_get_mode_config_web_search(self):
        """Test getting web_search mode configuration."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("web_search")
        assert config.get("web_search") is True
    
    def test_get_mode_config_unknown(self):
        """Test getting unknown mode returns empty config."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("unknown_mode")
        assert config == {}
    
    def test_get_mode_config_with_custom_args(self):
        """Test getting mode config with custom args override."""
        from praisonai.cli.features.compare import get_mode_config
        
        config = get_mode_config("basic", {"llm": "gpt-4o"})
        assert config.get("llm") == "gpt-4o"
    
    def test_list_available_modes(self):
        """Test listing all available modes."""
        from praisonai.cli.features.compare import list_available_modes
        
        modes = list_available_modes()
        assert "basic" in modes
        assert "tools" in modes
        assert "research" in modes
        assert "planning" in modes


class TestModeResult:
    """Tests for ModeResult dataclass."""
    
    def test_mode_result_creation(self):
        """Test creating a ModeResult."""
        from praisonai.cli.features.compare import ModeResult
        
        result = ModeResult(
            mode="basic",
            output="Test output",
            execution_time_ms=1234.5,
            model_used="gpt-4o-mini"
        )
        assert result.mode == "basic"
        assert result.output == "Test output"
        assert result.execution_time_ms == 1234.5
        assert result.model_used == "gpt-4o-mini"
    
    def test_mode_result_with_tokens(self):
        """Test ModeResult with token usage."""
        from praisonai.cli.features.compare import ModeResult
        
        result = ModeResult(
            mode="tools",
            output="Output",
            execution_time_ms=2000.0,
            model_used="gpt-4o-mini",
            tokens={"input": 100, "output": 200}
        )
        assert result.tokens["input"] == 100
        assert result.tokens["output"] == 200
    
    def test_mode_result_with_tools(self):
        """Test ModeResult with tools used."""
        from praisonai.cli.features.compare import ModeResult
        
        result = ModeResult(
            mode="tools",
            output="Output",
            execution_time_ms=2000.0,
            model_used="gpt-4o-mini",
            tools_used=["internet_search", "calculator"]
        )
        assert "internet_search" in result.tools_used
        assert "calculator" in result.tools_used
    
    def test_mode_result_to_dict(self):
        """Test converting ModeResult to dictionary."""
        from praisonai.cli.features.compare import ModeResult
        
        result = ModeResult(
            mode="basic",
            output="Test",
            execution_time_ms=1000.0,
            model_used="gpt-4o-mini"
        )
        d = result.to_dict()
        assert d["mode"] == "basic"
        assert d["execution_time_ms"] == 1000.0


class TestCompareResult:
    """Tests for CompareResult dataclass."""
    
    def test_compare_result_creation(self):
        """Test creating a CompareResult."""
        from praisonai.cli.features.compare import CompareResult, ModeResult
        
        result = CompareResult(
            query="What is AI?",
            comparisons=[
                ModeResult(mode="basic", output="AI is...", execution_time_ms=1000, model_used="gpt-4o-mini"),
                ModeResult(mode="tools", output="Based on search...", execution_time_ms=2000, model_used="gpt-4o-mini"),
            ]
        )
        assert result.query == "What is AI?"
        assert len(result.comparisons) == 2
    
    def test_compare_result_summary(self):
        """Test CompareResult summary generation."""
        from praisonai.cli.features.compare import CompareResult, ModeResult
        
        result = CompareResult(
            query="Test",
            comparisons=[
                ModeResult(mode="basic", output="A", execution_time_ms=1000, model_used="gpt-4o-mini"),
                ModeResult(mode="tools", output="B", execution_time_ms=2000, model_used="gpt-4o-mini"),
            ]
        )
        summary = result.get_summary()
        assert summary["fastest"] == "basic"
        assert summary["slowest"] == "tools"
    
    def test_compare_result_to_dict(self):
        """Test converting CompareResult to dictionary."""
        from praisonai.cli.features.compare import CompareResult, ModeResult
        
        result = CompareResult(
            query="Test",
            comparisons=[
                ModeResult(mode="basic", output="A", execution_time_ms=1000, model_used="gpt-4o-mini"),
            ]
        )
        d = result.to_dict()
        assert d["query"] == "Test"
        assert "comparisons" in d
        assert "summary" in d
    
    def test_compare_result_to_json(self):
        """Test converting CompareResult to JSON."""
        from praisonai.cli.features.compare import CompareResult, ModeResult
        
        result = CompareResult(
            query="Test",
            comparisons=[
                ModeResult(mode="basic", output="A", execution_time_ms=1000, model_used="gpt-4o-mini"),
            ]
        )
        json_str = result.to_json()
        data = json.loads(json_str)
        assert data["query"] == "Test"


class TestCompareExecution:
    """Tests for comparison execution."""
    
    @patch('praisonai.cli.features.compare.CompareHandler._run_mode')
    def test_compare_single_mode(self, mock_run_mode):
        """Test comparing with single mode."""
        from praisonai.cli.features.compare import CompareHandler, ModeResult
        
        mock_run_mode.return_value = ModeResult(
            mode="basic",
            output="Test output",
            execution_time_ms=1000,
            model_used="gpt-4o-mini"
        )
        
        handler = CompareHandler()
        result = handler.compare("What is AI?", modes=["basic"])
        
        assert len(result.comparisons) == 1
        assert result.comparisons[0].mode == "basic"
    
    @patch('praisonai.cli.features.compare.CompareHandler._run_mode')
    def test_compare_multiple_modes(self, mock_run_mode):
        """Test comparing with multiple modes."""
        from praisonai.cli.features.compare import CompareHandler, ModeResult
        
        def side_effect(query, mode, **kwargs):
            return ModeResult(
                mode=mode,
                output=f"Output for {mode}",
                execution_time_ms=1000 if mode == "basic" else 2000,
                model_used="gpt-4o-mini"
            )
        
        mock_run_mode.side_effect = side_effect
        
        handler = CompareHandler()
        result = handler.compare("What is AI?", modes=["basic", "tools"])
        
        assert len(result.comparisons) == 2
        assert result.comparisons[0].mode == "basic"
        assert result.comparisons[1].mode == "tools"
    
    @patch('praisonai.cli.features.compare.CompareHandler._run_mode')
    def test_compare_with_model_override(self, mock_run_mode):
        """Test comparing with model override."""
        from praisonai.cli.features.compare import CompareHandler, ModeResult
        
        mock_run_mode.return_value = ModeResult(
            mode="basic",
            output="Test",
            execution_time_ms=1000,
            model_used="gpt-4o"
        )
        
        handler = CompareHandler()
        compare_result = handler.compare("Test", modes=["basic"], model="gpt-4o")
        
        mock_run_mode.assert_called_once()
        call_kwargs = mock_run_mode.call_args[1]
        assert call_kwargs.get("model") == "gpt-4o"
        assert compare_result.query == "Test"


class TestCompareOutput:
    """Tests for comparison output formatting and saving."""
    
    def test_save_result_to_file(self):
        """Test saving comparison result to file."""
        from praisonai.cli.features.compare import CompareResult, ModeResult, save_compare_result
        
        result = CompareResult(
            query="Test",
            comparisons=[
                ModeResult(mode="basic", output="A", execution_time_ms=1000, model_used="gpt-4o-mini"),
            ]
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/result.json"
            success = save_compare_result(result, path)
            
            assert success is True
            assert Path(path).exists()
            
            with open(path) as f:
                data = json.load(f)
            assert data["query"] == "Test"
    
    def test_format_comparison_table(self):
        """Test formatting comparison as table."""
        from praisonai.cli.features.compare import CompareResult, ModeResult, format_comparison_table
        
        result = CompareResult(
            query="Test",
            comparisons=[
                ModeResult(mode="basic", output="A", execution_time_ms=1000, model_used="gpt-4o-mini"),
                ModeResult(mode="tools", output="B", execution_time_ms=2000, model_used="gpt-4o-mini"),
            ]
        )
        
        table_str = format_comparison_table(result)
        assert "basic" in table_str
        assert "tools" in table_str


class TestParseModes:
    """Tests for mode parsing from CLI input."""
    
    def test_parse_modes_comma_separated(self):
        """Test parsing comma-separated modes."""
        from praisonai.cli.features.compare import parse_modes
        
        modes = parse_modes("basic,tools,research")
        assert modes == ["basic", "tools", "research"]
    
    def test_parse_modes_single(self):
        """Test parsing single mode."""
        from praisonai.cli.features.compare import parse_modes
        
        modes = parse_modes("basic")
        assert modes == ["basic"]
    
    def test_parse_modes_with_spaces(self):
        """Test parsing modes with spaces."""
        from praisonai.cli.features.compare import parse_modes
        
        modes = parse_modes("basic, tools, research")
        assert modes == ["basic", "tools", "research"]
    
    def test_parse_modes_empty(self):
        """Test parsing empty string returns default."""
        from praisonai.cli.features.compare import parse_modes
        
        modes = parse_modes("")
        assert modes == ["basic"]


class TestCompareWithModel:
    """Tests for comparison with model override."""
    
    @patch('praisonai.cli.features.compare.CompareHandler._run_mode')
    def test_compare_execute_with_output_path(self, mock_run_mode):
        """Test execute method with output path."""
        from praisonai.cli.features.compare import CompareHandler, ModeResult
        
        mock_run_mode.return_value = ModeResult(
            mode="basic",
            output="Test output",
            execution_time_ms=1000,
            model_used="gpt-4o-mini"
        )
        
        handler = CompareHandler()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/result.json"
            compare_result = handler.execute("Test query", "basic", output_path=output_path)
            
            assert Path(output_path).exists()
            assert compare_result.query == "Test query"
