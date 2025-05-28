import unittest
import subprocess
import os
from praisonai.cli import PraisonAI
from .advanced_example import advanced
from .basic_example import main
from .auto_example import auto
# from xmlrunner import XMLTestRunner

# Patch for collections.abc MutableMapping issue
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping

class TestPraisonAIFramework(unittest.TestCase):
    def test_main_with_agents_advanced(self):
        praisonai = PraisonAI(agent_file="tests/agents-advanced.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_autogen_framework(self):
        praisonai = PraisonAI(agent_file="tests/autogen-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_custom_framework(self):
        praisonai = PraisonAI(agent_file="tests/crewai-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_internet_search_tool(self):
        praisonai = PraisonAI(agent_file="tests/search-tool-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_built_in_tool(self):
        praisonai = PraisonAI(agent_file="tests/built-in-tools-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)
    

class TestPraisonAICommandLine(unittest.TestCase):
    def run_command(self, command):
        """Helper method to run CLI commands"""
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout + result.stderr

    def test_praisonai_command(self):
        # Test basic praisonai command
        command = "praisonai --framework autogen --auto create a 2-agent team to write a simple python game"
        result = self.run_command(command)
        print(f"Result: {result}")
        self.assertIn('TERMINATE', result)

    def test_praisonai_init_command(self):
        # Test praisonai --init command
        command = "praisonai --framework autogen --init create a 2-agent team to write a simple python game"
        result = self.run_command(command)
        print(f"Result: {result}")
        self.assertIn('created successfully', result)

class TestExamples(unittest.TestCase):
    def test_advanced_example(self):
        result = advanced()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_auto_example(self):
        result = auto()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_basic_example(self):
        result = main()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

if __name__ == '__main__':
    # runner = XMLTestRunner(output='test-reports')
    unittest.main()
    # unittest.main(testRunner=runner, exit=False)