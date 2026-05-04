# AgentOS — PraisonAI Agent Dashboard

## Overview
A full-stack web dashboard for managing and interacting with AI agents powered by PraisonAI.

## Architecture

### Frontend (React + Vite) — Port 5000
```
frontend/
  index.html               # Entry point, Tailwind CDN, Google Fonts
  vite.config.js           # Vite config, proxy /api → localhost:8000
  src/
    main.jsx               # React root
    App.jsx                # Main app layout, state management
    components/
      Sidebar.jsx          # Agent list + New Agent button
      ChatPanel.jsx        # Conversation with activity collapsible
      AgentDetail.jsx      # Agent config view + stats
      ActivityLog.jsx      # Real-time activity feed (right panel)
      AgentForm.jsx        # Create/edit agent modal
```

### Backend (FastAPI) — Port 8000
```
backend/
  main.py                  # FastAPI app, JSON storage
  agents_store.json        # Agent definitions (persisted)
  history_store.json       # Conversation history (persisted)
```

## Running
- Frontend: `python run.py` (starts Vite dev server on port 5000)
- Backend: `python backend/main.py` (starts FastAPI on port 8000)

## API Endpoints
- `GET /agents` — list agents
- `POST /agents` — create agent
- `PUT /agents/{id}` — update agent
- `DELETE /agents/{id}` — delete agent
- `POST /agents/{id}/chat` — send message, get response + activity
- `GET /agents/{id}/history` — conversation history
- `DELETE /agents/{id}/history` — clear history
- `GET /agents/{id}/activity` — activity log

## Key Environment Variables
- `OPENAI_API_KEY` — enables real AI responses via praisonaiagents
  (without it, demo mode is used)

## Platform API (legacy)
The original praisonai-platform FastAPI app is still available in:
- `src/praisonai-platform/` — multi-tenant workspace/issue tracking API
- `src/praisonai-agents/` — core praisonaiagents SDK
