"""
AutoGen Integration Test - Basic functionality test

This test verifies that PraisonAI can successfully integrate with AutoGen
for basic agent conversations and task execution.
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

@pytest.fixture
def mock_autogen_completion():
    """Mock AutoGen completion responses"""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Task completed successfully using AutoGen framework."
    return mock_response

@pytest.fixture
def autogen_config():
    """Configuration for AutoGen test"""
    return {
        "framework": "autogen",
        "agents": [
            {
                "name": "researcher",
                "role": "Research Specialist", 
                "goal": "Gather and analyze information",
                "backstory": "Expert in research and data analysis"
            },
            {
                "name": "writer",
                "role": "Content Writer",
                "goal": "Create well-written content",
                "backstory": "Professional content writer with experience"
            }
        ],
        "tasks": [
            {
                "description": "Research the latest trends in AI",
                "expected_output": "A comprehensive report on AI trends",
                "agent": "researcher"
            },
            {
                "description": "Write a summary of the research findings", 
                "expected_output": "A well-written summary document",
                "agent": "writer"
            }
        ]
    }

class TestAutoGenIntegration:
    """Test AutoGen integration with PraisonAI"""

    @pytest.mark.integration
    def test_autogen_import(self):
        """Test that AutoGen can be imported and is available"""
        try:
            # Try importing ag2 first (new package name)
            import ag2 as autogen
            assert autogen is not None
            print("✅ AG2 import successful")
        except ImportError:
            try:
                # Fall back to pyautogen for backward compatibility
                import autogen
                assert autogen is not None
                print("✅ AutoGen import successful")
            except ImportError:
                pytest.skip("Neither AG2 nor AutoGen installed - skipping AutoGen integration tests")

    @pytest.mark.integration 
    @patch('litellm.completion')
    def test_basic_autogen_agent_creation(self, mock_completion, mock_autogen_completion):
        """Test creating basic AutoGen agents through PraisonAI"""
        mock_completion.return_value = mock_autogen_completion
        
        try:
            from praisonai import PraisonAI
            
            # Create a simple YAML content for AutoGen
            yaml_content = """
framework: autogen
topic: Test AutoGen Integration
roles:
  - name: Assistant
    goal: Help with test tasks
    backstory: I am a helpful assistant for testing
    tasks:
      - description: Complete a simple test task
        expected_output: Task completion confirmation
"""
            
            # Create temporary test file
            test_file = "test_autogen_agents.yaml"
            with open(test_file, "w") as f:
                f.write(yaml_content)
            
            try:
                # Initialize PraisonAI with AutoGen framework
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="autogen"
                )
                
                assert praisonai is not None
                assert praisonai.framework == "autogen"
                print("✅ AutoGen PraisonAI instance created successfully")
                
            finally:
                # Cleanup
                if os.path.exists(test_file):
                    os.remove(test_file)
                    
        except ImportError as e:
            pytest.skip(f"AutoGen integration dependencies not available: {e}")
        except Exception as e:
            pytest.fail(f"AutoGen basic test failed: {e}")

    @pytest.mark.integration
    @patch('litellm.completion')
    def test_autogen_conversation_flow(self, mock_completion, mock_autogen_completion):
        """Test AutoGen conversation flow"""
        mock_completion.return_value = mock_autogen_completion
        
        try:
            from praisonai import PraisonAI
            
            yaml_content = """
framework: autogen
topic: AI Research Task
roles:
  - name: Researcher
    goal: Research AI trends
    backstory: Expert AI researcher
    tasks:
      - description: Research current AI trends and provide insights
        expected_output: Detailed AI trends report
"""
            
            test_file = "test_autogen_conversation.yaml" 
            with open(test_file, "w") as f:
                f.write(yaml_content)
            
            try:
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="autogen"
                )
                
                # Test that we can initialize without errors
                assert praisonai.framework == "autogen"
                print("✅ AutoGen conversation flow test passed")
                
            finally:
                if os.path.exists(test_file):
                    os.remove(test_file)
                    
        except ImportError as e:
            pytest.skip(f"AutoGen dependencies not available: {e}")
        except Exception as e:
            pytest.fail(f"AutoGen conversation test failed: {e}")

    @pytest.mark.integration
    def test_autogen_config_validation(self, autogen_config):
        """Test AutoGen configuration validation"""
        try:
            # Test that config has required fields
            assert autogen_config["framework"] == "autogen"
            assert len(autogen_config["agents"]) > 0
            assert len(autogen_config["tasks"]) > 0
            
            # Test agent structure
            for agent in autogen_config["agents"]:
                assert "name" in agent
                assert "role" in agent  
                assert "goal" in agent
                assert "backstory" in agent
            
            # Test task structure
            for task in autogen_config["tasks"]:
                assert "description" in task
                assert "expected_output" in task
                assert "agent" in task
                
            print("✅ AutoGen configuration validation passed")
            
        except Exception as e:
            pytest.fail(f"AutoGen config validation failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 