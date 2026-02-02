"""
Migration Specification for Agent-Driven Code Migration.

This module defines the feature mapping specification used by the migration agents
to convert code from various agent framework patterns to PraisonAI format.

The spec is framework-agnostic - it describes patterns generically without
explicitly naming source frameworks.

Design:
- Pattern-based: Describes what to look for, not where it comes from
- Dynamic: LLM agents use this spec to understand and convert code
- Extensible: New patterns can be added without code changes
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PatternSpec:
    """Specification for a code pattern to detect and convert."""
    name: str
    description: str
    source_indicators: List[str]  # What to look for in source code
    target_equivalent: str  # PraisonAI equivalent
    parameter_mapping: Dict[str, str]  # source_param -> praisonai_param
    notes: str = ""


@dataclass
class MigrationSpec:
    """Complete migration specification for agent-driven conversion."""
    
    # Agent patterns
    agent_patterns: List[PatternSpec] = field(default_factory=list)
    
    # Task/Step patterns
    task_patterns: List[PatternSpec] = field(default_factory=list)
    
    # Team/Orchestrator patterns
    team_patterns: List[PatternSpec] = field(default_factory=list)
    
    # Workflow patterns
    workflow_patterns: List[PatternSpec] = field(default_factory=list)
    
    # Import patterns
    import_patterns: Dict[str, str] = field(default_factory=dict)
    
    # Method patterns
    method_patterns: Dict[str, str] = field(default_factory=dict)
    
    def to_prompt(self) -> str:
        """Convert spec to a prompt for LLM agents."""
        lines = [
            "# Code Migration Specification",
            "",
            "Use this specification to convert agent code to PraisonAI format.",
            "",
            "## Agent Patterns",
            ""
        ]
        
        for p in self.agent_patterns:
            lines.append(f"### {p.name}")
            lines.append(f"Description: {p.description}")
            lines.append(f"Look for: {', '.join(p.source_indicators)}")
            lines.append(f"Convert to: {p.target_equivalent}")
            lines.append("Parameter mapping:")
            for src, tgt in p.parameter_mapping.items():
                lines.append(f"  - {src} → {tgt}")
            if p.notes:
                lines.append(f"Notes: {p.notes}")
            lines.append("")
        
        lines.append("## Task Patterns")
        lines.append("")
        for p in self.task_patterns:
            lines.append(f"### {p.name}")
            lines.append(f"Description: {p.description}")
            lines.append(f"Look for: {', '.join(p.source_indicators)}")
            lines.append(f"Convert to: {p.target_equivalent}")
            lines.append("")
        
        lines.append("## Team/Orchestrator Patterns")
        lines.append("")
        for p in self.team_patterns:
            lines.append(f"### {p.name}")
            lines.append(f"Description: {p.description}")
            lines.append(f"Look for: {', '.join(p.source_indicators)}")
            lines.append(f"Convert to: {p.target_equivalent}")
            lines.append("Parameter mapping:")
            for src, tgt in p.parameter_mapping.items():
                lines.append(f"  - {src} → {tgt}")
            lines.append("")
        
        lines.append("## Import Conversions")
        lines.append("")
        for src, tgt in self.import_patterns.items():
            lines.append(f"- `{src}` → `{tgt}`")
        lines.append("")
        
        lines.append("## Method Conversions")
        lines.append("")
        for src, tgt in self.method_patterns.items():
            lines.append(f"- `.{src}()` → `.{tgt}()`")
        
        return "\n".join(lines)


def get_default_spec() -> MigrationSpec:
    """Get the default migration specification."""
    return MigrationSpec(
        agent_patterns=[
            PatternSpec(
                name="Role-Goal-Backstory Agent",
                description="Agent defined with role, goal, and backstory attributes",
                source_indicators=["role=", "goal=", "backstory=", "Agent("],
                target_equivalent="from praisonaiagents import Agent",
                parameter_mapping={
                    "role": "role",
                    "goal": "goal",
                    "backstory": "backstory",
                    "tools": "tools",
                    "llm": "llm",
                    "verbose": "verbose",
                },
            ),
            PatternSpec(
                name="Name-Instructions Agent",
                description="Agent defined with name and instructions",
                source_indicators=["name=", "instructions=", "model=", "Agent("],
                target_equivalent="from praisonaiagents import Agent",
                parameter_mapping={
                    "name": "name",
                    "instructions": "instructions",
                    "model": "llm",  # Convert model object to llm string
                    "tools": "tools",
                    "markdown": "markdown",
                },
                notes="model=ModelClass(...) should become llm='provider/model-name'",
            ),
        ],
        task_patterns=[
            PatternSpec(
                name="Description-Output Task",
                description="Task with description and expected_output",
                source_indicators=["description=", "expected_output=", "Task("],
                target_equivalent="from praisonaiagents import Task",
                parameter_mapping={
                    "description": "description",
                    "expected_output": "expected_output",
                    "agent": "agent",
                    "context": "context",
                },
            ),
            PatternSpec(
                name="Step Pattern",
                description="Workflow step with agent and description",
                source_indicators=["Step(", "agent=", "description="],
                target_equivalent="from praisonaiagents import Task",
                parameter_mapping={
                    "name": "name",
                    "agent": "agent",
                    "description": "description",
                },
            ),
        ],
        team_patterns=[
            PatternSpec(
                name="Crew/Team Orchestrator",
                description="Multi-agent orchestrator with agents list",
                source_indicators=["Crew(", "Team(", "agents=", "tasks=", "members="],
                target_equivalent="from praisonaiagents import AgentTeam",
                parameter_mapping={
                    "agents": "agents",
                    "members": "agents",  # members → agents
                    "tasks": "tasks",
                    "process": "process",
                    "verbose": "verbose",
                },
            ),
            PatternSpec(
                name="Workflow Orchestrator",
                description="Sequential workflow with steps",
                source_indicators=["Workflow(", "steps="],
                target_equivalent="from praisonaiagents import AgentFlow",
                parameter_mapping={
                    "name": "name",
                    "steps": "steps",
                    "description": "description",
                },
            ),
        ],
        workflow_patterns=[],
        import_patterns={
            # Generic patterns - the LLM will match these
            "from X.agent import Agent": "from praisonaiagents import Agent",
            "from X import Agent": "from praisonaiagents import Agent",
            "from X import Task": "from praisonaiagents import Task",
            "from X.team import Team": "from praisonaiagents import AgentTeam",
            "from X import Crew": "from praisonaiagents import AgentTeam",
            "from X.workflow import Workflow": "from praisonaiagents import AgentFlow",
            "from X.models.Y import Z": "# Use llm parameter instead",
            "from X.db.Y import Z": "# Use memory parameter instead",
        },
        method_patterns={
            "kickoff": "start",
            "run": "start",
            "print_response": "start",
            "execute": "start",
        },
    )


# PraisonAI reference code for the LLM to understand target format
PRAISONAI_REFERENCE = '''
# PraisonAI Agent Framework Reference

## Basic Agent
```python
from praisonaiagents import Agent

agent = Agent(
    name="assistant",           # Agent name
    role="Helper",              # Agent role
    goal="Help users",          # Agent goal
    backstory="Expert helper",  # Agent backstory
    instructions="Be helpful",  # System instructions
    llm="gpt-4o-mini",         # LLM model (provider/model format)
    tools=[my_tool],           # List of tools
    memory=True,               # Enable memory
    markdown=True,             # Enable markdown output
)

# Run the agent
response = agent.start("Hello!")
```

## Multi-Agent Team
```python
from praisonaiagents import Agent, AgentTeam

agent1 = Agent(name="researcher", role="Research")
agent2 = Agent(name="writer", role="Write")

team = AgentTeam(
    agents=[agent1, agent2],
    process="sequential",  # or "hierarchical"
)

result = team.start("Research and write about AI")
```

## AgentFlow (Workflow)
```python
from praisonaiagents import Agent, AgentFlow

flow = AgentFlow(
    name="my_flow",
    steps=[
        Agent(instructions="Step 1"),
        Agent(instructions="Step 2"),
    ],
)

result = flow.run("Start the workflow")
```

## LLM Format
Use "provider/model" format:
- OpenAI: "gpt-4o-mini", "gpt-4o", "o1-mini"
- Google: "gemini/gemini-2.0-flash", "gemini/gemini-pro"
- Anthropic: "anthropic/claude-3-sonnet"
- Ollama: "ollama/llama3"
'''
