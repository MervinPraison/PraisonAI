# tests/test_agents_playbook.py
import unittest
import subprocess
from praisonai import PraisonAI

class TestPraisonAIFramework(unittest.TestCase):
    def test_main_with_autogen_framework(self):
        praisonai = PraisonAI(agent_file='tests/autogen-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('### Task Output ###', result)
        except Exception as e:
            if ('Invalid API Key' in str(e) or 'AuthenticationError' in str(e) or 
                'InstructorRetryException' in str(e) or '401' in str(e)):
                self.skipTest(f"Skipping due to API authentication: {e}")
            else:
                raise

    def test_main_with_custom_framework(self):
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

    def test_main_with_internet_search_tool(self):
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

    def test_main_with_built_in_tool(self):
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