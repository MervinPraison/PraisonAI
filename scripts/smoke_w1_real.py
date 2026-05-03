#!/usr/bin/env python3
"""W1 real agentic smoke test (bypasses pytest conftest gating).

Runs::

    cd src/praisonai
    python ../../scripts/smoke_w1_real.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile


async def main() -> int:
    from praisonaiagents import Agent
    from praisonaiagents.session.identity import InMemoryIdentityResolver
    from praisonaiagents.session.store import DefaultSessionStore
    from praisonai.bots._session import BotSessionManager

    if os.getenv("ANTHROPIC_API_KEY"):
        model = "claude-3-5-haiku-latest"
    elif os.getenv("GOOGLE_API_KEY"):
        model = "gemini-1.5-flash"
    else:
        model = "gpt-4o-mini"
    print(f"Using model: {model}")

    agent = Agent(
        name="W1Tester",
        instructions=(
            "You are a helpful assistant. Always remember facts the user "
            "tells you and recall them precisely when asked."
        ),
        llm=model,
    )

    resolver = InMemoryIdentityResolver()
    resolver.link("telegram", "tg-12345", "alice-global")
    resolver.link("discord", "dc-67890", "alice-global")

    with tempfile.TemporaryDirectory() as tmp_path:
        store = DefaultSessionStore(session_dir=tmp_path)
        mgr_t = BotSessionManager(
            platform="telegram", identity_resolver=resolver, store=store
        )
        mgr_d = BotSessionManager(
            platform="discord", identity_resolver=resolver, store=store
        )

        out_t = await mgr_t.chat(
            agent, "tg-12345",
            "Remember this: my favourite colour is octarine.",
        )
        print(f"\n[Telegram] in:  Remember this: my favourite colour is octarine.")
        print(f"[Telegram] out: {out_t}\n")

        out_d = await mgr_d.chat(
            agent, "dc-67890",
            "What did I just tell you my favourite colour was?",
        )
        print(f"[Discord]  in:  What did I just tell you my favourite colour was?")
        print(f"[Discord]  out: {out_d}\n")

        if out_d and "octarine" in out_d.lower():
            print("PASS: Cross-platform context recalled.")
            return 0
        print("FAIL: Agent did not recall cross-platform fact.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
