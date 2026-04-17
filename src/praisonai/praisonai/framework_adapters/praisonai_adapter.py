"""
PraisonAI agents framework adapter.

Provides lazy-loaded integration with the PraisonAI agents framework.
"""

import logging
from typing import Dict, List, Any
from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class PraisonAIAdapter(BaseFrameworkAdapter):
    """Adapter for PraisonAI agents framework."""
    
    name = "praisonai"
    
    def is_available(self) -> bool:
        """Check if PraisonAI agents is available for import."""
        try:
            from praisonaiagents import Agent, Task, AgentTeam  # noqa: F401
            return True
        except ImportError:
            return False
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """
        Run PraisonAI agents with given configuration.
        
        Args:
            config: PraisonAI configuration with agents and tasks
            llm_config: LLM configuration list
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        if not self.is_available():
            raise ImportError("PraisonAI agents is not available. Install with: pip install praisonaiagents")
            
        # Import PraisonAI agents only when needed
        from praisonaiagents import Agent, Task, AgentTeam
        
        logger.info("Starting PraisonAI agents execution...")
        
        agents = []
        tasks = []
        
        # Create agents
        for agent_name, agent_details in config.get('agents', {}).items():
            agent = Agent(
                name=agent_name,
                instructions=self._format_template(agent_details.get('backstory', ''), topic=topic)
            )
            agents.append(agent)
        
        # Create tasks
        for agent_name, agent_details in config.get('agents', {}).items():
            agent = next((a for a in agents if a.name == agent_name), None)
            if agent:
                for task_name, task_details in agent_details.get('tasks', {}).items():
                    task = Task(
                        name=task_name,
                        description=self._format_template(task_details['description'], topic=topic),
                        agent=agent
                    )
                    tasks.append(task)
        
        # Create and run agent team
        team = AgentTeam(agents=agents, tasks=tasks)
        result = team.start()
        
        logger.info("PraisonAI agents execution completed")
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