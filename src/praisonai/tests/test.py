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

def _should_skip_api_test():
    """Check if API tests should be skipped due to invalid/test API key"""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    return (not api_key or 
            api_key.startswith('sk-test-') or 
            api_key == 'nokey' or
            'fallback' in api_key or
            'testing-only' in api_key or
            'not-real' in api_key)

class TestPraisonAIFramework(unittest.TestCase):
    def test_main_with_agents_advanced(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        praisonai = PraisonAI(agent_file="tests/agents-advanced.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_autogen_framework(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        praisonai = PraisonAI(agent_file="tests/autogen-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_custom_framework(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        praisonai = PraisonAI(agent_file="tests/crewai-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_internet_search_tool(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        praisonai = PraisonAI(agent_file="tests/search-tool-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

    def test_main_with_built_in_tool(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        praisonai = PraisonAI(agent_file="tests/inbuilt-tool-agents.yaml")
        result = praisonai.run()
        print(f"Result: {result}")
        self.assertIsNotNone(result)
    

class TestPraisonAICommandLine(unittest.TestCase):
    def run_command(self, command):
        result = subprocess.run(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            shell=True, 
            text=True, 
            env=os.environ.copy()  # Fix: Inherit environment variables
        )
        return result.stdout

    def test_praisonai_command(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        # Test basic praisonai command
        result = self.run_command(["praisonai", "--framework", "autogen", "create a 2-agent team to write a simple python game"])
        print(f"Result: {result}")
        self.assertIn('TERMINATE', result)

    def test_praisonai_init_command(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        # Test praisonai --init command
        result = self.run_command(["praisonai", "--init", "create a 2-agent team to write a simple python game"])
        print(f"Result: {result}")
        self.assertIn('created successfully', result)

class TestExamples(unittest.TestCase):
    def test_basic_example(self):
        if _should_skip_api_test():
            self.skipTest("Skipping due to no valid API key provided")
            
        # Test the basic example function
        try:
            result = main()
            self.assertIsNotNone(result)
            # Check if result contains expected success indicators or output
            self.assertTrue(
                isinstance(result, str) and (
                    "completed successfully" in result or 
                    "Task Output" in result or
                    len(result.strip()) > 0
                ),
                f"Expected meaningful result, got: {result}"
            )
        except Exception as e:
            # Fallback skip for API errors
            if any(error in str(e) for error in ['Invalid API Key', 'AuthenticationError', '401']):
                self.skipTest(f"Skipping due to API key issue: {e}")
            else:
                raise

    def test_advanced_example(self):
        if _should_skip_api_test():
            self.skipTest("Skipping due to no valid API key provided")
            
        # Test the advanced example function
        try:
            result = advanced()
            self.assertIsNotNone(result)
            # Check if result contains expected success indicators or output
            self.assertTrue(
                isinstance(result, str) and (
                    "completed successfully" in result or 
                    "Task Output" in result or
                    len(result.strip()) > 0
                ),
                f"Expected meaningful result, got: {result}"
            )
        except Exception as e:
            # Fallback skip for API errors
            if any(error in str(e) for error in ['Invalid API Key', 'AuthenticationError', '401']):
                self.skipTest(f"Skipping due to API key issue: {e}")
            else:
                raise

    def test_auto_example(self):
        if _should_skip_api_test():
            self.skipTest("Skipping API test due to invalid/test API key")
        
        result = auto()
        print(f"Result: {result}")
        self.assertIsNotNone(result)

if __name__ == '__main__':
    # runner = XMLTestRunner(output='test-reports')
    unittest.main()
    # unittest.main(testRunner=runner, exit=False)