"""
AutoGen framework adapters.

Provides lazy-loaded integration with AutoGen v0.2, AutoGen v0.4, and AG2 frameworks.
"""

import logging
import os
from typing import Dict, List, Any, Optional, Callable
from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class AutoGenAdapter(BaseFrameworkAdapter):
    """Adapter for AutoGen v0.2 framework with version resolution."""
    
    name = "autogen_v2"  # Changed from "autogen" to "autogen_v2" per PR fix
    install_hint = 'pip install "praisonai[autogen]"'  # v0.2 only
    requires_tools_extra = True
    
    def is_available(self) -> bool:
        """Check if AutoGen v0.2 is available for import."""
        from .._framework_availability import is_available
        return is_available("autogen")
    
    def resolve(self, *, config: Optional[Dict[str, Any]] = None) -> "BaseFrameworkAdapter":
        """Pick the concrete AutoGen adapter variant based on config and environment.
        
        Args:
            config: Framework configuration that may contain 'autogen_version'
            
        Returns:
            The resolved AutoGen adapter (v0.2 or v0.4)
        """
        # Priority: config['autogen_version'] > environment > 'auto'
        version = "auto"
        if config and config.get("autogen_version"):
            version = str(config["autogen_version"]).lower()
        else:
            version = os.environ.get("AUTOGEN_VERSION", "auto").lower()
        
        # Import the specific adapters
        v4_adapter = AutoGenV4Adapter()
        v2_adapter = self  # Current instance is v0.2
        
        if version == "v0.4" and v4_adapter.is_available():
            logger.info("AutoGen version resolution: Using v0.4 (explicitly requested)")
            return v4_adapter
        elif version == "v0.2" and v2_adapter.is_available():
            logger.info("AutoGen version resolution: Using v0.2 (explicitly requested)")
            return v2_adapter
        elif version == "auto":
            # Auto-detect: prefer v0.4 if available, fallback to v0.2
            if v4_adapter.is_available():
                logger.info("AutoGen version resolution: Using v0.4 (auto-detected)")
                return v4_adapter
            elif v2_adapter.is_available():
                logger.info("AutoGen version resolution: Using v0.2 (auto-detected)")
                return v2_adapter
        
        # If we get here, neither version is available
        raise ImportError(
            f"AutoGen is not available. Version requested: {version}. "
            f"Install with 'pip install praisonai[autogen]' for v0.2 or 'pip install praisonai[autogen-v4]' for v0.4"
        )
    
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
        Run AutoGen v0.2 with given configuration.
        
        Args:
            config: AutoGen configuration with agents
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Dictionary of available tools
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        # Availability already validated at CLI entry
        
        logger.info("Starting AutoGen v0.2 execution...")
        
        # Import AutoGen v0.2 modules
        import autogen
        
        llm_config_dict = {"config_list": llm_config}
        
        # Set up user proxy agent
        user_proxy = autogen.UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: (x.get("content") or "").rstrip().rstrip(".").lower().endswith("terminate") or "TERMINATE" in (x.get("content") or ""),
            code_execution_config={
                "work_dir": "coding",
                "use_docker": False,
            }
        )
        
        agents = {}
        tasks = []
        
        # Create agents from config
        for role, details in config.get('roles', {}).items():
            agent_name = self._format_template(details['role'], topic=topic)
            agent_goal = self._format_template(details['goal'], topic=topic)
            
            # Create AutoGen assistant agent
            agents[role] = autogen.AssistantAgent(
                name=agent_name,
                llm_config=llm_config_dict,
                system_message=self._format_template(details['backstory'], topic=topic) + 
                             ". Must Reply \"TERMINATE\" in the end when everything is done.",
            )
            
            # Register tools if specified
            if tools_dict and 'tools' in details:
                for tool_name in details['tools']:
                    if tool_name in tools_dict:
                        # Register tool with the agent
                        # This is a simplified approach - actual implementation may vary
                        pass
            
            # Prepare tasks
            for task_name, task_details in details.get('tasks', {}).items():
                description_filled = self._format_template(task_details['description'], topic=topic)
                
                chat_task = {
                    "recipient": agents[role],
                    "message": description_filled,
                    "summary_method": "last_msg",
                }
                tasks.append(chat_task)
        
        # Execute tasks
        response = user_proxy.initiate_chats(tasks)
        result = "### AutoGen v0.2 Output ###\n" + (response[-1].summary if hasattr(response[-1], 'summary') else "")
        
        logger.info("AutoGen v0.2 execution completed")
        return result
    
    def _format_template(self, template: str, **kwargs) -> str:
        """Safely format template string with given kwargs."""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing placeholder {e} in template: {template}")
            return template  # Return template as-is if formatting fails


class AutoGenV4Adapter(BaseFrameworkAdapter):
    """Adapter for AutoGen v0.4 framework."""
    
    name = "autogen_v4"
    install_hint = 'pip install "praisonai[autogen-v4]"'
    requires_tools_extra = True
    implemented: bool = False  # explicit marker
    
    def is_available(self) -> bool:
        """Check if AutoGen v0.4 is available for import."""
        if not self.implemented:
            return False  # treat unimplemented as unavailable for dispatch
        from .._framework_availability import is_available
        return is_available("autogen_v4")
    
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
        Run AutoGen v0.4 with given configuration.
        
        Args:
            config: AutoGen configuration with agents
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Dictionary of available tools
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        raise NotImplementedError(
            "AutoGen v0.4 adapter is not yet implemented. "
            "Use framework='autogen' (v0.2) or pin AUTOGEN_VERSION=v0.2."
        )


class AG2Adapter(BaseFrameworkAdapter):
    """Adapter for AG2 framework."""
    
    name = "ag2"
    install_hint = 'pip install "praisonai[ag2]"'
    requires_tools_extra = False
    implemented: bool = False  # explicit marker
    
    def is_available(self) -> bool:
        """Check if AG2 is available for import."""
        if not self.implemented:
            return False  # treat unimplemented as unavailable for dispatch
        from .._framework_availability import is_available
        return is_available("ag2")
    
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
        Run AG2 with given configuration.
        
        Args:
            config: AG2 configuration with agents
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Dictionary of available tools
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        raise NotImplementedError(
            "AG2 adapter is not yet implemented. "
            "Use framework='autogen' (v0.2) or pin AUTOGEN_VERSION=v0.2."
        )


class AutoGenFamilyAdapter(BaseFrameworkAdapter):
    """
    Router adapter for AutoGen family (v0.2, v0.4, AG2).
    Dispatches to concrete adapter based on config/environment.
    """
    
    name = "autogen"
    
    def is_available(self) -> bool:
        """Check if any AutoGen variant is available."""
        v2 = AutoGenAdapter()
        v4 = AutoGenV4Adapter()
        ag2 = AG2Adapter()
        return v2.is_available() or v4.is_available() or ag2.is_available()
    
    def resolve_alias(self) -> str:
        """Resolve which concrete AutoGen adapter to use."""
        requested = os.getenv("AUTOGEN_VERSION", "auto").lower()
        
        # Check availability
        v2_available = AutoGenAdapter().is_available()
        v4_available = AutoGenV4Adapter().is_available()
        ag2_available = AG2Adapter().is_available()

        # Explicit version pins with warnings if not available
        if requested == "v0.2":
            if not v2_available:
                logger.warning("AUTOGEN_VERSION=v0.2 requested but autogen (v0.2) is not installed")
            return "autogen_v2"
        if requested == "v0.4":
            if not v4_available:
                logger.warning("AUTOGEN_VERSION=v0.4 requested but autogen_agentchat (v0.4) is not installed")
            return "autogen_v4"
        if requested == "ag2":
            if not ag2_available:
                logger.warning("AUTOGEN_VERSION=ag2 requested but AG2 is not installed")
            return "ag2"
        
        # Auto selection: prefer v2 (v4 is currently unimplemented)
        if v2_available:
            return "autogen_v2"
        elif v4_available:
            logger.warning("AutoGen v0.4 is installed but not yet implemented, falling back.")
            return "autogen_v4"
        elif ag2_available:
            return "ag2"
        
        # Nothing available
        raise ImportError(
            "No AutoGen variant is available. Install with:\n"
            "  pip install 'praisonai[autogen]' for v0.2\n"
            "  pip install 'praisonai[autogen-v4]' for v0.4\n"
            "  pip install 'praisonai[ag2]' for AG2"
        )
    
    def resolve(self, *, config: Optional[Dict[str, Any]] = None) -> "BaseFrameworkAdapter":
        """Resolve to the concrete AutoGen adapter based on config/environment.
        
        This method is called by the orchestrator to get the actual adapter to use.
        
        Args:
            config: Framework configuration that may contain version hints
            
        Returns:
            The concrete AutoGen adapter instance
        """
        # Get the adapter name to use
        adapter_name = self.resolve_alias()
        
        # Import registry to create the concrete adapter
        from .registry import get_default_registry
        registry = get_default_registry()
        
        # Create and return the concrete adapter
        concrete_adapter = registry.create(adapter_name)
        logger.info(f"AutoGenFamilyAdapter resolved to: {adapter_name}")
        return concrete_adapter
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """Router should never run directly."""
        raise RuntimeError(
            "AutoGenFamilyAdapter.run() should not be called directly. "
            "The resolve() method should have been called first to get the concrete adapter."
        )