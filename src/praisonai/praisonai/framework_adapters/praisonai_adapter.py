"""
PraisonAI agents framework adapter.

Provides lazy-loaded integration with the PraisonAI agents framework.
"""

import logging
from typing import Dict, List, Any, Optional
from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class PraisonAIAdapter(BaseFrameworkAdapter):
    """Adapter for PraisonAI agents framework."""
    
    name = "praisonai"
    install_hint = 'pip install praisonaiagents'
    requires_tools_extra = False
    
    def is_available(self) -> bool:
        """Check if PraisonAI agents is available for import."""
        try:
            from praisonaiagents import Agent, Task, AgentTeam  # noqa: F401
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
        Run PraisonAI agents with given configuration.
        
        Args:
            config: PraisonAI configuration with agents and tasks
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Available tools dictionary
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        if not self.is_available():
            raise ImportError("PraisonAI agents is not available. Install with: pip install praisonaiagents")
            
        # Import PraisonAI components only when needed
        from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, AgentTeam
        
        logger.info("Starting PraisonAI execution...")
        
        # Basic implementation - create agents and tasks from config
        agents = {}
        tasks = []
        
        # Get model from llm_config or environment
        model_name = "gpt-4o-mini"
        if llm_config and llm_config[0].get('model'):
            model_name = llm_config[0]['model']
        
        # Create agents from roles
        for role, details in config.get('roles', {}).items():
            role_filled = self._format_template(details.get('role', role), topic=topic)
            goal_filled = self._format_template(details.get('goal', ''), topic=topic)
            backstory_filled = self._format_template(details.get('backstory', ''), topic=topic)
            
            # Resolve tools for this agent from tools_dict
            agent_tool_list = []
            if tools_dict:
                agent_tools = details.get('tools', [])
                agent_tool_list = [tools_dict[t] for t in agent_tools if t in tools_dict]
            
            # Create basic agent
            agent = PraisonAgent(
                name=role_filled,
                role=role_filled,
                goal=goal_filled,
                backstory=backstory_filled,
                instructions=details.get('instructions'),
                llm=model_name,
                allow_delegation=details.get('allow_delegation', False),
                tools=agent_tool_list,
            )
            
            if agent_callback:
                agent.step_callback = agent_callback
                
            agents[role] = agent
            
            # Create tasks for the agent
            agent_tasks = details.get('tasks', {})
            if not agent_tasks:
                # Auto-generate a task
                task_description = details.get('instructions') or backstory_filled
                task = PraisonTask(
                    description=task_description,
                    expected_output="Complete the assigned task successfully.",
                    agent=agent,
                )
                if task_callback:
                    task.callback = task_callback
                tasks.append(task)
            else:
                for task_name, task_details in agent_tasks.items():
                    description_filled = self._format_template(
                        task_details['description'], topic=topic
                    )
                    expected_output_filled = self._format_template(
                        task_details['expected_output'], topic=topic
                    )
                    
                    task = PraisonTask(
                        description=description_filled,
                        expected_output=expected_output_filled,
                        agent=agent,
                    )
                    
                    if task_callback:
                        task.callback = task_callback
                    
                    tasks.append(task)
        
        # Create and run the team
        memory = config.get('memory', False)
        
        if config.get('process') == 'hierarchical':
            team = AgentTeam(
                agents=list(agents.values()),
                tasks=tasks,
                process="hierarchical",
                manager_llm=config.get('manager_llm') or model_name,
                memory=memory
            )
        else:
            team = AgentTeam(
                agents=list(agents.values()),
                tasks=tasks,
                memory=memory
            )
        
        response = team.start()
        result = f"### PraisonAI Output ###\n{response}" if response else "### PraisonAI Output ###\nTask completed."
        
        logger.info("PraisonAI execution completed")
        return result
    
