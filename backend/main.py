"""AgentOS FastAPI backend."""
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="AgentOS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(__file__)
AGENTS_FILE = os.path.join(BASE_DIR, "agents_store.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history_store.json")


def load_agents() -> List[Dict]:
    if not os.path.exists(AGENTS_FILE):
        return []
    with open(AGENTS_FILE) as f:
        return json.load(f)


def save_agents(agents: List[Dict]) -> None:
    with open(AGENTS_FILE, "w") as f:
        json.dump(agents, f, indent=2)


def load_history() -> Dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE) as f:
        return json.load(f)


def save_history(history: Dict) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


class AgentCreate(BaseModel):
    name: str
    role: str
    instructions: str = ""
    tools: List[str] = []
    connections: List[str] = []
    llm: str = "gpt-4o-mini"
    status: str = "active"


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    instructions: Optional[str] = None
    tools: Optional[List[str]] = None
    connections: Optional[List[str]] = None
    llm: Optional[str] = None
    status: Optional[str] = None


class ChatMessage(BaseModel):
    message: str


@app.get("/agents")
def list_agents():
    return load_agents()


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    agents = load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.post("/agents", status_code=201)
def create_agent(data: AgentCreate):
    agents = load_agents()
    agent = {
        "id": f"agent-{uuid.uuid4().hex[:8]}",
        "name": data.name,
        "role": data.role,
        "instructions": data.instructions,
        "tools": data.tools,
        "connections": data.connections,
        "llm": data.llm,
        "status": data.status,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    agents.append(agent)
    save_agents(agents)
    return agent


@app.put("/agents/{agent_id}")
def update_agent(agent_id: str, data: AgentUpdate):
    agents = load_agents()
    idx = next((i for i, a in enumerate(agents) if a["id"] == agent_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    for field, value in data.model_dump(exclude_none=True).items():
        agents[idx][field] = value
    save_agents(agents)
    return agents[idx]


@app.delete("/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: str):
    agents = load_agents()
    new_agents = [a for a in agents if a["id"] != agent_id]
    if len(new_agents) == len(agents):
        raise HTTPException(status_code=404, detail="Agent not found")
    save_agents(new_agents)
    history = load_history()
    history.pop(agent_id, None)
    save_history(history)


@app.post("/agents/{agent_id}/chat")
def chat_with_agent(agent_id: str, body: ChatMessage):
    agents = load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    activity = []
    response_text = ""

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            from praisonaiagents import Agent
            activity.append(_log("tool", f"Initializing {agent['llm']} agent"))
            pa_agent = Agent(
                name=agent["name"],
                role=agent["role"],
                instructions=agent["instructions"],
                llm=agent["llm"],
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

    history = load_history()
    if agent_id not in history:
        history[agent_id] = []

    entry = {
        "id": uuid.uuid4().hex[:8],
        "user_message": body.message,
        "agent_response": response_text,
        "activity": activity,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    history[agent_id].append(entry)
    save_history(history)
    return entry


@app.get("/agents/{agent_id}/history")
def get_history(agent_id: str):
    history = load_history()
    return history.get(agent_id, [])


@app.delete("/agents/{agent_id}/history", status_code=204)
def clear_history(agent_id: str):
    history = load_history()
    history[agent_id] = []
    save_history(history)


@app.get("/agents/{agent_id}/activity")
def get_activity(agent_id: str):
    history = load_history()
    all_entries = history.get(agent_id, [])
    activity = []
    for entry in reversed(all_entries):
        activity.extend(entry.get("activity", []))
    return activity[-100:]


def _log(action_type: str, description: str) -> Dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "type": action_type,
        "description": description,
    }


def _demo_response(agent: Dict, message: str) -> str:
    name = agent.get("name", "Agent")
    role = agent.get("role", "assistant")
    tools = agent.get("tools", [])
    tool_str = ", ".join(tools) if tools else "no tools"
    return (
        f"Hi! I'm {name}, a {role}. "
        f"You asked: \"{message}\"\n\n"
        f"I have access to: {tool_str}. "
        f"To enable real AI responses, set your OPENAI_API_KEY environment variable."
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
