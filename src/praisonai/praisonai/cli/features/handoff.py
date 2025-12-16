"""
Handoff Handler for CLI.

Provides agent-to-agent delegation capability.
Usage: praisonai "Complex task" --handoff "researcher,writer,editor"
"""

from typing import Any, Dict, Tuple, List
from .base import FlagHandler


class HandoffHandler(FlagHandler):
    """
    Handler for --handoff flag.
    
    Enables agent-to-agent delegation for complex tasks.
    
    Example:
        praisonai "Research and write article" --handoff "researcher,writer"
        praisonai "Analyze and visualize data" --handoff "analyst,visualizer"
    """
    
    @property
    def feature_name(self) -> str:
        return "handoff"
    
    @property
    def flag_name(self) -> str:
        return "handoff"
    
    @property
    def flag_help(self) -> str:
        return "Comma-separated list of agent roles for task delegation"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if Handoff is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents") is not None:
                return True, ""
            return False, "praisonaiagents not installed"
        except ImportError:
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
    
    def parse_agent_names(self, names_str: str) -> List[str]:
        """
        Parse comma-separated agent names.
        
        Args:
            names_str: Comma-separated string of agent names/roles
            
        Returns:
            List of agent names
        """
        if not names_str:
            return []
        return [name.strip() for name in names_str.split(',') if name.strip()]
    
    def create_agents_with_handoff(self, agent_names: List[str], llm: str = None) -> List[Any]:
        """
        Create agents with handoff capability.
        
        Args:
            agent_names: List of agent role names
            llm: Optional LLM model name
            
        Returns:
            List of Agent instances with handoff configured
        """
        available, msg = self.check_dependencies()
        if not available:
            self.print_status(msg, "error")
            return []
        
        from praisonaiagents import Agent, Handoff
        
        agents = []
        
        # Create agents for each role
        for i, name in enumerate(agent_names):
            agent_config = {
                "name": name.title().replace("_", " "),
                "role": name.title().replace("_", " "),
                "goal": f"Complete tasks as {name}",
                "backstory": f"Expert {name} with specialized skills"
            }
            
            if llm:
                agent_config["llm"] = llm
            
            agent = Agent(**agent_config)
            agents.append(agent)
        
        # Set up handoffs between agents
        for i, agent in enumerate(agents[:-1]):
            next_agent = agents[i + 1]
            handoff = Handoff(
                target=next_agent,
                name=f"handoff_to_{agent_names[i + 1]}",
                description=f"Hand off task to {agent_names[i + 1]} for further processing"
            )
            
            # Add handoff to agent
            if not hasattr(agent, 'handoffs') or agent.handoffs is None:
                agent.handoffs = []
            agent.handoffs.append(handoff)
        
        self.print_status(f"🤝 Created {len(agents)} agents with handoff chain", "success")
        for i, name in enumerate(agent_names):
            arrow = " → " if i < len(agent_names) - 1 else ""
            self.print_status(f"  {name}{arrow}", "info")
        
        return agents
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply handoff configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Comma-separated agent names
            
        Returns:
            Modified configuration
        """
        if flag_value:
            agent_names = self.parse_agent_names(flag_value)
            config['handoff_agents'] = agent_names
            config['use_handoff'] = True
        return config
    
    def execute(self, prompt: str = None, agent_names: str = None, llm: str = None, **kwargs) -> Any:
        """
        Execute task with handoff agents.
        
        Args:
            prompt: Task prompt
            agent_names: Comma-separated agent names
            llm: Optional LLM model
            
        Returns:
            Task result
        """
        if not agent_names:
            self.print_status("No agent names provided for handoff", "error")
            return None
        
        names = self.parse_agent_names(agent_names)
        if len(names) < 2:
            self.print_status("Handoff requires at least 2 agents", "error")
            return None
        
        agents = self.create_agents_with_handoff(names, llm)
        if not agents:
            return None
        
        if prompt:
            # Execute with first agent
            try:
                result = agents[0].start(prompt)
                return result
            except Exception as e:
                self.print_status(f"Handoff execution failed: {e}", "error")
                return None
        
        return agents
