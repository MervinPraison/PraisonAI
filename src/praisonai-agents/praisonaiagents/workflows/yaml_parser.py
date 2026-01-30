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
from .workflows import Workflow, route, parallel, loop, repeat, Include, include
from ..task.task import Task


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
    
    def parse_file(self, file_path: Union[str, Path], extra_vars: Optional[Dict[str, Any]] = None) -> Workflow:
        """
        Parse a YAML workflow file.
        
        Args:
            file_path: Path to the YAML file
            extra_vars: Optional dict of variables to override YAML defaults (e.g., from CLI --var)
            
        Returns:
            Workflow object ready for execution
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Workflow file not found: {file_path}")
        
        with open(file_path, 'r') as f:
            yaml_content = f.read()
        
        return self.parse_string(yaml_content, extra_vars=extra_vars)
    
    def parse_string(self, yaml_content: str, extra_vars: Optional[Dict[str, Any]] = None) -> Workflow:
        """
        Parse a YAML workflow string.
        
        Args:
            yaml_content: YAML content as string
            extra_vars: Optional dict of variables to override YAML defaults (e.g., from CLI --var)
            
        Returns:
            Workflow object ready for execution
        """
        data = yaml.safe_load(yaml_content)
        # Normalize to canonical format (accept both old and new field names)
        normalized_data = self._normalize_yaml_config(data)
        return self._parse_workflow_data(normalized_data, extra_vars=extra_vars)
    
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
        
        # 3.5. Handle 'includes:' section - append include steps after role-based steps
        # This allows agents.yaml files to include other recipes as final steps
        if 'includes' in normalized:
            if 'steps' not in normalized:
                normalized['steps'] = []
            for include_item in normalized['includes']:
                if isinstance(include_item, str):
                    # Simple include: just recipe name
                    normalized['steps'].append({'include': include_item})
                elif isinstance(include_item, dict):
                    # Include with configuration
                    normalized['steps'].append({'include': include_item})
        
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
                                  'async_execution', 'guardrail', 'max_retries',
                                  'skip_on_failure', 'retry_delay']:
                        if field in task_config:
                            step[field] = task_config[field]
                    
                    steps.append(step)
        return steps
    
    def _parse_workflow_data(self, data: Dict[str, Any], extra_vars: Optional[Dict[str, Any]] = None) -> Workflow:
        """
        Parse workflow data dictionary into a Workflow object.
        
        Args:
            data: Parsed YAML data dictionary
            extra_vars: Optional dict of variables to override YAML defaults (e.g., from CLI --var)
            
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
        output_mode = workflow_config.get('output')  # NEW: parse output mode from YAML
        
        # Parse approve field for auto-approving tools (e.g., approve: [write_file, delete_file])
        # This allows recipes to pre-approve dangerous tools for non-interactive execution
        approve_tools = data.get('approve', [])
        if isinstance(approve_tools, str):
            approve_tools = [approve_tools]  # Handle single tool as string
        
        # Parse variables (YAML defaults), then merge CLI overrides (extra_vars take precedence)
        variables = data.get('variables', {})
        if extra_vars:
            variables = {**variables, **extra_vars}  # CLI --var overrides YAML defaults

        
        # Auto-add 'topic' to variables for include recipe propagation
        # This ensures included recipes receive the parent's topic via {{topic}}
        topic_value = data.get('topic')
        if topic_value and 'topic' not in variables:
            # Substitute template variables (e.g., {{today}}) in topic if present
            if "{{" in str(topic_value):
                from praisonaiagents.utils.variables import substitute_variables
                topic_value = substitute_variables(str(topic_value), variables)
            variables['topic'] = topic_value
        
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
        
        # Create workflow - use only valid Workflow dataclass fields
        # Build planning config if planning_llm is specified
        planning_value = planning
        if planning_llm:
            from .workflow_configs import WorkflowPlanningConfig
            planning_value = WorkflowPlanningConfig(enabled=bool(planning), llm=planning_llm, reasoning=reasoning)
        
        # Determine output mode: explicit output > verbose flag > default
        workflow_output = output_mode
        if workflow_output is None and verbose:
            workflow_output = "verbose"
        
        # Build memory config if specified - pass raw dict for flexibility
        memory_value = memory_config if memory_config else None
        
        # Parse context management config (CRITICAL for token overflow prevention)
        # Supports: context: true OR context: {auto_compact: true, strategy: smart, ...}
        # Also supports YAML-friendly aliases: enabled -> auto_compact, max_tool_output_tokens -> tool_output_max
        context_config = data.get('context')
        if context_config is True:
            # Simple enable: context: true
            context_value = True
        elif isinstance(context_config, dict):
            # Detailed config: context: {auto_compact: true, ...}
            # Apply field aliasing for YAML-friendly names
            normalized_config = context_config.copy()
            
            # Alias: enabled -> auto_compact
            if 'enabled' in normalized_config:
                normalized_config['auto_compact'] = normalized_config.pop('enabled')
            
            # Alias: max_tool_output_tokens -> tool_output_max
            if 'max_tool_output_tokens' in normalized_config:
                normalized_config['tool_output_max'] = normalized_config.pop('max_tool_output_tokens')
            
            # Alias: threshold -> compact_threshold
            if 'threshold' in normalized_config:
                normalized_config['compact_threshold'] = normalized_config.pop('threshold')
            
            # Alias: tool_output_limits -> tool_limits (per-tool configurable limits)
            if 'tool_output_limits' in normalized_config:
                normalized_config['tool_limits'] = normalized_config.pop('tool_output_limits')
            
            try:
                from ..context.models import ContextConfig
                context_value = ContextConfig(**normalized_config)
            except Exception:
                # Fallback: just enable with True if ContextConfig fails
                context_value = True
        else:
            context_value = None
        
        # Parse history flag for execution tracing (robustness feature)
        history_enabled = data.get('history', False)
        
        workflow = Workflow(
            name=name,
            steps=steps,
            variables=variables,
            planning=planning_value,
            default_llm=default_llm,
            process=process,  # Process type: sequential or hierarchical
            manager_llm=manager_llm,  # LLM for manager agent (hierarchical mode)
            output=workflow_output,  # Pass output mode to Workflow
            memory=memory_value,  # Pass memory config to Workflow
            context=context_value,  # Pass context management config to Workflow
            history=history_enabled,  # Enable execution history tracking (robustness)
        )
        
        # Store additional attributes for feature parity with agents.yaml
        workflow.description = description
        workflow.framework = framework
        
        # Store approved tools for auto-approval during workflow execution
        workflow.approve_tools = approve_tools
        
        # Store workflow input (from 'input' or 'topic' field)
        # This is the default input passed to workflow.start() if no input is provided
        default_input = data.get('input', data.get('topic', ''))
        
        # Substitute dynamic variables ({{today}}, {{now}}, etc.) in default_input
        if default_input and "{{" in default_input:
            from praisonaiagents.utils.variables import substitute_variables
            default_input = substitute_variables(default_input, {})
        
        workflow.default_input = default_input
        
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
            
            # Skip verbose - Agent no longer accepts it
            # if 'verbose' in role_config:
            #     agent['verbose'] = role_config['verbose']
            
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
    
    def _create_agent(self, agent_id: str, config: Dict[str, Any]) -> Any:
        """
        Create an Agent from configuration.
        
        Supports specialized agent types via the `agent:` field:
        - agent: AudioAgent  -> Creates AudioAgent for TTS/STT
        - agent: VideoAgent  -> Creates VideoAgent for video generation
        - agent: ImageAgent  -> Creates ImageAgent for image generation
        - agent: OCRAgent    -> Creates OCRAgent for text extraction
        - agent: DeepResearchAgent -> Creates DeepResearchAgent for research
        - (no agent field)   -> Creates default Agent
        
        Args:
            agent_id: Identifier for the agent
            config: Agent configuration dictionary
            
        Returns:
            Agent object (or specialized agent type)
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
        max_rpm = config.get('max_rpm')
        max_execution_time = config.get('max_execution_time')
        reflect_llm = config.get('reflect_llm')
        min_reflect = config.get('min_reflect')
        max_reflect = config.get('max_reflect')
        system_template = config.get('system_template')
        prompt_template = config.get('prompt_template')
        response_template = config.get('response_template')
        
        # Tool choice configuration (auto, required, none)
        tool_choice = config.get('tool_choice')
        
        # Check for specialized agent type via `agent:` field
        agent_type = config.get('agent', '').lower() if config.get('agent') else ''
        
        # Create appropriate agent based on type
        if agent_type == 'audioagent':
            agent = self._create_audio_agent(name, llm, config)
        elif agent_type == 'videoagent':
            agent = self._create_video_agent(name, llm, config)
        elif agent_type == 'imageagent':
            agent = self._create_image_agent(name, llm, config)
        elif agent_type == 'ocragent':
            agent = self._create_ocr_agent(name, llm, config)
        elif agent_type == 'deepresearchagent':
            agent = self._create_deep_research_agent(name, llm, config)
        else:
            # Default: create standard Agent
            agent = Agent(
                name=name,
                role=role,
                goal=goal,
                instructions=instructions,
                backstory=backstory,
                llm=llm,
                tools=tools if tools else None,
            )
        
        # Store additional attributes for later use
        agent._yaml_planning = planning
        agent._yaml_reasoning = reasoning
        agent._yaml_allow_delegation = allow_delegation
        agent._yaml_max_iter = max_iter
        agent._yaml_cache = cache
        
        # Store additional agents.yaml fields for feature parity
        agent._yaml_max_rpm = max_rpm
        agent._yaml_max_execution_time = max_execution_time
        agent._yaml_reflect_llm = reflect_llm
        agent._yaml_min_reflect = min_reflect
        agent._yaml_max_reflect = max_reflect
        agent._yaml_system_template = system_template
        agent._yaml_prompt_template = prompt_template
        agent._yaml_response_template = response_template
        
        # Store tool_choice for forcing tool usage (auto, required, none)
        agent._yaml_tool_choice = tool_choice
        
        return agent
    
    def _create_audio_agent(self, name: str, llm: Optional[str], config: Dict[str, Any]) -> Any:
        """
        Create an AudioAgent for TTS/STT operations.
        
        Args:
            name: Agent name
            llm: LLM model (e.g., openai/tts-1, openai/whisper-1)
            config: Full agent configuration
            
        Returns:
            AudioAgent instance
        """
        from ..agent import AudioAgent
        
        # AudioAgent accepts: llm, audio config
        audio_config = config.get('audio', {})
        
        agent = AudioAgent(
            llm=llm,
            audio=audio_config if audio_config else None,
        )
        # Store name for identification
        agent.name = name
        return agent
    
    def _create_video_agent(self, name: str, llm: Optional[str], config: Dict[str, Any]) -> Any:
        """
        Create a VideoAgent for video generation.
        
        Args:
            name: Agent name
            llm: LLM model (e.g., openai/sora-2)
            config: Full agent configuration
            
        Returns:
            VideoAgent instance
        """
        from ..agent import VideoAgent
        
        # VideoAgent accepts: llm, video config
        video_config = config.get('video', {})
        
        agent = VideoAgent(
            llm=llm,
            video=video_config if video_config else None,
        )
        agent.name = name
        return agent
    
    def _create_image_agent(self, name: str, llm: Optional[str], config: Dict[str, Any]) -> Any:
        """
        Create an ImageAgent for image generation.
        
        Args:
            name: Agent name
            llm: LLM model (e.g., openai/dall-e-3)
            config: Full agent configuration
            
        Returns:
            ImageAgent instance
        """
        from ..agent import ImageAgent
        
        # ImageAgent accepts: llm, style, and other image config
        style = config.get('style', 'natural')
        
        agent = ImageAgent(
            llm=llm,
            style=style,
        )
        agent.name = name
        return agent
    
    def _create_ocr_agent(self, name: str, llm: Optional[str], config: Dict[str, Any]) -> Any:
        """
        Create an OCRAgent for text extraction from documents/images.
        
        Args:
            name: Agent name
            llm: LLM model (e.g., mistral/mistral-ocr-latest)
            config: Full agent configuration
            
        Returns:
            OCRAgent instance
        """
        from ..agent import OCRAgent
        
        # OCRAgent accepts: llm, ocr config
        ocr_config = config.get('ocr', {})
        
        agent = OCRAgent(
            llm=llm,
            ocr=ocr_config if ocr_config else None,
        )
        agent.name = name
        return agent
    
    def _create_deep_research_agent(self, name: str, llm: Optional[str], config: Dict[str, Any]) -> Any:
        """
        Create a DeepResearchAgent for automated research.
        
        Args:
            name: Agent name
            llm: LLM model (e.g., o3-deep-research)
            config: Full agent configuration
            
        Returns:
            DeepResearchAgent instance
        """
        from ..agent import DeepResearchAgent
        
        # DeepResearchAgent accepts: model, instructions, etc.
        instructions = config.get('instructions', config.get('backstory', ''))
        
        agent = DeepResearchAgent(
            name=name,
            model=llm or 'o3-deep-research',
            instructions=instructions,
        )
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
            else:
                # Fallback: try to import from praisonaiagents.tools
                try:
                    from praisonaiagents import tools as builtin_tools
                    if hasattr(builtin_tools, tool_name):
                        tool_func = getattr(builtin_tools, tool_name)
                        if callable(tool_func):
                            tools.append(tool_func)
                except (ImportError, AttributeError):
                    pass
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
            List of workflow steps (Agent, Task, or pattern objects)
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
            Step object (Agent, Task, or pattern)
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
        elif 'include' in step_data:
            return self._parse_include_step(step_data)
        elif 'if' in step_data:
            return self._parse_if_step(step_data)
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
            
            # Handle output_variable (store output in named variable for loop iteration)
            output_variable = step_data.get('output_variable')
            if output_variable:
                agent._yaml_output_variable = output_variable
            
            # Handle skip_on_failure (robustness: allow workflow to continue if step fails)
            skip_on_failure = step_data.get('skip_on_failure')
            if skip_on_failure is not None:
                agent._yaml_skip_on_failure = skip_on_failure
            
            # Handle retry_delay (robustness: seconds between retries)
            retry_delay = step_data.get('retry_delay')
            if retry_delay is not None:
                agent._yaml_retry_delay = retry_delay
            
            return agent
        else:
            raise ValueError(f"Agent '{agent_id}' not defined in agents section")
    
    def _parse_include_step(self, step_data: Dict) -> Include:
        """
        Parse an include pattern step.
        
        Args:
            step_data: Step definition with 'include' key
            
        Returns:
            Include pattern object
            
        YAML syntax:
            # Simple include
            - include: wordpress-publisher
            
            # Include with configuration
            - include:
                recipe: wordpress-publisher
                input: "{{previous_output}}"
        """
        include_config = step_data['include']
        
        if isinstance(include_config, str):
            # Simple form: include: recipe-name
            recipe_name = include_config
            input_template = None
        else:
            # Config form: include: {recipe: ..., input: ...}
            recipe_name = include_config.get('recipe', '')
            input_template = include_config.get('input')
        
        return Include(recipe=recipe_name, input=input_template)
    
    def _parse_if_step(self, step_data: Dict):
        """
        Parse a conditional branching (if:) pattern step.
        
        Args:
            step_data: Step definition with 'if' key
            
        Returns:
            If pattern object
            
        YAML syntax:
            - if:
                condition: "{{score}} > 80"
                then:
                  - agent: approver
                else:
                  - agent: rejector
        """
        from .workflows import If
        
        if_config = step_data['if']
        
        condition = if_config.get('condition', '')
        
        # Parse then steps
        then_steps = []
        then_config = if_config.get('then', [])
        for step in then_config:
            parsed = self._parse_single_step(step)
            if parsed:
                then_steps.append(parsed)
        
        # Parse else steps (optional)
        else_steps = []
        else_config = if_config.get('else', [])
        for step in else_config:
            parsed = self._parse_single_step(step)
            if parsed:
                else_steps.append(parsed)
        
        return If(
            condition=condition,
            then_steps=then_steps,
            else_steps=else_steps if else_steps else None
        )
    
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
    
    def _parse_loop_step(self, step_data: Dict):
        """
        Parse a loop pattern step.
        
        Args:
            step_data: Step definition with 'loop' key
            
        Returns:
            Loop pattern object
            
        Supports multiple syntax forms:
            # Simple form with agent at step level
            - loop:
                over: items
              agent: processor
              
            # Nested step form
            - loop:
                over: items
                parallel: true
              step:
                agent: processor
                
            # Full nested form
            - loop:
                over: items
                parallel: true
                max_workers: 4
                step: processor
            
            # Multi-step form (NEW) - steps at step_data level
            - loop:
                over: items
                parallel: true
              steps:
                - agent: researcher
                - agent: writer
            
            # Multi-step form (NEW) - steps inside loop config
            - loop:
                over: items
                parallel: true
                steps:
                  - agent: researcher
                  - agent: writer
        """
        loop_config = step_data['loop']
        
        # Get loop parameters
        over = loop_config.get('over')
        from_csv = loop_config.get('from_csv')
        from_file = loop_config.get('from_file')
        var_name = loop_config.get('var_name', 'item')
        parallel_flag = loop_config.get('parallel', False)
        max_workers_raw = loop_config.get('max_workers')
        # Ensure max_workers is int (YAML may parse as string or contain template)
        max_workers = None
        if max_workers_raw is not None:
            try:
                max_workers = int(max_workers_raw)
            except (ValueError, TypeError):
                # If it's a template variable like {{max_workers}}, leave as None
                max_workers = None
        
        # Check for multi-step form (NEW) - steps: at step_data level or inside loop config
        nested_steps = step_data.get('steps') or loop_config.get('steps')
        if nested_steps and isinstance(nested_steps, list) and len(nested_steps) > 0:
            # Parse each nested step
            parsed_steps = []
            for nested_step_data in nested_steps:
                parsed_step = self._parse_single_step(nested_step_data)
                if parsed_step is not None:
                    parsed_steps.append(parsed_step)
            
            if parsed_steps:
                # Extract output_variable from step level
                output_variable = step_data.get('output_variable')
                
                return loop(
                    steps=parsed_steps,
                    over=over, 
                    from_csv=from_csv, 
                    from_file=from_file,
                    var_name=var_name,
                    parallel=parallel_flag, 
                    max_workers=max_workers,
                    output_variable=output_variable
                )
        
        # Resolve the step/agent to execute (single step - backward compat)
        agent_or_step = None
        
        # First check for agent at step level (original syntax)
        agent_id = step_data.get('agent')
        if agent_id and agent_id in self._agents:
            agent_or_step = self._agents[agent_id]
            # Store action if present
            if 'action' in step_data:
                agent_or_step._yaml_action = step_data['action']
        
        # Check for step: syntax (nested form)
        if 'step' in step_data:
            step_def = step_data['step']
            if isinstance(step_def, dict) and 'agent' in step_def:
                agent_id = step_def['agent']
                if agent_id in self._agents:
                    agent_or_step = self._agents[agent_id]
                    if 'action' in step_def:
                        agent_or_step._yaml_action = step_def['action']
            elif isinstance(step_def, str):
                # step: agent_name shorthand
                if step_def in self._agents:
                    agent_or_step = self._agents[step_def]
        
        # Check for step inside loop config
        if 'step' in loop_config:
            step_def = loop_config['step']
            if isinstance(step_def, str) and step_def in self._agents:
                agent_or_step = self._agents[step_def]
        
        # Check for include at step level (include inside loop)
        if agent_or_step is None and 'include' in step_data:
            include_value = step_data['include']
            if isinstance(include_value, str):
                agent_or_step = Include(recipe=include_value)
            elif isinstance(include_value, dict):
                agent_or_step = Include(
                    recipe=include_value.get('recipe', ''),
                    input=include_value.get('input')
                )
        
        if agent_or_step is None:
            raise ValueError("Loop step requires an agent, include, or steps")
        
        # Extract output_variable from step level (where user specifies it in YAML)
        output_variable = step_data.get('output_variable')
        
        return loop(
            step=agent_or_step, 
            over=over, 
            from_csv=from_csv, 
            from_file=from_file,
            var_name=var_name,
            parallel=parallel_flag, 
            max_workers=max_workers,
            output_variable=output_variable
        )
    
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
    
    def _parse_generic_step(self, step_data: Dict) -> Task:
        """
        Parse a generic workflow step.
        
        Args:
            step_data: Step definition dictionary
            
        Returns:
            Task object
        """
        name = step_data.get('name', 'step')
        action = step_data.get('action', '')
        
        return Task(
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
