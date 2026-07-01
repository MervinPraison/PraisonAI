"""
Handoff Handler for CLI.

Provides agent-to-agent delegation capability with unified HandoffConfig support.

Usage:
    praisonai "Complex task" --handoff "researcher,writer,editor"
    praisonai "Task" --handoff "a,b" --handoff-policy summary --handoff-timeout 60
"""

from typing import Any, Dict, Tuple, List
from .base import FlagHandler


class HandoffHandler(FlagHandler):
    """
    Handler for --handoff flag.
    
    Enables agent-to-agent delegation for complex tasks with unified HandoffConfig.
    
    Example:
        praisonai "Research and write article" --handoff "researcher,writer"
        praisonai "Analyze data" --handoff "analyst,viz" --handoff-policy summary
        praisonai "Task" --handoff "a,b" --handoff-timeout 60 --handoff-max-depth 5
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
    
    def create_agents_with_handoff(
        self, 
        agent_names: List[str], 
        llm: str = None,
        context_policy: str = None,
        timeout_seconds: float = None,
        max_concurrent: int = None,
        max_depth: int = None,
        detect_cycles: bool = None,
    ) -> List[Any]:
        """
        Create agents with handoff capability.
        
        Args:
            agent_names: List of agent role names
            llm: Optional LLM model name
            context_policy: Context sharing policy (full, summary, none, last_n)
            timeout_seconds: Timeout for handoff execution
            max_concurrent: Maximum concurrent handoffs
            max_depth: Maximum handoff chain depth
            detect_cycles: Enable cycle detection
            
        Returns:
            List of Agent instances with handoff configured
        """
        available, msg = self.check_dependencies()
        if not available:
            self.print_status(msg, "error")
            return []
        
        from praisonaiagents import Agent, handoff
        
        agents = []
        
        # First pass: Create all agents without handoffs
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
        
        # Second pass: Set up handoffs by recreating agents with handoff config
        final_agents = []
        for i, name in enumerate(agent_names):
            agent_config = {
                "name": name.title().replace("_", " "),
                "role": name.title().replace("_", " "),
                "goal": f"Complete tasks as {name}",
                "backstory": f"Expert {name} with specialized skills"
            }
            
            if llm:
                agent_config["llm"] = llm
            
            # Add handoff to next agent if not the last agent
            if i < len(agent_names) - 1:
                next_agent = agents[i + 1]
                next_agent_name = agent_names[i + 1]
                
                # Build handoff kwargs with config options
                handoff_kwargs = {
                    "agent": next_agent,
                    "tool_name_override": f"handoff_to_{next_agent_name}",
                    "tool_description_override": f"Hand off the task to {next_agent_name}. Call this after completing your part."
                }
                
                # Add config options if provided
                if context_policy is not None:
                    handoff_kwargs["context_policy"] = context_policy
                if timeout_seconds is not None:
                    handoff_kwargs["timeout_seconds"] = timeout_seconds
                if max_concurrent is not None:
                    handoff_kwargs["max_concurrent"] = max_concurrent
                if max_depth is not None:
                    handoff_kwargs["max_depth"] = max_depth
                if detect_cycles is not None:
                    handoff_kwargs["detect_cycles"] = detect_cycles
                
                # Pass handoffs via constructor - this properly registers them as tools
                agent_config["handoffs"] = [handoff(**handoff_kwargs)]
                
                # Add instructions to use handoff
                agent_config["instructions"] = f"After completing your task, you MUST use the handoff_to_{next_agent_name} tool to pass your work to the next agent."
            
            final_agent = Agent(**agent_config)
            final_agents.append(final_agent)
        
        self.print_status(f"🤝 Created {len(final_agents)} agents with handoff chain", "success")
        for i, name in enumerate(agent_names):
            arrow = " → " if i < len(agent_names) - 1 else ""
            self.print_status(f"  {name}{arrow}", "info")
        
        # Show config if non-default
        if any([context_policy, timeout_seconds, max_concurrent, max_depth, detect_cycles is not None]):
            config_info = []
            if context_policy:
                config_info.append(f"policy={context_policy}")
            if timeout_seconds:
                config_info.append(f"timeout={timeout_seconds}s")
            if max_depth:
                config_info.append(f"max_depth={max_depth}")
            if config_info:
                self.print_status(f"  Config: {', '.join(config_info)}", "info")
        
        return final_agents
    
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
    
    def execute(
        self, 
        prompt: str = None, 
        agent_names: str = None, 
        llm: str = None,
        context_policy: str = None,
        timeout_seconds: float = None,
        max_concurrent: int = None,
        max_depth: int = None,
        detect_cycles: bool = None,
        **kwargs
    ) -> Any:
        """
        Execute task with handoff agents.
        
        Args:
            prompt: Task prompt
            agent_names: Comma-separated agent names
            llm: Optional LLM model
            context_policy: Context sharing policy (full, summary, none, last_n)
            timeout_seconds: Timeout for handoff execution
            max_concurrent: Maximum concurrent handoffs
            max_depth: Maximum handoff chain depth
            detect_cycles: Enable cycle detection
            
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
        
        agents = self.create_agents_with_handoff(
            names, 
            llm=llm,
            context_policy=context_policy,
            timeout_seconds=timeout_seconds,
            max_concurrent=max_concurrent,
            max_depth=max_depth,
            detect_cycles=detect_cycles,
        )
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
