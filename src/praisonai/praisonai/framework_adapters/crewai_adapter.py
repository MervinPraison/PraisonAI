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
    install_hint = 'pip install "praisonai-frameworks[crewai]"'
    requires_tools_extra = True
    # CrewAI's kickoff() is sync-only; arun offloads run() to a bounded pool.
    SUPPORTS_ASYNC = False
    
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
        # Observability is initialized upstream (agents_generator._prepare_for_run);
        # finalize on EVERY exit path with the correct status so sessions are
        # never orphaned "in progress" on errors / cancellation. The guard starts
        # before the lazy imports so an import failure still finalizes the session.
        import sys as _sys
        from ..observability.hooks import finalize_observability

        try:
            # Import CrewAI only when needed (availability already validated at CLI entry)
            import os
            from crewai import Agent, Task, Crew
            from crewai.telemetry import Telemetry
            from .._framework_availability import is_available

            # Suppress crewai.cli.config logger (scoped to when CrewAI is actually used)
            logging.getLogger('crewai.cli.config').setLevel(logging.ERROR)

            # Use scoped telemetry disabling instead of global patching
            with scoped_telemetry_disable(Telemetry):
                from ._config_builder import build_agent_specs

                agents = {}
                tasks = []
                tasks_dict = {}

                # Single canonical YAML -> spec conversion (shared across adapters)
                specs = build_agent_specs(config, topic, tools_dict, self._format_template)

                # Create agents from the normalized specs
                for spec in specs:
                    details = spec.extras

                    # Configure LLM using shared resolver
                    llm = self._resolve_llm(details.get('llm'), llm_config)

                    # Configure function calling LLM using shared resolver
                    function_calling_llm = self._resolve_llm(details.get('function_calling_llm'), llm_config)

                    # Create CrewAI agent with full feature set
                    agent = Agent(
                        role=spec.role,
                        goal=spec.goal,
                        backstory=spec.backstory,
                        tools=spec.tools,
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

                    agents[spec.key] = agent

                    # Create tasks for the agent
                    for task_spec in spec.tasks:
                        task_details = task_spec.extras

                        task = Task(
                            description=task_spec.description,
                            expected_output=task_spec.expected_output,
                            agent=agent,
                            tools=task_spec.tools,
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
                        if task_spec.name in tasks_dict:
                            raise ValueError(
                                f"Duplicate CrewAI task name: {task_spec.name!r}. "
                                "Task names must be unique across roles so context "
                                "wiring resolves to the correct task."
                            )
                        tasks_dict[task_spec.name] = task

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

                return result
        finally:
            # Close observability session with status derived from exc state
            status = "Failure" if _sys.exc_info()[0] is not None else "Success"
            try:
                finalize_observability(self.name, status=status)
            except Exception as e:  # noqa: BLE001 -- telemetry must not crash the run
                logger.error(f"Error finalizing observability: {e}")
    
