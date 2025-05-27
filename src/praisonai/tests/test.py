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
        praisonai = PraisonAI(agent_file='tests/agents-advanced.yaml')
        try:
            result = praisonai.run()
            self.assertIn('Task Output', result)
        except Exception as e:
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise
        
    def test_main_with_autogen_framework(self):
        praisonai = PraisonAI(agent_file='tests/autogen-agents.yaml')
        try:
            result = praisonai.run()
            self.assertTrue('Task Output' in result or '### Output ###' in result)
        except Exception as e:
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise

    def test_main_with_custom_framework(self):
        praisonai = PraisonAI(agent_file='tests/crewai-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('Task Output', result)
        except Exception as e:
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise

    def test_main_with_internet_search_tool(self):
        praisonai = PraisonAI(agent_file='tests/search-tool-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('Task Output', result)
        except Exception as e:
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise

    def test_main_with_built_in_tool(self):
        praisonai = PraisonAI(agent_file='tests/inbuilt-tool-agents.yaml')
        try:
            result = praisonai.run()
            self.assertIn('Task Output', result)
        except Exception as e:
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise
    

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
        command = "praisonai --framework autogen --auto create movie script about cat in mars"
        result = self.run_command(command)
        # Only skip if no API key provided or using test/fallback key  
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if (not api_key or 
            api_key.startswith('sk-test-') or 
            api_key == 'nokey' or
            'fallback' in api_key):
            if ('Invalid API Key' in result or 'AuthenticationError' in result or 
                'InstructorRetryException' in result or '401' in result):
                self.skipTest(f"Skipping due to no valid API key provided")
        self.assertIn('TERMINATE', result)

    def test_praisonai_init_command(self):
        command = "praisonai --framework autogen --init create movie script about cat in mars"
        result = self.run_command(command)
        # Only skip if no API key provided or using test/fallback key
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if (not api_key or 
            api_key.startswith('sk-test-') or 
            api_key == 'nokey' or
            'fallback' in api_key):
            if ('Invalid API Key' in result or 'AuthenticationError' in result or 
                'InstructorRetryException' in result or '401' in result):
                self.skipTest(f"Skipping due to no valid API key provided")
        self.assertIn('created successfully', result)

class TestExamples(unittest.TestCase):
    def test_basic_example(self):
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
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise

    def test_advanced_example(self):
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
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise

    def test_auto_example(self):
        # Test the auto example function
        try:
            result = auto()
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
            # Only skip if no API key provided or using test/fallback key
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if (not api_key or 
                api_key.startswith('sk-test-') or 
                api_key == 'nokey' or
                'fallback' in api_key):
                self.skipTest(f"Skipping due to no valid API key provided: {e}")
            else:
                # Real API key provided - test should fail, not skip
                raise

if __name__ == '__main__':
    # runner = XMLTestRunner(output='test-reports')
    unittest.main()
    # unittest.main(testRunner=runner, exit=False)