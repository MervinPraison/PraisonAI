#!/usr/bin/env python3
"""
Agent Comparison Test - Run 5 tasks with both wrapper and direct agent

This test compares:
1. Direct Agent approach (praisonai_external_agent pattern)
2. CLI Wrapper approach (praisonai_wrapper_agent pattern)

Usage:
    python test_agent_comparison.py
"""
import sys
import os
import time
import asyncio
from datetime import datetime

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

# 5 Test Tasks (simple to moderately complex)
TEST_TASKS = [
    {
        "name": "list_directory",
        "instruction": "List all files in the current directory and count how many Python files exist",
        "expected_artifacts": ["file count", ".py count"]
    },
    {
        "name": "create_structure",
        "instruction": "Create a directory called 'test_workspace', create a file inside it named 'readme.txt' with content 'Hello World', then verify it exists",
        "expected_artifacts": ["test_workspace/", "readme.txt"]
    },
    {
        "name": "file_operations",
        "instruction": "Create a file called 'numbers.txt' with numbers 1-10 each on a new line, then display the first 3 lines",
        "expected_artifacts": ["numbers.txt"]
    },
    {
        "name": "system_info",
        "instruction": "Show the current working directory, current user, and Python version",
        "expected_artifacts": ["pwd output", "whoami output"]
    },
    {
        "name": "text_processing",
        "instruction": "Create a file 'words.txt' with 5 words (apple, banana, cherry, date, elderberry), then count the total characters in the file",
        "expected_artifacts": ["words.txt", "character count"]
    }
]


class DirectAgentRunner:
    """Runs tasks using direct Agent class approach."""
    
    def __init__(self):
        from praisonaiagents import Agent
        from praisonaiagents.tools import execute_command
        from praisonaiagents.approval import get_approval_registry, AutoApproveBackend
        
        self.Agent = Agent
        self.execute_command = execute_command
        self.registry = get_approval_registry()
        self.registry.set_backend(AutoApproveBackend())
        self.results = []
    
    def run_task(self, task: dict) -> dict:
        """Run a single task and return metrics."""
        print(f"\n🎯 Direct Agent - Running: {task['name']}")
        print(f"   Instruction: {task['instruction'][:60]}...")
        
        start_time = time.time()
        
        try:
            agent = self.Agent(
                name=f"direct-{task['name']}",
                instructions="You are a terminal task agent. Use execute_command tool to complete tasks.",
                tools=[self.execute_command],
                llm="gpt-4o-mini"
            )
            
            result = agent.start(task['instruction'])
            elapsed = time.time() - start_time
            
            # Get cost if available
            cost = getattr(agent, 'total_cost', 0) or 0
            
            print(f"   ✅ Completed in {elapsed:.2f}s")
            print(f"   💰 Cost: ${cost:.6f}")
            
            return {
                "task": task['name'],
                "success": True,
                "time": elapsed,
                "cost": cost,
                "result_preview": str(result)[:100] if result else "No output",
                "error": None
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"   ❌ Failed in {elapsed:.2f}s: {e}")
            return {
                "task": task['name'],
                "success": False,
                "time": elapsed,
                "cost": 0,
                "result_preview": None,
                "error": str(e)
            }


class WrapperAgentRunner:
    """Runs tasks using CLI wrapper approach via subprocess."""
    
    def __init__(self):
        self.results = []
    
    def run_task(self, task: dict) -> dict:
        """Run a single task using praisonai CLI via subprocess."""
        print(f"\n🎯 Wrapper Agent - Running: {task['name']}")
        print(f"   Instruction: {task['instruction'][:60]}...")
        
        start_time = time.time()
        
        try:
            import subprocess
            import shlex
            
            # Build the praisonai CLI command
            # Format: praisonai "TASK" --model MODEL
            cmd = [
                "praisonai",
                task['instruction'],
                "--model", "gpt-4o-mini"
            ]
            
            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                env={**os.environ, "LOGLEVEL": "WARNING"}
            )
            
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                print(f"   ✅ Completed in {elapsed:.2f}s")
                return {
                    "task": task['name'],
                    "success": True,
                    "time": elapsed,
                    "cost": 0,  # Cost tracking not available in CLI mode
                    "result_preview": result.stdout[:100] if result.stdout else "No output",
                    "error": None
                }
            else:
                print(f"   ❌ Failed with exit code {result.returncode} in {elapsed:.2f}s")
                return {
                    "task": task['name'],
                    "success": False,
                    "time": elapsed,
                    "cost": 0,
                    "result_preview": None,
                    "error": f"Exit code {result.returncode}: {result.stderr[:200]}"
                }
            
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            print(f"   ⏱️  Timeout after {elapsed:.2f}s")
            return {
                "task": task['name'],
                "success": False,
                "time": elapsed,
                "cost": 0,
                "result_preview": None,
                "error": "Timeout after 300s"
            }
            
        except FileNotFoundError:
            elapsed = time.time() - start_time
            print(f"   ⚠️ praisonai CLI not found")
            return {
                "task": task['name'],
                "success": False,
                "time": elapsed,
                "cost": 0,
                "result_preview": None,
                "error": "praisonai CLI not installed (pip install praisonai)"
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"   ❌ Failed in {elapsed:.2f}s: {e}")
            return {
                "task": task['name'],
                "success": False,
                "time": elapsed,
                "cost": 0,
                "result_preview": None,
                "error": str(e)
            }


def compare_results(direct_results: list, wrapper_results: list):
    """Compare results from both approaches."""
    print("\n" + "=" * 70)
    print("📊 COMPARISON RESULTS")
    print("=" * 70)
    
    # Calculate metrics
    direct_success = sum(1 for r in direct_results if r['success'])
    wrapper_success = sum(1 for r in wrapper_results if r['success'])
    
    direct_total_time = sum(r['time'] for r in direct_results)
    wrapper_total_time = sum(r['time'] for r in wrapper_results)
    
    direct_total_cost = sum(r['cost'] for r in direct_results)
    
    print(f"\n✅ Success Rate:")
    print(f"   Direct Agent:  {direct_success}/5 ({direct_success*20}%)")
    print(f"   Wrapper Agent: {wrapper_success}/5 ({wrapper_success*20}%)")
    
    print(f"\n⏱️  Total Time:")
    print(f"   Direct Agent:  {direct_total_time:.2f}s (avg: {direct_total_time/5:.2f}s per task)")
    print(f"   Wrapper Agent: {wrapper_total_time:.2f}s (avg: {wrapper_total_time/5:.2f}s per task)")
    
    print(f"\n💰 Total Cost (Direct Agent only):")
    print(f"   ${direct_total_cost:.6f} (avg: ${direct_total_cost/5:.6f} per task)")
    
    print(f"\n📋 Detailed Results:")
    print(f"   {'Task':<20} {'Direct':<12} {'Wrapper':<12} {'Winner':<10}")
    print(f"   {'-'*56}")
    
    for d, w in zip(direct_results, wrapper_results):
        d_status = "✅" if d['success'] else "❌"
        w_status = "✅" if w['success'] else "❌"
        
        if d['success'] and w['success']:
            winner = "Direct" if d['time'] < w['time'] else "Wrapper"
        elif d['success']:
            winner = "Direct"
        elif w['success']:
            winner = "Wrapper"
        else:
            winner = "None"
        
        print(f"   {d['task']:<20} {d_status} {d['time']:>6.2f}s  {w_status} {w['time']:>6.2f}s  {winner}")
    
    # Overall winner
    print(f"\n🏆 OVERALL WINNER:")
    if direct_success > wrapper_success:
        print(f"   🥇 Direct Agent (higher success rate)")
    elif wrapper_success > direct_success:
        print(f"   🥇 Wrapper Agent (higher success rate)")
    elif direct_success == wrapper_success == 5:
        if direct_total_time < wrapper_total_time:
            print(f"   🥇 Direct Agent (faster, same success rate)")
        else:
            print(f"   🥇 Wrapper Agent (faster, same success rate)")
    else:
        print(f"   ⚠️  Mixed results - both had failures")
    
    print("\n" + "=" * 70)


def main():
    print("=" * 70)
    print("🔬 AGENT COMPARISON TEST - 5 Tasks")
    print("=" * 70)
    print(f"\nTesting {len(TEST_TASKS)} tasks with both approaches...")
    print("Model: gpt-4o-mini")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Clean up any previous test artifacts
    print("\n🧹 Cleaning up previous test artifacts...")
    cleanup_commands = [
        "rm -rf test_workspace numbers.txt words.txt readme.txt 2>/dev/null; true"
    ]
    for cmd in cleanup_commands:
        os.system(cmd)
    
    # Run with Direct Agent
    print("\n" + "=" * 70)
    print("🤖 RUNNING WITH DIRECT AGENT (Agent class)")
    print("=" * 70)
    
    direct_runner = DirectAgentRunner()
    direct_results = []
    
    for task in TEST_TASKS:
        result = direct_runner.run_task(task)
        direct_results.append(result)
    
    # Clean up between runs
    print("\n🧹 Cleaning up before wrapper test...")
    for cmd in cleanup_commands:
        os.system(cmd)
    
    # Run with Wrapper Agent
    print("\n" + "=" * 70)
    print("📦 RUNNING WITH WRAPPER AGENT (CLI approach)")
    print("=" * 70)
    
    wrapper_runner = WrapperAgentRunner()
    wrapper_results = []
    
    for task in TEST_TASKS:
        result = wrapper_runner.run_task(task)
        wrapper_results.append(result)
    
    # Compare results
    compare_results(direct_results, wrapper_results)
    
    # Final cleanup
    print("\n🧹 Final cleanup...")
    for cmd in cleanup_commands:
        os.system(cmd)
    
    print(f"\n✅ Comparison complete! End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return direct_results, wrapper_results


if __name__ == "__main__":
    try:
        direct_results, wrapper_results = main()
        
        # Exit with error if both failed completely
        direct_success = sum(1 for r in direct_results if r['success'])
        wrapper_success = sum(1 for r in wrapper_results if r['success'])
        
        if direct_success == 0 and wrapper_success == 0:
            print("\n❌ Both approaches failed completely!")
            sys.exit(1)
        else:
            print("\n✅ At least one approach succeeded on some tasks")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
