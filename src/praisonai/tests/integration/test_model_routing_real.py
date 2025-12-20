"""
Real integration tests for Model Routing with actual API calls.

Tests the RouterHandler with real LLM providers.
Requires API keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from praisonai.cli.features.router import RouterHandler


class TestRouterHandlerReal:
    """Real integration tests for RouterHandler."""
    
    def test_router_handler_initialization(self):
        """Test RouterHandler initializes correctly."""
        handler = RouterHandler(verbose=True)
        
        assert handler is not None
        assert handler.model_router is not None
        assert len(handler.model_router) > 0
        print(f"✅ RouterHandler initialized with {len(handler.model_router)} default models")
    
    def test_complexity_analysis(self):
        """Test complexity analysis for different prompts."""
        handler = RouterHandler()
        
        # Simple prompts
        simple_prompts = [
            "What is 2+2?",
            "Define photosynthesis",
            "List the planets",
        ]
        
        for prompt in simple_prompts:
            complexity = handler.analyze_complexity(prompt)
            print(f"  '{prompt[:30]}...' -> {complexity}")
            assert complexity == 'simple', f"Expected 'simple' for: {prompt}"
        
        print("✅ Simple prompts correctly classified")
        
        # Complex prompts
        complex_prompts = [
            "Analyze and research the comprehensive impact of AI on healthcare systems globally",
            "Compare and evaluate different machine learning architectures for natural language processing",
        ]
        
        for prompt in complex_prompts:
            complexity = handler.analyze_complexity(prompt)
            print(f"  '{prompt[:40]}...' -> {complexity}")
            assert complexity == 'complex', f"Expected 'complex' for: {prompt}"
        
        print("✅ Complex prompts correctly classified")
    
    def test_model_selection_by_complexity(self):
        """Test model selection based on complexity."""
        handler = RouterHandler(verbose=True)
        
        # Simple task - should select cheap model
        simple_model = handler.select_model("What is the capital of France?")
        print(f"Simple task model: {simple_model}")
        assert simple_model in ['gpt-4o-mini', 'claude-3-haiku', 'gemini-1.5-flash']
        
        # Complex task - should select powerful model
        complex_model = handler.select_model(
            "Analyze and research the comprehensive impact of quantum computing on cybersecurity"
        )
        print(f"Complex task model: {complex_model}")
        assert complex_model in ['gpt-4-turbo', 'claude-3-opus', 'o1-preview']
        
        print("✅ Model selection by complexity works correctly")
    
    def test_model_selection_with_provider_preference(self):
        """Test model selection with provider preference."""
        handler = RouterHandler(verbose=True)
        
        # Prefer OpenAI
        openai_model = handler.select_model(
            "Write a simple greeting",
            preferred_provider='openai'
        )
        print(f"OpenAI preferred: {openai_model}")
        assert 'gpt' in openai_model.lower() or 'o1' in openai_model.lower()
        
        # Prefer Anthropic
        anthropic_model = handler.select_model(
            "Write a simple greeting",
            preferred_provider='anthropic'
        )
        print(f"Anthropic preferred: {anthropic_model}")
        assert 'claude' in anthropic_model.lower()
        
        # Prefer Google
        google_model = handler.select_model(
            "Write a simple greeting",
            preferred_provider='google'
        )
        print(f"Google preferred: {google_model}")
        assert 'gemini' in google_model.lower()
        
        print("✅ Provider preference works correctly")
    
    def test_custom_models_from_yaml(self):
        """Test loading custom models from YAML-like config."""
        handler = RouterHandler(verbose=True)
        
        # Define custom models (as would be in YAML)
        custom_models = {
            'my-cheap-model': {
                'provider': 'openai',
                'complexity': ['simple'],
                'cost_per_1k': 0.0001,
                'capabilities': ['text']
            },
            'my-balanced-model': {
                'provider': 'openai',
                'complexity': ['moderate'],
                'cost_per_1k': 0.001,
                'capabilities': ['text', 'function-calling']
            },
            'my-premium-model': {
                'provider': 'anthropic',
                'complexity': ['complex', 'very_complex'],
                'cost_per_1k': 0.015,
                'capabilities': ['text', 'vision', 'function-calling']
            }
        }
        
        # Load custom models
        handler.load_models_from_config(custom_models)
        
        # Verify models are loaded
        available = handler.get_available_models()
        print(f"Available models: {available}")
        
        assert 'my-cheap-model' in available
        assert 'my-balanced-model' in available
        assert 'my-premium-model' in available
        
        # Test selection with custom models
        simple_model = handler.select_model("What is 2+2?")
        print(f"Simple task -> {simple_model}")
        assert simple_model == 'my-cheap-model'
        
        complex_model = handler.select_model(
            "Analyze and research the comprehensive impact of AI"
        )
        print(f"Complex task -> {complex_model}")
        assert complex_model == 'my-premium-model'
        
        print("✅ Custom models from YAML config work correctly")
    
    def test_cost_threshold(self):
        """Test cost threshold filtering."""
        handler = RouterHandler(verbose=True)
        
        # Load models with different costs
        custom_models = {
            'cheap': {
                'provider': 'openai',
                'complexity': ['simple', 'moderate', 'complex'],
                'cost_per_1k': 0.0001,
                'capabilities': ['text']
            },
            'expensive': {
                'provider': 'anthropic',
                'complexity': ['simple', 'moderate', 'complex'],
                'cost_per_1k': 0.05,
                'capabilities': ['text']
            }
        }
        
        handler.load_models_from_config(custom_models)
        
        # Set cost threshold
        handler.set_cost_threshold(0.001)
        
        # Should only select cheap model
        model = handler.select_model("Any task here")
        print(f"With cost threshold 0.001: {model}")
        assert model == 'cheap'
        
        # Verify cost
        cost = handler.get_model_cost(model)
        assert cost <= 0.001
        
        print("✅ Cost threshold filtering works correctly")
    
    def test_merge_with_defaults(self):
        """Test merging custom models with defaults."""
        handler = RouterHandler(verbose=True)
        
        custom_models = {
            'my-custom-model': {
                'provider': 'custom',
                'complexity': ['moderate'],
                'cost_per_1k': 0.002,
                'capabilities': ['text']
            }
        }
        
        handler.load_models_from_config(custom_models, merge_with_defaults=True)
        
        available = handler.get_available_models()
        print(f"Available models (merged): {available}")
        
        # Should have both custom and default models
        assert 'my-custom-model' in available
        assert 'gpt-4o-mini' in available
        
        print("✅ Merge with defaults works correctly")


class TestRealAPIIntegration:
    """Tests that make real API calls - requires API keys."""
    
    @pytest.mark.skipif(
        not os.getenv('OPENAI_API_KEY') or 
        'test' in os.getenv('OPENAI_API_KEY', '').lower() or
        not os.getenv('OPENAI_API_KEY', '').startswith('sk-') or
        len(os.getenv('OPENAI_API_KEY', '')) < 40,
        reason="OPENAI_API_KEY not set or using test/invalid key"
    )
    def test_real_openai_call(self):
        """Test real OpenAI API call with routed model."""
        from praisonaiagents import Agent
        
        handler = RouterHandler(verbose=True)
        
        # Select model for simple task
        model = handler.select_model(
            "What is 2+2?",
            preferred_provider='openai'
        )
        print(f"Selected model: {model}")
        
        # Create agent with selected model
        agent = Agent(
            name="TestAgent",
            role="Calculator",
            goal="Answer simple math questions",
            llm=model,
            verbose=True
        )
        
        # Run simple task
        result = agent.start("What is 2+2? Answer with just the number.")
        print(f"Result: {result}")
        
        assert '4' in str(result)
        print("✅ Real OpenAI API call successful")
    
    @pytest.mark.skipif(
        not os.getenv('ANTHROPIC_API_KEY'),
        reason="ANTHROPIC_API_KEY not set"
    )
    def test_real_anthropic_call(self):
        """Test real Anthropic API call with routed model."""
        from praisonaiagents import Agent
        
        handler = RouterHandler(verbose=True)
        
        # Select Anthropic model
        model = handler.select_model(
            "What is the capital of France?",
            preferred_provider='anthropic'
        )
        print(f"Selected model: {model}")
        
        # Create agent with selected model
        agent = Agent(
            name="TestAgent",
            role="Geography Expert",
            goal="Answer geography questions",
            llm=model,
            verbose=True
        )
        
        # Run task
        result = agent.start("What is the capital of France? Answer with just the city name.")
        print(f"Result: {result}")
        
        assert 'paris' in str(result).lower()
        print("✅ Real Anthropic API call successful")
    
    @pytest.mark.skipif(
        not os.getenv('GEMINI_API_KEY'),
        reason="GEMINI_API_KEY not set"
    )
    def test_real_gemini_call(self):
        """Test real Gemini API call with routed model."""
        from praisonaiagents import Agent
        
        handler = RouterHandler(verbose=True)
        
        # Select Google model
        model = handler.select_model(
            "What is 3 times 7?",
            preferred_provider='google'
        )
        print(f"Selected model: {model}")
        
        # Create agent with selected model
        agent = Agent(
            name="TestAgent",
            role="Calculator",
            goal="Answer math questions",
            llm=f"gemini/{model}" if not model.startswith("gemini/") else model,
            verbose=True
        )
        
        # Run task
        result = agent.start("What is 3 times 7? Answer with just the number.")
        print(f"Result: {result}")
        
        assert '21' in str(result)
        print("✅ Real Gemini API call successful")


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '-s'])
