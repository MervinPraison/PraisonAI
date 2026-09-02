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

from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class PraisonAIAdapter(BaseFrameworkAdapter):
    """
    Adapter for running PraisonAI agents natively using praisonaiagents.
    
    This is the primary execution path for agent workflows, supporting:
    - Direct agent-task configuration
    - Per-agent model selection
    - Per-agent runtime selection (autogen, swarm, etc.)
    - Agent-centric tools (ACP/LSP)
    - Memory and planning features
    """

    # Native async path: arun() awaits team.astart() directly (no thread offload).
    SUPPORTS_ASYNC = True

    # Native PraisonAI is the only in-tree adapter that supports workflow YAML
    # execution and runtime features (cli_backend / runtime / models.*.runtime /
    # providers.*.runtime_default). Capability call sites read these flags
    # instead of hardcoding ``framework == "praisonai"``.
    SUPPORTS_WORKFLOW = True
    SUPPORTS_RUNTIME_FEATURES = True
    SUPPORTS_SESSION_CONTINUITY = True
    SUPPORTS_STREAM_BRIDGE = True

    @property
    def name(self) -> str:
        """Return adapter name."""
        return "praisonai"

    @property
    def install_hint(self) -> str:
        """Install hint for the native PraisonAI agents runtime."""
        return "pip install praisonaiagents"
    
    @property
    def supported_runtimes(self) -> List[str]:
        """List of supported agent runtimes this adapter can use."""
        return ["praisonai", "autogen", "swarm", "crewai", "langchain"]
    
    def is_available(self) -> bool:
        """Check if PraisonAI agents is available for import."""
        from .._framework_availability import is_available
        return is_available("praisonaiagents")
    
    def resolve(self, *, config=None):
        """
        Resolve the adapter variant based on the configuration.
        For PraisonAI adapter, we return self as there are no variants.
        
        Args:
            config: Configuration dictionary (optional)
        
        Returns:
            Self, as PraisonAI doesn't have variants
        """
        return self
    
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
        
        # 4. Check provider-scoped runtime. Provider inference is data-driven
        # and entry-point-extensible (core SDK), so any declared vendor —
        # groq, deepseek, mistral, cohere, ... — resolves, not just three.
        if agent_model and 'providers' in config:
            from praisonaiagents.llm.model_providers import resolve_provider

            provider = resolve_provider(agent_model)
            if provider:
                providers_config = config['providers']
                if isinstance(providers_config, dict) and provider in providers_config:
                    provider_config = providers_config[provider]
                    if isinstance(provider_config, dict) and 'runtime_default' in provider_config:
                        return provider_config['runtime_default']
            else:
                logger.debug(
                    "runtime resolution: no provider registered for model %r; "
                    "provider-scoped 'runtime_default' not consulted",
                    agent_model,
                )
        
        # 5. Check global config
        global_config = config.get('config', {})
        if 'runtime' in global_config:
            return global_config['runtime']
        
        # 6. Check global backend (legacy)
        if 'backend' in global_config:
            return global_config['backend']
        
        # 7. ``cli_backend`` is NOT a runtime id — it is resolved to a backend
        # instance and passed as the ``cli_backend`` kwarg instead (see the
        # agent construction path). Returning it here would send a CLI-backend
        # id into the runtime registry, which fails closed on unknown ids.
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
                # Otherwise map the wrapper approval dict onto the core
                # ApprovalConfig fields. The wrapper spec carries extra keys
                # (enabled, approve_all_tools, approve_level, guardrails,
                # default_policy, approve_tools) that the core dataclass does
                # not accept; passing them straight through raises TypeError.
                field_map = {'approve_all_tools': 'all_tools'}
                allowed = {'all_tools', 'timeout', 'permissions', 'permission_mode'}
                core_kwargs = {}
                for key, value in approval_config.items():
                    mapped = field_map.get(key, key)
                    if mapped in allowed:
                        core_kwargs[mapped] = value
                # ``backend`` on the wrapper spec is a string ("auto", "console",
                # ...); core ApprovalConfig.backend expects a backend object.
                # Resolve the ones we can, otherwise leave it to the registry.
                backend_name = approval_config.get('backend')
                resolved_backend = self._resolve_approval_backend(backend_name)
                if resolved_backend is not None:
                    core_kwargs['backend'] = resolved_backend
                return ApprovalConfig(**core_kwargs)
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

    @staticmethod
    def _resolve_approval_backend(backend_name):
        """Resolve a wrapper backend name (str) to a core backend instance.

        The wrapper approval spec stores ``backend`` as a string ("auto",
        "console", ...). Core ``ApprovalConfig.backend`` expects a backend
        object. We resolve the two names the CLI can emit and otherwise
        return ``None`` so the core falls back to its global registry.
        """
        if not isinstance(backend_name, str) or backend_name in ('none', 'auto'):
            # "auto" means auto-approve; that is expressed via all_tools /
            # AutoApproveBackend at the core level, but returning None keeps
            # this mapping minimal and lets the registry/all_tools drive it.
            if backend_name == 'auto':
                try:
                    from praisonaiagents.approval.backends import AutoApproveBackend
                    return AutoApproveBackend()
                except ImportError:
                    return None
            return None
        if backend_name == 'console':
            try:
                from praisonaiagents.approval.backends import ConsoleBackend
                return ConsoleBackend()
            except ImportError:
                return None
        return None

    @staticmethod
    def _normalize_autonomy(value):
        """Translate a wrapper autonomy value into one core Agent accepts.

        The wrapper YAML schema types ``autonomy`` as an int 0-10, but core
        ``Agent(autonomy=...)`` only understands ``bool``/``str`` preset/
        ``dict``/``AutonomyConfig``. Forwarding a raw int lands in core's
        disable branch, silently ignoring a configured level. We map the
        numeric level onto core's string presets and pass the other accepted
        forms straight through:

        - ``None`` / ``0``  -> ``None`` (autonomy off; nothing forwarded)
        - ``1``-``3``       -> ``"suggest"``
        - ``4``-``7``       -> ``"auto_edit"``
        - ``8``-``10``      -> ``"full_auto"``
        - ``bool``/``str``/``dict``/other -> passed through unchanged
        """
        if value is None:
            return None
        # bool is a subclass of int, so check it first and pass through.
        if isinstance(value, bool):
            return value or None
        if isinstance(value, int):
            if value <= 0:
                return None
            if value <= 3:
                return "suggest"
            if value <= 7:
                return "auto_edit"
            return "full_auto"
        # str preset, dict, or AutonomyConfig — core handles these directly.
        return value

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

    def _maybe_inject_centric_tools(self, interactive_runtime, tools_dict, *, wrap=None):
        """Inject agent-centric tools, honouring the caller's timeout wrap.

        The generator's ``_build_tools_dict`` wraps every YAML-declared tool with
        the per-run ``tool_timeout`` guard, but the ACP/LSP centric tools are
        added here — *after* that wrap — so without applying the same ``wrap``
        they would silently bypass the timeout (an LSP/ACP call could then hang
        forever). ``wrap`` is threaded through ``cli_config`` by the generator.
        """
        if interactive_runtime is None:
            return tools_dict or {}

        try:
            from praisonai.cli.features.agent_tools import create_agent_centric_tools
            centric_tools = create_agent_centric_tools(interactive_runtime)
            logger.info(f"Loaded {len(centric_tools)} InteractiveRuntime tools")
            if callable(wrap):
                centric_tools = {name: wrap(tool) for name, tool in centric_tools.items()}
            return {**(tools_dict or {}), **centric_tools}
        except Exception as e:
            logger.warning(f"Failed to inject agent-centric tools: {e}")
            return tools_dict or {}

    def _pick_model(self, llm_config: List[Dict]) -> str:
        """Extract model name from llm_config."""
        if llm_config and llm_config[0].get('model'):
            return llm_config[0]['model']
        return "gpt-4o-mini"

    def _build_agents_and_tasks(self, config, topic, tools_dict, agent_callback, task_callback, model_name, agent_tool_wrap_resolver=None):
        """Build agents and tasks from configuration."""
        from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask
        from ._config_builder import build_agent_specs

        agents = {}
        tasks = []

        # Single canonical YAML -> spec conversion (shared across adapters).
        # The optional per-agent tool_timeout wrap resolver (threaded from the
        # generator via cli_config) is applied inside build_agent_specs so each
        # agent's tools carry that agent's own budget instead of a shared one.
        specs = build_agent_specs(
            config, topic, tools_dict, self._format_template,
            agent_tool_wrap_resolver=agent_tool_wrap_resolver,
        )

        # Process agents from the normalized specs
        for spec in specs:
            role = spec.key
            details = spec.extras
            role_filled = spec.role
            goal_filled = spec.goal
            backstory_filled = spec.backstory

            # Resolve tools for this agent (already normalized by the builder)
            agent_tool_list = spec.tools
            
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

            # Agent-level ``cli_backend`` in YAML delegates this agent's turns
            # to an external coding CLI. Core Agent refuses raw string ids, so
            # resolve to an instance here in the wrapper layer.
            cli_backend_config = details.get('cli_backend')
            if cli_backend_config is not None:
                from praisonai.agents_generator import _resolve_yaml_cli_backend
                resolved_backend = _resolve_yaml_cli_backend(
                    cli_backend_config, logger
                )
                if resolved_backend is None:
                    # Fail closed: an explicitly requested backend that cannot
                    # be resolved must not silently fall back to the native
                    # LLM path (different tools, credentials, and billing).
                    raise ValueError(
                        f"Agent {role_filled!r} requests cli_backend="
                        f"{cli_backend_config!r} but it could not be "
                        "resolved. Install praisonai-code and use an id from "
                        "'praisonai backends', or remove the cli_backend field."
                    )
                agent_kwargs['cli_backend'] = resolved_backend
            
            # Forward agent-level fields that core Agent already accepts as-is
            # so CLI/YAML flags (--planning, --web, --autonomy, ...) are
            # honoured instead of being silently dropped. Each core param
            # accepts the wrapper's value directly (bool/str/dict/Config).
            # NOTE: `handoff` is handled after this loop by `_wire_handoffs`
            # once every agent object exists, so role->Agent resolution is a
            # plain dict lookup (see call at the end of this method).
            forwardable_fields = {
                'planning': 'planning',
                'reflection': 'reflection',
                'guardrails': 'guardrails',
                'web': 'web',
                'skills': 'skills',
            }
            for yaml_field, core_kwarg in forwardable_fields.items():
                if details.get(yaml_field) is not None:
                    agent_kwargs[core_kwarg] = details[yaml_field]

            # `autonomy` needs translation, not a raw forward: the wrapper YAML
            # schema types it as an int 0-10 (config/schema.py), but core Agent
            # only accepts bool/str/dict/AutonomyConfig — an int falls through to
            # the disable branch, silently ignoring a configured level. Map the
            # numeric level onto core's string presets (0 => off, so skip).
            autonomy_value = self._normalize_autonomy(details.get('autonomy'))
            if autonomy_value is not None:
                agent_kwargs['autonomy'] = autonomy_value

            # Add approval config if present
            if agent_approval:
                agent_kwargs['approval'] = agent_approval
            
            agent = PraisonAgent(**agent_kwargs)
            
            if agent_callback:
                agent.step_callback = agent_callback
                
            agents[role] = agent
            
            # Create tasks for the agent (already normalized by the builder)
            if not spec.tasks:
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
                for task_spec in spec.tasks:
                    task_kwargs = {
                        'description': task_spec.description,
                        'expected_output': task_spec.expected_output,
                        'agent': agent,
                    }
                    # Forward task-level tools so per-task YAML tools are honored
                    # consistently with the CrewAI adapter.
                    if task_spec.tools:
                        task_kwargs['tools'] = task_spec.tools
                    task = PraisonTask(**task_kwargs)
                    
                    if task_callback:
                        task.callback = task_callback
                    
                    tasks.append(task)

        # Resolve `handoff: {to: [role...], ...}` into core Agent.handoffs now
        # that every agent object exists (role name -> Agent is a dict lookup).
        self._wire_handoffs(agents, specs)

        return agents, tasks

    def _wire_handoffs(self, agents, specs):
        """Wire YAML/CLI ``handoff: {to: [role, ...], ...}`` into core
        ``Agent.handoffs``.

        The wrapper emits a dict (``{'to': [role names], 'timeout': ..., ...}``)
        while core ``Agent(handoffs=...)`` expects resolved ``Agent``/``Handoff``
        objects. This runs after every agent is built so each target role is a
        plain dict lookup. Optional execution knobs (timeout/max_depth/
        max_concurrent/detect_cycles) are mapped onto ``HandoffConfig`` when
        present; otherwise the bare target ``Agent`` is forwarded and core's
        ``_process_handoffs`` handles it directly.
        """
        for spec in specs:
            handoff_spec = spec.extras.get('handoff') if isinstance(spec.extras, dict) else None
            if not isinstance(handoff_spec, dict):
                continue

            source = agents.get(spec.key)
            if source is None:
                continue

            config = self._build_handoff_config(handoff_spec)

            targets = []
            for to_role in handoff_spec.get('to') or []:
                target = agents.get(to_role)
                if target is None:
                    logger.warning(
                        "handoff on %r references unknown role %r; skipping.",
                        spec.key, to_role,
                    )
                    continue
                targets.append(self._make_handoff(target, config))

            if targets:
                source.handoffs = list(source.handoffs or []) + targets
                if hasattr(source, '_process_handoffs'):
                    source._process_handoffs()

    @staticmethod
    def _build_handoff_config(handoff_spec):
        """Map the wrapper handoff dict onto a core ``HandoffConfig``.

        Only forwards keys core understands. The wrapper ``policy`` (e.g.
        "round-robin") is an orchestration hint with no core context-policy
        equivalent, so it is intentionally left untouched here.
        """
        try:
            from praisonaiagents.agent.handoff import HandoffConfig
        except ImportError:
            return None

        kwargs = {}
        if handoff_spec.get('timeout') is not None:
            try:
                kwargs['timeout_seconds'] = float(handoff_spec['timeout'])
            except (TypeError, ValueError):
                pass
        for src_key, dst_key in (('max_depth', 'max_depth'),
                                 ('max_concurrent', 'max_concurrent')):
            if handoff_spec.get(src_key) is not None:
                try:
                    kwargs[dst_key] = int(handoff_spec[src_key])
                except (TypeError, ValueError):
                    pass
        if handoff_spec.get('detect_cycles') is not None:
            kwargs['detect_cycles'] = bool(handoff_spec['detect_cycles'])

        return HandoffConfig(**kwargs) if kwargs else None

    @staticmethod
    def _make_handoff(target, config):
        """Wrap a target ``Agent`` in a core ``Handoff`` (with optional config),
        falling back to the bare agent when core is unavailable."""
        try:
            from praisonaiagents.agent.handoff import Handoff
        except ImportError:
            return target
        return Handoff(agent=target, config=config) if config else Handoff(agent=target)

    @staticmethod
    def _resolve_session_continuity(cli_config):
        """Resolve (session_id, auto_save) session-continuity settings from cli_config.

        Mirrors the single-agent CLI path: the wrapper threads
        ``resume_session`` / ``auto_save`` (set by ``--session``/``--continue``/
        ``--fork``) through ``cli_config`` (``vars(self.args)``). Returns a
        ``(session_id, auto_save)`` tuple where ``session_id`` is the id to
        restore from (may be ``None``) and ``auto_save`` is the id to persist
        under after the run (``None`` when ``--no-save`` / no session).
        """
        cfg = cli_config or {}
        resume = cfg.get('resume_session')
        auto_save = cfg.get('auto_save')
        return resume, auto_save

    _SESSION_CHAT_HISTORY_KEY = "_cli_session_chat_history"

    @classmethod
    def _capture_team_chat_history(cls, team) -> None:
        """Snapshot each agent's chat history into team state before saving.

        Core ``AgentTeam.save_session_state`` persists ``team._state`` but not
        per-agent ``chat_history``. To give YAML/team runs the same
        conversation continuity as the single-agent path (which restores
        ``agent.chat_history``), we stash a role-keyed history map into team
        state so it rides along with the existing save/restore machinery — no
        core change and no new params.
        """
        history_map: Dict[str, Any] = {}
        for agent in getattr(team, "agents", []) or []:
            key = getattr(agent, "display_name", None) or getattr(agent, "name", None)
            if not key:
                continue
            history = getattr(agent, "chat_history", None)
            if history:
                history_map[key] = list(history)
        if history_map:
            team.set_state(cls._SESSION_CHAT_HISTORY_KEY, history_map)

    @classmethod
    def _rehydrate_team_chat_history(cls, team) -> None:
        """Inject previously captured chat history back into team agents.

        Runs after ``restore_session_state`` has merged the saved team state.
        Only appends messages the agent does not already have so a fork/resume
        never duplicates history.
        """
        history_map = team.get_state(cls._SESSION_CHAT_HISTORY_KEY)
        if not isinstance(history_map, dict) or not history_map:
            return
        for agent in getattr(team, "agents", []) or []:
            key = getattr(agent, "display_name", None) or getattr(agent, "name", None)
            saved = history_map.get(key)
            if not saved:
                continue
            current = getattr(agent, "chat_history", None)
            if current is None:
                continue
            existing = {
                (m.get("role"), m.get("content"))
                for m in current
                if isinstance(m, dict)
            }
            for msg in saved:
                if not isinstance(msg, dict):
                    continue
                marker = (msg.get("role"), msg.get("content"))
                if marker not in existing:
                    current.append(msg)
                    existing.add(marker)

    def _build_team(self, config, agents, tasks, model_name, *, session_active=False):
        """Build AgentTeam from agents and tasks.

        When ``session_active`` is set (a ``--session``/``--continue``/``--fork``
        run), shared memory is force-enabled so the team exposes the
        ``shared_memory`` that ``save_session_state``/``restore_session_state``
        require to persist and rehydrate team conversation state.
        """
        from praisonaiagents import AgentTeam
        
        memory = config.get('memory', False) or session_active
        
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
        # Plain sync callers get the shared background loop via run_sync. Callers
        # already inside a running event loop (FastAPI handler, Jupyter, async
        # test) must not take the sync path — blocking the loop for the full
        # agent run is the "async-safe" pathology this project forbids — so we
        # fail loudly and point them at the awaitable ``arun``.
        import asyncio

        coro = self.arun(
            config, llm_config, topic,
            tools_dict=tools_dict,
            agent_callback=agent_callback,
            task_callback=task_callback,
            cli_config=cli_config,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            from praisonai._async_bridge import run_sync
            return run_sync(coro)

        # Inside a running loop: run_sync_or_offload enforces the strict
        # no-loop-blocking policy (and honours PRAISONAI_ALLOW_LOOP_BLOCKING for
        # callers that opt back into the legacy blocking behaviour), raising a
        # RuntimeError that steers callers to ``await adapter.arun(...)``.
        from praisonai._async_bridge import run_sync_or_offload
        return run_sync_or_offload(coro, thread_name="praisonai-adapter-sync")

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
        # Observability init/finalize is owned by the generator via the
        # observability_session context manager, so the adapter no longer
        # finalizes here — this keeps the lifecycle symmetric across every
        # adapter and prevents double-finalize.
        interactive_runtime = None
        try:
            # Import PraisonAI components only when needed
            from praisonaiagents import Agent as PraisonAgent, Task as PraisonTask, AgentTeam
            import os

            logger.info("Starting PraisonAI async execution...")

            # Get model from llm_config
            model_name = self._pick_model(llm_config)

            # Initialize InteractiveRuntime for ACP/LSP if enabled
            interactive_runtime = await self._astart_interactive_runtime(config)

            # Inject agent-centric tools if runtime is available. Thread the
            # generator's per-run tool_timeout wrap (stashed in cli_config) so the
            # injected ACP/LSP tools carry the same timeout guard as YAML tools.
            wrap = (cli_config or {}).get("_tool_timeout_wrap")
            tools_dict = self._maybe_inject_centric_tools(
                interactive_runtime, tools_dict, wrap=wrap
            )

            # Build agents and tasks from config. Thread the per-agent
            # tool_timeout wrap resolver (heterogeneous budgets) from cli_config
            # so each agent's tools carry its own timeout, not a shared one.
            agent_tool_wrap_resolver = (cli_config or {}).get("_agent_tool_wrap_resolver")
            agents, tasks = self._build_agents_and_tasks(
                config, topic, tools_dict, agent_callback, task_callback, model_name,
                agent_tool_wrap_resolver=agent_tool_wrap_resolver,
            )

            # Resolve CLI session continuity (--continue/--session/--fork) that the
            # wrapper threads through cli_config. When a session is active the team
            # is given shared memory so team state can be persisted/rehydrated.
            resume_session, auto_save = self._resolve_session_continuity(cli_config)
            session_active = bool(resume_session or auto_save)

            # Create the team
            team = self._build_team(
                config, agents, tasks, model_name, session_active=session_active
            )

            # Rehydrate prior team state before kickoff so a resumed/forked YAML
            # run continues where it left off, using the existing core API.
            if resume_session:
                if team.restore_session_state(resume_session):
                    # Core restore only merges team._state; re-inject the
                    # per-agent chat history we stashed there so the LLM
                    # actually continues the prior exchange (parity with the
                    # single-agent path).
                    self._rehydrate_team_chat_history(team)
                    logger.info(f"Restored session state: {resume_session}")
                else:
                    logger.info(f"No prior state for session: {resume_session}")

            # Bridge the team's aggregate per-step events onto the CLI
            # structured output stream so `--output stream-json` on a YAML/team
            # run emits the same per-agent NDJSON events as a single-agent run.
            # Best-effort and a no-op outside stream-json (the bridge guards on
            # its own `active`), so serve/jobs and non-CLI callers are unaffected.
            bridge, _ = self._attach_stream_bridge(team)
            try:
                # Use native async path
                response = await team.astart()
            except Exception as run_error:
                # Emit a terminal `run.error` so `--output stream-json`
                # consumers can distinguish a failed team run from an
                # incomplete/still-running one, matching the single-agent
                # path. Best-effort; never mask the original exception.
                if bridge is not None:
                    try:
                        bridge.emit_run_error(str(run_error))
                    except Exception:
                        logger.debug("Stream bridge run.error emit failed", exc_info=True)
                raise
            finally:
                self._detach_stream_bridge(team, bridge)
            result = f"### PraisonAI Output ###\n{response}" if response else "### PraisonAI Output ###\nTask completed."
            if bridge is not None:
                bridge.emit_run_result(response, ok=True)

            # Persist team state after kickoff so the run can be resumed later
            # (respects --no-save, which leaves auto_save unset).
            if auto_save:
                try:
                    # Snapshot per-agent chat history into team state so the
                    # existing save machinery persists the conversation, not
                    # just the bookkeeping _state dict.
                    self._capture_team_chat_history(team)
                    team.save_session_state(auto_save)
                    logger.info(f"Saved session state: {auto_save}")
                except Exception as e:  # never fail a completed run on save
                    logger.warning(f"Failed to save session state '{auto_save}': {e}")

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
    
    @staticmethod
    def _attach_stream_bridge(team):
        """Attach the CLI stream-json bridge to a team's aggregate emitter.

        Returns ``(bridge, output)``. Both are ``None`` when the CLI output
        layer is unavailable (non-CLI callers) or when not in a structured
        output mode (the bridge is inactive), so this is a safe no-op outside
        ``praisonai run ... --output stream-json``.
        """
        try:
            from praisonai_code.cli.output import get_output_controller, attach_bridge
        except ImportError:
            return None, None
        try:
            output = get_output_controller()
            bridge = attach_bridge(team, output)
            if bridge is not None:
                bridge.emit_run_start()
            return bridge, output
        except Exception:
            logger.debug("Stream bridge attach failed", exc_info=True)
            return None, None

    @staticmethod
    def _detach_stream_bridge(team, bridge):
        """Detach a previously attached stream bridge (best-effort)."""
        if bridge is None:
            return
        try:
            from praisonai_code.cli.output import detach_bridge
            detach_bridge(team, bridge)
        except Exception:
            logger.debug("Stream bridge detach failed", exc_info=True)

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
