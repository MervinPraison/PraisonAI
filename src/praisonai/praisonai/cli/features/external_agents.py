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

from typing import Dict, Any, List, Optional, Tuple

from .base import FlagHandler


class ExternalAgentsHandler(FlagHandler):
    """
    Handler for --external-agent flag.
    
    Integrates external AI coding CLI tools as agent tools.
    
    Example:
        praisonai "Refactor the auth module" --external-agent claude
        praisonai "Analyze this codebase" --external-agent gemini
    """
    
    # Mapping of integration names to their module paths
    INTEGRATIONS = {
        "claude": "claude_code.ClaudeCodeIntegration",
        "gemini": "gemini_cli.GeminiCLIIntegration",
        "codex": "codex_cli.CodexCLIIntegration",
        "cursor": "cursor_cli.CursorCLIIntegration",
    }
    
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
        return "External AI CLI tool to use (claude, gemini, codex, cursor)"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if integrations module is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonai.integrations") is not None:
                return True, ""
            return False, "Integrations module not available"
        except ImportError:
            return False, "Integrations module not available"
    
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
        if name not in self.INTEGRATIONS:
            raise ValueError(f"Unknown integration: {name}. Available: {list(self.INTEGRATIONS.keys())}")
        
        # Check cache first
        cache_key = f"{name}_{hash(frozenset(options.items()))}"
        if cache_key in self._integration_cache:
            return self._integration_cache[cache_key]
        
        # Lazy import the integration
        module_path = self.INTEGRATIONS[name]
        module_name, class_name = module_path.rsplit(".", 1)
        
        import importlib
        module = importlib.import_module(f"praisonai.integrations.{module_name}")
        integration_class = getattr(module, class_name)
        
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
        return list(self.INTEGRATIONS.keys())
    
    def check_availability(self) -> Dict[str, bool]:
        """
        Check availability of all integrations.
        
        Returns:
            Dict mapping integration name to availability
        """
        availability = {}
        for name in self.INTEGRATIONS:
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
    
    def _get_install_instructions(self, name: str) -> str:
        """Get installation instructions for an integration."""
        instructions = {
            "claude": "npm install -g @anthropic-ai/claude-code",
            "gemini": "npm install -g @anthropic-ai/gemini-cli",
            "codex": "npm install -g @openai/codex",
            "cursor": "Download from cursor.com",
        }
        return instructions.get(name, "See documentation")
