# tests/test_agents_playbook.py
import unittest
import subprocess
import pytest
import os
from praisonai import PraisonAI

class TestPraisonAIFramework(unittest.TestCase):
    
    @pytest.mark.real
    def test_main_with_autogen_framework(self):
        """Test AutoGen framework integration with real API calls"""
        # Check if we have a real API key
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key or api_key == 'test-key' or api_key.startswith('sk-test-'):
            self.skipTest("Skipping real test - no valid OPENAI_API_KEY provided")
            
        praisonai = PraisonAI(agent_file='tests/autogen-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('### Output ###', result)
        except Exception as e:
            if ('Invalid API Key' in str(e) or 'AuthenticationError' in str(e) or 
                'InstructorRetryException' in str(e) or '401' in str(e)):
                self.skipTest(f"Skipping due to API authentication: {e}")
            else:
                raise

    @pytest.mark.real
    def test_main_with_custom_framework(self):
        """Test CrewAI framework integration with real API calls"""
        # Check if we have a real API key
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key or api_key == 'test-key' or api_key.startswith('sk-test-'):
            self.skipTest("Skipping real test - no valid OPENAI_API_KEY provided")
            
        praisonai = PraisonAI(agent_file='tests/crewai-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('### Task Output ###', result)
        except Exception as e:
            if ('Invalid API Key' in str(e) or 'AuthenticationError' in str(e) or 
                'InstructorRetryException' in str(e) or '401' in str(e)):
                self.skipTest(f"Skipping due to API authentication: {e}")
            else:
                raise

    @pytest.mark.real
    def test_main_with_internet_search_tool(self):
        """Test internet search tool integration with real API calls"""
        # Check if we have a real API key
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key or api_key == 'test-key' or api_key.startswith('sk-test-'):
            self.skipTest("Skipping real test - no valid OPENAI_API_KEY provided")
            
        praisonai = PraisonAI(agent_file='tests/search-tool-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('### Task Output ###', result)
        except Exception as e:
            if ('Invalid API Key' in str(e) or 'AuthenticationError' in str(e) or 
                'InstructorRetryException' in str(e) or '401' in str(e)):
                self.skipTest(f"Skipping due to API authentication: {e}")
            else:
                raise

    @pytest.mark.real
    def test_main_with_built_in_tool(self):
        """Test built-in tool integration with real API calls"""
        # Check if we have a real API key
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key or api_key == 'test-key' or api_key.startswith('sk-test-'):
            self.skipTest("Skipping real test - no valid OPENAI_API_KEY provided")
            
        praisonai = PraisonAI(agent_file='tests/inbuilt-tool-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('### Task Output ###', result)
        except Exception as e:
            if ('Invalid API Key' in str(e) or 'AuthenticationError' in str(e) or 
                'InstructorRetryException' in str(e) or '401' in str(e)):
                self.skipTest(f"Skipping due to API authentication: {e}")
            else:
                raise