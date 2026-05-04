"""AgentOS FastAPI backend."""
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

try:
    from . import db as agentdb  # package import (uvicorn backend.main:app)
except ImportError:  # pragma: no cover - script execution fallback
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import db as agentdb  # type: ignore


@asynccontextmanager
async def lifespan(app: FastAPI):
    agentdb.init_db()
    yield


app = FastAPI(title="AgentOS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class AgentCreate(BaseModel):
    # Accept unknown legacy fields (role, tools, connections) without error.
    # `protected_namespaces=()` silences Pydantic v2 warnings about the
    # `model` field name colliding with its protected namespace.
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    name: str
    instructions: str = ""
    model: Optional[str] = None
    llm: Optional[str] = None  # legacy alias for `model`
    status: str = "active"
    generation: int = 1
    parent_id: Optional[str] = None
    performance_score: Optional[float] = None
    token_spend: int = 0
    exit_summary: Optional[str] = None


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    name: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    llm: Optional[str] = None  # legacy alias for `model`
    status: Optional[str] = None
    generation: Optional[int] = None
    parent_id: Optional[str] = None
    performance_score: Optional[float] = None
    token_spend: Optional[int] = None
    exit_summary: Optional[str] = None


class ChatMessage(BaseModel):
    message: str


def _validate_status(status: str) -> None:
    if status not in agentdb.ALLOWED_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(agentdb.ALLOWED_STATUS)}",
        )


@app.get("/agents")
def list_agents():
    return agentdb.list_agents()


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    agent = agentdb.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.post("/agents", status_code=201)
def create_agent(data: AgentCreate):
    _validate_status(data.status)
    if data.parent_id and not agentdb.get_agent(data.parent_id):
        raise HTTPException(status_code=400, detail="parent_id does not exist")
    record = {
        "id": f"agent-{uuid.uuid4().hex[:8]}",
        "name": data.name,
        "instructions": data.instructions,
        "model": data.model or data.llm or "gpt-4o-mini",
        "status": data.status,
        "generation": data.generation,
        "parent_id": data.parent_id,
        "performance_score": data.performance_score,
        "token_spend": data.token_spend,
        "exit_summary": data.exit_summary,
    }
    return agentdb.create_agent(record)


@app.put("/agents/{agent_id}")
def update_agent(agent_id: str, data: AgentUpdate):
    fields = data.model_dump(exclude_none=True)
    # Legacy `llm` alias -> `model`
    if "llm" in fields and "model" not in fields:
        fields["model"] = fields["llm"]
    fields.pop("llm", None)

    if "status" in fields:
        _validate_status(fields["status"])
    if fields.get("parent_id") and not agentdb.get_agent(fields["parent_id"]):
        raise HTTPException(status_code=400, detail="parent_id does not exist")

    updated = agentdb.update_agent(agent_id, fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return updated


@app.delete("/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: str):
    # chat_history rows cascade via FK ON DELETE CASCADE
    if not agentdb.delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")


@app.post("/agents/{agent_id}/chat")
def chat_with_agent(agent_id: str, body: ChatMessage):
    agent = agentdb.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    activity: List[Dict] = []
    response_text = ""

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            from praisonaiagents import Agent
            activity.append(_log("tool", f"Initializing {agent['model']} agent"))
            pa_agent = Agent(
                name=agent["name"],
                instructions=agent["instructions"],
                llm=agent["model"],
            )
            activity.append(_log("tool", "Running agent inference"))
            result = pa_agent.start(body.message)
            response_text = str(result)
            activity.append(_log("success", "Agent response generated"))
        except Exception as e:
            activity.append(_log("error", f"Agent error: {str(e)[:120]}"))
            response_text = f"Agent encountered an error: {str(e)[:200]}"
    else:
        activity.append(_log("message", "No OPENAI_API_KEY set — using demo mode"))
        response_text = _demo_response(agent, body.message)
        activity.append(_log("success", "Demo response generated"))

    entry = {
        "id": uuid.uuid4().hex[:8],
        "user_message": body.message,
        "agent_response": response_text,
        "activity": activity,
        "timestamp": _now_iso(),
    }
    agentdb.add_history_entry(agent_id, entry)
    return entry


@app.get("/agents/{agent_id}/history")
def get_history(agent_id: str):
    return agentdb.list_history(agent_id)


@app.delete("/agents/{agent_id}/history", status_code=204)
def clear_history(agent_id: str):
    agentdb.clear_history(agent_id)


@app.get("/agents/{agent_id}/activity")
def get_activity(agent_id: str):
    return agentdb.list_activity(agent_id, limit=100)


def _log(action_type: str, description: str) -> Dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "timestamp": _now_iso(),
        "type": action_type,
        "description": description,
    }


def _demo_response(agent: Dict, message: str) -> str:
    name = agent.get("name", "Agent")
    return (
        f"Hi! I'm {name}. "
        f"You asked: \"{message}\"\n\n"
        f"I'm running on {agent.get('model', 'unknown model')}. "
        f"To enable real AI responses, set your OPENAI_API_KEY environment variable."
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
