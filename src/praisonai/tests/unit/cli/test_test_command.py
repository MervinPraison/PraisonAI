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


class TestProviderMarkerGranularity:
    """The gating plugin must mark per test function, not per file.

    Regression guard for D7: one Ollama test used to tag its whole file
    provider_ollama, and the plugin implies `network` from any provider marker,
    so six unrelated fully-mocked tests were deselected in every CI job.
    """

    MIXED_SOURCE = '''
import pytest

class TestMixed:
    def test_mocked_openai_only(self):
        model = "openai/gpt-4o"
        assert model

    def test_mentions_ollama(self):
        assert "ollama/llama2"

def test_module_level_plain():
    assert True
'''

    def _map(self, tmp_path):
        from tests._pytest_plugins.test_gating import (
            _build_per_test_provider_map, _file_provider_cache, _file_content_cache,
        )
        _file_provider_cache.clear()
        _file_content_cache.clear()
        f = tmp_path / "test_mixed_providers.py"
        f.write_text(self.MIXED_SOURCE)
        return _build_per_test_provider_map(f)

    def test_ollama_does_not_leak_to_sibling_tests(self, tmp_path):
        """THE meta-test. If this fails, D7 has regressed."""
        m = self._map(tmp_path)
        assert 'provider_ollama' not in m[('TestMixed', 'test_mocked_openai_only')]
        assert 'provider_ollama' in m[('TestMixed', 'test_mentions_ollama')]

    def test_openai_does_not_leak_to_sibling_tests(self, tmp_path):
        m = self._map(tmp_path)
        assert 'provider_openai' in m[('TestMixed', 'test_mocked_openai_only')]
        assert 'provider_openai' not in m[('TestMixed', 'test_mentions_ollama')]

    def test_plain_test_gets_no_provider_markers(self, tmp_path):
        m = self._map(tmp_path)
        assert m[(None, 'test_module_level_plain')] == set()

    def test_decorators_are_scanned(self, tmp_path):
        """A provider named only in a parametrize decorator still counts."""
        from tests._pytest_plugins.test_gating import (
            _build_per_test_provider_map, _file_provider_cache, _file_content_cache,
        )
        _file_provider_cache.clear()
        _file_content_cache.clear()
        f = tmp_path / "test_decorated.py"
        f.write_text(
            'import pytest\n'
            '@pytest.mark.parametrize("m", ["ollama/llama2"])\n'
            'def test_decorated(m):\n'
            '    assert m\n'
        )
        got = _build_per_test_provider_map(f)[(None, 'test_decorated')]
        assert 'provider_ollama' in got

    def test_unparseable_file_falls_back_to_whole_file(self, tmp_path):
        """A file we cannot parse must stay conservatively over-marked."""
        from tests._pytest_plugins.test_gating import (
            _build_per_test_provider_map, _detect_providers_in_file,
            _file_provider_cache, _file_content_cache,
        )
        _file_provider_cache.clear()
        _file_content_cache.clear()
        f = tmp_path / "test_broken.py"
        f.write_text("def test_x(:\n    ollama\n")
        assert _build_per_test_provider_map(f) is None
        assert 'provider_ollama' in _detect_providers_in_file(f)

    def test_network_marker_remains_whole_file_derived(self, tmp_path):
        """Narrowing providers must not narrow `network`.

        That is what keeps this change selection-neutral for the 96 integration
        tests that stay deselected. Letting `network` narrow too would newly
        select 48 tests, 25 of them with no skipif.
        """
        from tests._pytest_plugins.test_gating import (
            _detect_providers_in_file, _file_content_cache,
        )
        _file_content_cache.clear()
        f = tmp_path / "test_mixed_providers.py"
        f.write_text(self.MIXED_SOURCE)
        assert {'provider_openai', 'provider_ollama'} <= _detect_providers_in_file(f)

    def test_offline_marker_is_registered(self):
        """`offline` must be in both marker tables or every use warns."""
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[4]
        for ini in ("praisonai/pytest.ini", "praisonai-agents/pytest.ini"):
            text = (root / ini).read_text()
            assert "offline:" in text, f"{ini} is missing the offline marker"

    FIXTURE_SUPPLIED_SOURCE = '''
import pytest

@pytest.fixture
def sample_document():
    """A doc that names OpenAI, mirroring a live RAG fixture."""
    return "PraisonAI supports OpenAI, Anthropic and Google."

class TestRAGLive:
    def test_rag_query(self, sample_document):
        assert sample_document

def test_plain(sample_document):
    assert sample_document
'''

    def test_module_scope_provider_reaches_every_test(self, tmp_path):
        """A provider named only in a shared fixture must still mark each test.

        Guards the D7 follow-up: positive selectors like
        ``-m "provider_openai or real"`` must keep live tests whose provider
        identity is supplied by a module-level fixture, not the test body.
        """
        from tests._pytest_plugins.test_gating import (
            _build_per_test_provider_map, _file_provider_cache, _file_content_cache,
        )
        _file_provider_cache.clear()
        _file_content_cache.clear()
        f = tmp_path / "test_fixture_supplied.py"
        f.write_text(self.FIXTURE_SUPPLIED_SOURCE)
        m = _build_per_test_provider_map(f)
        assert 'provider_openai' in m[('TestRAGLive', 'test_rag_query')]
        assert 'provider_openai' in m[(None, 'test_plain')]

    def test_module_scope_does_not_leak_sibling_bodies(self, tmp_path):
        """Module-scope union must not reintroduce sibling-body leakage.

        A provider named only inside one test body stays out of its siblings.
        """
        from tests._pytest_plugins.test_gating import (
            _build_per_test_provider_map, _file_provider_cache, _file_content_cache,
        )
        _file_provider_cache.clear()
        _file_content_cache.clear()
        f = tmp_path / "test_mixed_providers.py"
        f.write_text(self.MIXED_SOURCE)
        m = _build_per_test_provider_map(f)
        assert 'provider_ollama' not in m[('TestMixed', 'test_mocked_openai_only')]
        assert 'provider_openai' not in m[('TestMixed', 'test_mentions_ollama')]
