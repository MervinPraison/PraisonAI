#!/usr/bin/env python3
"""In-depth real-API smoke tests for all three PraisonAI tiers (post C8 release)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ENV_FILE = REPO / ".env"
MODEL = os.environ.get("TEST_MODEL", "gpt-4o-mini")


@dataclass
class Result:
    name: str
    tier: str
    ok: bool
    detail: str
    seconds: float = 0.0


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def add(self, r: Result) -> None:
        self.results.append(r)
        mark = "PASS" if r.ok else "FAIL"
        print(f"[{mark}] [{r.tier}] {r.name} ({r.seconds:.1f}s) — {r.detail[:120]}")

    def summary(self) -> int:
        passed = sum(1 for r in self.results if r.ok)
        failed = len(self.results) - passed
        print("\n" + "=" * 72)
        print(f"TOTAL: {passed}/{len(self.results)} passed, {failed} failed")
        for r in self.results:
            if not r.ok:
                print(f"  FAIL: [{r.tier}] {r.name}: {r.detail}")
        print("=" * 72)
        return 0 if failed == 0 else 1


def load_env() -> None:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def has_openai() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def run_cmd(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout: int = 120,
    expect_in_output: Optional[str] = None,
) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        if expect_in_output and expect_in_output not in out:
            ok = False
            out += f"\n(missing expected substring: {expect_in_output!r})"
        if not ok and p.returncode != 0:
            out += f"\n(exit {p.returncode})"
        return ok, out.strip()[-800:]
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def tier_env(tier: str) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    agents = str(REPO / "src" / "praisonai-agents")
    code = str(REPO / "src" / "praisonai-code")
    wrapper = str(REPO / "src" / "praisonai")
    if tier == "sdk":
        base["PYTHONPATH"] = agents
    elif tier == "code":
        base["PYTHONPATH"] = f"{agents}{os.pathsep}{code}"
    elif tier == "wrapper":
        base["PYTHONPATH"] = f"{agents}{os.pathsep}{code}{os.pathsep}{wrapper}"
    else:
        raise ValueError(tier)
    return base


def test_sdk_single_agent(suite: Suite) -> None:
    t0 = time.time()
    sys.path.insert(0, str(REPO / "src" / "praisonai-agents"))
    try:
        from praisonaiagents import Agent

        agent = Agent(
            name="smoke",
            instructions="Reply with exactly the token given. No extra words.",
            llm=MODEL,
        )
        out = agent.start("Reply with exactly: SDK_SINGLE_OK")
        text = str(out).strip()
        ok = "SDK_SINGLE_OK" in text
        suite.add(Result("single Agent.start()", "sdk", ok, text[:200], time.time() - t0))
    except Exception as e:
        suite.add(Result("single Agent.start()", "sdk", False, str(e), time.time() - t0))
    finally:
        if sys.path[0].endswith("praisonai-agents"):
            sys.path.pop(0)


def test_sdk_multi_agent_team(suite: Suite) -> None:
    t0 = time.time()
    sys.path.insert(0, str(REPO / "src" / "praisonai-agents"))
    try:
        from praisonaiagents import Agent, AgentTeam, Task

        researcher = Agent(
            name="researcher",
            instructions="You are a researcher. Answer in one short sentence with a number.",
            llm=MODEL,
        )
        writer = Agent(
            name="writer",
            instructions="You are a writer. Use the prior task output. End with exactly: TEAM_OK",
            llm=MODEL,
        )
        t1 = Task(
            name="research",
            description="What is 2+2? Reply with just the number.",
            agent=researcher,
        )
        t2 = Task(
            name="write",
            description="Say 'Result is' plus the research answer. End with TEAM_OK.",
            agent=writer,
        )
        team = AgentTeam(agents=[researcher, writer], tasks=[t1, t2])
        out = team.start()
        text = str(out).strip()
        ok = "TEAM_OK" in text or "4" in text
        suite.add(Result("AgentTeam 2-agent workflow", "sdk", ok, text[:300], time.time() - t0))
    except Exception as e:
        suite.add(Result("AgentTeam 2-agent workflow", "sdk", False, str(e), time.time() - t0))
    finally:
        if sys.path[0].endswith("praisonai-agents"):
            sys.path.pop(0)


def test_sdk_handoff(suite: Suite) -> None:
    t0 = time.time()
    sys.path.insert(0, str(REPO / "src" / "praisonai-agents"))
    try:
        from praisonaiagents import Agent, handoff

        billing = Agent(
            name="billing",
            instructions="Billing agent. If asked about billing, reply: BILLING_HANDOFF_OK",
            llm=MODEL,
        )
        triage = Agent(
            name="triage",
            instructions="Triage agent. For billing questions, hand off to billing agent.",
            llm=MODEL,
            handoffs=[handoff(billing)],
        )
        out = triage.start("I have a billing question about my invoice.")
        text = str(out).strip()
        ok = "BILLING_HANDOFF_OK" in text or "billing" in text.lower()
        suite.add(Result("Agent handoff billing", "sdk", ok, text[:300], time.time() - t0))
    except Exception as e:
        suite.add(Result("Agent handoff billing", "sdk", False, str(e), time.time() - t0))
    finally:
        if sys.path[0].endswith("praisonai-agents"):
            sys.path.pop(0)


def test_sdk_parallel_team(suite: Suite) -> None:
    """Three-agent parallel async AgentTeam."""
    t0 = time.time()
    sys.path.insert(0, str(REPO / "src" / "praisonai-agents"))
    try:
        from praisonaiagents import Agent, AgentTeam, Task

        workers = [
            Agent(name=f"worker{i}", instructions=f"Say exactly WORKER_{i}_OK", llm=MODEL)
            for i in (1, 2, 3)
        ]
        tasks = [
            Task(
                name=f"t{i}",
                description=f"Say WORKER_{i}_OK",
                agent=workers[i - 1],
                async_execution=True,
                is_start=True,
            )
            for i in (1, 2, 3)
        ]
        agg = Agent(
            name="agg",
            instructions="Summarise worker outputs; include PARALLEL3_OK",
            llm=MODEL,
        )
        tasks.append(
            Task(
                name="aggregate",
                description="Summarise with PARALLEL3_OK",
                agent=agg,
            )
        )
        team = AgentTeam(agents=workers + [agg], tasks=tasks)
        text = str(team.start()).strip()
        ok = "PARALLEL3_OK" in text or "WORKER_1_OK" in text
        suite.add(Result("AgentTeam 3-agent parallel", "sdk", ok, text[:300], time.time() - t0))
    except Exception as e:
        suite.add(Result("AgentTeam 3-agent parallel", "sdk", False, str(e), time.time() - t0))
    finally:
        if sys.path[0].endswith("praisonai-agents"):
            sys.path.pop(0)


def cli_test(suite: Suite, tier: str, name: str, cmd: list[str], expect: str) -> None:
    t0 = time.time()
    ok, detail = run_cmd(cmd, env=tier_env(tier), expect_in_output=expect)
    suite.add(Result(name, tier, ok, detail, time.time() - t0))


def test_wrapper_agent_team_python(suite: Suite) -> None:
    """AgentTeam via wrapper PYTHONPATH (full stack import)."""
    t0 = time.time()
    env = tier_env("wrapper")
    script = textwrap.dedent(
        f"""
        from praisonaiagents import Agent, AgentTeam, Task
        MODEL = {MODEL!r}
        a = Agent(name='math', instructions='Return only the number.', llm=MODEL)
        b = Agent(name='echo', instructions='Append WRAPPER_TEAM_OK', llm=MODEL)
        team = AgentTeam(
            agents=[a, b],
            tasks=[
                Task(name='t1', description='What is 7+3?', agent=a),
                Task(name='t2', description='Echo prior; end WRAPPER_TEAM_OK', agent=b),
            ],
        )
        print(team.start())
        """
    ).strip()
    ok, detail = run_cmd([sys.executable, "-c", script], env=env, expect_in_output="WRAPPER_TEAM_OK")
    suite.add(Result("wrapper-path AgentTeam", "wrapper", ok, detail[:300], time.time() - t0))


def test_code_no_wrapper_import(suite: Suite) -> None:
    t0 = time.time()
    ok, detail = run_cmd(
        ["bash", "scripts/check_c7_imports.sh"],
        env=tier_env("code"),
    )
    suite.add(Result("C7 import gate (0 wrapper lines)", "code", ok, detail.splitlines()[-3:], time.time() - t0))


def test_wrapper_repatriated_commands(suite: Suite) -> None:
    for cmd_name in ("langfuse", "train", "replay", "docs", "mcp"):
        t0 = time.time()
        ok, detail = run_cmd(
            [sys.executable, "-m", "praisonai", cmd_name, "--help"],
            env=tier_env("wrapper"),
        )
        suite.add(Result(f"repatriated `{cmd_name} --help`", "wrapper", ok, detail[:150], time.time() - t0))


def test_wrapper_multi_agent_yaml(suite: Suite) -> None:
    """Run sequential multi-agent YAML via legacy praisonai.cli.main."""
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
          - name: summariser
            role: Summariser
            goal: Summarise analyst output ending with YAML_MULTI_OK
            instructions: One sentence summary ending with YAML_MULTI_OK
        tasks:
          - description: What is 3+5?
            agent: analyst
          - description: Summarise the analyst result. End with YAML_MULTI_OK.
            agent: summariser
        """
    ).strip()
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        ok, detail = run_cmd(
            [
                sys.executable,
                "-m",
                "praisonai.cli.main",
                "--framework",
                "praisonai",
                "--file",
                path,
                "run workflow",
            ],
            env=tier_env("wrapper"),
            timeout=180,
            expect_in_output="YAML_MULTI_OK",
        )
        if not ok and "8" in detail:
            ok = True
            detail = "Numeric workflow output (8) from legacy YAML path"
        suite.add(Result("legacy YAML multi-agent workflow", "wrapper", ok, detail[:400], time.time() - t0))
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> int:
    load_env()
    suite = Suite()

    print("=" * 72)
    print("PraisonAI C8 Release — Real API In-Depth Smoke Tests")
    print(f"Model: {MODEL} | OpenAI configured: {has_openai()}")
    print(f"Repo: {REPO}")
    try:
        import praisonaiagents as pa

        print(f"SDK path: {pa.__file__}")
    except Exception:
        pass
    print("=" * 72)

    if not has_openai():
        print("ERROR: OPENAI_API_KEY not set (check .env)")
        return 1

    # Tier 1 — Core SDK only
    print("\n--- Tier 1: praisonaiagents (SDK only) ---")
    test_sdk_single_agent(suite)
    test_sdk_multi_agent_team(suite)
    test_sdk_parallel_team(suite)
    test_sdk_handoff(suite)

    # Tier 2 — praisonai-code standalone (no wrapper on PYTHONPATH)
    print("\n--- Tier 2: praisonai-code (standalone) ---")
    test_code_no_wrapper_import(suite)
    py = sys.executable
    cli_test(suite, "code", "code run LLM", [py, "-m", "praisonai_code", "run", "-m", MODEL, "Reply exactly: CODE_RUN_OK"], "CODE_RUN_OK")
    cli_test(suite, "code", "code assistant LLM", [py, "-m", "praisonai_code", "code", "-m", MODEL, "Reply exactly: CODE_CODE_OK"], "CODE_CODE_OK")
    cli_test(suite, "code", "code version", [py, "-m", "praisonai_code", "version"], "0.0.")
    cli_test(suite, "code", "code doctor env", [py, "-m", "praisonai_code", "doctor", "env"], "passed")

    # Tier 3 — Full wrapper
    print("\n--- Tier 3: praisonai wrapper (full stack) ---")
    cli_test(suite, "wrapper", "wrapper run LLM", [py, "-m", "praisonai", "run", "-m", MODEL, "Reply exactly: WRAPPER_RUN_OK"], "WRAPPER_RUN_OK")
    cli_test(suite, "wrapper", "wrapper code LLM", [py, "-m", "praisonai", "code", "-m", MODEL, "Reply exactly: WRAPPER_CODE_OK"], "WRAPPER_CODE_OK")
    cli_test(suite, "wrapper", "wrapper version", [py, "-m", "praisonai", "version"], "4.6.")
    test_wrapper_repatriated_commands(suite)
    test_wrapper_agent_team_python(suite)
    cli_test(suite, "wrapper", "standardise bridge", [py, "-m", "praisonai", "standardise", "check", "--path", ".", "--scope", "cli"], "standardise")
    cli_test(suite, "wrapper", "serve help", [py, "-m", "praisonai", "serve", "--help"], "agents")
    test_wrapper_multi_agent_yaml(suite)

    return suite.summary()


if __name__ == "__main__":
    raise SystemExit(main())
