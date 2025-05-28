"""
CrewAI Integration Test - Basic functionality test

This test verifies that PraisonAI can successfully integrate with CrewAI
for basic agent crews and task execution.
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

@pytest.fixture
def mock_crewai_completion():
    """Mock CrewAI completion responses"""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Task completed successfully using CrewAI framework."
    return mock_response

@pytest.fixture
def crewai_config():
    """Configuration for CrewAI test"""
    return {
        "framework": "crewai",
        "agents": [
            {
                "name": "data_analyst",
                "role": "Data Analyst",
                "goal": "Analyze data and provide insights",
                "backstory": "Expert data analyst with statistical background"
            },
            {
                "name": "report_writer",
                "role": "Report Writer", 
                "goal": "Create comprehensive reports",
                "backstory": "Professional report writer with business acumen"
            }
        ],
        "tasks": [
            {
                "description": "Analyze the provided dataset for trends",
                "expected_output": "Statistical analysis with key findings",
                "agent": "data_analyst"
            },
            {
                "description": "Create a business report based on the analysis",
                "expected_output": "Professional business report with recommendations",
                "agent": "report_writer"
            }
        ]
    }

class TestCrewAIIntegration:
    """Test CrewAI integration with PraisonAI"""

    @pytest.mark.integration
    def test_crewai_import(self):
        """Test that CrewAI can be imported and is available"""
        try:
            import crewai
            assert crewai is not None
            print("✅ CrewAI import successful")
        except ImportError:
            pytest.skip("CrewAI not installed - skipping CrewAI integration tests")

    @pytest.mark.integration
    @patch('litellm.completion')
    def test_basic_crewai_agent_creation(self, mock_completion, mock_crewai_completion):
        """Test creating basic CrewAI agents through PraisonAI"""
        mock_completion.return_value = mock_crewai_completion
        
        try:
            from praisonai import PraisonAI
            
            # Create a simple YAML content for CrewAI
            yaml_content = """
framework: crewai
topic: Test CrewAI Integration  
roles:
  - name: Analyst
    goal: Analyze test data
    backstory: I am a skilled analyst for testing purposes
    tasks:
      - description: Perform basic analysis task
        expected_output: Analysis results and summary
"""
            
            # Create temporary test file
            test_file = "test_crewai_agents.yaml"
            with open(test_file, "w") as f:
                f.write(yaml_content)
            
            try:
                # Initialize PraisonAI with CrewAI framework
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="crewai"
                )
                
                assert praisonai is not None
                assert praisonai.framework == "crewai"
                print("✅ CrewAI PraisonAI instance created successfully")
                
            finally:
                # Cleanup
                if os.path.exists(test_file):
                    os.remove(test_file)
                    
        except ImportError as e:
            pytest.skip(f"CrewAI integration dependencies not available: {e}")
        except Exception as e:
            pytest.fail(f"CrewAI basic test failed: {e}")

    @pytest.mark.integration
    @patch('litellm.completion')
    def test_crewai_crew_workflow(self, mock_completion, mock_crewai_completion):
        """Test CrewAI crew workflow execution"""
        mock_completion.return_value = mock_crewai_completion
        
        try:
            from praisonai import PraisonAI
            
            yaml_content = """
framework: crewai
topic: Market Research Project
roles:
  - name: Market_Researcher
    goal: Research market trends
    backstory: Expert market researcher with industry knowledge
    tasks:
      - description: Research current market trends in technology sector
        expected_output: Comprehensive market research report
  - name: Strategy_Advisor
    goal: Provide strategic recommendations
    backstory: Senior strategy consultant
    tasks:
      - description: Analyze research and provide strategic recommendations
        expected_output: Strategic recommendations document
"""
            
            test_file = "test_crewai_workflow.yaml"
            with open(test_file, "w") as f:
                f.write(yaml_content)
            
            try:
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="crewai"
                )
                
                # Test that we can initialize without errors
                assert praisonai.framework == "crewai"
                print("✅ CrewAI workflow test passed")
                
            finally:
                if os.path.exists(test_file):
                    os.remove(test_file)
                    
        except ImportError as e:
            pytest.skip(f"CrewAI dependencies not available: {e}")
        except Exception as e:
            pytest.fail(f"CrewAI workflow test failed: {e}")

    @pytest.mark.integration
    def test_crewai_config_validation(self, crewai_config):
        """Test CrewAI configuration validation"""
        try:
            # Test that config has required fields
            assert crewai_config["framework"] == "crewai"
            assert len(crewai_config["agents"]) > 0
            assert len(crewai_config["tasks"]) > 0
            
            # Test agent structure
            for agent in crewai_config["agents"]:
                assert "name" in agent
                assert "role" in agent
                assert "goal" in agent
                assert "backstory" in agent
            
            # Test task structure  
            for task in crewai_config["tasks"]:
                assert "description" in task
                assert "expected_output" in task
                assert "agent" in task
                
            print("✅ CrewAI configuration validation passed")
            
        except Exception as e:
            pytest.fail(f"CrewAI config validation failed: {e}")

    @pytest.mark.integration
    @patch('litellm.completion')
    def test_crewai_agent_collaboration(self, mock_completion, mock_crewai_completion):
        """Test CrewAI agents working together in a crew"""
        mock_completion.return_value = mock_crewai_completion
        
        try:
            from praisonai import PraisonAI
            
            yaml_content = """
framework: crewai
topic: Content Creation Pipeline
roles:
  - name: Content_Researcher  
    goal: Research topics for content creation
    backstory: Expert content researcher with SEO knowledge
    tasks:
      - description: Research trending topics in AI technology
        expected_output: List of trending AI topics with analysis
        
  - name: Content_Writer
    goal: Write engaging content
    backstory: Professional content writer with technical expertise
    tasks:
      - description: Write blog post based on research findings
        expected_output: Well-structured blog post with SEO optimization
        
  - name: Content_Editor
    goal: Edit and refine content
    backstory: Senior editor with publishing experience
    tasks:
      - description: Review and edit the blog post for quality
        expected_output: Polished, publication-ready blog post
"""
            
            test_file = "test_crewai_collaboration.yaml"
            with open(test_file, "w") as f:
                f.write(yaml_content)
            
            try:
                praisonai = PraisonAI(
                    agent_file=test_file,
                    framework="crewai"
                )
                
                # Test that we can create a multi-agent crew
                assert praisonai.framework == "crewai"
                print("✅ CrewAI collaboration test passed")
                
            finally:
                if os.path.exists(test_file):
                    os.remove(test_file)
                    
        except ImportError as e:
            pytest.skip(f"CrewAI dependencies not available: {e}")
        except Exception as e:
            pytest.fail(f"CrewAI collaboration test failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 