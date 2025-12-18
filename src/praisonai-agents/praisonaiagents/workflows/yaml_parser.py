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
        # Normalize to canonical format (accept both old and new field names)
        normalized_data = self._normalize_yaml_config(data)
        return self._parse_workflow_data(normalized_data)
    
    def _normalize_yaml_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize YAML config to canonical format.
        
        Accepts both old (agents.yaml) and new (workflow.yaml) field names.
        This implements "Accept liberally, suggest canonically" principle.
        
        Canonical names (preferred):
        - agents (not roles)
        - instructions (not backstory)  
        - action (not description)
        - steps (not tasks)
        - name (not topic)
        
        Args:
            data: Raw parsed YAML data
            
        Returns:
            Normalized data with canonical field names
        """
        if not data:
            return data
            
        normalized = data.copy()
        
        # 1. Normalize workflow name: topic -> name (only if topic is used as name, not as input)
        # Note: 'topic' is legacy, 'input' is canonical for workflow input data
        if 'topic' in normalized and 'name' not in normalized and 'input' not in normalized:
            # Legacy behavior: topic was used as both name and input
            normalized['name'] = normalized.get('topic', 'Unnamed Workflow')
        
        # 2. Normalize workflow input: 'input' is canonical, 'topic' is alias
        # Priority: input > topic (input takes precedence if both exist)
        if 'input' not in normalized and 'topic' in normalized:
            normalized['input'] = normalized['topic']
        
        # 3. Normalize container: roles -> agents
        # Note: _convert_roles_to_agents handles backstory -> instructions
        if 'roles' in normalized and 'agents' not in normalized:
            normalized['agents'] = self._convert_roles_to_agents(normalized['roles'])
            # Extract steps from tasks nested in roles if no steps defined
            if 'steps' not in normalized:
                normalized['steps'] = self._extract_steps_from_roles(normalized['roles'])
        
        # 4. Normalize agent fields: backstory -> instructions (for agents section)
        if 'agents' in normalized:
            for agent_id, agent_config in normalized['agents'].items():
                if isinstance(agent_config, dict):
                    # backstory -> instructions
                    if 'backstory' in agent_config and 'instructions' not in agent_config:
                        agent_config['instructions'] = agent_config['backstory']
        
        # 5. Normalize step fields: description -> action
        if 'steps' in normalized:
            for step in normalized['steps']:
                if isinstance(step, dict):
                    # description -> action
                    if 'description' in step and 'action' not in step:
                        step['action'] = step['description']
                    
                    # Handle parallel steps
                    if 'parallel' in step:
                        for parallel_step in step['parallel']:
                            if isinstance(parallel_step, dict):
                                if 'description' in parallel_step and 'action' not in parallel_step:
                                    parallel_step['action'] = parallel_step['description']
        
        return normalized
    
    def _extract_steps_from_roles(self, roles: Dict[str, Dict]) -> List[Dict]:
        """
        Extract steps from tasks nested within roles (agents.yaml format).
        
        Args:
            roles: The roles section from agents.yaml
            
        Returns:
            List of step definitions
        """
        steps = []
        for role_id, role_config in roles.items():
            if 'tasks' in role_config:
                for task_id, task_config in role_config['tasks'].items():
                    step = {
                        'name': task_id,
                        'agent': role_id,
                    }
                    # description -> action
                    if 'description' in task_config:
                        step['action'] = task_config['description']
                    elif 'action' in task_config:
                        step['action'] = task_config['action']
                    
                    # Copy other task fields
                    for field in ['expected_output', 'context', 'output_file', 
                                  'output_json', 'create_directory', 'callback',
                                  'async_execution', 'guardrail', 'max_retries']:
                        if field in task_config:
                            step[field] = task_config[field]
                    
                    steps.append(step)
        return steps
    
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
        
        # Extract framework and process (for feature parity with agents.yaml)
        framework = data.get('framework', 'praisonai')
        process = data.get('process', 'sequential')
        manager_llm = data.get('manager_llm')
        
        # Parse workflow configuration
        workflow_config = data.get('workflow', {})
        planning = workflow_config.get('planning', False)
        planning_llm = workflow_config.get('planning_llm')
        default_llm = workflow_config.get('default_llm')
        reasoning = workflow_config.get('reasoning', False)
        verbose = workflow_config.get('verbose', False)
        memory_config = workflow_config.get('memory_config')
        
        # Parse variables
        variables = data.get('variables', {})
        
        # Parse agents - support both 'agents' and 'roles' keys for backward compatibility
        agents_data = data.get('agents', {})
        if not agents_data and 'roles' in data:
            # Convert roles format to agents format
            agents_data = self._convert_roles_to_agents(data['roles'])
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
            default_llm=default_llm,
            reasoning=reasoning,
            verbose=verbose,
            memory_config=memory_config,
            on_workflow_start=self._callbacks.get('on_workflow_start'),
            on_step_complete=self._callbacks.get('on_step_complete'),
            on_workflow_complete=self._callbacks.get('on_workflow_complete'),
        )
        
        # Store additional attributes for feature parity with agents.yaml
        workflow.description = description
        workflow.framework = framework
        workflow.process = process
        workflow.manager_llm = manager_llm
        
        # Store workflow input (from 'input' or 'topic' field)
        # This is the default input passed to workflow.start() if no input is provided
        workflow.default_input = data.get('input', data.get('topic', ''))
        
        return workflow
    
    def _convert_roles_to_agents(self, roles: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        Convert agents.yaml 'roles' format to workflow 'agents' format.
        
        This enables backward compatibility with the existing agents.yaml format.
        
        Mapping:
        - backstory -> instructions
        - role -> role
        - goal -> goal
        - tools -> tools
        - llm -> llm
        - tasks -> (used to auto-generate steps if no steps defined)
        
        Args:
            roles: The roles section from agents.yaml
            
        Returns:
            Converted agents dictionary in workflow format
        """
        agents = {}
        for role_id, role_config in roles.items():
            agent = {
                'name': role_config.get('role', role_id),
                'role': role_config.get('role', role_id),
                'goal': role_config.get('goal', ''),
                'instructions': role_config.get('backstory', ''),
            }
            
            # Copy optional fields
            if 'llm' in role_config:
                llm_config = role_config['llm']
                if isinstance(llm_config, dict):
                    agent['llm'] = llm_config.get('model', 'gpt-4o-mini')
                else:
                    agent['llm'] = llm_config
            
            if 'tools' in role_config:
                agent['tools'] = [t for t in role_config['tools'] if t]
            
            if 'verbose' in role_config:
                agent['verbose'] = role_config['verbose']
            
            if 'max_iter' in role_config:
                agent['max_iter'] = role_config['max_iter']
            
            if 'planning' in role_config:
                agent['planning'] = role_config['planning']
            
            if 'reasoning' in role_config:
                agent['reasoning'] = role_config['reasoning']
            
            agents[role_id] = agent
        
        return agents
    
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
        
        # Advanced parameters (feature parity with agents.yaml)
        planning = config.get('planning', False)
        reasoning = config.get('reasoning', False)
        verbose = config.get('verbose', False)
        allow_delegation = config.get('allow_delegation', False)
        max_iter = config.get('max_iter')
        cache = config.get('cache', True)
        
        # Additional agents.yaml fields
        function_calling_llm = config.get('function_calling_llm')
        max_rpm = config.get('max_rpm')
        max_execution_time = config.get('max_execution_time')
        reflect_llm = config.get('reflect_llm')
        min_reflect = config.get('min_reflect')
        max_reflect = config.get('max_reflect')
        system_template = config.get('system_template')
        prompt_template = config.get('prompt_template')
        response_template = config.get('response_template')
        
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
        
        # Store additional agents.yaml fields for feature parity
        agent._yaml_function_calling_llm = function_calling_llm
        agent._yaml_max_rpm = max_rpm
        agent._yaml_max_execution_time = max_execution_time
        agent._yaml_reflect_llm = reflect_llm
        agent._yaml_min_reflect = min_reflect
        agent._yaml_max_reflect = max_reflect
        agent._yaml_system_template = system_template
        agent._yaml_prompt_template = prompt_template
        agent._yaml_response_template = response_template
        
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
            
            # Store step name if provided
            step_name = step_data.get('name')
            if step_name:
                agent._yaml_step_name = step_name
            
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
            
            # Handle expected_output (feature parity with agents.yaml tasks)
            expected_output = step_data.get('expected_output')
            if expected_output:
                agent._yaml_expected_output = expected_output
            
            # Handle context/dependencies (feature parity with agents.yaml tasks)
            context = step_data.get('context')
            if context:
                agent._yaml_context = context
            
            # Handle output_file
            output_file = step_data.get('output_file')
            if output_file:
                agent._yaml_output_file = output_file
            
            # Handle output_json (structured output)
            output_json = step_data.get('output_json')
            if output_json:
                agent._yaml_output_json = output_json
            
            # Handle output_pydantic
            output_pydantic = step_data.get('output_pydantic')
            if output_pydantic:
                agent._yaml_output_pydantic = output_pydantic
            
            # Handle create_directory
            create_directory = step_data.get('create_directory')
            if create_directory is not None:
                agent._yaml_create_directory = create_directory
            
            # Handle callback
            callback = step_data.get('callback')
            if callback:
                agent._yaml_callback = callback
            
            # Handle async_execution
            async_execution = step_data.get('async_execution')
            if async_execution is not None:
                agent._yaml_async_execution = async_execution
            
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
