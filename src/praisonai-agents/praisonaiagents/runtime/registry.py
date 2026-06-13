"""
Doctor rules registry with lazy plugin discovery.

Manages built-in and plugin-provided migration rules.
"""

import importlib
import warnings
from typing import Any, Dict, List, Optional, Type
from .doctor_protocol import DoctorContractProtocol, Finding
from .builtin_rules import CliBackendMigrationRule


class DoctorRulesRegistry:
    """Registry for doctor migration rules with lazy plugin discovery."""
    
    def __init__(self):
        self._rules: List[DoctorContractProtocol] = []
        self._plugins_loaded = False
    
    def register_rule(self, rule: DoctorContractProtocol) -> None:
        """Register a migration rule."""
        if not isinstance(rule, type(rule)) or not hasattr(rule, 'rule_id'):
            raise TypeError("Rule must implement DoctorContractProtocol")
        
        # Check for duplicate rule IDs
        for existing_rule in self._rules:
            if existing_rule.rule_id == rule.rule_id:
                warnings.warn(f"Duplicate rule ID '{rule.rule_id}' - replacing existing rule")
                self._rules.remove(existing_rule)
                break
        
        self._rules.append(rule)
    
    def get_rules(self) -> List[DoctorContractProtocol]:
        """Get all registered rules, loading plugins if not already loaded."""
        if not self._plugins_loaded:
            self._load_builtin_rules()
            self._load_plugin_rules()
            self._plugins_loaded = True
        
        return self._rules.copy()
    
    def get_rule(self, rule_id: str) -> Optional[DoctorContractProtocol]:
        """Get a specific rule by ID."""
        for rule in self.get_rules():
            if rule.rule_id == rule_id:
                return rule
        return None
    
    def collect_all_findings(self, config: Dict[str, Any]) -> List[Finding]:
        """Collect findings from all registered rules."""
        all_findings = []
        for rule in self.get_rules():
            try:
                findings = rule.collect_findings(config)
                all_findings.extend(findings)
            except Exception as e:
                # Log error but continue with other rules
                warnings.warn(f"Error in rule '{rule.rule_id}': {e}")
        
        return all_findings
    
    def apply_all_fixes(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply fixes from all rules that have findings."""
        result = config.copy()
        
        for rule in self.get_rules():
            try:
                findings = rule.collect_findings(result)
                if findings:
                    result = rule.apply_fix(result)
            except Exception as e:
                warnings.warn(f"Error applying fix for rule '{rule.rule_id}': {e}")
        
        return result
    
    def _load_builtin_rules(self) -> None:
        """Load built-in migration rules."""
        # Register built-in cli_backend migration rule
        self.register_rule(CliBackendMigrationRule())
    
    def _load_plugin_rules(self) -> None:
        """Discover and load plugin-provided rules via entry points."""
        try:
            import pkg_resources
            for entry_point in pkg_resources.iter_entry_points('praisonai.doctor_contracts'):
                try:
                    rule_class = entry_point.load()
                    if callable(rule_class):
                        rule_instance = rule_class()
                        self.register_rule(rule_instance)
                except Exception as e:
                    warnings.warn(f"Failed to load doctor rule from {entry_point.name}: {e}")
        except ImportError:
            # pkg_resources not available, try importlib.metadata (Python 3.8+)
            try:
                from importlib.metadata import entry_points
                eps = entry_points()
                if hasattr(eps, 'select'):
                    # Python 3.10+ API
                    doctor_eps = eps.select(group='praisonai.doctor_contracts')
                else:
                    # Python 3.8-3.9 API
                    doctor_eps = eps.get('praisonai.doctor_contracts', [])
                
                for entry_point in doctor_eps:
                    try:
                        rule_class = entry_point.load()
                        if callable(rule_class):
                            rule_instance = rule_class()
                            self.register_rule(rule_instance)
                    except Exception as e:
                        warnings.warn(f"Failed to load doctor rule from {entry_point.name}: {e}")
            except ImportError:
                # No entry point discovery available
                pass


# Global registry instance
_default_registry = DoctorRulesRegistry()


def get_default_registry() -> DoctorRulesRegistry:
    """Get the default doctor rules registry."""
    return _default_registry


def register_rule(rule: DoctorContractProtocol) -> None:
    """Register a rule with the default registry."""
    _default_registry.register_rule(rule)


def get_rules() -> List[DoctorContractProtocol]:
    """Get all rules from the default registry."""
    return _default_registry.get_rules()


def collect_findings(config: Dict[str, Any]) -> List[Finding]:
    """Collect findings from all rules in the default registry."""
    return _default_registry.collect_all_findings(config)


def apply_fixes(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply fixes from all rules in the default registry."""
    return _default_registry.apply_all_fixes(config)