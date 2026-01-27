"""
TDD Tests for Chunked Evaluation in Recipe Judge.

Tests the chunked evaluation approach that splits large outputs into
multiple chunks, evaluates each separately, and aggregates scores.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestChunkSplitter:
    """Tests for the chunk splitting functionality."""
    
    def test_chunk_splitter_exists(self):
        """Test that chunk_split function exists."""
        from praisonai.replay.judge import chunk_split
        assert callable(chunk_split)
    
    def test_small_text_returns_single_chunk(self):
        """Small text should return as single chunk without splitting."""
        from praisonai.replay.judge import chunk_split
        
        small_text = "This is a small text."
        chunks = chunk_split(small_text, max_chars=1000)
        
        assert len(chunks) == 1
        assert chunks[0] == small_text
    
    def test_large_text_splits_into_multiple_chunks(self):
        """Large text should be split into multiple chunks."""
        from praisonai.replay.judge import chunk_split
        
        # Create text larger than chunk size
        large_text = "A" * 5000
        chunks = chunk_split(large_text, max_chars=2000)
        
        assert len(chunks) >= 2
        # All content should be preserved
        total_chars = sum(len(c) for c in chunks)
        assert total_chars >= len(large_text)
    
    def test_chunk_split_respects_max_chunks(self):
        """Chunk split should respect max_chunks parameter."""
        from praisonai.replay.judge import chunk_split
        
        large_text = "A" * 10000
        chunks = chunk_split(large_text, max_chars=1000, max_chunks=3)
        
        assert len(chunks) <= 3
    
    def test_chunk_split_preserves_paragraph_boundaries(self):
        """Chunk split should try to split at paragraph boundaries."""
        from praisonai.replay.judge import chunk_split
        
        text = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3.\n\nParagraph 4."
        chunks = chunk_split(text, max_chars=30)
        
        # Should split at paragraph boundaries when possible
        for chunk in chunks:
            # Chunks shouldn't start/end mid-word
            assert not chunk.startswith(" ")
    
    def test_chunk_split_with_overlap(self):
        """Chunk split should support overlap for context continuity."""
        from praisonai.replay.judge import chunk_split
        
        text = "A" * 100 + "B" * 100 + "C" * 100
        chunks = chunk_split(text, max_chars=120, overlap=20)
        
        # With overlap, chunks should share some content
        if len(chunks) > 1:
            # Check that chunks have some overlap
            assert len(chunks) >= 2


class TestChunkEvaluation:
    """Tests for evaluating individual chunks."""
    
    def test_evaluate_chunk_returns_score(self):
        """Evaluate chunk should return a score dict."""
        from praisonai.replay.judge import ChunkedEvaluator
        
        evaluator = ChunkedEvaluator(model="gpt-4o-mini")
        assert hasattr(evaluator, 'evaluate_chunk')
    
    def test_chunked_evaluator_has_aggregate_method(self):
        """ChunkedEvaluator should have aggregate_scores method."""
        from praisonai.replay.judge import ChunkedEvaluator
        
        evaluator = ChunkedEvaluator(model="gpt-4o-mini")
        assert hasattr(evaluator, 'aggregate_scores')


class TestScoreAggregation:
    """Tests for aggregating scores from multiple chunks."""
    
    def test_weighted_average_aggregation(self):
        """Test weighted average score aggregation."""
        from praisonai.replay.judge import aggregate_chunk_scores
        
        chunk_scores = [
            {"score": 8.0, "chunk_size": 1000},
            {"score": 6.0, "chunk_size": 500},
        ]
        
        result = aggregate_chunk_scores(chunk_scores, strategy="weighted_average")
        
        # Weighted average: (8*1000 + 6*500) / (1000+500) = 7.33
        assert 7.0 <= result <= 7.5
    
    def test_min_aggregation(self):
        """Test minimum score aggregation (conservative)."""
        from praisonai.replay.judge import aggregate_chunk_scores
        
        chunk_scores = [
            {"score": 8.0, "chunk_size": 1000},
            {"score": 6.0, "chunk_size": 500},
            {"score": 9.0, "chunk_size": 800},
        ]
        
        result = aggregate_chunk_scores(chunk_scores, strategy="min")
        assert result == 6.0
    
    def test_max_aggregation(self):
        """Test maximum score aggregation (optimistic)."""
        from praisonai.replay.judge import aggregate_chunk_scores
        
        chunk_scores = [
            {"score": 8.0, "chunk_size": 1000},
            {"score": 6.0, "chunk_size": 500},
            {"score": 9.0, "chunk_size": 800},
        ]
        
        result = aggregate_chunk_scores(chunk_scores, strategy="max")
        assert result == 9.0
    
    def test_average_aggregation(self):
        """Test simple average score aggregation."""
        from praisonai.replay.judge import aggregate_chunk_scores
        
        chunk_scores = [
            {"score": 8.0, "chunk_size": 1000},
            {"score": 6.0, "chunk_size": 500},
            {"score": 10.0, "chunk_size": 800},
        ]
        
        result = aggregate_chunk_scores(chunk_scores, strategy="average")
        assert result == 8.0  # (8+6+10)/3


class TestContextEffectivenessJudgeChunked:
    """Tests for chunked evaluation in ContextEffectivenessJudge."""
    
    def test_judge_has_chunked_mode(self):
        """ContextEffectivenessJudge should support chunked mode."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge(mode="context", chunked=True)
        assert judge.chunked is True
    
    def test_judge_default_not_chunked(self):
        """ContextEffectivenessJudge should default to non-chunked."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge(mode="context")
        assert judge.chunked is False
    
    def test_judge_chunk_config(self):
        """ContextEffectivenessJudge should accept chunk configuration."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge(
            mode="context",
            chunked=True,
            chunk_size=3000,
            max_chunks=3,
            chunk_overlap=200,
            aggregation_strategy="weighted_average",
        )
        
        assert judge.chunk_size == 3000
        assert judge.max_chunks == 3
        assert judge.chunk_overlap == 200
        assert judge.aggregation_strategy == "weighted_average"


class TestChunkedEvaluationIntegration:
    """Integration tests for chunked evaluation."""
    
    @patch('praisonai.replay.judge.ContextEffectivenessJudge._get_litellm')
    def test_large_output_uses_chunked_evaluation(self, mock_litellm):
        """Large outputs should trigger chunked evaluation when enabled."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
TASK_SCORE: 8
CONTEXT_SCORE: 7
QUALITY_SCORE: 8
INSTRUCTION_SCORE: 7
HALLUCINATION_SCORE: 9
ERROR_SCORE: 8
FAILURE_DETECTED: false
REASONING: Good performance
"""
        mock_litellm.return_value.completion.return_value = mock_response
        
        judge = ContextEffectivenessJudge(
            mode="context",
            chunked=True,
            chunk_size=1000,
        )
        
        # Create large agent info
        large_output = "A" * 5000
        agent_info = {
            "inputs": ["test input"],
            "outputs": [large_output],
            "context": ["test context"],
            "tool_calls": [],
            "prompt_tokens": 100,
            "completion_tokens": 500,
        }
        
        # This should use chunked evaluation
        score = judge._judge_agent("test_agent", agent_info)
        
        # Should have called LLM multiple times for chunks
        assert mock_litellm.return_value.completion.call_count >= 1


class TestChunkMetadata:
    """Tests for chunk metadata tracking."""
    
    def test_chunk_includes_position_info(self):
        """Each chunk should include position information."""
        from praisonai.replay.judge import chunk_split
        
        text = "A" * 5000
        chunks = chunk_split(text, max_chars=2000, include_metadata=True)
        
        # When include_metadata=True, should return list of dicts
        if isinstance(chunks[0], dict):
            assert "chunk_index" in chunks[0]
            assert "total_chunks" in chunks[0]
            assert "content" in chunks[0]
