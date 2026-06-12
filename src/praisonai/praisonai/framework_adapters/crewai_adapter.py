"""
CrewAI framework adapter.

Provides lazy-loaded, scoped integration with CrewAI framework.
"""

import logging
from typing import Dict, List, Any, Optional
from .base import BaseFrameworkAdapter, scoped_telemetry_disable

logger = logging.getLogger(__name__)


class CrewAIAdapter(BaseFrameworkAdapter):
    """Adapter for CrewAI framework with scoped telemetry disabling."""
    
    name = "crewai"
    install_hint = 'pip install "praisonai[crewai]"'
    requires_tools_extra = True
    
    def is_available(self) -> bool:
        """Check if CrewAI is available for import."""
        from .._framework_availability import is_available
        return is_available("crewai")
    
    def run(
        self,
        config: Dict[str, Any],
        llm_config: List[Dict],
        topic: str,
        *,
        tools_dict: Optional[Dict[str, Any]] = None,
        agent_callback = None,
        task_callback = None,
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
        import os
        from crewai import Agent, Task, Crew
        from crewai.telemetry import Telemetry
        from ..inc import PraisonAIModel
        from .._framework_availability import is_available
        
        # Suppress crewai.cli.config logger (scoped to when CrewAI is actually used)
        logging.getLogger('crewai.cli.config').setLevel(logging.ERROR)
        
        # Use scoped telemetry disabling instead of global patching
        with scoped_telemetry_disable(Telemetry):
            agents = {}
            tasks = []
            tasks_dict = {}

            # Create agents from config
            for role, details in config['roles'].items():
                role_filled = self._format_template(details['role'], topic=topic)
                goal_filled = self._format_template(details['goal'], topic=topic)
                backstory_filled = self._format_template(details['backstory'], topic=topic)
                
                # Get agent tools
                agent_tools = [tools_dict[tool] for tool in details.get('tools', []) 
                             if tools_dict and tool in tools_dict]
                
                # Configure LLM
                llm_model = details.get('llm')
                if llm_model:
                    llm = PraisonAIModel(
                        model=llm_model.get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-4o-mini",
                        base_url=llm_config[0].get('base_url') if llm_config else None,
                        api_key=llm_config[0].get('api_key') if llm_config else None
                    ).get_model()
                else:
                    llm = PraisonAIModel(
                        base_url=llm_config[0].get('base_url') if llm_config else None,
                        api_key=llm_config[0].get('api_key') if llm_config else None
                    ).get_model()

                # Configure function calling LLM
                function_calling_llm_model = details.get('function_calling_llm')
                if function_calling_llm_model:
                    function_calling_llm = PraisonAIModel(
                        model=function_calling_llm_model.get("model") or os.environ.get("MODEL_NAME") or "openai/gpt-4o-mini",
                        base_url=llm_config[0].get('base_url') if llm_config else None,
                        api_key=llm_config[0].get('api_key') if llm_config else None
                    ).get_model()
                else:
                    function_calling_llm = PraisonAIModel(
                        base_url=llm_config[0].get('base_url') if llm_config else None,
                        api_key=llm_config[0].get('api_key') if llm_config else None
                    ).get_model()

                # Create CrewAI agent with full feature set
                agent = Agent(
                    role=role_filled,
                    goal=goal_filled,
                    backstory=backstory_filled,
                    tools=agent_tools,
                    allow_delegation=details.get('allow_delegation', False),
                    llm=llm,
                    function_calling_llm=function_calling_llm,
                    max_iter=details.get('max_iter') or 15,
                    max_rpm=details.get('max_rpm') or None,
                    max_execution_time=details.get('max_execution_time') or None,
                    verbose=details.get('verbose', True),
                    cache=details.get('cache', True),
                    system_template=details.get('system_template') or None,
                    prompt_template=details.get('prompt_template') or None,
                    response_template=details.get('response_template') or None,
                )
                
                # Set agent callback if provided
                if agent_callback:
                    agent.step_callback = agent_callback

                agents[role] = agent

                # Create tasks for the agent
                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = self._format_template(task_details['description'], topic=topic)
                    expected_output_filled = self._format_template(task_details['expected_output'], topic=topic)

                    # Resolve task tools from tools_dict
                    task_tools = []
                    for tool_name in task_details.get('tools', []):
                        if isinstance(tool_name, str) and tools_dict and tool_name in tools_dict:
                            task_tools.append(tools_dict[tool_name])
                        elif callable(tool_name):
                            # Already a callable tool object
                            task_tools.append(tool_name)

                    task = Task(
                        description=description_filled,
                        expected_output=expected_output_filled,
                        agent=agent,
                        tools=task_tools,
                        async_execution=task_details.get('async_execution', False),
                        context=[],
                        config=task_details.get('config', {}),
                        output_json=task_details.get('output_json'),
                        output_pydantic=task_details.get('output_pydantic'),
                        output_file=task_details.get('output_file', ""),
                        callback=task_details.get('callback'),
                        human_input=task_details.get('human_input', False),
                        create_directory=task_details.get('create_directory', False)
                    )
                    
                    # Set task callback if provided
                    if task_callback:
                        task.callback = task_callback

                    tasks.append(task)
                    tasks_dict[task_name] = task

            # Set up task contexts
            for details in config['roles'].values():
                for task_name, task_details in details.get('tasks', {}).items():
                    task = tasks_dict[task_name]
                    context_tasks = [tasks_dict[ctx] for ctx in task_details.get('context', []) 
                                   if ctx in tasks_dict]
                    task.context = context_tasks

            # Create and run the crew
            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True
            )
            
            logger.debug("Final Crew Configuration:")
            logger.debug(f"Agents: {crew.agents}")
            logger.debug(f"Tasks: {crew.tasks}")

            response = crew.kickoff()
            result = f"### Task Output ###\n{response}"
            
            # Close observability session
            from ..observability.hooks import finalize_observability
            finalize_observability(self.name)
                
            return result
    
