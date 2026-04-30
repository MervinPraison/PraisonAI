"""
AutoGen framework adapters.

Provides lazy-loaded integration with AutoGen v0.2, AutoGen v0.4, and AG2 frameworks.
"""

import logging
import os
from typing import Dict, List, Any
from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class AutoGenAdapter(BaseFrameworkAdapter):
    """Adapter for AutoGen v0.2 framework."""
    
    name = "autogen"
    
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
        if not self.is_available():
            raise ImportError("AutoGen v0.2 is not available. Install with: pip install autogen")
            
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


class AutoGenV4Adapter(BaseFrameworkAdapter):
    """Adapter for AutoGen v0.4 framework."""
    
    name = "autogen_v4"
    implemented: bool = False  # explicit marker
    
    def is_available(self) -> bool:
        """Check if AutoGen v0.4 is available for import."""
        if not self.implemented:
            return False  # treat unimplemented as unavailable for dispatch
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
        raise NotImplementedError(
            "AutoGen v0.4 adapter is not yet implemented. "
            "Use framework='autogen' (v0.2) or pin AUTOGEN_VERSION=v0.2."
        )


class AG2Adapter(BaseFrameworkAdapter):
    """Adapter for AG2 framework."""
    
    name = "ag2"
    implemented: bool = False  # explicit marker
    
    def is_available(self) -> bool:
        """Check if AG2 is available for import."""
        if not self.implemented:
            return False  # treat unimplemented as unavailable for dispatch
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
        raise NotImplementedError(
            "AG2 adapter is not yet implemented. "
            "Use framework='autogen' (v0.2) or pin AUTOGEN_VERSION=v0.2."
        )


class AutoGenFamilyAdapter(BaseFrameworkAdapter):
    """Front door for the autogen family — picks the concrete version."""
    
    name = "autogen"

    def is_available(self) -> bool:
        """Check if any AutoGen variant is available."""
        return (
            AutoGenAdapter().is_available()
            or AutoGenV4Adapter().is_available()
            or AG2Adapter().is_available()
        )

    def resolve_alias(self) -> str:
        """Select the concrete AutoGen version based on environment and availability."""
        requested = os.environ.get("AUTOGEN_VERSION", "auto").lower()
        v2_available = AutoGenAdapter().is_available()
        v4_available = AutoGenV4Adapter().is_available()

        if requested == "v0.2" and v2_available:
            return "autogen_v2"
        if requested == "v0.4" and v4_available:
            return "autogen_v4"
        
        # auto: prefer v2 (v4 is currently unimplemented; see Issue 1)
        if v2_available:
            return "autogen_v2"
        elif v4_available:
            return "autogen_v4"
        else:
            return "autogen_v2"  # fallback to v2 for error handling

    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """Should not be called - resolve_alias() should redirect."""
        raise RuntimeError("Call resolve_alias() then dispatch to the concrete adapter.")