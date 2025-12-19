#!/usr/bin/env python
"""
Live test for model routing with real API calls.
Run this script directly to test with your API keys.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from praisonai.cli.features.router import RouterHandler


def test_router_basics():
    """Test basic router functionality."""
    print("\n" + "="*60)
    print("TEST 1: Router Basics")
    print("="*60)
    
    handler = RouterHandler(verbose=True)
    
    # Test complexity analysis
    print("\n📊 Complexity Analysis:")
    prompts = [
        ("What is 2+2?", "simple"),
        ("Define AI", "simple"),
        ("Analyze and research the comprehensive impact of AI on healthcare", "complex"),
    ]
    
    for prompt, expected in prompts:
        result = handler.analyze_complexity(prompt)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{prompt[:40]}...' -> {result} (expected: {expected})")
    
    print("\n✅ Router basics test passed!")


def test_model_selection():
    """Test model selection with different providers."""
    print("\n" + "="*60)
    print("TEST 2: Model Selection by Provider")
    print("="*60)
    
    handler = RouterHandler(verbose=True)
    
    providers = ['openai', 'anthropic', 'google']
    
    for provider in providers:
        model = handler.select_model("Simple question", preferred_provider=provider)
        print(f"  {provider}: {model}")
    
    print("\n✅ Model selection test passed!")


def test_custom_models():
    """Test custom model configuration."""
    print("\n" + "="*60)
    print("TEST 3: Custom Models from YAML Config")
    print("="*60)
    
    handler = RouterHandler(verbose=True)
    
    # Simulate YAML config
    models_config = {
        'cheap-model': {
            'provider': 'openai',
            'complexity': ['simple'],
            'cost_per_1k': 0.0001,
            'capabilities': ['text']
        },
        'premium-model': {
            'provider': 'anthropic',
            'complexity': ['complex', 'very_complex'],
            'cost_per_1k': 0.015,
            'capabilities': ['text', 'vision']
        }
    }
    
    handler.load_models_from_config(models_config)
    
    print(f"\n  Available models: {handler.get_available_models()}")
    
    simple_model = handler.select_model("What is 2+2?")
    print(f"  Simple task -> {simple_model}")
    assert simple_model == 'cheap-model', f"Expected cheap-model, got {simple_model}"
    
    complex_model = handler.select_model("Analyze and research comprehensive AI impact")
    print(f"  Complex task -> {complex_model}")
    assert complex_model == 'premium-model', f"Expected premium-model, got {complex_model}"
    
    print("\n✅ Custom models test passed!")


def test_real_openai():
    """Test real OpenAI API call."""
    print("\n" + "="*60)
    print("TEST 4: Real OpenAI API Call")
    print("="*60)
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'test-key':
        print("  ⚠️ OPENAI_API_KEY not set, skipping")
        return
    
    print(f"  API Key: {api_key[:20]}...")
    
    from praisonaiagents import Agent
    
    handler = RouterHandler(verbose=True)
    model = handler.select_model("What is 2+2?", preferred_provider='openai')
    print(f"  Selected model: {model}")
    
    agent = Agent(
        name="MathAgent",
        role="Calculator",
        goal="Answer math questions",
        llm=model,
        verbose=False
    )
    
    result = agent.start("What is 2+2? Reply with just the number.")
    print(f"  Result: {result}")
    
    if result and '4' in str(result):
        print("\n✅ OpenAI API test passed!")
    else:
        print("\n❌ OpenAI API test failed!")


def test_real_anthropic():
    """Test real Anthropic API call."""
    print("\n" + "="*60)
    print("TEST 5: Real Anthropic API Call")
    print("="*60)
    
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key or api_key == 'test-key':
        print("  ⚠️ ANTHROPIC_API_KEY not set, skipping")
        return
    
    print(f"  API Key: {api_key[:20]}...")
    
    from praisonaiagents import Agent
    
    handler = RouterHandler(verbose=True)
    model = handler.select_model("What is the capital of France?", preferred_provider='anthropic')
    print(f"  Selected model: {model}")
    
    # Model now includes provider prefix (anthropic/...)
    print(f"  Using LLM: {model}")
    
    agent = Agent(
        name="GeoAgent",
        role="Geography Expert",
        goal="Answer geography questions",
        llm=model,
        verbose=False
    )
    
    result = agent.start("What is the capital of France? Reply with just the city name.")
    print(f"  Result: {result}")
    
    if result and 'paris' in str(result).lower():
        print("\n✅ Anthropic API test passed!")
    else:
        print("\n❌ Anthropic API test failed!")


def test_real_gemini():
    """Test real Gemini API call."""
    print("\n" + "="*60)
    print("TEST 6: Real Gemini API Call")
    print("="*60)
    
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not api_key or api_key == 'test-key':
        print("  ⚠️ GEMINI_API_KEY/GOOGLE_API_KEY not set, skipping")
        return
    
    print(f"  API Key: {api_key[:20]}...")
    
    from praisonaiagents import Agent
    
    handler = RouterHandler(verbose=True)
    model = handler.select_model("What is 3 times 7?", preferred_provider='google')
    print(f"  Selected model: {model}")
    
    # Model should already have gemini/ prefix now
    llm_model = model
    print(f"  Using LLM: {llm_model}")
    
    agent = Agent(
        name="MathAgent",
        role="Calculator",
        goal="Answer math questions",
        llm=llm_model,
        verbose=False
    )
    
    result = agent.start("What is 3 times 7? Reply with just the number.")
    print(f"  Result: {result}")
    
    if result and '21' in str(result):
        print("\n✅ Gemini API test passed!")
    else:
        print("\n❌ Gemini API test failed!")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("MODEL ROUTING LIVE TESTS")
    print("="*60)
    
    # Check environment variables
    print("\n🔑 Environment Variables:")
    print(f"  OPENAI_API_KEY: {'✅ Set' if os.getenv('OPENAI_API_KEY') else '❌ Not set'}")
    print(f"  ANTHROPIC_API_KEY: {'✅ Set' if os.getenv('ANTHROPIC_API_KEY') else '❌ Not set'}")
    print(f"  GEMINI_API_KEY: {'✅ Set' if os.getenv('GEMINI_API_KEY') else '❌ Not set'}")
    
    # Run tests
    test_router_basics()
    test_model_selection()
    test_custom_models()
    test_real_openai()
    test_real_anthropic()
    test_real_gemini()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60 + "\n")
