"""
PlanningAgent for creating implementation plans.

Provides planning functionality similar to:
- CrewAI AgentPlanner
- Cursor Plan Mode
- Claude Code Plan Mode

Features:
- Analyze requests and create detailed plans
- Read-only mode for safe research
- Plan refinement based on feedback
- Context analysis
"""

import json
import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from .plan import Plan, PlanStep

# Define READ_ONLY_TOOLS locally to avoid circular import
READ_ONLY_TOOLS = [
    "read_file",
    "list_directory",
    "search_codebase",
    "search_files",
    "grep_search",
    "find_files",
    "web_search",
    "get_file_content",
    "list_files",
    "read_document",
    "search_web",
    "fetch_url",
    "get_context",
]

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..task.task import Task

logger = logging.getLogger(__name__)


class PlanningAgent:
    """
    Agent specialized in creating implementation plans.
    
    The PlanningAgent analyzes requests, researches the codebase,
    and creates detailed step-by-step plans before execution.
    
    Attributes:
        llm_model: LLM model to use for planning
        read_only: Whether to restrict to read-only tools
        allowed_tools: List of tools available in planning mode
        verbose: Verbosity level
    """
    
    PLANNING_PROMPT = '''You are an expert planning specialist. Your task is to analyze the request and create a detailed, actionable implementation plan.

## Request
{request}

## Available Agents
{agents_info}

## Available Tasks (if any)
{tasks_info}

## Context
{context}

## Instructions
1. Analyze the request thoroughly
2. Break it down into clear, actionable steps
3. Assign appropriate agents to each step
4. Identify dependencies between steps
5. Consider potential risks and edge cases

## Output Format
Respond with a JSON object in this exact format:
{{
    "name": "Brief plan name",
    "description": "Detailed description of what this plan accomplishes",
    "steps": [
        {{
            "description": "Clear description of what this step does",
            "agent": "Name of the agent to execute this step (or null)",
            "tools": ["list", "of", "tools", "needed"],
            "dependencies": ["list of step IDs this depends on"]
        }}
    ]
}}

Important:
- Each step should be atomic and clearly defined
- Dependencies should reference step indices (e.g., "step_0", "step_1")
- Be specific about what each step accomplishes
- Consider the order of operations carefully'''

    REFINEMENT_PROMPT = '''You are refining an existing implementation plan based on feedback.

## Original Plan
{original_plan}

## Feedback
{feedback}

## Instructions
1. Review the original plan
2. Apply the feedback to improve the plan
3. Maintain the same JSON format
4. Keep steps that are still valid
5. Add, modify, or remove steps as needed

## Output Format
Respond with a JSON object in the same format as the original plan:
{{
    "name": "Updated plan name",
    "description": "Updated description",
    "steps": [...]
}}'''

    ANALYSIS_PROMPT = '''Analyze the following context and provide insights for planning:

## Context
{context}

## Instructions
1. Identify the key components and their relationships
2. Note any patterns or conventions
3. Highlight potential challenges
4. Suggest best practices to follow

Provide a concise analysis that will help in creating an implementation plan.'''

    def __init__(
        self,
        llm: str = "gpt-4o-mini",
        read_only: bool = True,
        verbose: int = 0,
        tools: Optional[List] = None,
        reasoning: bool = False,
        max_reasoning_steps: int = 5
    ):
        """
        Initialize PlanningAgent.
        
        Args:
            llm: LLM model to use for planning
            read_only: Whether to restrict to read-only tools
            verbose: Verbosity level
            tools: Optional list of tools for research during planning
            reasoning: Whether to enable reasoning mode with chain-of-thought
            max_reasoning_steps: Maximum reasoning iterations (default 5)
        """
        self.llm_model = llm
        self.read_only = read_only
        self.verbose = verbose
        self.tools = tools or []
        self.reasoning = reasoning
        self.max_reasoning_steps = max_reasoning_steps
        self.allowed_tools = READ_ONLY_TOOLS.copy() if read_only else []
        self._llm = None
        self._agent = None
        
    def _get_llm(self):
        """Lazy load LLM instance."""
        if self._llm is None:
            from ..llm import LLM
            self._llm = LLM(model=self.llm_model)
        return self._llm
    
    def _get_agent(self):
        """
        Lazy load Agent instance for tool-enabled planning.
        
        Returns:
            Agent instance if tools are provided, None otherwise
        """
        if not self.tools:
            return None
            
        if self._agent is None:
            from ..agent.agent import Agent
            self._agent = Agent(
                name="Planning Research Agent",
                role="Research and Planning Specialist",
                goal="Research information and create detailed implementation plans",
                llm=self.llm_model,
                tools=self.tools,
                output="verbose" if self.verbose > 0 else "silent"
            )
        return self._agent
    
    def _format_agents_info(self, agents: List['Agent']) -> str:
        """
        Format agent information for the prompt.
        
        Args:
            agents: List of Agent instances
            
        Returns:
            Formatted string describing agents
        """
        if not agents:
            return "No agents specified"
            
        lines = []
        for agent in agents:
            name = getattr(agent, 'name', 'Unnamed')
            role = getattr(agent, 'role', 'General')
            goal = getattr(agent, 'goal', '')
            
            line = f"- **{name}** ({role})"
            if goal:
                line += f": {goal}"
            lines.append(line)
            
        return "\n".join(lines)
    
    def _format_tasks_info(self, tasks: Optional[List['Task']]) -> str:
        """
        Format task information for the prompt.
        
        Args:
            tasks: List of Task instances
            
        Returns:
            Formatted string describing tasks
        """
        if not tasks:
            return "No predefined tasks"
            
        lines = []
        for task in tasks:
            name = getattr(task, 'name', None) or getattr(task, 'description', 'Unnamed')[:50]
            desc = getattr(task, 'description', '')[:100]
            
            lines.append(f"- {name}: {desc}")
            
        return "\n".join(lines)
    
    def _parse_plan_response(self, response: str) -> Plan:
        """
        Parse LLM response into a Plan object.
        
        Args:
            response: JSON string from LLM
            
        Returns:
            Plan instance
        """
        try:
            # Try to extract JSON from response
            # Handle cases where LLM includes extra text
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
                
            # Create steps
            steps = []
            for i, step_data in enumerate(data.get("steps", [])):
                step = PlanStep(
                    id=f"step_{i}",
                    description=step_data.get("description", ""),
                    agent=step_data.get("agent"),
                    tools=step_data.get("tools", []),
                    dependencies=step_data.get("dependencies", [])
                )
                steps.append(step)
                
            return Plan(
                name=data.get("name", "Implementation Plan"),
                description=data.get("description", ""),
                steps=steps
            )
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse plan response: {e}")
            # Return a simple plan with the response as a single step
            return Plan(
                name="Implementation Plan",
                description="Auto-generated plan",
                steps=[PlanStep(description=response[:500])]
            )
    
    async def create_plan(
        self,
        request: str,
        agents: List['Agent'],
        tasks: Optional[List['Task']] = None,
        context: Optional[str] = None
    ) -> Plan:
        """
        Create an implementation plan for the given request.
        
        Args:
            request: The user's request or goal
            agents: List of available agents
            tasks: Optional list of predefined tasks
            context: Optional additional context
            
        Returns:
            Plan instance with steps
        """
        llm = self._get_llm()
        
        # Format the prompt
        prompt = self.PLANNING_PROMPT.format(
            request=request,
            agents_info=self._format_agents_info(agents),
            tasks_info=self._format_tasks_info(tasks),
            context=context or "No additional context provided"
        )
        
        if self.verbose >= 2:
            logger.info(f"Creating plan for: {request[:100]}...")
            
        # Get LLM response
        response = await llm.get_response_async(prompt)
        
        # Parse response into Plan
        plan = self._parse_plan_response(response)
        
        if self.verbose >= 1:
            logger.info(f"Created plan '{plan.name}' with {len(plan.steps)} steps")
            
        return plan
    
    def create_plan_sync(
        self,
        request: str,
        agents: List['Agent'],
        tasks: Optional[List['Task']] = None,
        context: Optional[str] = None
    ) -> Plan:
        """
        Synchronous version of create_plan.
        
        Args:
            request: The user's request or goal
            agents: List of available agents
            tasks: Optional list of predefined tasks
            context: Optional additional context
            
        Returns:
            Plan instance with steps
        """
        # Format the prompt
        prompt = self.PLANNING_PROMPT.format(
            request=request,
            agents_info=self._format_agents_info(agents),
            tasks_info=self._format_tasks_info(tasks),
            context=context or "No additional context provided"
        )
        
        if self.verbose >= 2:
            logger.info(f"Creating plan for: {request[:100]}...")
        
        # Use Agent with tools if available, otherwise use bare LLM
        agent = self._get_agent()
        if agent is not None:
            # Use Agent.chat() for tool-enabled planning
            response = agent.chat(prompt)
        else:
            # Use bare LLM for simple planning
            llm = self._get_llm()
            response = llm.get_response(prompt)
        
        # Parse response into Plan
        plan = self._parse_plan_response(response)
        
        if self.verbose >= 1:
            logger.info(f"Created plan '{plan.name}' with {len(plan.steps)} steps")
            
        return plan
    
    async def refine_plan(
        self,
        plan: Plan,
        feedback: str
    ) -> Plan:
        """
        Refine an existing plan based on feedback.
        
        Args:
            plan: Original plan to refine
            feedback: User feedback for refinement
            
        Returns:
            Refined Plan instance
        """
        llm = self._get_llm()
        
        # Format the prompt
        prompt = self.REFINEMENT_PROMPT.format(
            original_plan=json.dumps(plan.to_dict(), indent=2),
            feedback=feedback
        )
        
        if self.verbose >= 2:
            logger.info(f"Refining plan based on feedback: {feedback[:100]}...")
            
        # Get LLM response
        response = await llm.get_response_async(prompt)
        
        # Parse response into Plan
        refined = self._parse_plan_response(response)
        
        # Preserve original ID
        refined.id = plan.id
        
        if self.verbose >= 1:
            logger.info(f"Refined plan '{refined.name}' with {len(refined.steps)} steps")
            
        return refined
    
    def refine_plan_sync(
        self,
        plan: Plan,
        feedback: str
    ) -> Plan:
        """
        Synchronous version of refine_plan.
        
        Args:
            plan: Original plan to refine
            feedback: User feedback for refinement
            
        Returns:
            Refined Plan instance
        """
        llm = self._get_llm()
        
        # Format the prompt
        prompt = self.REFINEMENT_PROMPT.format(
            original_plan=json.dumps(plan.to_dict(), indent=2),
            feedback=feedback
        )
        
        if self.verbose >= 2:
            logger.info(f"Refining plan based on feedback: {feedback[:100]}...")
            
        # Get LLM response
        response = llm.get_response(prompt)
        
        # Parse response into Plan
        refined = self._parse_plan_response(response)
        
        # Preserve original ID
        refined.id = plan.id
        
        if self.verbose >= 1:
            logger.info(f"Refined plan '{refined.name}' with {len(refined.steps)} steps")
            
        return refined
    
    async def analyze_context(
        self,
        context: str
    ) -> str:
        """
        Analyze context and provide insights for planning.
        
        Args:
            context: Context to analyze (e.g., codebase summary)
            
        Returns:
            Analysis string
        """
        llm = self._get_llm()
        
        prompt = self.ANALYSIS_PROMPT.format(context=context)
        
        if self.verbose >= 2:
            logger.info("Analyzing context...")
            
        response = await llm.get_response_async(prompt)
        
        return response
    
    def analyze_context_sync(
        self,
        context: str
    ) -> str:
        """
        Synchronous version of analyze_context.
        
        Args:
            context: Context to analyze
            
        Returns:
            Analysis string
        """
        llm = self._get_llm()
        
        prompt = self.ANALYSIS_PROMPT.format(context=context)
        
        if self.verbose >= 2:
            logger.info("Analyzing context...")
            
        response = llm.get_response(prompt)
        
        return response
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        """
        Check if a tool is allowed in planning mode.
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            True if tool is allowed
        """
        if not self.read_only:
            return True
        return tool_name in self.allowed_tools
