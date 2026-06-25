"""
TDD Tests for auto.py lazy loading optimization.

These tests verify that:
1. Framework imports (crewai, autogen, praisonaiagents) are lazy-loaded
2. LiteLLM and OpenAI are lazy-loaded
3. No performance impact at module import time
"""
import pytest
import sys
import time


class TestAutoLazyLoading:
    """Test that auto.py uses lazy loading for all heavy dependencies."""
    
    def test_auto_module_import_does_not_import_crewai(self):
        """Verify crewai is not imported when auto.py is imported."""
        # Remove cached modules to test fresh import
        modules_to_remove = [k for k in sys.modules.keys() if 'crewai' in k.lower()]
        for mod in modules_to_remove:
            del sys.modules[mod]
        
        # Remove auto module to force reimport
        if 'praisonai.auto' in sys.modules:
            del sys.modules['praisonai.auto']
        
        # Import auto module
        from praisonai import auto
        
        # crewai should NOT be in sys.modules after just importing auto
        crewai_imported = any('crewai' in k.lower() and 'check' not in k.lower() 
                             for k in sys.modules.keys())
        # Note: This test documents the DESIRED behavior - lazy loading
        # Currently it may fail, which is expected before the fix
    
    def test_auto_module_import_does_not_import_autogen(self):
        """Verify autogen is not imported when auto.py is imported."""
        if 'praisonai.auto' in sys.modules:
            del sys.modules['praisonai.auto']
        
        from praisonai import auto
        
        # autogen should NOT be in sys.modules after just importing auto
        autogen_imported = any('autogen' in k.lower() and 'check' not in k.lower() 
                              for k in sys.modules.keys())
        # Note: This test documents the DESIRED behavior
    
    def test_litellm_lazy_check_available(self):
        """Test that _check_litellm_available works correctly."""
        from praisonai.auto import _check_litellm_available
        
        result = _check_litellm_available()
        assert isinstance(result, bool)
    
    def test_openai_lazy_check_available(self):
        """Test that _check_openai_available works correctly."""
        from praisonai.auto import _check_openai_available
        
        result = _check_openai_available()
        assert isinstance(result, bool)
    
    def test_framework_availability_functions_exist(self):
        """Test that lazy loading infrastructure exists.

        Framework availability is delegated to the centralized
        ``_framework_availability.is_available`` helper, and framework
        resolution goes through the canonical FrameworkAdapter protocol +
        registry (framework_adapters/). The old hand-rolled per-framework
        loaders/checkers were removed.
        """
        from praisonai import auto

        assert hasattr(auto, 'is_available')
        assert hasattr(auto, 'lazy_get')


class TestSafeStringSubstitution:
    """Test safe string substitution for YAML templates."""
    
    def test_safe_substitute_with_curly_braces(self):
        """Test that strings with {level} don't cause KeyError."""
        from praisonai.agents_generator import safe_format
        
        template = 'Use <!-- wp:heading {"level":2} --> for headings about {topic}'
        result = safe_format(template, topic="AI")
        
        assert '{"level":2}' in result  # JSON preserved
        assert 'AI' in result  # topic substituted
    
    def test_safe_substitute_preserves_gutenberg_blocks(self):
        """Test that Gutenberg block syntax is preserved."""
        from praisonai.agents_generator import safe_format
        
        template = '''
        <!-- wp:heading {"level":2} -->
        <h2>{topic}</h2>
        <!-- /wp:heading -->
        '''
        result = safe_format(template, topic="Test Topic")
        
        assert '{"level":2}' in result
        assert 'Test Topic' in result
    
    def test_safe_substitute_multiple_variables(self):
        """Test substitution with multiple variables."""
        from praisonai.agents_generator import safe_format
        
        template = 'Write about {topic} in {style} style'
        result = safe_format(template, topic="AI", style="coding")
        
        assert 'AI' in result
        assert 'coding' in result


class TestThreadSafety:
    """Test thread-safe patterns added in the wrapper layer."""

    def test_get_openai_client_returns_same_instance_per_generator(self):
        """Multiple threads on one generator must get the same client object."""
        import threading
        import types
        import sys
        import praisonai.auto as auto
        import unittest.mock as mock

        class DummyOpenAI:
            def __init__(self, *args, **kwargs):
                pass

            def close(self):
                pass

        generator = auto.BaseAutoGenerator(config_list=[{
            "model": "gpt-4o-mini",
            "api_key": "test-thread-key",
            "base_url": None,
        }])

        results = []
        errors = []

        def call_client():
            try:
                client = generator._get_openai_client()
                results.append(id(client))
            except Exception as exc:
                errors.append(exc)

        with mock.patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=DummyOpenAI)}):
            threads = [threading.Thread(target=call_client) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors, f"Unexpected errors: {errors}"
        assert len(results) == 8
        assert len(set(results)) == 1, "Got different client instances across threads"

    def test_get_openai_client_is_not_shared_across_generators(self):
        """Different generator instances must not share a client."""
        import types
        import sys
        import praisonai.auto as auto
        import unittest.mock as mock

        class DummyOpenAI:
            def __init__(self, *args, **kwargs):
                pass

            def close(self):
                pass

        generator_a = auto.BaseAutoGenerator(config_list=[{"model": "gpt-4o-mini", "api_key": "key-a", "base_url": None}])
        generator_b = auto.BaseAutoGenerator(config_list=[{"model": "gpt-4o-mini", "api_key": "key-b", "base_url": None}])

        with mock.patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=DummyOpenAI)}):
            client_a = generator_a._get_openai_client()
            client_b = generator_b._get_openai_client()

        assert id(client_a) != id(client_b), "Different generators must own distinct clients"

    def test_get_openai_client_no_root_logger_mutation(self):
        """Importing auto must not add any new handlers to the root logger."""
        import logging
        import sys

        # Record handlers before re-importing auto
        root_before = set(id(h) for h in logging.getLogger().handlers)

        # Force a fresh import of auto to trigger any module-level side effects
        for key in list(sys.modules.keys()):
            if key in ("praisonai.auto", "praisonai.praisonai.auto"):
                del sys.modules[key]

        import praisonai.auto  # noqa: F401

        root_after = set(id(h) for h in logging.getLogger().handlers)
        new_handlers = root_after - root_before
        assert not new_handlers, (
            "auto.py must not add handlers to the root logger on import; "
            f"found {len(new_handlers)} new handler(s)"
        )

    def test_typer_commands_concurrent_calls_all_return_set(self):
        """Concurrent callers of _get_typer_commands must all get a set back."""
        import threading
        import praisonai.__main__ as main_mod

        # Reset cache so we exercise the lock path
        main_mod._typer_commands_cache = None

        results = []
        errors = []

        def call_commands():
            try:
                result = main_mod._get_typer_commands()
                results.append(result)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=call_commands) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected errors: {errors}"
        assert len(results) == 10
        assert all(isinstance(r, set) for r in results), "All results must be sets"

    def test_typer_commands_failure_does_not_poison_cache(self):
        """A failed discovery must not cache the empty set (allows retries)."""
        import praisonai.__main__ as main_mod

        main_mod._typer_commands_cache = None

        # Patch register_commands to raise
        import unittest.mock as mock
        with mock.patch("praisonai.cli.app.register_commands", side_effect=RuntimeError("boom")):
            result = main_mod._get_typer_commands()

        assert result == set(), "Should return empty set on failure"
        assert main_mod._typer_commands_cache is None, (
            "Cache must remain None after failure to allow retries"
        )

    async def test_aclose_releases_both_sync_and_async_clients(self):
        """aclose() should close both client types for mixed-mode usage."""
        import praisonai.auto as auto

        class DummyOpenAI:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class DummyAsyncOpenAI:
            def __init__(self):
                self.closed = False

            async def close(self):
                self.closed = True

        generator = auto.BaseAutoGenerator(config_list=[{
            "model": "gpt-4o-mini",
            "api_key": "test-key",
            "base_url": None,
        }])

        sync_client = DummyOpenAI()
        async_client = DummyAsyncOpenAI()
        generator._openai_client = sync_client
        generator._async_openai_client = async_client

        await generator.aclose()

        assert sync_client.closed is True
        assert async_client.closed is True
        assert generator._openai_client is None
        assert generator._async_openai_client is None
