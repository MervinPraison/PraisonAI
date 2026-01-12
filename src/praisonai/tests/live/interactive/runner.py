"""Live interactive mode test runner.

This runner executes tests using HeadlessInteractiveCore - the same pipeline
as the interactive TUI. Tests run with real API calls and retry on failure.

Environment variables:
- PRAISONAI_LIVE_INTERACTIVE=1  - Enable live interactive tests
- OPENAI_API_KEY                - Required for live tests
- PRAISONAI_LIVE_MODEL          - Override model (default: gpt-4o-mini)
- PRAISON_APPROVAL_MODE         - Auto-set to 'auto' for non-interactive
"""

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MODEL = os.environ.get("PRAISONAI_LIVE_MODEL", "gpt-4o-mini")
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60


def is_live_interactive_enabled() -> bool:
    """Check if live interactive tests are enabled."""
    return os.environ.get("PRAISONAI_LIVE_INTERACTIVE", "0") == "1"


def has_api_key() -> bool:
    """Check if OpenAI API key is available."""
    return bool(os.environ.get("OPENAI_API_KEY"))


@dataclass
class ScenarioResult:
    """Result of a scenario execution."""
    scenario_id: str
    name: str
    passed: bool
    attempts: int
    duration: float
    response: str = ""
    tool_calls: List[str] = field(default_factory=list)
    error: Optional[str] = None
    assertions: Dict[str, bool] = field(default_factory=dict)
    artifacts_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "passed": self.passed,
            "attempts": self.attempts,
            "duration": self.duration,
            "response": self.response[:500] if self.response else "",
            "tool_calls": self.tool_calls,
            "error": self.error,
            "assertions": self.assertions,
            "artifacts_path": self.artifacts_path,
        }


@dataclass
class InteractiveScenario:
    """A test scenario for interactive mode verification."""
    id: str
    name: str
    description: str
    prompts: List[str]
    expected_tools: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    expected_files: Dict[str, str] = field(default_factory=dict)
    expected_response: str = ""
    workspace_fixture: str = "empty"
    max_retries: int = MAX_RETRIES
    timeout: int = DEFAULT_TIMEOUT
    model: str = ""


@dataclass
class RunSummary:
    """Summary of all scenario runs."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    duration: float = 0.0
    results: List[ScenarioResult] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "duration": self.duration,
            "results": [r.to_dict() for r in self.results],
        }
    
    def print_summary(self) -> None:
        """Print summary to console."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            table = Table(title="Live Interactive Test Results")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="white")
            table.add_column("Status")
            table.add_column("Attempts", justify="right")
            table.add_column("Duration", justify="right")
            
            for r in self.results:
                status = "[green]✓ PASS[/green]" if r.passed else "[red]✗ FAIL[/red]"
                table.add_row(
                    r.scenario_id,
                    r.name[:30],
                    status,
                    str(r.attempts),
                    f"{r.duration:.2f}s",
                )
            
            console.print(table)
            console.print()
            console.print(f"[bold]Total:[/bold] {self.total} | "
                         f"[green]Passed:[/green] {self.passed} | "
                         f"[red]Failed:[/red] {self.failed} | "
                         f"[bold]Pass Rate:[/bold] {self.pass_rate:.1%}")
            console.print(f"[bold]Total Duration:[/bold] {self.duration:.2f}s")
            
        except ImportError:
            print("\n=== Live Interactive Test Results ===")
            for r in self.results:
                status = "✓" if r.passed else "✗"
                print(f"  {status} {r.scenario_id}: {r.name} ({r.attempts} attempts, {r.duration:.2f}s)")
            print(f"\nTotal: {self.total} | Passed: {self.passed} | Failed: {self.failed}")
            print(f"Pass Rate: {self.pass_rate:.1%} | Duration: {self.duration:.2f}s")


class LiveInteractiveRunner:
    """
    Live test runner for interactive mode using HeadlessInteractiveCore.
    
    Runs scenarios with retry logic until they pass or max retries reached.
    """
    
    def __init__(
        self,
        model: str = "",
        artifacts_dir: Optional[Path] = None,
        keep_artifacts: bool = True,
        verbose: bool = True,
    ):
        self.model = model or DEFAULT_MODEL
        self.artifacts_dir = artifacts_dir or Path(tempfile.mkdtemp(prefix="praison_live_"))
        self.keep_artifacts = keep_artifacts
        self.verbose = verbose
        self.results: List[ScenarioResult] = []
        
        # Ensure approval mode is auto for non-interactive
        os.environ["PRAISON_APPROVAL_MODE"] = "auto"
    
    def run_all(self, scenarios: List[InteractiveScenario]) -> RunSummary:
        """
        Run all scenarios, retrying failures until satisfied.
        
        Args:
            scenarios: List of scenarios to run
            
        Returns:
            RunSummary with all results
        """
        start_time = time.time()
        self.results = []
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Running {len(scenarios)} live interactive tests")
            print(f"Model: {self.model}")
            print(f"Artifacts: {self.artifacts_dir}")
            print(f"{'='*60}\n")
        
        for i, scenario in enumerate(scenarios):
            if self.verbose:
                print(f"\n[{i+1}/{len(scenarios)}] {scenario.id}: {scenario.name}")
                print(f"  Description: {scenario.description}")
            
            result = self._run_with_retry(scenario)
            self.results.append(result)
            
            if self.verbose:
                status = "✓ PASS" if result.passed else "✗ FAIL"
                print(f"  Result: {status} (attempts: {result.attempts}, {result.duration:.2f}s)")
                if result.error:
                    print(f"  Error: {result.error}")
        
        summary = RunSummary(
            total=len(self.results),
            passed=sum(1 for r in self.results if r.passed),
            failed=sum(1 for r in self.results if not r.passed),
            duration=time.time() - start_time,
            results=self.results,
        )
        
        # Save summary
        summary_path = self.artifacts_dir / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary.to_dict(), f, indent=2)
        
        return summary
    
    def _run_with_retry(self, scenario: InteractiveScenario) -> ScenarioResult:
        """Run a scenario with retry logic."""
        start_time = time.time()
        last_error = None
        last_response = ""
        last_tool_calls = []
        last_assertions = {}
        
        for attempt in range(1, scenario.max_retries + 1):
            if self.verbose and attempt > 1:
                print(f"  Retry {attempt}/{scenario.max_retries}...")
            
            try:
                result = self._run_single(scenario, attempt)
                
                if result.passed:
                    return result
                
                last_error = result.error
                last_response = result.response
                last_tool_calls = result.tool_calls
                last_assertions = result.assertions
                
            except Exception as e:
                last_error = str(e)
                if self.verbose:
                    print(f"  Attempt {attempt} error: {e}")
        
        # All retries exhausted
        return ScenarioResult(
            scenario_id=scenario.id,
            name=scenario.name,
            passed=False,
            attempts=scenario.max_retries,
            duration=time.time() - start_time,
            response=last_response,
            tool_calls=last_tool_calls,
            error=last_error or "Max retries exhausted",
            assertions=last_assertions,
            artifacts_path=str(self.artifacts_dir / scenario.id),
        )
    
    def _run_single(self, scenario: InteractiveScenario, attempt: int) -> ScenarioResult:
        """Run a single attempt of a scenario."""
        start_time = time.time()
        
        # Create workspace
        workspace = Path(tempfile.mkdtemp(prefix=f"praison_{scenario.id}_"))
        artifacts_path = self.artifacts_dir / scenario.id / f"attempt_{attempt}"
        
        try:
            # Import harness (lazy)
            from praisonai.cli.features.interactive_test_harness import (
                InteractiveTestHarness,
            )
            
            # Create harness
            harness = InteractiveTestHarness(
                workspace=workspace,
                artifacts_dir=artifacts_path,
                keep_workspace=self.keep_artifacts,
            )
            
            # Setup workspace
            harness.setup_workspace(scenario.workspace_fixture)
            
            # Run prompts
            exec_result = harness.run(
                prompts=scenario.prompts,
                model=scenario.model or self.model,
                approval_mode="auto",
            )
            
            duration = time.time() - start_time
            
            # Get response
            response = "\n".join(exec_result.responses) if exec_result.responses else ""
            
            # Verify assertions
            assertions = {}
            
            # Tool call assertions
            tool_result = harness.verify_tool_calls(
                expected_tools=scenario.expected_tools,
                forbidden_tools=scenario.forbidden_tools,
            )
            assertions["tools"] = tool_result["passed"]
            
            # File assertions
            if scenario.expected_files:
                file_results = harness.verify_files(scenario.expected_files)
                assertions["files"] = all(file_results.values())
            else:
                assertions["files"] = True
            
            # Response assertion
            if scenario.expected_response:
                assertions["response"] = harness.verify_response(response, scenario.expected_response)
            else:
                assertions["response"] = True
            
            # Execution success
            assertions["execution"] = exec_result.success
            
            # Determine overall pass
            all_passed = all(assertions.values())
            
            # Snapshot workspace if keeping artifacts
            if self.keep_artifacts:
                harness.snapshot_workspace()
            
            # Save artifacts
            harness.save_artifacts(f"attempt_{attempt}")
            
            return ScenarioResult(
                scenario_id=scenario.id,
                name=scenario.name,
                passed=all_passed,
                attempts=attempt,
                duration=duration,
                response=response,
                tool_calls=harness._executor.get_tools_called() if harness._executor else [],
                error=exec_result.error if not exec_result.success else None,
                assertions=assertions,
                artifacts_path=str(artifacts_path),
            )
            
        except Exception as e:
            return ScenarioResult(
                scenario_id=scenario.id,
                name=scenario.name,
                passed=False,
                attempts=attempt,
                duration=time.time() - start_time,
                error=str(e),
            )
        finally:
            if not self.keep_artifacts:
                try:
                    shutil.rmtree(workspace)
                except Exception:
                    pass


def run_live_interactive_tests(
    scenarios: List[InteractiveScenario],
    model: str = "",
    artifacts_dir: Optional[Path] = None,
    verbose: bool = True,
) -> RunSummary:
    """
    Convenience function to run live interactive tests.
    
    Args:
        scenarios: List of scenarios to run
        model: LLM model (default: gpt-4o-mini)
        artifacts_dir: Directory for artifacts
        verbose: Print progress
        
    Returns:
        RunSummary with all results
    """
    runner = LiveInteractiveRunner(
        model=model,
        artifacts_dir=artifacts_dir,
        verbose=verbose,
    )
    return runner.run_all(scenarios)
