"""
Tests for Memory and Knowledge trace event emission.

TDD tests to verify that memory and knowledge events are properly emitted
when tracing is enabled.
"""

"""Unit tests for memory and knowledge trace events."""


class TestMemoryKnowledgeEventTypes:
    """Tests for memory and knowledge event types in ContextEventType."""
    
    def test_memory_event_types_exist(self):
        """Test that MEMORY_STORE and MEMORY_SEARCH event types exist."""
        from praisonaiagents.trace.context_events import ContextEventType
        
        assert hasattr(ContextEventType, 'MEMORY_STORE')
        assert hasattr(ContextEventType, 'MEMORY_SEARCH')
        assert ContextEventType.MEMORY_STORE.value == "memory_store"
        assert ContextEventType.MEMORY_SEARCH.value == "memory_search"
    
    def test_knowledge_event_types_exist(self):
        """Test that KNOWLEDGE_SEARCH and KNOWLEDGE_ADD event types exist."""
        from praisonaiagents.trace.context_events import ContextEventType
        
        assert hasattr(ContextEventType, 'KNOWLEDGE_SEARCH')
        assert hasattr(ContextEventType, 'KNOWLEDGE_ADD')
        assert ContextEventType.KNOWLEDGE_SEARCH.value == "knowledge_search"
        assert ContextEventType.KNOWLEDGE_ADD.value == "knowledge_add"


class TestEmitterMemoryMethods:
    """Tests for ContextTraceEmitter memory event methods."""
    
    def test_emitter_has_memory_store_method(self):
        """Test that ContextTraceEmitter has memory_store method."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        assert hasattr(emitter, 'memory_store')
        assert callable(emitter.memory_store)
    
    def test_emitter_has_memory_search_method(self):
        """Test that ContextTraceEmitter has memory_search method."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        assert hasattr(emitter, 'memory_search')
        assert callable(emitter.memory_search)
    
    def test_memory_store_emits_event(self):
        """Test that memory_store method emits MEMORY_STORE event."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        emitter.memory_store(
            agent_name="test_agent",
            memory_type="short_term",
            content_length=100,
            metadata={"key": "value"}
        )
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == ContextEventType.MEMORY_STORE
        assert events[0].agent_name == "test_agent"
        assert events[0].data["memory_type"] == "short_term"
        assert events[0].data["content_length"] == 100
    
    def test_memory_search_emits_event(self):
        """Test that memory_search method emits MEMORY_SEARCH event."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        emitter.memory_search(
            agent_name="test_agent",
            query="test query",
            result_count=5,
            memory_type="long_term",
            top_score=0.95
        )
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == ContextEventType.MEMORY_SEARCH
        assert events[0].agent_name == "test_agent"
        assert events[0].data["query"] == "test query"
        assert events[0].data["result_count"] == 5
        assert events[0].data["memory_type"] == "long_term"
        assert events[0].data["top_score"] == 0.95


class TestEmitterKnowledgeMethods:
    """Tests for ContextTraceEmitter knowledge event methods."""
    
    def test_emitter_has_knowledge_search_method(self):
        """Test that ContextTraceEmitter has knowledge_search method."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        assert hasattr(emitter, 'knowledge_search')
        assert callable(emitter.knowledge_search)
    
    def test_emitter_has_knowledge_add_method(self):
        """Test that ContextTraceEmitter has knowledge_add method."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        assert hasattr(emitter, 'knowledge_add')
        assert callable(emitter.knowledge_add)
    
    def test_knowledge_search_emits_event(self):
        """Test that knowledge_search method emits KNOWLEDGE_SEARCH event."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        emitter.knowledge_search(
            agent_name="test_agent",
            query="test query",
            result_count=3,
            sources=["doc1.pdf", "doc2.txt"],
            top_score=0.88
        )
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == ContextEventType.KNOWLEDGE_SEARCH
        assert events[0].agent_name == "test_agent"
        assert events[0].data["query"] == "test query"
        assert events[0].data["result_count"] == 3
        assert events[0].data["sources"] == ["doc1.pdf", "doc2.txt"]
        assert events[0].data["top_score"] == 0.88
    
    def test_knowledge_add_emits_event(self):
        """Test that knowledge_add method emits KNOWLEDGE_ADD event."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink, ContextEventType
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        emitter.knowledge_add(
            agent_name="test_agent",
            source="docs/manual.pdf",
            chunk_count=15,
            metadata={"type": "pdf"}
        )
        
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].event_type == ContextEventType.KNOWLEDGE_ADD
        assert events[0].agent_name == "test_agent"
        assert events[0].data["source"] == "docs/manual.pdf"
        assert events[0].data["chunk_count"] == 15


class TestEmitterDisabledBehavior:
    """Tests for emitter behavior when disabled."""
    
    def test_memory_store_no_event_when_disabled(self):
        """Test that memory_store doesn't emit when emitter is disabled."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=False)
        
        emitter.memory_store(
            agent_name="test_agent",
            memory_type="short_term",
            content_length=100
        )
        
        events = sink.get_events()
        assert len(events) == 0
    
    def test_knowledge_search_no_event_when_disabled(self):
        """Test that knowledge_search doesn't emit when emitter is disabled."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=False)
        
        emitter.knowledge_search(
            agent_name="test_agent",
            query="test",
            result_count=0,
            sources=[]
        )
        
        events = sink.get_events()
        assert len(events) == 0


class TestQueryTruncation:
    """Tests for query truncation in events."""
    
    def test_memory_search_truncates_long_query(self):
        """Test that memory_search truncates queries longer than 500 chars."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        long_query = "x" * 1000
        emitter.memory_search(
            agent_name="test_agent",
            query=long_query,
            result_count=0,
            memory_type="short_term"
        )
        
        events = sink.get_events()
        assert len(events[0].data["query"]) == 500
    
    def test_knowledge_search_truncates_long_query(self):
        """Test that knowledge_search truncates queries longer than 500 chars."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, ContextListSink
        )
        
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test", enabled=True)
        
        long_query = "y" * 1000
        emitter.knowledge_search(
            agent_name="test_agent",
            query=long_query,
            result_count=0
        )
        
        events = sink.get_events()
        assert len(events[0].data["query"]) == 500
