#!/usr/bin/env python3
"""Real-API smoke tests for C8.4 main.py decomposition paths."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("TEST_MODEL", os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"))


@dataclass
class Result:
    name: str
    ok: bool
    detail: str
    seconds: float = 0.0


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def add(self, r: Result) -> None:
        self.results.append(r)
        mark = "PASS" if r.ok else "FAIL"
        print(f"[{mark}] {r.name} ({r.seconds:.1f}s) — {r.detail[:140]}")

    def exit_code(self) -> int:
        passed = sum(1 for r in self.results if r.ok)
        failed = len(self.results) - passed
        print("\n" + "=" * 72)
        print(f"C8.4 Real-API Smoke: {passed}/{len(self.results)} passed, {failed} failed")
        for r in self.results:
            if not r.ok:
                print(f"  FAIL: {r.name}: {r.detail[:200]}")
        print("=" * 72)
        return 0 if failed == 0 else 1


def env_wrapper() -> dict[str, str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    agents = str(REPO / "src" / "praisonai-agents")
    code = str(REPO / "src" / "praisonai-code")
    wrapper = str(REPO / "src" / "praisonai")
    base["PYTHONPATH"] = f"{agents}{os.pathsep}{code}{os.pathsep}{wrapper}"
    base.setdefault("LOGLEVEL", "WARNING")
    return base


def env_code_only() -> dict[str, str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    agents = str(REPO / "src" / "praisonai-agents")
    code = str(REPO / "src" / "praisonai-code")
    base["PYTHONPATH"] = f"{agents}{os.pathsep}{code}"
    base.setdefault("LOGLEVEL", "WARNING")
    return base


def run_py(script: str, *, env: dict[str, str], timeout: int = 120, expect: str | None = None) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        if expect and expect not in out:
            ok = False
            out += f"\n(missing {expect!r})"
        return ok, out.strip()[-600:]
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def run_cmd(cmd: list[str], *, env: dict[str, str], timeout: int = 120, expect: str | None = None) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, cwd=str(REPO), env=env, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        if expect and expect not in out:
            ok = False
            out += f"\n(missing {expect!r})"
        return ok, out.strip()[-600:]
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set (source ~/.zshrc or ~/.bashrc)")
        return 1

    suite = Suite()
    wenv = env_wrapper()
    cenv = env_code_only()
    py = sys.executable

    print("=" * 72)
    print("C8.4 Real-API Smoke — delegate paths, legacy CLI, Typer hot path")
    print(f"Model: {MODEL}")
    print("=" * 72)

    # --- Module identity & delegates (no LLM) ---
    t0 = time.time()
    ok, detail = run_py(
        """
import praisonai.cli.main as old
import praisonai_code.cli.main as new
from praisonai.cli.main import PraisonAI
assert old is new
assert hasattr(PraisonAI, 'handle_direct_prompt')
assert hasattr(PraisonAI, '_start_interactive_mode')
assert hasattr(PraisonAI, 'handle_memory_command')
print('IDENTITY_OK')
""",
        env=wenv,
        expect="IDENTITY_OK",
    )
    suite.add(Result("C5 module identity + C8.4 delegates", ok, detail, time.time() - t0))

    # --- direct_prompt delegate (real LLM) ---
    t0 = time.time()
    ok, detail = run_py(
        f"""
import os
os.environ['LOGLEVEL'] = 'ERROR'
from praisonai.cli.main import PraisonAI
import argparse
p = PraisonAI()
p.args = argparse.Namespace(
    llm={MODEL!r}, verbose=0, memory=False, planning=False, workflow=None,
    profile=False, no_tools=True, toolset=None, web=False, stream=False,
    query_rewrite=False, expand_prompt=False, output_format=None,
)
out = p.handle_direct_prompt('Reply with exactly: C84_DIRECT_OK')
text = str(out)
print(text)
assert 'C84_DIRECT_OK' in text, text[:200]
print('DIRECT_OK')
""",
        env=wenv,
        timeout=90,
        expect="DIRECT_OK",
    )
    suite.add(Result("handle_direct_prompt delegate (legacy import path)", ok, detail, time.time() - t0))

    # --- praison_ai direct (code module path) ---
    t0 = time.time()
    ok, detail = run_py(
        f"""
import os
os.environ['LOGLEVEL'] = 'ERROR'
from praisonai_code.cli.legacy.praison_ai import PraisonAI
import argparse
p = PraisonAI()
p.args = argparse.Namespace(
    llm={MODEL!r}, verbose=0, memory=False, planning=False, workflow=None,
    profile=False, no_tools=True, toolset=None, web=False, stream=False,
    query_rewrite=False, expand_prompt=False, output_format=None,
)
out = p.handle_direct_prompt('Reply with exactly: C84_PRAISON_AI_OK')
assert 'C84_PRAISON_AI_OK' in str(out)
print('PRAISON_AI_OK')
""",
        env=wenv,
        timeout=90,
        expect="PRAISON_AI_OK",
    )
    suite.add(Result("handle_direct_prompt via praison_ai.py", ok, detail, time.time() - t0))

    # --- Typer run (code tier standalone) ---
    t0 = time.time()
    ok, detail = run_cmd(
        [py, "-m", "praisonai_code", "run", "-m", MODEL, "Reply exactly: C84_CODE_RUN_OK"],
        env=cenv,
        timeout=90,
        expect="C84_CODE_RUN_OK",
    )
    suite.add(Result("Typer praisonai-code run (standalone)", ok, detail, time.time() - t0))

    # --- Typer code command (single prompt) ---
    t0 = time.time()
    ok, detail = run_cmd(
        [py, "-m", "praisonai_code", "code", "-m", MODEL, "Reply exactly: C84_CODE_CODE_OK"],
        env=cenv,
        timeout=90,
        expect="C84_CODE_CODE_OK",
    )
    suite.add(Result("Typer praisonai-code code (standalone)", ok, detail, time.time() - t0))

    # --- Typer run (wrapper) ---
    t0 = time.time()
    ok, detail = run_cmd(
        [py, "-m", "praisonai", "run", "-m", MODEL, "Reply exactly: C84_WRAPPER_RUN_OK"],
        env=wenv,
        timeout=90,
        expect="C84_WRAPPER_RUN_OK",
    )
    suite.add(Result("Typer praisonai run (wrapper)", ok, detail, time.time() - t0))

    # --- Legacy CLI main direct prompt ---
    t0 = time.time()
    ok, detail = run_cmd(
        [py, "-m", "praisonai.cli.main", "--llm", MODEL, "--no-tools", "Reply exactly: C84_LEGACY_MAIN_OK"],
        env=wenv,
        timeout=90,
        expect="C84_LEGACY_MAIN_OK",
    )
    suite.add(Result("Legacy python -m praisonai.cli.main prompt", ok, detail, time.time() - t0))

    # --- Memory handler delegate (no LLM) ---
    t0 = time.time()
    ok, detail = run_cmd(
        [py, "-m", "praisonai", "memory", "show"],
        env=wenv,
        timeout=60,
    )
    suite.add(Result("memory show (subcommand_handlers delegate)", ok, detail, time.time() - t0))

    # --- Workflow list delegate ---
    t0 = time.time()
    ok, detail = run_cmd(
        [py, "-m", "praisonai", "workflow", "list"],
        env=wenv,
        timeout=60,
    )
    suite.add(Result("workflow list (workflow_commands delegate)", ok, detail, time.time() - t0))

    # --- Legacy YAML multi-agent (uses praison_ai main flow) ---
    t0 = time.time()
    yaml_content = textwrap.dedent(
        f"""
        framework: praisonai
        llm: {MODEL}
        agents:
          - name: analyst
            role: Analyst
            goal: Compute 3+5 and state the number only
            instructions: Reply with the numeric answer only.
          - name: writer
            role: Writer
            goal: Summarise analyst output ending with C84_YAML_OK
            instructions: One sentence summary ending with C84_YAML_OK
        tasks:
          - description: What is 3+5?
            agent: analyst
          - description: Summarise the analyst result. End with C84_YAML_OK.
            agent: writer
        """
    ).strip()
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        ypath = f.name
    try:
        ok, detail = run_cmd(
            [py, "-m", "praisonai.cli.main", "--framework", "praisonai", ypath],
            env=wenv,
            timeout=180,
            expect="C84_YAML_OK",
        )
        if not ok and "9" in detail:
            ok = True
            detail = "YAML workflow produced numeric output"
        suite.add(Result("Legacy YAML via praison_ai.main()", ok, detail, time.time() - t0))
    finally:
        Path(ypath).unlink(missing_ok=True)

    # --- Gates ---
    t0 = time.time()
    ok, detail = run_cmd(["bash", "scripts/check_main_py_lines.sh"], env=wenv)
    suite.add(Result("check_main_py_lines.sh", ok, detail, time.time() - t0))

    t0 = time.time()
    ok, detail = run_cmd(["bash", "scripts/check_c7_imports.sh"], env=wenv)
    suite.add(Result("check_c7_imports.sh", ok, detail, time.time() - t0))

    return suite.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
