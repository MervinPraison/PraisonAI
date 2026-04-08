"""
Unit tests for the new protocol-driven architecture components added in issue #1302.

Tests cover:
- AdapterRegistry base class (generic, thread-safe)
- MemoryAdapterRegistry
- KnowledgeAdapterRegistry
- InMemoryAdapter
- LLM provider adapters (DefaultAdapter, OllamaAdapter, AnthropicAdapter, GeminiAdapter)
- get_provider_adapter() dispatch function
"""

import pytest
import threading
from typing import Optional


# ---------------------------------------------------------------------------
# AdapterRegistry
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    """Tests for the generic AdapterRegistry base class."""

    def _make_registry(self):
        from praisonaiagents.utils.adapter_registry import AdapterRegistry
        return AdapterRegistry(adapter_type_name="Test")

    def test_register_and_get_adapter(self):
        reg = self._make_registry()

        class DummyAdapter:
            def __init__(self, **kwargs):
                pass

        reg.register_adapter("dummy", DummyAdapter)
        instance = reg.get_adapter("dummy")
        assert isinstance(instance, DummyAdapter)

    def test_register_and_get_factory(self):
        reg = self._make_registry()

        class FactoryAdapter:
            def __init__(self, x=0):
                self.x = x

        reg.register_factory("factory", lambda **kw: FactoryAdapter(x=kw.get("x", 42)))
        instance = reg.get_adapter("factory", x=99)
        assert instance.x == 99

    def test_factory_takes_priority_over_class(self):
        """Factory should be tried before class when both are registered."""
        reg = self._make_registry()
        results = []

        class ClassAdapter:
            def __init__(self, **kw):
                results.append("class")

        reg.register_adapter("both", ClassAdapter)
        reg.register_factory("both", lambda **kw: results.append("factory") or ClassAdapter())

        reg.get_adapter("both")
        assert results[0] == "factory"

    def test_returns_none_for_unknown_name(self):
        reg = self._make_registry()
        assert reg.get_adapter("nonexistent") is None

    def test_raises_when_factory_fails(self):
        import pytest
        reg = self._make_registry()

        def bad_factory(**kw):
            raise RuntimeError("intentional failure")

        reg.register_factory("bad", bad_factory)
        with pytest.raises(RuntimeError):
            reg.get_adapter("bad")

    def test_raises_when_class_fails(self):
        import pytest
        reg = self._make_registry()

        class BadAdapter:
            def __init__(self, **kw):
                raise ValueError("intentional failure")

        reg.register_adapter("bad", BadAdapter)
        with pytest.raises(RuntimeError):
            reg.get_adapter("bad")

    def test_list_adapters_sorted(self):
        reg = self._make_registry()

        class A:
            pass

        reg.register_adapter("b_adapter", A)
        reg.register_adapter("a_adapter", A)
        reg.register_factory("c_factory", lambda **kw: A())
        names = reg.list_adapters()
        assert names == sorted(names)
        assert set(names) == {"a_adapter", "b_adapter", "c_factory"}

    def test_is_available(self):
        reg = self._make_registry()

        class A:
            pass

        assert not reg.is_available("x")
        reg.register_adapter("x", A)
        assert reg.is_available("x")

    def test_get_first_available_returns_first_match(self):
        reg = self._make_registry()

        class A:
            pass

        class B:
            pass

        reg.register_adapter("b", B)
        result = reg.get_first_available(["a", "b"])
        assert result is not None
        name, instance = result
        assert name == "b"
        assert isinstance(instance, B)

    def test_get_first_available_returns_none_if_all_fail(self):
        reg = self._make_registry()
        assert reg.get_first_available(["x", "y"]) is None

    def test_thread_safety(self):
        """Concurrent registration and reads should not cause data races."""
        from praisonaiagents.utils.adapter_registry import AdapterRegistry

        reg = AdapterRegistry(adapter_type_name="ThreadTest")
        errors = []

        class TAdapter:
            def __init__(self, **kw):
                pass

        def writer():
            try:
                for i in range(50):
                    reg.register_adapter(f"t{i}", TAdapter)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(50):
                    reg.list_adapters()
                    reg.get_adapter("t0")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"


# ---------------------------------------------------------------------------
# MemoryAdapterRegistry
# ---------------------------------------------------------------------------

class TestMemoryAdapterRegistry:
    def test_imports(self):
        from praisonaiagents.memory.adapters.registry import (
            MemoryAdapterRegistry,
            register_memory_adapter,
            get_memory_adapter,
            list_memory_adapters,
            get_first_available_memory_adapter,
        )

    def test_core_adapters_registered(self):
        from praisonaiagents.memory.adapters import list_memory_adapters
        adapters = list_memory_adapters()
        assert "sqlite" in adapters
        assert "in_memory" in adapters

    def test_get_in_memory_adapter(self):
        from praisonaiagents.memory.adapters import get_memory_adapter
        adapter = get_memory_adapter("in_memory")
        assert adapter is not None

    def test_get_first_available_defaults(self):
        from praisonaiagents.memory.adapters import get_first_available_memory_adapter
        result = get_first_available_memory_adapter()
        assert result is not None
        name, instance = result
        assert name in ("sqlite", "in_memory")

    def test_custom_registry_isolation(self):
        """Custom MemoryAdapterRegistry instances are independent."""
        from praisonaiagents.memory.adapters.registry import MemoryAdapterRegistry

        reg = MemoryAdapterRegistry()

        class MyAdapter:
            def __init__(self, **kw):
                pass

        reg.register_adapter("custom", MyAdapter)
        assert reg.is_available("custom")

        # The global registry should NOT see our custom adapter
        from praisonaiagents.memory.adapters.registry import list_memory_adapters
        assert "custom" not in list_memory_adapters()


# ---------------------------------------------------------------------------
# KnowledgeAdapterRegistry
# ---------------------------------------------------------------------------

class TestKnowledgeAdapterRegistry:
    def test_imports(self):
        from praisonaiagents.knowledge.adapters.registry import (
            KnowledgeAdapterRegistry,
            register_knowledge_adapter,
            get_knowledge_adapter,
            list_knowledge_adapters,
            get_first_available_knowledge_adapter,
        )

    def test_register_and_retrieve(self):
        from praisonaiagents.knowledge.adapters.registry import (
            KnowledgeAdapterRegistry,
        )

        reg = KnowledgeAdapterRegistry()

        class FakeStore:
            def __init__(self, **kw):
                pass

        reg.register_adapter("fake", FakeStore)
        instance = reg.get_adapter("fake")
        assert isinstance(instance, FakeStore)


# ---------------------------------------------------------------------------
# InMemoryAdapter
# ---------------------------------------------------------------------------

class TestInMemoryAdapter:
    def _adapter(self):
        from praisonaiagents.memory.adapters.in_memory_adapter import InMemoryAdapter
        return InMemoryAdapter()

    def test_store_and_search_short_term(self):
        a = self._adapter()
        a.store_short_term("hello world", {"tag": "test"})
        results = a.search_short_term("hello")
        assert len(results) == 1
        assert results[0]["text"] == "hello world"

    def test_store_and_search_long_term(self):
        a = self._adapter()
        a.store_long_term("important fact", {"tag": "lm"})
        results = a.search_long_term("important")
        assert len(results) == 1
        assert results[0]["type"] == "long"

    def test_search_respects_limit(self):
        a = self._adapter()
        for i in range(10):
            a.store_short_term(f"item {i}")
        results = a.search_short_term("item", limit=3)
        assert len(results) == 3

    def test_short_term_not_in_long_term_search(self):
        a = self._adapter()
        a.store_short_term("cross contamination")
        results = a.search_long_term("cross")
        assert len(results) == 0

    def test_get_all_memories(self):
        a = self._adapter()
        a.store_short_term("s1")
        a.store_long_term("l1")
        all_mem = a.get_all_memories()
        assert len(all_mem) == 2

    def test_case_insensitive_search(self):
        a = self._adapter()
        a.store_short_term("Hello World")
        results = a.search_short_term("hello")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# LLM Provider Adapters
# ---------------------------------------------------------------------------

class TestLLMProviderAdapters:
    def test_imports(self):
        from praisonaiagents.llm.adapters import (
            DefaultAdapter,
            OllamaAdapter,
            AnthropicAdapter,
            GeminiAdapter,
            get_provider_adapter,
        )

    def test_default_adapter_implements_protocol(self):
        from praisonaiagents.llm.adapters import DefaultAdapter
        from praisonaiagents.llm.protocols import LLMProviderAdapterProtocol
        adapter = DefaultAdapter()
        assert isinstance(adapter, LLMProviderAdapterProtocol)

    def test_ollama_adapter_implements_protocol(self):
        from praisonaiagents.llm.adapters import OllamaAdapter
        from praisonaiagents.llm.protocols import LLMProviderAdapterProtocol
        adapter = OllamaAdapter()
        assert isinstance(adapter, LLMProviderAdapterProtocol)

    def test_anthropic_adapter_prompt_caching(self):
        from praisonaiagents.llm.adapters import AnthropicAdapter
        adapter = AnthropicAdapter()
        assert adapter.supports_prompt_caching() is True

    def test_default_adapter_no_prompt_caching(self):
        from praisonaiagents.llm.adapters import DefaultAdapter
        adapter = DefaultAdapter()
        assert adapter.supports_prompt_caching() is False

    def test_ollama_threshold_matches_production(self):
        """OllamaAdapter.should_summarize_tools threshold must match LLM.OLLAMA_SUMMARY_ITERATION_THRESHOLD."""
        from praisonaiagents.llm.adapters import OllamaAdapter
        from praisonaiagents.llm.llm import LLM
        adapter = OllamaAdapter()
        threshold = LLM.OLLAMA_SUMMARY_ITERATION_THRESHOLD
        # At threshold the adapter must return True
        assert adapter.should_summarize_tools(threshold) is True
        # Before threshold it must return False
        if threshold > 0:
            assert adapter.should_summarize_tools(threshold - 1) is False

    def test_gemini_adapter_formats_internal_tools(self):
        """GeminiAdapter must recognise the actual Gemini internal tool names."""
        from praisonaiagents.llm.adapters import GeminiAdapter
        from praisonaiagents.llm.model_capabilities import GEMINI_INTERNAL_TOOLS

        adapter = GeminiAdapter()
        tools = [{"name": name} for name in GEMINI_INTERNAL_TOOLS]
        tools.append({"name": "regular_tool"})

        formatted = adapter.format_tools(tools)
        internal = [t for t in formatted if "function" in t]
        regular = [t for t in formatted if "function" not in t]

        assert len(internal) == len(GEMINI_INTERNAL_TOOLS)
        assert len(regular) == 1
        assert regular[0]["name"] == "regular_tool"


class TestGetProviderAdapter:
    def test_claude_model_returns_anthropic_adapter(self):
        from praisonaiagents.llm.adapters import get_provider_adapter, AnthropicAdapter
        assert isinstance(get_provider_adapter("claude-3.5-sonnet"), AnthropicAdapter)

    def test_anthropic_in_name_returns_anthropic_adapter(self):
        from praisonaiagents.llm.adapters import get_provider_adapter, AnthropicAdapter
        assert isinstance(get_provider_adapter("anthropic/claude-instant"), AnthropicAdapter)

    def test_ollama_prefix_returns_ollama_adapter(self):
        from praisonaiagents.llm.adapters import get_provider_adapter, OllamaAdapter
        assert isinstance(get_provider_adapter("ollama/llama3"), OllamaAdapter)

    def test_ollama_in_name_returns_ollama_adapter(self):
        from praisonaiagents.llm.adapters import get_provider_adapter, OllamaAdapter
        assert isinstance(get_provider_adapter("my-ollama-model"), OllamaAdapter)

    def test_gemini_prefix_returns_gemini_adapter(self):
        from praisonaiagents.llm.adapters import get_provider_adapter, GeminiAdapter
        assert isinstance(get_provider_adapter("gemini-pro"), GeminiAdapter)

    def test_gemini_slash_prefix_returns_gemini_adapter(self):
        from praisonaiagents.llm.adapters import get_provider_adapter, GeminiAdapter
        assert isinstance(get_provider_adapter("gemini/gemini-2.0-flash"), GeminiAdapter)

    def test_unknown_model_returns_default_adapter(self):
        from praisonaiagents.llm.adapters import get_provider_adapter, DefaultAdapter
        assert isinstance(get_provider_adapter("gpt-4o"), DefaultAdapter)
