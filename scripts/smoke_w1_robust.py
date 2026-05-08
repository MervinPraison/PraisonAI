#!/usr/bin/env python3
"""W1 deep-validation smoke test.

Exercises every robustness dimension of W1 with REAL LLM calls:

  T1. 3-platform unification (telegram → discord → slack, one user)
  T2. Persistence across restart (FileIdentityResolver)
  T3. Concurrent users do NOT leak history
  T4. SessionContext is visible to a tool the agent calls
  T5. Self-improving probe — ask the agent to "learn a new skill"
       (this surfaces the W1↔W2 boundary honestly)

Run::

    cd /Users/praison/worktrees/hermes-parity
    PYTHONPATH=src/praisonai-agents:src/praisonai python scripts/smoke_w1_robust.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path


def _pick_model() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic/claude-haiku-4-5"
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini/gemini-2.5-flash"
    return "gpt-4o-mini"


# ─────────────────────────────────────────────────────────────────────────────
# T1 — 3-platform unification
# ─────────────────────────────────────────────────────────────────────────────
async def test_three_platform_unification(tmp_path: Path, model: str) -> bool:
    print("\n" + "=" * 72)
    print("T1: 3-platform unification (telegram → discord → slack, same user)")
    print("=" * 72)

    from praisonaiagents import Agent
    from praisonaiagents.session import (
        FileIdentityResolver,
        DefaultSessionStore,
    )
    from praisonai.bots._session import BotSessionManager

    resolver = FileIdentityResolver(path=tmp_path / "identity.json")
    resolver.link("telegram", "tg-1", "alice")
    resolver.link("discord", "dc-1", "alice")
    resolver.link("slack", "sl-1", "alice")
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    agent = Agent(
        name="T1",
        instructions="Remember facts the user tells you and recall them precisely.",
        llm=model,
    )

    mgr = lambda p: BotSessionManager(platform=p, identity_resolver=resolver, store=store)
    mgr_t, mgr_d, mgr_s = mgr("telegram"), mgr("discord"), mgr("slack")

    out_t = await mgr_t.chat(agent, "tg-1", "My name is Vimes and my badge number is 177.")
    print(f"[Telegram] {out_t}")

    out_d = await mgr_d.chat(agent, "dc-1", "What did I tell you my badge number was?")
    print(f"[Discord]  {out_d}")

    out_s = await mgr_s.chat(agent, "sl-1", "And what did I say my name was?")
    print(f"[Slack]    {out_s}")

    ok = (
        out_d and "177" in out_d
        and out_s and "vimes" in out_s.lower()
    )
    print("  RESULT:", "PASS" if ok else "FAIL")
    return bool(ok)


# ─────────────────────────────────────────────────────────────────────────────
# T2 — Persistence across restart
# ─────────────────────────────────────────────────────────────────────────────
async def test_persistence_across_restart(tmp_path: Path, model: str) -> bool:
    print("\n" + "=" * 72)
    print("T2: Persistence — links + history survive 'restart' (new resolver+store)")
    print("=" * 72)

    from praisonaiagents import Agent
    from praisonaiagents.session import (
        FileIdentityResolver,
        DefaultSessionStore,
    )
    from praisonai.bots._session import BotSessionManager

    id_path = tmp_path / "identity.json"
    sess_dir = tmp_path / "sessions"

    # ── First "process" ─────────────────────────────────────────────
    r1 = FileIdentityResolver(path=id_path)
    r1.link("telegram", "tg-2", "bob")
    s1 = DefaultSessionStore(session_dir=str(sess_dir))
    agent1 = Agent(name="T2", instructions="You remember facts.", llm=model)
    mgr1 = BotSessionManager(platform="telegram", identity_resolver=r1, store=s1)
    out1 = await mgr1.chat(
        agent1, "tg-2",
        "Remember: project name is 'pyramid-of-tsort'.",
    )
    print(f"[Run1 Telegram] {out1}")

    # ── Second "process" — fresh objects, same files ────────────────
    r2 = FileIdentityResolver(path=id_path)
    s2 = DefaultSessionStore(session_dir=str(sess_dir))
    agent2 = Agent(name="T2", instructions="You remember facts.", llm=model)
    mgr2 = BotSessionManager(platform="telegram", identity_resolver=r2, store=s2)

    # Link must have survived
    assert r2.resolve("telegram", "tg-2") == "bob", "FileIdentityResolver lost link!"

    out2 = await mgr2.chat(agent2, "tg-2", "What was the project name I told you?")
    print(f"[Run2 Telegram] {out2}")

    ok = bool(out2 and "pyramid" in out2.lower())
    print("  RESULT:", "PASS" if ok else "FAIL")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# T3 — Concurrent users do NOT leak history
# ─────────────────────────────────────────────────────────────────────────────
async def test_concurrent_users_isolated(tmp_path: Path, model: str) -> bool:
    print("\n" + "=" * 72)
    print("T3: Concurrent users — no history leakage")
    print("=" * 72)

    from praisonaiagents import Agent
    from praisonaiagents.session import (
        FileIdentityResolver,
        DefaultSessionStore,
    )
    from praisonai.bots._session import BotSessionManager

    resolver = FileIdentityResolver(path=tmp_path / "identity.json")
    resolver.link("telegram", "u-alice", "alice")
    resolver.link("telegram", "u-bob", "bob")
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    agent = Agent(name="T3", instructions="You remember facts per user.", llm=model)
    mgr = BotSessionManager(
        platform="telegram", identity_resolver=resolver, store=store
    )

    await asyncio.gather(
        mgr.chat(agent, "u-alice", "I love mangoes."),
        mgr.chat(agent, "u-bob", "I love durian."),
    )
    out_alice = await mgr.chat(agent, "u-alice", "What fruit did I say I love?")
    out_bob = await mgr.chat(agent, "u-bob", "What fruit did I say I love?")
    print(f"[Alice] {out_alice}")
    print(f"[Bob]   {out_bob}")

    a_ok = out_alice and "mango" in out_alice.lower() and "durian" not in out_alice.lower()
    b_ok = out_bob and "durian" in out_bob.lower() and "mango" not in out_bob.lower()
    ok = bool(a_ok and b_ok)
    print("  RESULT:", "PASS" if ok else "FAIL")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# T4 — SessionContext visible to a tool
# ─────────────────────────────────────────────────────────────────────────────
async def test_session_context_visible_to_tool(tmp_path: Path, model: str) -> bool:
    print("\n" + "=" * 72)
    print("T4: SessionContext is visible to a tool the agent invokes")
    print("=" * 72)

    from praisonaiagents import Agent
    from praisonaiagents.session import (
        FileIdentityResolver,
        DefaultSessionStore,
        get_session_context,
    )
    from praisonai.bots._session import BotSessionManager

    captured = {}

    def whoami() -> str:
        """Return the platform and user id of the caller."""
        ctx = get_session_context()
        captured["platform"] = ctx.platform
        captured["unified_user_id"] = ctx.unified_user_id
        return f"platform={ctx.platform} user={ctx.unified_user_id}"

    resolver = FileIdentityResolver(path=tmp_path / "identity.json")
    resolver.link("telegram", "tg-99", "alice")
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))

    agent = Agent(
        name="T4",
        instructions=(
            "When the user asks 'who am I' or about platform info, "
            "ALWAYS call the whoami tool and report its result verbatim."
        ),
        tools=[whoami],
        llm=model,
    )
    mgr = BotSessionManager(
        platform="telegram", identity_resolver=resolver, store=store
    )

    out = await mgr.chat(
        agent, "tg-99",
        "Please call the whoami tool and tell me what you see.",
        chat_id="100", user_name="Alice",
    )
    print(f"[Agent] {out}")
    print(f"[Tool captured] platform={captured.get('platform')!r} "
          f"unified_user_id={captured.get('unified_user_id')!r}")

    ok = (
        captured.get("platform") == "telegram"
        and captured.get("unified_user_id") == "alice"
    )
    print("  RESULT:", "PASS" if ok else "FAIL")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# T5 — Self-improving probe (W1 ↔ W2 boundary)
# ─────────────────────────────────────────────────────────────────────────────
async def test_self_improving_probe(tmp_path: Path, model: str) -> bool:
    print("\n" + "=" * 72)
    print("T5: Self-improving probe — ask the agent to 'learn a new skill'")
    print("    (Expectation: W1 does NOT enable this — it is W2's job.)")
    print("=" * 72)

    from praisonaiagents import Agent
    from praisonaiagents.session import FileIdentityResolver, DefaultSessionStore
    from praisonai.bots._session import BotSessionManager

    resolver = FileIdentityResolver(path=tmp_path / "identity.json")
    resolver.link("telegram", "tg-77", "alice")
    store = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    agent = Agent(name="T5", instructions="You are a helpful assistant.", llm=model)
    mgr = BotSessionManager(platform="telegram", identity_resolver=resolver, store=store)

    out = await mgr.chat(
        agent, "tg-77",
        "I want you to learn a new skill called 'fizzbuzz_writer' that "
        "writes Python FizzBuzz. Add it to your permanent skills so a "
        "future session can use it. Then describe what you did.",
    )
    print(f"[Agent] {out}\n")

    # Probe whether anything actually got persisted to disk as a skill.
    candidate_paths = [
        Path.home() / ".praisonai" / "skills",
        Path.cwd() / ".praison" / "skills",
        Path.cwd() / ".claude" / "skills",
    ]
    found = []
    for p in candidate_paths:
        if p.exists():
            for child in p.glob("**/SKILL.md"):
                if "fizzbuzz" in child.read_text(errors="ignore").lower():
                    found.append(str(child))

    print(f"[Disk] SKILL.md files matching 'fizzbuzz': {found or 'none'}")
    print()
    print("  EXPECTED: W1 does NOT persist new skills — that's W2's curator loop.")
    print("  This test PASSES by demonstrating the gap, not by creating a file.")
    return True  # Always pass — this is a documentation/probe test.


# ─────────────────────────────────────────────────────────────────────────────
async def main() -> int:
    model = _pick_model()
    print(f"\n{'#' * 72}\n# W1 ROBUSTNESS SUITE — model: {model}\n{'#' * 72}")

    results = {}
    with tempfile.TemporaryDirectory() as td:
        for name, coro_factory in [
            ("T1", lambda p: test_three_platform_unification(p, model)),
            ("T2", lambda p: test_persistence_across_restart(p, model)),
            ("T3", lambda p: test_concurrent_users_isolated(p, model)),
            ("T4", lambda p: test_session_context_visible_to_tool(p, model)),
            ("T5", lambda p: test_self_improving_probe(p, model)),
        ]:
            sub = Path(td) / name
            sub.mkdir()
            try:
                results[name] = await coro_factory(sub)
            except Exception as e:
                print(f"\n  EXCEPTION in {name}: {type(e).__name__}: {e}")
                results[name] = False

    print(f"\n{'#' * 72}\n# SUMMARY\n{'#' * 72}")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
