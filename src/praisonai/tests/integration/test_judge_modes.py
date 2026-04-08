"""
Integration tests for LLM Judge memory and knowledge modes.

Tests the full flow:
1. Generate trace events (memory/knowledge)
2. Save trace to file
3. Run judge with appropriate mode
4. Verify judge output
"""
import tempfile
from pathlib import Path


class TestJudgeMemoryMode:
    """Test judge with memory mode."""
    
    def test_judge_extracts_memory_events(self):
        """Test that judge correctly extracts memory events from trace."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, 
            ContextListSink,
            ContextEventType,
        )
        
        # Create trace with memory events
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-memory", enabled=True)
        
        # Emit session start
        emitter.session_start({"test": True})
        
        # Emit agent events
        emitter.agent_start("MemoryAgent", {"role": "Memory Specialist", "goal": "Use memory effectively"})
        
        # Emit memory events
        emitter.memory_store("MemoryAgent", "short_term", 100, {"key": "value"})
        emitter.memory_store("MemoryAgent", "long_term", 200, {"important": True})
        emitter.memory_search("MemoryAgent", "find user preferences", 3, "short_term", 0.85)
        emitter.memory_search("MemoryAgent", "recall important facts", 5, "long_term", 0.92)
        
        # Emit LLM events
        emitter.llm_request("MemoryAgent", "gpt-4o-mini", [{"role": "user", "content": "test"}])
        emitter.llm_response("MemoryAgent", 100, 500, "stop", "Test response")
        
        emitter.agent_end("MemoryAgent")
        emitter.session_end()
        
        events = sink.get_events()
        
        # Verify memory events exist
        memory_events = [e for e in events if e.event_type in [
            ContextEventType.MEMORY_STORE, 
            ContextEventType.MEMORY_SEARCH
        ]]
        assert len(memory_events) == 4, f"Expected 4 memory events, got {len(memory_events)}"
        
        # Verify event data
        store_events = [e for e in memory_events if e.event_type == ContextEventType.MEMORY_STORE]
        search_events = [e for e in memory_events if e.event_type == ContextEventType.MEMORY_SEARCH]
        
        assert len(store_events) == 2
        assert len(search_events) == 2
        assert store_events[0].data["memory_type"] == "short_term"
        assert store_events[1].data["memory_type"] == "long_term"
        assert search_events[0].data["query"] == "find user preferences"
        assert search_events[1].data["top_score"] == 0.92


class TestJudgeKnowledgeMode:
    """Test judge with knowledge mode."""
    
    def test_judge_extracts_knowledge_events(self):
        """Test that judge correctly extracts knowledge events from trace."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, 
            ContextListSink,
            ContextEventType,
        )
        
        # Create trace with knowledge events
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-knowledge", enabled=True)
        
        # Emit session start
        emitter.session_start({"test": True})
        
        # Emit agent events
        emitter.agent_start("KnowledgeAgent", {"role": "Knowledge Specialist", "goal": "Use knowledge effectively"})
        
        # Emit knowledge events
        emitter.knowledge_add("KnowledgeAgent", "docs/manual.pdf", 50, {"type": "pdf"})
        emitter.knowledge_add("KnowledgeAgent", "data/faq.md", 20, {"type": "markdown"})
        emitter.knowledge_search("KnowledgeAgent", "how to configure settings", 5, ["manual.pdf", "faq.md"], 0.88)
        emitter.knowledge_search("KnowledgeAgent", "troubleshooting steps", 3, ["manual.pdf"], 0.75)
        
        # Emit LLM events
        emitter.llm_request("KnowledgeAgent", "gpt-4o-mini", [{"role": "user", "content": "test"}])
        emitter.llm_response("KnowledgeAgent", 100, 500, "stop", "Test response")
        
        emitter.agent_end("KnowledgeAgent")
        emitter.session_end()
        
        events = sink.get_events()
        
        # Verify knowledge events exist
        knowledge_events = [e for e in events if e.event_type in [
            ContextEventType.KNOWLEDGE_SEARCH, 
            ContextEventType.KNOWLEDGE_ADD
        ]]
        assert len(knowledge_events) == 4, f"Expected 4 knowledge events, got {len(knowledge_events)}"
        
        # Verify event data
        add_events = [e for e in knowledge_events if e.event_type == ContextEventType.KNOWLEDGE_ADD]
        search_events = [e for e in knowledge_events if e.event_type == ContextEventType.KNOWLEDGE_SEARCH]
        
        assert len(add_events) == 2
        assert len(search_events) == 2
        assert add_events[0].data["source"] == "docs/manual.pdf"
        assert add_events[0].data["chunk_count"] == 50
        assert search_events[0].data["sources"] == ["manual.pdf", "faq.md"]


class TestJudgePromptTemplates:
    """Test that judge uses correct prompt templates for each mode."""
    
    def test_context_mode_uses_context_template(self):
        """Test context mode uses context-focused template."""
        import sys
        sys.path.insert(0, '/Users/praison/praisonai-package/src/praisonai')
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge(mode="context")
        assert "CONTEXT UTILIZATION" in judge.prompt_template
        assert "TASK ACHIEVEMENT" in judge.prompt_template
    
    def test_memory_mode_uses_memory_template(self):
        """Test memory mode uses memory-focused template."""
        import sys
        sys.path.insert(0, '/Users/praison/praisonai-package/src/praisonai')
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge(mode="memory")
        assert "RETRIEVAL_RELEVANCE" in judge.prompt_template
        assert "STORAGE_QUALITY" in judge.prompt_template
        assert "RECALL_EFFECTIVENESS" in judge.prompt_template
        assert "MEMORY_EFFICIENCY" in judge.prompt_template
    
    def test_knowledge_mode_uses_knowledge_template(self):
        """Test knowledge mode uses knowledge-focused template."""
        import sys
        sys.path.insert(0, '/Users/praison/praisonai-package/src/praisonai')
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge(mode="knowledge")
        assert "RETRIEVAL_ACCURACY" in judge.prompt_template
        assert "SOURCE_COVERAGE" in judge.prompt_template
        assert "CITATION_QUALITY" in judge.prompt_template
        assert "KNOWLEDGE_INTEGRATION" in judge.prompt_template


class TestTraceFileSaveAndLoad:
    """Test saving and loading trace files with memory/knowledge events."""
    
    def test_save_and_load_memory_trace(self):
        """Test that memory events are correctly saved and loaded from trace file."""
        from praisonaiagents.trace.context_events import (
            ContextTraceEmitter, 
            ContextListSink,
        )
        
        # Create trace with memory events in list sink
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="test-memory", enabled=True)
        
        emitter.session_start({"test": True})
        emitter.agent_start("MemoryAgent", {"role": "Memory Specialist"})
        emitter.memory_store("MemoryAgent", "short_term", 100, {})
        emitter.memory_search("MemoryAgent", "test query", 3, "short_term", 0.9)
        emitter.agent_end("MemoryAgent")
        emitter.session_end()
        
        events = sink.get_events()
        
        # Verify memory events exist
        from praisonaiagents.trace.context_events import ContextEventType
        memory_events = [e for e in events if e.event_type in [
            ContextEventType.MEMORY_STORE, ContextEventType.MEMORY_SEARCH
        ]]
        assert len(memory_events) == 2, f"Expected 2 memory events, got {len(memory_events)}"
