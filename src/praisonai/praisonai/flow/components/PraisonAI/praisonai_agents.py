"""PraisonAI Agents (Multi-Agent) Component for Langflow.

Creates and executes a PraisonAI Agents orchestrator for multi-agent workflows
with sequential, hierarchical, or workflow process types.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langflow.custom import Component
from langflow.io import (
    BoolInput,
    DictInput,
    DropdownInput,
    HandleInput,
    MessageTextInput,
    MultilineInput,
    Output,
)
from langflow.schema.message import Message


class PraisonAIAgentsComponent(Component):
    """PraisonAI Agents component for multi-agent orchestration in Langflow.

    Orchestrates multiple PraisonAI agents with sequential, hierarchical,
    or workflow process types.
    """

    display_name: str = "Agent Team"
    description: str = "Orchestrate multiple PraisonAI agents for complex workflows."
    documentation: str = "https://docs.praison.ai"
    icon: str = "bot"
    name: str = "PraisonAIAgents"

    inputs = [
        # ============================================================
        # CORE CONFIGURATION
        # ============================================================
        MessageTextInput(
            name="team_name",
            display_name="Name",
            info="Name for this multi-agent team.",
            value="AgentTeam",
        ),
        # ============================================================
        # AGENTS & TASKS
        # ============================================================
        HandleInput(
            name="agents",
            display_name="Agents",
            info="List of PraisonAI agents to orchestrate.",
            input_types=["Agent"],
            is_list=True,
        ),
        # ============================================================
        # INPUT
        # ============================================================
        HandleInput(
            name="input_value",
            display_name="Input",
            info="Initial input to start the multi-agent workflow.",
            input_types=["Message", "str"],
        ),
        # ============================================================
        # PROCESS TYPE
        # ============================================================
        DropdownInput(
            name="process",
            display_name="Process",
            info="How agents should collaborate.",
            options=["sequential", "hierarchical", "workflow"],
            value="sequential",
        ),
        # ============================================================
        # MANAGER (for hierarchical)
        # ============================================================
        HandleInput(
            name="manager_agent",
            display_name="Manager Agent",
            info="Manager agent for hierarchical process (optional).",
            input_types=["Agent"],
            advanced=True,
        ),
        MultilineInput(
            name="manager_llm",
            display_name="Manager LLM",
            info="LLM for auto-created manager in hierarchical mode.",
            value="openai/gpt-4o",
            advanced=True,
        ),
        # ============================================================
        # VARIABLES
        # ============================================================
        DictInput(
            name="global_variables",
            display_name="Variables",
            info="Global variables for substitution in all task descriptions.",
            advanced=True,
        ),
        # ============================================================
        # MEMORY
        # ============================================================
        BoolInput(
            name="memory",
            display_name="Shared Memory",
            info="Enable shared memory across all agents.",
            value=False,
            advanced=True,
        ),
        # ============================================================
        # GUARDRAILS
        # ============================================================
        BoolInput(
            name="guardrails",
            display_name="Guardrails",
            info="Enable output validation for all agents.",
            value=False,
            advanced=True,
        ),
        # ============================================================
        # EXECUTION OPTIONS
        # ============================================================
        BoolInput(
            name="verbose",
            display_name="Verbose",
            info="Show detailed execution logs.",
            value=False,
            advanced=True,
        ),
        BoolInput(
            name="full_output",
            display_name="Full Output",
            info="Return full output including all task results.",
            value=False,
            advanced=True,
        ),
        # ============================================================
        # ADVANCED FEATURES
        # ============================================================
        BoolInput(
            name="planning",
            display_name="Planning",
            info="Enable planning mode for complex task decomposition.",
            value=False,
            advanced=True,
        ),
        BoolInput(
            name="reflection",
            display_name="Reflection",
            info="Enable self-reflection for improved results.",
            value=False,
            advanced=True,
        ),
        BoolInput(
            name="caching",
            display_name="Caching",
            info="Enable caching of agent responses.",
            value=False,
            advanced=True,
        ),
    ]

    outputs = [
        Output(
            display_name="Response",
            name="response",
            method="build_response",
        ),
        Output(
            display_name="Agents Instance",
            name="agents_instance",
            method="build_agents",
            types=["Agents"]
        ),
    ]

    def _import_agents(self):
        """Import Agents class with proper error handling."""
        try:
            from praisonaiagents import AgentTeam
        except ImportError as e:
            msg = "PraisonAI Agents is not installed. Install with: pip install praisonaiagents"
            raise ImportError(msg) from e
        else:
            return AgentTeam

    def _sort_agents_by_chain(self, agents: list) -> list:
        """Sort agents by their chain order (previous_agent connections).
        
        Agents are connected: Agent1 → Agent2 → Agent3
        The first agent has no previous_agent, subsequent agents point to their predecessor.
        """
        if len(agents) <= 1:
            return agents
        
        # Find agents that have a previous_agent set
        has_previous = set()
        
        for agent in agents:
            prev = getattr(agent, '_langflow_previous', None)
            if prev is not None:
                has_previous.add(id(agent))
        
        # Find starting agents (those with no previous)
        starting_agents = [a for a in agents if id(a) not in has_previous or getattr(a, '_langflow_previous', None) is None]
        
        if not starting_agents:
            # No clear start, return as-is
            return agents
        
        # Build chain from each starting agent
        sorted_agents = []
        visited = set()
        
        # Start with agents that have no previous
        for start in starting_agents:
            if id(start) in visited:
                continue
            sorted_agents.append(start)
            visited.add(id(start))
        
        # Now add agents that follow (have previous_agent set)
        # Keep iterating until all agents are placed
        remaining = [a for a in agents if id(a) not in visited]
        while remaining:
            added = False
            for agent in remaining[:]:
                prev = getattr(agent, '_langflow_previous', None)
                if prev is not None and id(prev) in visited:
                    sorted_agents.append(agent)
                    visited.add(id(agent))
                    remaining.remove(agent)
                    added = True
            if not added:
                # No progress, add remaining as-is
                sorted_agents.extend(remaining)
                break
        
        return sorted_agents

    def build_agents(self) -> Any:
        """Build and return the PraisonAI Agents instance."""
        agents_class = self._import_agents()

        # Filter out None values
        agents = [a for a in (self.agents or []) if a is not None]

        if not agents:
            msg = "At least one agent is required."
            raise ValueError(msg)
        
        # Sort agents by chain order (previous_agent connections)
        agents = self._sort_agents_by_chain(agents)

        # Build kwargs - tasks auto-generated from agents
        kwargs = {
            "agents": agents,
            "process": self.process,
        }

        # Add output config
        if self.verbose or self.full_output:
            kwargs["output"] = "verbose" if self.verbose else "actions"

        # Add name if provided
        if self.team_name and self.team_name != "AgentTeam":
            kwargs["name"] = self.team_name

        # Add variables if provided
        if self.global_variables:
            kwargs["variables"] = self.global_variables

        # Add memory configuration
        if self.memory:
            session_id = getattr(self.graph, "session_id", None) if hasattr(self, "graph") else None
            kwargs["memory"] = {"auto_save": session_id} if session_id else True

        # Add manager for hierarchical
        if self.process == "hierarchical":
            if self.manager_agent:
                kwargs["manager_agent"] = self.manager_agent
            elif self.manager_llm:
                kwargs["manager_llm"] = self.manager_llm

        # Add advanced features
        if self.guardrails:
            kwargs["guardrails"] = True

        if self.planning:
            kwargs["planning"] = True

        if self.reflection:
            kwargs["reflection"] = True

        if self.caching:
            kwargs["caching"] = True

        # Build Agents
        agents_instance = agents_class(**kwargs)

        self.status = f"Agents orchestrator '{self.team_name}' created with {len(agents)} agents"
        return agents_instance

    def build_response(self) -> Message:
        """Execute the multi-agent workflow and return the response."""
        agents_instance = self.build_agents()

        # Get input value
        input_value = self.input_value
        if hasattr(input_value, "text"):
            input_value = input_value.text
        elif input_value is None:
            input_value = ""

        # Execute agents (sync)
        result = agents_instance.start(str(input_value))

        # Convert to Langflow Message
        output_text = result.get("final_output", str(result)) if isinstance(result, dict) else str(result)

        return Message(text=output_text)

    async def build_response_async(self) -> Message:
        """Execute the multi-agent workflow asynchronously."""
        return await asyncio.to_thread(self.build_response)
