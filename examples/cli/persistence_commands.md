# Persistence CLI Commands

## Quick Reference

```bash
# Check database connectivity
praisonai persistence doctor \
  --conversation-url postgresql://localhost:5432/praisonai \
  --state-url redis://localhost:6379

# Run agent with persistence
praisonai persistence run \
  --conversation-url postgresql://localhost:5432/praisonai \
  --session-id my-session

# Resume a session
praisonai persistence resume \
  --conversation-url postgresql://localhost:5432/praisonai \
  --session-id my-session

# Export session to file
praisonai persistence export \
  --conversation-url postgresql://localhost:5432/praisonai \
  --session-id my-session \
  --output session_backup.jsonl

# Import session from file
praisonai persistence import \
  --conversation-url postgresql://localhost:5432/praisonai \
  --file session_backup.jsonl

# Check schema status
praisonai persistence status \
  --conversation-url postgresql://localhost:5432/praisonai \
  --state-url redis://localhost:6379

# Apply migrations
praisonai persistence migrate \
  --conversation-url postgresql://localhost:5432/praisonai \
  --state-url redis://localhost:6379
```

## Environment Variables

Instead of CLI flags, you can use environment variables:

```bash
export PRAISON_CONVERSATION_URL=postgresql://localhost:5432/praisonai
export PRAISON_STATE_URL=redis://localhost:6379
export PRAISON_KNOWLEDGE_URL=http://localhost:6333

# Then run without URL flags
praisonai persistence doctor
praisonai persistence status
```

## Docker Setup

```bash
# Start all services
docker run -d --name praison-postgres \
  -e POSTGRES_PASSWORD=praison123 \
  -e POSTGRES_DB=praisonai \
  -p 5432:5432 postgres:16

docker run -d --name praison-redis \
  -p 6379:6379 redis:7

docker run -d --name praison-qdrant \
  -p 6333:6333 -p 6334:6334 qdrant/qdrant

# Verify
docker ps
```

## Example Workflow

```bash
# 1. Start services
docker-compose up -d

# 2. Check connectivity
praisonai persistence doctor

# 3. Run agent
praisonai persistence run --session-id demo-session

# 4. Export for backup
praisonai persistence export --session-id demo-session --output backup.jsonl

# 5. Import to another environment
praisonai persistence import --file backup.jsonl
```
