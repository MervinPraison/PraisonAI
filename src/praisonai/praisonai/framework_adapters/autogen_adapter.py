"""
AutoGen framework adapters.

Provides lazy-loaded integration with AutoGen v0.2, AutoGen v0.4, and AG2 frameworks.
"""

import logging
from typing import Dict, List, Any, Optional, Callable
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
    
    def _sanitize_agent_name_for_autogen_v4(self, name: str) -> str:
        """Sanitize agent name to be a valid Python identifier for AutoGen v0.4."""
        import re
        # Replace non-alphanumeric with underscores, ensure it starts with letter/underscore
        clean = re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
        if clean and not clean[0].isalpha() and clean[0] != '_':
            clean = '_' + clean
        return clean or 'agent'


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
            config: AutoGen v0.4 configuration with agents
            llm_config: LLM configuration list
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        # Import AutoGen v0.4 components
        import asyncio
        import os
        from autogen_agentchat.agents import AssistantAgent as AutoGenV4AssistantAgent
        from autogen_agentchat.teams import RoundRobinGroupChat
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        
        logger.info("Starting AutoGen v0.4 execution...")
        
        async def run_autogen_v4_async():
            # Create model client for v0.4
            model_config = llm_config[0] if llm_config else {}
            model_client = OpenAIChatCompletionClient(
                model=model_config.get('model', 'gpt-4o-mini'),
                api_key=model_config.get('api_key', os.environ.get("OPENAI_API_KEY")),
                base_url=model_config.get('base_url', "https://api.openai.com/v1")
            )
            
            agents = []
            combined_tasks = []
            
            # Create agents from config
            for role, details in config.get('roles', {}).items():
                # For AutoGen v0.4, ensure agent name is a valid Python identifier
                agent_name = self._format_template(details.get('role', role), topic=topic)
                agent_name = self._sanitize_agent_name_for_autogen_v4(agent_name)
                backstory = self._format_template(details.get('backstory', ''), topic=topic)
                
                # Convert tools for v0.4 - simplified tool passing
                agent_tools = []
                if tools_dict:
                    for tool_name in details.get('tools', []):
                        if tool_name in tools_dict:
                            tool_instance = tools_dict[tool_name]
                            # For v0.4, we can pass the tool's run method directly if it's callable
                            if hasattr(tool_instance, 'run') and callable(tool_instance.run):
                                agent_tools.append(tool_instance.run)
                
                # Create v0.4 AssistantAgent
                assistant = AutoGenV4AssistantAgent(
                    name=agent_name,
                    system_message=backstory + ". Must reply with 'TERMINATE' when the task is complete.",
                    model_client=model_client,
                    tools=agent_tools,
                    reflect_on_tool_use=True
                )
                
                agents.append(assistant)
                
                # Collect tasks from agent config
                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = self._format_template(task_details['description'], topic=topic)
                    combined_tasks.append(description_filled)
            
            # Create group chat for multi-agent interaction
            group_chat = RoundRobinGroupChat(participants=agents)
            
            # Run the combined tasks
            result_messages = []
            for task in combined_tasks:
                stream = group_chat.run_stream(task=task)
                async for message in stream:
                    result_messages.append(str(message.content) if hasattr(message, 'content') else str(message))
                    if "TERMINATE" in str(message).upper():
                        break
            
            return "\n".join(result_messages)
        
        # Run async execution
        try:
            result = asyncio.run(run_autogen_v4_async())
            return f"### AutoGen v0.4 Output ###\n{result}"
        except Exception as e:
            logger.error(f"AutoGen v0.4 execution failed: {e}")
            return f"### AutoGen v0.4 Output ###\nExecution failed: {e}"


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
            
        Returns:
            Execution result as string
        """
        # Import AG2 components (installs under 'autogen' namespace)
        import os
        import re as _re
        from autogen import (
            AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager, LLMConfig
        )
        
        logger.info("Starting AG2 execution...")
        
        model_config = llm_config[0] if llm_config else {}
        
        # Allow YAML top-level llm block to override config_list values
        yaml_llm = config.get("llm", {}) or {}
        # Also check first role's llm block as a fallback
        first_role_llm = {}
        for role_details in config.get("roles", {}).values():
            first_role_llm = role_details.get("llm", {}) or {}
            break
        
        # Priority: YAML top-level llm > first role llm > config_list > env vars
        def _resolve(key, env_var=None, default=None):
            return (yaml_llm.get(key) or first_role_llm.get(key)
                    or model_config.get(key)
                    or (os.environ.get(env_var) if env_var else None)
                    or default)
        
        api_type = _resolve("api_type", default="openai").lower()
        model_name = _resolve("model", default="gpt-4o-mini")
        api_key = _resolve("api_key", env_var="OPENAI_API_KEY")
        base_url = _resolve("base_url", default="https://api.openai.com/v1")
        
        # Build LLMConfig 
        if api_type == "bedrock":
            llm_config_entry = {"api_type": "bedrock", "model": model_name}
        else:
            llm_config_entry = {
                "model": model_name,
                "api_key": api_key,
                "base_url": base_url
            }
        
        # Use LLMConfig context manager for AG2
        with LLMConfig(config_list=[llm_config_entry]):
            # Create user proxy
            user_proxy = UserProxyAgent(
                name="User_Proxy",
                code_execution_config={"work_dir": "coding", "use_docker": False},
                human_input_mode="NEVER",
                is_termination_msg=lambda msg: "TERMINATE" in str(msg.get("content", "")).upper()
            )
            
            agents = [user_proxy]
            combined_tasks = []
            
            # Create agents from config
            for role, details in config.get('roles', {}).items():
                agent_name = self._format_template(details.get('role', role), topic=topic)
                backstory = self._format_template(details.get('backstory', ''), topic=topic)
                
                # Register tools if available
                agent_tools = []
                if tools_dict:
                    for tool_name in details.get('tools', []):
                        if tool_name in tools_dict:
                            tool_instance = tools_dict[tool_name]
                            # Register tool with user_proxy for AG2
                            if hasattr(tool_instance, 'run') and callable(tool_instance.run):
                                user_proxy.register_for_llm(name=tool_name, description=getattr(tool_instance, 'description', tool_name))(tool_instance.run)
                                user_proxy.register_for_execution(name=tool_name)(tool_instance.run)
                
                # Create AG2 AssistantAgent
                assistant = AssistantAgent(
                    name=agent_name,
                    system_message=backstory + ". Must reply with 'TERMINATE' when the task is complete."
                )
                
                agents.append(assistant)
                
                # Collect tasks from agent config
                for task_name, task_details in details.get('tasks', {}).items():
                    description_filled = self._format_template(task_details['description'], topic=topic)
                    combined_tasks.append(description_filled)
            
            # Create group chat
            group_chat = GroupChat(agents=agents, messages=[], max_round=50)
            manager = GroupChatManager(groupchat=group_chat)
            
            # Run tasks
            results = []
            for task in combined_tasks:
                chat_result = user_proxy.initiate_chat(
                    manager,
                    message=task
                )
                if hasattr(chat_result, 'summary'):
                    results.append(chat_result.summary)
                else:
                    results.append(str(chat_result))
            
            return f"### AG2 Output ###\n" + "\n\n".join(results)