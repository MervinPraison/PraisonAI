#!/usr/bin/env python3
"""W1 real agentic smoke test (high-level BotOS API, no manual mgr).

Uses the user-facing API only — ``Bot``, ``BotOS``, ``InMemoryIdentityResolver`` —
and exercises the same cross-platform-continuity scenario as
``smoke_w1_real.py`` but without touching ``BotSessionManager`` directly.

The mock-platform pattern: we instantiate two ``Bot``s but reach into
their adapter ``_session`` to drive the chat manually — this proves the
wire-up from ``BotOS(identity_resolver=...)`` → ``Bot._identity_resolver``
→ adapter splice works end-to-end.

Run::

    cd /Users/praison/worktrees/hermes-parity
    PYTHONPATH=src/praisonai-agents:src/praisonai python scripts/smoke_w1_botos_real.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile


async def main() -> int:
    from praisonaiagents import Agent
    from praisonaiagents.session import (
        FileIdentityResolver,
        DefaultSessionStore,
    )
    from praisonai.bots import Bot, BotOS

    if os.getenv("ANTHROPIC_API_KEY"):
        model = "claude-3-5-haiku-latest"
    elif os.getenv("GOOGLE_API_KEY"):
        model = "gemini-1.5-flash"
    else:
        model = "gpt-4o-mini"
    print(f"Using model: {model}")

    agent = Agent(
        name="W1BotOSTester",
        instructions=(
            "You are a helpful assistant. Always remember facts the user "
            "tells you and recall them precisely when asked."
        ),
        llm=model,
    )

    with tempfile.TemporaryDirectory() as tmp:
        # Persistent FileIdentityResolver — survives restart.
        resolver = FileIdentityResolver(path=f"{tmp}/identity.json")
        resolver.link("telegram", "tg-aaa", "alice-prod")
        resolver.link("discord", "dc-bbb", "alice-prod")
        store = DefaultSessionStore(session_dir=f"{tmp}/sessions")

        # Create two Bots; BotOS wires the resolver to each.
        bot_t = Bot("telegram", agent=agent, token="dummy")
        bot_d = Bot("discord", agent=agent, token="dummy")

        os_ = BotOS(bots=[bot_t, bot_d], identity_resolver=resolver)
        assert bot_t._identity_resolver is resolver
        assert bot_d._identity_resolver is resolver
        print(f"BotOS wired resolver to {os_.list_bots()}")

        # We don't need the network; build adapters lazily and use their
        # _session managers directly. Splicing logic is the same code
        # path real adapters take during start().
        adapter_t = bot_t._build_adapter()
        adapter_d = bot_d._build_adapter()
        # Inject the shared store into both managers so unification works.
        adapter_t._session._store = store
        adapter_d._session._store = store

        out_t = await adapter_t._session.chat(
            agent, "tg-aaa",
            "Remember this: my favourite music genre is darkwave.",
            chat_id="100", user_name="Alice",
        )
        print(f"\n[Telegram] {out_t}\n")

        out_d = await adapter_d._session.chat(
            agent, "dc-bbb",
            "Hey, what was my favourite music genre I just told you?",
            chat_id="200", user_name="Alice",
        )
        print(f"[Discord]  {out_d}\n")

        if out_d and "darkwave" in out_d.lower():
            print("PASS: BotOS-wired cross-platform continuity verified.")
            return 0
        print("FAIL: agent did not recall via BotOS-wired path.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
