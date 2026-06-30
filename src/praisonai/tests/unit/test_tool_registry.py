"""Unit tests for ToolRegistry, focusing on thread-safety."""

import threading
import pytest
from praisonai.tool_registry import ToolRegistry


class TestToolRegistryBasic:
    """Basic functionality tests for ToolRegistry."""

    def test_register_and_get_function(self):
        registry = ToolRegistry()
        func = lambda x: x
        registry.register_function("my_func", func)
        assert registry.get_function("my_func") is func

    def test_register_non_callable_raises(self):
        registry = ToolRegistry()
        with pytest.raises(ValueError):
            registry.register_function("bad", "not_callable")

    def test_get_missing_function_returns_none(self):
        registry = ToolRegistry()
        assert registry.get_function("missing") is None

    def test_list_functions(self):
        registry = ToolRegistry()
        registry.register_function("a", lambda: None)
        registry.register_function("b", lambda: None)
        names = registry.list_functions()
        assert sorted(names) == ["a", "b"]

    def test_get_functions_dict_returns_copy(self):
        registry = ToolRegistry()
        f = lambda: None
        registry.register_function("f", f)
        d = registry.get_functions_dict()
        assert d == {"f": f}
        # Mutating the returned dict does not affect the registry
        d["extra"] = lambda: None
        assert "extra" not in registry.get_functions_dict()

    def test_clear(self):
        registry = ToolRegistry()
        registry.register_function("f", lambda: None)
        registry.register_function("g", lambda: None)
        registry.clear()
        assert len(registry) == 0

    def test_len(self):
        registry = ToolRegistry()
        assert len(registry) == 0
        registry.register_function("f", lambda: None)
        assert len(registry) == 1
        registry.register_function("g", lambda: None)
        assert len(registry) == 2

    def test_contains(self):
        registry = ToolRegistry()
        registry.register_function("f", lambda: None)
        assert "f" in registry
        assert "missing" not in registry


class TestToolRegistryThreadSafety:
    """Thread-safety tests for ToolRegistry."""

    def test_concurrent_writes_no_error(self):
        """Concurrent register_function calls must not raise."""
        registry = ToolRegistry()
        errors = []

        def writer(n):
            try:
                for i in range(50):
                    registry.register_function(f"func_{n}_{i}", lambda: None)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent writes raised: {errors}"
        assert len(registry) == 250  # 5 threads * 50 registrations

    def test_concurrent_reads_writes_no_error(self):
        """Concurrent reads and writes must not raise RuntimeError."""
        registry = ToolRegistry()
        # Pre-populate
        for i in range(20):
            registry.register_function(f"pre_{i}", lambda: None)

        errors = []

        def writer():
            try:
                for i in range(30):
                    registry.register_function(f"w_{i}", lambda: None)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    registry.list_functions()
                    registry.get_functions_dict()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent read/write raised: {errors}"

    def test_concurrent_clear_and_register(self):
        """clear() racing with register_function() must not corrupt state."""
        registry = ToolRegistry()
        errors = []

        def writer():
            try:
                for i in range(50):
                    registry.register_function(f"w_{i}", lambda: None)
            except Exception as e:
                errors.append(e)

        def clearer():
            try:
                for _ in range(20):
                    registry.clear()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=clearer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent clear/register raised: {errors}"


class TestListAvailableSurfacesRegistry:
    """Discovery (list_available) must match resolution for registry tools.

    Regression for issue #2474: entry-point-discovered and registry-registered
    tools resolve at run time but were invisible to ``tools list``.
    """

    def test_wrapper_registry_tool_listed(self):
        """A tool registered in the wrapper ToolRegistry appears in list_available()."""
        from praisonai.tool_resolver import ToolResolver

        registry = ToolRegistry()
        registry.register_function("my_wrapper_tool", lambda x: x)
        resolver = ToolResolver(registry=registry)

        available = resolver.list_available()
        assert "my_wrapper_tool" in available
        # And it resolves at run time too (discovery matches resolution).
        assert resolver.resolve("my_wrapper_tool") is not None

    def test_core_registry_tool_listed(self):
        """A tool registered in the core SDK registry appears in list_available()."""
        pytest.importorskip("praisonaiagents")
        from praisonaiagents.tools.registry import get_registry
        from praisonai.tool_resolver import ToolResolver

        core_reg = get_registry()
        tool_name = "issue2474_core_registry_tool"

        def _sample_tool(x):
            """Sample registry tool for discovery test."""
            return x

        core_reg.register(_sample_tool, name=tool_name)
        try:
            resolver = ToolResolver()
            available = resolver.list_available()
            assert tool_name in available
            assert resolver.resolve(tool_name) is not None
        finally:
            # Avoid leaking the test tool into the process-wide singleton.
            core_reg.unregister(tool_name)


class TestListAvailableSourceAttribution:
    """Source attribution must match the resolution precedence chain.

    Regression for the discovery-ordering and docstring-as-source-tag issues
    raised in review of #2474: the reported source must reflect the callable
    that ``resolve()`` would actually return, independent of descriptions.
    """

    def test_source_matches_resolution_precedence(self):
        """A name in both wrapper registry and a higher-precedence-listed source
        is attributed to the source resolve() actually returns."""
        from praisonai.tool_resolver import ToolResolver

        registry = ToolRegistry()

        sentinel = lambda x: x
        registry.register_function("issue2474_precedence_tool", sentinel)
        resolver = ToolResolver(registry=registry)

        sources = resolver.list_available_sources()
        # Wrapper-registry tool surfaces and is attributed to the registry.
        assert sources.get("issue2474_precedence_tool") == "registered"
        # And resolution returns the wrapper-registry callable (precedence holds).
        assert resolver.resolve("issue2474_precedence_tool") is sentinel

    def test_local_docstring_does_not_change_source(self):
        """A local tool whose docstring mentions 'Registered' stays 'local'."""
        from praisonai.tool_resolver import ToolResolver

        def _ResolveResult(x):
            """Registered user handler that looks like a registry tool."""
            return x

        resolver = ToolResolver()
        # Inject a local tool directly into the (immutable) cache to avoid
        # touching the filesystem / PRAISONAI_ALLOW_LOCAL_TOOLS gate.
        from types import MappingProxyType
        resolver._local_tools_cache = MappingProxyType(
            {"registered_looking_local": _ResolveResult}
        )
        resolver._local_tools_loaded = True

        sources = resolver.list_available_sources()
        assert sources["registered_looking_local"] == "local"

    def test_custom_sources_do_not_advertise_default_registry(self):
        """A resolver with a custom source chain must not list default-chain
        tools it cannot resolve (built-in / external / core registry)."""
        from praisonai.tool_resolver import ToolResolver

        # Empty custom chain: resolves nothing, so discovery must be empty too.
        resolver = ToolResolver(sources=[])
        available = resolver.list_available()
        assert available == {}
