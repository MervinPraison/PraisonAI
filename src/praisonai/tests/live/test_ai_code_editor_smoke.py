"""Live smoke tests for AI code editor verification.

These tests verify that PraisonAI behaves as a real AI code editor:
- Edits files on disk
- Runs terminal commands (pytest, ruff, etc.)
- Observes failures and fixes them
- Converges to green tests

Run with: PRAISONAI_LIVE_SMOKE=1 pytest tests/live/test_ai_code_editor_smoke.py -v
"""

import pytest

from .runner import (
    is_live_smoke_enabled,
    has_api_key,
    create_working_dir,
    cleanup_working_dir,
    run_scenario,
    run_pytest,
)
from .scenarios import ALL_SCENARIOS


pytestmark = pytest.mark.skipif(
    not is_live_smoke_enabled() or not has_api_key(),
    reason="Live smoke tests disabled (set PRAISONAI_LIVE_SMOKE=1 and OPENAI_API_KEY)"
)


@pytest.fixture
def work_dir():
    """Create and cleanup working directory for each test."""
    work_dir = create_working_dir()
    yield work_dir
    cleanup_working_dir(work_dir)


class TestAICodeEditorSmoke:
    """Live smoke tests for AI code editor scenarios."""

    def test_fixture_has_failing_tests(self, work_dir):
        """Verify the fixture project has intentionally failing tests."""
        project_dir = work_dir / "project"
        passed, output = run_pytest(project_dir)
        assert not passed, "Fixture should have failing tests initially"
        assert "FAILED" in output, "Should show failed tests"

    @pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.name)
    def test_scenario(self, work_dir, scenario):
        """Run a single AI code editor scenario."""
        result = run_scenario(scenario, work_dir)
        
        if not result.success:
            print(f"\n{'='*60}")
            print(f"SCENARIO FAILED: {scenario.name}")
            print(f"{'='*60}")
            print(f"Description: {scenario.description}")
            print(f"Prompt: {scenario.prompt}")
            print(f"\nChecks passed: {result.checks_passed}")
            print(f"Checks failed: {result.checks_failed}")
            print(f"\nFile diffs: {list(result.file_diffs.keys())}")
            print(f"\nOutput (last 1000 chars):\n{result.output[-1000:]}")
            print(f"{'='*60}\n")
        
        assert result.success, f"Scenario {scenario.name} failed: {result.checks_failed}"


class TestIndividualScenarios:
    """Individual scenario tests for targeted debugging."""

    def test_scenario_1_implement_converter(self, work_dir):
        """Test implementing celsius_to_fahrenheit."""
        from .scenarios import SCENARIO_1_IMPLEMENT_CONVERTER
        result = run_scenario(SCENARIO_1_IMPLEMENT_CONVERTER, work_dir)
        assert result.success, f"Failed: {result.checks_failed}"

    def test_scenario_2_fix_divide_bug(self, work_dir):
        """Test fixing divide by zero bug."""
        from .scenarios import SCENARIO_2_FIX_DIVIDE_BUG
        result = run_scenario(SCENARIO_2_FIX_DIVIDE_BUG, work_dir)
        assert result.success, f"Failed: {result.checks_failed}"

    def test_scenario_10_full_suite(self, work_dir):
        """Test making all tests pass."""
        from .scenarios import SCENARIO_10_FULL_TEST_SUITE
        result = run_scenario(SCENARIO_10_FULL_TEST_SUITE, work_dir)
        assert result.success, f"Failed: {result.checks_failed}"
