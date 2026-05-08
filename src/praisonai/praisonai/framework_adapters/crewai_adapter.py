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
                
                agent = Agent(
                    role=agent_details.get('role', agent_name),
                    goal=self._format_template(agent_details.get('goal', ''), topic=topic),
                    backstory=self._format_template(agent_details.get('backstory', ''), topic=topic),
                    tools=agent_tool_list,
                    verbose=True,
                    allow_delegation=agent_details.get('allow_delegation', False)
                )
                if agent_callback:
                    agent.step_callback = agent_callback
                agents[agent_name] = agent
            
            # Create tasks
            for agent_name, agent_details in config.get('roles', {}).items():
                for task_name, task_details in agent_details.get('tasks', {}).items():
                    task = Task(
                        description=self._format_template(task_details['description'], topic=topic),
                        expected_output=self._format_template(task_details['expected_output'], topic=topic),
                        agent=agents[agent_name]
                    )
                    if task_callback:
                        task.callback = task_callback
                    tasks.append(task)
            
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
    
