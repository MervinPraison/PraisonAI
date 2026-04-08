"""
Recipe Optimization Loop (CLI-based)

Demonstrates the 5-cycle recipe improvement pattern using CLI commands:
    Create (once) → Run → Judge → Optimize (loop 5x)

Usage:
    pip install praisonai
    export OPENAI_API_KEY=your-key
    export TAVILY_API_KEY=your-key
    python recipe_optimization_loop.py "research AI trends in healthcare"
"""
import subprocess
import sys
import os
import json
from pathlib import Path


def run_cli(cmd: str, cwd: str = None) -> tuple[int, str, str]:
    """Run a CLI command and return (exit_code, stdout, stderr)."""
    # Use shell=False with shlex.split for safer execution
    import shlex
    args = shlex.split(cmd)
    result = subprocess.run(
        args,
        shell=False,  # Use shell=False for security
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout, result.stderr


def create_recipe(goal: str, work_dir: str) -> str:
    """Create a recipe once. Returns recipe name."""
    print(f"\n{'═'*60}")
    print("STEP 1: CREATE RECIPE (once)")
    print(f"{'═'*60}")
    print(f"Goal: {goal}")
    
    cmd = f'praisonai recipe create "{goal}" --no-optimize'
    code, stdout, stderr = run_cli(cmd, cwd=work_dir)
    
    if code != 0:
        print(f"❌ Failed to create recipe: {stderr}")
        return None
    
    # Extract recipe name from output
    for line in stdout.split('\n'):
        if 'Created recipe:' in line:
            recipe_name = line.split('Created recipe:')[1].strip()
            print(f"✅ Created: {recipe_name}")
            return recipe_name
    
    print(f"✅ Recipe created")
    return None


def run_recipe(recipe_name: str, trace_name: str, work_dir: str) -> tuple[bool, str]:
    """Run the recipe and save trace. Returns (success, output)."""
    cmd = f'praisonai recipe run {recipe_name} --save --name {trace_name}'
    code, stdout, stderr = run_cli(cmd, cwd=work_dir)
    
    success = code == 0 and 'status: completed' in stdout.lower()
    return success, stdout


def judge_recipe(trace_name: str, work_dir: str) -> tuple[float, str]:
    """Judge the trace. Returns (score, feedback)."""
    cmd = f'praisonai recipe judge {trace_name}'
    code, stdout, stderr = run_cli(cmd, cwd=work_dir)
    
    # Extract score from output
    score = 0.0
    for line in stdout.split('\n'):
        if 'Overall Score:' in line:
            try:
                score = float(line.split(':')[1].strip().split('/')[0])
            except:
                pass
    
    return score, stdout


def optimize_recipe(recipe_name: str, iterations: int, work_dir: str) -> tuple[float, str]:
    """Optimize the recipe. Returns (final_score, output)."""
    cmd = f'praisonai recipe optimize {recipe_name} --iterations {iterations}'
    code, stdout, stderr = run_cli(cmd, cwd=work_dir)
    
    # Extract final score
    score = 0.0
    for line in stdout.split('\n'):
        if 'Final score:' in line or 'score:' in line.lower():
            try:
                score = float(line.split(':')[1].strip().split('/')[0])
            except:
                pass
    
    return score, stdout


def run_optimization_loop(goal: str, num_cycles: int = 5, threshold: float = 8.0):
    """Run the full Create → Run → Judge → Optimize loop."""
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║       Recipe Optimization Loop (CLI-based)                 ║")
    print("║  Pattern: Create (once) → Run → Judge → Optimize (loop)   ║")
    print(f"║  Cycles: {num_cycles} | Threshold: {threshold}/10                         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Create work directory
    work_dir = Path("/tmp/recipe-optimization-loop")
    work_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(work_dir)
    
    # Step 1: Create recipe (once)
    recipe_name = create_recipe(goal, str(work_dir))
    if not recipe_name:
        print("Failed to create recipe. Exiting.")
        return
    
    # Step 2-N: Run → Judge → Optimize loop
    results = []
    
    for cycle in range(1, num_cycles + 1):
        print(f"\n{'─'*60}")
        print(f"CYCLE {cycle}/{num_cycles}")
        print(f"{'─'*60}")
        
        trace_name = f"cycle-{cycle}"
        
        # Run
        print(f"  📝 Running recipe...")
        success, run_output = run_recipe(recipe_name, trace_name, str(work_dir))
        run_status = "✅" if success else "⚠️"
        print(f"  {run_status} Run complete")
        
        # Judge
        print(f"  ⚖️ Judging output...")
        score, judge_output = judge_recipe(trace_name, str(work_dir))
        score_status = "✅" if score >= threshold else "⚠️" if score >= 6.0 else "❌"
        print(f"  {score_status} Score: {score}/10")
        
        # Check if threshold met
        if score >= threshold:
            print(f"  🎉 Threshold {threshold}/10 reached!")
            results.append({"cycle": cycle, "score": score, "status": "passed"})
            break
        
        # Optimize
        print(f"  🔧 Optimizing recipe...")
        opt_score, opt_output = optimize_recipe(recipe_name, 1, str(work_dir))
        print(f"  → Optimized score: {opt_score}/10")
        
        results.append({
            "cycle": cycle,
            "initial_score": score,
            "optimized_score": opt_score,
            "status": "optimized" if opt_score > score else "no_change"
        })
    
    # Summary
    print(f"\n{'═'*60}")
    print("SUMMARY")
    print(f"{'═'*60}")
    
    for r in results:
        if "initial_score" in r:
            print(f"  Cycle {r['cycle']}: {r['initial_score']} → {r['optimized_score']}/10")
        else:
            print(f"  Cycle {r['cycle']}: {r['score']}/10 ✅ PASSED")
    
    final_score = results[-1].get("optimized_score", results[-1].get("score", 0))
    success = final_score >= threshold
    
    print(f"\n  Final Score: {final_score}/10")
    print(f"  Success: {'Yes ✅' if success else 'No ❌'}")
    print(f"  Recipe: {work_dir}/{recipe_name}")
    
    return results


if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else "research latest AI trends and create a summary report"
    run_optimization_loop(goal, num_cycles=5, threshold=8.0)
