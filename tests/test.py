# tests/test.py
import unittest
import subprocess
from praisonai.cli import PraisonAI
from .advanced_example import advanced
from .basic_example import main
from .auto_example import auto
from xmlrunner import XMLTestRunner

class TestPraisonAIFramework(unittest.TestCase):
    def test_main_with_autogen_framework(self):
        praison_ai = PraisonAI(agent_file='tests/autogen-agents.yaml')
        result = praison_ai.main()
        self.assertIn('### Task Output ###', result)

    def test_main_with_custom_framework(self):
        praison_ai = PraisonAI(agent_file='tests/crewai-agents.yaml')
        result = praison_ai.main()
        self.assertIn('### Task Output ###', result)

    def test_main_with_internet_search_tool(self):
        praison_ai = PraisonAI(agent_file='tests/search-tool-agents.yaml')
        result = praison_ai.main()
        self.assertIn('### Task Output ###', result)

    def test_main_with_built_in_tool(self):
        praison_ai = PraisonAI(agent_file='tests/inbuilt-tool-agents.yaml')
        result = praison_ai.main()
        self.assertIn('### Task Output ###', result)

class TestPraisonAICommandLine(unittest.TestCase):
    def run_command(self, command):
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, text=True)
        return result.stdout

    def test_praisonai_command(self):
        command = "praisonai --framework autogen --auto create movie script about cat in mars"
        result = self.run_command(command)
        self.assertIn('TERMINATE', result)

    def test_praisonai_init_command(self):
        command = "praisonai --framework autogen --init create movie script about cat in mars"
        result = self.run_command(command)
        self.assertIn('created successfully', result)

class TestExamples(unittest.TestCase):
    def test_basic_example(self):
        # Assuming main() has been adjusted to return a value for assertion
        result = main()
        self.assertIsNotNone(result)  # Adjust this assertion based on the expected outcome of main()

    def test_advanced_example(self):
        # Assuming advanced() returns a value suitable for assertion
        result = advanced()
        self.assertIsNotNone(result)  # Adjust this assertion as needed

    def test_auto_example(self):
        # Assuming auto() returns a value that can be asserted
        result = auto()
        self.assertIsNotNone(result)  # Adjust this assertion according to what auto() is expected to do

if __name__ == '__main__':
    with open('unittest_report.xml', 'wb') as output:
        unittest.main(testRunner=XMLTestRunner(output=output))
