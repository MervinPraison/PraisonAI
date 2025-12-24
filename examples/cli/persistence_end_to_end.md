# PraisonAI Persistence CLI - End-to-End Guide

This guide demonstrates the CLI commands for database persistence.

## Prerequisites

```bash
pip install "praisonai[tools]"

# Start Docker containers
docker run -d --name praison-postgres -p 5432:5432 \
    -e POSTGRES_PASSWORD=praison123 \
    -e POSTGRES_DB=praisonai \
    postgres:16

docker run -d --name praison-qdrant -p 6333:6333 qdrant/qdrant
docker run -d --name praison-redis -p 6379:6379 redis:7
```

## 1. Doctor Command - Validate Connectivity

```bash
# Check all stores
praisonai persistence doctor \
    --conversation-url "postgresql://postgres:praison123@localhost:5432/praisonai" \
    --knowledge-url "http://localhost:6333" \
    --state-url "redis://localhost:6379"
```

**Expected Output:**
```
==================================================
PraisonAI Persistence Doctor
==================================================

[Conversation Store] Testing: postgresql://postgres:****@localhost:5432/praisonai
  ✅ Connected (postgres)

[Knowledge Store] Testing: http://localhost:6333
  ✅ Connected (qdrant)

[State Store] Testing: redis://localhost:6379
  ✅ Connected (redis)

==================================================
Results: 3/3 stores connected successfully
==================================================
```

## 2. Run Command - Execute Agent with Persistence

```bash
# Run agent with persistence (dry-run first)
praisonai persistence run \
    --session-id "cli-demo-001" \
    --conversation-url "postgresql://postgres:praison123@localhost:5432/praisonai" \
    --dry-run \
    "Hello, my name is Bob"

# Actually run it
praisonai persistence run \
    --session-id "cli-demo-001" \
    --conversation-url "postgresql://postgres:praison123@localhost:5432/praisonai" \
    "Hello, my name is Bob"
```

**Expected Output:**
```
[Session: cli-demo-001]
Agent: Hello Bob! Nice to meet you. How can I help you today?
```

## 3. Resume Command - Continue a Session

```bash
# Show history
praisonai persistence resume \
    --session-id "cli-demo-001" \
    --conversation-url "postgresql://postgres:praison123@localhost:5432/praisonai" \
    --show-history

# Continue conversation
praisonai persistence resume \
    --session-id "cli-demo-001" \
    --conversation-url "postgresql://postgres:praison123@localhost:5432/praisonai" \
    --continue "What's my name?"
```

**Expected Output:**
```
[Session: cli-demo-001]
Messages in history: 2

--- Conversation History ---
[USER] Hello, my name is Bob
[ASSISTANT] Hello Bob! Nice to meet you...
--- End History ---

Agent: Your name is Bob!
```

## Environment Variables

Instead of passing URLs on command line, use environment variables:

```bash
export PRAISON_CONVERSATION_URL="postgresql://postgres:praison123@localhost:5432/praisonai"
export PRAISON_KNOWLEDGE_URL="http://localhost:6333"
export PRAISON_STATE_URL="redis://localhost:6379"
export OPENAI_API_KEY="your-key"

# Now commands are simpler
praisonai persistence doctor --all
praisonai persistence run --session-id "my-session" "Hello!"
```

## Full CLI Reference

```
praisonai persistence --help
praisonai persistence doctor --help
praisonai persistence run --help
praisonai persistence resume --help
```
