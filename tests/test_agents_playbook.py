# tests/test_agents_playbook.py
import unittest
import subprocess
from praisonai import PraisonAI

class TestPraisonAIFramework(unittest.TestCase):
    def test_main_with_autogen_framework(self):
        praisonai = PraisonAI(agent_file='tests/autogen-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Task Output ###', result)

    def test_main_with_custom_framework(self):
        praisonai = PraisonAI(agent_file='tests/crewai-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Task Output ###', result)

    def test_main_with_internet_search_tool(self):
        praisonai = PraisonAI(agent_file='tests/search-tool-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Task Output ###', result)

    def test_main_with_built_in_tool(self):
        praisonai = PraisonAI(agent_file='tests/inbuilt-tool-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Task Output ###', result)