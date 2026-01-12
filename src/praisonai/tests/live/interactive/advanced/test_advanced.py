"""
Advanced Agent-Centric Test Suite.

Tests the agent's ability to autonomously complete complex tasks
using ONLY a single text prompt per scenario.

Run with: PRAISONAI_LIVE_INTERACTIVE=1 pytest tests/live/interactive/advanced/test_advanced.py -v
"""

import pytest

from ..runner import LiveInteractiveRunner
from . import can_run_advanced_tests
from .scenarios import ALL_ADVANCED_SCENARIOS


pytestmark = pytest.mark.skipif(
    not can_run_advanced_tests()[0],
    reason=f"Advanced tests disabled: {can_run_advanced_tests()[1]}"
)


@pytest.fixture(scope="module")
def runner():
    """Create a shared runner for all tests."""
    return LiveInteractiveRunner(verbose=True)


class TestAdvancedScenarios:
    """Advanced agent-centric test scenarios."""

    @pytest.mark.parametrize("scenario", ALL_ADVANCED_SCENARIOS, ids=lambda s: s.id)
    def test_scenario(self, scenario, runner):
        """Run a single advanced scenario with retry."""
        result = runner._run_with_retry(scenario)
        
        if not result.passed:
            print(f"\n{'='*60}")
            print(f"SCENARIO FAILED: {scenario.id} - {scenario.name}")
            print(f"{'='*60}")
            print(f"Description: {scenario.description}")
            print(f"Prompt: {scenario.prompts[0][:200]}...")
            print(f"Attempts: {result.attempts}")
            print(f"Assertions: {result.assertions}")
            print(f"Tool calls: {result.tool_calls}")
            print(f"Error: {result.error}")
            print(f"\nResponse (last 500 chars):\n{result.response[-500:] if result.response else 'None'}")
            print(f"{'='*60}\n")
        
        assert result.passed, f"Scenario {scenario.id} failed after {result.attempts} attempts: {result.error}"


def run_all_and_report():
    """Run all scenarios and print report (for direct execution)."""
    runner = LiveInteractiveRunner(verbose=True)
    summary = runner.run_all(ALL_ADVANCED_SCENARIOS)
    summary.print_summary()
    return summary.pass_rate == 1.0


if __name__ == "__main__":
    import sys
    success = run_all_and_report()
    sys.exit(0 if success else 1)
