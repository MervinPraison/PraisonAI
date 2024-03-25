# tests/test.py
import unittest
from praisonai.cli import generate_crew_and_kickoff
# from .debug import * # Uncomment this line to import the debug.py file for debugging

class TestGenerateCrewAndKickoff(unittest.TestCase):
    def test_generate_crew_and_kickoff_with_autogen_framework(self):
        result = generate_crew_and_kickoff('tests/autogen-agents.yaml')
        # Assert the result
        self.assertIn('### Output ###', result)

    def test_generate_crew_and_kickoff_with_custom_framework(self):
        result = generate_crew_and_kickoff('tests/crewai-agents.yaml')
        # Assert the result
        self.assertIn('### Output ###', result)

if __name__ == '__main__':
    unittest.main()