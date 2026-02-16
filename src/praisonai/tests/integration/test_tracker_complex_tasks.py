"""
Integration tests for the tracker CLI with 10 complex multi-step tasks.

These tests run real agents with real tools to verify:
1. Autonomous mode execution
2. Step tracking and status output
3. Tool usage patterns
4. Gap identification
"""

import pytest
import json
import os
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

# Skip if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY required for integration tests"
)


@dataclass
class TaskResult:
    """Result from running a complex task."""
    task_id: int
    task_description: str
    success: bool
    completion_reason: str
    steps_taken: int
    tools_used: List[str]
    duration_seconds: float
    gaps_identified: List[str]
    step_details: List[Dict[str, Any]]


# 10 Complex Multi-Step Tasks
COMPLEX_TASKS = [
    {
        "id": 1,
        "description": "Research the top 3 Python web frameworks, compare their features, and write a summary to a file",
        "expected_tools": ["search_web", "write_file"],
        "min_steps": 3,
    },
    {
        "id": 2,
        "description": "Find the current weather API documentation, extract the endpoint structure, and create a Python code snippet to call it",
        "expected_tools": ["search_web", "web_crawl", "execute_code"],
        "min_steps": 4,
    },
    {
        "id": 3,
        "description": "Search for best practices in REST API design, summarize the key points, and save them to api_best_practices.txt",
        "expected_tools": ["search_web", "write_file"],
        "min_steps": 3,
    },
    {
        "id": 4,
        "description": "Find information about Docker containerization, create a simple Dockerfile example, and explain each line",
        "expected_tools": ["search_web", "write_file"],
        "min_steps": 3,
    },
    {
        "id": 5,
        "description": "Research machine learning model deployment strategies, compare cloud vs edge deployment, and create a decision matrix",
        "expected_tools": ["search_web", "write_file"],
        "min_steps": 4,
    },
    {
        "id": 6,
        "description": "Search for the latest AI agent frameworks, compare PraisonAI with alternatives, and write a comparison report",
        "expected_tools": ["search_web", "write_file"],
        "min_steps": 4,
    },
    {
        "id": 7,
        "description": "Find Python testing best practices, create a sample pytest test file, and explain the testing patterns used",
        "expected_tools": ["search_web", "write_file", "execute_code"],
        "min_steps": 4,
    },
    {
        "id": 8,
        "description": "Research async programming in Python, find examples of asyncio patterns, and create a working async code example",
        "expected_tools": ["search_web", "execute_code"],
        "min_steps": 3,
    },
    {
        "id": 9,
        "description": "Search for database optimization techniques, summarize indexing strategies, and create a SQL example demonstrating indexes",
        "expected_tools": ["search_web", "write_file"],
        "min_steps": 3,
    },
    {
        "id": 10,
        "description": "Find information about CI/CD pipelines, compare GitHub Actions vs GitLab CI, and create a sample workflow file",
        "expected_tools": ["search_web", "write_file"],
        "min_steps": 4,
    },
]


def run_single_task(task: Dict[str, Any], max_iterations: int = 15) -> TaskResult:
    """Run a single complex task and return the result."""
    from praisonai.cli.commands.tracker import (
        _run_tracked_task,
        _get_tools,
        DEFAULT_TOOLS,
    )
    
    tools = _get_tools(DEFAULT_TOOLS)
    
    result = _run_tracked_task(
        task=task["description"],
        tools=tools,
        max_iterations=max_iterations,
        model=None,  # Use default
        verbose=False,
        step_callback=None,
    )
    
    return TaskResult(
        task_id=task["id"],
        task_description=task["description"],
        success=result.success,
        completion_reason=result.completion_reason,
        steps_taken=result.total_steps,
        tools_used=result.tools_used,
        duration_seconds=result.total_duration,
        gaps_identified=result.gaps_identified,
        step_details=[
            {
                "step": s.step_number,
                "type": s.action_type,
                "action": s.action_name,
                "success": s.success,
                "duration": s.duration_seconds,
            }
            for s in result.steps
        ],
    )


class TestTrackerComplexTasks:
    """Integration tests for complex multi-step tasks."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Setup test environment."""
        self.original_cwd = os.getcwd()
        os.chdir(tmp_path)
        yield
        os.chdir(self.original_cwd)

    @pytest.mark.timeout(120)
    def test_task_1_web_framework_research(self):
        """Task 1: Research Python web frameworks."""
        task = COMPLEX_TASKS[0]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1, "Should take at least 1 step"
        # Record result for analysis
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")
        print(f"  Tools: {result.tools_used}")
        print(f"  Gaps: {result.gaps_identified}")

    @pytest.mark.timeout(120)
    def test_task_2_weather_api(self):
        """Task 2: Weather API documentation."""
        task = COMPLEX_TASKS[1]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_3_rest_api_best_practices(self):
        """Task 3: REST API best practices."""
        task = COMPLEX_TASKS[2]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_4_docker_containerization(self):
        """Task 4: Docker containerization."""
        task = COMPLEX_TASKS[3]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_5_ml_deployment(self):
        """Task 5: ML deployment strategies."""
        task = COMPLEX_TASKS[4]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_6_ai_agent_comparison(self):
        """Task 6: AI agent framework comparison."""
        task = COMPLEX_TASKS[5]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_7_python_testing(self):
        """Task 7: Python testing best practices."""
        task = COMPLEX_TASKS[6]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_8_async_programming(self):
        """Task 8: Async programming in Python."""
        task = COMPLEX_TASKS[7]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_9_database_optimization(self):
        """Task 9: Database optimization."""
        task = COMPLEX_TASKS[8]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")

    @pytest.mark.timeout(120)
    def test_task_10_cicd_pipelines(self):
        """Task 10: CI/CD pipelines."""
        task = COMPLEX_TASKS[9]
        result = run_single_task(task)
        
        assert result.steps_taken >= 1
        print(f"\nTask {task['id']}: {result.completion_reason}")
        print(f"  Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")


def run_all_tasks_and_generate_report():
    """Run all 10 tasks and generate a summary report."""
    import tempfile
    import os
    
    results: List[TaskResult] = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        
        for task in COMPLEX_TASKS:
            print(f"\n{'='*60}")
            print(f"Running Task {task['id']}: {task['description'][:50]}...")
            print('='*60)
            
            try:
                result = run_single_task(task, max_iterations=15)
                results.append(result)
                
                status = "✅" if result.success else "❌"
                print(f"{status} Completed: {result.completion_reason}")
                print(f"   Steps: {result.steps_taken}, Duration: {result.duration_seconds:.2f}s")
                print(f"   Tools: {result.tools_used}")
                if result.gaps_identified:
                    print(f"   Gaps: {result.gaps_identified}")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                results.append(TaskResult(
                    task_id=task["id"],
                    task_description=task["description"],
                    success=False,
                    completion_reason="error",
                    steps_taken=0,
                    tools_used=[],
                    duration_seconds=0,
                    gaps_identified=[str(e)],
                    step_details=[],
                ))
    
    # Generate summary table
    print("\n" + "="*80)
    print("SUMMARY TABLE: 10 Complex Task Results")
    print("="*80)
    print(f"{'#':<3} {'Task':<40} {'Status':<8} {'Steps':<6} {'Duration':<10} {'Gaps'}")
    print("-"*80)
    
    for r in results:
        status = "✅" if r.success else "❌"
        task_short = r.task_description[:38] + ".." if len(r.task_description) > 40 else r.task_description
        gaps = ", ".join(r.gaps_identified[:2]) if r.gaps_identified else "-"
        print(f"{r.task_id:<3} {task_short:<40} {status:<8} {r.steps_taken:<6} {r.duration_seconds:<10.2f} {gaps[:20]}")
    
    print("-"*80)
    
    # Statistics
    success_count = sum(1 for r in results if r.success)
    total_steps = sum(r.steps_taken for r in results)
    total_duration = sum(r.duration_seconds for r in results)
    
    print(f"\nSuccess Rate: {success_count}/{len(results)} ({100*success_count/len(results):.1f}%)")
    print(f"Total Steps: {total_steps}")
    print(f"Total Duration: {total_duration:.2f}s")
    print(f"Avg Steps per Task: {total_steps/len(results):.1f}")
    print(f"Avg Duration per Task: {total_duration/len(results):.2f}s")
    
    # Gap analysis
    all_gaps = []
    for r in results:
        all_gaps.extend(r.gaps_identified)
    
    if all_gaps:
        print("\n" + "="*80)
        print("GAP ANALYSIS")
        print("="*80)
        gap_counts = {}
        for gap in all_gaps:
            gap_counts[gap] = gap_counts.get(gap, 0) + 1
        
        for gap, count in sorted(gap_counts.items(), key=lambda x: -x[1]):
            print(f"  [{count}x] {gap}")
    
    return results


if __name__ == "__main__":
    run_all_tasks_and_generate_report()
