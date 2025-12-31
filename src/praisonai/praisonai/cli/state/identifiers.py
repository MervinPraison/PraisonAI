"""
Identifier generation for PraisonAI CLI.

Provides stable, unique identifiers for runs, traces, and agents.
"""

import hashlib
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


def generate_run_id() -> str:
    """
    Generate a unique run ID.
    
    Format: run_YYYYMMDD_HHMMSS_<random>
    Example: run_20241231_143022_a1b2c3
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    random_suffix = secrets.token_hex(3)  # 6 characters
    return f"run_{timestamp}_{random_suffix}"


def generate_trace_id() -> str:
    """
    Generate a unique trace ID.
    
    Format: trace_<random>
    Example: trace_a1b2c3d4e5f6
    """
    return f"trace_{secrets.token_hex(6)}"


def generate_agent_id(agent_name: str, run_id: str, index: int = 0) -> str:
    """
    Generate a deterministic agent ID.
    
    The ID is deterministic based on agent name, run ID, and index,
    ensuring consistent IDs across the same run.
    
    Format: agent_<hash>_<index>
    Example: agent_a1b2c3_001
    
    Args:
        agent_name: Name of the agent
        run_id: Current run ID
        index: Agent index within the run
        
    Returns:
        Deterministic agent ID
    """
    # Create deterministic hash from agent name and run ID
    hash_input = f"{agent_name}:{run_id}:{index}"
    hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:6]
    return f"agent_{hash_value}_{index:03d}"


@dataclass
class RunContext:
    """
    Context for a single run.
    
    Holds all identifiers and metadata for the current execution.
    """
    run_id: str = field(default_factory=generate_run_id)
    trace_id: str = field(default_factory=generate_trace_id)
    start_time: datetime = field(default_factory=datetime.utcnow)
    
    # Agent tracking
    agents: Dict[str, str] = field(default_factory=dict)  # name -> agent_id
    _agent_counter: int = field(default=0, repr=False)
    
    # Metadata
    config_summary: Dict[str, str] = field(default_factory=dict)
    workspace: Optional[str] = None
    
    def get_agent_id(self, agent_name: str) -> str:
        """
        Get or create an agent ID for the given agent name.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Agent ID (creates new one if not exists)
        """
        if agent_name not in self.agents:
            agent_id = generate_agent_id(agent_name, self.run_id, self._agent_counter)
            self.agents[agent_name] = agent_id
            self._agent_counter += 1
        return self.agents[agent_name]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "start_time": self.start_time.isoformat(),
            "agents": self.agents.copy(),
            "config_summary": self.config_summary.copy(),
            "workspace": self.workspace,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "RunContext":
        """Create from dictionary."""
        ctx = cls(
            run_id=data.get("run_id", generate_run_id()),
            trace_id=data.get("trace_id", generate_trace_id()),
            workspace=data.get("workspace"),
        )
        ctx.agents = data.get("agents", {})
        ctx.config_summary = data.get("config_summary", {})
        ctx._agent_counter = len(ctx.agents)
        
        start_time = data.get("start_time")
        if start_time:
            try:
                ctx.start_time = datetime.fromisoformat(start_time)
            except (ValueError, TypeError):
                pass
        
        return ctx


# Thread-local storage for current context
_context_local = threading.local()


def get_current_context() -> Optional[RunContext]:
    """Get the current run context for this thread."""
    return getattr(_context_local, "context", None)


def set_current_context(context: Optional[RunContext]) -> None:
    """Set the current run context for this thread."""
    _context_local.context = context


def create_context(workspace: Optional[str] = None) -> RunContext:
    """
    Create a new run context and set it as current.
    
    Args:
        workspace: Optional workspace path
        
    Returns:
        New RunContext instance
    """
    context = RunContext(workspace=workspace or os.getcwd())
    set_current_context(context)
    return context


def clear_context() -> None:
    """Clear the current run context."""
    set_current_context(None)
