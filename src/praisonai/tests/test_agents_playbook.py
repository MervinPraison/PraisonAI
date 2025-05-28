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
        praisonai = PraisonAI(agent_file='tests/autogen-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Output ###', result)

    @pytest.mark.real
    def test_main_with_custom_framework(self):
        """Test CrewAI framework integration with real API calls"""
        praisonai = PraisonAI(agent_file='tests/crewai-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Task Output ###', result)

    @pytest.mark.real
    def test_main_with_internet_search_tool(self):
        """Test internet search tool integration with real API calls"""
        praisonai = PraisonAI(agent_file='tests/search-tool-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Task Output ###', result)

    @pytest.mark.real
    def test_main_with_built_in_tool(self):
        """Test built-in tool integration with real API calls"""
        praisonai = PraisonAI(agent_file='tests/inbuilt-tool-agents.yaml')
        result = praisonai.run()
        self.assertIn('### Task Output ###', result)