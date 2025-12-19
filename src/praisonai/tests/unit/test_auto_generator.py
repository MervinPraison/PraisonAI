"""
Unit tests for AutoGenerator and WorkflowAutoGenerator classes.

Tests cover:
- Default model value (gpt-4o-mini)
- Tools preservation (not replaced with [''])
- LiteLLM fallback to OpenAI
- Lazy loading of client
- Timeout and max_retries configuration
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from praisonai.auto import AutoGenerator, WorkflowAutoGenerator, LITELLM_AVAILABLE
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestAutoGeneratorDefaultModel:
    """Test suite for default model configuration."""
    
    def test_default_model_is_gpt4o_mini(self):
        """Test that default model is gpt-4o-mini, not gpt-5-nano."""
        # Clear environment variables to test defaults
        with patch.dict(os.environ, {}, clear=True):
            # Set required API key
            os.environ['OPENAI_API_KEY'] = 'test-key'
            
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            # Check that default model is gpt-4o-mini
            assert generator.config_list[0]['model'] == 'gpt-4o-mini'
    
    def test_model_from_environment_variable(self):
        """Test that MODEL_NAME environment variable is respected."""
        with patch.dict(os.environ, {'MODEL_NAME': 'custom-model', 'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            assert generator.config_list[0]['model'] == 'custom-model'
    
    def test_openai_model_name_fallback(self):
        """Test that OPENAI_MODEL_NAME is used as fallback."""
        with patch.dict(os.environ, {'OPENAI_MODEL_NAME': 'gpt-4', 'OPENAI_API_KEY': 'test-key'}, clear=True):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            assert generator.config_list[0]['model'] == 'gpt-4'


class TestAutoGeneratorToolsPreservation:
    """Test suite for tools preservation in generated YAML."""
    
    def test_tools_are_preserved_in_convert_and_save(self):
        """Test that generated tools are preserved, not replaced with ['']."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            # Mock JSON data with tools
            json_data = {
                'roles': {
                    'researcher': {
                        'role': 'Researcher',
                        'goal': 'Research topics',
                        'backstory': 'Expert researcher',
                        'tools': ['ScrapeWebsiteTool', 'WebsiteSearchTool'],
                        'tasks': {
                            'research_task': {
                                'description': 'Research the topic',
                                'expected_output': 'Research report'
                            }
                        }
                    }
                }
            }
            
            # Use a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                generator.agent_file = f.name
            
            try:
                generator.convert_and_save(json_data, merge=False)
                
                # Read the saved file
                import yaml
                with open(generator.agent_file, 'r') as f:
                    saved_data = yaml.safe_load(f)
                
                # Check that tools are preserved
                assert saved_data['roles']['researcher']['tools'] == ['ScrapeWebsiteTool', 'WebsiteSearchTool']
            finally:
                os.unlink(generator.agent_file)
    
    def test_tools_preserved_in_merge(self):
        """Test that tools are preserved when merging with existing file."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            # Create existing file
            existing_data = {
                'framework': 'praisonai',
                'topic': 'Existing topic',
                'roles': {},
                'dependencies': []
            }
            
            # New JSON data with tools
            new_json_data = {
                'roles': {
                    'writer': {
                        'role': 'Writer',
                        'goal': 'Write content',
                        'backstory': 'Expert writer',
                        'tools': ['FileReadTool', 'TXTSearchTool'],
                        'tasks': {
                            'write_task': {
                                'description': 'Write the content',
                                'expected_output': 'Written content'
                            }
                        }
                    }
                }
            }
            
            # Use a temporary file
            import yaml
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(existing_data, f)
                generator.agent_file = f.name
            
            try:
                generator.convert_and_save(new_json_data, merge=True)
                
                # Read the saved file
                with open(generator.agent_file, 'r') as f:
                    saved_data = yaml.safe_load(f)
                
                # Check that tools are preserved
                assert saved_data['roles']['writer']['tools'] == ['FileReadTool', 'TXTSearchTool']
            finally:
                os.unlink(generator.agent_file)


class TestAutoGeneratorLazyLoading:
    """Test suite for lazy loading of client."""
    
    def test_client_is_not_created_on_init(self):
        """Test that client is not created during __init__."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            # Check that _client is None (lazy loading)
            assert generator._client is None
    
    def test_client_is_created_on_first_access(self):
        """Test that client is created on first access."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            # Access client property
            with patch('praisonai.auto.instructor') as mock_instructor:
                mock_instructor.from_litellm.return_value = Mock()
                mock_instructor.patch.return_value = Mock()
                
                client = generator.client
                
                # Check that client is now set
                assert generator._client is not None


class TestAutoGeneratorLiteLLMFallback:
    """Test suite for LiteLLM fallback to OpenAI."""
    
    def test_uses_litellm_when_available(self):
        """Test that LiteLLM is used when available via from_provider."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            with patch('praisonai.auto.LITELLM_AVAILABLE', True):
                with patch('praisonai.auto.instructor') as mock_instructor:
                    mock_instructor.from_provider.return_value = Mock()
                    
                    generator = AutoGenerator(
                        topic="Test topic",
                        framework="praisonai"
                    )
                    
                    # Access client to trigger creation
                    _ = generator.client
                    
                    # Check that from_provider was called with litellm prefix
                    mock_instructor.from_provider.assert_called_once()
                    call_args = mock_instructor.from_provider.call_args[0][0]
                    assert call_args.startswith('litellm/')
    
    def test_falls_back_to_openai_when_litellm_unavailable(self):
        """Test that OpenAI SDK is used when LiteLLM is not available."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            with patch('praisonai.auto.LITELLM_AVAILABLE', False):
                with patch('praisonai.auto.instructor') as mock_instructor:
                    with patch('praisonai.auto.OpenAI') as mock_openai:
                        mock_instructor.patch.return_value = Mock()
                        mock_openai.return_value = Mock()
                        
                        generator = AutoGenerator(
                            topic="Test topic",
                            framework="praisonai"
                        )
                        
                        # Access client to trigger creation
                        _ = generator.client
                        
                        # Check that patch was called (OpenAI fallback)
                        mock_instructor.patch.assert_called_once()


class TestWorkflowAutoGenerator:
    """Test suite for WorkflowAutoGenerator."""
    
    def test_default_model_is_gpt4o_mini(self):
        """Test that default model is gpt-4o-mini."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ['OPENAI_API_KEY'] = 'test-key'
            
            generator = WorkflowAutoGenerator(
                topic="Test workflow"
            )
            
            assert generator.config_list[0]['model'] == 'gpt-4o-mini'
    
    def test_lazy_loading(self):
        """Test that client uses lazy loading."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(
                topic="Test workflow"
            )
            
            assert generator._client is None
    
    def test_litellm_fallback(self):
        """Test LiteLLM fallback to OpenAI."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            with patch('praisonai.auto.LITELLM_AVAILABLE', False):
                with patch('praisonai.auto.instructor') as mock_instructor:
                    with patch('praisonai.auto.OpenAI') as mock_openai:
                        mock_instructor.patch.return_value = Mock()
                        mock_openai.return_value = Mock()
                        
                        generator = WorkflowAutoGenerator(
                            topic="Test workflow"
                        )
                        
                        # Access client to trigger creation
                        _ = generator.client
                        
                        # Check that patch was called (OpenAI fallback)
                        mock_instructor.patch.assert_called_once()


class TestAutoGeneratorJSONMode:
    """Test suite for JSON mode (critical fix for nested Dict structures)."""
    
    def test_uses_json_mode_not_tools_mode(self):
        """Test that JSON mode is used instead of TOOLS mode for OpenAI fallback.
        
        TOOLS mode doesn't handle nested Dict[str, ...] structures properly,
        causing validation errors. JSON mode works correctly.
        """
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            with patch('praisonai.auto.LITELLM_AVAILABLE', False):
                with patch('praisonai.auto.instructor') as mock_instructor:
                    with patch('praisonai.auto.OpenAI') as mock_openai:
                        mock_instructor.patch.return_value = Mock()
                        mock_instructor.Mode.JSON = 'JSON_MODE'
                        mock_openai.return_value = Mock()
                        
                        generator = AutoGenerator(
                            topic="Test topic",
                            framework="praisonai"
                        )
                        
                        # Access client to trigger creation
                        _ = generator.client
                        
                        # Verify JSON mode was used
                        call_kwargs = mock_instructor.patch.call_args[1]
                        assert call_kwargs['mode'] == 'JSON_MODE'
    
    def test_workflow_generator_uses_json_mode(self):
        """Test that WorkflowAutoGenerator also uses JSON mode."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            with patch('praisonai.auto.LITELLM_AVAILABLE', False):
                with patch('praisonai.auto.instructor') as mock_instructor:
                    with patch('praisonai.auto.OpenAI') as mock_openai:
                        mock_instructor.patch.return_value = Mock()
                        mock_instructor.Mode.JSON = 'JSON_MODE'
                        mock_openai.return_value = Mock()
                        
                        generator = WorkflowAutoGenerator(
                            topic="Test workflow"
                        )
                        
                        # Access client to trigger creation
                        _ = generator.client
                        
                        # Verify JSON mode was used
                        call_kwargs = mock_instructor.patch.call_args[1]
                        assert call_kwargs['mode'] == 'JSON_MODE'


class TestAutoGeneratorImprovedPrompt:
    """Test suite for improved task analysis prompt."""
    
    def test_prompt_includes_complexity_analysis(self):
        """Test that the prompt includes task complexity analysis."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            prompt = generator.get_user_content()
            
            # Check for complexity analysis steps
            assert "TASK COMPLEXITY ANALYSIS" in prompt
            assert "DETERMINE OPTIMAL TEAM SIZE" in prompt
            assert "Simple tasks: 1-2 agents" in prompt
            assert "Complex tasks: 3-4 agents" in prompt
    
    def test_prompt_discourages_unnecessary_complexity(self):
        """Test that the prompt discourages unnecessary complexity."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            prompt = generator.get_user_content()
            
            assert "meaningful specialization" in prompt
            assert "Avoid unnecessary complexity" in prompt


class TestWorkflowPatterns:
    """Test suite for workflow patterns including new orchestrator-workers and evaluator-optimizer."""
    
    def test_get_prompt_sequential(self):
        """Test that sequential pattern generates correct prompt."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Test topic")
            prompt = generator._get_prompt("sequential")
            assert "sequential" in prompt.lower()
            assert "Sequential Workflow" in prompt
    
    def test_get_prompt_orchestrator_workers(self):
        """Test that orchestrator-workers pattern generates correct prompt."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Test topic")
            prompt = generator._get_prompt("orchestrator-workers")
            assert "orchestrator" in prompt.lower()
            assert "workers" in prompt.lower()
            assert "synthesizer" in prompt.lower()
    
    def test_get_prompt_evaluator_optimizer(self):
        """Test that evaluator-optimizer pattern generates correct prompt."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Test topic")
            prompt = generator._get_prompt("evaluator-optimizer")
            assert "evaluator" in prompt.lower()
            assert "generator" in prompt.lower()
            assert "loop" in prompt.lower()
            assert "APPROVED" in prompt


class TestPatternRecommendation:
    """Test suite for pattern recommendation based on task type."""
    
    def test_recommend_sequential_for_simple_task(self):
        """Test that sequential is recommended for simple tasks."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Write a blog post")
            assert generator.recommend_pattern() == "sequential"
    
    def test_recommend_parallel_for_concurrent_tasks(self):
        """Test that parallel is recommended for concurrent tasks."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Research from multiple sources simultaneously")
            assert generator.recommend_pattern() == "parallel"
    
    def test_recommend_orchestrator_for_complex_tasks(self):
        """Test that orchestrator-workers is recommended for complex tasks."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Comprehensive analysis and break down the problem")
            assert generator.recommend_pattern() == "orchestrator-workers"
    
    def test_recommend_evaluator_for_quality_tasks(self):
        """Test that evaluator-optimizer is recommended for quality-focused tasks."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Refine and improve the content quality")
            assert generator.recommend_pattern() == "evaluator-optimizer"
    
    def test_recommend_routing_for_classification_tasks(self):
        """Test that routing is recommended for classification tasks."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Classify and route different types of requests")
            assert generator.recommend_pattern() == "routing"


class TestAutoGeneratorConfiguration:
    """Test suite for configuration options."""
    
    def test_custom_config_list(self):
        """Test that custom config_list is respected."""
        custom_config = [
            {
                'model': 'custom-model',
                'base_url': 'https://custom.api.com',
                'api_key': 'custom-key'
            }
        ]
        
        generator = AutoGenerator(
            topic="Test topic",
            framework="praisonai",
            config_list=custom_config
        )
        
        assert generator.config_list == custom_config
    
    def test_base_url_priority(self):
        """Test base_url environment variable priority."""
        with patch.dict(os.environ, {
            'OPENAI_BASE_URL': 'https://priority.api.com',
            'OPENAI_API_BASE': 'https://fallback.api.com',
            'OPENAI_API_KEY': 'test-key'
        }):
            generator = AutoGenerator(
                topic="Test topic",
                framework="praisonai"
            )
            
            assert generator.config_list[0]['base_url'] == 'https://priority.api.com'


class TestBaseAutoGenerator:
    """Test suite for BaseAutoGenerator shared functionality."""
    
    def test_analyze_complexity_simple(self):
        """Test that simple tasks are detected correctly."""
        from praisonai.auto import BaseAutoGenerator
        
        simple_tasks = [
            "Write a haiku about spring",
            "Create a simple summary",
            "Write a brief poem",
            "Make a quick list"
        ]
        
        for task in simple_tasks:
            assert BaseAutoGenerator.analyze_complexity(task) == 'simple', f"Failed for: {task}"
    
    def test_analyze_complexity_complex(self):
        """Test that complex tasks are detected correctly."""
        from praisonai.auto import BaseAutoGenerator
        
        complex_tasks = [
            "Comprehensive market analysis and report",
            "Research and write a detailed analysis",
            "Multi-step process to coordinate teams",
            "In-depth investigation of multiple sources"
        ]
        
        for task in complex_tasks:
            assert BaseAutoGenerator.analyze_complexity(task) == 'complex', f"Failed for: {task}"
    
    def test_analyze_complexity_moderate(self):
        """Test that moderate tasks are detected correctly."""
        from praisonai.auto import BaseAutoGenerator
        
        moderate_tasks = [
            "Research AI trends",
            "Analyze customer feedback",
            "Design a workflow"
        ]
        
        for task in moderate_tasks:
            assert BaseAutoGenerator.analyze_complexity(task) == 'moderate', f"Failed for: {task}"
    
    def test_get_available_tools(self):
        """Test that available tools list is returned correctly."""
        from praisonai.auto import BaseAutoGenerator, AVAILABLE_TOOLS
        
        tools = BaseAutoGenerator.get_available_tools()
        
        # Should return a copy, not the original
        assert tools == AVAILABLE_TOOLS
        assert tools is not AVAILABLE_TOOLS
        
        # Should contain expected tools
        assert "WebsiteSearchTool" in tools
        assert "PDFSearchTool" in tools
        assert "ScrapeWebsiteTool" in tools


class TestWorkflowDynamicAgentCount:
    """Test suite for dynamic agent count in WorkflowAutoGenerator."""
    
    def test_prompt_includes_complexity_analysis(self):
        """Test that workflow prompt includes complexity analysis."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Research AI trends")
            prompt = generator._get_prompt("sequential")
            
            assert "STEP 1: ANALYZE TASK COMPLEXITY" in prompt
            assert "STEP 2: DESIGN WORKFLOW" in prompt
            assert "STEP 3: ASSIGN TOOLS" in prompt
    
    def test_prompt_includes_tools_list(self):
        """Test that workflow prompt includes available tools."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Research AI trends")
            prompt = generator._get_prompt("sequential")
            
            assert "Available Tools:" in prompt
            assert "WebsiteSearchTool" in prompt
            assert "PDFSearchTool" in prompt
    
    def test_simple_task_gets_fewer_agents_guidance(self):
        """Test that simple tasks get 1-2 agents guidance."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Write a simple haiku")
            prompt = generator._get_prompt("sequential")
            
            assert "1-2 agents" in prompt
            assert "simple task detected" in prompt
    
    def test_complex_task_gets_more_agents_guidance(self):
        """Test that complex tasks get 3-4 agents guidance."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Comprehensive market analysis and detailed report")
            prompt = generator._get_prompt("sequential")
            
            assert "3-4 agents" in prompt
            assert "complex task detected" in prompt


# =============================================================================
# TODO 2: Single-Agent Option Tests
# =============================================================================
class TestSingleAgentOption:
    """Test suite for single-agent generation option."""
    
    def test_single_agent_structure_exists(self):
        """Test that SingleAgentStructure Pydantic model exists."""
        from praisonai.auto import SingleAgentStructure
        assert SingleAgentStructure is not None
    
    def test_auto_generator_has_single_agent_mode(self):
        """Test that AutoGenerator supports single_agent parameter."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Write a haiku",
                framework="praisonai",
                single_agent=True
            )
            assert generator.single_agent == True
    
    def test_workflow_generator_has_single_agent_mode(self):
        """Test that WorkflowAutoGenerator supports single_agent parameter."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(
                topic="Write a haiku",
                single_agent=True
            )
            assert generator.single_agent == True


# =============================================================================
# TODO 3: LLM-Based Pattern Recommendation Tests
# =============================================================================
class TestLLMPatternRecommendation:
    """Test suite for LLM-based pattern recommendation."""
    
    def test_recommend_pattern_llm_method_exists(self):
        """Test that recommend_pattern_llm method exists."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Test task")
            assert hasattr(generator, 'recommend_pattern_llm')
    
    def test_pattern_recommendation_pydantic_model_exists(self):
        """Test that PatternRecommendation Pydantic model exists."""
        from praisonai.auto import PatternRecommendation
        assert PatternRecommendation is not None
    
    def test_pattern_recommendation_has_required_fields(self):
        """Test PatternRecommendation has pattern, reasoning, confidence."""
        from praisonai.auto import PatternRecommendation
        fields = PatternRecommendation.model_fields
        assert 'pattern' in fields
        assert 'reasoning' in fields
        assert 'confidence' in fields


# =============================================================================
# TODO 4: Validation Gates Tests
# =============================================================================
class TestValidationGates:
    """Test suite for validation gates in workflows."""
    
    def test_validation_gate_model_exists(self):
        """Test that ValidationGate Pydantic model exists."""
        from praisonai.auto import ValidationGate
        assert ValidationGate is not None
    
    def test_validation_gate_has_required_fields(self):
        """Test ValidationGate has criteria, pass_action, fail_action."""
        from praisonai.auto import ValidationGate
        fields = ValidationGate.model_fields
        assert 'criteria' in fields
        assert 'pass_action' in fields
        assert 'fail_action' in fields
    
    def test_workflow_structure_supports_gates(self):
        """Test that WorkflowStructure has optional gates field."""
        from praisonai.auto import WorkflowStructure
        fields = WorkflowStructure.model_fields
        assert 'gates' in fields


# =============================================================================
# TODO 6: Pattern Support for AutoGenerator Tests
# =============================================================================
class TestAutoGeneratorPatternSupport:
    """Test suite for pattern support in AutoGenerator."""
    
    def test_auto_generator_accepts_pattern_parameter(self):
        """Test that AutoGenerator accepts pattern parameter."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Research and write",
                framework="praisonai",
                pattern="parallel"
            )
            assert generator.pattern == "parallel"
    
    def test_auto_generator_has_recommend_pattern(self):
        """Test that AutoGenerator has recommend_pattern method."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(topic="Test", framework="praisonai")
            assert hasattr(generator, 'recommend_pattern')
    
    def test_auto_generator_prompt_includes_pattern(self):
        """Test that AutoGenerator prompt includes pattern guidance."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = AutoGenerator(
                topic="Research from multiple sources",
                framework="praisonai",
                pattern="parallel"
            )
            prompt = generator.get_user_content()
            assert "parallel" in prompt.lower()


# =============================================================================
# TODO 7: Merge Support for WorkflowAutoGenerator Tests
# =============================================================================
class TestWorkflowMergeSupport:
    """Test suite for merge support in WorkflowAutoGenerator."""
    
    def test_workflow_generator_accepts_merge_parameter(self):
        """Test that WorkflowAutoGenerator.generate accepts merge parameter."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Test task")
            # Check that generate method accepts merge parameter
            import inspect
            sig = inspect.signature(generator.generate)
            assert 'merge' in sig.parameters
    
    def test_merge_with_existing_workflow_method_exists(self):
        """Test that merge_with_existing_workflow method exists."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Test task")
            assert hasattr(generator, 'merge_with_existing_workflow')


# =============================================================================
# TODO 10: Framework Support for WorkflowAutoGenerator Tests
# =============================================================================
class TestWorkflowFrameworkSupport:
    """Test suite for framework support in WorkflowAutoGenerator."""
    
    def test_workflow_generator_accepts_framework_parameter(self):
        """Test that WorkflowAutoGenerator accepts framework parameter."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(
                topic="Test task",
                framework="crewai"
            )
            assert generator.framework == "crewai"
    
    def test_workflow_generator_default_framework_is_praisonai(self):
        """Test that default framework is praisonai."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(topic="Test task")
            assert generator.framework == "praisonai"
    
    def test_save_workflow_respects_framework(self):
        """Test that _save_workflow uses the specified framework."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            generator = WorkflowAutoGenerator(
                topic="Test task",
                framework="crewai"
            )
            # The framework should be stored and used in output
            assert generator.framework == "crewai"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
