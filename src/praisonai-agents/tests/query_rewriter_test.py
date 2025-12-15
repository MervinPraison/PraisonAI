"""
Tests for QueryRewriterAgent

Run with: python -m pytest tests/query_rewriter_test.py -v
"""

import pytest
from unittest.mock import patch


class TestQueryRewriterImports:
    """Test that all imports work correctly."""
    
    def test_import_from_package(self):
        """Test importing from main package."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy, RewriteResult
        assert QueryRewriterAgent is not None
        assert RewriteStrategy is not None
        assert RewriteResult is not None
    
    def test_import_from_agent_module(self):
        """Test importing from agent module."""
        from praisonaiagents.agent import QueryRewriterAgent, RewriteStrategy, RewriteResult
        assert QueryRewriterAgent is not None
        assert RewriteStrategy is not None
        assert RewriteResult is not None


class TestRewriteStrategy:
    """Test RewriteStrategy enum."""
    
    def test_strategy_values(self):
        """Test all strategy values exist."""
        from praisonaiagents import RewriteStrategy
        
        assert RewriteStrategy.BASIC.value == "basic"
        assert RewriteStrategy.HYDE.value == "hyde"
        assert RewriteStrategy.STEP_BACK.value == "step_back"
        assert RewriteStrategy.SUB_QUERIES.value == "sub_queries"
        assert RewriteStrategy.MULTI_QUERY.value == "multi_query"
        assert RewriteStrategy.CONTEXTUAL.value == "contextual"
        assert RewriteStrategy.AUTO.value == "auto"


class TestRewriteResult:
    """Test RewriteResult dataclass."""
    
    def test_result_creation(self):
        """Test creating a RewriteResult."""
        from praisonaiagents import RewriteResult, RewriteStrategy
        
        result = RewriteResult(
            original_query="test query",
            rewritten_queries=["rewritten test query"],
            strategy_used=RewriteStrategy.BASIC
        )
        
        assert result.original_query == "test query"
        assert result.rewritten_queries == ["rewritten test query"]
        assert result.strategy_used == RewriteStrategy.BASIC
    
    def test_primary_query_property(self):
        """Test primary_query property."""
        from praisonaiagents import RewriteResult, RewriteStrategy
        
        result = RewriteResult(
            original_query="test",
            rewritten_queries=["first", "second"],
            strategy_used=RewriteStrategy.MULTI_QUERY
        )
        
        assert result.primary_query == "first"
    
    def test_primary_query_fallback(self):
        """Test primary_query falls back to original if empty."""
        from praisonaiagents import RewriteResult, RewriteStrategy
        
        result = RewriteResult(
            original_query="test",
            rewritten_queries=[],
            strategy_used=RewriteStrategy.BASIC
        )
        
        assert result.primary_query == "test"
    
    def test_all_queries_property(self):
        """Test all_queries property combines all queries."""
        from praisonaiagents import RewriteResult, RewriteStrategy
        
        result = RewriteResult(
            original_query="original",
            rewritten_queries=["rewritten"],
            strategy_used=RewriteStrategy.STEP_BACK,
            step_back_question="step back",
            sub_queries=["sub1", "sub2"]
        )
        
        all_q = result.all_queries
        assert "original" in all_q
        assert "rewritten" in all_q
        assert "step back" in all_q
        assert "sub1" in all_q
        assert "sub2" in all_q


class TestQueryRewriterAgentInit:
    """Test QueryRewriterAgent initialization."""
    
    def test_default_initialization(self):
        """Test agent initializes with defaults."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        assert agent.name == "QueryRewriterAgent"
        assert agent.model == "gpt-4o-mini"
        assert not agent.verbose
        assert agent.max_queries == 5
        assert agent.temperature == 0.3
        assert agent.max_tokens == 500
    
    def test_custom_initialization(self):
        """Test agent initializes with custom values."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent(
            name="CustomRewriter",
            model="gpt-4o",
            verbose=True,
            max_queries=10,
            temperature=0.5,
            max_tokens=1000
        )
        
        assert agent.name == "CustomRewriter"
        assert agent.model == "gpt-4o"
        assert agent.verbose
        assert agent.max_queries == 10
        assert agent.temperature == 0.5
        assert agent.max_tokens == 1000
    
    def test_default_abbreviations(self):
        """Test default abbreviations are set."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        assert "AI" in agent.abbreviations
        assert "ML" in agent.abbreviations
        assert "RAG" in agent.abbreviations
        assert agent.abbreviations["AI"] == "Artificial Intelligence"


class TestAbbreviationExpansion:
    """Test abbreviation expansion functionality."""
    
    def test_expand_abbreviations(self):
        """Test _expand_abbreviations method."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        result = agent._expand_abbreviations("AI trends")
        assert "Artificial Intelligence" in result
    
    def test_add_abbreviation(self):
        """Test adding single abbreviation."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        agent.add_abbreviation("K8s", "Kubernetes")
        
        assert "K8S" in agent.abbreviations
        assert agent.abbreviations["K8S"] == "Kubernetes"
    
    def test_add_abbreviations(self):
        """Test adding multiple abbreviations."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        agent.add_abbreviations({
            "TF": "TensorFlow",
            "PT": "PyTorch"
        })
        
        assert "TF" in agent.abbreviations
        assert "PT" in agent.abbreviations


class TestQueryDetection:
    """Test query analysis methods."""
    
    def test_is_short_query(self):
        """Test short query detection."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        assert agent._is_short_query("AI")
        assert agent._is_short_query("AI trends")
        assert not agent._is_short_query("What are the latest AI trends in 2025?")
    
    def test_is_follow_up(self):
        """Test follow-up query detection."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        assert agent._is_follow_up("What about it?")
        assert agent._is_follow_up("And this one?")
        assert not agent._is_follow_up("What is AI?")
    
    def test_is_complex_query(self):
        """Test complex query detection."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        assert agent._is_complex_query("What is A and what is B?")
        assert agent._is_complex_query("Question one? Question two?")
        assert not agent._is_complex_query("What is AI?")


class TestStrategyDetection:
    """Test automatic strategy detection."""
    
    def test_detect_basic_for_short(self):
        """Test BASIC detected for short queries."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        agent = QueryRewriterAgent()
        
        strategy = agent._detect_strategy("AI")
        assert strategy == RewriteStrategy.BASIC
    
    def test_detect_contextual_for_followup(self):
        """Test CONTEXTUAL detected for follow-up with history."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        agent = QueryRewriterAgent()
        chat_history = [{"role": "user", "content": "Tell me about Python"}]
        
        strategy = agent._detect_strategy("What about it?", chat_history)
        assert strategy == RewriteStrategy.CONTEXTUAL
    
    def test_detect_sub_queries_for_complex(self):
        """Test SUB_QUERIES detected for complex queries."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        agent = QueryRewriterAgent()
        
        strategy = agent._detect_strategy("What is A and what is B?")
        assert strategy == RewriteStrategy.SUB_QUERIES


class TestJSONParsing:
    """Test JSON array parsing from LLM responses."""
    
    def test_parse_valid_json(self):
        """Test parsing valid JSON array."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        result = agent._parse_json_array('["query1", "query2"]')
        assert result == ["query1", "query2"]
    
    def test_parse_json_in_text(self):
        """Test extracting JSON from surrounding text."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        result = agent._parse_json_array('Here are the queries: ["q1", "q2"]')
        assert result == ["q1", "q2"]
    
    def test_parse_fallback_newlines(self):
        """Test fallback to newline splitting."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        result = agent._parse_json_array("1. Query one\n2. Query two\n3. Query three")
        assert len(result) >= 2


class TestRewriteWithMockedLLM:
    """Test rewrite methods with mocked LLM."""
    
    @patch.object(__import__('praisonaiagents.agent.query_rewriter_agent', fromlist=['QueryRewriterAgent']).QueryRewriterAgent, '_call_agent')
    def test_rewrite_basic(self, mock_llm):
        """Test basic rewriting with mocked LLM."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        mock_llm.return_value = "What are the current trends in AI?"
        
        agent = QueryRewriterAgent()
        result = agent.rewrite("AI trends", strategy=RewriteStrategy.BASIC)
        
        assert result.strategy_used == RewriteStrategy.BASIC
        assert len(result.rewritten_queries) > 0
        mock_llm.assert_called_once()
    
    @patch.object(__import__('praisonaiagents.agent.query_rewriter_agent', fromlist=['QueryRewriterAgent']).QueryRewriterAgent, '_call_agent')
    def test_rewrite_hyde(self, mock_llm):
        """Test HyDE rewriting with mocked LLM."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        mock_llm.return_value = "Quantum computing is a type of computation..."
        
        agent = QueryRewriterAgent()
        result = agent.rewrite("What is quantum computing?", strategy=RewriteStrategy.HYDE)
        
        assert result.strategy_used == RewriteStrategy.HYDE
        assert result.hypothetical_document is not None
        mock_llm.assert_called_once()
    
    @patch.object(__import__('praisonaiagents.agent.query_rewriter_agent', fromlist=['QueryRewriterAgent']).QueryRewriterAgent, '_call_agent')
    def test_rewrite_step_back(self, mock_llm):
        """Test step-back rewriting with mocked LLM."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        # First call for step-back, second for basic
        mock_llm.side_effect = [
            "What are the fundamentals of language models?",
            "What are the differences between GPT-4 and Claude 3?"
        ]
        
        agent = QueryRewriterAgent()
        result = agent.rewrite("GPT-4 vs Claude 3?", strategy=RewriteStrategy.STEP_BACK)
        
        assert result.strategy_used == RewriteStrategy.STEP_BACK
        assert result.step_back_question is not None
    
    @patch.object(__import__('praisonaiagents.agent.query_rewriter_agent', fromlist=['QueryRewriterAgent']).QueryRewriterAgent, '_call_agent')
    def test_rewrite_sub_queries(self, mock_llm):
        """Test sub-query decomposition with mocked LLM."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        mock_llm.return_value = '["What is RAG?", "What are the best embedding models?"]'
        
        agent = QueryRewriterAgent()
        result = agent.rewrite("RAG setup and embedding models?", strategy=RewriteStrategy.SUB_QUERIES)
        
        assert result.strategy_used == RewriteStrategy.SUB_QUERIES
        assert result.sub_queries is not None
        assert len(result.sub_queries) >= 1
    
    @patch.object(__import__('praisonaiagents.agent.query_rewriter_agent', fromlist=['QueryRewriterAgent']).QueryRewriterAgent, '_call_agent')
    def test_rewrite_multi_query(self, mock_llm):
        """Test multi-query generation with mocked LLM."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        mock_llm.return_value = '["Query 1", "Query 2", "Query 3"]'
        
        agent = QueryRewriterAgent()
        result = agent.rewrite("LLM quality?", strategy=RewriteStrategy.MULTI_QUERY, num_queries=3)
        
        assert result.strategy_used == RewriteStrategy.MULTI_QUERY
        assert len(result.rewritten_queries) >= 1
    
    @patch.object(__import__('praisonaiagents.agent.query_rewriter_agent', fromlist=['QueryRewriterAgent']).QueryRewriterAgent, '_call_agent')
    def test_rewrite_contextual(self, mock_llm):
        """Test contextual rewriting with mocked LLM."""
        from praisonaiagents import QueryRewriterAgent, RewriteStrategy
        
        mock_llm.return_value = "How does Python's performance compare to other languages?"
        
        agent = QueryRewriterAgent()
        chat_history = [
            {"role": "user", "content": "Tell me about Python"},
            {"role": "assistant", "content": "Python is a programming language..."}
        ]
        
        result = agent.rewrite(
            "What about its performance?",
            strategy=RewriteStrategy.CONTEXTUAL,
            chat_history=chat_history
        )
        
        assert result.strategy_used == RewriteStrategy.CONTEXTUAL
        assert "Python" in result.primary_query or len(result.rewritten_queries) > 0


class TestConvenienceMethods:
    """Test convenience methods."""
    
    def test_convenience_methods_exist(self):
        """Test all convenience methods exist."""
        from praisonaiagents import QueryRewriterAgent
        
        agent = QueryRewriterAgent()
        
        assert hasattr(agent, 'rewrite_basic')
        assert hasattr(agent, 'rewrite_hyde')
        assert hasattr(agent, 'rewrite_step_back')
        assert hasattr(agent, 'rewrite_sub_queries')
        assert hasattr(agent, 'rewrite_multi_query')
        assert hasattr(agent, 'rewrite_contextual')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
