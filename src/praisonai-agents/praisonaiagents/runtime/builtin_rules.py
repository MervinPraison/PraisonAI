"""
Built-in migration rules for doctor.

Contains core migration rules that ship with PraisonAI,
including the cli_backend migration rule.
"""

from typing import Any, Dict, List
from .doctor_protocol import DoctorContractProtocol, Finding


class CliBackendMigrationRule:
    """
    Built-in rule to migrate cli_backend to models.<default>.runtime.
    
    Maps known cli_backend values to runtime configuration under
    the default model configuration.
    """
    
    # Mapping table for known cli_backend values
    CLI_BACKEND_MAPPING = {
        "claude-code": "claude-code",
        "openai-gpt": "openai-gpt", 
        "anthropic": "anthropic",
        "gemini": "gemini",
        # Add more mappings as needed
    }
    
    @property
    def rule_id(self) -> str:
        return "cli_backend_migration"
    
    def collect_findings(self, config: Dict[str, Any]) -> List[Finding]:
        """Detect cli_backend usage in configuration."""
        findings = []
        
        # Check for cli_backend in top-level config
        if "cli_backend" in config:
            backend_value = config["cli_backend"]
            findings.append(Finding(
                rule_id=self.rule_id,
                severity="warning",
                message=f"Legacy field 'cli_backend: {backend_value}' should be migrated to model-scoped runtime configuration",
                fix_description=f"Move cli_backend to models.<default>.runtime: {self._map_backend(backend_value)}",
                context={"field": "cli_backend", "value": backend_value, "location": "root"}
            ))
        
        # Check for cli_backend in roles
        if "roles" in config and isinstance(config["roles"], dict):
            for role_name, role_config in config["roles"].items():
                if isinstance(role_config, dict) and "cli_backend" in role_config:
                    backend_value = role_config["cli_backend"]
                    findings.append(Finding(
                        rule_id=self.rule_id,
                        severity="warning", 
                        message=f"Legacy field 'cli_backend: {backend_value}' in role '{role_name}' should be migrated",
                        fix_description=f"Move cli_backend to models.<default>.runtime: {self._map_backend(backend_value)}",
                        context={"field": "cli_backend", "value": backend_value, "location": f"roles.{role_name}"}
                    ))
        
        return findings
    
    def apply_fix(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply cli_backend migration to configuration."""
        import copy
        result = copy.deepcopy(config)
        
        # Migrate top-level cli_backend
        if "cli_backend" in result:
            backend_value = result.pop("cli_backend")
            runtime_value = self._map_backend(backend_value)
            
            # Ensure models structure exists
            if "models" not in result:
                result["models"] = {}
            if "default" not in result["models"]:
                result["models"]["default"] = {}
            
            result["models"]["default"]["runtime"] = runtime_value
        
        # Migrate cli_backend in roles
        if "roles" in result and isinstance(result["roles"], dict):
            for role_name, role_config in result["roles"].items():
                if isinstance(role_config, dict) and "cli_backend" in role_config:
                    backend_value = role_config.pop("cli_backend")
                    runtime_value = self._map_backend(backend_value)
                    
                    # Ensure models structure exists in role
                    if "models" not in role_config:
                        role_config["models"] = {}
                    if "default" not in role_config["models"]:
                        role_config["models"]["default"] = {}
                    
                    role_config["models"]["default"]["runtime"] = runtime_value
        
        return result
    
    def _map_backend(self, backend_value: str) -> str:
        """Map legacy cli_backend value to runtime id."""
        return self.CLI_BACKEND_MAPPING.get(backend_value, backend_value)