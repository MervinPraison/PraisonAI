"""
Feedo memory example for PraisonAI.

Feedo is a decentralized storage + semantic search network. This example wires
it up as the agent's memory backend.

Prerequisites:
    pip install praisonaiagents feedo-sdk

Get a usage key at https://feedo.ink/identity.html (connect a wallet, register
a DID, generate a usage key), then set it below and run this script.
"""

from praisonaiagents import Agent

# Configure Feedo as the agent's memory backend.
#
# Only `usage_key` is required — the owner DID is auto-resolved from the
# usage key's delegation stored on the Feedo consensus network.
#
# Options:
#   user_id  — isolate memories per user (defaults to your DID)
#   private  — True (default): owner-only memories; False: public memories
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with long-term memory.",
    memory={
        "provider": "feedo",
        "config": {
            "usage_key": "0x...",     # your delegated usage key
            "user_id": "user123",     # optional
            "private": True,          # optional (default True)
        },
    },
)

# The agent now stores and recalls memories on the Feedo decentralized network.
agent.start("Hi! Remember that I prefer dark mode.")
