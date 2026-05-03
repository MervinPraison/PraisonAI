#!/usr/bin/env python3
"""N4 — Real agentic smoke test for inbound DLQ.

Scenario:
  1. Real Agent (anthropic/claude-haiku-4-5 or gemini/2.5-flash).
  2. First chat attempt fails (we patch agent.chat to raise once).
  3. BotSessionManager enqueues to DLQ.
  4. Operator replays the DLQ — second attempt hits the **real** LLM
     and produces a real reply.
  5. Assert DLQ is empty and the reply contains the expected fact.

Run::

    cd /Users/praison/worktrees/n4-dlq
    PYTHONPATH=src/praisonai-agents:src/praisonai python scripts/smoke_n4_real.py
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
    raise RuntimeError(
        "No supported API key found. Set ANTHROPIC_API_KEY or GOOGLE_API_KEY to run smoke tests."
    )


async def main() -> int:
    from praisonaiagents import Agent
    from praisonai.bots import BotSessionManager, InboundDLQ

    model = _pick_model()
    print(f"Model: {model}")

    agent = Agent(
        name="N4Tester",
        instructions="You are a helpful assistant. Reply with one short sentence.",
        llm=model,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dlq_path = Path(tmp) / "dlq.sqlite"
        dlq = InboundDLQ(path=dlq_path)
        mgr = BotSessionManager(platform="telegram", dlq=dlq)

        # 1) Force first chat to fail by monkey-patching agent.chat.
        original_chat = agent.chat

        def failing_chat_first_time(prompt, *a, **kw):
            agent.chat = original_chat  # next call goes to real LLM
            raise RuntimeError("simulated LLM 503")

        agent.chat = failing_chat_first_time

        prompt = "What is 2 plus 2? Answer with a single digit."
        print(f"\n[1] Sending failing message: {prompt!r}")
        try:
            await mgr.chat(
                agent, "tg-1", prompt,
                chat_id="100", user_name="OpsTester",
            )
            print("UNEXPECTED: first call did not raise.")
            return 1
        except RuntimeError as e:
            print(f"   Caught expected error: {e}")

        # 2) DLQ must hold one entry.
        if dlq.size() != 1:
            print(f"FAIL: expected DLQ size 1, got {dlq.size()}")
            return 1
        print(f"   DLQ size after fail: {dlq.size()}  ✅")

        # 3) Replay through the (now-restored) real LLM.
        print("\n[2] Replaying DLQ via real LLM …")
        seen_replies = []

        async def replayer(entry):
            try:
                reply = await mgr.chat(
                    agent, entry.user_id, entry.prompt,
                    chat_id=entry.chat_id,
                    user_name=entry.user_name,
                )
                seen_replies.append(reply)
                return True
            except Exception as e:
                print(f"   replay failed: {e}")
                return False

        succeeded, failed = await dlq.replay(replayer)
        print(f"   succeeded={succeeded}, failed={failed}, "
              f"remaining={dlq.size()}")

        if succeeded != 1 or failed != 0 or dlq.size() != 0:
            print("FAIL: replay outcome wrong.")
            return 1

        reply = seen_replies[0]
        print(f"\n[Real LLM reply] {reply}\n")

        if reply and "4" in reply:
            print("PASS: DLQ → replay → real LLM produced expected '4'.")
            return 0
        print("FAIL: reply did not contain expected answer.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
