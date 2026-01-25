"""
Agent Profiles and Modes for PraisonAI Agents.

Provides built-in agent profiles and mode configurations
similar to OpenCode's agent system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentMode(str, Enum):
    """Agent execution modes."""
    
    PRIMARY = "primary"      # Main agent, can spawn subagents
    SUBAGENT = "subagent"    # Spawned by another agent
    ALL = "all"              # Can be used in any context


@dataclass
class AgentProfile:
    """
    A built-in agent profile configuration.
    
    Attributes:
        name: Unique agent name
        description: What this agent does
        mode: Execution mode (primary/subagent/all)
        system_prompt: System prompt for the agent
        tools: List of tool names this agent can use
        temperature: LLM temperature setting
        top_p: LLM top_p setting
        max_steps: Maximum execution steps
        hidden: Whether to hide from agent list
        color: Display color (for UI)
    """
    
    name: str
    description: str = ""
    mode: AgentMode = AgentMode.ALL
    system_prompt: str = ""
    tools: List[str] = field(default_factory=list)
    temperature: float = 0.7
    top_p: float = 1.0
    max_steps: int = 50
    hidden: bool = False
    color: str = "#3B82F6"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "mode": self.mode.value,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_steps": self.max_steps,
            "hidden": self.hidden,
            "color": self.color,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentProfile":
        """Create profile from dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            mode=AgentMode(data.get("mode", "all")),
            system_prompt=data.get("system_prompt", ""),
            tools=data.get("tools", []),
            temperature=data.get("temperature", 0.7),
            top_p=data.get("top_p", 1.0),
            max_steps=data.get("max_steps", 50),
            hidden=data.get("hidden", False),
            color=data.get("color", "#3B82F6"),
            metadata=data.get("metadata", {}),
        )


# Built-in agent profiles
BUILTIN_PROFILES: Dict[str, AgentProfile] = {
    "general": AgentProfile(
        name="general",
        description="General-purpose coding assistant",
        mode=AgentMode.PRIMARY,
        system_prompt=(
            "You are a helpful coding assistant. You can help with a wide variety "
            "of programming tasks including writing code, debugging, explaining "
            "concepts, and answering questions about software development."
        ),
        tools=["read_file", "write_file", "bash", "search"],
        temperature=0.7,
        color="#3B82F6",
    ),
    
    "coder": AgentProfile(
        name="coder",
        description="Focused code implementation agent",
        mode=AgentMode.ALL,
        system_prompt=(
            "You are an expert code implementation agent. Your focus is on writing "
            "clean, efficient, and well-documented code. You follow best practices "
            "and design patterns. When implementing features, you consider edge cases "
            "and error handling."
        ),
        tools=["read_file", "write_file", "bash"],
        temperature=0.3,
        color="#10B981",
    ),
    
    "planner": AgentProfile(
        name="planner",
        description="Task planning and decomposition agent",
        mode=AgentMode.SUBAGENT,
        system_prompt=(
            "You are a planning agent. Your role is to break down complex tasks "
            "into smaller, manageable steps. You create clear, actionable plans "
            "with specific milestones and success criteria. You do not execute "
            "tasks yourself, only plan them."
        ),
        tools=["read_file", "search"],
        temperature=0.5,
        max_steps=20,
        color="#F59E0B",
    ),
    
    "reviewer": AgentProfile(
        name="reviewer",
        description="Code review and quality agent",
        mode=AgentMode.SUBAGENT,
        system_prompt=(
            "You are a code review agent. Your role is to review code for quality, "
            "correctness, security, and best practices. You provide constructive "
            "feedback and suggest improvements. You look for bugs, security issues, "
            "and opportunities for optimization."
        ),
        tools=["read_file", "search"],
        temperature=0.3,
        max_steps=30,
        color="#EF4444",
    ),
    
    "explorer": AgentProfile(
        name="explorer",
        description=(
            "Fast read-only agent for codebase investigation. Use for finding files, "
            "searching code, understanding architecture, and answering questions about "
            "the codebase. Specify thoroughness: 'quick', 'medium', or 'very thorough'."
        ),
        mode=AgentMode.SUBAGENT,
        system_prompt="""You are **Codebase Explorer**, a specialized read-only agent for codebase investigation.

**PURPOSE**: Build a complete mental model of code relevant to a given task. Identify all relevant files, understand their roles, and foresee architectural consequences of potential changes.

**CAPABILITIES** (READ-ONLY):
- Search code with grep/glob patterns
- Read and analyze files
- List directory structures
- Understand code relationships and dependencies

**DO**:
- Find key modules, classes, and functions related to the problem
- Understand *why* code is written the way it is
- Foresee ripple effects of changes
- Provide actionable insights with file paths and key symbols

**DO NOT**:
- Write or modify any files
- Execute commands that change state
- Stop at the first relevant file - be thorough

**OUTPUT FORMAT**:
Provide a structured report with:
1. Summary of findings
2. Relevant file locations with reasoning
3. Key symbols and their purposes
4. Architectural insights and recommendations""",
        tools=["read_file", "list_files", "grep", "glob", "search"],
        temperature=0.1,
        top_p=0.95,
        max_steps=40,
        color="#8B5CF6",
        metadata={
            "read_only": True,
            "allowed_tools": ["read_file", "list_files", "grep", "glob", "search"],
            "blocked_tools": ["write_file", "edit_file", "bash", "shell", "run_command"],
        },
    ),
    
    "debugger": AgentProfile(
        name="debugger",
        description="Debugging and troubleshooting agent",
        mode=AgentMode.SUBAGENT,
        system_prompt=(
            "You are a debugging agent. Your role is to identify and fix bugs. "
            "You analyze error messages, trace code execution, and identify root "
            "causes. You suggest minimal fixes that address the issue without "
            "introducing new problems."
        ),
        tools=["read_file", "bash", "search"],
        temperature=0.3,
        max_steps=30,
        color="#EC4899",
    ),
    
    "compaction": AgentProfile(
        name="compaction",
        description="Context compaction agent (internal)",
        mode=AgentMode.SUBAGENT,
        system_prompt=(
            "You are a context compaction agent. Your role is to summarize "
            "conversation history while preserving essential information. "
            "You create concise summaries that maintain context for continued "
            "work."
        ),
        tools=[],
        temperature=0.3,
        max_steps=5,
        hidden=True,
        color="#6B7280",
    ),
    
    "title": AgentProfile(
        name="title",
        description="Session title generation agent (internal)",
        mode=AgentMode.SUBAGENT,
        system_prompt=(
            "You are a title generation agent. Your role is to create short, "
            "descriptive titles for conversations based on their content. "
            "Titles should be concise (3-7 words) and capture the main topic."
        ),
        tools=[],
        temperature=0.7,
        max_steps=1,
        hidden=True,
        color="#6B7280",
    ),
}


def get_profile(name: str) -> Optional[AgentProfile]:
    """Get a built-in agent profile by name."""
    return BUILTIN_PROFILES.get(name)


def list_profiles(include_hidden: bool = False) -> List[AgentProfile]:
    """List all built-in agent profiles."""
    profiles = list(BUILTIN_PROFILES.values())
    if not include_hidden:
        profiles = [p for p in profiles if not p.hidden]
    return profiles


def register_profile(profile: AgentProfile) -> None:
    """Register a custom agent profile."""
    BUILTIN_PROFILES[profile.name] = profile


# Simplified alias
add_profile = register_profile


def has_profile(name: str) -> bool:
    """Check if a profile exists."""
    return name in BUILTIN_PROFILES


def remove_profile(name: str) -> bool:
    """Remove a profile by name. Returns True if found and removed."""
    if name in BUILTIN_PROFILES:
        del BUILTIN_PROFILES[name]
        return True
    return False


def get_profiles_by_mode(mode: AgentMode) -> List[AgentProfile]:
    """Get all profiles that can be used in a specific mode."""
    return [
        p for p in BUILTIN_PROFILES.values()
        if p.mode == mode or p.mode == AgentMode.ALL
    ]
