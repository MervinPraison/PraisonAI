import unittest
import subprocess
import os
import pytest
from praisonai.cli import PraisonAI
from .advanced_example import advanced
from .basic_example import main
from .auto_example import auto
# from xmlrunner import XMLTestRunner

# Patch for collections.abc MutableMapping issue
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping

class TestPraisonAIFramework(unittest.TestCase):
    @pytest.mark.real
    def test_main_with_agents_advanced(self):
        praisonai = PraisonAI(agent_file="tests/agents-advanced.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    @pytest.mark.real
    def test_main_with_autogen_framework(self):
        praisonai = PraisonAI(agent_file="tests/autogen-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    @pytest.mark.real
    def test_main_with_custom_framework(self):
        praisonai = PraisonAI(agent_file="tests/crewai-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    @pytest.mark.real
    def test_main_with_internet_search_tool(self):
        praisonai = PraisonAI(agent_file="tests/search-tool-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    @pytest.mark.real
    def test_main_with_built_in_tool(self):
        praisonai = PraisonAI(agent_file="tests/inbuilt-tool-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)
    

class TestPraisonAICommandLine(unittest.TestCase):
    def run_command(self, command):
        """Helper method to run CLI commands"""
        # Ensure OPENAI_API_KEY is available to the subprocess if this test is marked as real
        env = os.environ.copy()
        if 'OPENAI_API_KEY' not in env:
            # This is a fallback for local runs if the key isn't explicitly set for the main test process
            # In CI, it should be set by the workflow
            print("Warning: OPENAI_API_KEY not found in CLI test environment. API calls might fail if not mocked.")
            
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, env=env, timeout=120)
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "TIMEOUT: Command exceeded 120 seconds"

    @pytest.mark.real
    def test_praisonai_command(self):
        # Test basic praisonai command
        command = "praisonai --framework autogen --auto \"create a 2-agent team to write a simple python game\""
        result = self.run_command(command)
        print(f"Result: {result}")
        self.assertIn('TERMINATE', result)

    @pytest.mark.real
    def test_praisonai_init_command(self):
        # Test praisonai --init command
        # This command primarily creates files, but let's ensure it uses the real key if any underlying PraisonAI init involves API calls
        command = "praisonai --framework autogen --init \"create a 2-agent team to write a simple python game\""
        result = self.run_command(command)
        print(f"Result: {result}")
        # Check for success indicator in the output
        success_phrases = ['created successfully', 'agents.yaml created', 'File created']
        found_success = any(phrase in result for phrase in success_phrases)
        self.assertTrue(found_success, f"No success message found. Expected one of {success_phrases}. Last 1000 chars: {result[-1000:]}")

class TestExamples(unittest.TestCase):
    def test_advanced_example(self):
        result = advanced()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    @pytest.mark.real
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