"""
Unit tests for the praisonai test CLI command.

Tests the test tier and provider options without actually running pytest.
"""

import os

# Import the module under test
from praisonai.cli.commands.test import (
    _get_pytest_args,
    _set_environment,
)


class TestGetPytestArgs:
    """Tests for _get_pytest_args function."""
    
    def test_smoke_tier_args(self):
        """Smoke tier should target unit tests only with no slow/network."""
        args = _get_pytest_args(
            tier="smoke",
            provider=None,
            live=False,
            parallel=None,
            verbose=False,
            coverage=False,
        )
        assert "tests/unit/" in args
        assert "-m" in args
        assert "not slow and not network" in args
        assert "--timeout=30" in args
    
    def test_main_tier_args(self):
        """Main tier should exclude non-OpenAI providers."""
        args = _get_pytest_args(
            tier="main",
            provider=None,
            live=False,
            parallel=None,
            verbose=False,
            coverage=False,
        )
        assert "tests/unit/" in args
        assert "tests/integration/" in args
        assert "-m" in args
        # Should exclude non-OpenAI providers - find the marker expression
        # The -m flag may appear multiple times, find the one with provider exclusions
        found_exclusion = False
        for i, arg in enumerate(args):
            if arg == "-m" and i + 1 < len(args):
                marker_expr = args[i + 1]
                if "provider_anthropic" in marker_expr and "provider_google" in marker_expr:
                    found_exclusion = True
                    break
        assert found_exclusion, f"Expected provider exclusion markers in args: {args}"
    
    def test_extended_tier_args(self):
        """Extended tier should include all tests."""
        args = _get_pytest_args(
            tier="extended",
            provider=None,
            live=False,
            parallel=None,
            verbose=False,
            coverage=False,
        )
        assert "tests/" in args
        assert "--timeout=120" in args
    
    def test_provider_filter(self):
        """Provider option should add provider marker filter."""
        args = _get_pytest_args(
            tier="main",
            provider="anthropic",
            live=False,
            parallel=None,
            verbose=False,
            coverage=False,
        )
        assert "-m" in args
        # Find the provider marker
        found_provider = False
        for i, arg in enumerate(args):
            if arg == "-m" and i + 1 < len(args):
                if "provider_anthropic" in args[i + 1]:
                    found_provider = True
        assert found_provider
    
    def test_parallel_auto(self):
        """Parallel auto should add -n auto."""
        args = _get_pytest_args(
            tier="main",
            provider=None,
            live=False,
            parallel="auto",
            verbose=False,
            coverage=False,
        )
        assert "-n" in args
        assert "auto" in args
    
    def test_parallel_number(self):
        """Parallel with number should add -n <number>."""
        args = _get_pytest_args(
            tier="main",
            provider=None,
            live=False,
            parallel="4",
            verbose=False,
            coverage=False,
        )
        assert "-n" in args
        assert "4" in args
    
    def test_verbose_flag(self):
        """Verbose should add -v flag."""
        args = _get_pytest_args(
            tier="main",
            provider=None,
            live=False,
            parallel=None,
            verbose=True,
            coverage=False,
        )
        assert "-v" in args
        assert "-q" not in args
    
    def test_quiet_by_default(self):
        """Non-verbose should add -q flag."""
        args = _get_pytest_args(
            tier="main",
            provider=None,
            live=False,
            parallel=None,
            verbose=False,
            coverage=False,
        )
        assert "-q" in args
        assert "-v" not in args
    
    def test_coverage_flag(self):
        """Coverage should add coverage args."""
        args = _get_pytest_args(
            tier="main",
            provider=None,
            live=False,
            parallel=None,
            verbose=False,
            coverage=True,
        )
        assert "--cov=praisonai" in args
        assert "--cov-report=term-missing" in args
        assert "--cov-report=xml" in args
    
    def test_always_ignores_fixtures(self):
        """All tiers should ignore fixtures directory."""
        for tier in ["smoke", "main", "extended", "nightly"]:
            args = _get_pytest_args(
                tier=tier,
                provider=None,
                live=False,
                parallel=None,
                verbose=False,
                coverage=False,
            )
            assert "--ignore=tests/fixtures" in args


class TestSetEnvironment:
    """Tests for _set_environment function."""
    
    def test_sets_tier(self):
        """Should set PRAISONAI_TEST_TIER."""
        _set_environment("smoke", None, False)
        assert os.environ.get("PRAISONAI_TEST_TIER") == "smoke"
    
    def test_live_enables_network(self):
        """Live mode should enable network and live tests."""
        _set_environment("main", None, True)
        assert os.environ.get("PRAISONAI_ALLOW_NETWORK") == "1"
        assert os.environ.get("PRAISONAI_LIVE_TESTS") == "1"
    
    def test_no_live_disables_network(self):
        """Non-live mode should disable network."""
        _set_environment("main", None, False)
        assert os.environ.get("PRAISONAI_ALLOW_NETWORK") == "0"
        assert os.environ.get("PRAISONAI_LIVE_TESTS") == "0"
    
    def test_sets_provider(self):
        """Should set PRAISONAI_TEST_PROVIDERS when provider specified."""
        _set_environment("main", "anthropic", False)
        assert os.environ.get("PRAISONAI_TEST_PROVIDERS") == "anthropic"


class TestTestGatingPlugin:
    """Tests for the test gating plugin functionality."""
    
    def test_provider_patterns_detect_openai(self):
        """Provider patterns should detect OpenAI references."""
        from tests._pytest_plugins.test_gating import PROVIDER_PATTERNS
        
        pattern = PROVIDER_PATTERNS['provider_openai']
        assert pattern.search("from openai import OpenAI")
        assert pattern.search("gpt-4 model")
        assert pattern.search("ChatGPT response")
    
    def test_provider_patterns_detect_anthropic(self):
        """Provider patterns should detect Anthropic references."""
        from tests._pytest_plugins.test_gating import PROVIDER_PATTERNS
        
        pattern = PROVIDER_PATTERNS['provider_anthropic']
        assert pattern.search("from anthropic import Client")
        assert pattern.search("claude-3 model")
    
    def test_provider_patterns_detect_ollama(self):
        """Provider patterns should detect Ollama references."""
        from tests._pytest_plugins.test_gating import PROVIDER_PATTERNS
        
        pattern = PROVIDER_PATTERNS['provider_ollama']
        assert pattern.search("ollama run llama")
        assert pattern.search("Ollama client")
    
    def test_get_test_type_from_path(self):
        """Should detect test type from path."""
        from tests._pytest_plugins.test_gating import _get_test_type_from_path
        
        assert _get_test_type_from_path("tests/unit/test_foo.py") == "unit"
        assert _get_test_type_from_path("tests/integration/test_bar.py") == "integration"
        assert _get_test_type_from_path("tests/e2e/test_baz.py") == "e2e"
        assert _get_test_type_from_path("tests/live/test_qux.py") == "e2e"
        assert _get_test_type_from_path("tests/test_random.py") is None


class TestNetworkGuard:
    """Tests for the network guard plugin."""
    
    def test_localhost_allowed(self):
        """Localhost connections should always be allowed."""
        from tests._pytest_plugins.network_guard import _is_localhost
        
        assert _is_localhost(("127.0.0.1", 8080))
        assert _is_localhost(("localhost", 80))
        assert _is_localhost(("::1", 443))
        assert not _is_localhost(("example.com", 80))
        assert not _is_localhost(("8.8.8.8", 53))


class TestExcludedPaths:
    """Tests for the excluded path detection in gating plugin."""
    
    def test_pytest_plugins_excluded(self):
        """_pytest_plugins directory should be excluded from provider detection."""
        from tests._pytest_plugins.test_gating import _is_excluded_path
        
        assert _is_excluded_path("/path/to/tests/_pytest_plugins/test_gating.py")
        assert _is_excluded_path("/path/to/tests/_pytest_plugins/network_guard.py")
        assert _is_excluded_path("tests/_pytest_plugins/some_file.py")
    
    def test_meta_excluded(self):
        """_meta directory should be excluded from provider detection."""
        from tests._pytest_plugins.test_gating import _is_excluded_path
        
        assert _is_excluded_path("/path/to/tests/_meta/inventory.json")
        assert _is_excluded_path("tests/_meta/anything.py")
    
    def test_conftest_excluded(self):
        """conftest files should be excluded from provider detection."""
        from tests._pytest_plugins.test_gating import _is_excluded_path
        
        assert _is_excluded_path("/path/to/tests/conftest.py")
        assert _is_excluded_path("conftest.py")
    
    def test_fixtures_excluded(self):
        """fixtures directory should be excluded from provider detection."""
        from tests._pytest_plugins.test_gating import _is_excluded_path
        
        assert _is_excluded_path("/path/to/tests/fixtures/mock_data.py")
        assert _is_excluded_path("tests/fixtures/")
    
    def test_regular_tests_not_excluded(self):
        """Regular test files should NOT be excluded."""
        from tests._pytest_plugins.test_gating import _is_excluded_path
        
        assert not _is_excluded_path("/path/to/tests/unit/test_agent.py")
        assert not _is_excluded_path("tests/integration/test_openai.py")
        assert not _is_excluded_path("tests/e2e/test_workflow.py")
    
    def test_nodeid_also_checked(self):
        """Nodeid should also be checked for exclusions."""
        from tests._pytest_plugins.test_gating import _is_excluded_path
        
        # Even if filepath doesn't match, nodeid should be checked
        assert _is_excluded_path("/some/path.py", "tests/_pytest_plugins/test_gating.py::test_foo")
        assert not _is_excluded_path("/some/path.py", "tests/unit/test_agent.py::test_bar")
