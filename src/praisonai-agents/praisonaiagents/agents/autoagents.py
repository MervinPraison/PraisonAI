"""
AutoAgents - A class for automatically creating and managing AI agents and tasks.

This class provides a simplified interface for creating and running AI agents with tasks.
It automatically handles agent creation, task setup, and execution flow.
"""

from .agents import PraisonAIAgents
from ..agent.agent import Agent
from ..task.task import Task
from typing import List, Any, Optional, Dict, Tuple
import logging
import os
from pydantic import BaseModel, ConfigDict
from ..main import display_instruction, display_tool_call, display_interaction
from ..llm import get_openai_client, LLM, OpenAIClient
import json

# Define Pydantic models for structured output
class TaskConfig(BaseModel):
    name: str
    description: str
    expected_output: str
    tools: List[str]

class AgentConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    role: str
    goal: str
    backstory: str
    tools: List[str]
    tasks: List[TaskConfig]

class AutoAgentsConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    main_instruction: str
    process_type: str
    agents: List[AgentConfig]

class AutoAgents(PraisonAIAgents):
    def __init__(
        self,
        instructions: str,
        tools: Optional[List[Any]] = None,
        verbose: bool = False,
        process: str = "sequential",
        manager_llm: Optional[str] = None,
        max_retries: int = 5,
        completion_checker: Optional[Any] = None,
        allow_code_execution: bool = False,
        memory: bool = True,
        markdown: bool = True,
        self_reflect: bool = False,
        max_reflect: int = 3,
        min_reflect: int = 1,
        llm: Optional[str] = None,
        function_calling_llm: Optional[str] = None,
        respect_context_window: bool = True,
        code_execution_mode: str = "safe",
        embedder_config: Optional[Dict[str, Any]] = None,
        knowledge_sources: Optional[List[Any]] = None,
        use_system_prompt: bool = True,
        cache: bool = True,
        allow_delegation: bool = False,
        step_callback: Optional[Any] = None,
        system_template: Optional[str] = None,
        prompt_template: Optional[str] = None,
        response_template: Optional[str] = None,
        max_rpm: Optional[int] = None,
        max_execution_time: Optional[int] = None,
        max_iter: int = 20,
        reflect_llm: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_agents: int = 3  # New parameter for maximum number of agents
    ):
        """Initialize AutoAgents with configuration for automatic agent and task creation."""
        if max_agents < 1:
            raise ValueError("max_agents must be at least 1")
        if max_agents > 10:
            raise ValueError("max_agents cannot exceed 10")
            
        # Store all configuration parameters first
        self.instructions = instructions
        self.tools = tools or []
        self.verbose = verbose  # Store verbose parameter
        self.max_agents = max_agents  # Store max_agents parameter
        self.allow_code_execution = allow_code_execution
        self.memory = memory
        self.markdown = markdown
        self.self_reflect = self_reflect
        self.max_reflect = max_reflect
        self.min_reflect = min_reflect
        self.llm = llm or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
        self.function_calling_llm = function_calling_llm
        self.respect_context_window = respect_context_window
        self.code_execution_mode = code_execution_mode
        self.embedder_config = embedder_config
        self.knowledge_sources = knowledge_sources
        self.use_system_prompt = use_system_prompt
        self.cache = cache
        self.allow_delegation = allow_delegation
        self.step_callback = step_callback
        self.system_template = system_template
        self.prompt_template = prompt_template
        self.response_template = response_template
        self.max_rpm = max_rpm
        self.max_execution_time = max_execution_time
        self.max_iter = max_iter
        self.reflect_llm = reflect_llm
        self.base_url = base_url
        self.api_key = api_key
        
        # Display initial instruction
        if self.verbose:
            display_instruction(f"🎯 Main Task: {self.instructions}")
            display_instruction(f"📊 Maximum Agents: {self.max_agents}")
            if self.tools:
                tool_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
                display_tool_call(f"🛠️  Available Tools: {', '.join(tool_names)}")
        
        # Generate agents and tasks configuration
        config = self._generate_config()
        agents, tasks = self._create_agents_and_tasks(config)
        
        # Display agents and their tasks
        if self.verbose:
            self._display_agents_and_tasks(agents, tasks)
        
        # Initialize parent class with generated agents and tasks
        super().__init__(
            agents=agents,
            tasks=tasks,
            verbose=verbose,
            completion_checker=completion_checker,
            max_retries=max_retries,
            process=process,
            manager_llm=manager_llm
        )

    def _display_agents_and_tasks(self, agents: List[Agent], tasks: List[Task]):
        """Display the created agents and their assigned tasks"""
        display_instruction("\n🤖 Generated Agents and Tasks:")
        
        # Create a mapping of agents to their tasks
        agent_tasks = {}
        for task in tasks:
            if task.agent not in agent_tasks:
                agent_tasks[task.agent] = []
            agent_tasks[task.agent].append(task)
        
        # Display each agent and their tasks
        for agent in agents:
            agent_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in agent.tools]
            display_interaction(
                f"\n👤 Agent: {agent.name}",
                f"""Role: {agent.role}
Goal: {agent.goal}
Tools: {', '.join(agent_tools)}"""
            )
            
            # Display tasks for this agent
            if agent in agent_tasks:
                for i, task in enumerate(agent_tasks[agent], 1):
                    task_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in task.tools]
                    display_instruction(
                        f"""  📋 Task {i}: {task.name}
     Description: {task.description}
     Expected Output: {task.expected_output}
     Tools: {', '.join(task_tools)}"""
                    )

    def _get_available_tools(self) -> List[str]:
        """Get list of available tools"""
        if not self.tools:
            return []
        return [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]

    def _get_tool_by_name(self, tool_name: str) -> Optional[Any]:
        """Get tool object by its name"""
        for tool in self.tools:
            if (hasattr(tool, '__name__') and tool.__name__ == tool_name) or str(tool) == tool_name:
                return tool
        return None

    def _assign_tools_to_agent(self, agent_config: AgentConfig) -> List[Any]:
        """
        Assign appropriate tools to an agent based on its role and tasks.
        
        Args:
            agent_config: The agent configuration containing role and required tools
            
        Returns:
            List of tool objects assigned to this agent
        """
        assigned_tools = []
        tool_names = set(agent_config.tools)
        
        # Also look at task requirements
        for task in agent_config.tasks:
            tool_names.update(task.tools)
        
        # Assign tools that match the requirements
        for tool_name in tool_names:
            tool = self._get_tool_by_name(tool_name)
            if tool:
                assigned_tools.append(tool)
        
        # If no specific tools matched but we have tools available,
        # assign all tools to ensure functionality
        if not assigned_tools and self.tools:
            assigned_tools = self.tools
            
        return assigned_tools

    def _validate_config(self, config: AutoAgentsConfig) -> tuple[bool, str]:
        """
        Validate that the configuration has proper TaskConfig objects.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        for agent_idx, agent in enumerate(config.agents):
            if not hasattr(agent, 'tasks') or not agent.tasks:
                return False, f"Agent '{agent.name}' has no tasks defined"
            
            for task_idx, task in enumerate(agent.tasks):
                # Check if task is a proper TaskConfig instance
                if not isinstance(task, TaskConfig):
                    return False, f"Task at index {task_idx} for agent '{agent.name}' is not a proper TaskConfig object"
                
                # Check required fields
                if not task.name:
                    return False, f"Task at index {task_idx} for agent '{agent.name}' has no name"
                if not task.description:
                    return False, f"Task at index {task_idx} for agent '{agent.name}' has no description"
                if not task.expected_output:
                    return False, f"Task at index {task_idx} for agent '{agent.name}' has no expected_output"
                if task.tools is None:
                    return False, f"Task at index {task_idx} for agent '{agent.name}' has no tools field"
        
        return True, ""

    def _generate_config(self) -> AutoAgentsConfig:
        """Generate the configuration for agents and tasks with retry logic"""
        base_prompt = f"""
Generate a configuration for AI agents to accomplish this task: "{self.instructions}"

The configuration should include:
1. A main instruction that clearly states the overall goal
2. A process type (sequential, workflow, or hierarchical)
3. A list of maximum {self.max_agents} agents (no more, no less), each with:
   - Name, role, goal, and backstory
   - List of required tools from: {self._get_available_tools()}
   - Only add tools that are needed for the agent to perform its task
   - Only one task per agent. Add more than one task if absolutely necessary.
   - List of specific tasks they need to perform
   - Whether they should self-reflect or allow delegation

Requirements:
1. Each agent should have clear, focused responsibilities
2. Tasks should be broken down into manageable steps
3. Tool selection should be appropriate for each task
4. The process type should match the task requirements
5. Generate maximum {self.max_agents} agents to handle this task efficiently

Return the configuration in a structured JSON format matching this exact schema:
{{
  "main_instruction": "Overall goal description",
  "process_type": "sequential|workflow|hierarchical",
  "agents": [
    {{
      "name": "Agent Name",
      "role": "Agent Role",
      "goal": "Agent Goal",
      "backstory": "Agent Backstory",
      "tools": ["tool1", "tool2"],
      "tasks": [
        {{
          "name": "Task Name",
          "description": "Detailed task description",
          "expected_output": "What the task should produce",
          "tools": ["tool1", "tool2"]
        }}
      ]
    }}
  ]
}}

IMPORTANT: Each task MUST be an object with name, description, expected_output, and tools fields, NOT a simple string.
"""
        
        max_retries = 3
        last_response = None
        last_error = None
        
        for attempt in range(max_retries):
            # Initialize variables for this attempt
            use_openai_structured = False
            client = None
            
            # Prepare prompt for this attempt
            if attempt > 0 and last_response and last_error:
                # On retry, include the previous response and error
                prompt = f"""{base_prompt}

PREVIOUS ATTEMPT FAILED!
Your previous response was:
```json
{last_response}
```

Error: {last_error}

REMEMBER: Tasks MUST be objects with the following structure:
{{
  "name": "Task Name",
  "description": "Task Description",
  "expected_output": "Expected Output",
  "tools": ["tool1", "tool2"]
}}

DO NOT use strings for tasks. Each task MUST be a complete object with all four fields."""
            else:
                prompt = base_prompt
            
            try:
                # Check if we have OpenAI API and the model supports structured output
                from ..llm import supports_structured_outputs
                if self.llm and supports_structured_outputs(self.llm):
                    client = get_openai_client()
                    use_openai_structured = True
            except:
                # If OpenAI client is not available, we'll use the LLM class
                pass
            
            try:
                if use_openai_structured and client:
                    # Use OpenAI's structured output for OpenAI models (backward compatibility)
                    config = client.parse_structured_output(
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant designed to generate AI agent configurations."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format=AutoAgentsConfig,
                        model=self.llm
                    )
                    # Store the response for potential retry
                    last_response = json.dumps(config.model_dump(), indent=2)
                else:
                    # Use LLM class for all other providers (Gemini, Anthropic, etc.)
                    llm_instance = LLM(
                        model=self.llm,
                        base_url=self.base_url,
                        api_key=self.api_key
                    )
                    
                    response_text = llm_instance.get_response(
                        prompt=prompt,
                        system_prompt="You are a helpful assistant designed to generate AI agent configurations.",
                        output_pydantic=AutoAgentsConfig,
                        temperature=0.7,
                        stream=False,
                        verbose=False
                    )
                    
                    # Store the raw response for potential retry
                    last_response = response_text
                    
                    # Parse the JSON response
                    try:
                        # First try to parse as is
                        config_dict = json.loads(response_text)
                        config = AutoAgentsConfig(**config_dict)
                    except json.JSONDecodeError:
                        # If that fails, try to extract JSON from the response
                        # Handle cases where the model might wrap JSON in markdown blocks
                        cleaned_response = response_text.strip()
                        if cleaned_response.startswith("```json"):
                            cleaned_response = cleaned_response[7:]
                        if cleaned_response.startswith("```"):
                            cleaned_response = cleaned_response[3:]
                        if cleaned_response.endswith("```"):
                            cleaned_response = cleaned_response[:-3]
                        cleaned_response = cleaned_response.strip()
                        
                        config_dict = json.loads(cleaned_response)
                        config = AutoAgentsConfig(**config_dict)
                
                # Validate the configuration
                is_valid, error_msg = self._validate_config(config)
                if not is_valid:
                    last_error = error_msg
                    if attempt < max_retries - 1:
                        logging.warning(f"Configuration validation failed (attempt {attempt + 1}/{max_retries}): {error_msg}")
                        continue
                    else:
                        raise ValueError(f"Configuration validation failed after {max_retries} attempts: {error_msg}")
                
                # Ensure we have exactly max_agents number of agents
                if len(config.agents) > self.max_agents:
                    config.agents = config.agents[:self.max_agents]
                elif len(config.agents) < self.max_agents:
                    logging.warning(f"Generated {len(config.agents)} agents, expected {self.max_agents}")
                
                return config
                
            except ValueError as e:
                # Re-raise validation errors
                raise
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    logging.warning(f"Error generating configuration (attempt {attempt + 1}/{max_retries}): {e}")
                    continue
                else:
                    logging.error(f"Error generating configuration after {max_retries} attempts: {e}")
                    raise
        
        # This should never be reached due to the raise statements above
        raise RuntimeError(f"Failed to generate valid configuration after {max_retries} attempts")

    def _create_agents_and_tasks(self, config: AutoAgentsConfig) -> Tuple[List[Agent], List[Task]]:
        """Create agents and tasks from configuration"""
        agents = []
        tasks = []
        
        for agent_config in config.agents:
            # Get appropriate tools for this agent
            agent_tools = self._assign_tools_to_agent(agent_config)
            
            # Create the agent with all parameters
            agent = Agent(
                name=agent_config.name,
                role=agent_config.role,
                goal=agent_config.goal,
                backstory=agent_config.backstory,
                tools=agent_tools,  # Use assigned tools
                verbose=self.verbose >= 1,
                allow_code_execution=self.allow_code_execution,
                memory=self.memory,
                markdown=self.markdown,
                self_reflect=self.self_reflect,
                max_reflect=self.max_reflect,
                min_reflect=self.min_reflect,
                llm=self.llm,
                function_calling_llm=self.function_calling_llm,
                respect_context_window=self.respect_context_window,
                code_execution_mode=self.code_execution_mode,
                embedder_config=self.embedder_config,
                knowledge=self.knowledge_sources,
                use_system_prompt=self.use_system_prompt,
                cache=self.cache,
                allow_delegation=self.allow_delegation,
                step_callback=self.step_callback,
                system_template=self.system_template,
                prompt_template=self.prompt_template,
                response_template=self.response_template,
                max_rpm=self.max_rpm,
                max_execution_time=self.max_execution_time,
                max_iter=self.max_iter,
                reflect_llm=self.reflect_llm,
                base_url=self.base_url,
                api_key=self.api_key
            )
            agents.append(agent)
            
            # Create tasks for this agent
            for task_config in agent_config.tasks:
                # Get task-specific tools
                task_tools = [self._get_tool_by_name(t) for t in task_config.tools]
                task_tools = [t for t in task_tools if t]  # Remove None values
                
                # If no specific tools matched, use agent's tools
                if not task_tools:
                    task_tools = agent_tools
                
                task = Task(
                    name=task_config.name,
                    description=task_config.description,
                    expected_output=task_config.expected_output,
                    agent=agent,
                    tools=task_tools  # Use task-specific tools
                )
                tasks.append(task)
        
        return agents, tasks

    async def astart(self):
        """
        Async version of start() method.
        Creates tasks based on the instructions, then starts execution.
        Returns the task status and results dictionary.
        """
        return await super().astart()

    def start(self):
        """
        Creates tasks based on the instructions, then starts execution.
        Returns the task status and results dictionary.
        """
        return super().start()