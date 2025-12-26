"""
Observability CLI Handler

CLI commands for managing observability providers.
Usage: praisonai obs <command>
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from .base import FlagHandler


class ObservabilityHandler(FlagHandler):
    """
    Handler for observability CLI commands.
    
    Commands:
        praisonai obs list          - List available providers
        praisonai obs doctor        - Check provider connectivity
        praisonai obs init <name>   - Initialize a provider
    """
    
    @property
    def feature_name(self) -> str:
        return "observability"
    
    @property
    def flag_name(self) -> str:
        return "obs"
    
    @property
    def flag_help(self) -> str:
        return "Observability commands (list, doctor, init)"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if observability module is available."""
        try:
            from praisonai_tools.observability import obs
            return True, ""
        except ImportError:
            return False, "Observability requires praisonai-tools. Install with: pip install praisonai-tools"
    
    def list_providers(self) -> Dict[str, Any]:
        """List all available observability providers."""
        result = {
            "registered": [],
            "available": [],
            "configured": [],
        }
        
        try:
            from praisonai_tools.observability.manager import ObservabilityManager
            from praisonai_tools.observability.config import PROVIDER_ENV_KEYS
            
            mgr = ObservabilityManager()
            
            # Get all registered providers
            result["registered"] = mgr.list_providers()
            
            # Check which have env vars configured
            for provider, keys in PROVIDER_ENV_KEYS.items():
                if all(os.getenv(key) for key in keys):
                    result["configured"].append(provider)
            
            # Check which SDKs are available
            for provider in result["registered"]:
                try:
                    mgr._load_provider(provider)
                    if provider in mgr._providers:
                        provider_class = mgr._providers[provider]
                        instance = provider_class()
                        if instance.is_available():
                            result["available"].append(provider)
                except Exception:
                    pass
            
        except ImportError:
            pass
        
        return result
    
    def doctor(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Run diagnostics on observability setup."""
        try:
            from praisonai_tools.observability import obs
            
            if provider:
                obs.init(provider=provider)
            
            return obs.doctor()
            
        except ImportError:
            return {
                "error": "praisonai-tools not installed",
                "enabled": False,
            }
    
    def init_provider(self, provider: str, **kwargs) -> bool:
        """Initialize a specific provider."""
        try:
            from praisonai_tools.observability import obs
            return obs.init(provider=provider, **kwargs)
        except ImportError:
            return False
    
    def execute(self, action: str = "list", **kwargs) -> Any:
        """
        Execute observability command.
        
        Args:
            action: Command to execute (list, doctor, init)
            **kwargs: Additional arguments
            
        Returns:
            Command result
        """
        if action == "list":
            return self._execute_list()
        elif action == "doctor":
            return self._execute_doctor(kwargs.get("provider"))
        elif action == "init":
            return self._execute_init(kwargs.get("provider"), **kwargs)
        else:
            self.print_status(f"Unknown action: {action}", "error")
            return None
    
    def _execute_list(self) -> Dict[str, Any]:
        """Execute list command."""
        result = self.list_providers()
        
        self.print_status("\n📊 Observability Providers", "info")
        self.print_status("=" * 40, "info")
        
        # Provider status table
        all_providers = [
            "agentops", "langfuse", "langsmith", "traceloop",
            "arize_phoenix", "openlit", "langtrace", "langwatch",
            "datadog", "mlflow", "opik", "portkey",
            "braintrust", "maxim", "weave", "neatlogs",
            "langdb", "atla", "patronus", "truefoundry",
        ]
        
        for provider in all_providers:
            status_parts = []
            if provider in result.get("available", []):
                status_parts.append("✅ SDK")
            else:
                status_parts.append("❌ SDK")
            
            if provider in result.get("configured", []):
                status_parts.append("🔑 Keys")
            else:
                status_parts.append("⚪ Keys")
            
            status = " | ".join(status_parts)
            self.print_status(f"  {provider:20} {status}", "info")
        
        self.print_status("\n✅ = Available  ❌ = Not installed  🔑 = API key configured", "info")
        
        return result
    
    def _execute_doctor(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Execute doctor command."""
        result = self.doctor(provider)
        
        self.print_status("\n🩺 Observability Diagnostics", "info")
        self.print_status("=" * 40, "info")
        
        self.print_status(f"  Enabled: {result.get('enabled', False)}", "info")
        self.print_status(f"  Provider: {result.get('provider', 'None')}", "info")
        
        if result.get("connection_status") is not None:
            status = "✅" if result["connection_status"] else "❌"
            self.print_status(f"  Connection: {status} {result.get('connection_message', '')}", "info")
        
        if result.get("available_providers"):
            self.print_status(f"  Available: {', '.join(result['available_providers'])}", "info")
        
        return result
    
    def _execute_init(self, provider: str, **kwargs) -> bool:
        """Execute init command."""
        if not provider:
            self.print_status("Provider name required. Usage: praisonai obs init <provider>", "error")
            return False
        
        success = self.init_provider(provider, **kwargs)
        
        if success:
            self.print_status(f"✅ {provider} initialized successfully", "success")
        else:
            self.print_status(f"❌ Failed to initialize {provider}", "error")
            self.print_status(f"   Check that {provider} SDK is installed and API keys are set", "info")
        
        return success
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """Apply observability to agent config."""
        if flag_value:
            try:
                from praisonai_tools.observability import obs
                
                if isinstance(flag_value, str):
                    obs.init(provider=flag_value)
                else:
                    obs.init()
                
                self.print_status("📊 Observability enabled", "success")
            except ImportError:
                self.print_status("Observability requires praisonai-tools", "warning")
        
        return config


# Provider environment variable reference
PROVIDER_SETUP_GUIDE = {
    "agentops": {
        "env_vars": ["AGENTOPS_API_KEY"],
        "install": "pip install agentops",
        "docs": "https://agentops.ai/",
    },
    "langfuse": {
        "env_vars": ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
        "install": "pip install opentelemetry-sdk opentelemetry-exporter-otlp",
        "docs": "https://langfuse.com/",
    },
    "langsmith": {
        "env_vars": ["LANGSMITH_API_KEY"],
        "install": "pip install opentelemetry-sdk opentelemetry-exporter-otlp",
        "docs": "https://smith.langchain.com/",
    },
    "traceloop": {
        "env_vars": ["TRACELOOP_API_KEY"],
        "install": "pip install traceloop-sdk",
        "docs": "https://traceloop.com/",
    },
    "arize_phoenix": {
        "env_vars": ["PHOENIX_API_KEY"],
        "install": "pip install arize-phoenix openinference-instrumentation",
        "docs": "https://phoenix.arize.com/",
    },
    "openlit": {
        "env_vars": [],
        "install": "pip install openlit",
        "docs": "https://github.com/openlit/openlit",
    },
    "langtrace": {
        "env_vars": ["LANGTRACE_API_KEY"],
        "install": "pip install langtrace-python-sdk",
        "docs": "https://langtrace.ai/",
    },
    "langwatch": {
        "env_vars": ["LANGWATCH_API_KEY"],
        "install": "pip install langwatch",
        "docs": "https://langwatch.ai/",
    },
    "datadog": {
        "env_vars": ["DD_API_KEY"],
        "install": "pip install ddtrace",
        "docs": "https://www.datadoghq.com/product/llm-observability/",
    },
    "mlflow": {
        "env_vars": ["MLFLOW_TRACKING_URI"],
        "install": "pip install mlflow",
        "docs": "https://mlflow.org/",
    },
    "opik": {
        "env_vars": ["OPIK_API_KEY"],
        "install": "pip install opik",
        "docs": "https://www.comet.com/docs/opik/",
    },
    "portkey": {
        "env_vars": ["PORTKEY_API_KEY"],
        "install": "pip install portkey-ai",
        "docs": "https://portkey.ai/",
    },
    "braintrust": {
        "env_vars": ["BRAINTRUST_API_KEY"],
        "install": "pip install braintrust",
        "docs": "https://www.braintrust.dev/",
    },
    "maxim": {
        "env_vars": ["MAXIM_API_KEY"],
        "install": "pip install maxim-py",
        "docs": "https://getmaxim.ai/",
    },
    "weave": {
        "env_vars": ["WANDB_API_KEY"],
        "install": "pip install weave",
        "docs": "https://weave-docs.wandb.ai/",
    },
}
