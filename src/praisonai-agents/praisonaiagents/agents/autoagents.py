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
from ..main import display_instruction, display_tool_call, display_interaction, client

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

    def _generate_config(self) -> AutoAgentsConfig:
        """Generate the configuration for agents and tasks"""
        prompt = f"""
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

Return the configuration in a structured JSON format matching the AutoAgentsConfig schema.
"""
        
        try:
            response = client.beta.chat.completions.parse(
                model=self.llm,
                response_format=AutoAgentsConfig,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant designed to generate AI agent configurations."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Ensure we have exactly max_agents number of agents
            if len(response.choices[0].message.parsed.agents) > self.max_agents:
                response.choices[0].message.parsed.agents = response.choices[0].message.parsed.agents[:self.max_agents]
            elif len(response.choices[0].message.parsed.agents) < self.max_agents:
                logging.warning(f"Generated {len(response.choices[0].message.parsed.agents)} agents, expected {self.max_agents}")
            
            return response.choices[0].message.parsed
        except Exception as e:
            logging.error(f"Error generating configuration: {e}")
            raise

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
                reflect_llm=self.reflect_llm
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