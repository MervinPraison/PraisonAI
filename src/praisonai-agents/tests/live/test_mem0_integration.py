"""
Live integration tests for mem0 backend.

These tests require:
- OPENAI_API_KEY environment variable
- RUN_LIVE_TESTS=1 environment variable

Run with: RUN_LIVE_TESTS=1 python -m pytest tests/live/test_mem0_integration.py -v
"""

import os
import sys
import tempfile
import shutil

# Skip all tests if RUN_LIVE_TESTS is not set
import pytest
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="Live tests disabled. Set RUN_LIVE_TESTS=1 to run."
)


class TestMem0IntegrationLive:
    """Live tests for mem0 integration."""
    
    def test_knowledge_search_with_mem0_metadata_none(self):
        """Test that Knowledge.search handles mem0 metadata=None correctly."""
        from praisonaiagents.knowledge import Knowledge
        
        # Create temp directory with test file
        temp_dir = tempfile.mkdtemp(prefix='praison_mem0_test_')
        try:
            test_file = os.path.join(temp_dir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('The capital of France is Paris. This is a test document.')
            
            # Initialize Knowledge and add content
            knowledge = Knowledge()
            knowledge.add(temp_dir, user_id='test_user_live')
            
            # Search - this should NOT raise AttributeError
            results = knowledge.search('capital', user_id='test_user_live')
            
            # Verify results structure
            assert isinstance(results, dict)
            assert 'results' in results
            
            # Verify metadata handling
            for result in results.get('results', []):
                if result is not None:
                    # metadata should be accessible without error
                    metadata = result.get('metadata')
                    # Even if None, accessing it shouldn't crash
                    if metadata is not None:
                        assert isinstance(metadata, dict)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_agent_chat_with_knowledge_no_crash(self):
        """Test that Agent.chat with knowledge doesn't crash on metadata=None."""
        from praisonaiagents import Agent
        
        temp_dir = tempfile.mkdtemp(prefix='praison_agent_test_')
        try:
            test_file = os.path.join(temp_dir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('The capital of France is Paris.')
            
            # Create agent with knowledge
            agent = Agent(
                name="TestAgent",
                instructions="You are a helpful assistant.",
                knowledge=[temp_dir],
                user_id='test_user_agent',
            )
            
            # This should NOT raise "NoneType has no attribute get"
            response = agent.chat("What is the capital of France?")
            
            assert response is not None
            assert isinstance(response, str)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_rag_context_builder_with_mem0_results(self):
        """Test RAG context builder handles mem0 results correctly."""
        from praisonaiagents.rag.context import build_context, deduplicate_chunks
        
        # Simulate mem0 results with metadata=None
        mem0_results = [
            {
                "id": "1",
                "memory": "Paris is the capital of France.",
                "score": 0.95,
                "metadata": None,  # mem0 returns this!
                "user_id": "test",
            },
            {
                "id": "2", 
                "memory": "London is the capital of UK.",
                "score": 0.85,
                "metadata": {"source": "geography.txt"},
            },
        ]
        
        # Should not crash
        deduped = deduplicate_chunks(mem0_results)
        assert len(deduped) == 2
        
        context, used = build_context(mem0_results)
        assert "Paris" in context
        assert "London" in context
        assert len(used) == 2


class TestImportPerformance:
    """Tests for import-time performance."""
    
    def test_core_import_does_not_load_mem0(self):
        """Test that importing praisonaiagents doesn't load mem0."""
        # This test runs even without RUN_LIVE_TESTS
        # Clear any existing mem0 imports
        mem0_modules = [k for k in list(sys.modules.keys()) if k.startswith('mem0')]
        for mod in mem0_modules:
            sys.modules.pop(mod, None)
        
        # Fresh import
        import importlib
        if 'praisonaiagents' in sys.modules:
            importlib.reload(sys.modules['praisonaiagents'])
        else:
            import praisonaiagents
        
        # mem0 should NOT be loaded
        mem0_loaded = any(k.startswith('mem0') for k in sys.modules.keys())
        assert not mem0_loaded, "mem0 should not be imported at package import time"
    
    def test_knowledge_import_does_not_load_mem0(self):
        """Test that importing Knowledge doesn't load mem0."""
        mem0_modules = [k for k in list(sys.modules.keys()) if k.startswith('mem0')]
        for mod in mem0_modules:
            sys.modules.pop(mod, None)
        
        from praisonaiagents import Knowledge  # noqa: F401
        
        mem0_loaded = any(k.startswith('mem0') for k in sys.modules.keys())
        # Note: Knowledge class definition doesn't import mem0
        # mem0 is only imported when Knowledge is instantiated and used
        assert not mem0_loaded, "mem0 should not be imported when importing Knowledge class"
