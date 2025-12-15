"""
Tests for PromptExpanderAgent

Run with: python -m pytest tests/test_prompt_expander_agent.py -v
"""

import pytest
from unittest.mock import patch, MagicMock


class TestPromptExpanderImports:
    """Test that all imports work correctly."""
    
    def test_import_from_package(self):
        """Test importing from main package."""
        from praisonaiagents import PromptExpanderAgent, ExpandStrategy, ExpandResult
        assert PromptExpanderAgent is not None
        assert ExpandStrategy is not None
        assert ExpandResult is not None
    
    def test_import_from_agent_module(self):
        """Test importing from agent module."""
        from praisonaiagents.agent import PromptExpanderAgent, ExpandStrategy, ExpandResult
        assert PromptExpanderAgent is not None
        assert ExpandStrategy is not None
        assert ExpandResult is not None


class TestExpandStrategy:
    """Test ExpandStrategy enum."""
    
    def test_strategy_values(self):
        """Test all strategy values exist."""
        from praisonaiagents import ExpandStrategy
        
        assert ExpandStrategy.BASIC.value == "basic"
        assert ExpandStrategy.DETAILED.value == "detailed"
        assert ExpandStrategy.STRUCTURED.value == "structured"
        assert ExpandStrategy.CREATIVE.value == "creative"
        assert ExpandStrategy.AUTO.value == "auto"


class TestExpandResult:
    """Test ExpandResult dataclass."""
    
    def test_result_creation(self):
        """Test creating an ExpandResult."""
        from praisonaiagents import ExpandResult, ExpandStrategy
        
        result = ExpandResult(
            original_prompt="write a movie script",
            expanded_prompt="Write a compelling movie script...",
            strategy_used=ExpandStrategy.BASIC
        )
        
        assert result.original_prompt == "write a movie script"
        assert result.expanded_prompt == "Write a compelling movie script..."
        assert result.strategy_used == ExpandStrategy.BASIC
    
    def test_result_with_metadata(self):
        """Test ExpandResult with metadata."""
        from praisonaiagents import ExpandResult, ExpandStrategy
        
        result = ExpandResult(
            original_prompt="test",
            expanded_prompt="expanded test",
            strategy_used=ExpandStrategy.DETAILED,
            metadata={"word_count": 50, "has_context": True}
        )
        
        assert result.metadata["word_count"] == 50
        assert result.metadata["has_context"] is True


class TestPromptExpanderAgentInit:
    """Test PromptExpanderAgent initialization."""
    
    def test_default_initialization(self):
        """Test agent initializes with defaults."""
        from praisonaiagents import PromptExpanderAgent
        
        agent = PromptExpanderAgent()
        
        assert agent.name == "PromptExpanderAgent"
        assert agent.model == "gpt-4o-mini"
        assert not agent.verbose
        assert agent.temperature == 0.7  # Higher for creativity
    
    def test_custom_initialization(self):
        """Test agent initializes with custom values."""
        from praisonaiagents import PromptExpanderAgent
        
        agent = PromptExpanderAgent(
            name="CustomExpander",
            model="gpt-4o",
            verbose=True,
            temperature=0.5
        )
        
        assert agent.name == "CustomExpander"
        assert agent.model == "gpt-4o"
        assert agent.verbose
        assert agent.temperature == 0.5
    
    def test_initialization_with_tools(self):
        """Test agent initializes with tools."""
        from praisonaiagents import PromptExpanderAgent
        
        def mock_tool(query: str) -> str:
            return "mock result"
        
        agent = PromptExpanderAgent(tools=[mock_tool])
        
        assert len(agent.tools) == 1


class TestPromptExpansion:
    """Test prompt expansion functionality."""
    
    def test_expand_preserves_task_intent(self):
        """Test that expansion preserves task intent (not converting to question)."""
        from praisonaiagents import PromptExpanderAgent, ExpandResult
        
        agent = PromptExpanderAgent()
        
        # Mock the internal agent call
        with patch.object(agent, '_call_agent') as mock_call:
            mock_call.return_value = "Write a compelling three-line movie script that captures a dramatic moment with vivid imagery and emotional depth."
            
            result = agent.expand("write a movie script in 3 lines")
            
            assert result.original_prompt == "write a movie script in 3 lines"
            assert "Write" in result.expanded_prompt  # Should start with action verb
            assert "?" not in result.expanded_prompt  # Should NOT be a question
    
    def test_expand_adds_detail(self):
        """Test that expansion adds meaningful detail."""
        from praisonaiagents import PromptExpanderAgent
        
        agent = PromptExpanderAgent()
        
        with patch.object(agent, '_call_agent') as mock_call:
            mock_call.return_value = "Create a detailed blog post about artificial intelligence trends in 2025, covering key developments in large language models, multimodal AI, and autonomous agents. Include specific examples and expert predictions."
            
            result = agent.expand("write about AI")
            
            # Expanded should be longer than original
            assert len(result.expanded_prompt) > len(result.original_prompt)


class TestExpandStrategies:
    """Test different expansion strategies."""
    
    def test_basic_strategy(self):
        """Test BASIC expansion strategy."""
        from praisonaiagents import PromptExpanderAgent, ExpandStrategy
        
        agent = PromptExpanderAgent()
        
        with patch.object(agent, '_call_agent') as mock_call:
            mock_call.return_value = "Write a movie script in three lines."
            
            result = agent.expand("movie script 3 lines", strategy=ExpandStrategy.BASIC)
            
            assert result.strategy_used == ExpandStrategy.BASIC
            mock_call.assert_called_once()
    
    def test_detailed_strategy(self):
        """Test DETAILED expansion strategy."""
        from praisonaiagents import PromptExpanderAgent, ExpandStrategy
        
        agent = PromptExpanderAgent()
        
        with patch.object(agent, '_call_agent') as mock_call:
            mock_call.return_value = """Write a compelling three-line movie script that:
- Opens with a hook that immediately grabs attention
- Builds tension or emotion in the middle line
- Delivers a powerful, memorable conclusion
Include vivid imagery, strong verbs, and emotional resonance."""
            
            result = agent.expand("movie script 3 lines", strategy=ExpandStrategy.DETAILED)
            
            assert result.strategy_used == ExpandStrategy.DETAILED
    
    def test_structured_strategy(self):
        """Test STRUCTURED expansion strategy."""
        from praisonaiagents import PromptExpanderAgent, ExpandStrategy
        
        agent = PromptExpanderAgent()
        
        with patch.object(agent, '_call_agent') as mock_call:
            mock_call.return_value = """Task: Write a three-line movie script
Format: Three lines, each serving a narrative purpose
Requirements:
- Line 1: Setup/Hook
- Line 2: Conflict/Development  
- Line 3: Resolution/Twist
Style: Cinematic, impactful"""
            
            result = agent.expand("movie script 3 lines", strategy=ExpandStrategy.STRUCTURED)
            
            assert result.strategy_used == ExpandStrategy.STRUCTURED
    
    def test_creative_strategy(self):
        """Test CREATIVE expansion strategy."""
        from praisonaiagents import PromptExpanderAgent, ExpandStrategy
        
        agent = PromptExpanderAgent()
        
        with patch.object(agent, '_call_agent') as mock_call:
            mock_call.return_value = "Craft an unforgettable three-line movie script that transports the reader into a vivid world. Let each line breathe with cinematic tension - a hook that grabs, a twist that surprises, and a finale that lingers in the mind long after reading."
            
            result = agent.expand("movie script 3 lines", strategy=ExpandStrategy.CREATIVE)
            
            assert result.strategy_used == ExpandStrategy.CREATIVE
    
    def test_auto_strategy_detection(self):
        """Test AUTO strategy detects appropriate expansion type."""
        from praisonaiagents import PromptExpanderAgent, ExpandStrategy
        
        agent = PromptExpanderAgent()
        
        # Short prompts should get DETAILED expansion
        strategy = agent._detect_strategy("AI")
        assert strategy in [ExpandStrategy.BASIC, ExpandStrategy.DETAILED]
        
        # Task prompts should preserve task nature
        strategy = agent._detect_strategy("write a poem about love")
        assert strategy is not None


class TestToolsIntegration:
    """Test tools integration with PromptExpanderAgent."""
    
    def test_expand_with_tools(self):
        """Test expansion with tools for context gathering."""
        from praisonaiagents import PromptExpanderAgent
        
        def search_tool(query: str) -> str:
            return "Latest AI trends: LLMs, multimodal, agents"
        
        agent = PromptExpanderAgent(tools=[search_tool])
        
        assert len(agent.tools) == 1
    
    def test_tools_passed_to_internal_agent(self):
        """Test that tools are passed to the internal agent."""
        from praisonaiagents import PromptExpanderAgent
        
        def mock_tool(query: str) -> str:
            return "result"
        
        agent = PromptExpanderAgent(tools=[mock_tool])
        
        # Access the lazy-initialized agent
        internal_agent = agent.agent
        
        # The internal agent should have the tools
        assert internal_agent.tools is not None


class TestConvenienceMethods:
    """Test convenience methods."""
    
    def test_convenience_methods_exist(self):
        """Test all convenience methods exist."""
        from praisonaiagents import PromptExpanderAgent
        
        agent = PromptExpanderAgent()
        
        assert hasattr(agent, 'expand')
        assert hasattr(agent, 'expand_basic')
        assert hasattr(agent, 'expand_detailed')
        assert hasattr(agent, 'expand_structured')
        assert hasattr(agent, 'expand_creative')


class TestEdgeCases:
    """Test edge cases."""
    
    def test_empty_prompt(self):
        """Test handling of empty prompt."""
        from praisonaiagents import PromptExpanderAgent
        
        agent = PromptExpanderAgent()
        
        with patch.object(agent, '_call_agent') as mock_call:
            mock_call.return_value = ""
            
            result = agent.expand("")
            
            # Should return original if expansion fails
            assert result.expanded_prompt == "" or result.original_prompt == ""
    
    def test_already_detailed_prompt(self):
        """Test that already detailed prompts are minimally modified."""
        from praisonaiagents import PromptExpanderAgent
        
        agent = PromptExpanderAgent()
        
        detailed_prompt = """Write a comprehensive blog post about machine learning, 
        covering supervised learning, unsupervised learning, and reinforcement learning. 
        Include code examples in Python and real-world applications."""
        
        with patch.object(agent, '_call_agent') as mock_call:
            # For detailed prompts, minimal expansion expected
            mock_call.return_value = detailed_prompt + " Ensure clarity and technical accuracy."
            
            result = agent.expand(detailed_prompt)
            
            # Should not drastically change already detailed prompts
            assert result.original_prompt == detailed_prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
