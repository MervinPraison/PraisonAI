"""Live smoke tests for interactive mode.

These tests verify PraisonAI's interactive mode using real API calls.
Tests use HeadlessInteractiveCore to execute prompts through the same
pipeline as the interactive TUI.

Run with: PRAISONAI_LIVE_INTERACTIVE=1 pytest tests/live/interactive/test_smoke.py -v
"""

import pytest

from .runner import (
    is_live_interactive_enabled,
    has_api_key,
    LiveInteractiveRunner,
)
from .scenarios import ALL_SCENARIOS, get_scenarios_by_category


pytestmark = pytest.mark.skipif(
    not is_live_interactive_enabled() or not has_api_key(),
    reason="Live interactive tests disabled (set PRAISONAI_LIVE_INTERACTIVE=1 and OPENAI_API_KEY)"
)


@pytest.fixture(scope="module")
def runner():
    """Create a shared runner for all tests."""
    return LiveInteractiveRunner(verbose=True)


class TestLiveInteractiveSmoke:
    """Live smoke tests for interactive mode scenarios."""

    @pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.id)
    def test_scenario(self, scenario, runner):
        """Run a single interactive scenario with retry."""
        result = runner._run_with_retry(scenario)
        
        if not result.passed:
            print(f"\n{'='*60}")
            print(f"SCENARIO FAILED: {scenario.id} - {scenario.name}")
            print(f"{'='*60}")
            print(f"Description: {scenario.description}")
            print(f"Prompts: {scenario.prompts}")
            print(f"Attempts: {result.attempts}")
            print(f"Assertions: {result.assertions}")
            print(f"Tool calls: {result.tool_calls}")
            print(f"Error: {result.error}")
            print(f"\nResponse (last 500 chars):\n{result.response[-500:] if result.response else 'None'}")
            print(f"{'='*60}\n")
        
        assert result.passed, f"Scenario {scenario.id} failed after {result.attempts} attempts: {result.error}"


class TestBasicChat:
    """Basic chat scenarios."""

    @pytest.mark.parametrize("scenario", get_scenarios_by_category("basic"), ids=lambda s: s.id)
    def test_basic(self, scenario, runner):
        """Test basic chat scenarios."""
        result = runner._run_with_retry(scenario)
        assert result.passed, f"Failed: {result.error}"


class TestFileOperations:
    """File operation scenarios."""

    @pytest.mark.parametrize("scenario", get_scenarios_by_category("files"), ids=lambda s: s.id)
    def test_files(self, scenario, runner):
        """Test file operation scenarios."""
        result = runner._run_with_retry(scenario)
        assert result.passed, f"Failed: {result.error}"


class TestCodeIntelligence:
    """Code intelligence scenarios."""

    @pytest.mark.parametrize("scenario", get_scenarios_by_category("code"), ids=lambda s: s.id)
    def test_code(self, scenario, runner):
        """Test code intelligence scenarios."""
        result = runner._run_with_retry(scenario)
        assert result.passed, f"Failed: {result.error}"


class TestWorkflows:
    """Multi-step workflow scenarios."""

    @pytest.mark.parametrize("scenario", get_scenarios_by_category("workflow"), ids=lambda s: s.id)
    def test_workflow(self, scenario, runner):
        """Test workflow scenarios."""
        result = runner._run_with_retry(scenario)
        assert result.passed, f"Failed: {result.error}"


class TestMultiAgent:
    """Multi-agent scenarios."""

    @pytest.mark.parametrize("scenario", get_scenarios_by_category("multi"), ids=lambda s: s.id)
    def test_multi(self, scenario, runner):
        """Test multi-agent scenarios."""
        result = runner._run_with_retry(scenario)
        assert result.passed, f"Failed: {result.error}"


class TestEdgeCases:
    """Edge case scenarios."""

    @pytest.mark.parametrize("scenario", get_scenarios_by_category("edge"), ids=lambda s: s.id)
    def test_edge(self, scenario, runner):
        """Test edge case scenarios."""
        result = runner._run_with_retry(scenario)
        assert result.passed, f"Failed: {result.error}"


def run_all_and_report():
    """Run all scenarios and print report (for direct execution)."""
    from .scenarios import ALL_SCENARIOS
    
    runner = LiveInteractiveRunner(verbose=True)
    summary = runner.run_all(ALL_SCENARIOS)
    summary.print_summary()
    
    return summary.pass_rate == 1.0


if __name__ == "__main__":
    import sys
    success = run_all_and_report()
    sys.exit(0 if success else 1)
