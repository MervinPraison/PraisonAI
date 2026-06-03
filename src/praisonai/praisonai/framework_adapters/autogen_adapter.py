"""AutoGen framework adapter implementing the full protocol."""

import os
import logging
from typing import Dict, List, Any, Optional, Callable
from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class AutoGenAdapter(BaseFrameworkAdapter):
    """AutoGen framework adapter for v0.2.x."""
    
    name = "autogen"
    
    def is_available(self) -> bool:
        from .._framework_availability import is_available
        return is_available("autogen")
    
    def resolve(self) -> "BaseFrameworkAdapter":
        """Pick the concrete AutoGen adapter variant based on environment and availability."""
        autogen_version = os.environ.get("AUTOGEN_VERSION", "auto").lower()
        
        # Import the specific adapters
        v4_adapter = AutoGenV4Adapter()
        v2_adapter = self  # Current instance is v0.2
        
        if autogen_version == "v0.4" and v4_adapter.is_available():
            logger.info("AutoGen version resolution: Using v0.4 (explicitly requested)")
            return v4_adapter
        elif autogen_version == "v0.2" and v2_adapter.is_available():
            logger.info("AutoGen version resolution: Using v0.2 (explicitly requested)")
            return v2_adapter
        elif autogen_version == "auto":
            # Auto-detect: prefer v0.4 if available, fallback to v0.2
            if v4_adapter.is_available():
                logger.info("AutoGen version resolution: Using v0.4 (auto-detected)")
                return v4_adapter
            else:
                logger.info("AutoGen version resolution: Using v0.2 (auto-detected fallback)")
                return v2_adapter
        else:
            # Invalid version or neither available, try both
            if v4_adapter.is_available() and not v2_adapter.is_available():
                logger.info("AutoGen version resolution: Using v0.4 (only available version)")
                return v4_adapter
            else:
                logger.info("AutoGen version resolution: Using v0.2 (default fallback)")
                return v2_adapter
    
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
        """Run AutoGen v0.2 agents with the given configuration."""
        try:
            import autogen
        except ImportError as e:
            raise ImportError("autogen is not installed. Please install it with 'pip install pyautogen'") from e
            
        # Implementation would go here - keeping it simple for the merge resolution
        # The old framework methods were removed from agents_generator.py per this PR
        agents = {}
        tasks = []
        
        # Basic implementation
        user_proxy = autogen.UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: "TERMINATE" in (x.get("content") or ""),
            code_execution_config={"work_dir": "coding", "use_docker": False}
        )
        
        llm_config_dict = {"config_list": llm_config}
        
        for role, details in config.get('roles', {}).items():
            agent_name = details.get('role', role)
            
            agent = autogen.AssistantAgent(
                name=agent_name,
                llm_config=llm_config_dict,
                system_message=details.get('backstory', '') + " Reply TERMINATE when done."
            )
            
            agents[role] = agent
            
            # Add tasks
            for task_name, task_details in details.get('tasks', {}).items():
                description = task_details.get('description', '')
                chat_task = {
                    "recipient": agent,
                    "message": description,
                    "summary_method": "last_msg"
                }
                tasks.append(chat_task)
        
        if not tasks:
            return "No tasks defined"
            
        response = user_proxy.initiate_chats(tasks)
        result = "### Output ###\n" + (response[-1].summary if hasattr(response[-1], 'summary') else str(response))
        
        return result


class AutoGenV4Adapter(BaseFrameworkAdapter):
    """AutoGen v0.4 framework adapter with full implementation."""
    
    name = "autogen_v4"
    
    def is_available(self) -> bool:
        try:
            import autogen_core
            import autogen_agentchat
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
        """Run AutoGen v0.4 agents with full implementation."""
        if not self.is_available():
            raise ImportError("AutoGen v0.4 is not available")
            
        try:
            from autogen_agentchat.agents import AssistantAgent
            from autogen_agentchat.teams import RoundRobinGroupChat
            from autogen_ext.models import OpenAIChatCompletionClient
            from ._async_bridge import run_sync
        except ImportError as e:
            raise ImportError("Required AutoGen v0.4 components not available") from e
        
        async def run_autogen_v4_async():
            model_client = None
            try:
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
                    agent_name = details.get('role', role)
                    system_message = details.get('backstory', f'You are a {agent_name}')
                    
                    # Convert tools for v0.4
                    agent_tools = []
                    for tool_name in details.get('tools', []):
                        if tools_dict and tool_name in tools_dict:
                            tool_instance = tools_dict[tool_name]
                            if callable(tool_instance):
                                agent_tools.append(tool_instance)
                            elif hasattr(tool_instance, 'run') and callable(tool_instance.run):
                                agent_tools.append(tool_instance.run)
                    
                    agent = AssistantAgent(
                        name=agent_name,
                        model_client=model_client,
                        tools=agent_tools,
                        system_message=system_message
                    )
                    agents.append(agent)
                    
                    # Collect tasks
                    for task_name, task_details in details.get('tasks', {}).items():
                        combined_tasks.append(task_details.get('description', ''))
                
                if not agents:
                    return "No agents created"
                
                if not combined_tasks:
                    combined_tasks = [topic or "Complete the assigned task"]
                
                # Create team and run
                team = RoundRobinGroupChat(participants=agents)
                stream = team.run_stream(task=combined_tasks[0])
                
                result_messages = []
                async for message in stream:
                    result_messages.append(str(message))
                
                return "### AutoGen v0.4 Output ###\n" + "\n".join(result_messages)
                
            finally:
                # Close the model client
                if model_client is not None:
                    await model_client.close()
        
        return run_sync(run_autogen_v4_async())


class AG2Adapter(BaseFrameworkAdapter):
    """AG2 framework adapter with full implementation."""
    
    name = "ag2"
    
    def is_available(self) -> bool:
        try:
            import autogen as ag2
            # Check if this is AG2 (has specific attributes)
            return hasattr(ag2, '__version__') and 'ag2' in ag2.__file__.lower()
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
        """Run AG2 agents with full implementation."""
        if not self.is_available():
            raise ImportError("AG2 is not available")
            
        try:
            import autogen as ag2
        except ImportError as e:
            raise ImportError("ag2 is not installed") from e
        
        def _resolve(key: str, env_var: str = None):
            """Resolve configuration value with environment fallback."""
            if llm_config and llm_config[0].get(key):
                return llm_config[0][key]
            if env_var and os.environ.get(env_var):
                return os.environ[env_var]
            return None
        
        # Configuration resolution
        api_key = _resolve("api_key", "OPENAI_API_KEY") or "dummy-key"
        base_url = llm_config[0].get('base_url') if llm_config else "https://api.openai.com/v1"
        model_name = _resolve("model") or "gpt-4o-mini"
        
        llm_config_dict = {
            "config_list": [{
                "model": model_name,
                "api_key": api_key,
                "base_url": base_url
            }]
        }
        
        # Create user proxy
        user_proxy = ag2.UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: "TERMINATE" in (x.get("content") or ""),
            code_execution_config={"work_dir": "coding", "use_docker": False}
        )
        
        agents = {}
        tasks = []
        
        for role, details in config.get('roles', {}).items():
            agent_name = details.get('role', role)
            system_message = details.get('backstory', f'You are a {agent_name}') + " Reply TERMINATE when done."
            
            assistant = ag2.AssistantAgent(
                name=agent_name,
                llm_config=llm_config_dict,
                system_message=system_message
            )
            
            # Register tools
            for tool_name in details.get('tools', []):
                if tools_dict and tool_name in tools_dict:
                    tool = tools_dict[tool_name]
                    
                    # Get the actual callable function
                    if hasattr(tool, 'run') and callable(tool.run):
                        func = tool.run
                    elif callable(tool):
                        func = tool
                    else:
                        logger.warning(f"Tool {tool_name} is not callable")
                        continue
                    
                    # Register with AG2
                    wrapped = func
                    if hasattr(wrapped, "__name__"):
                        try:
                            wrapped.__name__ = tool_name
                        except AttributeError:
                            pass
                    assistant.register_for_llm(description=f"Tool: {tool_name}")(wrapped)
                    user_proxy.register_for_execution()(wrapped)
            
            agents[role] = assistant
            
            # Create tasks
            for task_name, task_details in details.get('tasks', {}).items():
                description = task_details.get('description', '')
                chat_task = {
                    "recipient": assistant,
                    "message": description,
                    "summary_method": "last_msg"
                }
                tasks.append(chat_task)
        
        if not tasks:
            return "No tasks defined"
        
        # Execute tasks
        response = user_proxy.initiate_chats(tasks)
        result = "### AG2 Output ###\n" + (response[-1].summary if hasattr(response[-1], 'summary') else str(response))
        
        return result