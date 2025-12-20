"""
Integration tests for AutoGenerator and WorkflowAutoGenerator.

These tests require a real OpenAI API key and make actual API calls.
Run with: OPENAI_API_KEY=your-key pytest tests/integration/test_auto_generator_integration.py -v
"""

import pytest
import os
import sys
import tempfile
import yaml

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Skip if no API key or using test/invalid key
# Valid OpenAI keys start with 'sk-' and are typically 51+ characters
api_key = os.environ.get('OPENAI_API_KEY', '')
is_test_key = (
    not api_key or 
    'test' in api_key.lower() or 
    not api_key.startswith('sk-') or 
    len(api_key) < 40
)
if is_test_key:
    pytest.skip("OPENAI_API_KEY not set or using test/invalid key", allow_module_level=True)

try:
    from praisonai.auto import AutoGenerator, WorkflowAutoGenerator
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestAutoGeneratorIntegration:
    """Integration tests for AutoGenerator with real API calls."""
    
    @pytest.mark.integration
    def test_generate_agents_yaml(self):
        """Test generating agents.yaml with real API call."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            agent_file = f.name
        
        try:
            generator = AutoGenerator(
                topic="Create a simple greeting bot",
                agent_file=agent_file,
                framework="praisonai"
            )
            
            result_path = generator.generate()
            
            # Verify file was created
            assert os.path.exists(result_path)
            
            # Verify file content
            with open(result_path, 'r') as f:
                data = yaml.safe_load(f)
            
            # Check structure
            assert 'framework' in data
            assert 'topic' in data
            assert 'roles' in data
            assert len(data['roles']) > 0
            
            # Check that tools are preserved (not empty list)
            for role_id, role_data in data['roles'].items():
                assert 'tools' in role_data
                # Tools should be a list (may be empty if LLM didn't suggest any)
                assert isinstance(role_data['tools'], list)
                
            print(f"✓ Generated agents.yaml successfully")
            print(f"  Roles: {list(data['roles'].keys())}")
            
        finally:
            if os.path.exists(agent_file):
                os.unlink(agent_file)
    
    @pytest.mark.integration
    def test_generate_with_merge(self):
        """Test generating and merging agents."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            agent_file = f.name
        
        try:
            # First generation
            generator1 = AutoGenerator(
                topic="Create a researcher",
                agent_file=agent_file,
                framework="praisonai"
            )
            generator1.generate()
            
            # Second generation with merge
            generator2 = AutoGenerator(
                topic="Create a writer",
                agent_file=agent_file,
                framework="praisonai"
            )
            generator2.generate(merge=True)
            
            # Verify merged content
            with open(agent_file, 'r') as f:
                data = yaml.safe_load(f)
            
            # Should have roles from both generations
            assert len(data['roles']) >= 2
            
            print(f"✓ Merged agents.yaml successfully")
            print(f"  Total roles: {len(data['roles'])}")
            
        finally:
            if os.path.exists(agent_file):
                os.unlink(agent_file)


class TestWorkflowAutoGeneratorIntegration:
    """Integration tests for WorkflowAutoGenerator with real API calls."""
    
    @pytest.mark.integration
    def test_generate_sequential_workflow(self):
        """Test generating sequential workflow."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            workflow_file = f.name
        
        try:
            generator = WorkflowAutoGenerator(
                topic="Research and summarize AI news",
                workflow_file=workflow_file
            )
            
            result_path = generator.generate(pattern="sequential")
            
            # Verify file was created
            assert os.path.exists(result_path)
            
            # Verify file content
            with open(result_path, 'r') as f:
                data = yaml.safe_load(f)
            
            # Check structure
            assert 'name' in data
            assert 'agents' in data
            assert 'steps' in data
            assert len(data['agents']) > 0
            assert len(data['steps']) > 0
            
            print(f"✓ Generated sequential workflow successfully")
            print(f"  Agents: {list(data['agents'].keys())}")
            print(f"  Steps: {len(data['steps'])}")
            
        finally:
            if os.path.exists(workflow_file):
                os.unlink(workflow_file)
    
    @pytest.mark.integration
    def test_generate_parallel_workflow(self):
        """Test generating parallel workflow."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            workflow_file = f.name
        
        try:
            generator = WorkflowAutoGenerator(
                topic="Multi-source research on climate change",
                workflow_file=workflow_file
            )
            
            result_path = generator.generate(pattern="parallel")
            
            # Verify file was created
            assert os.path.exists(result_path)
            
            # Verify file content
            with open(result_path, 'r') as f:
                data = yaml.safe_load(f)
            
            # Check structure
            assert 'agents' in data
            assert 'steps' in data
            
            print(f"✓ Generated parallel workflow successfully")
            print(f"  Agents: {list(data['agents'].keys())}")
            
        finally:
            if os.path.exists(workflow_file):
                os.unlink(workflow_file)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])
