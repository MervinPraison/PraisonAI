"""
Unit tests for Query Engine Patterns.
"""

from praisonaiagents.knowledge.query_engine import (
    QueryMode,
    QueryResult,
    get_query_engine_registry,
    decompose_question,
    synthesize_answer,
    SimpleQueryEngine,
    SubQuestionEngine,
)


class TestQueryMode:
    """Tests for QueryMode enum."""
    
    def test_query_mode_values(self):
        """Test query mode enum values."""
        assert QueryMode.DEFAULT == "default"
        assert QueryMode.SUB_QUESTION == "sub_question"
        assert QueryMode.SQL == "sql"
        assert QueryMode.ROUTER == "router"
        assert QueryMode.SUMMARIZE == "summarize"
    
    def test_query_mode_from_string(self):
        """Test creating query mode from string."""
        assert QueryMode("default") == QueryMode.DEFAULT
        assert QueryMode("sub_question") == QueryMode.SUB_QUESTION


class TestQueryResult:
    """Tests for QueryResult dataclass."""
    
    def test_result_creation(self):
        """Test basic result creation."""
        result = QueryResult(answer="The answer is 42")
        assert result.answer == "The answer is 42"
        assert result.sources == []
        assert result.sub_questions is None
        assert result.metadata == {}
    
    def test_result_with_sources(self):
        """Test result with sources."""
        result = QueryResult(
            answer="Test answer",
            sources=[
                {"text": "Source 1", "score": 0.9},
                {"text": "Source 2", "score": 0.8}
            ]
        )
        assert len(result.sources) == 2
        assert result.sources[0]["score"] == 0.9
    
    def test_result_with_sub_questions(self):
        """Test result with sub-questions."""
        result = QueryResult(
            answer="Combined answer",
            sub_questions=["What is X?", "What is Y?"]
        )
        assert len(result.sub_questions) == 2
    
    def test_result_to_dict(self):
        """Test result serialization."""
        result = QueryResult(
            answer="Test",
            sources=[{"text": "Source"}],
            metadata={"mode": "default"}
        )
        d = result.to_dict()
        assert d["answer"] == "Test"
        assert len(d["sources"]) == 1
        assert d["metadata"]["mode"] == "default"


class TestDecomposeQuestion:
    """Tests for question decomposition."""
    
    def test_simple_question(self):
        """Test that simple questions are not decomposed."""
        questions = decompose_question("What is Python?")
        assert len(questions) == 1
        assert questions[0] == "What is Python?"
    
    def test_compound_question_and(self):
        """Test decomposing compound question with 'and'."""
        questions = decompose_question("What is Python and what is JavaScript?")
        assert len(questions) >= 2
    
    def test_compound_question_also(self):
        """Test decomposing compound question with 'also'."""
        questions = decompose_question("Explain Python also explain JavaScript")
        assert len(questions) >= 2
    
    def test_question_mark_added(self):
        """Test that question marks are added."""
        questions = decompose_question("What is X and what is Y")
        for q in questions:
            assert q.endswith("?")
    
    def test_capitalization(self):
        """Test that questions are capitalized."""
        questions = decompose_question("what is x and what is y")
        for q in questions:
            assert q[0].isupper()


class TestSynthesizeAnswer:
    """Tests for answer synthesis."""
    
    def test_empty_contexts(self):
        """Test synthesis with no contexts."""
        answer = synthesize_answer("What is X?", [])
        assert "No relevant information" in answer
    
    def test_single_context(self):
        """Test synthesis with single context."""
        answer = synthesize_answer(
            "What is Python?",
            ["Python is a programming language."]
        )
        assert "Python is a programming language" in answer
    
    def test_multiple_contexts(self):
        """Test synthesis with multiple contexts."""
        answer = synthesize_answer(
            "What is Python?",
            [
                "Python is a programming language.",
                "Python was created by Guido van Rossum."
            ]
        )
        assert "Python" in answer
    
    def test_context_truncation(self):
        """Test that long contexts are truncated."""
        long_context = "x" * 5000
        answer = synthesize_answer("Question?", [long_context], max_context_length=100)
        # Answer should be shorter than the original context
        assert len(answer) < 5000


class TestSimpleQueryEngine:
    """Tests for SimpleQueryEngine."""
    
    def test_query_with_context(self):
        """Test querying with context."""
        engine = SimpleQueryEngine()
        result = engine.query(
            "What is Python?",
            context=["Python is a programming language."]
        )
        
        assert result.answer is not None
        assert len(result.sources) == 1
        assert result.metadata["mode"] == "default"
    
    def test_query_without_context(self):
        """Test querying without context."""
        engine = SimpleQueryEngine()
        result = engine.query("What is Python?")
        
        assert "No relevant information" in result.answer
        assert len(result.sources) == 0
    
    def test_aquery_async(self):
        """Test async querying."""
        import asyncio
        
        engine = SimpleQueryEngine()
        
        async def run_test():
            result = await engine.aquery(
                "What is Python?",
                context=["Python is a language."]
            )
            return result
        
        result = asyncio.run(run_test())
        assert result.answer is not None


class TestSubQuestionEngine:
    """Tests for SubQuestionEngine."""
    
    def test_query_decomposes(self):
        """Test that query decomposes questions."""
        engine = SubQuestionEngine()
        result = engine.query(
            "What is Python and what is JavaScript?",
            context=["Python is a language.", "JavaScript is also a language."]
        )
        
        assert result.answer is not None
        assert result.sub_questions is not None
        assert len(result.sub_questions) >= 1
    
    def test_query_simple_question(self):
        """Test with simple question (no decomposition needed)."""
        engine = SubQuestionEngine()
        result = engine.query(
            "What is Python?",
            context=["Python is a programming language."]
        )
        
        assert result.answer is not None
    
    def test_metadata_includes_count(self):
        """Test that metadata includes sub-question count."""
        engine = SubQuestionEngine()
        result = engine.query(
            "What is X and what is Y?",
            context=["X is something.", "Y is something else."]
        )
        
        assert "sub_question_count" in result.metadata


class TestQueryEngineRegistry:
    """Tests for QueryEngineRegistry."""
    
    def test_default_engine_registered(self):
        """Test that default engine is registered."""
        registry = get_query_engine_registry()
        assert "default" in registry.list_engines()
        assert "simple" in registry.list_engines()
    
    def test_sub_question_engine_registered(self):
        """Test that sub_question engine is registered."""
        registry = get_query_engine_registry()
        assert "sub_question" in registry.list_engines()
    
    def test_get_default_engine(self):
        """Test getting default engine."""
        registry = get_query_engine_registry()
        engine = registry.get("default")
        assert engine is not None
        assert engine.mode == QueryMode.DEFAULT
    
    def test_get_nonexistent_engine(self):
        """Test getting non-existent engine."""
        registry = get_query_engine_registry()
        assert registry.get("nonexistent") is None
    
    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = get_query_engine_registry()
        registry2 = get_query_engine_registry()
        assert registry1 is registry2
