"""
CrewAI framework adapter.

Provides lazy-loaded, scoped integration with CrewAI framework.
"""

import logging
from typing import Dict, List, Any
from .base import BaseFrameworkAdapter, scoped_telemetry_disable

logger = logging.getLogger(__name__)


class CrewAIAdapter(BaseFrameworkAdapter):
    """Adapter for CrewAI framework with scoped telemetry disabling."""
    
    name = "crewai"
    
    def is_available(self) -> bool:
        """Check if CrewAI is available for import."""
        try:
            import crewai  # noqa: F401
            return True
        except ImportError:
            return False
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """
        Run CrewAI with given configuration.
        
        Args:
            config: CrewAI configuration with agents and tasks
            llm_config: LLM configuration list
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        if not self.is_available():
            raise ImportError("CrewAI is not available. Install with: pip install crewai")
            
        # Import CrewAI only when needed
        from crewai import Agent, Task, Crew
        from crewai.telemetry import Telemetry
        
        # Use scoped telemetry disabling instead of global patching
        with scoped_telemetry_disable(Telemetry):
            agents = {}
            tasks = []
            
            # Create agents
            for agent_name, agent_details in config.get('agents', {}).items():
                agent = Agent(
                    role=agent_details.get('role', agent_name),
                    goal=self._format_template(agent_details.get('goal', ''), topic=topic),
                    backstory=self._format_template(agent_details.get('backstory', ''), topic=topic),
                    verbose=True,
                    allow_delegation=agent_details.get('allow_delegation', False)
                )
                agents[agent_name] = agent
            
            # Create tasks
            for agent_name, agent_details in config.get('agents', {}).items():
                for task_name, task_details in agent_details.get('tasks', {}).items():
                    task = Task(
                        description=self._format_template(task_details['description'], topic=topic),
                        expected_output=self._format_template(task_details['expected_output'], topic=topic),
                        agent=agents[agent_name]
                    )
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
    
    def _format_template(self, template: str, **kwargs) -> str:
        """Safely format template string with given kwargs."""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Template formatting failed for key {e}, returning original template")
            return template
        except Exception as e:
            logger.warning(f"Template formatting error: {e}, returning original template")
            return template