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
    install_hint = 'pip install "praisonai-frameworks[autogen]"'  # v0.2 only
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
            f"Install with 'pip install praisonai-frameworks[autogen]' for v0.2 or 'pip install praisonai-frameworks[autogen-v4]' for v0.4"
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
        
        from ._config_builder import build_agent_specs

        agents = {}
        tasks = []

        # Single canonical YAML -> spec conversion (shared across adapters)
        specs = build_agent_specs(config, topic, tools_dict, self._format_template)

        # Create agents from the normalized specs
        for spec in specs:
            # Create AutoGen assistant agent
            agents[spec.key] = autogen.AssistantAgent(
                name=spec.role,
                llm_config=llm_config_dict,
                system_message=spec.backstory +
                             ". Must Reply \"TERMINATE\" in the end when everything is done.",
            )
            
            # NOTE: AutoGen v0.2 tool/function registration (register_for_llm /
            # register_for_execution) is intentionally not wired here yet — the
            # resolved callables live on ``spec.tools``. Tracked separately so we
            # don't ship a half-registration that silently no-ops.
            
            # Prepare tasks
            for task_spec in spec.tasks:
                chat_task = {
                    "recipient": agents[spec.key],
                    "message": task_spec.description,
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
    install_hint = 'pip install "praisonai-frameworks[autogen-v4]"'
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
    install_hint = 'pip install "praisonai-frameworks[ag2]"'
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
    install_hint = 'pip install "praisonai-frameworks[autogen]"'
    is_router = True
    
    def is_available(self) -> bool:
        """Check if any AutoGen variant is runnable.

        Mirrors ``resolve_alias()``'s registry-backed selectability so router
        availability stays consistent: ``registry.is_available("autogen")`` only
        reports True when a concrete variant is registered AND available, and
        thus actually dispatchable by ``resolve()``. Raw v4/ag2 packages alone
        (no registered adapter) correctly report unavailable.
        """
        try:
            from .registry import get_default_registry
            registry = get_default_registry()
            registered = set(registry.list_names())
        except ImportError:
            return False
        return any(
            alias in registered and registry.is_available(alias)
            for alias in ("autogen_v2", "autogen_v4", "ag2")
        )
    
    def resolve_alias(self, config: Optional[Dict[str, Any]] = None) -> str:
        """Resolve which concrete AutoGen adapter to use.

        Only returns an alias whose concrete adapter is actually registered AND
        available, so the downstream ``registry.create(alias)`` never fails with
        an opaque lookup error. ``autogen_v4`` / ``ag2`` are unimplemented and
        unregistered by default, so explicit pins for them fall back to v0.2
        when possible, otherwise raise an actionable ``ImportError``.

        The workflow-supplied ``autogen_version`` (config/YAML) takes precedence
        over the ``AUTOGEN_VERSION`` environment variable so an explicit YAML
        pin wins over ambient env state.
        """
        requested = str(
            (config or {}).get("autogen_version")
            or os.getenv("AUTOGEN_VERSION", "auto")
        ).strip().lower()

        # A variant is selectable only if its adapter is registered in the
        # registry (built-in or entry-point) and reports availability.
        try:
            from .registry import get_default_registry
            registry = get_default_registry()
            registered = set(registry.list_names())

            def _selectable(alias: str) -> bool:
                return alias in registered and registry.is_available(alias)
        except ImportError:
            registered = set()

            def _selectable(alias: str) -> bool:
                return False

        v2_available = _selectable("autogen_v2")
        v4_available = _selectable("autogen_v4")
        ag2_available = _selectable("ag2")

        # Explicit version pins: honour only when the variant can actually run.
        # An explicit pin must NOT silently fall back to a different variant —
        # a workflow that depends on v0.4 / AG2 APIs would otherwise run under
        # v0.2 with different behaviour. Fail fast with an actionable error so
        # the mismatch surfaces instead of producing wrong-runtime results.
        if requested == "v0.2":
            if v2_available:
                return "autogen_v2"
            raise ImportError(
                "AUTOGEN_VERSION=v0.2 was requested, but the AutoGen v0.2 adapter "
                "is not available. Install with: pip install 'praisonai-frameworks[autogen]'."
            )
        elif requested == "v0.4":
            if v4_available:
                return "autogen_v4"
            raise ImportError(
                "AUTOGEN_VERSION=v0.4 was requested, but the v0.4 adapter is not "
                "registered or available. Install/register an autogen_v4 adapter "
                "(pip install 'praisonai-frameworks[autogen-v4]'), or unset AUTOGEN_VERSION "
                "to use auto-selection."
            )
        elif requested == "ag2":
            if ag2_available:
                return "ag2"
            raise ImportError(
                "AUTOGEN_VERSION=ag2 was requested, but the AG2 adapter is not "
                "registered or available. Install/register an AG2 adapter "
                "(pip install 'praisonai-frameworks[ag2]'), or unset AUTOGEN_VERSION to use "
                "auto-selection."
            )

        # Auto selection: prefer v2 (v4/ag2 are currently unimplemented).
        if v2_available:
            return "autogen_v2"
        if v4_available:
            return "autogen_v4"
        if ag2_available:
            return "ag2"

        # Nothing selectable.
        raise ImportError(
            "No runnable AutoGen variant is available. Install with:\n"
            "  pip install 'praisonai-frameworks[autogen]' for v0.2\n"
            "  pip install 'praisonai-frameworks[autogen-v4]' for v0.4\n"
            "  pip install 'praisonai-frameworks[ag2]' for AG2"
        )
    
    def resolve(self, *, config: Optional[Dict[str, Any]] = None) -> "BaseFrameworkAdapter":
        """Resolve to the concrete AutoGen adapter based on config/environment.
        
        This method is called by the orchestrator to get the actual adapter to use.
        
        Args:
            config: Framework configuration that may contain version hints
            
        Returns:
            The concrete AutoGen adapter instance
        """
        # Get the adapter name to use (config autogen_version wins over env)
        adapter_name = self.resolve_alias(config)
        
        # Import registry to create the concrete adapter
        from .registry import get_default_registry
        registry = get_default_registry()
        
        # Create and return the concrete adapter
        concrete_adapter = registry.create(adapter_name)
        logger.info(f"AutoGenFamilyAdapter resolved to: {adapter_name}")
        return concrete_adapter
    
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
        """Router should never run directly."""
        raise RuntimeError(
            "AutoGenFamilyAdapter.run() should not be called directly. "
            "The resolve() method should have been called first to get the concrete adapter."
        )