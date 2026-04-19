# PraisonAI Platform

## Overview
PraisonAI is an AI Agents Framework for building, managing, and deploying multi-agent systems. This repository is a monorepo containing Python, TypeScript, and Rust implementations.

The main application running in this environment is the **PraisonAI Platform API** — a FastAPI-based REST API providing workspace management, authentication, issue tracking, and project management on top of the praisonaiagents SDK.

## Architecture

### Packages
- **`src/praisonai-agents/`** — Core `praisonaiagents` SDK (Python). Provides agent execution, auth protocols, db adapters, LLM orchestration.
- **`src/praisonai-platform/`** — Platform API (`praisonai-platform`). FastAPI REST API with SQLAlchemy/SQLite for workspace, auth, issues, projects, agents.
- **`src/praisonai/`** — High-level CLI/TUI framework. Integrates CrewAI/AutoGen.
- **`src/praisonai-ts/`** — TypeScript implementation using Vercel AI SDK.
- **`src/praisonai-rust/`** — Rust implementation using rig-core.

### Platform API Structure
```
src/praisonai-platform/
  praisonai_platform/
    api/
      app.py          # FastAPI app factory
      deps.py         # DI: get_db, get_current_user
      routes/         # auth, workspaces, projects, issues, agents, labels, dependencies, activity
      schemas.py      # Pydantic request/response models
    db/
      __init__.py
      base.py         # SQLAlchemy engine, session factory, Base
      models.py       # ORM models: User, Workspace, Member, Project, Issue, Comment, Agent, etc.
    services/         # Business logic services
    client/           # PlatformClient SDK
```

## Running the App
- Entry point: `run.py` (root)
- Command: `python run.py`
- Port: 5000
- Uses SQLite by default (`platform.db`), configurable via `PLATFORM_DATABASE_URL` env var

## Key Environment Variables
- `PLATFORM_JWT_SECRET` — JWT signing secret (default: `dev-secret-change-me`, required in production)
- `PLATFORM_DATABASE_URL` — Database URL (default: `sqlite+aiosqlite:///./platform.db`)
- `PLATFORM_JWT_TTL` — JWT token TTL in seconds (default: 30 days)
- `PLATFORM_ENV` — Set to `production` to enforce secrets check

## API Endpoints
- `GET /health` — Health check
- `POST /api/v1/auth/register` — Register user
- `POST /api/v1/auth/login` — Login
- `GET/POST /api/v1/workspaces/` — Workspace CRUD
- `GET/POST /api/v1/workspaces/{id}/projects/` — Project CRUD
- `GET/POST /api/v1/workspaces/{id}/issues/` — Issue CRUD
- `GET/POST /api/v1/workspaces/{id}/agents/` — Agent CRUD
- Interactive API docs: `GET /docs`

## Notes
- The `db` module (`src/praisonai-platform/praisonai_platform/db/`) was created during import setup — it was missing from the original repo.
- Both `praisonaiagents` and `praisonai-platform` packages are installed in editable mode.
