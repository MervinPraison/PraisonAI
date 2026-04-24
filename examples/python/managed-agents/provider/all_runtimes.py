"""Run every managed-runtime example and report a summary.

Executes the runtime_*.py files in this directory as subprocesses with a
30s per-example timeout. Exits non-zero if any example fails.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = [
    # ── LLM providers (where the LLM reasoning happens) ──
    "runtime_anthropic.py",   # full loop in Anthropic cloud
    "runtime_openai.py",      # LLM in OpenAI cloud
    "runtime_gemini.py",      # LLM in Google cloud
    "runtime_ollama.py",      # LLM on local/self-hosted Ollama
    # ── Cloud/compute providers (where tool execution happens) ──
    "runtime_e2b.py",         # tools sandboxed in E2B cloud VM
    "runtime_modal.py",       # tools sandboxed in Modal serverless cloud
    "runtime_fly.py",         # tools sandboxed on Fly.io Machines
    "runtime_daytona.py",     # tools sandboxed in Daytona cloud workspace
    "runtime_docker.py",      # tools sandboxed in local Docker container
]

results = []
for name in EXAMPLES:
    path = os.path.join(HERE, name)
    start = time.time()
    proc = subprocess.run(
        [sys.executable, path],
        capture_output=True, text=True, timeout=120,
        env=os.environ.copy(),  # propagate API keys and PYTHONPATH
    )
    dur = time.time() - start
    ok = proc.returncode == 0
    results.append((name, ok, dur, proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""))
    print(f"[{'OK' if ok else 'FAIL'}] {name:30s} {dur:.2f}s")
    if not ok:
        print(proc.stdout)
        print(proc.stderr)

print("\nSummary:")
for name, ok, dur, tail in results:
    print(f"  {'✓' if ok else '✗'} {name:30s} {dur:5.2f}s  {tail[:60]}")

sys.exit(0 if all(r[1] for r in results) else 1)
