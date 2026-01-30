"""
TDD Tests for Unified Parameter Resolver.

Tests the precedence rules: Instance > Config > Array > String > Bool > Default

These tests are written FIRST (TDD approach) to define expected behavior.
"""

import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# =============================================================================
# Test Fixtures - Mock Config Classes
# =============================================================================

@dataclass
class MockMemoryConfig:
    """Mock memory config for testing."""
    backend: str = "file"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


@dataclass
class MockOutputConfig:
    """Mock output config for testing."""
    verbose: bool = True
    markdown: bool = True
    stream: bool = False


@dataclass
class MockExecutionConfig:
    """Mock execution config for testing."""
    max_iter: int = 20
    max_retry_limit: int = 2


@dataclass
class MockKnowledgeConfig:
    """Mock knowledge config for testing."""
    sources: List[str] = field(default_factory=list)
    embedder: str = "openai"


@dataclass
class MockWebConfig:
    """Mock web config for testing."""
    search: bool = True
    fetch: bool = True
    search_provider: str = "duckduckgo"


class MockMemoryInstance:
    """Mock memory instance with search/add methods."""
    def search(self, query: str) -> List[str]:
        return []
    
    def add(self, content: str) -> None:
        pass


class MockDbInstance:
    """Mock database instance."""
    def __init__(self, database_url: str):
        self.database_url = database_url
    
    def connect(self):
        pass


# =============================================================================
# Test: Precedence Order - Instance > Config > Array > String > Bool > Default
# =============================================================================

class TestPrecedenceOrder:
    """Test that precedence rules are correctly enforced."""
    
    def test_none_returns_default(self):
        """None value should return the default."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=None,
            param_name="memory",
            config_class=MockMemoryConfig,
            default=None,
        )
        assert result is None
    
    def test_instance_takes_highest_precedence(self):
        """Instance should be returned as-is (highest precedence)."""
        from praisonaiagents.config.param_resolver import resolve
        
        instance = MockMemoryInstance()
        result = resolve(
            value=instance,
            param_name="memory",
            config_class=MockMemoryConfig,
            instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
        )
        assert result is instance
    
    def test_config_takes_precedence_over_array(self):
        """Config instance should be returned as-is."""
        from praisonaiagents.config.param_resolver import resolve
        
        config = MockMemoryConfig(backend="redis", user_id="test123")
        result = resolve(
            value=config,
            param_name="memory",
            config_class=MockMemoryConfig,
        )
        assert result is config
        assert result.backend == "redis"
        assert result.user_id == "test123"
    
    def test_array_takes_precedence_over_string(self):
        """Array should be parsed before string."""
        from praisonaiagents.config.param_resolver import resolve
        
        # Array with preset + overrides
        result = resolve(
            value=["verbose", {"stream": True}],
            param_name="output",
            config_class=MockOutputConfig,
            presets={
                "verbose": MockOutputConfig(verbose=True, markdown=True, stream=False),
            },
            array_mode="preset_override",
        )
        assert isinstance(result, MockOutputConfig)
        assert result.verbose is True
        assert result.stream is True  # Override applied
    
    def test_string_takes_precedence_over_bool(self):
        """String preset should be resolved before bool."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value="verbose",
            param_name="output",
            config_class=MockOutputConfig,
            presets={
                "verbose": MockOutputConfig(verbose=True, markdown=True, stream=False),
            },
        )
        assert isinstance(result, MockOutputConfig)
        assert result.verbose is True
    
    def test_bool_true_returns_default_config(self):
        """Bool True should return default config instance."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=True,
            param_name="memory",
            config_class=MockMemoryConfig,
        )
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "file"  # Default
    
    def test_bool_false_returns_none(self):
        """Bool False should return None (disabled)."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=False,
            param_name="memory",
            config_class=MockMemoryConfig,
        )
        assert result is None


# =============================================================================
# Test: String Parsing
# =============================================================================

class TestStringParsing:
    """Test string parsing for various patterns."""
    
    def test_preset_string_lookup(self):
        """String should lookup in presets dict."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "fast": MockExecutionConfig(max_iter=10, max_retry_limit=1),
            "thorough": MockExecutionConfig(max_iter=50, max_retry_limit=5),
        }
        
        result = resolve(
            value="fast",
            param_name="execution",
            config_class=MockExecutionConfig,
            presets=presets,
        )
        assert result.max_iter == 10
        assert result.max_retry_limit == 1
    
    def test_url_string_detection_postgresql(self):
        """PostgreSQL URL should be detected and parsed."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value="postgresql://postgres:praison123@localhost:5432/praisonai",
            param_name="memory",
            config_class=MockMemoryConfig,
            url_schemes={"postgresql": "postgres", "postgres": "postgres"},
        )
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "postgres"
        assert result.config is not None
        assert "url" in result.config
    
    def test_url_string_detection_redis(self):
        """Redis URL should be detected and parsed."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value="redis://localhost:6379",
            param_name="memory",
            config_class=MockMemoryConfig,
            url_schemes={"redis": "redis"},
        )
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "redis"
    
    def test_url_string_detection_sqlite(self):
        """SQLite URL should be detected and parsed."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value="sqlite:///data.db",
            param_name="memory",
            config_class=MockMemoryConfig,
            url_schemes={"sqlite": "sqlite"},
        )
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "sqlite"
    
    def test_path_string_for_knowledge(self):
        """Path-like string should be treated as source."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value="docs/",
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
            string_mode="path_as_source",
        )
        assert isinstance(result, MockKnowledgeConfig)
        assert "docs/" in result.sources
    
    def test_invalid_preset_raises_error_with_suggestion(self):
        """Invalid preset should raise helpful error with suggestion."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "fast": MockExecutionConfig(max_iter=10, max_retry_limit=1),
            "thorough": MockExecutionConfig(max_iter=50, max_retry_limit=5),
        }
        
        with pytest.raises(ValueError) as exc_info:
            resolve(
                value="fsat",  # Typo
                param_name="execution",
                config_class=MockExecutionConfig,
                presets=presets,
            )
        
        error_msg = str(exc_info.value)
        assert "fsat" in error_msg
        assert "fast" in error_msg  # Suggestion
        assert "execution" in error_msg


# =============================================================================
# Test: Array Parsing
# =============================================================================

class TestArrayParsing:
    """Test array parsing for various patterns."""
    
    def test_single_item_url_array(self):
        """Single-item array with URL should be treated as URL."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=["postgresql://localhost/db"],
            param_name="memory",
            config_class=MockMemoryConfig,
            url_schemes={"postgresql": "postgres"},
            array_mode="single_or_list",
        )
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "postgres"
    
    def test_preset_with_overrides_array(self):
        """Array with preset + dict should apply overrides."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "verbose": MockOutputConfig(verbose=True, markdown=True, stream=False),
        }
        
        result = resolve(
            value=["verbose", {"stream": True, "markdown": False}],
            param_name="output",
            config_class=MockOutputConfig,
            presets=presets,
            array_mode="preset_override",
        )
        assert result.verbose is True  # From preset
        assert result.stream is True  # Override
        assert result.markdown is False  # Override
    
    def test_sources_list_array(self):
        """Array of strings should be treated as sources list."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=["docs/", "data.pdf", "https://example.com"],
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
            array_mode="sources",
        )
        assert isinstance(result, MockKnowledgeConfig)
        assert result.sources == ["docs/", "data.pdf", "https://example.com"]
    
    def test_sources_with_config_override(self):
        """Array of sources + config dict should merge."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=["docs/", "data.pdf", {"embedder": "cohere", "sources": ["extra/"]}],
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
            array_mode="sources_with_config",
        )
        assert isinstance(result, MockKnowledgeConfig)
        assert "docs/" in result.sources
        assert "data.pdf" in result.sources
        assert "extra/" in result.sources
        assert result.embedder == "cohere"
    
    def test_hooks_list_passthrough(self):
        """List of callables should be passed through."""
        from praisonaiagents.config.param_resolver import resolve
        
        def hook1(): pass
        def hook2(): pass
        
        result = resolve(
            value=[hook1, hook2],
            param_name="hooks",
            config_class=None,  # No config class for hooks list
            array_mode="passthrough",
        )
        assert result == [hook1, hook2]
    
    def test_empty_array_returns_none(self):
        """Empty array should return None (disabled)."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=[],
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
            array_mode="sources",
        )
        assert result is None


# =============================================================================
# Test: Dict Parsing
# =============================================================================

class TestDictParsing:
    """Test dict parsing."""
    
    def test_dict_converted_to_config(self):
        """Dict should be converted to config class."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value={"backend": "redis", "user_id": "test123"},
            param_name="memory",
            config_class=MockMemoryConfig,
        )
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "redis"
        assert result.user_id == "test123"


# =============================================================================
# Test: Performance - O(1) Happy Path
# =============================================================================

class TestPerformance:
    """Test that happy path operations are O(1)."""
    
    def test_no_fuzzy_matching_on_valid_preset(self):
        """Valid preset should not trigger fuzzy matching."""
        from praisonaiagents.config.param_resolver import resolve
        from praisonaiagents.config import parse_utils
        
        # Track if suggest_similar was called
        original_suggest = parse_utils.suggest_similar
        call_count = [0]
        
        def tracking_suggest(*args, **kwargs):
            call_count[0] += 1
            return original_suggest(*args, **kwargs)
        
        parse_utils.suggest_similar = tracking_suggest
        
        try:
            presets = {"fast": MockExecutionConfig(max_iter=10, max_retry_limit=1)}
            resolve(
                value="fast",
                param_name="execution",
                config_class=MockExecutionConfig,
                presets=presets,
            )
            assert call_count[0] == 0, "suggest_similar should not be called for valid preset"
        finally:
            parse_utils.suggest_similar = original_suggest
    
    def test_instance_check_is_fast(self):
        """Instance check should be a simple attribute check."""
        from praisonaiagents.config.param_resolver import resolve
        
        instance = MockMemoryInstance()
        
        # This should be O(1) - just hasattr checks
        result = resolve(
            value=instance,
            param_name="memory",
            config_class=MockMemoryConfig,
            instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
        )
        assert result is instance


# =============================================================================
# Test: Error Messages
# =============================================================================

class TestErrorMessages:
    """Test that error messages are helpful."""
    
    def test_invalid_preset_shows_available_options(self):
        """Error should list available presets."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "fast": MockExecutionConfig(max_iter=10, max_retry_limit=1),
            "thorough": MockExecutionConfig(max_iter=50, max_retry_limit=5),
            "unlimited": MockExecutionConfig(max_iter=1000, max_retry_limit=10),
        }
        
        with pytest.raises(ValueError) as exc_info:
            resolve(
                value="invalid",
                param_name="execution",
                config_class=MockExecutionConfig,
                presets=presets,
            )
        
        error_msg = str(exc_info.value)
        assert "fast" in error_msg
        assert "thorough" in error_msg
        assert "unlimited" in error_msg
    
    def test_invalid_url_scheme_shows_valid_schemes(self):
        """Error should list valid URL schemes."""
        from praisonaiagents.config.param_resolver import resolve
        
        with pytest.raises(ValueError) as exc_info:
            resolve(
                value="mongodb://localhost/db",  # Not supported
                param_name="memory",
                config_class=MockMemoryConfig,
                url_schemes={"postgresql": "postgres", "redis": "redis", "sqlite": "sqlite"},
            )
        
        error_msg = str(exc_info.value)
        assert "mongodb" in error_msg
        assert "postgresql" in error_msg or "redis" in error_msg


# =============================================================================
# Test: Memory Parameter Specific
# =============================================================================

class TestMemoryParameter:
    """Test memory parameter specific behaviors."""
    
    def test_memory_db_instance(self):
        """db() instance should be recognized."""
        from praisonaiagents.config.param_resolver import resolve
        
        db_instance = MockDbInstance("postgresql://localhost/db")
        
        result = resolve(
            value=db_instance,
            param_name="memory",
            config_class=MockMemoryConfig,
            instance_check=lambda v: hasattr(v, 'database_url') or (hasattr(v, 'search') and hasattr(v, 'add')),
        )
        assert result is db_instance
    
    def test_memory_string_preset(self):
        """Memory preset strings should work."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "file": MockMemoryConfig(backend="file"),
            "redis": MockMemoryConfig(backend="redis"),
            "postgres": MockMemoryConfig(backend="postgres"),
        }
        
        result = resolve(
            value="redis",
            param_name="memory",
            config_class=MockMemoryConfig,
            presets=presets,
        )
        assert result.backend == "redis"


# =============================================================================
# Test: Web Parameter Specific
# =============================================================================

class TestWebParameter:
    """Test web parameter specific behaviors."""
    
    def test_web_provider_string(self):
        """Web provider string should set provider."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "tavily": MockWebConfig(search=True, fetch=True, search_provider="tavily"),
            "duckduckgo": MockWebConfig(search=True, fetch=True, search_provider="duckduckgo"),
            "search_only": MockWebConfig(search=True, fetch=False),
        }
        
        result = resolve(
            value="tavily",
            param_name="web",
            config_class=MockWebConfig,
            presets=presets,
        )
        assert result.search_provider == "tavily"
    
    def test_web_mode_string(self):
        """Web mode string should configure search/fetch."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "search_only": MockWebConfig(search=True, fetch=False),
            "fetch_only": MockWebConfig(search=False, fetch=True),
        }
        
        result = resolve(
            value="search_only",
            param_name="web",
            config_class=MockWebConfig,
            presets=presets,
        )
        assert result.search is True
        assert result.fetch is False
    
    def test_web_array_provider_mode(self):
        """Web array with provider + mode should work."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "tavily": MockWebConfig(search=True, fetch=True, search_provider="tavily"),
        }
        
        result = resolve(
            value=["tavily", {"fetch": False}],
            param_name="web",
            config_class=MockWebConfig,
            presets=presets,
            array_mode="preset_override",
        )
        assert result.search_provider == "tavily"
        assert result.fetch is False


# =============================================================================
# Test: Workflow Step Context/Routing
# =============================================================================

class TestTaskParams:
    """Test workflow step specific parameters."""
    
    def test_context_step_names_array(self):
        """Context array of step names should work."""
        from praisonaiagents.config.param_resolver import resolve
        
        @dataclass
        class MockStepContextConfig:
            from_steps: List[str] = field(default_factory=list)
        
        result = resolve(
            value=["step1", "step2"],
            param_name="context",
            config_class=MockStepContextConfig,
            array_mode="step_names",
        )
        assert result.from_steps == ["step1", "step2"]
    
    def test_routing_step_names_array(self):
        """Routing array of step names should work."""
        from praisonaiagents.config.param_resolver import resolve
        
        @dataclass
        class MockRoutingConfig:
            next_steps: List[str] = field(default_factory=list)
        
        result = resolve(
            value=["next_step1", "next_step2"],
            param_name="routing",
            config_class=MockRoutingConfig,
            array_mode="step_names",
        )
        assert result.next_steps == ["next_step1", "next_step2"]
