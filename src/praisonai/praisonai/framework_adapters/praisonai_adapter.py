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
        from .._framework_availability import is_available
        return is_available("praisonaiagents")
    
    def _resolve_agent_model(self, details: Dict[str, Any], default_model: str) -> str:
        """Resolve the LLM model for a specific agent, supporting per-agent configuration."""
        llm_spec = details.get('llm')
        
        # Handle string format: llm: "gpt-4o-mini"
        if isinstance(llm_spec, str) and llm_spec.strip():
            return llm_spec.strip()
        
        # Handle dict format: llm: {"model": "groq/llama3-70b-8192"}
        if isinstance(llm_spec, dict) and llm_spec.get('model'):
            return llm_spec['model']
        
        # Fall back to global default
        return default_model
    
    def _resolve_agent_runtime(self, details: Dict[str, Any], config: Dict[str, Any]) -> Any:
        """Resolve runtime configuration for a specific agent.
        
        Resolution order:
        1. Agent-level runtime parameter
        2. Model-scoped runtime from models section
        3. Provider-scoped runtime from providers section
        4. Legacy cli_backend (with deprecation warning)
        5. None (use default LLM execution)
        
        Args:
            details: Agent configuration details
            config: Full YAML configuration
            
        Returns:
            Runtime configuration or None
        """
        # 1. Check agent-level runtime parameter
        if 'runtime' in details:
            return details['runtime']
        
        # 2. Check model-scoped runtime
        agent_model = self._resolve_agent_model(details, "")
        if agent_model and 'models' in config:
            models_config = config['models']
            if isinstance(models_config, dict) and agent_model in models_config:
                model_config = models_config[agent_model]
                if isinstance(model_config, dict) and 'runtime' in model_config:
                    return model_config['runtime']
        
        # 3. Check provider-scoped runtime
        if agent_model and 'providers' in config:
            # Extract provider from model name
            provider = None
            if '/' in agent_model:
                provider = agent_model.split('/')[0]
            elif 'claude' in agent_model.lower():
                provider = 'anthropic'
            elif 'gpt' in agent_model.lower():
                provider = 'openai'
            elif 'gemini' in agent_model.lower():
                provider = 'google'
            
            if provider:
                providers_config = config['providers']
                if isinstance(providers_config, dict) and provider in providers_config:
                    provider_config = providers_config[provider]
                    if isinstance(provider_config, dict) and 'runtime_default' in provider_config:
                        return provider_config['runtime_default']
        
        # 4. Check legacy cli_backend (with deprecation warning handled by Agent.__init__)
        if 'cli_backend' in details:
            import warnings
            warnings.warn(
                "Agent-level 'cli_backend' in YAML is deprecated. "
                "Use 'runtime' parameter or model-scoped runtime configuration instead.",
                DeprecationWarning,
                stacklevel=3
            )
            return details['cli_backend']
        
        return None
    
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
        # Availability already validated at CLI entry
        
        # Import PraisonAI components only when needed
        from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, AgentTeam
        from .._framework_availability import is_available
        import os
        
        logger.info("Starting PraisonAI execution...")
        
        agents = {}
        tasks = []
        
        # Get model from llm_config or environment
        model_name = "gpt-4o-mini"
        if llm_config and llm_config[0].get('model'):
            model_name = llm_config[0]['model']
        
        # Initialize InteractiveRuntime for ACP/LSP if enabled globally
        global_config = config.get('config', {})
        acp_enabled = global_config.get('acp', False)
        lsp_enabled = global_config.get('lsp', False)
        interactive_runtime = None
        
        if acp_enabled or lsp_enabled:
            try:
                from praisonai._async_bridge import run_sync
                from praisonai.cli.features.interactive_runtime import InteractiveRuntime, RuntimeConfig
                from praisonai.cli.features.agent_tools import create_agent_centric_tools
                
                # Use scoped configuration instead of process-global mutations
                runtime_config = RuntimeConfig(
                    workspace=os.getcwd(),
                    acp_enabled=acp_enabled,
                    lsp_enabled=lsp_enabled,
                    approval_mode=os.environ.get("PRAISONAI_APPROVAL_MODE", "prompt")
                )
                rt = InteractiveRuntime(runtime_config)
                logger.info(f"Starting InteractiveRuntime (ACP: {acp_enabled}, LSP: {lsp_enabled})")
                
                # Start the runtime on the shared background loop where it stays alive
                # and its asyncio primitives remain valid for the duration of this call
                run_sync(rt.start())
                interactive_runtime = rt  # only assign AFTER start() succeeds
                
            except ImportError as e:
                logger.warning(f"InteractiveRuntime not available: {e}")
                interactive_runtime = None
            except (RuntimeError, OSError, ConnectionError) as e:
                logger.warning(f"InteractiveRuntime startup failed: {e}")
                interactive_runtime = None
        try:
            # All work that can throw *after* start() lives here, including
            # create_agent_centric_tools, tools_dict.update, agent construction,
            # team.start(), etc.
            if interactive_runtime is not None:
                from praisonai.cli.features.agent_tools import create_agent_centric_tools
                centric_tools = create_agent_centric_tools(interactive_runtime)
                logger.info(f"Loaded {len(centric_tools)} InteractiveRuntime tools")
                tools_dict = {**(tools_dict or {}), **centric_tools}

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
                
                # Extract toolsets from YAML config
                agent_toolsets = details.get('toolsets', [])
                
                # Resolve per-agent LLM model
                agent_model = self._resolve_agent_model(details, model_name)
                
                # Resolve per-agent runtime configuration
                agent_runtime = self._resolve_agent_runtime(details, config)
                
                # Create basic agent (pass both tools and toolsets)
                agent = PraisonAgent(
                    name=role_filled,
                    role=role_filled,
                    goal=goal_filled,
                    backstory=backstory_filled,
                    instructions=details.get('instructions'),
                    llm=agent_model,
                    allow_delegation=details.get('allow_delegation', False),
                    tools=agent_tool_list,
                    toolsets=agent_toolsets,
                    runtime=agent_runtime,
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
                # Use specific manager_llm or fall back to global model
                manager_model = config.get('manager_llm') or model_name
                team = AgentTeam(
                    agents=list(agents.values()),
                    tasks=tasks,
                    process="hierarchical",
                    manager_llm=manager_model,
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
            
            # Close observability session
            from ..observability.hooks import finalize_observability
            finalize_observability(self.name, status="Success")
            
            logger.info("PraisonAI execution completed")
            return result
        finally:
            # Cleanup InteractiveRuntime if it was started
            if interactive_runtime is not None:
                try:
                    logger.info("Stopping InteractiveRuntime")
                    from praisonai._async_bridge import run_sync
                    run_sync(interactive_runtime.stop())
                except Exception as e:
                    logger.error(f"Error stopping InteractiveRuntime: {e}")
    
    async def arun(
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
        Run PraisonAI agents asynchronously using the native async path.
        
        This uses AgentTeam.astart() instead of thread offloading for true async execution.
        """
        # Import PraisonAI components only when needed
        from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, AgentTeam
        from .._framework_availability import is_available
        import os
        
        logger.info("Starting PraisonAI async execution...")
        
        agents = {}
        tasks = []
        
        # Get model from llm_config or environment
        model_name = "gpt-4o-mini"
        if llm_config and llm_config[0].get('model'):
            model_name = llm_config[0]['model']
        
        # Initialize InteractiveRuntime for ACP/LSP if enabled globally
        global_config = config.get('config', {})
        acp_enabled = global_config.get('acp', False)
        lsp_enabled = global_config.get('lsp', False)
        interactive_runtime = None
        
        if acp_enabled or lsp_enabled:
            try:
                from praisonai.cli.features.interactive_runtime import InteractiveRuntime, RuntimeConfig
                from praisonai.cli.features.agent_tools import create_agent_centric_tools
                
                # Use scoped configuration instead of process-global mutations
                runtime_config = RuntimeConfig(
                    workspace=os.getcwd(),
                    acp_enabled=acp_enabled,
                    lsp_enabled=lsp_enabled,
                    approval_mode=os.environ.get("PRAISONAI_APPROVAL_MODE", "prompt")
                )
                rt = InteractiveRuntime(runtime_config)
                logger.info(f"Starting InteractiveRuntime (ACP: {acp_enabled}, LSP: {lsp_enabled})")
                
                # Start the runtime asynchronously
                await rt.start()
                interactive_runtime = rt  # only assign AFTER start() succeeds
                
            except ImportError as e:
                logger.warning(f"InteractiveRuntime not available: {e}")
                interactive_runtime = None
            except (RuntimeError, OSError, ConnectionError) as e:
                logger.warning(f"InteractiveRuntime startup failed: {e}")
                interactive_runtime = None
        
        try:
            # All work that can throw *after* start() lives here
            if interactive_runtime is not None:
                from praisonai.cli.features.agent_tools import create_agent_centric_tools
                centric_tools = create_agent_centric_tools(interactive_runtime)
                logger.info(f"Loaded {len(centric_tools)} InteractiveRuntime tools")
                tools_dict = {**(tools_dict or {}), **centric_tools}

            # Create agents from roles - same logic as sync version
            for role, details in config.get('roles', {}).items():
                role_filled = self._format_template(details.get('role', role), topic=topic)
                goal_filled = self._format_template(details.get('goal', ''), topic=topic)
                backstory_filled = self._format_template(details.get('backstory', ''), topic=topic)
                
                # Resolve tools for this agent from tools_dict
                agent_tool_list = []
                if tools_dict:
                    agent_tools = details.get('tools', [])
                    agent_tool_list = [tools_dict[t] for t in agent_tools if t in tools_dict]
                
                # Extract toolsets from YAML config
                agent_toolsets = details.get('toolsets', [])
                
                # Resolve per-agent LLM model
                agent_model = self._resolve_agent_model(details, model_name)
                
                # Resolve per-agent runtime configuration
                agent_runtime = self._resolve_agent_runtime(details, config)
                
                # Create basic agent (pass both tools and toolsets)
                agent = PraisonAgent(
                    name=role_filled,
                    role=role_filled,
                    goal=goal_filled,
                    backstory=backstory_filled,
                    instructions=details.get('instructions'),
                    llm=agent_model,
                    allow_delegation=details.get('allow_delegation', False),
                    tools=agent_tool_list,
                    toolsets=agent_toolsets,
                    runtime=agent_runtime,
                )
                
                if agent_callback:
                    agent.step_callback = agent_callback
                    
                agents[role] = agent
                
                # Create tasks for the agent - same logic as sync version
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
            
            # Create and run the team asynchronously
            memory = config.get('memory', False)
            
            if config.get('process') == 'hierarchical':
                # Use specific manager_llm or fall back to global model
                manager_model = config.get('manager_llm') or model_name
                team = AgentTeam(
                    agents=list(agents.values()),
                    tasks=tasks,
                    process="hierarchical",
                    manager_llm=manager_model,
                    memory=memory
                )
            else:
                team = AgentTeam(
                    agents=list(agents.values()),
                    tasks=tasks,
                    memory=memory
                )
            
            # Use native async path instead of team.start()
            response = await team.astart()
            result = f"### PraisonAI Output ###\n{response}" if response else "### PraisonAI Output ###\nTask completed."
            
            # Close observability session
            from ..observability.hooks import finalize_observability
            finalize_observability(self.name, status="Success")
            
            logger.info("PraisonAI async execution completed")
            return result
        finally:
            # Cleanup InteractiveRuntime if it was started
            if interactive_runtime is not None:
                try:
                    logger.info("Stopping InteractiveRuntime")
                    await interactive_runtime.stop()
                except Exception as e:
                    logger.error(f"Error stopping InteractiveRuntime: {e}")
    
