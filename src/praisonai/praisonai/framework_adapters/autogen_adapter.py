"""
AutoGen framework adapters.

Provides lazy-loaded integration with AutoGen v0.2, AutoGen v0.4, and AG2 frameworks.
"""

import logging
from typing import Dict, List, Any
from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class AutoGenAdapter(BaseFrameworkAdapter):
    """Adapter for AutoGen v0.2 framework."""
    
    name = "autogen"
    install_hint = 'pip install "praisonai[autogen]"'  # v0.2 only
    requires_tools_extra = True
    
    def is_available(self) -> bool:
        """Check if AutoGen v0.2 is available for import."""
        try:
            import autogen  # noqa: F401
            return True
        except ImportError:
            return False
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """
        Run AutoGen v0.2 with given configuration.
        
        Args:
            config: AutoGen configuration with agents
            llm_config: LLM configuration list
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        # Availability already validated at CLI entry
        
        # Import AutoGen only when needed
        import autogen
        
        logger.info("Starting AutoGen v0.2 execution...")
        
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
    


class AutoGenV4Adapter(BaseFrameworkAdapter):
    """Adapter for AutoGen v0.4 framework."""
    
    name = "autogen_v4"
    install_hint = 'pip install "praisonai[autogen-v4]"'
    requires_tools_extra = True
    
    def is_available(self) -> bool:
        """Check if AutoGen v0.4 is available for import."""
        try:
            from autogen_agentchat.agents import AssistantAgent  # noqa: F401
            from autogen_ext.models.openai import OpenAIChatCompletionClient  # noqa: F401
            return True
        except ImportError:
            return False
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """
        Run AutoGen v0.4 with given configuration.
        
        Args:
            config: AutoGen v0.4 configuration with agents
            llm_config: LLM configuration list
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        # Availability already validated at CLI entry
        
        logger.info("Starting AutoGen v0.4 execution...")
        # For now, return a proper error message instead of delegating
        # TODO: Implement full AutoGen v0.4 adapter logic
        logger.warning("AutoGen v0.4 adapter is not yet fully implemented")
        return "### AutoGen v0.4 Output ###\nAutoGen v0.4 adapter is not yet fully implemented. Please use 'autogen' framework for AutoGen v0.2 support."


class AG2Adapter(BaseFrameworkAdapter):
    """Adapter for AG2 framework."""
    
    name = "ag2"
    install_hint = 'pip install "praisonai[ag2]"'
    requires_tools_extra = False
    
    def is_available(self) -> bool:
        """Check if AG2 is available for import."""
        try:
            import importlib.metadata as _importlib_metadata
            _importlib_metadata.distribution('ag2')
            from autogen import LLMConfig  # noqa: F401 — AG2-exclusive class
            return True
        except Exception:
            return False
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """
        Run AG2 with given configuration.
        
        Args:
            config: AG2 configuration with agents
            llm_config: LLM configuration list  
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        # Availability already validated at CLI entry
            
        logger.info("Starting AG2 execution...")
        # For now, return a proper error message instead of delegating
        # TODO: Implement full AG2 adapter logic
        logger.warning("AG2 adapter is not yet fully implemented")
        return "### AG2 Output ###\nAG2 adapter is not yet fully implemented. Please use 'autogen' framework for AutoGen/AG2 support."