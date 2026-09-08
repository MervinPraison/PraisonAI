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
# No credential requirement: _offline_embeddings below replaces the embedding
# call, so these run anywhere chromadb is installed. The old guard excluded one
# placeholder by value ("not-needed") while CI exports 'sk-not-a-real-key', so it
# never skipped -- the tests hit the real OpenAI endpoint, got a 401, and failed
# on "assert 0 > 0" because add() swallows the embedding error into its result
# rather than raising. The in-test `except ... pytest.skip("api_key")` guards
# never fired for the same reason: nothing escapes add() to catch.
requires_knowledge = pytest.mark.skipif(
    not _KNOWLEDGE_DEPS_INSTALLED,
    reason="Knowledge dependencies (chromadb) not installed."
)


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch):
    """Deterministic bag-of-words embeddings, so ingestion and search run offline.

    Not a constant vector: these tests assert that a search for ZEBRA-71 returns
    the ZEBRA document FIRST, so the stub has to preserve real ranking. Shared
    tokens raise cosine similarity, which is enough to order two documents whose
    vocabularies barely overlap. crc32 keeps it stable across processes, where
    hash() is randomised per run.
    """
    import re
    from zlib import crc32

    DIM = 256

    def _vector(text):
        vec = [0.0] * DIM
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            vec[crc32(token.encode()) % DIM] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    class _Result:
        def __init__(self, texts):
            self.embeddings = [_vector(t) for t in texts]

    def _fake_embedding(input, **kwargs):
        texts = [input] if isinstance(input, str) else list(input)
        return _Result(texts)

    # importlib, not `import praisonaiagents.embedding as _emb`: the package
    # exposes a lazy proxy under that name which resolves to the FUNCTION, so the
    # plain import yields the proxy and setattr fails with "has no attribute
    # 'embedding'". The module object is what both call sites resolve against.
    import importlib
    _emb = importlib.import_module("praisonaiagents.embedding")
    monkeypatch.setattr(_emb, "embedding", _fake_embedding)


def _make_knowledge_or_skip():
    """Create a Knowledge() instance, skipping if OpenAI API key is unavailable."""
    from praisonaiagents import Knowledge
    try:
        return Knowledge()
    except Exception as e:
        if "api_key" in str(e).lower() or "openai" in str(e).lower():
            pytest.skip(f"Skipping: OpenAI API key required for embeddings: {e}")
        raise


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
        knowledge = _make_knowledge_or_skip()
        
        try:
            result = knowledge.add(temp_knowledge_dir, user_id='test_user')
        except Exception as e:
            if "api_key" in str(e).lower() or "openai" in str(e).lower():
                pytest.skip(f"Skipping: OpenAI API key required: {e}")
            raise
        
        # Should have results from files
        assert 'results' in result
        assert len(result['results']) > 0
        
        # Search for unique content
        search_result = knowledge.search('ZEBRA-71', user_id='test_user')
        
        if isinstance(search_result, dict):
            results = search_result.get('results', [])
        else:
            results = getattr(search_result, 'results', [])

        assert len(results) > 0
        
        # The memory field should contain actual text, NOT the directory path
        if len(results) > 0:
            print(f"DEBUG results[0]: {results[0]}")
            if isinstance(results[0], dict):
                memory = results[0].get('memory', results[0].get('text', '')) or ''
            else:
                # Need to handle mem0 Pydantic objects which might have 'text'=None but store content in metadata
                base_text = getattr(results[0], 'text', None) or getattr(results[0], 'memory', None) or ''
                metadata = getattr(results[0], 'metadata', {})
                if not base_text and isinstance(metadata, dict):
                    base_text = metadata.get('data', '') or metadata.get('text', '') or ''
                memory = base_text
        
            assert 'zebra-71' in memory.lower(), f"Expected 'zebra-71' in memory, got: {memory}"
            assert temp_knowledge_dir not in memory, f"Directory path should not be in memory: {memory}"
    
    def test_directory_ingestion_processes_multiple_files(self, temp_knowledge_dir):
        """Test that all files in a directory are processed."""
        knowledge = _make_knowledge_or_skip()
        
        try:
            knowledge.add(temp_knowledge_dir, user_id='test_user')
        except Exception as e:
            if "api_key" in str(e).lower() or "openai" in str(e).lower():
                pytest.skip(f"Skipping: OpenAI API key required: {e}")
            raise
        
        # Search for content from both files
        search1 = knowledge.search('ZEBRA-71', user_id='test_user')
        search2 = knowledge.search('TIGER-42', user_id='test_user')
        
        # Both should find results
        res1 = search1.get('results', []) if isinstance(search1, dict) else getattr(search1, 'results', [])
        res2 = search2.get('results', []) if isinstance(search2, dict) else getattr(search2, 'results', [])
        assert len(res1) > 0, "Should find ZEBRA-71"
        assert len(res2) > 0, "Should find TIGER-42"
    
    def test_directory_ingestion_sets_metadata(self, temp_knowledge_dir):
        """Test that file metadata is properly set."""
        knowledge = _make_knowledge_or_skip()
        
        try:
            knowledge.add(temp_knowledge_dir, user_id='test_user')
        except Exception as e:
            if "api_key" in str(e).lower() or "openai" in str(e).lower():
                pytest.skip(f"Skipping: OpenAI API key required: {e}")
            raise
        
        search_result = knowledge.search('ZEBRA-71', user_id='test_user')
        
        results = search_result.get('results', []) if isinstance(search_result, dict) else getattr(search_result, 'results', [])
        if results:
            if isinstance(results[0], dict):
                metadata = results[0].get('metadata', {})
            else:
                metadata = getattr(results[0], 'metadata', {})
                
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
        
        try:
            agent = Agent(
                name='TestAgent',
                instructions='Answer based on knowledge.',
                knowledge=[temp_knowledge_dir],
                output='silent',
            )
            
            # Ensure knowledge is processed
            agent._ensure_knowledge_processed()
        except Exception as e:
            if "api_key" in str(e).lower() or "openai" in str(e).lower():
                pytest.skip(f"Skipping: OpenAI API key required: {e}")
            raise
        
        # Mock the self.knowledge.search method
        try:
            from unittest.mock import MagicMock
            if agent.knowledge:
                agent.knowledge.search = MagicMock(return_value=[
                    {"text": "The secret password is WRENCH-992. Do not share.", "metadata": {}}
                ])
        except Exception as e:
            pass
            
        # Get context
        context, _ = agent._get_knowledge_context('What is the password?', use_rag=True)
        
        # Context should contain the secret, not the path
        assert 'wrench-992' in context.lower(), f"Expected 'wrench-992' in context, got: {context[:200]}"
        assert temp_knowledge_dir not in context, f"Path should not be in context: {context[:200]}"
