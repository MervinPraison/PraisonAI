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
            tools_dict: Available tools dictionary
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
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
            config: AutoGen v0.4 configuration with agents
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Available tools dictionary
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        # Availability already validated at CLI entry
        
        logger.info("Starting AutoGen v0.4 execution...")
        import asyncio
        import os
        import re
        
        async def run_autogen_v4_async():
            from autogen_agentchat.agents import AssistantAgent
            from autogen_ext.models.openai import OpenAIChatCompletionClient
            from autogen_agentchat.teams import RoundRobinGroupChat
            from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
            
            # Create model client for v0.4
            model_config = llm_config[0] if llm_config else {}
            model_client = OpenAIChatCompletionClient(
                model=model_config.get('model', 'gpt-4o-mini'),
                api_key=model_config.get('api_key', os.environ.get("OPENAI_API_KEY")),
                base_url=model_config.get('base_url', "https://api.openai.com/v1")
            )
            
            agents = []
            combined_tasks = []
            
            try:
                # Create agents from config
                for role, details in config['roles'].items():
                    # For AutoGen v0.4, ensure agent name is a valid Python identifier
                    agent_name = self._format_template(details['role'], topic=topic)
                    agent_name = self._sanitize_agent_name_for_autogen_v4(agent_name)
                    backstory = self._format_template(details['backstory'], topic=topic)
                    
                    # Convert tools for v0.4 - simplified tool passing
                    agent_tools = []
                    for tool_name in details.get('tools', []):
                        if tools_dict and tool_name in tools_dict:
                            tool_instance = tools_dict[tool_name]
                            # For v0.4, we can pass the tool's run method directly if it's callable
                            if hasattr(tool_instance, 'run') and callable(tool_instance.run):
                                agent_tools.append(tool_instance.run)
                    
                    # Create v0.4 AssistantAgent
                    assistant = AssistantAgent(
                        name=agent_name,
                        system_message=backstory + ". Must reply with 'TERMINATE' when the task is complete.",
                        model_client=model_client,
                        tools=agent_tools,
                        reflect_on_tool_use=True
                    )
                    
                    agents.append(assistant)
                    
                    # Collect all task descriptions for sequential execution
                    for task_name, task_details in details.get('tasks', {}).items():
                        description_filled = self._format_template(task_details['description'], topic=topic)
                        combined_tasks.append(description_filled)
                
                if not agents:
                    return "No agents created from configuration"
                
                # Create termination conditions
                text_termination = TextMentionTermination("TERMINATE")
                max_messages_termination = MaxMessageTermination(max_messages=20)
                termination_condition = text_termination | max_messages_termination
                
                # Create RoundRobinGroupChat for parallel/sequential execution
                group_chat = RoundRobinGroupChat(
                    agents,
                    termination_condition=termination_condition,
                    max_turns=len(agents) * 3  # Allow multiple rounds
                )
                
                # Combine all tasks into a single task description
                task_description = f"Topic: {topic}\n\nTasks to complete:\n" + "\n".join(
                    f"{i+1}. {task}" for i, task in enumerate(combined_tasks)
                )
                
                # Run the group chat
                result = await group_chat.run(task=task_description)
                
                # Extract the final message content
                if result.messages:
                    final_message = result.messages[-1]
                    if hasattr(final_message, 'content'):
                        return f"### AutoGen v0.4 Output ###\n{final_message.content}"
                    else:
                        return f"### AutoGen v0.4 Output ###\n{str(final_message)}"
                else:
                    return "### AutoGen v0.4 Output ###\nNo messages generated"
                    
            except Exception as e:
                logger.error(f"Error in AutoGen v0.4 execution: {str(e)}")
                return f"### AutoGen v0.4 Error ###\n{str(e)}"
            
            finally:
                # Close the model client
                await model_client.close()
        
        # Run the async function using safe bridge
        try:
            from .._async_bridge import run_sync
            return run_sync(run_autogen_v4_async())
        except ImportError:
            # Fallback if _async_bridge is not available
            return asyncio.run(run_autogen_v4_async())
        except Exception as e:
            logger.error(f"Error running AutoGen v0.4: {str(e)}")
            return f"### AutoGen v0.4 Error ###\n{str(e)}"
    
    def _sanitize_agent_name_for_autogen_v4(self, name):
        """
        Sanitize agent name to be a valid Python identifier for AutoGen v0.4.
        
        Args:
            name (str): The original agent name
            
        Returns:
            str: A valid Python identifier
        """
        import re
        import keyword
        
        # Convert to string and replace invalid characters with underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
        
        # Collapse only very excessive underscores (5 or more) to reduce extreme cases
        sanitized = re.sub(r'_{5,}', '_', sanitized)
        
        # Remove trailing underscores only if not part of a dunder pattern and only if singular
        if sanitized.endswith('_') and not sanitized.endswith('__') and sanitized != '_':
            sanitized = sanitized.rstrip('_')
        
        # Ensure it doesn't start with a digit
        if sanitized and sanitized[0].isdigit():
            sanitized = 'agent_' + sanitized
        
        # If it's empty or just underscores, use a default
        if not sanitized or sanitized == '_':
            sanitized = 'agent'
        
        # Check if it's a Python keyword and append underscore if so
        if keyword.iskeyword(sanitized):
            sanitized += '_'
        
        return sanitized


class AG2Adapter(BaseFrameworkAdapter):
    """Adapter for AG2 framework."""
    
    name = "ag2"
    install_hint = 'pip install "praisonai[ag2]"'
    requires_tools_extra = False
    
    def is_available(self) -> bool:
        """Check if AG2 is available for import."""
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
            tools_dict: Available tools dictionary
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        # Availability already validated at CLI entry
            
        logger.info("Starting AG2 execution...")
        import re
        import os
        from autogen import (
            AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager, LLMConfig
        )

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
        # Use resolver for consistent env-var precedence as fallback
        try:
            from praisonai.llm.env import resolve_llm_endpoint
            ep = resolve_llm_endpoint()
            base_url = (model_config.get("base_url")
                        or yaml_llm.get("base_url")
                        or ep.base_url)
        except ImportError:
            base_url = model_config.get("base_url") or yaml_llm.get("base_url")

        # Build LLMConfig — Bedrock needs no api_key
        if api_type == "bedrock":
            llm_config_entry = {"api_type": "bedrock", "model": model_name}
        else:
            llm_config_entry = {"model": model_name}
            if api_key:
                llm_config_entry["api_key"] = api_key
            if base_url and base_url not in ("https://api.openai.com/v1", "https://api.openai.com/v1/"):
                llm_config_entry["base_url"] = base_url
        llm_config = LLMConfig(llm_config_entry)

        user_proxy = UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: "TERMINATE" in (x.get("content") or ""),
            code_execution_config=False,
        )

        # Create one AssistantAgent per role
        ag2_agent_entries = []
        for role, details in config["roles"].items():
            agent_name = self._format_template(details.get("role", role), topic=topic)
            backstory = self._format_template(details.get("backstory", ""), topic=topic)
            agent_name_safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", agent_name)
            assistant = AssistantAgent(
                name=agent_name_safe,
                system_message=backstory + "\nWhen the task is done, reply 'TERMINATE'.",
                llm_config=llm_config,
            )
            ag2_agent_entries.append((role, details, assistant))

        # Register tools via AG2 decorator pattern
        for role, details, assistant in ag2_agent_entries:
            for tool_name in details.get("tools", []):
                tool = tools_dict.get(tool_name) if tools_dict else None
                if tool is None:
                    continue
                func = tool if callable(tool) else getattr(tool, "run", None)
                if func is None:
                    continue

                def make_tool_fn(f, name):
                    def tool_fn(**kwargs):
                        return f(**kwargs) if callable(f) else str(f)
                    tool_fn.__name__ = name
                    return tool_fn

                wrapped = make_tool_fn(func, tool_name)
                assistant.register_for_llm(description=f"Tool: {tool_name}")(wrapped)
                user_proxy.register_for_execution()(wrapped)

        all_assistants = [a for _, _, a in ag2_agent_entries]
        if not all_assistants:
            return "### AG2 Output ###\nNo agents created from configuration."

        # Build initial message from all task descriptions
        task_lines = []
        for role, details, _ in ag2_agent_entries:
            for task_name, task_details in details.get("tasks", {}).items():
                desc = self._format_template(task_details.get("description", ""), topic=topic)
                if desc:
                    task_lines.append(desc)
        initial_message = "\n".join(task_lines) if task_lines else topic

        groupchat = GroupChat(
            agents=[user_proxy] + all_assistants,
            messages=[],
            max_round=12,
        )
        manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

        try:
            chat_result = user_proxy.initiate_chat(manager, message=initial_message)
        except Exception as e:
            return f"### AG2 Error ###\n{str(e)}"

        # Prefer ChatResult.summary if available, otherwise scan messages
        result_content = ""
        summary = getattr(chat_result, "summary", None)
        if summary and isinstance(summary, str) and summary.strip():
            result_content = re.sub(r'[\s\.\,]*TERMINATE[\s\.\,]*$', '', summary, flags=re.IGNORECASE).strip().rstrip('.')

        if not result_content:
            for msg in reversed(groupchat.messages):
                if msg.get("name") == "User":
                    continue
                content = (msg.get("content") or "").strip()
                if content:
                    result_content = re.sub(r'[\s\.\,]*TERMINATE[\s\.\,]*$', '', content, flags=re.IGNORECASE).strip().rstrip('.')
                    if result_content:
                        break

        if not result_content:
            result_content = "Task completed."

        return f"### AG2 Output ###\n{result_content}"
