"""
CrewAI framework adapter.

Provides lazy-loaded, scoped integration with CrewAI framework.
"""

import logging
from typing import Dict, List, Any, Optional, Callable
from .base import BaseFrameworkAdapter, scoped_telemetry_disable

logger = logging.getLogger(__name__)


class CrewAIAdapter(BaseFrameworkAdapter):
    """Adapter for CrewAI framework with scoped telemetry disabling."""
    
    name = "crewai"
    install_hint = 'pip install "praisonai[crewai]"'
    requires_tools_extra = True
    
    def _resolve_task_tools(self, tool_names: List[str], tools_dict: Optional[Dict[str, Any]]) -> List:
        """Resolve task tool names to tool objects via tools_dict."""
        if not tools_dict:
            return []
        return [tools_dict[tool_name] for tool_name in tool_names if tool_name in tools_dict]
    
    def is_available(self) -> bool:
        """Check if CrewAI is available for import."""
        try:
            import crewai  # noqa: F401
            return True
        except ImportError:
            return False
    
    def run(
        self,
        config: Dict[str, Any],
        llm_config: List[Dict],
        topic: str,
        *,
        tools_dict: Optional[Dict[str, Any]] = None,
        agent_callback: Optional[Callable] = None,
        task_callback: Optional[Callable] = None,
        cli_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Run CrewAI with given configuration.
        
        Args:
            config: CrewAI configuration with agents and tasks
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Available tools dictionary
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        # Import CrewAI only when needed (availability already validated at CLI entry)
        from crewai import Agent, Task, Crew
        from crewai.telemetry import Telemetry
        
        # Suppress crewai.cli.config logger (scoped to when CrewAI is actually used)
        logging.getLogger('crewai.cli.config').setLevel(logging.ERROR)
        
        # Use scoped telemetry disabling instead of global patching
        with scoped_telemetry_disable(Telemetry):
            # For now, use simplified CrewAI execution
            agents = {}
            tasks = []
            
            # Create agents
            for agent_name, agent_details in config.get('roles', {}).items():
                # Resolve tools for this agent from tools_dict
                agent_tool_list = []
                if tools_dict:
                    agent_tools = agent_details.get('tools', [])
                    agent_tool_list = [tools_dict[t] for t in agent_tools if t in tools_dict]
                
                # Extract LLM config for this agent
                agent_llm = None
                function_calling_llm = None
                if llm_config:
                    # Use first config as default
                    agent_llm = llm_config[0]
                    function_calling_llm = llm_config[0] if len(llm_config) == 1 else llm_config[1] if len(llm_config) > 1 else llm_config[0]
                
                agent = Agent(
                    role=agent_details.get('role', agent_name),
                    goal=self._format_template(agent_details.get('goal', ''), topic=topic),
                    backstory=self._format_template(agent_details.get('backstory', ''), topic=topic),
                    tools=agent_tool_list,
                    allow_delegation=agent_details.get('allow_delegation', False),
                    llm=agent_llm,
                    function_calling_llm=function_calling_llm,
                    max_iter=agent_details.get('max_iter', 15),
                    max_rpm=agent_details.get('max_rpm'),
                    max_execution_time=agent_details.get('max_execution_time'),
                    verbose=agent_details.get('verbose', True),
                    cache=agent_details.get('cache', True),
                    system_template=agent_details.get('system_template'),
                    prompt_template=agent_details.get('prompt_template'),
                    response_template=agent_details.get('response_template'),
                )
                if agent_callback:
                    agent.step_callback = agent_callback
                agents[agent_name] = agent
            
            # Store tasks by name for context linking
            tasks_dict = {}
            
            # Create tasks
            for agent_name, agent_details in config.get('roles', {}).items():
                for task_name, task_details in agent_details.get('tasks', {}).items():
                    task = Task(
                        description=self._format_template(task_details['description'], topic=topic),
                        expected_output=self._format_template(task_details['expected_output'], topic=topic),
                        agent=agents[agent_name],
                        tools=self._resolve_task_tools(task_details.get('tools', []), tools_dict),
                        async_execution=task_details.get('async_execution', False),
                        config=task_details.get('config', {}),
                        output_json=task_details.get('output_json'),
                        output_pydantic=task_details.get('output_pydantic'),
                        output_file=task_details.get('output_file', ''),
                        callback=task_details.get('callback'),
                        human_input=task_details.get('human_input', False),
                        create_directory=task_details.get('create_directory', False)
                    )
                    if task_callback:
                        task.callback = task_callback
                    tasks.append(task)
                    tasks_dict[task_name] = task
            
            # Set up task contexts - second pass to link dependencies
            for agent_details in config.get('roles', {}).values():
                for task_name, task_details in agent_details.get('tasks', {}).items():
                    if 'context' in task_details:
                        task = tasks_dict[task_name]
                        context_tasks = [tasks_dict[ctx] for ctx in task_details['context'] 
                                       if ctx in tasks_dict]
                        task.context = context_tasks
            
            # Create and run crew
            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True
            )
            
            logger.info("Starting CrewAI execution...")
            result = crew.kickoff()
            logger.info("CrewAI execution completed")
            
            return str(result)
    
