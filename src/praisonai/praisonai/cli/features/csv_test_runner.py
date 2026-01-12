"""
CSV-driven Interactive Test Runner for PraisonAI.

Provides a CSV-driven test runner that:
- Loads test cases from CSV with defined schema
- Runs each test in isolated temp workspace
- Executes prompts via headless interactive core
- Validates tool calls, files, and responses
- Integrates LLM-as-judge for response quality
- Emits artifacts per-test
"""

import csv
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# CSV Schema definition
CSV_SCHEMA = {
    # Required columns
    "id": {"required": True, "type": str, "description": "Unique test identifier"},
    "name": {"required": True, "type": str, "description": "Test name"},
    "prompts": {"required": True, "type": str, "description": "Single prompt or JSON array"},
    # Optional columns
    "description": {"required": False, "type": str, "default": ""},
    "mode": {"required": False, "type": str, "default": "headless"},
    "workspace_fixture": {"required": False, "type": str, "default": "empty"},
    "expected_tools": {"required": False, "type": str, "default": ""},
    "forbidden_tools": {"required": False, "type": str, "default": ""},
    "expected_files": {"required": False, "type": str, "default": "{}"},
    "expected_response": {"required": False, "type": str, "default": ""},
    "judge_rubric": {"required": False, "type": str, "default": ""},
    "judge_threshold": {"required": False, "type": float, "default": 7.0},
    "judge_model": {"required": False, "type": str, "default": "gpt-4o-mini"},
    "timeout": {"required": False, "type": int, "default": 60},
    "retries": {"required": False, "type": int, "default": 0},
    "skip_if": {"required": False, "type": str, "default": ""},
    "agents": {"required": False, "type": str, "default": "[]"},
    "workflow": {"required": False, "type": str, "default": "{}"},
}


@dataclass
class TestCase:
    """A single test case from CSV."""
    id: str
    name: str
    prompts: List[str]
    description: str = ""
    mode: str = "headless"
    workspace_fixture: str = "empty"
    expected_tools: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    expected_files: Dict[str, str] = field(default_factory=dict)
    expected_response: str = ""
    judge_rubric: str = ""
    judge_threshold: float = 7.0
    judge_model: str = "gpt-4o-mini"
    timeout: int = 60
    retries: int = 0
    skip_if: str = ""
    agents: List[Dict[str, Any]] = field(default_factory=list)
    workflow: Dict[str, Any] = field(default_factory=dict)
    
    def should_skip(self) -> Optional[str]:
        """Check if test should be skipped."""
        if not self.skip_if:
            return None
        
        conditions = [c.strip() for c in self.skip_if.split(",")]
        
        for condition in conditions:
            if condition == "no_openai_key":
                if not os.environ.get("OPENAI_API_KEY"):
                    return "OPENAI_API_KEY not set"
            elif condition == "no_anthropic_key":
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    return "ANTHROPIC_API_KEY not set"
            elif condition == "no_lsp":
                # Could check if LSP is available
                pass
            elif condition == "no_network":
                if os.environ.get("PRAISONAI_NO_NETWORK"):
                    return "Network disabled"
        
        return None


@dataclass
class TestResult:
    """Result of a single test."""
    test_id: str
    test_name: str
    status: str  # passed, failed, skipped, error
    duration: float
    tool_calls: List[str] = field(default_factory=list)
    response: str = ""
    judge_score: Optional[float] = None
    judge_passed: Optional[bool] = None
    judge_reasoning: str = ""
    artifacts_path: Optional[str] = None
    error: Optional[str] = None
    skip_reason: Optional[str] = None
    assertions: Dict[str, bool] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "status": self.status,
            "duration": self.duration,
            "tool_calls": self.tool_calls,
            "response": self.response[:500] if self.response else "",
            "judge_score": self.judge_score,
            "judge_passed": self.judge_passed,
            "judge_reasoning": self.judge_reasoning,
            "artifacts_path": self.artifacts_path,
            "error": self.error,
            "skip_reason": self.skip_reason,
            "assertions": self.assertions,
        }


@dataclass
class TestSummary:
    """Summary of all test results."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    judge_avg: Optional[float] = None
    results: List[TestResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration": self.duration,
            "judge_avg": self.judge_avg,
            "pass_rate": self.passed / self.total if self.total > 0 else 0,
            "results": [r.to_dict() for r in self.results],
        }
    
    def print_summary(self) -> None:
        """Print summary to console."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            table = Table(title="Interactive Test Results")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="white")
            table.add_column("Status")
            table.add_column("Duration", justify="right")
            table.add_column("Judge", justify="right")
            
            for r in self.results:
                status_style = {
                    "passed": "[green]✓ passed[/green]",
                    "failed": "[red]✗ failed[/red]",
                    "skipped": "[yellow]○ skipped[/yellow]",
                    "error": "[red]! error[/red]",
                }.get(r.status, r.status)
                
                judge_str = f"{r.judge_score:.1f}" if r.judge_score is not None else "-"
                
                table.add_row(
                    r.test_id,
                    r.test_name[:30],
                    status_style,
                    f"{r.duration:.2f}s",
                    judge_str,
                )
            
            console.print(table)
            console.print()
            console.print(f"[bold]Total:[/bold] {self.total} | "
                         f"[green]Passed:[/green] {self.passed} | "
                         f"[red]Failed:[/red] {self.failed} | "
                         f"[yellow]Skipped:[/yellow] {self.skipped}")
            if self.judge_avg is not None:
                console.print(f"[bold]Average Judge Score:[/bold] {self.judge_avg:.2f}")
            console.print(f"[bold]Total Duration:[/bold] {self.duration:.2f}s")
            
        except ImportError:
            # Fallback to plain print
            print("\n=== Interactive Test Results ===")
            for r in self.results:
                status = {"passed": "✓", "failed": "✗", "skipped": "○", "error": "!"}.get(r.status, "?")
                print(f"  {status} {r.test_id}: {r.test_name} ({r.duration:.2f}s)")
            print(f"\nTotal: {self.total} | Passed: {self.passed} | Failed: {self.failed} | Skipped: {self.skipped}")


def parse_csv(csv_path: Path) -> List[TestCase]:
    """
    Parse CSV file into TestCase objects.
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        List of TestCase objects
    """
    test_cases = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
            try:
                # Parse prompts (single string or JSON array)
                prompts_raw = row.get("prompts", "").strip()
                if prompts_raw.startswith("["):
                    prompts = json.loads(prompts_raw)
                else:
                    prompts = [prompts_raw] if prompts_raw else []
                
                # Parse expected_tools
                expected_tools = []
                if row.get("expected_tools"):
                    expected_tools = [t.strip() for t in row["expected_tools"].split(",") if t.strip()]
                
                # Parse forbidden_tools
                forbidden_tools = []
                if row.get("forbidden_tools"):
                    forbidden_tools = [t.strip() for t in row["forbidden_tools"].split(",") if t.strip()]
                
                # Parse expected_files JSON
                expected_files = {}
                if row.get("expected_files"):
                    try:
                        expected_files = json.loads(row["expected_files"])
                    except json.JSONDecodeError:
                        logger.warning(f"Row {row_num}: Invalid JSON in expected_files")
                
                # Parse agents JSON
                agents = []
                if row.get("agents"):
                    try:
                        agents = json.loads(row["agents"])
                    except json.JSONDecodeError:
                        logger.warning(f"Row {row_num}: Invalid JSON in agents")
                
                # Parse workflow JSON
                workflow = {}
                if row.get("workflow"):
                    try:
                        workflow = json.loads(row["workflow"])
                    except json.JSONDecodeError:
                        logger.warning(f"Row {row_num}: Invalid JSON in workflow")
                
                # Parse numeric fields
                judge_threshold = float(row.get("judge_threshold", 7.0) or 7.0)
                timeout = int(row.get("timeout", 60) or 60)
                retries = int(row.get("retries", 0) or 0)
                
                test_case = TestCase(
                    id=row.get("id", f"test_{row_num}"),
                    name=row.get("name", f"Test {row_num}"),
                    prompts=prompts,
                    description=row.get("description", ""),
                    mode=row.get("mode", "headless"),
                    workspace_fixture=row.get("workspace_fixture", "empty"),
                    expected_tools=expected_tools,
                    forbidden_tools=forbidden_tools,
                    expected_files=expected_files,
                    expected_response=row.get("expected_response", ""),
                    judge_rubric=row.get("judge_rubric", ""),
                    judge_threshold=judge_threshold,
                    judge_model=row.get("judge_model", "gpt-4o-mini"),
                    timeout=timeout,
                    retries=retries,
                    skip_if=row.get("skip_if", ""),
                    agents=agents,
                    workflow=workflow,
                )
                
                test_cases.append(test_case)
                
            except Exception as e:
                logger.error(f"Error parsing row {row_num}: {e}")
                continue
    
    return test_cases


class CSVTestRunner:
    """
    CSV-driven test runner for interactive mode.
    
    Usage:
        runner = CSVTestRunner(csv_path="tests.csv")
        summary = runner.run()
        summary.print_summary()
    """
    
    def __init__(
        self,
        csv_path: Path,
        model: str = "gpt-4o-mini",
        judge_model: str = "gpt-4o-mini",
        workspace: Optional[Path] = None,
        artifacts_dir: Optional[Path] = None,
        fail_fast: bool = False,
        keep_artifacts: bool = False,
        no_judge: bool = False,
        verbose: bool = False,
    ):
        """
        Initialize CSV test runner.
        
        Args:
            csv_path: Path to CSV file with test cases
            model: LLM model for agent
            judge_model: LLM model for judge
            workspace: Base workspace directory
            artifacts_dir: Directory for artifacts
            fail_fast: Stop on first failure
            keep_artifacts: Keep artifacts after run
            no_judge: Skip judge even if rubric present
            verbose: Verbose output
        """
        self.csv_path = Path(csv_path)
        self.model = model
        self.judge_model = judge_model
        self.workspace = workspace
        self.artifacts_dir = artifacts_dir
        self.fail_fast = fail_fast
        self.keep_artifacts = keep_artifacts
        self.no_judge = no_judge
        self.verbose = verbose
        self.results: List[TestResult] = []
    
    def run(self) -> TestSummary:
        """
        Run all tests from CSV.
        
        Returns:
            TestSummary with all results
        """
        start_time = time.time()
        
        # Parse CSV
        test_cases = parse_csv(self.csv_path)
        logger.info(f"Loaded {len(test_cases)} test cases from {self.csv_path}")
        
        if self.verbose:
            print(f"Running {len(test_cases)} tests from {self.csv_path}")
        
        # Run each test
        for i, test_case in enumerate(test_cases):
            if self.verbose:
                print(f"\n[{i+1}/{len(test_cases)}] Running: {test_case.name}")
            
            # Check skip conditions
            skip_reason = test_case.should_skip()
            if skip_reason:
                result = TestResult(
                    test_id=test_case.id,
                    test_name=test_case.name,
                    status="skipped",
                    duration=0.0,
                    skip_reason=skip_reason,
                )
                self.results.append(result)
                if self.verbose:
                    print(f"  Skipped: {skip_reason}")
                continue
            
            # Run test
            result = self._run_single_test(test_case)
            self.results.append(result)
            
            if self.verbose:
                status_icon = {"passed": "✓", "failed": "✗", "error": "!"}.get(result.status, "?")
                print(f"  {status_icon} {result.status} ({result.duration:.2f}s)")
                if result.error:
                    print(f"    Error: {result.error}")
            
            # Fail fast
            if self.fail_fast and result.status in ("failed", "error"):
                logger.info(f"Stopping due to fail-fast: {test_case.id}")
                break
        
        # Create summary
        summary = self._create_summary(time.time() - start_time)
        
        return summary
    
    def _run_single_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case."""
        import tempfile
        
        start_time = time.time()
        
        # Create workspace
        if self.workspace:
            test_workspace = self.workspace / test_case.id
        else:
            test_workspace = Path(tempfile.mkdtemp(prefix=f"praison_test_{test_case.id}_"))
        
        # Create artifacts dir
        if self.artifacts_dir:
            test_artifacts = self.artifacts_dir / test_case.id
        else:
            test_artifacts = test_workspace / "artifacts"
        
        try:
            # Import harness (lazy)
            from .interactive_test_harness import InteractiveTestHarness
            
            # Create harness
            harness = InteractiveTestHarness(
                workspace=test_workspace,
                artifacts_dir=test_artifacts,
                keep_workspace=self.keep_artifacts,
            )
            
            # Setup workspace
            harness.setup_workspace(test_case.workspace_fixture)
            
            # Run prompts
            exec_result = harness.run(
                prompts=test_case.prompts,
                model=self.model,
                approval_mode="auto",
                agents=test_case.agents if test_case.agents else None,
                workflow=test_case.workflow if test_case.workflow else None,
            )
            
            duration = time.time() - start_time
            
            # Get response
            response = "\n".join(exec_result.responses) if exec_result.responses else ""
            
            # Verify assertions
            assertions = {}
            
            # Tool call assertions
            tool_result = harness.verify_tool_calls(
                expected_tools=test_case.expected_tools,
                forbidden_tools=test_case.forbidden_tools,
            )
            assertions["tools"] = tool_result["passed"]
            
            # File assertions
            if test_case.expected_files:
                file_results = harness.verify_files(test_case.expected_files)
                assertions["files"] = all(file_results.values())
            else:
                assertions["files"] = True
            
            # Response assertion
            if test_case.expected_response:
                assertions["response"] = harness.verify_response(response, test_case.expected_response)
            else:
                assertions["response"] = True
            
            # Judge evaluation
            judge_score = None
            judge_passed = None
            judge_reasoning = ""
            
            if test_case.judge_rubric and not self.no_judge:
                judge_result = self._run_judge(
                    response=response,
                    rubric=test_case.judge_rubric,
                    threshold=test_case.judge_threshold,
                    model=test_case.judge_model or self.judge_model,
                )
                judge_score = judge_result.get("score")
                judge_passed = judge_result.get("passed")
                judge_reasoning = judge_result.get("reasoning", "")
                assertions["judge"] = judge_passed if judge_passed is not None else True
                harness.artifacts.judge_result = judge_result
            
            # Determine overall status
            all_passed = all(assertions.values()) and exec_result.success
            status = "passed" if all_passed else "failed"
            
            # Snapshot workspace if keeping artifacts
            if self.keep_artifacts:
                harness.snapshot_workspace()
            
            # Save artifacts
            artifacts_path = str(harness.save_artifacts(test_case.id))
            
            return TestResult(
                test_id=test_case.id,
                test_name=test_case.name,
                status=status,
                duration=duration,
                tool_calls=harness._executor.get_tools_called() if harness._executor else [],
                response=response,
                judge_score=judge_score,
                judge_passed=judge_passed,
                judge_reasoning=judge_reasoning,
                artifacts_path=artifacts_path,
                assertions=assertions,
            )
            
        except Exception as e:
            logger.error(f"Test {test_case.id} error: {e}", exc_info=True)
            return TestResult(
                test_id=test_case.id,
                test_name=test_case.name,
                status="error",
                duration=time.time() - start_time,
                error=str(e),
            )
        finally:
            if not self.keep_artifacts:
                try:
                    import shutil
                    if test_workspace.exists() and not self.workspace:
                        shutil.rmtree(test_workspace)
                except Exception:
                    pass
    
    def _run_judge(
        self,
        response: str,
        rubric: str,
        threshold: float,
        model: str,
    ) -> Dict[str, Any]:
        """
        Run LLM judge on response using Agent class.
        
        Args:
            response: Response to evaluate
            rubric: Evaluation rubric
            threshold: Pass threshold (1-10)
            model: Judge model
            
        Returns:
            Dict with score, passed, reasoning
        """
        try:
            from praisonaiagents import Agent
            
            # Create judge agent
            judge_agent = Agent(
                name="Judge",
                role="Evaluator",
                goal="Evaluate response quality based on rubric",
                instructions=f"""You are an expert evaluator. Your task is to evaluate a response based on the given rubric.

RUBRIC:
{rubric}

RESPONSE TO EVALUATE:
{response}

Provide your evaluation in the following format:
SCORE: [1-10]
REASONING: [Your detailed reasoning]

Be strict but fair. A score of 7+ means the response adequately meets the rubric criteria.""",
                llm=model,
                verbose=False,
            )
            
            # Get evaluation
            eval_response = judge_agent.chat("Please evaluate the response based on the rubric.")
            
            # Parse score from response
            score = self._parse_judge_score(eval_response)
            passed = score >= threshold if score is not None else None
            
            return {
                "score": score,
                "passed": passed,
                "reasoning": eval_response,
                "threshold": threshold,
                "model": model,
            }
            
        except Exception as e:
            logger.warning(f"Judge evaluation failed: {e}")
            return {
                "score": None,
                "passed": None,
                "reasoning": f"Judge error: {e}",
                "error": str(e),
            }
    
    def _parse_judge_score(self, response: str) -> Optional[float]:
        """Parse score from judge response."""
        import re
        
        # Try to find "SCORE: X" pattern
        match = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)", response, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        
        # Try to find standalone number at start
        match = re.search(r"^(\d+(?:\.\d+)?)", response.strip())
        if match:
            try:
                score = float(match.group(1))
                if 1 <= score <= 10:
                    return score
            except ValueError:
                pass
        
        return None
    
    def _create_summary(self, total_duration: float) -> TestSummary:
        """Create test summary."""
        summary = TestSummary(
            total=len(self.results),
            passed=sum(1 for r in self.results if r.status == "passed"),
            failed=sum(1 for r in self.results if r.status == "failed"),
            skipped=sum(1 for r in self.results if r.status == "skipped"),
            errors=sum(1 for r in self.results if r.status == "error"),
            duration=total_duration,
            results=self.results,
        )
        
        # Calculate average judge score
        judge_scores = [r.judge_score for r in self.results if r.judge_score is not None]
        if judge_scores:
            summary.judge_avg = sum(judge_scores) / len(judge_scores)
        
        return summary


def generate_csv_template(output_path: Path = None) -> str:
    """
    Generate a CSV template with all columns.
    
    Args:
        output_path: Path to write template (optional)
        
    Returns:
        CSV template string
    """
    headers = list(CSV_SCHEMA.keys())
    
    # Example rows
    examples = [
        {
            "id": "smoke_01",
            "name": "Basic Chat",
            "prompts": "Hello, what is 2+2?",
            "description": "Test basic chat response",
            "mode": "headless",
            "workspace_fixture": "empty",
            "expected_tools": "",
            "forbidden_tools": "",
            "expected_files": "{}",
            "expected_response": "4",
            "judge_rubric": "Response contains the number 4",
            "judge_threshold": "7.0",
            "judge_model": "gpt-4o-mini",
            "timeout": "60",
            "retries": "0",
            "skip_if": "",
            "agents": "[]",
            "workflow": "{}",
        },
        {
            "id": "tools_01",
            "name": "Create File",
            "prompts": "Create a file called hello.py with print('hello')",
            "description": "Test file creation",
            "mode": "headless",
            "workspace_fixture": "empty",
            "expected_tools": "acp_create_file",
            "forbidden_tools": "",
            "expected_files": '{"hello.py": "print.*hello"}',
            "expected_response": "",
            "judge_rubric": "File was created successfully",
            "judge_threshold": "7.0",
            "judge_model": "gpt-4o-mini",
            "timeout": "60",
            "retries": "0",
            "skip_if": "no_openai_key",
            "agents": "[]",
            "workflow": "{}",
        },
        {
            "id": "multi_01",
            "name": "Multi-step Edit",
            "prompts": '["Create test.py with x=1", "Edit test.py to change x=1 to x=2"]',
            "description": "Test multi-step editing",
            "mode": "headless",
            "workspace_fixture": "empty",
            "expected_tools": "acp_create_file,acp_edit_file",
            "forbidden_tools": "",
            "expected_files": '{"test.py": "x.*=.*2"}',
            "expected_response": "",
            "judge_rubric": "",
            "judge_threshold": "7.0",
            "judge_model": "gpt-4o-mini",
            "timeout": "120",
            "retries": "0",
            "skip_if": "no_openai_key",
            "agents": "[]",
            "workflow": "{}",
        },
    ]
    
    # Build CSV string
    import io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for example in examples:
        writer.writerow(example)
    
    csv_content = output.getvalue()
    
    if output_path:
        Path(output_path).write_text(csv_content)
        logger.info(f"Generated CSV template at {output_path}")
    
    return csv_content
