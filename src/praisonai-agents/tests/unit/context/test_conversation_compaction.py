"""
Tests for intelligent conversation compaction functionality.
"""

import pytest
from unittest.mock import Mock

from praisonaiagents.context.conversation import (
    HybridConversationAnalyzer,
    IntelligentConversationCompactor,
    get_conversation_analyzer,
    get_conversation_compactor,
)
from praisonaiagents.context.protocols import ConversationContext
from praisonaiagents.context.optimizer import ConversationOptimizer
from praisonaiagents.context.models import OptimizerStrategy, OptimizationResult


class TestConversationAnalyzer:
    """Test conversation analysis functionality."""
    
    def test_rule_based_analysis(self):
        """Test rule-based conversation analysis."""
        analyzer = HybridConversationAnalyzer()
        
        messages = [
            {"role": "user", "content": "I need help building a website"},
            {"role": "assistant", "content": "I can help you build a website. What kind of site do you need?"},
            {"role": "user", "content": "I want to create an e-commerce site for selling books"},
            {"role": "assistant", "content": "Great! We'll need to implement user authentication, product catalog, and payment processing."},
            {"role": "user", "content": "Let's start with the user authentication"},
            {"role": "assistant", "content": "I'll help you implement user registration and login functionality."},
        ]
        
        context = analyzer.analyze_conversation(messages)
        
        assert isinstance(context, ConversationContext)
        assert context.original_message_count == len(messages)
        assert context.main_topic  # Should identify some topic
        assert context.conversation_tone in ["casual", "professional", "formal"]
    
    def test_extract_key_decisions(self):
        """Test extraction of key decisions from conversation."""
        analyzer = HybridConversationAnalyzer()
        
        messages = [
            {"role": "user", "content": "Should we use React or Vue?"},
            {"role": "assistant", "content": "Both are good choices. What's your experience?"},
            {"role": "user", "content": "I decided to go with React for this project"},
            {"role": "assistant", "content": "Good choice! Let's also use TypeScript for better type safety"},
        ]
        
        decisions = analyzer.extract_key_decisions(messages)
        
        assert len(decisions) > 0
        assert any("React" in decision for decision in decisions)
    
    def test_identify_main_topic(self):
        """Test main topic identification."""
        analyzer = HybridConversationAnalyzer()
        
        messages = [
            {"role": "user", "content": "Help me implement a REST API for my blog application"},
            {"role": "assistant", "content": "I'll help you create a REST API. What endpoints do you need?"},
        ]
        
        topic = analyzer.identify_main_topic(messages)
        
        assert topic
        assert "REST API" in topic or "blog" in topic or "API" in topic
    
    def test_llm_analysis_fallback(self):
        """Test that LLM analysis falls back to rule-based when LLM fails."""
        # Mock LLM function that raises exception
        def failing_llm_fn(prompt, max_tokens=None):
            raise Exception("LLM service unavailable")
        
        analyzer = HybridConversationAnalyzer(llm_analyze_fn=failing_llm_fn)
        
        messages = [
            {"role": "user", "content": "I want to build a machine learning model"},
            {"role": "assistant", "content": "What type of ML model are you looking to build?"},
        ]
        
        # Should not raise exception and should return valid context
        context = analyzer.analyze_conversation(messages)
        
        assert isinstance(context, ConversationContext)
        assert context.main_topic


class TestConversationCompactor:
    """Test intelligent conversation compaction."""
    
    def test_conversation_compaction(self):
        """Test basic conversation compaction."""
        analyzer = HybridConversationAnalyzer()
        compactor = IntelligentConversationCompactor(analyzer)
        
        # Create a longer conversation
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"This is user message {i} with some content to make it longer and exceed token limits"})
            messages.append({"role": "assistant", "content": f"This is assistant response {i} providing helpful information and guidance"})
        
        # Compact to a much smaller target
        target_tokens = 200  # Very small target to force compaction
        
        result, context = compactor.compact_conversation(
            messages=messages,
            target_tokens=target_tokens,
            preserve_recent=3
        )
        
        # Should have fewer messages than original
        assert len(result) < len(messages)
        
        # Should have a summary message
        summary_messages = [m for m in result if m.get("_metadata", {}).get("is_conversation_summary")]
        assert len(summary_messages) >= 1
        
        # Context should have useful information
        assert isinstance(context, ConversationContext)
        assert context.original_message_count == len(messages)
    
    def test_no_compaction_needed(self):
        """Test when no compaction is needed."""
        analyzer = HybridConversationAnalyzer()
        compactor = IntelligentConversationCompactor(analyzer)
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        result, context = compactor.compact_conversation(
            messages=messages,
            target_tokens=10000,  # Large target
        )
        
        # Should return original messages unchanged
        assert result == messages
        assert context.original_message_count == len(messages)
    
    def test_min_compaction_ratio(self):
        """Test minimum compaction ratio enforcement."""
        analyzer = HybridConversationAnalyzer()
        compactor = IntelligentConversationCompactor(
            analyzer=analyzer,
            min_compaction_ratio=0.5  # Require 50% compression
        )
        
        # Small conversation that won't achieve 50% compression
        messages = [
            {"role": "user", "content": "Short question"},
            {"role": "assistant", "content": "Short answer"},
        ]
        
        result, context = compactor.compact_conversation(
            messages=messages,
            target_tokens=50,  # Force compaction attempt
        )
        
        # Should return original if compression ratio too small
        # (depends on implementation details)
        assert len(result) <= len(messages)


class TestConversationOptimizer:
    """Test ConversationOptimizer integration."""
    
    def test_conversation_optimizer_basic(self):
        """Test basic conversation optimizer functionality."""
        optimizer = ConversationOptimizer(preserve_recent=2)
        
        messages = []
        for i in range(10):
            messages.append({"role": "user", "content": f"User message {i}" * 50})  # Make it long
            messages.append({"role": "assistant", "content": f"Assistant message {i}" * 50})
        
        target_tokens = 500  # Force optimization
        
        result, optimization_result = optimizer.optimize(messages, target_tokens)
        
        assert isinstance(optimization_result, OptimizationResult)
        assert optimization_result.strategy_used == OptimizerStrategy.CONVERSATION
        
        # Should have achieved some optimization
        assert len(result) <= len(messages)
    
    def test_conversation_optimizer_fallback(self):
        """Test fallback to summarization when conversation module not available."""
        # Create optimizer that will fail to load conversation module
        optimizer = ConversationOptimizer(preserve_recent=2)
        
        # Mock the analyzer to return None (simulating import failure)
        optimizer._get_analyzer = lambda: None
        optimizer._get_compactor = lambda: None
        
        messages = [
            {"role": "user", "content": "Test message" * 100},
            {"role": "assistant", "content": "Test response" * 100},
        ]
        
        result, optimization_result = optimizer.optimize(messages, target_tokens=100)
        
        # Should still work (fallback to summarization)
        assert isinstance(optimization_result, OptimizationResult)
        assert len(result) <= len(messages)


class TestFactoryFunctions:
    """Test factory functions."""
    
    def test_get_conversation_analyzer(self):
        """Test conversation analyzer factory."""
        # Test hybrid strategy
        analyzer = get_conversation_analyzer("hybrid")
        assert isinstance(analyzer, HybridConversationAnalyzer)
        
        # Test rule-based strategy  
        analyzer = get_conversation_analyzer("rule_based")
        assert isinstance(analyzer, HybridConversationAnalyzer)
        
        # Test with LLM function
        mock_llm = Mock()
        analyzer = get_conversation_analyzer("hybrid", llm_analyze_fn=mock_llm)
        assert analyzer.llm_analyze_fn == mock_llm
    
    def test_get_conversation_compactor(self):
        """Test conversation compactor factory."""
        analyzer = get_conversation_analyzer("hybrid")
        compactor = get_conversation_compactor(analyzer)
        
        assert isinstance(compactor, IntelligentConversationCompactor)
        assert compactor.analyzer == analyzer
    
    def test_invalid_strategy(self):
        """Test invalid strategy handling."""
        with pytest.raises(ValueError):
            get_conversation_analyzer("invalid_strategy")


class TestConversationContext:
    """Test ConversationContext functionality."""
    
    def test_conversation_context_summary_message(self):
        """Test conversion to summary message."""
        context = ConversationContext(
            main_topic="Building a website",
            current_goal="Implement user authentication",
            progress_summary="Discussed technology choices",
            key_decisions=["Use React framework", "Add TypeScript"],
            important_facts=["Need SSL certificates", "Database will be PostgreSQL"],
            action_items=["Set up development environment", "Create wireframes"],
            user_preferences=["Prefer minimal design", "Mobile-first approach"],
            tool_results_summary=["npm install completed successfully"],
            conversation_tone="professional",
            original_message_count=15,
            compacted_message_count=5,
        )
        
        summary_msg = context.to_summary_message()
        
        assert summary_msg["role"] == "system"
        assert "Building a website" in summary_msg["content"]
        assert "React framework" in summary_msg["content"]
        assert "SSL certificates" in summary_msg["content"]
        
        metadata = summary_msg["_metadata"]
        assert metadata["is_conversation_summary"] is True
        assert metadata["original_message_count"] == 15
        assert metadata["conversation_tone"] == "professional"


if __name__ == "__main__":
    pytest.main([__file__])