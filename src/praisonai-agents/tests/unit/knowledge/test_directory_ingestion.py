"""
Tests for directory ingestion fix - ensures directories are processed correctly
and file contents (not paths) are stored.
"""
import os
import tempfile
import shutil
import importlib.util
import pytest

# Check if knowledge dependencies are installed
_KNOWLEDGE_DEPS_INSTALLED = importlib.util.find_spec("chromadb") is not None
requires_knowledge = pytest.mark.skipif(
    not _KNOWLEDGE_DEPS_INSTALLED,
    reason="Knowledge dependencies not installed. Install with: pip install praisonaiagents[knowledge]"
)


@requires_knowledge
class TestDirectoryIngestion:
    """Test that directories are properly processed and file contents stored."""
    
    @pytest.fixture
    def temp_knowledge_dir(self):
        """Create a temporary directory with test files."""
        temp_dir = tempfile.mkdtemp(prefix='praison_test_')
        
        # Create test file with unique content
        policy_file = os.path.join(temp_dir, 'policy.txt')
        with open(policy_file, 'w') as f:
            f.write('Remote work policy: Manager approval code is ZEBRA-71.')
        
        # Create another test file
        guide_file = os.path.join(temp_dir, 'guide.txt')
        with open(guide_file, 'w') as f:
            f.write('Employee handbook: Vacation requests require code TIGER-42.')
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_directory_ingestion_stores_text_not_path(self, temp_knowledge_dir):
        """Test that ingesting a directory stores file contents, not the directory path."""
        from praisonaiagents import Knowledge
        
        knowledge = Knowledge()
        result = knowledge.add(temp_knowledge_dir, user_id='test_user')
        
        # Should have results from files
        assert 'results' in result
        assert len(result['results']) > 0
        
        # Search for unique content
        search_result = knowledge.search('ZEBRA-71', user_id='test_user')
        
        assert isinstance(search_result, dict)
        assert 'results' in search_result
        assert len(search_result['results']) > 0
        
        # The memory field should contain actual text, NOT the directory path
        memory = search_result['results'][0].get('memory', '')
        assert 'zebra-71' in memory.lower(), f"Expected 'zebra-71' in memory, got: {memory}"
        assert temp_knowledge_dir not in memory, f"Directory path should not be in memory: {memory}"
    
    def test_directory_ingestion_processes_multiple_files(self, temp_knowledge_dir):
        """Test that all files in a directory are processed."""
        from praisonaiagents import Knowledge
        
        knowledge = Knowledge()
        result = knowledge.add(temp_knowledge_dir, user_id='test_user')
        
        # Search for content from both files
        search1 = knowledge.search('ZEBRA-71', user_id='test_user')
        search2 = knowledge.search('TIGER-42', user_id='test_user')
        
        # Both should find results
        assert len(search1.get('results', [])) > 0, "Should find ZEBRA-71"
        assert len(search2.get('results', [])) > 0, "Should find TIGER-42"
    
    def test_directory_ingestion_sets_metadata(self, temp_knowledge_dir):
        """Test that file metadata is properly set."""
        from praisonaiagents import Knowledge
        
        knowledge = Knowledge()
        knowledge.add(temp_knowledge_dir, user_id='test_user')
        
        search_result = knowledge.search('ZEBRA-71', user_id='test_user')
        
        if search_result.get('results'):
            metadata = search_result['results'][0].get('metadata') or {}
            # Should have filename in metadata
            assert 'filename' in metadata, f"Expected 'filename' in metadata: {metadata}"
            assert metadata['filename'] == 'policy.txt'


@requires_knowledge
class TestContextBuilderUsesText:
    """Test that context builder injects text, not paths."""
    
    @pytest.fixture
    def temp_knowledge_dir(self):
        """Create a temporary directory with test files."""
        temp_dir = tempfile.mkdtemp(prefix='praison_ctx_')
        
        policy_file = os.path.join(temp_dir, 'secret.txt')
        with open(policy_file, 'w') as f:
            f.write('The secret password is WRENCH-992. Do not share.')
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_agent_context_contains_text_not_path(self, temp_knowledge_dir):
        """Test that Agent._get_knowledge_context returns text, not path."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name='TestAgent',
            instructions='Answer based on knowledge.',
            knowledge=[temp_knowledge_dir],
            user_id='test_user',
            verbose=False,
        )
        
        # Ensure knowledge is processed
        agent._ensure_knowledge_processed()
        
        # Get context
        context, _ = agent._get_knowledge_context('What is the password?', use_rag=True)
        
        # Context should contain the secret, not the path
        assert 'wrench-992' in context.lower(), f"Expected 'wrench-992' in context, got: {context[:200]}"
        assert temp_knowledge_dir not in context, f"Path should not be in context: {context[:200]}"
