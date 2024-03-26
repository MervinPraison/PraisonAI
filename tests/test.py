# tests/test.py
# from .debug import * # Uncomment this line to import the debug.py file for debugging
import unittest
import os
from praisonai.cli import PraisonAI
from .advanced_example import advanced
from .basic_example import main
from .auto_example import auto

class TestGenerateCrewAndKickoff(unittest.TestCase):
    def test_generate_crew_and_kickoff_with_autogen_framework(self):
        praison_ai = PraisonAI(agent_file='tests/autogen-agents.yaml')
        result = praison_ai.generate_crew_and_kickoff()
        # Assert the result
        self.assertIn('### Output ###', result)

    def test_generate_crew_and_kickoff_with_custom_framework(self):
        praison_ai = PraisonAI(agent_file='tests/crewai-agents.yaml')
        result = praison_ai.generate_crew_and_kickoff()
        # Assert the result
        self.assertIn('### Output ###', result)
class TestPraisonAICommand(unittest.TestCase):
    def test_praisonai_command(self):
        command = "praisonai --framework autogen --auto create movie script about cat in mars"
        result = os.popen(command).read()
        self.assertIn('Task output', result)
        
class TestPraisonAIInitCommand(unittest.TestCase):
    def test_praisonai_init_command(self):
        command = "praisonai --framework autogen --init create movie script about cat in mars"
        result = os.popen(command).read()
        self.assertIn('Task output', result)

class TestBasicExample(unittest.TestCase):
    def test_basic_example(self):
        main()

class TestAdvancedExample(unittest.TestCase):
    def test_advanced_example(self):
        advanced()
        
class TestAutoExample(unittest.TestCase):
    def test_auto_example(self):
        auto()

if __name__ == '__main__':
    unittest.main()