"""
Perseus Vault memory backend for PraisonAI.

Perseus Vault (https://github.com/Perseus-Computing-LLC/perseus-vault) is a
single static-binary MCP memory server: SQLite + FTS5 + bundled ONNX
embeddings, optional AES-256-GCM, fully local and offline. This example wires
it into a PraisonAI Agent as the memory backend.

Prereqs:
  1. Install the perseus-vault binary (single file, no Python deps) and put it
     on PATH, or set PERSEUS_VAULT_BIN=/path/to/perseus-vault.
  2. pip install praisonaiagents

Run:
  python perseus_vault_memory.py
"""

from praisonaiagents import Agent, Task, PraisonAIAgents


def main():
    # The "perseus_vault" adapter is registered out of the box. Point it at the
    # binary + a DB file; short/long-term memory map onto vault categories.
    agent = Agent(
        name="Researcher",
        role="Research assistant with persistent, local-first memory",
        goal="Remember findings across sessions and recall them on demand",
        memory=True,
    )

    task = Task(
        description="Summarize why local-first agent memory matters, and remember it.",
        expected_output="A short summary, persisted to Perseus Vault.",
        agent=agent,
    )

    workflow = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        memory=True,
        memory_config={
            "provider": "perseus_vault",
            "config": {
                # Falls back to PERSEUS_VAULT_BIN / PERSEUS_VAULT_DB env if omitted.
                "binary": "perseus-vault",
                "db_path": "./praisonai-perseus-vault.db",
                # Optional: path to an AES-256-GCM key file for encryption at rest.
                # "encryption_key": "/path/to/key",
                "search_mode": "hybrid",  # fts5 | dense | hybrid
            },
        },
    )

    workflow.start()


if __name__ == "__main__":
    main()
