"""
External Agents Handler for CLI.

Provides integration with external AI coding CLI tools:
- Claude Code CLI
- Gemini CLI
- OpenAI Codex CLI
- Cursor CLI

Usage:
    praisonai "Refactor the code" --external-agent claude
    praisonai "Analyze codebase" --external-agent gemini
    praisonai "Fix bugs" --external-agent codex
    praisonai "Add tests" --external-agent cursor
"""

from typing import Dict, Any, Iterator, List, Mapping, Optional, Tuple

from .base import FlagHandler


_WRAPPER_TOO_OLD = (
    "your installed 'praisonai' wrapper is too old for --external-agent "
    "(missing external_agent_catalog); upgrade with: pip install -U praisonai"
)


def _resolve_catalog_fn():
    """Return ``(fn, error)`` for the wrapper's ``external_agent_catalog``.

    Distinguishes three states so a version-skewed install is not mistaken for
    an empty catalog (issue #4167):

    - wrapper absent            -> ``(None, None)`` (standalone: degrade quietly)
    - wrapper present but old    -> ``(None, _WRAPPER_TOO_OLD)`` (report it)
    - wrapper present and current-> ``(fn, None)``

    Routed through ``_wrapper_bridge`` so ``praisonai-code`` keeps its C7/C8
    import boundary (no direct ``from praisonai.*`` reverse import).
    """
    from praisonai_code._wrapper_bridge import get_wrapper_attr, wrapper_available

    if not wrapper_available():
        return None, None
    try:
        return get_wrapper_attr(
            "praisonai.integrations.registry", "external_agent_catalog"
        ), None
    except AttributeError:
        # Wrapper importable but predates external_agent_catalog: a mixed-version
        # install. Surface it rather than silently returning ``{}``.
        return None, _WRAPPER_TOO_OLD
    except ImportError:
        return None, None


def _catalog() -> Dict[str, Dict[str, Any]]:
    """Live view of the external-agent registry (lazy: ``praisonai`` is optional).

    Degrades to an empty catalog when the wrapper is unavailable (absent) *or*
    too old, so passive listing surfaces (``--help`` choices, UI toggles) never
    raise. The execution path uses :func:`_require_catalog` instead, which
    surfaces a too-old wrapper as an error rather than a misleading empty list.
    """
    fn, _error = _resolve_catalog_fn()
    if fn is None:
        return {}
    return fn()


def _require_catalog() -> Dict[str, Dict[str, Any]]:
    """Resolve the catalog for the *execution* path (issue #4167 defect 3).

    Unlike :func:`_catalog`, a wrapper that is present but predates
    ``external_agent_catalog`` raises the version-skew error so the user sees the
    upgrade guidance instead of a misleading "Unknown integration". An absent
    wrapper still degrades to an empty catalog (standalone stays usable).
    """
    fn, error = _resolve_catalog_fn()
    if fn is None:
        if error is not None:
            raise RuntimeError(error)
        return {}
    return fn()


class _RegistryIntegrations(Mapping):
    """Read-only ``name -> integration class`` view backed by the registry.

    Kept so the historical ``ExternalAgentsHandler.INTEGRATIONS`` attribute
    still supports ``in``, iteration and ``[]`` — but it is now a *view*, not a
    hand-written copy that can drift from the registry.
    """

    def __getitem__(self, key: str) -> Any:
        return _catalog()[key]["cls"]

    def __iter__(self) -> Iterator[str]:
        return iter(_catalog())

    def __len__(self) -> int:
        return len(_catalog())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"_RegistryIntegrations({list(self)!r})"


class ExternalAgentsHandler(FlagHandler):
    """
    Handler for --external-agent flag.
    
    Integrates external AI coding CLI tools as agent tools.
    
    Example:
        praisonai "Refactor the auth module" --external-agent claude
        praisonai "Analyze this codebase" --external-agent gemini
    """
    
    # Live view of praisonai.integrations.registry — NOT a hand-written copy.
    INTEGRATIONS = _RegistryIntegrations()
    
    def __init__(self, verbose: bool = False):
        """Initialize the handler."""
        super().__init__(verbose)
        self._integration_cache: Dict[str, Any] = {}
    
    @property
    def feature_name(self) -> str:
        """Return the feature name."""
        return "external_agents"
    
    @property
    def flag_name(self) -> str:
        """Return the flag name."""
        return "external-agent"
    
    @property
    def flag_help(self) -> str:
        """Return the flag help text."""
        names = ", ".join(self.list_integrations()) or "none registered"
        return f"External AI CLI tool to use ({names})"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if the integrations module is available *and* new enough.

        A version-skewed install (new ``praisonai-code`` against a ``praisonai``
        wrapper predating ``external_agent_catalog``) is reported as too old
        rather than passing here and then yielding an empty catalog downstream.
        """
        try:
            import importlib.util
            if importlib.util.find_spec("praisonai.integrations") is None:
                return False, "Integrations module not available"
        except ImportError:
            return False, "Integrations module not available"

        _fn, error = _resolve_catalog_fn()
        if error is not None:
            return False, error
        return True, ""
    
    def get_integration(self, name: str, **options):
        """
        Get an integration instance by name.
        
        Args:
            name: Integration name (claude, gemini, codex, cursor)
            **options: Options to pass to the integration
            
        Returns:
            Integration instance
            
        Raises:
            ValueError: If integration name is invalid
        """
        catalog = _require_catalog()
        if name not in catalog:
            raise ValueError(f"Unknown integration: {name}. Available: {list(catalog)}")
        
        # Check cache first
        cache_key = f"{name}_{hash(frozenset(options.items()))}"
        if cache_key in self._integration_cache:
            return self._integration_cache[cache_key]
        
        # Resolve through the registry (built-ins and entry-point plugins alike)
        integration_class = catalog[name]["cls"]
        
        # Create instance with options
        integration = integration_class(**options)
        
        # Cache it
        self._integration_cache[cache_key] = integration
        
        return integration
    
    def list_integrations(self) -> List[str]:
        """
        List all available integration names.
        
        Returns:
            List of integration names
        """
        return list(_catalog())
    
    def check_availability(self) -> Dict[str, bool]:
        """
        Check availability of all integrations.
        
        Returns:
            Dict mapping integration name to availability
        """
        availability = {}
        for name in _catalog():
            try:
                integration = self.get_integration(name)
                availability[name] = integration.is_available
            except Exception:
                availability[name] = False
        return availability
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply external agent configuration to agent config.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Integration name or dict with name and options
            
        Returns:
            Modified configuration with external agent tool
        """
        if not flag_value:
            return config
        
        # Handle both string and dict formats
        if isinstance(flag_value, str):
            name = flag_value
            options = {}
        elif isinstance(flag_value, dict):
            name = flag_value.get("name", "")
            options = {k: v for k, v in flag_value.items() if k != "name"}
        else:
            return config
        
        try:
            integration = self.get_integration(name, **options)
            
            if integration.is_available:
                # Add tool to existing tools
                existing_tools = config.get("tools", [])
                if isinstance(existing_tools, list):
                    existing_tools.append(integration.as_tool())
                else:
                    existing_tools = [integration.as_tool()]
                config["tools"] = existing_tools
                
                self.print_status(f"🔌 External agent connected: {name}", "success")
            else:
                self.print_status(f"⚠️ External agent not available: {name}", "warning")
                
        except ValueError as e:
            self.print_status(str(e), "error")
        except Exception as e:
            self.print_status(f"Failed to connect external agent: {e}", "error")
        
        return config
    
    def execute(
        self, 
        integration_name: str = None, 
        **options
    ) -> Optional[Any]:
        """
        Execute external agent setup.
        
        Args:
            integration_name: Name of the integration
            **options: Options for the integration
            
        Returns:
            Integration instance or None
        """
        if not integration_name:
            # List available integrations
            self.print_status("\n🔧 Available External Agents:", "info")
            self.print_status("-" * 40, "info")
            
            availability = self.check_availability()
            for name, available in availability.items():
                status = "✅ Available" if available else "❌ Not installed"
                self.print_status(f"  {name}: {status}", "info")
            
            return None
        
        try:
            integration = self.get_integration(integration_name, **options)
            
            if integration.is_available:
                self.print_status(f"🔌 External agent ready: {integration_name}", "success")
                return integration
            else:
                self.print_status(f"⚠️ External agent not installed: {integration_name}", "warning")
                self.print_status(f"   Install with: {self._get_install_instructions(integration_name)}", "info")
                return None
                
        except ValueError as e:
            self.print_status(str(e), "error")
            return None
        except RuntimeError as e:
            # Version-skewed wrapper (issue #4167): surface the upgrade guidance
            # instead of a misleading "Unknown integration" error.
            self.print_status(str(e), "error")
            return None
    
    def _get_install_instructions(self, name: str) -> str:
        """Get installation instructions for an integration."""
        meta = _catalog().get(name)
        return meta["install"] if meta else "See documentation"
