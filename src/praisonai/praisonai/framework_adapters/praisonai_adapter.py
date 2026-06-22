"""
PraisonAI native framework adapter implementation.

This adapter uses PraisonAI's native `praisonaiagents` library directly,
without going through external frameworks like CrewAI, Autogen, or Swarm.
It has full control over the agents and tasks, allowing for more flexibility
and direct integration with PraisonAI's features.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import FrameworkAdapter

logger = logging.getLogger(__name__)


class PraisonAIAdapter(FrameworkAdapter):
    """
    Adapter for running PraisonAI agents natively using praisonaiagents.
    
    This is the primary execution path for agent workflows, supporting:
    - Direct agent-task configuration
    - Per-agent model selection
    - Per-agent runtime selection (autogen, swarm, etc.)
    - Agent-centric tools (ACP/LSP)
    - Memory and planning features
    """
    
    @property
    def name(self) -> str:
        """Return adapter name."""
        return "praisonai"
    
    @property
    def supported_runtimes(self) -> List[str]:
        """List of supported agent runtimes this adapter can use."""
        return ["praisonai", "autogen", "swarm", "crewai", "langchain"]
    
    def is_available(self) -> bool:
        """Check if PraisonAI agents is available for import."""
        from .._framework_availability import is_available
        return is_available("praisonaiagents")
    
    def _format_template(self, text: str, **kwargs) -> str:
        """Format a template string with provided values."""
        if not text:
            return ""
        
        import re
        formatted = text
        for key, value in kwargs.items():
            # Replace {key} with value
            pattern = r'\{' + key + r'\}'
            formatted = re.sub(pattern, str(value), formatted)
        return formatted
    
    def _resolve_agent_model(self, details: Dict, default_model: str) -> str:
        """
        Resolve the LLM model for a specific agent.
        
        Priority:
        1. Agent-specific llm/model field (string or dict with 'model' key)
        2. Default model from llm_config
        3. Fallback to gpt-4o-mini
        """
        # Check for agent-specific model (could be 'llm' or 'model' key)
        llm_spec = details.get('llm') or details.get('model')
        if isinstance(llm_spec, str) and llm_spec.strip():
            return llm_spec.strip()
        if isinstance(llm_spec, dict) and llm_spec.get('model'):
            return llm_spec['model']
        
        # Use default or fallback
        return default_model or "gpt-4o-mini"
    
    def _resolve_agent_runtime(self, details: Dict, config: Dict) -> Optional[str]:
        """
        Resolve the runtime backend for a specific agent.
        
        Priority:
        1. Agent-specific runtime field
        2. Agent-specific backend field (legacy)
        3. Model-scoped runtime from models section
        4. Provider-scoped runtime from providers section
        5. Global config.runtime
        6. Global config.backend (legacy)
        7. CLI backend override (legacy with warning)
        8. None (uses default)
        """
        # 1. Check agent-specific runtime
        if 'runtime' in details:
            return details['runtime']
        
        # 2. Check agent-specific backend (legacy)
        if 'backend' in details:
            return details['backend']
        
        # 3. Check model-scoped runtime
        agent_model = self._resolve_agent_model(details, "")
        if agent_model and 'models' in config:
            models_config = config['models']
            if isinstance(models_config, dict) and agent_model in models_config:
                model_config = models_config[agent_model]
                if isinstance(model_config, dict) and 'runtime' in model_config:
                    return model_config['runtime']
        
        # 4. Check provider-scoped runtime
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
        
        # 5. Check global config
        global_config = config.get('config', {})
        if 'runtime' in global_config:
            return global_config['runtime']
        
        # 6. Check global backend (legacy)
        if 'backend' in global_config:
            return global_config['backend']
        
        # 7. Check CLI backend override (legacy with warning)
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
    
    def _resolve_agent_approval(self, details: Dict[str, Any], config: Dict[str, Any]):
        """
        Resolve approval configuration for an agent.
        
        Precedence:
        1. Agent-level approval config
        2. Global permissions config from YAML
        3. None (fallback to environment or defaults)
        """
        from praisonaiagents.approval.protocols import ApprovalConfig
        from praisonai.cli.approval_backend import InteractiveCLIApprovalBackend
        
        # Check for agent-level approval
        if 'approval' in details:
            approval_config = details['approval']
            if isinstance(approval_config, dict):
                # Check if permissions are specified inline
                permissions = approval_config.get('permissions')
                if permissions:
                    # Create backend with permissions
                    backend = InteractiveCLIApprovalBackend(
                        permissions_config=permissions
                    )
                    return ApprovalConfig(
                        backend=backend,
                        all_tools=approval_config.get('all_tools', False),
                        timeout=approval_config.get('timeout', 0),
                        permissions=permissions,
                    )
                # Otherwise return the approval config as-is
                return ApprovalConfig(**approval_config)
            return approval_config
        
        # Check for global permissions in config
        if 'permissions' in config:
            permissions = config['permissions']
            if permissions:
                # Create backend with global permissions
                backend = InteractiveCLIApprovalBackend(
                    permissions_config=permissions
                )
                return ApprovalConfig(
                    backend=backend,
                    permissions=permissions,
                )
        
        return None
    
    async def _astart_interactive_runtime(self, config: Dict[str, Any]):
        """Start InteractiveRuntime if ACP/LSP is enabled."""
        import os
        global_config = config.get('config', {})
        acp_enabled = global_config.get('acp', False)
        lsp_enabled = global_config.get('lsp', False)
        
        if not (acp_enabled or lsp_enabled):
            return None
            
        try:
            from praisonai.cli.features.interactive_runtime import InteractiveRuntime, RuntimeConfig
            
            runtime_config = RuntimeConfig(
                workspace=os.getcwd(),
                acp_enabled=acp_enabled,
                lsp_enabled=lsp_enabled,
                approval_mode=os.environ.get("PRAISONAI_APPROVAL_MODE", "prompt")
            )
            rt = InteractiveRuntime(runtime_config)
            logger.info(f"Starting InteractiveRuntime (ACP: {acp_enabled}, LSP: {lsp_enabled})")
            await rt.start()
            return rt
        except ImportError as e:
            logger.warning(f"InteractiveRuntime not available: {e}")
            return None
        except (RuntimeError, OSError, ConnectionError) as e:
            logger.warning(f"InteractiveRuntime startup failed: {e}")
            return None

    def _maybe_inject_centric_tools(self, interactive_runtime, tools_dict):
        """Inject agent-centric tools if runtime is available."""
        if interactive_runtime is None:
            return tools_dict or {}
            
        try:
            from praisonai.cli.features.agent_tools import create_agent_centric_tools
            centric_tools = create_agent_centric_tools(interactive_runtime)
            logger.info(f"Loaded {len(centric_tools)} InteractiveRuntime tools")
            return {**(tools_dict or {}), **centric_tools}
        except Exception as e:
            logger.warning(f"Failed to inject agent-centric tools: {e}")
            return tools_dict or {}

    def _pick_model(self, llm_config: List[Dict]) -> str:
        """Extract model name from llm_config."""
        if llm_config and llm_config[0].get('model'):
            return llm_config[0]['model']
        return "gpt-4o-mini"

    def _build_agents_and_tasks(self, config, topic, tools_dict, agent_callback, task_callback, model_name):
        """Build agents and tasks from configuration."""
        from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask
        
        agents = {}
        tasks = []
        
        # Process agents from config
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
            
            # Resolve approval configuration
            agent_approval = self._resolve_agent_approval(details, config)
            
            # Create basic agent (pass both tools and toolsets)
            agent_kwargs = {
                'name': role_filled,
                'role': role_filled,
                'goal': goal_filled,
                'backstory': backstory_filled,
                'instructions': details.get('instructions'),
                'llm': agent_model,
                'allow_delegation': details.get('allow_delegation', False),
                'tools': agent_tool_list,
                'toolsets': agent_toolsets,
                'runtime': agent_runtime,
            }
            
            # Add approval config if present
            if agent_approval:
                agent_kwargs['approval'] = agent_approval
            
            agent = PraisonAgent(**agent_kwargs)
            
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
                for _task_name, task_details in agent_tasks.items():
                    description_filled = self._format_template(
                        task_details.get('description', ''), topic=topic
                    )
                    expected_output_filled = self._format_template(
                        task_details.get('expected_output', 'Task completed successfully.'), topic=topic
                    )
                    
                    task = PraisonTask(
                        description=description_filled,
                        expected_output=expected_output_filled,
                        agent=agent,
                    )
                    
                    if task_callback:
                        task.callback = task_callback
                    
                    tasks.append(task)
        
        return agents, tasks

    def _build_team(self, config, agents, tasks, model_name):
        """Build AgentTeam from agents and tasks."""
        from praisonaiagents import AgentTeam
        
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
        
        return team

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
        # Single source of truth: sync goes through the async bridge.
        from praisonai._async_bridge import run_sync
        return run_sync(self.arun(
            config, llm_config, topic,
            tools_dict=tools_dict,
            agent_callback=agent_callback,
            task_callback=task_callback,
            cli_config=cli_config,
        ))

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
        import os
        
        logger.info("Starting PraisonAI async execution...")
        
        # Get model from llm_config
        model_name = self._pick_model(llm_config)
        
        # Initialize InteractiveRuntime for ACP/LSP if enabled
        interactive_runtime = await self._astart_interactive_runtime(config)
        
        try:
            # Inject agent-centric tools if runtime is available
            tools_dict = self._maybe_inject_centric_tools(interactive_runtime, tools_dict)

            # Build agents and tasks from config
            agents, tasks = self._build_agents_and_tasks(
                config, topic, tools_dict, agent_callback, task_callback, model_name
            )
            
            # Create the team
            team = self._build_team(config, agents, tasks, model_name)
            
            # Use native async path
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
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration for PraisonAI.
        
        Args:
            config: Configuration dictionary to validate
        
        Returns:
            True if configuration is valid
        
        Raises:
            ValueError: If configuration is invalid with details
        """
        if not config:
            raise ValueError("Configuration is empty")
        
        roles = config.get('roles', {})
        if not roles:
            raise ValueError("No agents defined in 'roles' section")
        
        return True