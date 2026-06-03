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

    def test_register_and_get_autogen_adapter(self):
        registry = ToolRegistry()
        adapter = lambda: None
        registry.register_autogen_adapter("MyTool", adapter)
        assert registry.get_autogen_adapter("MyTool") is adapter

    def test_list_functions(self):
        registry = ToolRegistry()
        registry.register_function("a", lambda: None)
        registry.register_function("b", lambda: None)
        names = registry.list_functions()
        assert sorted(names) == ["a", "b"]

    def test_list_autogen_adapters(self):
        registry = ToolRegistry()
        registry.register_autogen_adapter("T1", lambda: None)
        registry.register_autogen_adapter("T2", lambda: None)
        names = registry.list_autogen_adapters()
        assert sorted(names) == ["T1", "T2"]

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
        registry.register_autogen_adapter("A", lambda: None)
        registry.clear()
        assert len(registry) == 0

    def test_len(self):
        registry = ToolRegistry()
        assert len(registry) == 0
        registry.register_function("f", lambda: None)
        assert len(registry) == 1
        registry.register_autogen_adapter("A", lambda: None)
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
