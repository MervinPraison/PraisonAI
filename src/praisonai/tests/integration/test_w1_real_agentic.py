"""W1 — Real agentic test for cross-platform unified session.

Spins up a real ``Agent`` (calls a real LLM), wires it into two
``BotSessionManager`` instances representing Telegram and Discord,
links the user via ``InMemoryIdentityResolver``, sends a fact on
"Telegram", then asks about it on "Discord". The agent must recall
the fact from the unified history.

Run manually::

    cd src/praisonai
    OPENAI_API_KEY=... pytest tests/integration/test_w1_real_agentic.py -s

This test is opt-in (skipped without ``RUN_REAL_AGENTIC=1``) so CI
without LLM credentials doesn't break.
"""

from __future__ import annotations

import os

import pytest


pytestmark = [
    pytest.mark.skipif(
        os.getenv("PRAISONAI_ALLOW_NETWORK", "") != "1"
        and os.getenv("RUN_REAL_AGENTIC", "") != "1",
        reason="Set PRAISONAI_ALLOW_NETWORK=1 to run real LLM tests",
    ),
    pytest.mark.network,
]


@pytest.mark.asyncio
async def test_cross_platform_continuity_real_llm(tmp_path):
    from praisonaiagents import Agent
    from praisonaiagents.session.identity import InMemoryIdentityResolver
    from praisonaiagents.session.store import DefaultSessionStore
    from praisonai.bots._session import BotSessionManager

    # 1. Real Agent
    # Pick first available provider
    if os.getenv("GOOGLE_API_KEY"):
        model = "gemini/gemini-2.5-flash"
    elif os.getenv("ANTHROPIC_API_KEY"):
        model = "claude-3-5-haiku-20241022"
    else:
        model = "gpt-4o-mini"

    agent = Agent(
        name="W1Tester",
        instructions=(
            "You are a helpful assistant. Always remember facts the user "
            "tells you and recall them precisely when asked."
        ),
        llm=model,
    )

    # 2. Identity resolver — same human, two platform IDs
    resolver = InMemoryIdentityResolver()
    resolver.link("telegram", "tg-12345", "alice-global")
    resolver.link("discord", "dc-67890", "alice-global")

    # 3. Shared persistent store
    store = DefaultSessionStore(session_dir=str(tmp_path))

    # 4. Two managers (one per platform), shared store + resolver
    mgr_t = BotSessionManager(
        platform="telegram", identity_resolver=resolver, store=store
    )
    mgr_d = BotSessionManager(
        platform="discord", identity_resolver=resolver, store=store
    )

    # 5. Tell agent a fact via "Telegram"
    fact_response = await mgr_t.chat(
        agent, "tg-12345",
        "Remember this: my favourite colour is octarine.",
    )
    print("\n[Telegram in] my favourite colour is octarine")
    print(f"[Telegram out] {fact_response}\n")

    # 6. Ask via "Discord" — agent should recall from unified history
    recall_response = await mgr_d.chat(
        agent, "dc-67890",
        "What did I just tell you my favourite colour was?",
    )
    print(f"[Discord in] What did I just tell you my favourite colour was?")
    print(f"[Discord out] {recall_response}\n")

    # The agent must mention "octarine" — proof the cross-platform mirror works
    assert "octarine" in recall_response.lower(), (
        f"Agent failed to recall cross-platform fact. Got: {recall_response}"
    )
