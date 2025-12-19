"""
Unit tests for Model Routing features.

Tests cover:
1. Model config parsing from agents.yaml/workflow.yaml
2. Per-agent LLM field support
3. Unified CLI Router with ModelRouter
4. Custom model profiles

TDD approach - tests written before implementation.
"""

import pytest
import yaml
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# =============================================================================
# Feature 1: Model Config in YAML
# =============================================================================

class TestModelConfigParsing:
    """Tests for parsing 'models' section from agents.yaml/workflow.yaml."""
    
    def test_parse_models_section_basic(self):
        """Test parsing basic models configuration from YAML."""
        yaml_content = """
name: Test Workflow
description: Test workflow with custom models

models:
  gpt-4o-mini:
    provider: openai
    complexity: [simple, moderate]
    cost_per_1k: 0.00075
    capabilities: [text, function-calling]

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics

steps:
  - agent: researcher
    action: "Research: {{input}}"
"""
        config = yaml.safe_load(yaml_content)
        
        # Verify models section exists
        assert 'models' in config
        assert 'gpt-4o-mini' in config['models']
        
        model_config = config['models']['gpt-4o-mini']
        assert model_config['provider'] == 'openai'
        assert model_config['complexity'] == ['simple', 'moderate']
        assert model_config['cost_per_1k'] == 0.00075
        assert 'text' in model_config['capabilities']
    
    def test_parse_multiple_models(self):
        """Test parsing multiple model configurations."""
        yaml_content = """
models:
  gpt-4o-mini:
    provider: openai
    complexity: [simple, moderate]
    cost_per_1k: 0.00075
    capabilities: [text, function-calling]
  
  claude-3-5-sonnet:
    provider: anthropic
    complexity: [moderate, complex, very_complex]
    cost_per_1k: 0.009
    capabilities: [text, vision, function-calling]
  
  custom-openrouter-model:
    provider: openrouter
    complexity: [moderate, complex]
    cost_per_1k: 0.001
    capabilities: [text]
    context_window: 32000

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
"""
        config = yaml.safe_load(yaml_content)
        
        assert len(config['models']) == 3
        assert 'gpt-4o-mini' in config['models']
        assert 'claude-3-5-sonnet' in config['models']
        assert 'custom-openrouter-model' in config['models']
        
        # Verify custom model has context_window
        custom_model = config['models']['custom-openrouter-model']
        assert custom_model.get('context_window') == 32000
    
    def test_parse_model_with_all_fields(self):
        """Test parsing model with all optional fields."""
        yaml_content = """
models:
  full-model:
    provider: openai
    complexity: [simple, moderate, complex]
    cost_per_1k: 0.005
    capabilities: [text, vision, function-calling, streaming]
    context_window: 128000
    supports_tools: true
    supports_streaming: true
    strengths: [reasoning, code-generation, analysis]
"""
        config = yaml.safe_load(yaml_content)
        
        model = config['models']['full-model']
        assert model['provider'] == 'openai'
        assert model['context_window'] == 128000
        assert model['supports_tools'] is True
        assert model['supports_streaming'] is True
        assert 'reasoning' in model['strengths']
    
    def test_models_section_optional(self):
        """Test that models section is optional - backward compatibility."""
        yaml_content = """
name: Simple Workflow

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics

steps:
  - agent: researcher
    action: "Research: {{input}}"
"""
        config = yaml.safe_load(yaml_content)
        
        # models section should not exist
        assert 'models' not in config or config.get('models') is None
        # But agents should still work
        assert 'agents' in config


class TestModelConfigToModelProfile:
    """Tests for converting YAML model config to ModelProfile objects."""
    
    def test_convert_yaml_to_model_profile(self):
        """Test converting YAML model config to ModelProfile."""
        from praisonai.cli.features.router import RouterHandler
        
        yaml_model_config = {
            'provider': 'openai',
            'complexity': ['simple', 'moderate'],
            'cost_per_1k': 0.00075,
            'capabilities': ['text', 'function-calling'],
            'context_window': 128000,
            'supports_tools': True,
            'strengths': ['speed', 'cost-effective']
        }
        
        handler = RouterHandler()
        profile = handler.yaml_to_model_profile('gpt-4o-mini', yaml_model_config)
        
        assert profile is not None
        assert profile.name == 'gpt-4o-mini'
        assert profile.provider == 'openai'
        assert profile.cost_per_1k_tokens == 0.00075
        assert profile.context_window == 128000
    
    def test_convert_complexity_strings_to_enum(self):
        """Test converting complexity strings to TaskComplexity enum."""
        from praisonai.cli.features.router import RouterHandler
        
        yaml_model_config = {
            'provider': 'anthropic',
            'complexity': ['moderate', 'complex', 'very_complex'],
            'cost_per_1k': 0.009,
            'capabilities': ['text']
        }
        
        handler = RouterHandler()
        profile = handler.yaml_to_model_profile('claude-3-5-sonnet', yaml_model_config)
        
        # Complexity range should be (MODERATE, VERY_COMPLEX)
        min_complexity, max_complexity = profile.complexity_range
        assert min_complexity.value == 2  # MODERATE
        assert max_complexity.value == 4  # VERY_COMPLEX


class TestRouterWithCustomModels:
    """Tests for RouterHandler using custom models from YAML."""
    
    def test_router_loads_custom_models(self):
        """Test that router loads custom models from YAML config."""
        from praisonai.cli.features.router import RouterHandler
        
        models_config = {
            'my-custom-model': {
                'provider': 'openrouter',
                'complexity': ['simple', 'moderate'],
                'cost_per_1k': 0.001,
                'capabilities': ['text', 'function-calling']
            }
        }
        
        handler = RouterHandler()
        handler.load_models_from_config(models_config)
        
        # Custom model should be available
        assert 'my-custom-model' in handler.get_available_models()
    
    def test_router_selects_custom_model(self):
        """Test that router can select custom model based on complexity."""
        from praisonai.cli.features.router import RouterHandler
        
        models_config = {
            'cheap-model': {
                'provider': 'custom',
                'complexity': ['simple'],
                'cost_per_1k': 0.0001,
                'capabilities': ['text']
            },
            'expensive-model': {
                'provider': 'custom',
                'complexity': ['complex', 'very_complex'],
                'cost_per_1k': 0.05,
                'capabilities': ['text', 'function-calling']
            }
        }
        
        handler = RouterHandler()
        handler.load_models_from_config(models_config)
        
        # Simple task should select cheap model
        simple_model = handler.select_model("What is 2+2?")
        assert simple_model == 'cheap-model'
        
        # Complex task should select expensive model
        complex_model = handler.select_model(
            "Analyze the comprehensive impact of quantum computing on cybersecurity"
        )
        assert complex_model == 'expensive-model'
    
    def test_router_merges_with_default_models(self):
        """Test that custom models merge with default models."""
        from praisonai.cli.features.router import RouterHandler
        
        models_config = {
            'my-custom-model': {
                'provider': 'openrouter',
                'complexity': ['moderate'],
                'cost_per_1k': 0.002,
                'capabilities': ['text']
            }
        }
        
        handler = RouterHandler()
        handler.load_models_from_config(models_config, merge_with_defaults=True)
        
        available = handler.get_available_models()
        
        # Should have both custom and default models
        assert 'my-custom-model' in available
        assert 'gpt-4o-mini' in available  # Default model


# =============================================================================
# Feature 2: Per-Agent LLM Field
# =============================================================================

class TestPerAgentLLM:
    """Tests for per-agent LLM configuration in YAML."""
    
    def test_parse_agent_with_llm_field(self):
        """Test parsing agent with explicit llm field."""
        yaml_content = """
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    llm: gpt-4o
    
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    llm: claude-3-5-sonnet-20241022
"""
        config = yaml.safe_load(yaml_content)
        
        assert config['agents']['researcher']['llm'] == 'gpt-4o'
        assert config['agents']['writer']['llm'] == 'claude-3-5-sonnet-20241022'
    
    def test_parse_agent_with_llm_routing(self):
        """Test parsing agent with llm_routing strategy."""
        yaml_content = """
agents:
  smart_agent:
    name: Smart Agent
    role: Adaptive Assistant
    goal: Handle various tasks
    llm_routing: auto
    llm_models:
      - gpt-4o-mini
      - gpt-4o
      - claude-3-5-sonnet-20241022
"""
        config = yaml.safe_load(yaml_content)
        
        agent = config['agents']['smart_agent']
        assert agent['llm_routing'] == 'auto'
        assert len(agent['llm_models']) == 3
    
    def test_agent_llm_defaults_when_not_specified(self):
        """Test that agent uses default LLM when not specified."""
        yaml_content = """
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    # No llm field - should use default
"""
        config = yaml.safe_load(yaml_content)
        
        # llm field should not exist
        assert 'llm' not in config['agents']['researcher']
    
    def test_agent_llm_with_provider_prefix(self):
        """Test parsing agent LLM with provider/model format."""
        yaml_content = """
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    llm: openrouter/anthropic/claude-3-5-sonnet
"""
        config = yaml.safe_load(yaml_content)
        
        assert config['agents']['researcher']['llm'] == 'openrouter/anthropic/claude-3-5-sonnet'


class TestAgentCreationWithLLM:
    """Tests for creating Agent objects with LLM from YAML config."""
    
    def test_create_agent_with_custom_llm(self):
        """Test that Agent config with custom LLM is properly parsed."""
        agent_config = {
            'name': 'Researcher',
            'role': 'Research Analyst',
            'goal': 'Research topics',
            'llm': 'gpt-4o'
        }
        
        # This tests the parsing logic, not actual agent creation
        llm_value = agent_config.get('llm', 'gpt-4o-mini')
        assert llm_value == 'gpt-4o'
    
    def test_agent_config_with_routing_strategy(self):
        """Test agent config with routing strategy is properly structured."""
        agent_config = {
            'name': 'Smart Agent',
            'role': 'Adaptive Assistant',
            'goal': 'Handle various tasks',
            'llm_routing': 'cost-optimized',
            'llm_models': ['gpt-4o-mini', 'gpt-4o', 'claude-3-5-sonnet-20241022']
        }
        
        # Verify structure
        assert agent_config['llm_routing'] == 'cost-optimized'
        assert isinstance(agent_config['llm_models'], list)
        assert len(agent_config['llm_models']) == 3


# =============================================================================
# Feature 3: Unified CLI Router with ModelRouter
# =============================================================================

class TestUnifiedRouter:
    """Tests for unified RouterHandler that uses ModelRouter internally."""
    
    def test_router_handler_uses_model_router(self):
        """Test that RouterHandler uses ModelRouter for selection."""
        from praisonai.cli.features.router import RouterHandler
        
        handler = RouterHandler()
        
        # Should have internal model_router
        assert hasattr(handler, 'model_router') or hasattr(handler, '_model_router')
    
    def test_router_complexity_analysis_matches(self):
        """Test that complexity analysis is consistent."""
        from praisonai.cli.features.router import RouterHandler
        
        handler = RouterHandler()
        
        # Simple prompts
        assert handler.analyze_complexity("What is 2+2?") == 'simple'
        assert handler.analyze_complexity("Define photosynthesis") == 'simple'
        
        # Complex prompts
        assert handler.analyze_complexity(
            "Analyze and research the comprehensive impact of AI on healthcare"
        ) == 'complex'
    
    def test_router_cost_threshold(self):
        """Test router respects cost threshold."""
        from praisonai.cli.features.router import RouterHandler
        
        handler = RouterHandler()
        handler.set_cost_threshold(0.001)  # Max $0.001 per 1k tokens
        
        # Should only select cheap models
        model = handler.select_model("Complex analysis task")
        
        # Model should be within cost threshold
        model_cost = handler.get_model_cost(model)
        assert model_cost <= 0.001
    
    def test_router_provider_preference(self):
        """Test router respects provider preference."""
        from praisonai.cli.features.router import RouterHandler
        
        handler = RouterHandler()
        
        # Prefer Anthropic
        model = handler.select_model(
            "Write a detailed analysis",
            preferred_provider='anthropic'
        )
        
        assert 'claude' in model.lower()


class TestRouterIntegrationWithWorkflow:
    """Tests for router integration with workflow execution."""
    
    def test_workflow_uses_models_config(self):
        """Test that workflow uses models config for routing."""
        yaml_content = """
name: Routing Workflow

models:
  fast-model:
    provider: openai
    complexity: [simple]
    cost_per_1k: 0.0001
    capabilities: [text]
  
  smart-model:
    provider: anthropic
    complexity: [complex, very_complex]
    cost_per_1k: 0.01
    capabilities: [text, function-calling]

workflow:
  verbose: true
  router: true  # Enable model routing

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    llm_routing: auto  # Use auto-routing with models config
"""
        config = yaml.safe_load(yaml_content)
        
        # Verify workflow has router enabled
        assert config['workflow'].get('router') is True
        
        # Verify agent has routing enabled
        assert config['agents']['researcher']['llm_routing'] == 'auto'
        
        # Verify models are defined
        assert 'fast-model' in config['models']
        assert 'smart-model' in config['models']


# =============================================================================
# Integration Tests
# =============================================================================

class TestEndToEndModelRouting:
    """End-to-end tests for model routing feature."""
    
    def test_full_yaml_with_model_routing(self):
        """Test complete YAML with all model routing features."""
        yaml_content = """
name: Full Model Routing Workflow
description: Demonstrates all model routing features

# Custom models configuration
models:
  cheap-fast:
    provider: openai
    complexity: [simple]
    cost_per_1k: 0.0001
    capabilities: [text]
    context_window: 16000
  
  balanced:
    provider: openai
    complexity: [moderate]
    cost_per_1k: 0.001
    capabilities: [text, function-calling]
    context_window: 128000
  
  premium:
    provider: anthropic
    complexity: [complex, very_complex]
    cost_per_1k: 0.015
    capabilities: [text, vision, function-calling]
    context_window: 200000
    strengths: [reasoning, analysis, code-generation]

workflow:
  verbose: true
  router: true
  routing_strategy: cost-optimized

agents:
  classifier:
    name: Classifier
    role: Request Classifier
    goal: Classify incoming requests
    llm: cheap-fast  # Always use cheap model for classification
  
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics thoroughly
    llm_routing: auto  # Auto-select based on task
    llm_models: [balanced, premium]
  
  writer:
    name: Writer
    role: Content Writer
    goal: Write high-quality content
    llm: premium  # Always use premium for writing

steps:
  - agent: classifier
    action: "Classify: {{input}}"
    
  - name: routing
    route:
      simple: [researcher]
      complex: [researcher, writer]
      default: [researcher]
"""
        config = yaml.safe_load(yaml_content)
        
        # Verify complete structure
        assert 'models' in config
        assert len(config['models']) == 3
        
        assert 'workflow' in config
        assert config['workflow']['router'] is True
        assert config['workflow']['routing_strategy'] == 'cost-optimized'
        
        assert 'agents' in config
        assert config['agents']['classifier']['llm'] == 'cheap-fast'
        assert config['agents']['researcher']['llm_routing'] == 'auto'
        assert config['agents']['writer']['llm'] == 'premium'
        
        assert 'steps' in config
        assert len(config['steps']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
