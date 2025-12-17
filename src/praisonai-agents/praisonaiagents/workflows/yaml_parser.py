"""
YAML Workflow Parser for PraisonAI Agents.

Parses YAML workflow files into Workflow objects with support for:
- Agent definitions with planning, reasoning, tools
- Workflow patterns: route(), parallel(), loop(), repeat()
- Variables and template substitution
- Callbacks and guardrails
- Memory configuration
"""

import yaml
from typing import Any, Callable, Dict, List, Optional, Union
from pathlib import Path

from ..agent.agent import Agent
from .workflows import Workflow, WorkflowStep, route, parallel, loop, repeat


class YAMLWorkflowParser:
    """
    Parser for YAML workflow files.
    
    Converts YAML workflow definitions into Workflow objects that can be executed.
    
    Example YAML format:
    ```yaml
    name: My Workflow
    description: A multi-agent workflow
    
    workflow:
      planning: true
      reasoning: true
      verbose: true
      memory_config:
        provider: chroma
        persist: true
    
    variables:
      topic: AI trends
    
    agents:
      researcher:
        name: Researcher
        role: Research Analyst
        goal: Research topics
        instructions: "Provide research findings"
        tools:
          - tavily_search
    
    steps:
      - agent: researcher
        action: "Research {{topic}}"
      - name: routing
        route:
          technical: [tech_agent]
          default: [general_agent]
    
    callbacks:
      on_step_complete: log_step
    ```
    """
    
    def __init__(self, tool_registry: Optional[Dict[str, Callable]] = None):
        """
        Initialize the YAML workflow parser.
        
        Args:
            tool_registry: Optional dictionary mapping tool names to callable functions
        """
        self.tool_registry = tool_registry or {}
        self._agents: Dict[str, Agent] = {}
        self._callbacks: Dict[str, Callable] = {}
    
    def parse_file(self, file_path: Union[str, Path]) -> Workflow:
        """
        Parse a YAML workflow file.
        
        Args:
            file_path: Path to the YAML file
            
        Returns:
            Workflow object ready for execution
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Workflow file not found: {file_path}")
        
        with open(file_path, 'r') as f:
            yaml_content = f.read()
        
        return self.parse_string(yaml_content)
    
    def parse_string(self, yaml_content: str) -> Workflow:
        """
        Parse a YAML workflow string.
        
        Args:
            yaml_content: YAML content as string
            
        Returns:
            Workflow object ready for execution
        """
        data = yaml.safe_load(yaml_content)
        return self._parse_workflow_data(data)
    
    def _parse_workflow_data(self, data: Dict[str, Any]) -> Workflow:
        """
        Parse workflow data dictionary into a Workflow object.
        
        Args:
            data: Parsed YAML data dictionary
            
        Returns:
            Workflow object
        """
        # Extract workflow metadata
        name = data.get('name', 'Unnamed Workflow')
        description = data.get('description', '')
        
        # Parse workflow configuration
        workflow_config = data.get('workflow', {})
        planning = workflow_config.get('planning', False)
        planning_llm = workflow_config.get('planning_llm')
        reasoning = workflow_config.get('reasoning', False)
        verbose = workflow_config.get('verbose', False)
        memory_config = workflow_config.get('memory_config')
        
        # Parse variables
        variables = data.get('variables', {})
        
        # Parse agents
        agents_data = data.get('agents', {})
        self._agents = self._parse_agents(agents_data)
        
        # Parse callbacks
        callbacks_data = data.get('callbacks', {})
        self._parse_callbacks(callbacks_data)
        
        # Parse steps
        steps_data = data.get('steps', [])
        steps = self._parse_steps(steps_data)
        
        # Create workflow
        workflow = Workflow(
            name=name,
            steps=steps,
            variables=variables,
            planning=planning,
            planning_llm=planning_llm,
            reasoning=reasoning,
            verbose=verbose,
            memory_config=memory_config,
            on_workflow_start=self._callbacks.get('on_workflow_start'),
            on_step_complete=self._callbacks.get('on_step_complete'),
            on_workflow_complete=self._callbacks.get('on_workflow_complete'),
        )
        
        # Store description as attribute
        workflow.description = description
        
        return workflow
    
    def _parse_agents(self, agents_data: Dict[str, Dict]) -> Dict[str, Agent]:
        """
        Parse agent definitions from YAML.
        
        Args:
            agents_data: Dictionary of agent definitions
            
        Returns:
            Dictionary mapping agent names to Agent objects
        """
        agents = {}
        
        for agent_id, agent_config in agents_data.items():
            agent = self._create_agent(agent_id, agent_config)
            agents[agent_id] = agent
        
        return agents
    
    def _create_agent(self, agent_id: str, config: Dict[str, Any]) -> Agent:
        """
        Create an Agent from configuration.
        
        Args:
            agent_id: Identifier for the agent
            config: Agent configuration dictionary
            
        Returns:
            Agent object
        """
        # Extract agent parameters
        name = config.get('name', agent_id)
        role = config.get('role', 'Assistant')
        goal = config.get('goal', '')
        instructions = config.get('instructions', '')
        backstory = config.get('backstory', '')
        
        # LLM configuration
        llm = config.get('llm')
        
        # Tools
        tools_config = config.get('tools', [])
        tools = self._resolve_tools(tools_config)
        
        # Advanced parameters
        planning = config.get('planning', False)
        reasoning = config.get('reasoning', False)
        verbose = config.get('verbose', False)
        allow_delegation = config.get('allow_delegation', False)
        max_iter = config.get('max_iter')
        cache = config.get('cache', True)
        
        # Create agent
        agent = Agent(
            name=name,
            role=role,
            goal=goal,
            instructions=instructions,
            backstory=backstory,
            llm=llm,
            tools=tools if tools else None,
            verbose=verbose,
        )
        
        # Store additional attributes for later use
        agent._yaml_planning = planning
        agent._yaml_reasoning = reasoning
        agent._yaml_allow_delegation = allow_delegation
        agent._yaml_max_iter = max_iter
        agent._yaml_cache = cache
        
        return agent
    
    def _resolve_tools(self, tools_config: List[str]) -> List[Callable]:
        """
        Resolve tool names to callable functions.
        
        Args:
            tools_config: List of tool names
            
        Returns:
            List of callable tool functions
        """
        tools = []
        for tool_name in tools_config:
            if tool_name in self.tool_registry:
                tools.append(self.tool_registry[tool_name])
            # If tool not in registry, skip it (will be resolved later or is a string reference)
        return tools
    
    def _parse_callbacks(self, callbacks_data: Dict[str, str]) -> None:
        """
        Parse callback definitions.
        
        Args:
            callbacks_data: Dictionary of callback name to function name
        """
        # For now, store callback names - they can be resolved later
        # In a full implementation, these would be resolved to actual functions
        for callback_name, func_name in callbacks_data.items():
            # Store as None for now - actual resolution happens at runtime
            self._callbacks[callback_name] = None
    
    def _parse_steps(self, steps_data: List[Dict]) -> List:
        """
        Parse workflow steps from YAML.
        
        Args:
            steps_data: List of step definitions
            
        Returns:
            List of workflow steps (Agent, WorkflowStep, or pattern objects)
        """
        steps = []
        
        for step_data in steps_data:
            step = self._parse_single_step(step_data)
            if step is not None:
                steps.append(step)
        
        return steps
    
    def _parse_single_step(self, step_data: Dict) -> Any:
        """
        Parse a single step definition.
        
        Args:
            step_data: Step definition dictionary
            
        Returns:
            Step object (Agent, WorkflowStep, or pattern)
        """
        # Check for pattern types
        if 'route' in step_data:
            return self._parse_route_step(step_data)
        elif 'parallel' in step_data:
            return self._parse_parallel_step(step_data)
        elif 'loop' in step_data:
            return self._parse_loop_step(step_data)
        elif 'repeat' in step_data:
            return self._parse_repeat_step(step_data)
        elif 'agent' in step_data:
            return self._parse_agent_step(step_data)
        else:
            # Generic step
            return self._parse_generic_step(step_data)
    
    def _parse_agent_step(self, step_data: Dict) -> Agent:
        """
        Parse an agent step.
        
        Args:
            step_data: Step definition with 'agent' key
            
        Returns:
            Agent object
        """
        agent_id = step_data['agent']
        
        if agent_id in self._agents:
            agent = self._agents[agent_id]
            
            # If there's an action, we need to handle it
            action = step_data.get('action')
            if action:
                # Store action as task for the agent
                agent._yaml_action = action
            
            # Handle guardrail
            guardrail = step_data.get('guardrail')
            if guardrail:
                agent._yaml_guardrail = guardrail
            
            # Handle max_retries
            max_retries = step_data.get('max_retries')
            if max_retries:
                agent._yaml_max_retries = max_retries
            
            return agent
        else:
            raise ValueError(f"Agent '{agent_id}' not defined in agents section")
    
    def _parse_route_step(self, step_data: Dict) -> Dict:
        """
        Parse a route pattern step.
        
        Args:
            step_data: Step definition with 'route' key
            
        Returns:
            Route pattern object
        """
        route_config = step_data['route']
        
        # Build routes dictionary with resolved agents
        routes = {}
        for route_key, agent_ids in route_config.items():
            if isinstance(agent_ids, list):
                routes[route_key] = [self._agents[aid] for aid in agent_ids if aid in self._agents]
            else:
                if agent_ids in self._agents:
                    routes[route_key] = [self._agents[agent_ids]]
        
        return route(routes)
    
    def _parse_parallel_step(self, step_data: Dict) -> Dict:
        """
        Parse a parallel pattern step.
        
        Args:
            step_data: Step definition with 'parallel' key
            
        Returns:
            Parallel pattern object
        """
        parallel_config = step_data['parallel']
        
        # Build list of parallel steps
        parallel_steps = []
        for item in parallel_config:
            if 'agent' in item:
                agent_id = item['agent']
                if agent_id in self._agents:
                    agent = self._agents[agent_id]
                    # Store action if present
                    if 'action' in item:
                        agent._yaml_action = item['action']
                    parallel_steps.append(agent)
        
        return parallel(parallel_steps)
    
    def _parse_loop_step(self, step_data: Dict) -> Dict:
        """
        Parse a loop pattern step.
        
        Args:
            step_data: Step definition with 'loop' key
            
        Returns:
            Loop pattern object
        """
        loop_config = step_data['loop']
        agent_id = step_data.get('agent')
        
        if agent_id and agent_id in self._agents:
            agent = self._agents[agent_id]
            
            # Store action if present
            if 'action' in step_data:
                agent._yaml_action = step_data['action']
            
            # Get loop parameters
            over = loop_config.get('over')
            from_csv = loop_config.get('from_csv')
            
            return loop(agent, over=over, from_csv=from_csv)
        
        raise ValueError("Loop step requires an agent")
    
    def _parse_repeat_step(self, step_data: Dict) -> Dict:
        """
        Parse a repeat pattern step.
        
        Args:
            step_data: Step definition with 'repeat' key
            
        Returns:
            Repeat pattern object
        """
        repeat_config = step_data['repeat']
        agent_id = step_data.get('agent')
        
        if agent_id and agent_id in self._agents:
            agent = self._agents[agent_id]
            
            # Store action if present
            if 'action' in step_data:
                agent._yaml_action = step_data['action']
            
            # Get repeat parameters
            until = repeat_config.get('until')
            max_iterations = repeat_config.get('max_iterations', 5)
            
            # Create condition function from 'until' string
            if isinstance(until, str):
                condition = self._create_condition_from_string(until)
            else:
                condition = until
            
            return repeat(agent, until=condition, max_iterations=max_iterations)
        
        raise ValueError("Repeat step requires an agent")
    
    def _create_condition_from_string(self, condition_str: str) -> Callable:
        """
        Create a condition function from a string.
        
        Args:
            condition_str: Condition string (e.g., "approved", "comprehensive")
            
        Returns:
            Callable condition function
        """
        def condition(ctx) -> bool:
            result = str(ctx.previous_result).lower()
            return condition_str.lower() in result
        return condition
    
    def _parse_generic_step(self, step_data: Dict) -> WorkflowStep:
        """
        Parse a generic workflow step.
        
        Args:
            step_data: Step definition dictionary
            
        Returns:
            WorkflowStep object
        """
        name = step_data.get('name', 'step')
        action = step_data.get('action', '')
        
        return WorkflowStep(
            name=name,
            action=action,
        )
    
    def register_tool(self, name: str, tool: Callable) -> None:
        """
        Register a tool for use in workflows.
        
        Args:
            name: Tool name as referenced in YAML
            tool: Callable tool function
        """
        self.tool_registry[name] = tool
    
    def register_callback(self, name: str, callback: Callable) -> None:
        """
        Register a callback function.
        
        Args:
            name: Callback name as referenced in YAML
            callback: Callable callback function
        """
        self._callbacks[name] = callback
